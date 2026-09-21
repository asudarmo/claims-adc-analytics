"""
Age-to-age (LDF) and cumulative development (CDF) factors from a validated
cumulative-paid triangle.

Input shape throughout: a long DataFrame with columns
rating_group, accident_year, dev_age_months, cumulative_paid
(this is exactly marts.fct_triangle_cell).
"""
import numpy as np
import pandas as pd

DEV_AGES = [12, 24, 36, 48, 60, 72]


def compute_ldfs(triangle: pd.DataFrame) -> pd.DataFrame:
    """
    Volume-weighted age-to-age factors, pooled across accident years, per
    rating group: LDF_j = sum(Paid at j+1) / sum(Paid at j), summed only
    over accident years where both ages are observed.
    """
    rows = []
    for group, sub in triangle.groupby("rating_group"):
        wide = sub.pivot(index="accident_year", columns="dev_age_months", values="cumulative_paid")
        for j in range(len(DEV_AGES) - 1):
            a, b = DEV_AGES[j], DEV_AGES[j + 1]
            if a not in wide.columns or b not in wide.columns:
                continue
            both = wide[[a, b]].dropna()
            if len(both) == 0:
                continue
            ldf = both[b].sum() / both[a].sum()
            rows.append(dict(rating_group=group, age_from=a, age_to=b, ldf=ldf))
    return pd.DataFrame(rows)


def compute_cdfs(ldfs: pd.DataFrame) -> pd.DataFrame:
    """
    Cumulative development factor from each development age to ultimate
    (72 months, the last age modelled before any tail extension):
    CDF_j = LDF_j x CDF_{j+1}, with CDF_72 = 1.
    """
    rows = []
    for group, sub in ldfs.groupby("rating_group"):
        ldf_by_from = dict(zip(sub["age_from"], sub["ldf"]))
        cdf = {72: 1.0}
        for age in reversed(DEV_AGES[:-1]):
            next_age = DEV_AGES[DEV_AGES.index(age) + 1]
            ldf = ldf_by_from.get(age)
            if ldf is None:
                continue
            cdf[age] = ldf * cdf[next_age]
        for age, value in cdf.items():
            rows.append(dict(rating_group=group, dev_age_months=age, cdf=value))
    return pd.DataFrame(rows)


def latest_diagonal(triangle: pd.DataFrame) -> pd.DataFrame:
    """
    One row per rating_group x accident_year: the latest observed dev age
    and its cumulative paid, i.e. what's actually known as of the
    valuation date.
    """
    idx = triangle.groupby(["rating_group", "accident_year"])["dev_age_months"].idxmax()
    latest = triangle.loc[idx, ["rating_group", "accident_year", "dev_age_months", "cumulative_paid"]]
    return latest.rename(columns={"dev_age_months": "latest_dev_age_months", "cumulative_paid": "paid_to_date"})
