"""Tests for the OpenRouter-backed optimization agent.

No network access is required: a stub transport returns canned responses,
so the tests are fast and deterministic.
"""

import json

import httpx
import pytest

from app.models.schemas import ChannelType, OfferType, SegmentType, TimingType
from app.services.llm_agent import (
    ENGINE_FALLBACK,
    ENGINE_LLM,
    MAX_DISCOUNT_PERCENT,
    OpenRouterOptimizationAgent,
)
from app.services.optimization_agent import OptimizationInput


def _payload(**overrides) -> OptimizationInput:
    defaults = dict(
        customer_id=1, segment=SegmentType.REPEAT_BUYER, price_sensitivity=1.4,
        lifetime_value=10_000.0, total_orders=6, avg_order_value=2500.0,
        days_since_last_purchase=4, cart_total=0.0, preferred_channel=ChannelType.PUSH,
    )
    defaults.update(overrides)
    return OptimizationInput(**defaults)


def _stub_client(model_reply: dict | str, status_code: int = 200) -> httpx.Client:
    """Build an httpx client whose transport returns a fixed chat completion."""
    content = model_reply if isinstance(model_reply, str) else json.dumps(model_reply, ensure_ascii=False)
    body = {"choices": [{"message": {"content": content}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _agent(model_reply, status_code: int = 200) -> OpenRouterOptimizationAgent:
    return OpenRouterOptimizationAgent(api_key="test-key", client=_stub_client(model_reply, status_code))


VALID_REPLY = {
    "overall_strategy": "Работа с ценой для эластичного клиента",
    "recommendations": [
        {
            "offer_type": "discount_percent", "value": 18, "channel": "email",
            "timing": "next_morning", "expected_conversion": 0.31,
            "reasoning": "Клиент реагирует на скидки",
        }
    ],
}


def test_missing_api_key_falls_back_to_deterministic_engine():
    agent = OpenRouterOptimizationAgent(api_key="")
    assert agent.is_configured is False
    _, _, engine = agent.get_recommendations(_payload())
    assert engine == ENGINE_FALLBACK


def test_valid_model_reply_is_used():
    recommendations, strategy, engine = _agent(VALID_REPLY).get_recommendations(_payload())
    assert engine == ENGINE_LLM
    assert strategy == VALID_REPLY["overall_strategy"]
    assert recommendations[0].offer_type == OfferType.DISCOUNT_PERCENT
    assert recommendations[0].channel == ChannelType.EMAIL
    assert recommendations[0].timing == TimingType.NEXT_MORNING


def test_excessive_discount_is_clamped_to_the_ceiling():
    reply = {
        "overall_strategy": "Агрессивная скидка",
        "recommendations": [dict(VALID_REPLY["recommendations"][0], value=90)],
    }
    recommendations, _, engine = _agent(reply).get_recommendations(_payload())
    assert engine == ENGINE_LLM
    assert recommendations[0].value == MAX_DISCOUNT_PERCENT


def test_discount_for_protected_customer_is_rejected():
    """A VIP suggestion containing only a discount must trigger the fallback."""
    vip = _payload(segment=SegmentType.VIP, price_sensitivity=0.35, lifetime_value=120_000.0)
    recommendations, _, engine = _agent(VALID_REPLY).get_recommendations(vip)
    assert engine == ENGINE_FALLBACK
    discounts = {OfferType.DISCOUNT_PERCENT, OfferType.DISCOUNT_FIXED}
    assert not any(r.offer_type in discounts for r in recommendations)


def test_non_discount_offer_survives_for_protected_customer():
    reply = {
        "overall_strategy": "Удержание через сервис",
        "recommendations": [{
            "offer_type": "concierge", "value": 0, "channel": "email",
            "timing": "same_day_evening", "expected_conversion": 0.2,
            "reasoning": "Высокий LTV",
        }],
    }
    vip = _payload(segment=SegmentType.VIP, price_sensitivity=0.35, lifetime_value=120_000.0)
    recommendations, _, engine = _agent(reply).get_recommendations(vip)
    assert engine == ENGINE_LLM
    assert recommendations[0].offer_type == OfferType.CONCIERGE


def test_unknown_offer_type_is_discarded():
    reply = {
        "overall_strategy": "Некорректный тип",
        "recommendations": [dict(VALID_REPLY["recommendations"][0], offer_type="free_lunch")],
    }
    _, _, engine = _agent(reply).get_recommendations(_payload())
    assert engine == ENGINE_FALLBACK


def test_conversion_probability_is_clamped_to_unit_interval():
    reply = {
        "overall_strategy": "Завышенная конверсия",
        "recommendations": [dict(VALID_REPLY["recommendations"][0], expected_conversion=7.5)],
    }
    recommendations, _, _ = _agent(reply).get_recommendations(_payload())
    assert recommendations[0].expected_conversion == 1.0


def test_malformed_json_falls_back():
    _, _, engine = _agent("this is not json").get_recommendations(_payload())
    assert engine == ENGINE_FALLBACK


def test_http_error_falls_back():
    _, _, engine = _agent(VALID_REPLY, status_code=500).get_recommendations(_payload())
    assert engine == ENGINE_FALLBACK


def test_empty_recommendation_list_falls_back():
    reply = {"overall_strategy": "Пусто", "recommendations": []}
    _, _, engine = _agent(reply).get_recommendations(_payload())
    assert engine == ENGINE_FALLBACK


def test_never_returns_more_than_three_recommendations():
    item = VALID_REPLY["recommendations"][0]
    reply = {"overall_strategy": "Много офферов", "recommendations": [item] * 6}
    recommendations, _, _ = _agent(reply).get_recommendations(_payload())
    assert len(recommendations) == 3


def test_missing_strategy_is_taken_from_the_deterministic_agent():
    reply = {"overall_strategy": "   ", "recommendations": VALID_REPLY["recommendations"]}
    _, strategy, engine = _agent(reply).get_recommendations(_payload())
    assert engine == ENGINE_LLM
    assert strategy.strip()
