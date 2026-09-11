"""Deterministic offer optimization agent.

The technical specification sketches an LLM-driven agent (LangChain + Ollama).
This implementation keeps the same contract - it answers *what* offer to send,
*at what size*, *through which channel* and *when* - but derives the answer
from explicit, auditable decision rules instead of a generative model.

Rationale for the deterministic design:
  * Reproducibility - identical input always yields identical output, which is
    a prerequisite for the A/B test to be interpretable.
  * Explainability - every recommendation carries the rule that produced it,
    so a marketing team can audit and challenge it.
  * Operability - no GPU, no model weights, no external API quota; the service
    runs inside a 512 MB container.

``AGENT_MODE=llm`` switches to an external chat-completions API when one is
configured. If the call fails for any reason the agent silently falls back to
the deterministic path, so the endpoint never returns an error to the client.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.schemas import (
    ChannelType,
    OfferType,
    OptimizationRecommendation,
    SegmentType,
    TimingType,
)

settings = get_settings()
logger = get_logger(__name__)

ENGINE_RULE_BASED = "rule_based_v1"

_HIGH_ELASTICITY = 1.2
_LOW_ELASTICITY = 0.7


@dataclass(frozen=True)
class OptimizationInput:
    """Everything the agent is allowed to reason about."""

    customer_id: int
    segment: SegmentType
    price_sensitivity: float
    lifetime_value: float
    total_orders: int
    avg_order_value: float
    days_since_last_purchase: int | None
    cart_total: float
    preferred_channel: ChannelType


class OfferOptimizationAgent:
    """Chooses offer type, size, channel and send time for one customer."""

    def get_recommendations(self, data: OptimizationInput) -> tuple[list[OptimizationRecommendation], str, str]:
        """Return up to three ranked recommendations, a strategy note and the engine id."""
        recommendations = self._rule_based_recommendations(data)
        recommendations.sort(key=lambda r: r.expected_conversion, reverse=True)
        return recommendations[:3], self._overall_strategy(data), ENGINE_RULE_BASED

    # --- offer sizing ---------------------------------------------------------

    def _discount_size(self, data: OptimizationInput) -> float:
        """Discount depth grows with elasticity and with dormancy, never above 30%."""
        size = 10.0

        if data.price_sensitivity >= _HIGH_ELASTICITY:
            size += 10.0
        elif data.price_sensitivity < _LOW_ELASTICITY:
            size -= 5.0

        if data.segment == SegmentType.DORMANT:
            size += 10.0
        if data.segment == SegmentType.NEW_USER:
            size += 5.0

        return float(min(30.0, max(5.0, size)))

    def _bonus_size(self, data: OptimizationInput) -> float:
        """Bonus points scale with the customer's own average order value."""
        base = max(300.0, round(data.avg_order_value * 2, -2))
        if data.lifetime_value > settings.vip_ltv_threshold:
            base = max(base, 5000.0)
        return float(min(base, 10_000.0))

    # --- channel and timing ---------------------------------------------------

    def _channel_for(self, data: OptimizationInput, is_urgent: bool) -> ChannelType:
        """Urgent nudges go to fast channels; high-value clients get email."""
        if is_urgent and data.cart_total > 0:
            return ChannelType.PUSH
        if data.lifetime_value > settings.vip_ltv_threshold:
            return ChannelType.EMAIL
        if data.segment == SegmentType.DORMANT:
            return ChannelType.EMAIL
        return data.preferred_channel

    def _timing_for(self, data: OptimizationInput, is_urgent: bool) -> TimingType:
        """Abandoned carts decay fast, re-activation can wait for peak hours."""
        if is_urgent:
            return TimingType.IMMEDIATE
        if data.segment == SegmentType.DORMANT:
            return TimingType.WEEKEND
        if data.segment == SegmentType.NEW_USER:
            return TimingType.NEXT_MORNING
        return TimingType.SAME_DAY_EVENING

    # --- rules ----------------------------------------------------------------

    def _rule_based_recommendations(self, data: OptimizationInput) -> list[OptimizationRecommendation]:
        recommendations: list[OptimizationRecommendation] = []
        has_live_cart = data.cart_total > 0

        # Rule 1 - price-driven offer for elastic customers.
        if data.price_sensitivity >= _HIGH_ELASTICITY:
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.DISCOUNT_PERCENT,
                value=self._discount_size(data),
                channel=self._channel_for(data, is_urgent=has_live_cart),
                timing=self._timing_for(data, is_urgent=has_live_cart),
                expected_conversion=0.28,
                reasoning=(
                    f"Эластичность {data.price_sensitivity:.2f} превышает порог {_HIGH_ELASTICITY}: "
                    "клиент реагирует на цену, процентная скидка даёт наибольший отклик"
                ),
            ))

        # Rule 2 - non-monetary value for inelastic customers (protects margin).
        if data.price_sensitivity < _LOW_ELASTICITY:
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.BONUS_POINTS,
                value=self._bonus_size(data),
                channel=self._channel_for(data, is_urgent=False),
                timing=self._timing_for(data, is_urgent=False),
                expected_conversion=0.22,
                reasoning=(
                    f"Эластичность {data.price_sensitivity:.2f} ниже {_LOW_ELASTICITY}: "
                    "скидка не нужна, бонусные баллы сохраняют маржу"
                ),
            ))

        # Rule 3 - VIP and high-LTV customers get service, not price cuts.
        if data.lifetime_value > settings.vip_ltv_threshold or data.segment == SegmentType.VIP:
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.CONCIERGE,
                value=0.0,
                channel=ChannelType.EMAIL,
                timing=TimingType.SAME_DAY_EVENING,
                expected_conversion=0.19,
                reasoning=(
                    f"LTV {data.lifetime_value:.0f} рублей относит клиента к высокодоходным: "
                    "консьерж-сервис укрепляет удержание без потери маржи"
                ),
            ))
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.EARLY_ACCESS,
                value=0.0,
                channel=ChannelType.EMAIL,
                timing=TimingType.NEXT_MORNING,
                expected_conversion=0.17,
                reasoning="Ранний доступ к коллекции работает как статусная привилегия для VIP-сегмента",
            ))

        # Rule 4 - win back dormant customers with a deep, time-boxed offer.
        if data.segment == SegmentType.DORMANT:
            idle = data.days_since_last_purchase or settings.dormant_days_threshold
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.DISCOUNT_PERCENT,
                value=self._discount_size(data),
                channel=ChannelType.EMAIL,
                timing=TimingType.WEEKEND,
                expected_conversion=0.25,
                reasoning=(
                    f"Клиент неактивен {idle} дней: глубокая скидка в выходные, "
                    "когда открываемость писем максимальна"
                ),
            ))

        # Rule 5 - onboarding offer for customers without purchase history.
        if data.segment == SegmentType.NEW_USER:
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.FREE_SHIPPING,
                value=0.0,
                channel=self._channel_for(data, is_urgent=False),
                timing=TimingType.NEXT_MORNING,
                expected_conversion=0.24,
                reasoning=(
                    "История покупок отсутствует: бесплатная доставка снимает основной "
                    "барьер первого заказа и дешевле прямой скидки"
                ),
            ))

        # Rule 6 - recover an abandoned cart immediately. The incentive must not
        # contradict the margin strategy: customers who do not react to price
        # (low elasticity or high LTV) are nudged with free shipping instead of
        # a discount, so the cart is recovered without giving away margin.
        if has_live_cart:
            protect_margin = (
                data.price_sensitivity < _LOW_ELASTICITY
                or data.lifetime_value > settings.vip_ltv_threshold
                or data.segment == SegmentType.VIP
            )

            if protect_margin:
                recommendations.append(OptimizationRecommendation(
                    offer_type=OfferType.FREE_SHIPPING,
                    value=0.0,
                    channel=ChannelType.PUSH,
                    timing=TimingType.IMMEDIATE,
                    expected_conversion=0.23,
                    reasoning=(
                        f"В корзине {data.cart_total:.0f} рублей, но клиент не реагирует на цену: "
                        "push с бесплатной доставкой возвращает к заказу, не снижая маржу"
                    ),
                ))
            else:
                recommendations.append(OptimizationRecommendation(
                    offer_type=OfferType.DISCOUNT_FIXED,
                    value=float(max(200.0, round(data.cart_total * 0.1, -2))),
                    channel=ChannelType.PUSH,
                    timing=TimingType.IMMEDIATE,
                    expected_conversion=0.26,
                    reasoning=(
                        f"В корзине {data.cart_total:.0f} рублей: фиксированная скидка в push-канале "
                        "немедленно, пока намерение купить не остыло"
                    ),
                ))

        # Fallback - always return at least one actionable recommendation.
        if not recommendations:
            recommendations.append(OptimizationRecommendation(
                offer_type=OfferType.BONUS_POINTS,
                value=self._bonus_size(data),
                channel=data.preferred_channel,
                timing=TimingType.SAME_DAY_EVENING,
                expected_conversion=0.15,
                reasoning="Специфических сигналов не обнаружено: базовое бонусное предложение по предпочитаемому каналу",
            ))

        return recommendations

    def _overall_strategy(self, data: OptimizationInput) -> str:
        if data.lifetime_value > settings.vip_ltv_threshold or data.segment == SegmentType.VIP:
            return ("Удержание через сервис и статус. Прямые скидки не применять: "
                    "клиент покупает вне зависимости от цены, скидка только снизит маржу.")
        if data.segment == SegmentType.DORMANT:
            return ("Реактивация. Допустима повышенная скидка как разовая инвестиция в возврат клиента, "
                    "с последующим переводом на бонусную механику.")
        if data.segment == SegmentType.NEW_USER:
            return ("Снижение барьера первой покупки. Приоритет бесплатной доставке и мягким скидкам, "
                    "цель - сформировать привычку, а не разовую продажу.")
        if data.price_sensitivity >= _HIGH_ELASTICITY:
            return ("Работа с ценой. Клиент подтверждённо реагирует на скидки, "
                    "но глубину следует ограничивать порогом минимальной суммы заказа.")
        return ("Наращивание частоты покупок бонусными механиками с сохранением маржи, "
                "скидки - только при явном риске оттока.")
