"""Unit tests for the rule-based segment classifier."""

from datetime import datetime, timedelta

from app.services.segmentation import CustomerSignals, SegmentClassifier
from app.models.schemas import SegmentType

NOW = datetime(2026, 9, 11, 12, 0, 0)


def _signals(**overrides) -> CustomerSignals:
    defaults = dict(total_orders=5, lifetime_value=10_000.0,
                    last_purchase_at=NOW - timedelta(days=3), price_sensitivity=0.7, now=NOW)
    defaults.update(overrides)
    return CustomerSignals(**defaults)


def test_customer_without_orders_is_new_user():
    assert SegmentClassifier().classify(_signals(total_orders=0)) == SegmentType.NEW_USER


def test_idle_customer_is_dormant_even_with_high_ltv():
    signals = _signals(last_purchase_at=NOW - timedelta(days=60), total_orders=20, lifetime_value=90_000.0)
    assert SegmentClassifier().classify(signals) == SegmentType.DORMANT


def test_high_value_active_customer_is_vip():
    signals = _signals(total_orders=15, lifetime_value=75_000.0)
    assert SegmentClassifier().classify(signals) == SegmentType.VIP


def test_elastic_customer_is_price_sensitive():
    assert SegmentClassifier().classify(_signals(price_sensitivity=1.5)) == SegmentType.PRICE_SENSITIVE


def test_default_case_is_repeat_buyer():
    assert SegmentClassifier().classify(_signals()) == SegmentType.REPEAT_BUYER
