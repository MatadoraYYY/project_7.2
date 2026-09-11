"""Personal offer endpoints, including optimization and campaign management."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_api_key
from app.models.schemas import (
    ApplyOfferRequest,
    ApplyOfferResponse,
    CampaignPerformanceResponse,
    CampaignScheduleRequest,
    CampaignScheduleResponse,
    ChannelType,
    OfferAnalyticsOut,
    OfferGenerationResponse,
    OptimizationResponse,
)
from app.services.campaign_service import CampaignService
from app.services.customer_service import CustomerService
from app.services.offer_engine import OfferContext, PersonalOfferEngine
from app.services.offer_service import OfferService
from app.services.optimization_agent import OfferOptimizationAgent, OptimizationInput

router = APIRouter(prefix="/api/v1/offers", tags=["Personal Offers"])

_engine = PersonalOfferEngine(top_n=3)
_agent = OfferOptimizationAgent()


@router.get("/generate/{customer_id}", response_model=OfferGenerationResponse)
def generate_personal_offers(
    customer_id: int,
    cart_total: float = Query(default=0.0, ge=0, le=1_000_000),
    is_abandoned_cart: bool = Query(default=False),
    favorite_category_matches: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> OfferGenerationResponse:
    """Generate the top-3 personalized offers for a customer."""
    customers = CustomerService(db)
    customer = customers.get_by_id(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")

    segment = customers.get_segment(customer)
    context = OfferContext(
        cart_total=cart_total,
        is_abandoned_cart=is_abandoned_cart,
        favorite_category_matches=favorite_category_matches,
    )
    offers = _engine.generate_offers(
        segment=segment,
        price_sensitivity=customer.price_sensitivity,
        context=context,
        lifetime_value=customer.lifetime_value,
    )
    OfferService(db).persist_offers(customer, segment, offers)

    return OfferGenerationResponse(
        customer_id=customer.id,
        external_ref=customer.external_ref,
        segment=segment,
        price_sensitivity=round(customer.price_sensitivity, 2),
        offers=offers,
    )


@router.post("/apply/{offer_uid}", response_model=ApplyOfferResponse, dependencies=[Depends(verify_api_key)])
def apply_offer(offer_uid: str, payload: ApplyOfferRequest, db: Session = Depends(get_db)) -> ApplyOfferResponse:
    """Mark an offer as applied to an order."""
    service = OfferService(db)
    record = service.get_by_uid(offer_uid)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    if record.is_applied:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offer has already been applied.")

    updated = service.apply_offer(record, payload.order_reference, payload.converted)
    return ApplyOfferResponse(offer_uid=updated.offer_uid, status="applied", applied_at=updated.applied_at)


@router.get("/analytics/{customer_id}", response_model=OfferAnalyticsOut)
def get_offer_analytics(customer_id: int, db: Session = Depends(get_db)) -> OfferAnalyticsOut:
    """Offer statistics for a single customer."""
    customers = CustomerService(db)
    if customers.get_by_id(customer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return OfferService(db).customer_analytics(customer_id)


@router.get("/optimization/recommendations", response_model=OptimizationResponse)
def get_offer_recommendations(
    customer_id: int = Query(..., ge=1, description="Customer to optimize offers for"),
    cart_total: float = Query(default=0.0, ge=0, le=1_000_000),
    db: Session = Depends(get_db),
) -> OptimizationResponse:
    """Recommend which offer to send, at what size, through which channel and when."""
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
    recommendations, strategy, engine = _agent.get_recommendations(agent_input)

    return OptimizationResponse(
        customer_id=customer.id,
        segment=segment,
        price_sensitivity=round(customer.price_sensitivity, 2),
        lifetime_value=round(customer.lifetime_value, 2),
        recommendations=recommendations,
        overall_strategy=strategy,
        engine=engine,
    )


@router.post("/campaign/schedule", response_model=CampaignScheduleResponse,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key)])
def schedule_personal_campaign(payload: CampaignScheduleRequest, db: Session = Depends(get_db)) -> CampaignScheduleResponse:
    """Schedule a personalized offer campaign for a customer segment."""
    return CampaignService(db).schedule(
        segment=payload.segment,
        offer_type=payload.offer_type,
        channel=payload.channel,
        scheduled_for=payload.scheduled_for,
    )


@router.get("/campaign/performance", response_model=CampaignPerformanceResponse)
def get_campaign_performance(
    campaign_id: str = Query(..., min_length=1, max_length=64),
    start_date: datetime | None = Query(default=None, description="ISO date, defaults to 30 days ago"),
    end_date: datetime | None = Query(default=None, description="ISO date, defaults to now"),
    db: Session = Depends(get_db),
) -> CampaignPerformanceResponse:
    """Measure the performance of a personalized offer campaign."""
    period_end = end_date or datetime.utcnow()
    period_start = start_date or (period_end - timedelta(days=30))
    if period_start > period_end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must not be after end_date.")
    return CampaignService(db).performance(campaign_id, period_start, period_end)
