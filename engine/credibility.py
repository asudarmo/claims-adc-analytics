"""
On-level premium, the experience indication, and the credibility-weighted
a priori loss ratio. Formula names follow the original spreadsheet model's
notation (OLF, TF, EI, Z, ELR) so the two can be compared line by line.
"""
import numpy as np


def on_level_factor(cumulative_rate_index: dict, latest_year: int) -> dict:
    """OLF_i = RateIdx_latest / RateIdx_i, per accident year."""
    latest_index = cumulative_rate_index[latest_year]
    return {year: latest_index / idx for year, idx in cumulative_rate_index.items()}


def trend_factor(accident_year: int, latest_year: int, loss_trend: float) -> float:
    """TF_i = (1 + loss_trend) ** (latest_year - year_i), trending an older
    accident year's claims up to the latest year's cost level."""
    return (1 + loss_trend) ** (latest_year - accident_year)


def experience_indication(mature_years: list, cl_ultimate: dict, trend: dict, on_level_premium: dict) -> float:
    """EI = sum(CL_i * TF_i) / sum(OLP_i) over the mature accident years."""
    numerator = sum(cl_ultimate[y] * trend[y] for y in mature_years)
    denominator = sum(on_level_premium[y] for y in mature_years)
    return numerator / denominator


def credibility_z(claim_count: float, cred_full: float) -> float:
    """Z = min(1, sqrt(n / cred_full)), the limited fluctuation standard."""
    return min(1.0, np.sqrt(claim_count / cred_full))


def blend_elr(z: float, experience_indication_value: float, plan_loss_ratio: float) -> float:
    """ELR = Z * EI + (1 - Z) * Plan_LR."""
    return z * experience_indication_value + (1 - z) * plan_loss_ratio
