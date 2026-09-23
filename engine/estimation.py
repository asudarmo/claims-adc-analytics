"""
Data-driven alternatives to judgmental assumptions, for parameters that are
plausibly estimable from the claims themselves rather than only assumed.
Loss trend is the clearest case: a business-plan loss ratio and a stress
inflation shock are inherently judgmental or hypothetical, but severity
trend is something the historical claims can speak to directly.

This is an alternative trend_source ("Estimated"), not a replacement for
the assumed one ("Assumed") - engine/main.py can run either, or both as
separate tracked runs, see docs/reserving-engine.md ("Assumed vs estimated
loss trend").
"""
import numpy as np
import pandas as pd


def common_maturity(triangle: pd.DataFrame, mature_years: list[int]) -> int:
    """
    The development age, in months, observed for every one of the mature
    years. Comparing average severity across accident years is only fair
    at a shared maturity: an older year's own latest diagonal is more
    developed than a younger year's, so using each year's own latest age
    would confound "more time to develop" with "true severity trend."
    The binding constraint is the youngest mature year's own latest age.
    """
    max_age_by_year = (
        triangle[triangle.accident_year.isin(mature_years)]
        .groupby("accident_year")["dev_age_months"].max()
    )
    if len(max_age_by_year) < len(mature_years):
        missing = set(mature_years) - set(max_age_by_year.index)
        raise ValueError(f"No triangle data for mature year(s) {missing}")
    return int(max_age_by_year.min())


def estimate_severity_trend(triangle: pd.DataFrame, claim_counts: pd.DataFrame, mature_years: list[int]) -> dict[str, float]:
    """
    Per rating group, a log-linear regression of average paid severity per
    claim (cumulative paid at the common maturity, divided by claim count)
    against accident year, across the mature years. Returns the implied
    annual trend rate, e.g. 0.055 for +5.5% p.a., in the same units as
    assumptions_global's loss_trend.

    Needs at least two mature years to fit a trend at all.
    """
    if len(mature_years) < 2:
        raise ValueError("Need at least two mature accident years to estimate a trend.")

    age = common_maturity(triangle, mature_years)
    at_maturity = triangle[(triangle.accident_year.isin(mature_years)) & (triangle.dev_age_months == age)]

    trends = {}
    for group in sorted(triangle.rating_group.unique()):
        paid = at_maturity[at_maturity.rating_group == group].set_index("accident_year")["cumulative_paid"]
        counts = claim_counts[claim_counts.rating_group == group].set_index("accident_year")["n"]
        severity = (paid / counts).dropna().sort_index()

        if len(severity) < 2:
            raise ValueError(f"Not enough data to estimate a severity trend for group {group}.")

        years = severity.index.to_numpy(dtype=float)
        log_severity = np.log(severity.to_numpy())
        slope, _intercept = np.polyfit(years, log_severity, deg=1)
        trends[group] = float(np.exp(slope) - 1)

    return trends
