"""Unit tests for the price sensitivity calculator."""

import pytest

from app.services.elasticity import PriceSensitivityCalculator, PurchaseSignal


def test_returns_default_when_history_too_short():
    calc = PriceSensitivityCalculator()
    assert calc.calculate([PurchaseSignal(price=100, quantity=1, had_discount=False)]) == 0.7


def test_returns_default_when_no_discounted_purchases():
    calc = PriceSensitivityCalculator()
    purchases = [PurchaseSignal(price=100, quantity=1, had_discount=False) for _ in range(5)]
    assert calc.calculate(purchases) == 0.7


def test_higher_quantity_on_discount_increases_sensitivity():
    calc = PriceSensitivityCalculator()
    purchases = [
        PurchaseSignal(price=100, quantity=1, had_discount=False),
        PurchaseSignal(price=100, quantity=1, had_discount=False),
        PurchaseSignal(price=80, quantity=3, had_discount=True),
        PurchaseSignal(price=80, quantity=3, had_discount=True),
    ]
    assert calc.calculate(purchases) > 0.7


def test_result_is_always_within_bounds():
    calc = PriceSensitivityCalculator(min_bound=0.3, max_bound=2.0)
    purchases = [
        PurchaseSignal(price=10, quantity=1, had_discount=False),
        PurchaseSignal(price=10, quantity=1, had_discount=False),
        PurchaseSignal(price=5, quantity=100, had_discount=True),
    ]
    assert 0.3 <= calc.calculate(purchases) <= 2.0


def test_invalid_bounds_raise_value_error():
    with pytest.raises(ValueError):
        PriceSensitivityCalculator(min_bound=2.0, max_bound=1.0)
