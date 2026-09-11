"""Unit tests for the personal offer engine."""

from app.models.schemas import OfferType, SegmentType
from app.services.offer_engine import OfferContext, PersonalOfferEngine


def test_returns_at_most_three_offers():
    offers = PersonalOfferEngine(top_n=3).generate_offers(SegmentType.DORMANT, 0.7, OfferContext())
    assert len(offers) <= 3


def test_offers_are_sorted_by_descending_score():
    offers = PersonalOfferEngine().generate_offers(SegmentType.PRICE_SENSITIVE, 1.5, OfferContext(cart_total=5000))
    scores = [o.score for o in offers]
    assert scores == sorted(scores, reverse=True)


def test_cart_below_threshold_is_penalised_with_explanation():
    offers = PersonalOfferEngine(top_n=10).generate_offers(
        SegmentType.REPEAT_BUYER, 0.7, OfferContext(cart_total=100)
    )
    penalised = [o for o in offers if "ниже минимального порога" in o.reason]
    assert penalised


def test_abandoned_cart_boosts_percentage_discount():
    engine = PersonalOfferEngine(top_n=10)
    baseline = engine.generate_offers(SegmentType.DORMANT, 0.7, OfferContext(cart_total=1000))
    boosted = engine.generate_offers(SegmentType.DORMANT, 0.7, OfferContext(cart_total=1000, is_abandoned_cart=True))

    def percent_score(offers):
        return max(o.score for o in offers if o.offer_type == OfferType.DISCOUNT_PERCENT)

    assert percent_score(boosted) > percent_score(baseline)


def test_scores_never_exceed_bounds():
    offers = PersonalOfferEngine(top_n=10).generate_offers(
        SegmentType.PRICE_SENSITIVE, 2.0, OfferContext(cart_total=99_999, is_abandoned_cart=True, favorite_category_matches=True)
    )
    assert all(0.05 <= o.score <= 0.95 for o in offers)
