"""Personal offer generation engine with explainable, rule-based scoring."""

import uuid
from dataclasses import dataclass

from app.core.config import get_settings
from app.models.schemas import GeneratedOffer, OfferType, SegmentType

settings = get_settings()

MAX_SCORE = 0.95
MIN_SCORE = 0.05

PRICE_INSENSITIVE_THRESHOLD = 0.6
PRICE_SENSITIVE_THRESHOLD = 1.2


@dataclass(frozen=True)
class OfferTemplate:
    offer_type: OfferType
    value: float
    title: str
    base_score: float
    min_order_value: float = 0.0


@dataclass(frozen=True)
class OfferContext:
    cart_total: float = 0.0
    is_abandoned_cart: bool = False
    favorite_category_matches: bool = False


_OFFER_CATALOG: dict[SegmentType, list[OfferTemplate]] = {
    SegmentType.NEW_USER: [
        OfferTemplate(OfferType.DISCOUNT_PERCENT, 15, "Скидка 15% на первый заказ", base_score=0.55),
        OfferTemplate(OfferType.FREE_SHIPPING, 0, "Бесплатная доставка", base_score=0.45),
        OfferTemplate(OfferType.BONUS_POINTS, 300, "300 бонусных баллов", base_score=0.35),
    ],
    SegmentType.REPEAT_BUYER: [
        OfferTemplate(OfferType.BONUS_POINTS, 500, "500 бонусных баллов", base_score=0.5, min_order_value=3000),
        OfferTemplate(OfferType.DISCOUNT_FIXED, 300, "Скидка 300 рублей", base_score=0.45, min_order_value=3000),
        OfferTemplate(OfferType.FREE_SHIPPING, 0, "Бесплатная доставка", base_score=0.4),
    ],
    SegmentType.VIP: [
        OfferTemplate(OfferType.EARLY_ACCESS, 0, "Ранний доступ к новой коллекции", base_score=0.5),
        OfferTemplate(OfferType.BONUS_POINTS, 1000, "1000 бонусных баллов", base_score=0.45),
        OfferTemplate(OfferType.GIFT, 0, "Премиальный подарок к заказу", base_score=0.4, min_order_value=5000),
    ],
    SegmentType.DORMANT: [
        OfferTemplate(OfferType.DISCOUNT_PERCENT, 25, "Скидка 25% на возвращение", base_score=0.6),
        OfferTemplate(OfferType.FREE_SHIPPING, 0, "Бесплатная доставка", base_score=0.5),
        OfferTemplate(OfferType.GIFT, 0, "Подарок при заказе от 3000 рублей", base_score=0.4, min_order_value=3000),
    ],
    SegmentType.PRICE_SENSITIVE: [
        OfferTemplate(OfferType.DISCOUNT_PERCENT, 20, "Скидка 20% на заказ", base_score=0.6),
        OfferTemplate(OfferType.DISCOUNT_FIXED, 500, "Скидка 500 рублей от 3000 рублей", base_score=0.5, min_order_value=3000),
        OfferTemplate(OfferType.FREE_SHIPPING, 0, "Бесплатная доставка", base_score=0.45),
    ],
}

# Supplementary pools mixed into the segment catalog when the customer's
# elasticity or lifetime value justifies it (see technical specification).
_PRICE_SENSITIVE_POOL: list[OfferTemplate] = [
    OfferTemplate(OfferType.BUNDLE, 0, "Комплект «2+1» на любимую категорию", base_score=0.5),
    OfferTemplate(OfferType.DISCOUNT_FIXED, 1000, "Скидка 1000 рублей от 3000 рублей", base_score=0.45, min_order_value=3000),
]

_PRICE_INSENSITIVE_POOL: list[OfferTemplate] = [
    OfferTemplate(OfferType.EARLY_ACCESS, 0, "Эксклюзивный ранний доступ", base_score=0.45),
    OfferTemplate(OfferType.PERSONAL_MANAGER, 0, "Персональный менеджер", base_score=0.4),
]

_HIGH_LTV_POOL: list[OfferTemplate] = [
    OfferTemplate(OfferType.CONCIERGE, 0, "Консьерж-сервис", base_score=0.5),
    OfferTemplate(OfferType.BONUS_POINTS, 5000, "5000 бонусных баллов", base_score=0.45),
]


class PersonalOfferEngine:
    def __init__(self, top_n: int = 3) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be a positive integer")
        self._top_n = top_n

    def generate_offers(
        self,
        segment: SegmentType,
        price_sensitivity: float,
        context: OfferContext | None = None,
        lifetime_value: float = 0.0,
    ) -> list[GeneratedOffer]:
        context = context or OfferContext()
        templates = self._build_offer_pool(segment, price_sensitivity, lifetime_value)
        if not templates:
            return []
        scored = [self._score(t, price_sensitivity, context) for t in templates]
        scored.sort(key=lambda o: o.score, reverse=True)
        return scored[: self._top_n]

    def _build_offer_pool(self, segment: SegmentType, price_sensitivity: float, lifetime_value: float) -> list[OfferTemplate]:
        """Combine the segment catalog with elasticity- and LTV-driven pools."""
        pool = list(_OFFER_CATALOG.get(segment, []))

        if price_sensitivity < PRICE_INSENSITIVE_THRESHOLD:
            pool += _PRICE_INSENSITIVE_POOL
        elif price_sensitivity > PRICE_SENSITIVE_THRESHOLD:
            pool += _PRICE_SENSITIVE_POOL

        if lifetime_value > settings.vip_ltv_threshold:
            pool += _HIGH_LTV_POOL

        return self._deduplicate(pool)

    @staticmethod
    def _deduplicate(templates: list[OfferTemplate]) -> list[OfferTemplate]:
        """Keep the highest-scoring template for each (type, value) pair."""
        best: dict[tuple[OfferType, float], OfferTemplate] = {}
        for template in templates:
            key = (template.offer_type, template.value)
            current = best.get(key)
            if current is None or template.base_score > current.base_score:
                best[key] = template
        return list(best.values())

    def _score(self, template: OfferTemplate, price_sensitivity: float, context: OfferContext) -> GeneratedOffer:
        score = template.base_score
        reasons: list[str] = []

        if template.min_order_value and context.cart_total < template.min_order_value:
            score -= 0.15
            reasons.append(f"Сумма корзины ({context.cart_total:.0f}) ниже минимального порога ({template.min_order_value:.0f}) для этого оффера")
        elif template.min_order_value:
            score += 0.1
            reasons.append("Сумма корзины соответствует условиям оффера")

        if context.is_abandoned_cart and template.offer_type == OfferType.DISCOUNT_PERCENT:
            score += 0.2
            reasons.append("Обнаружена брошенная корзина, скидка стимулирует завершение заказа")

        if price_sensitivity >= 1.2 and template.offer_type in (OfferType.DISCOUNT_PERCENT, OfferType.DISCOUNT_FIXED, OfferType.BUNDLE):
            score += 0.15
            reasons.append("Клиент чувствителен к цене, скидка повышает вероятность конверсии")

        if price_sensitivity < 0.7 and template.offer_type in (OfferType.EARLY_ACCESS, OfferType.GIFT, OfferType.PERSONAL_MANAGER, OfferType.CONCIERGE):
            score += 0.1
            reasons.append("Клиент малочувствителен к цене, нематериальная ценность работает лучше скидки")

        if context.favorite_category_matches:
            score += 0.05
            reasons.append("Предложение относится к любимой категории клиента")

        score = max(MIN_SCORE, min(MAX_SCORE, score))
        reason_text = "; ".join(reasons) if reasons else "Базовая рекомендация для сегмента клиента"

        return GeneratedOffer(
            offer_uid=f"offer-{uuid.uuid4().hex[:12]}",
            offer_type=template.offer_type,
            value=template.value,
            title=template.title,
            score=round(score, 2),
            expected_conversion=round(score, 2),
            reason=reason_text,
        )
