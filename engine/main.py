"""
Orchestrates the full reserving exercise: reads the validated triangle and
assumptions from Postgres, computes Chain Ladder / Expected Claims /
Bornhuetter-Ferguson under the base scenario and under the tail-plus-
inflation stress scenario, values the Adverse Development Cover against the
stress scenario, solves for the breakeven inflation rate, and writes the
results back to Postgres as marts.fct_reserve_results and
marts.fct_reinsurance_valuation.

The loss trend is a genuine input choice, not something always computed
two ways: --trend-source picks "assumed" (the seeded judgmental value, or
--trend-value to override it), "estimated" (fit from the claims
themselves, see engine/estimation.py), or "both" to get one run of each in
a single invocation. Whichever is chosen, every parameter used (plus the
*other* trend value, for reference even when it wasn't the one used) is
logged to fct_reserving_run_parameters, and results are appended to
fct_reserve_results / fct_reinsurance_valuation rather than replacing
them, so past runs stay comparable instead of overwriting each other. See
engine/tracking.py and docs/reserving-engine.md ("Every run is tracked, not
overwritten").

Every run gets its own run_id (one per trend source produced), and every
invocation of this script gets its own invocation_id shared by whichever
run(s) it produces, so "these came from the same button-press" is a real,
explicit fact rather than something inferred from matching timestamps.

Run: python -m engine.main [--trend-source assumed|estimated|both]
                           [--trend-value 0.06] [--label "a note"]
"""
from datetime import datetime, timezone

import pandas as pd

from engine import credibility, estimation, extension, io, methods, reinsurance, tracking
from engine.triangle import compute_cdfs, compute_ldfs, latest_diagonal

LATEST_YEAR = 2025

# earned_premium_000 is in GBP thousands; every claims figure (paid,
# ultimate) is in raw GBP. This is the one place that unit conversion
# happens, so nothing downstream needs to think about it again.
PREMIUM_UNITS = 1000


def build_base_context(triangle, premium_rate, assumptions_by_group, loss_trend_by_group: dict, claim_counts, cred_full: float, mature_years: list):
    """Everything needed by both the base and the extension scenario:
    CDFs, the latest diagonal, on-level premium, trend factors, and the
    credibility-weighted a priori loss ratio per rating group.

    loss_trend_by_group is passed in rather than read from assumptions
    directly, since it may be the single assumed value broadcast to every
    group, or a per-group estimate from engine/estimation.py."""
    ldfs = compute_ldfs(triangle)
    cdfs = compute_cdfs(ldfs)
    diagonal = latest_diagonal(triangle)

    context = {}
    for group in sorted(triangle.rating_group.unique()):
        group_diag = diagonal[diagonal.rating_group == group].set_index("accident_year")
        cdf_by_age = dict(zip(cdfs[cdfs.rating_group == group].dev_age_months, cdfs[cdfs.rating_group == group].cdf))
        cdf_at_latest = {y: cdf_by_age[row.latest_dev_age_months] for y, row in group_diag.iterrows()}

        rate = premium_rate[premium_rate.rating_group == group].set_index("accident_year")
        cumulative_rate_index = rate["cumulative_rate_index"].to_dict()
        olf = credibility.on_level_factor(cumulative_rate_index, LATEST_YEAR)
        earned_premium = (rate["earned_premium_000"] * PREMIUM_UNITS).to_dict()
        on_level_premium = {y: earned_premium[y] * olf[y] for y in earned_premium}

        trend = {y: credibility.trend_factor(y, LATEST_YEAR, loss_trend_by_group[group]) for y in group_diag.index}

        cl_base = {y: methods.chain_ladder(group_diag.loc[y, "paid_to_date"], cdf_at_latest[y]) for y in group_diag.index}
        ei = credibility.experience_indication(mature_years, cl_base, trend, on_level_premium)
        z = credibility.credibility_z(claim_counts.get(group, 0), cred_full)
        elr = credibility.blend_elr(z, ei, assumptions_by_group[group]["plan_loss_ratio"])

        context[group] = dict(
            diagonal=group_diag, cdf_at_latest=cdf_at_latest, on_level_premium=on_level_premium,
            trend=trend, z=z, elr=elr, mature_years=mature_years,
        )
    return context


def compute_scenario_ultimates(context, assumptions_by_group, tail_by_group: dict, shock: float, ext_tail_lag_years: float):
    """CL / EC / BF ultimates for every rating_group x accident_year under
    a given (tail, shock) pair. tail_by_group={group: 1.0} and shock=0.0
    reproduces the base scenario exactly - see tests/test_extension.py."""
    rows = []
    for group, ctx in context.items():
        tail = tail_by_group[group]
        plan_lr = assumptions_by_group[group]["plan_loss_ratio"]

        cdf_prime = {y: extension.apply_tail(cdf, tail) for y, cdf in ctx["cdf_at_latest"].items()}
        cl_prime = {
            y: methods.chain_ladder(ctx["diagonal"].loc[y, "paid_to_date"], cdf_prime[y])
            for y in ctx["diagonal"].index
        }
        ei_prime = credibility.experience_indication(ctx["mature_years"], cl_prime, ctx["trend"], ctx["on_level_premium"])
        elr_prime = credibility.blend_elr(ctx["z"], ei_prime, plan_lr)

        for year in ctx["diagonal"].index:
            paid = ctx["diagonal"].loc[year, "paid_to_date"]
            latest_age = ctx["diagonal"].loc[year, "latest_dev_age_months"]
            lag = extension.payment_lag_years(latest_age, ext_tail_lag_years)
            uplift = extension.inflation_uplift(lag, shock)

            ec_prime = methods.expected_claims(ctx["on_level_premium"][year], elr_prime, ctx["trend"][year])
            bf_prime = methods.bornhuetter_ferguson(paid, ec_prime, cdf_prime[year])

            for method_name, tail_adjusted in [("ChainLadder", cl_prime[year]), ("ExpectedClaims", ec_prime), ("BornhuetterFerguson", bf_prime)]:
                ultimate = extension.apply_extension_to_ultimate(paid, tail_adjusted, uplift)
                rows.append(dict(rating_group=group, accident_year=year, method=method_name, paid_to_date=paid, ultimate=ultimate))
    return pd.DataFrame(rows)


def add_ratios(df: pd.DataFrame, premium_rate: pd.DataFrame, assumptions_by_group: dict) -> pd.DataFrame:
    df = df.merge(premium_rate[["rating_group", "accident_year", "earned_premium_000"]], on=["rating_group", "accident_year"])
    df["reserve"] = df["ultimate"] - df["paid_to_date"]
    df["earned_premium"] = df["earned_premium_000"] * PREMIUM_UNITS
    df["loss_ratio"] = df["ultimate"] / df["earned_premium"]
    df["expense_ratio"] = df["rating_group"].map(lambda g: assumptions_by_group[g]["expense_ratio"])
    df["combined_ratio"] = df["loss_ratio"] + df["expense_ratio"]
    return df.drop(columns=["earned_premium_000", "earned_premium"])


def run_reserving_pass(loss_trend_by_group: dict, *, triangle, premium_rate, assumptions_by_group,
                        assumptions_global, claim_counts, mature_years) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Runs the full base + stress + ADC valuation for one loss-trend
    input, returning (reserve_results, reinsurance_valuation). Neither
    DataFrame is tagged with which trend source produced it, that's the
    caller's job (a column on dim_reserving_run, not on these facts, see
    docs/dashboard.md). reinsurance_valuation values the cover once per
    candidate booked_method (ChainLadder/ExpectedClaims/BornhuetterFerguson),
    since which method a committee books is a real decision the dashboard
    should let a viewer compare, not something fixed in code, see
    docs/reserving-engine.md ("Booked reserve")."""
    context = build_base_context(
        triangle, premium_rate, assumptions_by_group, loss_trend_by_group,
        claim_counts, assumptions_global["cred_full"], mature_years,
    )

    base = compute_scenario_ultimates(context, assumptions_by_group, {g: 1.0 for g in context}, 0.0, 0.0)
    base["scenario"] = "Base"

    tail_by_group = {g: assumptions_by_group[g]["ext_tail_factor"] for g in context}
    ext_shock = assumptions_global["ext_inflation_shock"]
    ext_tail_lag_years = assumptions_global["ext_tail_lag_years"]

    stress = compute_scenario_ultimates(context, assumptions_by_group, tail_by_group, ext_shock, ext_tail_lag_years)
    stress["scenario"] = "Extension"

    results = pd.concat([base, stress], ignore_index=True)
    results = add_ratios(results, premium_rate, assumptions_by_group)

    def reserve_at_shock(method: str, shock: float) -> float:
        df = compute_scenario_ultimates(context, assumptions_by_group, tail_by_group, shock, ext_tail_lag_years)
        rows = df[df.method == method]
        return (rows["ultimate"] - rows["paid_to_date"]).sum()

    adc_rows = []
    for method in ("ChainLadder", "ExpectedClaims", "BornhuetterFerguson"):
        booked_reserve = results.query("method == @method and scenario == 'Base'")["reserve"].sum()
        terms = reinsurance.adc_terms(
            booked_reserve,
            assumptions_global["adc_attachment_pct"],
            assumptions_global["adc_exhaustion_pct"],
            assumptions_global["adc_rate_on_line"],
        )

        assumed_reserve = reserve_at_shock(method, ext_shock)
        assumed_recovery = reinsurance.recovery(assumed_reserve, terms)
        breakeven_shock = reinsurance.find_breakeven_shock(lambda shock, m=method: reserve_at_shock(m, shock), terms)
        breakeven_reserve = reserve_at_shock(method, breakeven_shock)
        breakeven_recovery = reinsurance.recovery(breakeven_reserve, terms)

        adc_rows.append(dict(
            booked_method=method, scenario="Assumed stress", inflation_shock=ext_shock, stressed_reserve=assumed_reserve,
            booked_reserve=terms.booked, attachment=terms.attachment, exhaustion=terms.exhaustion,
            adc_limit=terms.limit, premium=terms.premium, recovery=assumed_recovery,
            net_benefit=assumed_recovery - terms.premium,
        ))
        adc_rows.append(dict(
            booked_method=method, scenario="Breakeven", inflation_shock=breakeven_shock, stressed_reserve=breakeven_reserve,
            booked_reserve=terms.booked, attachment=terms.attachment, exhaustion=terms.exhaustion,
            adc_limit=terms.limit, premium=terms.premium, recovery=breakeven_recovery,
            net_benefit=breakeven_recovery - terms.premium,
        ))

    adc_df = pd.DataFrame(adc_rows)

    return results, adc_df


def main(trend_source: str = "assumed", trend_value: float | None = None, label: str | None = None):
    trend_source = trend_source.lower()
    if trend_source not in ("assumed", "estimated", "both"):
        raise ValueError(f"trend_source must be 'assumed', 'estimated', or 'both', got {trend_source!r}")

    invocation_id = tracking.new_invocation_id()
    run_timestamp = datetime.now(timezone.utc)

    engine = io.get_engine()
    triangle = io.read_triangle(engine)
    premium_rate = io.read_premium_rate(engine)
    assumptions_by_group, assumptions_global = io.read_assumptions(engine)

    mature_years_count = int(assumptions_global["cred_mature_years"])
    mature_years = sorted(triangle.accident_year.unique())[:mature_years_count]
    claim_counts_total = io.read_mature_claim_counts(engine, mature_years)
    claim_counts_by_year = io.read_claim_counts_by_year(engine, mature_years)

    groups = sorted(triangle.rating_group.unique())
    assumed_value = trend_value if trend_value is not None else assumptions_global["loss_trend"]
    assumed_trend = {g: assumed_value for g in groups}
    # Computed regardless of which source was chosen, so it's always
    # available to log as a point of reference (see tracking.flatten_parameters).
    estimated_trend = estimation.estimate_severity_trend(triangle, claim_counts_by_year, mature_years)

    print("Loss trend, assumed vs estimated from mature-year severity:")
    for g in groups:
        print(f"  Group {g}: assumed {assumed_trend[g]:.1%}, estimated {estimated_trend[g]:.1%}")

    variants = []
    if trend_source in ("assumed", "both"):
        variants.append(("Assumed", assumed_trend))
    if trend_source in ("estimated", "both"):
        variants.append(("Estimated", estimated_trend))

    for variant_label, trend_by_group in variants:
        run_id = tracking.new_run_id(variant_label)

        results, adc_df = run_reserving_pass(
            trend_by_group,
            triangle=triangle, premium_rate=premium_rate,
            assumptions_by_group=assumptions_by_group, assumptions_global=assumptions_global,
            claim_counts=claim_counts_total, mature_years=mature_years,
        )
        results["run_id"] = run_id
        adc_df["run_id"] = run_id

        print(f"\n[{variant_label}] reserve results by method and scenario (account totals, GBP):")
        print(results.groupby(["method", "scenario"])[["ultimate", "reserve"]].sum().round(0))

        print(f"\n[{variant_label}] Adverse Development Cover valuation:")
        print(adc_df.round(2).to_string(index=False))

        parameter_rows = tracking.flatten_parameters(assumptions_by_group, assumptions_global, estimated_trend)

        print(f"\nWriting results to Postgres as run {run_id} (invocation {invocation_id}):")
        io.write_run_metadata(engine, run_id, invocation_id, variant_label, run_timestamp, label)
        io.write_run_parameters(engine, run_id, parameter_rows)
        io.append_table(engine, results, "fct_reserve_results")
        io.append_table(engine, adc_df, "fct_reinsurance_valuation")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the claims reserving engine.")
    parser.add_argument("--trend-source", choices=["assumed", "estimated", "both"], default="assumed",
                         help="Which loss trend input(s) to compute a run for.")
    parser.add_argument("--trend-value", type=float, default=None,
                         help="Override the assumed loss trend with a specific value instead of the seeded default.")
    parser.add_argument("--label", default=None, help="Optional free-text label for this run.")
    args = parser.parse_args()

    main(trend_source=args.trend_source, trend_value=args.trend_value, label=args.label)
