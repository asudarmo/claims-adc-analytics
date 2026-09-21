import pandas as pd
import pytest

from engine import methods
from engine.extension import apply_extension_to_ultimate, apply_tail, inflation_uplift, payment_lag_years
from engine.main import compute_scenario_ultimates


def test_apply_tail_of_1_is_a_no_op():
    assert apply_tail(2.53, ext_tail=1.0) == pytest.approx(2.53)


def test_inflation_uplift_of_zero_shock_is_1():
    assert inflation_uplift(lag_years=5.0, ext_shock=0.0) == pytest.approx(1.0)


def test_extension_with_no_uplift_returns_the_tail_adjusted_ultimate_unchanged():
    assert apply_extension_to_ultimate(paid_to_date=1000, tail_adjusted_ultimate=2500, uplift=1.0) == pytest.approx(2500)


def test_payment_lag_is_just_the_tail_lag_for_a_fully_developed_year():
    assert payment_lag_years(latest_dev_age_months=72, ext_tail_lag_years=3.0) == pytest.approx(3.0)


def test_payment_lag_is_longer_for_a_less_mature_year():
    assert payment_lag_years(12, ext_tail_lag_years=3.0) > payment_lag_years(60, ext_tail_lag_years=3.0)


@pytest.fixture
def toy_context():
    diagonal = pd.DataFrame(
        [dict(accident_year=2024, paid_to_date=1000.0, latest_dev_age_months=24),
         dict(accident_year=2025, paid_to_date=500.0, latest_dev_age_months=12)]
    ).set_index("accident_year")
    return {
        "A": dict(
            diagonal=diagonal,
            cdf_at_latest={2024: 1.5, 2025: 2.5},
            on_level_premium={2024: 3000.0, 2025: 3200.0},
            trend={2024: 1.055, 2025: 1.0},
            z=0.6,
            elr=None,  # recomputed internally from the mature-year experience indication
            mature_years=[2024],
        )
    }


def test_tail_1_shock_0_reproduces_the_base_scenario_exactly(toy_context):
    """
    The invariant stated directly in the original assignment: setting the
    tail factor to 1.0 and the inflation shock to 0 must reproduce the base
    scenario exactly for every method. This is the single most important
    correctness check on the whole extension module - if this doesn't
    hold, the stress scenario isn't a modification of the base case, it's
    a different, incomparable calculation.
    """
    assumptions_by_group = {"A": {"plan_loss_ratio": 0.65, "ext_tail_factor": 1.3, "expense_ratio": 0.27}}

    base = compute_scenario_ultimates(
        toy_context, assumptions_by_group, tail_by_group={"A": 1.0}, shock=0.0, ext_tail_lag_years=0.0,
    )

    # recompute the same figures directly from methods.py, with no tail/shock machinery at all
    ctx = toy_context["A"]
    cl_2024 = methods.chain_ladder(1000.0, 1.5)
    cl_2025 = methods.chain_ladder(500.0, 2.5)
    from engine.credibility import blend_elr, experience_indication
    ei = experience_indication([2024], {2024: cl_2024, 2025: cl_2025}, ctx["trend"], ctx["on_level_premium"])
    elr = blend_elr(ctx["z"], ei, 0.65)
    ec_2024 = methods.expected_claims(ctx["on_level_premium"][2024], elr, ctx["trend"][2024])
    ec_2025 = methods.expected_claims(ctx["on_level_premium"][2025], elr, ctx["trend"][2025])
    bf_2024 = methods.bornhuetter_ferguson(1000.0, ec_2024, 1.5)
    bf_2025 = methods.bornhuetter_ferguson(500.0, ec_2025, 2.5)

    expected = {
        ("ChainLadder", 2024): cl_2024, ("ChainLadder", 2025): cl_2025,
        ("ExpectedClaims", 2024): ec_2024, ("ExpectedClaims", 2025): ec_2025,
        ("BornhuetterFerguson", 2024): bf_2024, ("BornhuetterFerguson", 2025): bf_2025,
    }
    for row in base.itertuples():
        assert row.ultimate == pytest.approx(expected[(row.method, row.accident_year)])


def test_a_real_tail_and_shock_increases_every_method_ultimate(toy_context):
    assumptions_by_group = {"A": {"plan_loss_ratio": 0.65, "ext_tail_factor": 1.3, "expense_ratio": 0.27}}

    base = compute_scenario_ultimates(toy_context, assumptions_by_group, {"A": 1.0}, 0.0, 0.0)
    stressed = compute_scenario_ultimates(toy_context, assumptions_by_group, {"A": 1.3}, 0.04, 3.0)

    merged = base.merge(stressed, on=["rating_group", "accident_year", "method"], suffixes=("_base", "_stressed"))
    assert (merged["ultimate_stressed"] >= merged["ultimate_base"]).all()
