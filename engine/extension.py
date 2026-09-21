"""
The stress scenario: a tail factor extending development beyond 72 months,
plus additional claims inflation applied to whatever is still unpaid,
scaled by how far in the future that payment is expected to fall rather
than as a flat uplift.

Setting ext_tail = 1.0 and ext_shock = 0.0 must reproduce the base scenario
exactly (checked in tests/test_extension.py) - that invariant is stated
directly in the original assignment and is the main thing worth trusting
about this module.
"""


def apply_tail(cdf_to_ultimate: float, ext_tail: float) -> float:
    """CDF' = CDF x ext_tail, extending every development age's cumulative
    factor to include the tail beyond 72 months."""
    return cdf_to_ultimate * ext_tail


def payment_lag_years(latest_dev_age_months: int, ext_tail_lag_years: float) -> float:
    """
    Years until the remaining unpaid amount for this accident year is
    expected to be paid, used to scale the inflation uplift.

    Defined here as the time remaining to reach 72 months of development,
    plus the tail's own average payment lag beyond that point. A mature
    accident year (already at 72 months) has only the tail left, so its lag
    is just ext_tail_lag_years; a fresh accident year has further
    development ages still to come, plus the same tail lag on top.

    This is a stated modelling choice, not a value recovered from the
    original spreadsheet's notation, since the exact definition wasn't
    available to carry forward. It has the right qualitative shape (longer
    lag for less mature years) and reduces to the tail lag alone for fully
    developed years, which is the one case the original assumption
    (ext_tail_lag_years) was directly measuring.
    """
    years_to_72 = max(72 - latest_dev_age_months, 0) / 12
    return years_to_72 + ext_tail_lag_years


def inflation_uplift(lag_years: float, ext_shock: float) -> float:
    """Uplift = (1 + ext_shock) ** lag_years."""
    return (1 + ext_shock) ** lag_years


def apply_extension_to_ultimate(paid_to_date: float, tail_adjusted_ultimate: float, uplift: float) -> float:
    """X' = Paid + max(X - Paid, 0) x Uplift: the inflation shock is applied
    only to the unpaid (reserve) portion of the tail-adjusted ultimate."""
    reserve = max(tail_adjusted_ultimate - paid_to_date, 0.0)
    return paid_to_date + reserve * uplift
