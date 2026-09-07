"""Aggregated analytics endpoints: A/B testing and dashboard summary."""

from fastapi import APIRouter, Depends

from app.api.deps import get_ab_test_service, get_customer_service
from app.core.security import enforce_rate_limit
from app.models.schemas import ABTestGroupResult, ABTestResponse, DashboardSummary
from app.services.ab_test_service import ABTestService
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/ab-test", response_model=ABTestResponse, dependencies=[Depends(enforce_rate_limit)])
def get_ab_test_results(service: ABTestService = Depends(get_ab_test_service)) -> ABTestResponse:
    result = service.compute_comparison()
    return ABTestResponse(
        personalized=ABTestGroupResult(**result["personalized"]),
        mass_promotion=ABTestGroupResult(**result["mass_promotion"]),
        conversion_uplift_pct=result["conversion_uplift_pct"],
        margin_uplift_pct=result["margin_uplift_pct"],
        note=result["note"],
    )


@router.get("/dashboard", response_model=DashboardSummary, dependencies=[Depends(enforce_rate_limit)])
def get_dashboard_summary(service: CustomerService = Depends(get_customer_service)) -> DashboardSummary:
    summary = service.get_dashboard_summary()
    return DashboardSummary(**summary)
