"""Additional endpoint exposing the LLM-backed optimization agent.

Kept in a separate router so that ``app/api/offers.py`` stays untouched.
The route lives under the same ``/api/v1/offers`` prefix and adds the suffix
``/optimization/recommendations/llm``, so the deterministic endpoint keeps
its original path and behaviour.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas import ChannelType, OptimizationResponse
from app.services.customer_service import CustomerService
from app.services.llm_agent import OpenRouterOptimizationAgent
from app.services.optimization_agent import OptimizationInput

router = APIRouter(prefix="/api/v1/offers", tags=["Personal Offers"])

_llm_agent = OpenRouterOptimizationAgent()


@router.get("/optimization/recommendations/llm", response_model=OptimizationResponse)
def get_llm_offer_recommendations(
    customer_id: int = Query(..., ge=1, description="Customer to optimize offers for"),
    cart_total: float = Query(default=0.0, ge=0, le=1_000_000),
    db: Session = Depends(get_db),
) -> OptimizationResponse:
    """Recommend offers using the OpenRouter language model.

    The ``engine`` field in the response reports which engine actually
    produced the result: ``openrouter_llm_v1`` when the model answered and
    passed validation, or ``rule_based_v1_fallback`` when the deterministic
    agent had to take over.
    """
    customers = CustomerService(db)
    customer = customers.get_by_id(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")

    segment = customers.get_segment(customer)
    agent_input = OptimizationInput(
        customer_id=customer.id,
        segment=segment,
        price_sensitivity=customer.price_sensitivity,
        lifetime_value=customer.lifetime_value,
        total_orders=customer.total_orders,
        avg_order_value=customer.avg_order_value,
        days_since_last_purchase=customers.days_since_last_purchase(customer),
        cart_total=cart_total,
        preferred_channel=ChannelType(customer.preferred_channel),
    )
    recommendations, strategy, engine = _llm_agent.get_recommendations(agent_input)

    return OptimizationResponse(
        customer_id=customer.id,
        segment=segment,
        price_sensitivity=round(customer.price_sensitivity, 2),
        lifetime_value=round(customer.lifetime_value, 2),
        recommendations=recommendations,
        overall_strategy=strategy,
        engine=engine,
    )
