import pytest

from engine.credibility import blend_elr, credibility_z, experience_indication, on_level_factor, trend_factor


def test_on_level_factor_is_1_for_the_latest_year():
    idx = {2020: 1.0, 2023: 1.15, 2025: 1.30}
    olf = on_level_factor(idx, latest_year=2025)
    assert olf[2025] == pytest.approx(1.0)
    assert olf[2020] == pytest.approx(1.30 / 1.0)
    assert olf[2023] == pytest.approx(1.30 / 1.15)


def test_trend_factor_grows_older_years_up_to_latest():
    assert trend_factor(2025, latest_year=2025, loss_trend=0.055) == pytest.approx(1.0)
    assert trend_factor(2020, latest_year=2025, loss_trend=0.055) == pytest.approx(1.055 ** 5)


def test_experience_indication_is_trended_claims_over_on_level_premium():
    mature_years = [2020, 2021]
    cl = {2020: 1000, 2021: 1200}
    trend = {2020: 1.1, 2021: 1.05}
    olp = {2020: 2000, 2021: 2200}
    ei = experience_indication(mature_years, cl, trend, olp)
    assert ei == pytest.approx((1000 * 1.1 + 1200 * 1.05) / (2000 + 2200))


def test_credibility_z_is_capped_at_1():
    assert credibility_z(claim_count=1082, cred_full=1082) == pytest.approx(1.0)
    assert credibility_z(claim_count=5000, cred_full=1082) == pytest.approx(1.0)  # capped, not > 1
    assert credibility_z(claim_count=270.5, cred_full=1082) == pytest.approx(0.5)  # sqrt(1/4) = 0.5


def test_blend_elr_at_the_extremes():
    assert blend_elr(z=1.0, experience_indication_value=0.8, plan_loss_ratio=0.6) == pytest.approx(0.8)
    assert blend_elr(z=0.0, experience_indication_value=0.8, plan_loss_ratio=0.6) == pytest.approx(0.6)
    assert blend_elr(z=0.5, experience_indication_value=0.8, plan_loss_ratio=0.6) == pytest.approx(0.7)
