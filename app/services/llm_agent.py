"""LLM-backed offer optimization agent (OpenRouter).

This module is ADDITIVE: it does not modify or monkey-patch any existing
module. It wraps the deterministic ``OfferOptimizationAgent`` and adds a
second, generative engine that calls the OpenRouter chat-completions API.

Design contract
---------------
The class exposes exactly the same method signature as the deterministic
agent::

    get_recommendations(data: OptimizationInput)
        -> tuple[list[OptimizationRecommendation], str, str]

so any caller can swap one engine for the other without further changes.

Safety guarantees
-----------------
The language model is treated as an *untrusted* source of suggestions, never
as an authority. Every field it returns passes through ``_sanitize``:

  * ``offer_type``, ``channel`` and ``timing`` must match the project enums,
    otherwise the recommendation is discarded;
  * percentage discounts are clamped to the same 30% ceiling the
    deterministic agent enforces;
  * a discount is stripped entirely for customers the margin policy protects
    (low elasticity, VIP, or high lifetime value);
  * ``expected_conversion`` is clamped to [0, 1].

If the API key is absent, the network call fails, the response is malformed,
or every suggestion is rejected, the agent falls back to the deterministic
engine. The endpoint therefore never fails because of the model.
"""

from __future__ import annotations

import json
import os

import httpx

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.schemas import (
    ChannelType,
    OfferType,
    OptimizationRecommendation,
    SegmentType,
    TimingType,
)
from app.services.optimization_agent import (
    OfferOptimizationAgent,
    OptimizationInput,
)

settings = get_settings()
logger = get_logger(__name__)

ENGINE_LLM = "openrouter_llm_v1"
ENGINE_FALLBACK = "rule_based_v1_fallback"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_DISCOUNT_PERCENT = 30.0
MAX_RECOMMENDATIONS = 3
LOW_ELASTICITY = 0.7

SYSTEM_PROMPT = (
    "Ты - аналитик по промо-акциям в электронной коммерции. "
    "По профилю клиента предложи до трёх промо-предложений. "
    "Для каждого укажи тип оффера, его размер, канал доставки, время отправки, "
    "ожидаемую конверсию и краткое обоснование на русском языке. "
    "Правила, которые нельзя нарушать: процентная скидка не выше 30; "
    "клиенту с эластичностью ниже 0.7 или с LTV выше "
    f"{settings.vip_ltv_threshold:.0f} рублей скидки не предлагай - "
    "используй бонусы, подарок, ранний доступ, персонального менеджера "
    "или консьерж-сервис, чтобы сохранить маржу. "
    "Отвечай только объектом JSON без пояснений вне JSON."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_strategy": {"type": "string"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "offer_type": {"type": "string", "enum": [t.value for t in OfferType]},
                    "value": {"type": "number"},
                    "channel": {"type": "string", "enum": [c.value for c in ChannelType]},
                    "timing": {"type": "string", "enum": [t.value for t in TimingType]},
                    "expected_conversion": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "offer_type", "value", "channel",
                    "timing", "expected_conversion", "reasoning",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_strategy", "recommendations"],
    "additionalProperties": False,
}

_DISCOUNT_TYPES = (OfferType.DISCOUNT_PERCENT, OfferType.DISCOUNT_FIXED)


class OpenRouterOptimizationAgent:
    """Generative offer optimizer with a deterministic safety net."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self._model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
        self._timeout = timeout if timeout is not None else float(
            os.getenv("OPENROUTER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self._client = client
        self._fallback = OfferOptimizationAgent()

    @property
    def is_configured(self) -> bool:
        """True when an API key is present, so a live call can be attempted."""
        return bool(self._api_key)

    # --- public contract ------------------------------------------------------

    def get_recommendations(
        self, data: OptimizationInput
    ) -> tuple[list[OptimizationRecommendation], str, str]:
        """Return recommendations, a strategy note and the engine identifier."""
        if not self.is_configured:
            logger.info("OPENROUTER_API_KEY is not set, using the deterministic engine")
            return self._fallback_result(data)

        try:
            payload = self._call_model(data)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as error:
            logger.warning("OpenRouter call failed (%s), using the deterministic engine", error)
            return self._fallback_result(data)

        recommendations = self._sanitize(payload.get("recommendations", []), data)
        if not recommendations:
            logger.warning("Every LLM suggestion was rejected, using the deterministic engine")
            return self._fallback_result(data)

        strategy = str(payload.get("overall_strategy") or "").strip()
        if not strategy:
            strategy = self._fallback._overall_strategy(data)

        return recommendations[:MAX_RECOMMENDATIONS], strategy, ENGINE_LLM

    # --- transport ------------------------------------------------------------

    def _call_model(self, data: OptimizationInput) -> dict:
        request_body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_prompt(data)},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "offer_recommendations",
                    "strict": True,
                    "schema": RESPONSE_SCHEMA,
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "Personal Promo Offers API",
        }

        client = self._client
        if client is None:
            with httpx.Client(timeout=self._timeout) as owned_client:
                response = owned_client.post(OPENROUTER_URL, json=request_body, headers=headers)
        else:
            response = client.post(OPENROUTER_URL, json=request_body, headers=headers)

        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Model returned JSON that is not an object")
        return parsed

    @staticmethod
    def _build_user_prompt(data: OptimizationInput) -> str:
        idle = data.days_since_last_purchase
        idle_text = "покупок не было" if idle is None else f"{idle} дней назад"
        return (
            "Профиль клиента:\n"
            f"- сегмент: {data.segment.value}\n"
            f"- ценовая эластичность: {data.price_sensitivity:.2f}\n"
            f"- пожизненная ценность: {data.lifetime_value:.0f} рублей\n"
            f"- всего заказов: {data.total_orders}\n"
            f"- средний чек: {data.avg_order_value:.0f} рублей\n"
            f"- последняя покупка: {idle_text}\n"
            f"- сумма активной корзины: {data.cart_total:.0f} рублей\n"
            f"- предпочитаемый канал: {data.preferred_channel.value}\n\n"
            "Допустимые типы офферов: "
            + ", ".join(t.value for t in OfferType)
            + ".\nДопустимые каналы: "
            + ", ".join(c.value for c in ChannelType)
            + ".\nДопустимое время отправки: "
            + ", ".join(t.value for t in TimingType)
            + "."
        )

    # --- validation -----------------------------------------------------------

    def _protects_margin(self, data: OptimizationInput) -> bool:
        """Customers for whom a direct discount is economically wasteful."""
        return (
            data.price_sensitivity < LOW_ELASTICITY
            or data.lifetime_value > settings.vip_ltv_threshold
            or data.segment == SegmentType.VIP
        )

    def _sanitize(self, raw_items: object, data: OptimizationInput) -> list[OptimizationRecommendation]:
        """Convert untrusted model output into validated recommendations."""
        if not isinstance(raw_items, list):
            return []

        protect_margin = self._protects_margin(data)
        accepted: list[OptimizationRecommendation] = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                offer_type = OfferType(str(item["offer_type"]))
                channel = ChannelType(str(item["channel"]))
                timing = TimingType(str(item["timing"]))
                value = float(item.get("value") or 0.0)
                conversion = float(item.get("expected_conversion") or 0.0)
                reasoning = str(item.get("reasoning") or "").strip()
            except (KeyError, TypeError, ValueError):
                logger.warning("Discarded a malformed LLM recommendation")
                continue

            if protect_margin and offer_type in _DISCOUNT_TYPES:
                logger.info(
                    "Discarded a %s suggestion: the margin policy protects this customer",
                    offer_type.value,
                )
                continue

            if offer_type == OfferType.DISCOUNT_PERCENT:
                value = min(max(value, 0.0), MAX_DISCOUNT_PERCENT)

            accepted.append(OptimizationRecommendation(
                offer_type=offer_type,
                value=round(max(value, 0.0), 2),
                channel=channel,
                timing=timing,
                expected_conversion=round(min(max(conversion, 0.0), 1.0), 4),
                reasoning=reasoning or "Обоснование не предоставлено моделью",
            ))

        accepted.sort(key=lambda r: r.expected_conversion, reverse=True)
        return accepted

    # --- fallback -------------------------------------------------------------

    def _fallback_result(
        self, data: OptimizationInput
    ) -> tuple[list[OptimizationRecommendation], str, str]:
        recommendations, strategy, _ = self._fallback.get_recommendations(data)
        return recommendations, strategy, ENGINE_FALLBACK
