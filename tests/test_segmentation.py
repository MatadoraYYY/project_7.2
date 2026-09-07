"""Unit tests for the rule-based segment classifier."""

from datetime import datetime, timedelta

from app.models.schemas import SegmentType
from app.services.segmentation import CustomerSignals, SegmentClassifier


def _now():
    return datetime(2026, 9, 7, 12, 0, 0)


def test_zero_orders_is_new_user():
    classifier = SegmentClassifier()
    signals = CustomerSignals(total_orders=0, lifetime_value=0, last_purchase_at=None, price_sensitivity=0.7, now=_now())
    assert classifier.classify(signals) == SegmentType.NEW_USER


def test_inactive_for_30_days_is_dormant():
    classifier = SegmentClassifier()
    signals = CustomerSignals(total_orders=5, lifetime_value=1000, last_purchase_at=_now() - timedelta(days=45), price_sensitivity=0.7, now=_now())
    assert classifier.classify(signals) == SegmentType.DORMANT


def test_high_ltv_and_orders_is_vip():
    classifier = SegmentClassifier()
    signals = CustomerSignals(total_orders=12, lifetime_value=60000, last_purchase_at=_now() - timedelta(days=1), price_sensitivity=0.5, now=_now())
    assert classifier.classify(signals) == SegmentType.VIP


def test_high_price_sensitivity_wins_over_repeat_buyer():
    classifier = SegmentClassifier()
    signals = CustomerSignals(total_orders=4, lifetime_value=3000, last_purchase_at=_now() - timedelta(days=2), price_sensitivity=1.5, now=_now())
    assert classifier.classify(signals) == SegmentType.PRICE_SENSITIVE


def test_default_case_is_repeat_buyer():
    classifier = SegmentClassifier()
    signals = CustomerSignals(total_orders=3, lifetime_value=2000, last_purchase_at=_now() - timedelta(days=2), price_sensitivity=0.8, now=_now())
    assert classifier.classify(signals) == SegmentType.REPEAT_BUYER
