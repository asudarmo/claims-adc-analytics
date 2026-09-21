import pytest

from engine.reinsurance import adc_terms, find_breakeven_shock, recovery


def test_adc_terms_basic_arithmetic():
    terms = adc_terms(booked_reserve=10_000_000, attachment_pct=1.05, exhaustion_pct=1.30, rate_on_line=0.12)
    assert terms.attachment == pytest.approx(10_500_000)
    assert terms.exhaustion == pytest.approx(13_000_000)
    assert terms.limit == pytest.approx(2_500_000)
    assert terms.premium == pytest.approx(300_000)


def test_recovery_is_zero_below_attachment():
    terms = adc_terms(10_000_000, 1.05, 1.30, 0.12)
    assert recovery(stressed_reserve=10_000_000, terms=terms) == pytest.approx(0.0)
    assert recovery(stressed_reserve=10_500_000, terms=terms) == pytest.approx(0.0)


def test_recovery_is_capped_at_the_limit():
    terms = adc_terms(10_000_000, 1.05, 1.30, 0.12)
    assert recovery(stressed_reserve=20_000_000, terms=terms) == pytest.approx(terms.limit)


def test_recovery_between_attachment_and_exhaustion_is_linear():
    terms = adc_terms(10_000_000, 1.05, 1.30, 0.12)
    # exactly halfway between attachment and exhaustion
    midpoint = terms.attachment + terms.limit / 2
    assert recovery(midpoint, terms) == pytest.approx(terms.limit / 2)


def test_find_breakeven_shock_matches_a_known_monotonic_function():
    terms = adc_terms(10_000_000, 1.05, 1.30, 0.12)  # limit = 2,500,000, attachment = 10,500,000

    # a synthetic reserve function: reserve = 10,000,000 * (1 + shock) ** 2,
    # so we know exactly where it crosses exhaustion (13,000,000)
    def reserve_at_shock(shock):
        return 10_000_000 * (1 + shock) ** 2

    expected_shock = (13_000_000 / 10_000_000) ** 0.5 - 1
    found_shock = find_breakeven_shock(reserve_at_shock, terms)
    assert found_shock == pytest.approx(expected_shock, abs=1e-5)
    assert recovery(reserve_at_shock(found_shock), terms) == pytest.approx(terms.limit, abs=50.0)


def test_find_breakeven_shock_returns_zero_when_already_exhausted_at_zero_shock():
    terms = adc_terms(10_000_000, 1.05, 1.30, 0.12)

    def reserve_at_shock(shock):
        return 20_000_000  # already well past exhaustion regardless of shock

    assert find_breakeven_shock(reserve_at_shock, terms) == pytest.approx(0.0)


def test_find_breakeven_shock_raises_when_unreachable():
    terms = adc_terms(10_000_000, 1.05, 1.30, 0.12)

    def reserve_at_shock(shock):
        return 10_000_000  # never moves, never exhausts

    with pytest.raises(ValueError):
        find_breakeven_shock(reserve_at_shock, terms)
