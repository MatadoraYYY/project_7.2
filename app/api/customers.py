"""Customer profile management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_customer_service
from app.core.security import enforce_rate_limit, verify_api_key
from app.models.schemas import CustomerCreate, CustomerProfileOut, PurchaseCreate
from app.services.customer_service import CustomerService, CustomerNotFoundError, DuplicateCustomerError

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


def _to_profile_out(customer, service: CustomerService) -> CustomerProfileOut:
    segment = service.get_segment(customer)
    return CustomerProfileOut(
        id=customer.id,
        external_ref=customer.external_ref,
        total_orders=customer.total_orders,
        total_revenue=customer.total_revenue,
        avg_order_value=customer.avg_order_value,
        first_purchase_at=customer.first_purchase_at,
        last_purchase_at=customer.last_purchase_at,
        price_sensitivity=customer.price_sensitivity,
        lifetime_value=customer.lifetime_value,
        preferred_channel=customer.preferred_channel,
        segment=segment,
    )


@router.post("", response_model=CustomerProfileOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(enforce_rate_limit), Depends(verify_api_key)])
def create_customer(payload: CustomerCreate, service: CustomerService = Depends(get_customer_service)) -> CustomerProfileOut:
    try:
        customer = service.create_customer(payload)
    except DuplicateCustomerError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_profile_out(customer, service)


@router.get("", response_model=list[CustomerProfileOut], dependencies=[Depends(enforce_rate_limit)])
def list_customers(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0), service: CustomerService = Depends(get_customer_service)) -> list[CustomerProfileOut]:
    customers = service.list_customers(limit=limit, offset=offset)
    return [_to_profile_out(c, service) for c in customers]


@router.get("/{customer_id}", response_model=CustomerProfileOut, dependencies=[Depends(enforce_rate_limit)])
def get_customer(customer_id: int, service: CustomerService = Depends(get_customer_service)) -> CustomerProfileOut:
    try:
        customer = service.get_customer(customer_id)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_profile_out(customer, service)


@router.post("/{customer_id}/purchases", response_model=CustomerProfileOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(enforce_rate_limit), Depends(verify_api_key)])
def add_purchase(customer_id: int, payload: PurchaseCreate, service: CustomerService = Depends(get_customer_service)) -> CustomerProfileOut:
    try:
        customer = service.record_purchase(customer_id, payload)
    except CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_profile_out(customer, service)
