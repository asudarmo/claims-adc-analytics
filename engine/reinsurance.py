"""
Adverse Development Cover valuation, and the breakeven inflation search:
at what additional inflation rate does the cover exhaust (recovery hits the
limit), holding the tail factors fixed and varying only the shock.

Booked, attachment, exhaustion, limit, and premium are all account-level
figures (summed across every rating group and accident year), since this
cover attaches to the reserve for the whole account, not to any one
accident year or group.
"""
from dataclasses import dataclass


@dataclass
class AdcTerms:
    booked: float
    attachment: float
    exhaustion: float
    limit: float
    premium: float


def adc_terms(booked_reserve: float, attachment_pct: float, exhaustion_pct: float, rate_on_line: float) -> AdcTerms:
    attachment = booked_reserve * attachment_pct
    exhaustion = booked_reserve * exhaustion_pct
    limit = exhaustion - attachment
    premium = limit * rate_on_line
    return AdcTerms(booked=booked_reserve, attachment=attachment, exhaustion=exhaustion, limit=limit, premium=premium)


def recovery(stressed_reserve: float, terms: AdcTerms) -> float:
    """Recovery = min(max(Reserve' - Attach, 0), Limit)."""
    return min(max(stressed_reserve - terms.attachment, 0.0), terms.limit)


def find_breakeven_shock(reserve_at_shock, terms: AdcTerms, low: float = 0.0, high: float = 2.0, tol: float = 1e-6) -> float:
    """
    Finds the additional-inflation shock at which the cover is fully
    exhausted, i.e. where recovery(shock) == limit. `reserve_at_shock` is a
    callable taking a shock rate and returning the resulting account-level
    stressed reserve.

    Plain bisection rather than a library root-finder: recovery is
    monotonically non-decreasing in the shock (more inflation never reduces
    the reserve), so bisection on (recovery - limit) is guaranteed to
    converge and needs no extra dependency for something this simple.
    """
    def gap(shock):
        return recovery(reserve_at_shock(shock), terms) - terms.limit

    if gap(high) < 0:
        raise ValueError(
            f"No breakeven within the search range: even a {high:.0%} shock doesn't exhaust the cover."
        )
    if gap(low) >= 0:
        return low

    while high - low > tol:
        mid = (low + high) / 2
        if gap(mid) < 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2
