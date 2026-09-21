"""
Regression fixture: Group A's 2020 accident year from the original
spreadsheet model, the one fully-developed row available in that workbook.
This checks the engine's LDF/CDF arithmetic against a real external
reference, not just against our own synthetic data.
"""
import pandas as pd
import pytest

from engine.triangle import compute_cdfs, compute_ldfs, latest_diagonal

ORIGINAL_GROUP_A_2020 = {12: 960.7, 24: 1755.3, 36: 2087.5, 48: 2271.0, 60: 2344.6, 72: 2432.5}


@pytest.fixture
def single_row_triangle():
    return pd.DataFrame(
        [dict(rating_group="A", accident_year=2020, dev_age_months=age, cumulative_paid=paid)
         for age, paid in ORIGINAL_GROUP_A_2020.items()]
    )


def test_ldfs_match_original_workbook(single_row_triangle):
    ldfs = compute_ldfs(single_row_triangle)
    ldf_by_pair = {(row.age_from, row.age_to): row.ldf for row in ldfs.itertuples()}

    assert ldf_by_pair[(12, 24)] == pytest.approx(1.827, abs=1e-3)
    assert ldf_by_pair[(24, 36)] == pytest.approx(1.189, abs=1e-3)
    assert ldf_by_pair[(36, 48)] == pytest.approx(1.088, abs=1e-3)
    assert ldf_by_pair[(48, 60)] == pytest.approx(1.032, abs=1e-3)
    assert ldf_by_pair[(60, 72)] == pytest.approx(1.037, abs=1e-3)


def test_cdf_to_ultimate_matches_original_workbook(single_row_triangle):
    ldfs = compute_ldfs(single_row_triangle)
    cdfs = compute_cdfs(ldfs)
    cdf_12 = cdfs.loc[cdfs.dev_age_months == 12, "cdf"].iloc[0]

    # product of the five original LDFs, hand-computed from the same source
    assert cdf_12 == pytest.approx(2.53, abs=0.01)
    assert cdfs.loc[cdfs.dev_age_months == 72, "cdf"].iloc[0] == pytest.approx(1.0)


def test_ldfs_pool_volume_weighted_across_years():
    # two accident years with different volumes: the pooled LDF must be the
    # ratio of SUMS, not the average of the two years' individual ratios
    triangle = pd.DataFrame([
        dict(rating_group="A", accident_year=2019, dev_age_months=12, cumulative_paid=100),
        dict(rating_group="A", accident_year=2019, dev_age_months=24, cumulative_paid=150),
        dict(rating_group="A", accident_year=2020, dev_age_months=12, cumulative_paid=200),
        dict(rating_group="A", accident_year=2020, dev_age_months=24, cumulative_paid=400),
    ])
    ldfs = compute_ldfs(triangle)
    ldf_12_24 = ldfs.loc[ldfs.age_from == 12, "ldf"].iloc[0]
    assert ldf_12_24 == pytest.approx((150 + 400) / (100 + 200))


def test_latest_diagonal_picks_the_most_developed_observed_age():
    triangle = pd.DataFrame([
        dict(rating_group="A", accident_year=2024, dev_age_months=12, cumulative_paid=100),
        dict(rating_group="A", accident_year=2024, dev_age_months=24, cumulative_paid=180),
        dict(rating_group="A", accident_year=2025, dev_age_months=12, cumulative_paid=90),
    ])
    diag = latest_diagonal(triangle).set_index("accident_year")
    assert diag.loc[2024, "latest_dev_age_months"] == 24
    assert diag.loc[2024, "paid_to_date"] == 180
    assert diag.loc[2025, "latest_dev_age_months"] == 12
