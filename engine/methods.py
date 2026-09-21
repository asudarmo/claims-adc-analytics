"""
The three reserving bases. Each takes plain scalars for one accident year
and rating group, so they're trivial to unit-test against hand-computed
figures, and easy to re-run under the extension scenario's tail-adjusted
CDFs without touching this module at all.
"""


def chain_ladder(paid_to_date: float, cdf_to_ultimate: float) -> float:
    """CL = Paid x CDF, the Chain Ladder ultimate."""
    return paid_to_date * cdf_to_ultimate


def expected_claims(on_level_premium: float, elr: float, trend: float) -> float:
    """EC = OLP x ELR / TF, the Expected Claims ultimate at the accident
    year's own cost level (dividing back out the trend used to compute ELR
    at the latest year's level)."""
    return on_level_premium * elr / trend


def bornhuetter_ferguson(paid_to_date: float, expected_claims_ultimate: float, cdf_to_ultimate: float) -> float:
    """BF = Paid + EC x (1 - 1/CDF), accepting paid-to-date and applying
    the a priori expectation only to the undeveloped portion."""
    return paid_to_date + expected_claims_ultimate * (1 - 1 / cdf_to_ultimate)
