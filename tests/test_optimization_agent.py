"""Tests for the deterministic offer optimization agent."""

from app.models.schemas import ChannelType, OfferType, SegmentType, TimingType
from app.services.optimization_agent import OfferOptimizationAgent, OptimizationInput

agent = OfferOptimizationAgent()


def _payload(**overrides) -> OptimizationInput:
    defaults = dict(customer_id=1, segment=SegmentType.REPEAT_BUYER, price_sensitivity=0.9,
                    lifetime_value=10_000.0, total_orders=5, avg_order_value=2000.0,
                    days_since_last_purchase=5, cart_total=0.0, preferred_channel=ChannelType.PUSH)
    defaults.update(overrides)
    return OptimizationInput(**defaults)


def test_returns_at_most_three_recommendations():
    recommendations, _, _ = agent.get_recommendations(_payload(segment=SegmentType.VIP, lifetime_value=80_000, cart_total=5000))
    assert 1 <= len(recommendations) <= 3


def test_elastic_customer_receives_percentage_discount():
    recommendations, _, _ = agent.get_recommendations(_payload(price_sensitivity=1.6))
    assert any(r.offer_type == OfferType.DISCOUNT_PERCENT for r in recommendations)


def test_inelastic_customer_is_not_given_a_discount_first():
    recommendations, strategy, _ = agent.get_recommendations(_payload(price_sensitivity=0.4))
    assert recommendations[0].offer_type == OfferType.BONUS_POINTS
    assert "марж" in strategy


def test_live_cart_triggers_immediate_push():
    recommendations, _, _ = agent.get_recommendations(_payload(cart_total=4000))
    urgent = [r for r in recommendations if r.timing == TimingType.IMMEDIATE]
    assert urgent and urgent[0].channel == ChannelType.PUSH


def test_cart_recovery_for_inelastic_customer_protects_margin():
    """A customer who ignores price must not be offered a discount."""
    recommendations, _, _ = agent.get_recommendations(_payload(price_sensitivity=0.4, cart_total=8000))
    urgent = [r for r in recommendations if r.timing == TimingType.IMMEDIATE]
    assert urgent and urgent[0].offer_type == OfferType.FREE_SHIPPING


def test_cart_recovery_for_vip_avoids_discounts_entirely():
    recommendations, strategy, _ = agent.get_recommendations(
        _payload(segment=SegmentType.VIP, price_sensitivity=0.35, lifetime_value=90_000, cart_total=9000)
    )
    discount_types = {OfferType.DISCOUNT_PERCENT, OfferType.DISCOUNT_FIXED}
    assert not any(r.offer_type in discount_types for r in recommendations)
    assert "скидки не применять" in strategy.lower()


def test_dormant_customer_is_contacted_by_email_on_weekend():
    recommendations, _, _ = agent.get_recommendations(_payload(segment=SegmentType.DORMANT, days_since_last_purchase=90))
    weekend = [r for r in recommendations if r.timing == TimingType.WEEKEND]
    assert weekend and weekend[0].channel == ChannelType.EMAIL


def test_discount_depth_never_exceeds_thirty_percent():
    recommendations, _, _ = agent.get_recommendations(
        _payload(segment=SegmentType.DORMANT, price_sensitivity=2.0, days_since_last_purchase=200)
    )
    discounts = [r.value for r in recommendations if r.offer_type == OfferType.DISCOUNT_PERCENT]
    assert all(v <= 30.0 for v in discounts)


def test_recommendations_are_reproducible():
    first, strategy_a, engine_a = agent.get_recommendations(_payload(price_sensitivity=1.4, cart_total=3000))
    second, strategy_b, engine_b = agent.get_recommendations(_payload(price_sensitivity=1.4, cart_total=3000))
    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]
    assert strategy_a == strategy_b and engine_a == engine_b


def test_every_recommendation_carries_reasoning():
    recommendations, _, _ = agent.get_recommendations(_payload(segment=SegmentType.NEW_USER, total_orders=0))
    assert all(r.reasoning.strip() for r in recommendations)
