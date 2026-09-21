import pytest

from engine.methods import bornhuetter_ferguson, chain_ladder, expected_claims


def test_chain_ladder_is_paid_times_cdf():
    assert chain_ladder(paid_to_date=1000, cdf_to_ultimate=2.5) == pytest.approx(2500)


def test_expected_claims_divides_out_the_trend():
    # OLP=1,000,000, ELR=0.65, trend=1.1 -> EC at this year's own cost level
    ec = expected_claims(on_level_premium=1_000_000, elr=0.65, trend=1.1)
    assert ec == pytest.approx(1_000_000 * 0.65 / 1.1)


def test_bornhuetter_ferguson_between_paid_and_paid_plus_full_expected():
    paid = 1000
    ec = 5000
    cdf = 2.0  # half of ultimate still to develop
    bf = bornhuetter_ferguson(paid, ec, cdf)
    assert bf == pytest.approx(paid + ec * 0.5)
    assert paid < bf < paid + ec


def test_bornhuetter_ferguson_at_cdf_1_equals_paid():
    # a fully-developed claim (CDF=1) has nothing left to add from the a priori
    assert bornhuetter_ferguson(paid_to_date=5000, expected_claims_ultimate=9999, cdf_to_ultimate=1.0) == pytest.approx(5000)
