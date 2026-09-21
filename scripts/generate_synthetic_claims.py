"""
Synthetic individual-claims generator for a commercial motor reserving
analytics pipeline.

This continues the scenario used in an earlier spreadsheet-based reserving
model (three rating groups, accident years 2020-2025, valuation date
31 Dec 2025, paid-claims chain ladder / expected claims / BF triangle
methods) but generates data one level down: individual claim headers and
claim transactions, from which the development triangles are built
downstream (in dbt/SQL), rather than generating the triangle directly.

Two sets of output are written:
  data/ground_truth/   - the true simulated claim experience (including the
                          true ultimate per claim and a log of every data
                          quality issue that was deliberately injected). This
                          is answer-key material for validating the pipeline
                          and for a later "backtest" dashboard page. It is not
                          meant to be loaded into the reserving model itself.
  data/raw_extract/     - the "as received" extract: ground truth with
                          reporting/payment timing censored at the valuation
                          date, plus deliberately injected data quality issues.
                          This is the input to the validation/cleaning step.

Run: python scripts/generate_synthetic_claims.py
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta

RNG_SEED = 42
rng = np.random.default_rng(RNG_SEED)

VALUATION_DATE = date(2025, 12, 31)
ACCIDENT_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
GROUPS = ["A", "B", "C"]

# ---------------------------------------------------------------------------
# Rating group assumptions
# Anchored to the same order of magnitude as the original workbook
# (Group A largest/fastest, Group C smallest/heaviest-tailed with a
# bodily-injury skew) but independently simulated, not reproduced cell-for-cell.
# ---------------------------------------------------------------------------
GROUP_PARAMS = {
    "A": dict(
        label="Light commercial vehicles",
        base_claim_count=[300, 315, 325, 340, 360, 380],
        sev_mean_2020=8000.0, sev_cv=0.9,
        large_loss_prob=0.004, large_loss_mult=(3, 6),
        report_delay_mean_days=20, report_delay_sigma=0.7,
        weibull_shape=1.35, weibull_scale_months=13,   # payment timing (fast)
        n_payments_range=(2, 5),
        reopen_prob=0.005,
        reserve_noise_sigma=0.18,
    ),
    "B": dict(
        label="Heavy goods vehicles",
        base_claim_count=[145, 150, 155, 160, 175, 190],
        sev_mean_2020=12800.0, sev_cv=1.15,
        large_loss_prob=0.010, large_loss_mult=(3, 8),
        report_delay_mean_days=30, report_delay_sigma=0.8,
        weibull_shape=1.15, weibull_scale_months=19,   # intermediate
        n_payments_range=(2, 6),
        reopen_prob=0.015,
        reserve_noise_sigma=0.25,
    ),
    "C": dict(
        label="Specialist haulage",
        base_claim_count=[60, 64, 68, 72, 80, 86],
        sev_mean_2020=21000.0, sev_cv=1.65,
        large_loss_prob=0.020, large_loss_mult=(3, 7),   # bodily-injury tail
        report_delay_mean_days=45, report_delay_sigma=0.9,
        weibull_shape=0.90, weibull_scale_months=23,   # slow, long tail
        n_payments_range=(3, 8),
        reopen_prob=0.04,
        reserve_noise_sigma=0.35,
    ),
}

SEVERITY_TREND = 0.055  # per annum, matches original Loss_trend assumption
MAX_DEV_MONTHS_MODELLED = 72  # matches original triangle; later months = tail


def lognormal_params(mean, cv):
    sigma2 = np.log(1 + cv ** 2)
    sigma = np.sqrt(sigma2)
    mu = np.log(mean) - sigma2 / 2
    return mu, sigma


def random_date_in_year(year, n):
    start = date(year, 1, 1).toordinal()
    end = date(year, 12, 31).toordinal()
    days = rng.integers(start, end + 1, size=n)
    return [date.fromordinal(int(d)) for d in days]


# ---------------------------------------------------------------------------
# 1. Simulate claims (ground truth)
# ---------------------------------------------------------------------------
claim_rows = []
claim_id_counter = 1

for group in GROUPS:
    p = GROUP_PARAMS[group]
    _, sigma = lognormal_params(p["sev_mean_2020"], p["sev_cv"])

    for i, year in enumerate(ACCIDENT_YEARS):
        # true ultimate claim count: anchor +/- Poisson-ish noise, small IBNR
        # allowance built into the anchor itself (kept deterministic here so
        # counts stay auditable; noise lives in severity/timing instead)
        n_claims = p["base_claim_count"][i]
        accident_dates = random_date_in_year(year, n_claims)

        trend_factor = (1 + SEVERITY_TREND) ** (year - 2020)
        mu = np.log(p["sev_mean_2020"] * trend_factor) - sigma ** 2 / 2  # trend on the mean, sigma held constant

        base_sev = rng.lognormal(mean=mu, sigma=sigma, size=n_claims)
        is_large = rng.random(n_claims) < p["large_loss_prob"]
        mult = rng.uniform(p["large_loss_mult"][0], p["large_loss_mult"][1], size=n_claims)
        true_ultimate = np.where(is_large, base_sev * mult, base_sev)

        report_delay_days = rng.lognormal(
            mean=np.log(p["report_delay_mean_days"]), sigma=p["report_delay_sigma"],
            size=n_claims,
        )

        for j in range(n_claims):
            claim_rows.append(
                dict(
                    claim_id=f"CLM-{claim_id_counter:06d}",
                    rating_group=group,
                    accident_year=year,
                    accident_date=accident_dates[j],
                    report_date=accident_dates[j] + timedelta(days=float(report_delay_days[j])),
                    true_ultimate=round(float(true_ultimate[j]), 2),
                )
            )
            claim_id_counter += 1

claims = pd.DataFrame(claim_rows)

# ---------------------------------------------------------------------------
# 2. Simulate payment and case-reserve transactions per claim
# ---------------------------------------------------------------------------
txn_rows = []
txn_id_counter = 1
closure_info = []

for row in claims.itertuples(index=False):
    p = GROUP_PARAMS[row.rating_group]
    k = rng.integers(p["n_payments_range"][0], p["n_payments_range"][1] + 1)

    # draw k payment times (months since report), sort, convert to cumulative
    # fraction of ultimate paid via a Weibull CDF -> guarantees an increasing,
    # eventually-saturating payment curve whose shape matches the group's
    # settlement speed (fast for A, long-tailed for C).
    raw_times = rng.weibull(p["weibull_shape"], size=k) * p["weibull_scale_months"]
    times_months = np.sort(raw_times)
    cum_frac = 1 - np.exp(-(times_months / p["weibull_scale_months"]) ** p["weibull_shape"])
    cum_frac = cum_frac / cum_frac[-1]  # force last payment to close the claim (frac -> 1.0)

    cum_paid = 0.0
    prev_date = row.report_date
    last_txn_date = row.report_date
    for t_month, frac in zip(times_months, cum_frac):
        txn_date = row.report_date + timedelta(days=float(t_month * 30.44))
        target_paid = row.true_ultimate * frac
        increment = round(target_paid - cum_paid, 2)
        if increment <= 0:
            continue
        cum_paid += increment
        last_txn_date = txn_date

        # case reserve snapshot recorded alongside the payment: analyst's
        # estimate of the remaining outstanding, with claim-specific noise
        # (some claims run consistently over/under reserved)
        remaining_true = max(row.true_ultimate - cum_paid, 0.0)
        reserve_factor = np.exp(rng.normal(0, p["reserve_noise_sigma"]))
        case_reserve = round(remaining_true * reserve_factor, 2) if remaining_true > 0 else 0.0

        txn_rows.append(dict(
            transaction_id=f"TX-{txn_id_counter:07d}", claim_id=row.claim_id,
            transaction_date=txn_date, transaction_type="Payment", amount=increment,
        ))
        txn_id_counter += 1
        txn_rows.append(dict(
            transaction_id=f"TX-{txn_id_counter:07d}", claim_id=row.claim_id,
            transaction_date=txn_date, transaction_type="CaseReserveEstimate", amount=case_reserve,
        ))
        txn_id_counter += 1
        prev_date = txn_date

    closed = rng.random() > p["reopen_prob"]
    closure_info.append(dict(claim_id=row.claim_id, close_date=last_txn_date, closed_clean=closed))

    # a reopen: claim closes, then some time later a further loss emerges
    if not closed:
        reopen_gap_days = rng.integers(60, 540)
        reopen_date = last_txn_date + timedelta(days=int(reopen_gap_days))
        extra = round(row.true_ultimate * rng.uniform(0.03, 0.15), 2)
        claims.loc[claims.claim_id == row.claim_id, "true_ultimate"] += extra
        txn_rows.append(dict(
            transaction_id=f"TX-{txn_id_counter:07d}", claim_id=row.claim_id,
            transaction_date=reopen_date, transaction_type="Payment", amount=extra,
        ))
        txn_id_counter += 1
        txn_rows.append(dict(
            transaction_id=f"TX-{txn_id_counter:07d}", claim_id=row.claim_id,
            transaction_date=reopen_date, transaction_type="CaseReserveEstimate", amount=0.0,
        ))
        txn_id_counter += 1
        closure_info[-1]["close_date"] = reopen_date

transactions = pd.DataFrame(txn_rows)
closure = pd.DataFrame(closure_info)
claims = claims.merge(closure, on="claim_id")

print(f"Simulated {len(claims):,} claims and {len(transactions):,} transactions.")

claims["status"] = np.where(claims["close_date"] <= VALUATION_DATE, "Closed", "Open")
claims.loc[claims["close_date"] > VALUATION_DATE, "close_date"] = pd.NaT
claims = claims.drop(columns=["closed_clean"])

# ---------------------------------------------------------------------------
# 3. Censor at the valuation date: this is what makes it a reserving problem.
#    Anything dated after 31 Dec 2025 has simply not happened yet as far as
#    the "extract" is concerned. Ground truth keeps everything.
# ---------------------------------------------------------------------------
ground_truth_claims = claims.copy()
ground_truth_transactions = transactions.copy()

observed_transactions = transactions[transactions.transaction_date <= VALUATION_DATE].copy()
observed_claim_ids = set(observed_transactions.claim_id) | set(
    claims[claims.report_date <= VALUATION_DATE].claim_id
)
observed_claims = claims[claims.claim_id.isin(observed_claim_ids)].copy()
observed_claims.loc[observed_claims.report_date > VALUATION_DATE, "report_date"] = pd.NaT

# ---------------------------------------------------------------------------
# 4. Premium and rate-change history (portfolio-level, not claim-level)
#    Same softening-then-hardening narrative as the original model, freshly
#    simulated rather than copied.
# ---------------------------------------------------------------------------
PREMIUM_2020 = {"A": 4300.0, "B": 3200.0, "C": 1850.0}   # (GBP 000s)
PREMIUM_GROWTH = {"A": 0.055, "B": 0.065, "C": 0.075}    # nominal exposure growth p.a.
RATE_CHANGES = {
    "A": [0.02, -0.02, 0.01, 0.05, 0.07, 0.03],
    "B": [0.03, -0.03, 0.005, 0.06, 0.085, 0.04],
    "C": [0.015, -0.035, 0.02, 0.065, 0.08, 0.045],
}

premium_rows, rate_rows = [], []
for group in GROUPS:
    cum_rate = 1.0
    for i, year in enumerate(ACCIDENT_YEARS):
        cum_rate *= (1 + RATE_CHANGES[group][i])
        premium = PREMIUM_2020[group] * ((1 + PREMIUM_GROWTH[group]) ** i) * cum_rate / (1 + RATE_CHANGES[group][0])
        premium_rows.append(dict(accident_year=year, rating_group=group, earned_premium_000=round(premium, 1)))
        rate_rows.append(dict(accident_year=year, rating_group=group, rate_change=RATE_CHANGES[group][i]))

earned_premium = pd.DataFrame(premium_rows)
rate_changes = pd.DataFrame(rate_rows)

# ---------------------------------------------------------------------------
# 5. Save ground truth (answer key - not for the dashboard)
# ---------------------------------------------------------------------------
GT_DIR = "data/ground_truth"
ground_truth_claims.to_csv(f"{GT_DIR}/claims_header_ground_truth.csv", index=False)
ground_truth_transactions.to_csv(f"{GT_DIR}/claims_transactions_ground_truth.csv", index=False)

# ---------------------------------------------------------------------------
# 6. Inject data quality issues into the "raw extract" that will actually be
#    validated and cleaned downstream. Each issue is logged separately so the
#    validation rules can later be checked for recall.
# ---------------------------------------------------------------------------
issues_log = []

raw_claims = observed_claims.drop(columns=["true_ultimate"]).copy().reset_index(drop=True)
raw_txns = observed_transactions.copy().reset_index(drop=True)
raw_premium = earned_premium.copy()
raw_rates = rate_changes.copy()


def log_issue(table, key, issue_type, detail):
    issues_log.append(dict(table=table, key=key, issue_type=issue_type, detail=detail))


# 6a. Missing rating_group on a handful of claim headers
idx = rng.choice(raw_claims.index, size=max(3, int(0.002 * len(raw_claims))), replace=False)
for i in idx:
    log_issue("claims_header", raw_claims.loc[i, "claim_id"], "missing_rating_group",
               f"was {raw_claims.loc[i, 'rating_group']}")
    raw_claims.loc[i, "rating_group"] = np.nan

# 6b. Missing report_date on a handful of claims
idx = rng.choice(raw_claims.index, size=max(3, int(0.004 * len(raw_claims))), replace=False)
for i in idx:
    log_issue("claims_header", raw_claims.loc[i, "claim_id"], "missing_report_date",
               f"was {raw_claims.loc[i, 'report_date']}")
    raw_claims.loc[i, "report_date"] = pd.NaT

# 6c. Decimal-point keying errors on payment amounts (x10 or /10)
pay_idx = raw_txns.index[raw_txns.transaction_type == "Payment"]
idx = rng.choice(pay_idx, size=max(5, int(0.005 * len(pay_idx))), replace=False)
for i in idx:
    factor = rng.choice([10, 0.1])
    old = raw_txns.loc[i, "amount"]
    raw_txns.loc[i, "amount"] = round(old * factor, 2)
    log_issue("claims_transactions", raw_txns.loc[i, "transaction_id"], "decimal_point_error",
               f"amount {old} -> {raw_txns.loc[i, 'amount']} (x{factor})")

# 6d. Duplicate transaction rows (exact copy re-keyed with a new transaction_id)
idx = rng.choice(raw_txns.index, size=max(4, int(0.003 * len(raw_txns))), replace=False)
dupes = raw_txns.loc[idx].copy()
dupes["transaction_id"] = [f"TX-DUP{n:05d}" for n in range(len(dupes))]
for _, r in dupes.iterrows():
    log_issue("claims_transactions", r["transaction_id"], "duplicate_transaction",
               f"duplicate of a genuine transaction on claim {r['claim_id']}")
raw_txns = pd.concat([raw_txns, dupes], ignore_index=True)

# 6e. Text placeholders in the amount field ("N/A", "-")
idx = rng.choice(raw_txns.index, size=max(4, int(0.003 * len(raw_txns))), replace=False)
raw_txns["amount"] = raw_txns["amount"].astype(object)
for i in idx:
    placeholder = rng.choice(["N/A", "-", ""])
    log_issue("claims_transactions", raw_txns.loc[i, "transaction_id"], "text_placeholder",
               f"amount replaced with '{placeholder}'")
    raw_txns.loc[i, "amount"] = placeholder

# 6f. Sign errors: a payment keyed as negative (no salvage/subrogation exists
#     on this account, so a negative payment is never legitimate)
num_pay_idx = [i for i in pay_idx if i in raw_txns.index and not isinstance(raw_txns.loc[i, "amount"], str)]
idx = rng.choice(num_pay_idx, size=max(3, int(0.002 * len(num_pay_idx))), replace=False)
for i in idx:
    old = raw_txns.loc[i, "amount"]
    raw_txns.loc[i, "amount"] = -abs(float(old))
    log_issue("claims_transactions", raw_txns.loc[i, "transaction_id"], "negative_payment",
               f"amount {old} -> {raw_txns.loc[i, 'amount']}")

# 6g. Orphan transaction: claim_id typo pointing at a claim that doesn't exist.
# Fake id is offset well outside the real claim_id numbering range, with a
# uniqueness check, rather than fragile string surgery on the real id (an
# earlier version tweaked the last digit, which could - and twice did -
# collide with a different real claim instead of producing a true orphan).
idx = rng.choice(raw_txns.index, size=3, replace=False)
valid_ids = set(raw_claims.claim_id)
for n, i in enumerate(idx):
    real_id = raw_txns.loc[i, "claim_id"]
    fake_id = f"CLM-{900000 + n:06d}"
    assert fake_id not in valid_ids
    raw_txns.loc[i, "claim_id"] = fake_id
    log_issue("claims_transactions", raw_txns.loc[i, "transaction_id"], "orphan_claim_id",
               f"claim_id {real_id} -> {fake_id} (does not exist in claims_header)")

# 6h. Future-dated transaction (year-typo style keying error). Pushed a fixed
# distance past the valuation date rather than "+1 year" on the original date
# - a +1-year shift on an early transaction can easily still land inside the
# valid window (report_date..valuation_date) and silently fail to be an
# out-of-bounds value at all, which is what an earlier version of this did.
idx = rng.choice(raw_txns.index, size=3, replace=False)
for n, i in enumerate(idx):
    old = raw_txns.loc[i, "transaction_date"]
    bad_date = VALUATION_DATE + timedelta(days=30 * (n + 1))
    raw_txns.loc[i, "transaction_date"] = bad_date
    log_issue("claims_transactions", raw_txns.loc[i, "transaction_id"], "date_out_of_bounds",
               f"transaction_date {old} -> {bad_date} (after valuation date / year mis-key)")

# 6i. Rate-change magnitude error (percentage entered as a whole number)
bad_row = raw_rates.sample(1, random_state=7).index[0]
old = raw_rates.loc[bad_row, "rate_change"]
raw_rates.loc[bad_row, "rate_change"] = old * 100
log_issue("rate_changes", f"{raw_rates.loc[bad_row,'accident_year']}-{raw_rates.loc[bad_row,'rating_group']}",
           "magnitude_error", f"rate_change {old} -> {raw_rates.loc[bad_row, 'rate_change']}")

# 6j. A missing earned-premium cell (period not written to the extract)
bad_row = raw_premium.sample(1, random_state=11).index[0]
log_issue("earned_premium", f"{raw_premium.loc[bad_row,'accident_year']}-{raw_premium.loc[bad_row,'rating_group']}",
           "missing_value", f"earned_premium_000 {raw_premium.loc[bad_row,'earned_premium_000']} -> blank")
raw_premium.loc[bad_row, "earned_premium_000"] = np.nan

issues_df = pd.DataFrame(issues_log)

# ---------------------------------------------------------------------------
# 7. Save the raw extract (this is what the validation/cleaning step consumes)
# ---------------------------------------------------------------------------
RAW_DIR = "data/raw_extract"
raw_claims.to_csv(f"{RAW_DIR}/claims_header_raw.csv", index=False)
raw_txns.to_csv(f"{RAW_DIR}/claims_transactions_raw.csv", index=False)
raw_premium.to_csv(f"{RAW_DIR}/earned_premium_raw.csv", index=False)
raw_rates.to_csv(f"{RAW_DIR}/rate_changes_raw.csv", index=False)
issues_df.to_csv(f"{GT_DIR}/injected_issues_log.csv", index=False)

print(f"\nInjected {len(issues_df)} data quality issues across {issues_df.table.nunique()} tables.")
print(issues_df.groupby(["table", "issue_type"]).size())

# ---------------------------------------------------------------------------
# 8. Sanity check: rebuild a cumulative paid triangle from the CLEAN observed
#    transactions (ignoring the injected issues) and compare its shape/scale
#    to the original workbook's triangle.
# ---------------------------------------------------------------------------
clean_pay = observed_transactions[observed_transactions.transaction_type == "Payment"].merge(
    observed_claims[["claim_id", "rating_group", "accident_year"]], on="claim_id"
)
clean_pay["dev_month"] = clean_pay.apply(
    lambda r: (r.transaction_date.year - r.accident_year) * 12 + r.transaction_date.month, axis=1
)
clean_pay["dev_bucket"] = ((clean_pay["dev_month"] - 1) // 12 + 1) * 12
clean_pay = clean_pay[clean_pay.dev_bucket <= MAX_DEV_MONTHS_MODELLED]

triangle = (
    clean_pay.groupby(["rating_group", "accident_year", "dev_bucket"])["amount"].sum()
    .groupby(level=[0, 1]).cumsum()
    .unstack("dev_bucket")
)
print("\nSanity-check cumulative paid triangle (from clean simulated transactions, GBP):")
print(triangle.round(0))

