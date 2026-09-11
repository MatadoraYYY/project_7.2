"""Tests for elasticity- and LTV-driven supplementary offer pools."""

from app.models.schemas import OfferType, SegmentType
from app.services.offer_engine import OfferContext, PersonalOfferEngine

engine = PersonalOfferEngine(top_n=20)


def test_price_insensitive_pool_is_mixed_in_for_low_elasticity():
    offers = engine.generate_offers(SegmentType.REPEAT_BUYER, 0.4, OfferContext(), lifetime_value=1000)
    types = {o.offer_type for o in offers}
    assert OfferType.PERSONAL_MANAGER in types


def test_price_sensitive_pool_is_mixed_in_for_high_elasticity():
    offers = engine.generate_offers(SegmentType.REPEAT_BUYER, 1.6, OfferContext(), lifetime_value=1000)
    types = {o.offer_type for o in offers}
    assert OfferType.BUNDLE in types


def test_high_ltv_pool_adds_concierge_offer():
    offers = engine.generate_offers(SegmentType.VIP, 0.5, OfferContext(), lifetime_value=90_000)
    types = {o.offer_type for o in offers}
    assert OfferType.CONCIERGE in types


def test_neutral_elasticity_keeps_base_catalog_only():
    offers = engine.generate_offers(SegmentType.REPEAT_BUYER, 0.9, OfferContext(), lifetime_value=1000)
    types = {o.offer_type for o in offers}
    assert OfferType.BUNDLE not in types and OfferType.PERSONAL_MANAGER not in types


def test_duplicate_templates_are_collapsed():
    offers = engine.generate_offers(SegmentType.VIP, 0.5, OfferContext(), lifetime_value=90_000)
    keys = [(o.offer_type, o.value) for o in offers]
    assert len(keys) == len(set(keys))
