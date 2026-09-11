"""Customer management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_api_key
from app.models.schemas import CustomerCreate, CustomerProfileOut, PurchaseCreate
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


def _to_profile(service: CustomerService, customer) -> CustomerProfileOut:
    return CustomerProfileOut(
        id=customer.id,
        external_ref=customer.external_ref,
        total_orders=customer.total_orders,
        total_revenue=round(customer.total_revenue, 2),
        avg_order_value=round(customer.avg_order_value, 2),
        first_purchase_at=customer.first_purchase_at,
        last_purchase_at=customer.last_purchase_at,
        price_sensitivity=round(customer.price_sensitivity, 2),
        lifetime_value=round(customer.lifetime_value, 2),
        preferred_channel=customer.preferred_channel,
        segment=service.get_segment(customer),
    )


@router.post("", response_model=CustomerProfileOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_api_key)])
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> CustomerProfileOut:
    """Create an anonymized customer profile."""
    service = CustomerService(db)
    if service.get_by_external_ref(payload.external_ref):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer with this external_ref already exists.")
    customer = service.create(payload.external_ref, payload.preferred_channel)
    return _to_profile(service, customer)


@router.get("", response_model=list[CustomerProfileOut])
def list_customers(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
                   db: Session = Depends(get_db)) -> list[CustomerProfileOut]:
    """List customer profiles with their computed segment."""
    service = CustomerService(db)
    return [_to_profile(service, c) for c in service.list_customers(limit=limit, offset=offset)]


@router.get("/{customer_id}", response_model=CustomerProfileOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerProfileOut:
    """Retrieve one customer profile."""
    service = CustomerService(db)
    customer = service.get_by_id(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return _to_profile(service, customer)


@router.post("/{customer_id}/purchases", response_model=CustomerProfileOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key)])
def add_purchase(customer_id: int, payload: PurchaseCreate, db: Session = Depends(get_db)) -> CustomerProfileOut:
    """Record a purchase and recalculate the customer's elasticity and segment."""
    service = CustomerService(db)
    customer = service.get_by_id(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    service.add_purchase(customer, payload.price, payload.quantity, payload.had_discount,
                         payload.category, payload.occurred_at)
    db.refresh(customer)
    return _to_profile(service, customer)
