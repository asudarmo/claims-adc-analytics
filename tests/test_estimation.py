import numpy as np
import pandas as pd
import pytest

from engine.estimation import common_maturity, estimate_severity_trend


@pytest.fixture
def toy_triangle():
    # Group A: severities of 100, 110, 121 at ages 24/24/24 for accident
    # years 2020/2021/2022 evaluated at their common maturity of 24 months
    # (2022's own latest age), a clean +10% per year trend by construction.
    rows = []
    for year, ultimate_at_24 in zip([2020, 2021, 2022], [1000, 1100, 1210]):
        rows.append(dict(rating_group="A", accident_year=year, dev_age_months=24, cumulative_paid=ultimate_at_24))
        rows.append(dict(rating_group="A", accident_year=year, dev_age_months=36, cumulative_paid=ultimate_at_24 * 1.2))
    # 2022 has no 36-month data yet, so 24 months is the common maturity
    rows = [r for r in rows if not (r["accident_year"] == 2022 and r["dev_age_months"] == 36)]
    return pd.DataFrame(rows)


@pytest.fixture
def toy_claim_counts():
    return pd.DataFrame([
        dict(rating_group="A", accident_year=2020, n=10),
        dict(rating_group="A", accident_year=2021, n=10),
        dict(rating_group="A", accident_year=2022, n=10),
    ])


def test_common_maturity_is_bound_by_the_youngest_mature_year(toy_triangle):
    assert common_maturity(toy_triangle, [2020, 2021, 2022]) == 24


def test_common_maturity_raises_if_a_mature_year_is_missing(toy_triangle):
    with pytest.raises(ValueError):
        common_maturity(toy_triangle, [2019, 2020, 2021, 2022])


def test_estimated_trend_recovers_a_known_constant_growth_rate(toy_triangle, toy_claim_counts):
    trends = estimate_severity_trend(toy_triangle, toy_claim_counts, [2020, 2021, 2022])
    # severity per claim is 100, 110, 121 -> exactly +10% p.a. by construction
    assert trends["A"] == pytest.approx(0.10, abs=1e-6)


def test_estimate_severity_trend_needs_at_least_two_years(toy_triangle, toy_claim_counts):
    with pytest.raises(ValueError):
        estimate_severity_trend(toy_triangle, toy_claim_counts, [2022])
