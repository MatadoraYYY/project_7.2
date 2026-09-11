"""Unit tests for the price sensitivity calculator."""

from app.services.elasticity import PriceSensitivityCalculator, PurchaseSignal


def _signals(specs: list[tuple[int, bool]]) -> list[PurchaseSignal]:
    return [PurchaseSignal(price=1000.0, quantity=qty, had_discount=disc) for qty, disc in specs]


def test_short_history_returns_neutral_default():
    calculator = PriceSensitivityCalculator()
    assert calculator.calculate(_signals([(1, False), (2, True)])) == 0.7


def test_missing_discount_group_returns_neutral_default():
    calculator = PriceSensitivityCalculator()
    assert calculator.calculate(_signals([(1, False), (2, False), (3, False)])) == 0.7


def test_higher_quantity_on_discount_raises_sensitivity():
    calculator = PriceSensitivityCalculator()
    score = calculator.calculate(_signals([(1, False), (1, False), (4, True), (4, True)]))
    assert score > 0.7


def test_result_is_clipped_to_configured_bounds():
    calculator = PriceSensitivityCalculator(min_bound=0.3, max_bound=2.0)
    score = calculator.calculate(_signals([(1, False), (1, False), (100, True), (100, True)]))
    assert score == 2.0


def test_invalid_bounds_are_rejected():
    import pytest
    with pytest.raises(ValueError):
        PriceSensitivityCalculator(min_bound=2.0, max_bound=1.0)
