"""Personal offer generation and management endpoints."""

import random

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_customer_service
from app.core.security import enforce_rate_limit, verify_api_key
from app.models.orm_models import OfferRecord
from app.models.schemas import ApplyOfferRequest, ApplyOfferResponse, OfferAnalyticsOut, OfferGenerationResponse
from app.services.customer_service import CustomerNotFoundError, CustomerService
from app.services.offer_engine import OfferContext, PersonalOfferEngine

router = APIRouter(prefix="/api/v1/offers", tags=["Personal Offers"])
_engine = PersonalOfferEngine(top_n=3)
_CONTROL_GROUP_ASSIGNMENT_PROBABILITY = 0.5


@router.get("/generate/{customer_id}", response_model=OfferGenerationResponse, dependencies=[Depends(enforce_rate_limit)])
def generate_offers(customer_id: int, cart_total: float = Query(default=0.0, ge=0), is_abandoned_cart: bool = Query(default=False), service: CustomerService = Depends(get_customer_service)) -> OfferGenerationResponse:
    try:
        customer = service.get_customer(customer_id)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    segment = service.get_segment(customer)
    context = OfferContext(cart_total=cart_total, is_abandoned_cart=is_abandoned_cart)
    generated_offers = _engine.generate_offers(segment, customer.price_sensitivity, context)

    is_control_group = random.random() < _CONTROL_GROUP_ASSIGNMENT_PROBABILITY
    records = [
        OfferRecord(
            offer_uid=offer.offer_uid,
            offer_type=offer.offer_type.value,
            value=offer.value,
            segment_at_generation=segment.value,
            score=offer.score,
            is_control_group=is_control_group,
        )
        for offer in generated_offers
    ]
    service.save_offer_records(customer.id, records)

    return OfferGenerationResponse(
        customer_id=customer.id,
        external_ref=customer.external_ref,
        segment=segment,
        price_sensitivity=customer.price_sensitivity,
        offers=generated_offers,
    )


@router.post("/apply/{offer_uid}", response_model=ApplyOfferResponse, dependencies=[Depends(enforce_rate_limit), Depends(verify_api_key)])
def apply_offer(offer_uid: str, payload: ApplyOfferRequest, service: CustomerService = Depends(get_customer_service)) -> ApplyOfferResponse:
    try:
        record = service.mark_offer_applied(offer_uid, payload.order_reference, payload.converted)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApplyOfferResponse(offer_uid=record.offer_uid, status="applied", applied_at=record.applied_at)


@router.get("/analytics/{customer_id}", response_model=OfferAnalyticsOut, dependencies=[Depends(enforce_rate_limit)])
def get_offer_analytics(customer_id: int, service: CustomerService = Depends(get_customer_service)) -> OfferAnalyticsOut:
    try:
        service.get_customer(customer_id)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    analytics = service.get_offer_analytics(customer_id)
    return OfferAnalyticsOut(**analytics)
