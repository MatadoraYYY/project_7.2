"""Aggregated analytics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.orm_models import Customer, OfferRecord
from app.models.schemas import ABTestResponse, DashboardSummary
from app.services.ab_test_service import ABTestService
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/ab-test", response_model=ABTestResponse)
def get_ab_test_results(db: Session = Depends(get_db)) -> ABTestResponse:
    """Compare personalized offers against mass promotion."""
    return ABTestService(db).run()


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    """Headline metrics and segment distribution for the dashboard."""
    service = CustomerService(db)
    customers = list(db.scalars(select(Customer)))

    distribution: dict[str, int] = {}
    for customer in customers:
        segment = service.get_segment(customer).value
        distribution[segment] = distribution.get(segment, 0) + 1

    generated = db.scalar(select(func.count(OfferRecord.id))) or 0
    applied = db.scalar(select(func.count(OfferRecord.id)).where(OfferRecord.is_applied.is_(True))) or 0

    return DashboardSummary(
        total_customers=len(customers),
        total_offers_generated=generated,
        total_offers_applied=applied,
        overall_conversion_rate=round(applied / generated, 4) if generated else 0.0,
        segment_distribution=dict(sorted(distribution.items(), key=lambda kv: kv[1], reverse=True)),
    )
