"""Unit tests for the personal offer engine."""

from app.models.schemas import SegmentType
from app.services.offer_engine import OfferContext, PersonalOfferEngine


def test_generates_top_n_offers():
    engine = PersonalOfferEngine(top_n=3)
    offers = engine.generate_offers(SegmentType.NEW_USER, price_sensitivity=0.7)
    assert len(offers) <= 3
    assert all(0 <= o.score <= 1 for o in offers)


def test_offers_sorted_by_score_descending():
    engine = PersonalOfferEngine(top_n=5)
    offers = engine.generate_offers(SegmentType.PRICE_SENSITIVE, price_sensitivity=1.5)
    scores = [o.score for o in offers]
    assert scores == sorted(scores, reverse=True)


def test_below_min_order_value_reduces_score():
    engine = PersonalOfferEngine(top_n=5)
    offers_low = engine.generate_offers(SegmentType.REPEAT_BUYER, price_sensitivity=0.9, context=OfferContext(cart_total=100))
    offers_high = engine.generate_offers(SegmentType.REPEAT_BUYER, price_sensitivity=0.9, context=OfferContext(cart_total=10000))

    bonus_low = next(o for o in offers_low if o.title == "500 бонусных баллов")
    bonus_high = next(o for o in offers_high if o.title == "500 бонусных баллов")
    assert bonus_high.score > bonus_low.score


def test_unknown_segment_returns_empty_list():
    engine = PersonalOfferEngine()
    offers = engine.generate_offers(SegmentType.NEW_USER, price_sensitivity=0.7)
    assert isinstance(offers, list)


def test_abandoned_cart_boosts_discount_offer_score():
    engine = PersonalOfferEngine(top_n=5)
    baseline = engine.generate_offers(SegmentType.DORMANT, price_sensitivity=1.0, context=OfferContext(cart_total=0, is_abandoned_cart=False))
    boosted = engine.generate_offers(SegmentType.DORMANT, price_sensitivity=1.0, context=OfferContext(cart_total=0, is_abandoned_cart=True))

    baseline_discount = next(o for o in baseline if o.title == "Скидка 25% на возвращение")
    boosted_discount = next(o for o in boosted if o.title == "Скидка 25% на возвращение")
    assert boosted_discount.score >= baseline_discount.score
