"""Pydantic schemas (API request/response contracts)."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SegmentType(str, Enum):
    NEW_USER = "new_user"
    REPEAT_BUYER = "repeat_buyer"
    VIP = "vip"
    DORMANT = "dormant"
    PRICE_SENSITIVE = "price_sensitive"


class OfferType(str, Enum):
    DISCOUNT_PERCENT = "discount_percent"
    DISCOUNT_FIXED = "discount_fixed"
    FREE_SHIPPING = "free_shipping"
    BONUS_POINTS = "bonus_points"
    GIFT = "gift"
    EARLY_ACCESS = "early_access"
    PERSONAL_MANAGER = "personal_manager"
    CONCIERGE = "concierge"
    BUNDLE = "bundle"


class ChannelType(str, Enum):
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    TELEGRAM = "telegram"


class TimingType(str, Enum):
    IMMEDIATE = "immediate"
    SAME_DAY_EVENING = "same_day_evening"
    NEXT_MORNING = "next_morning"
    WEEKEND = "weekend"


class CustomerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_ref: str = Field(..., min_length=1, max_length=64, description="Anonymized customer identifier")
    preferred_channel: str = Field(default="push", pattern="^(push|email|sms|telegram)$")

    @field_validator("external_ref")
    @classmethod
    def external_ref_must_be_safe(cls, value: str) -> str:
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("external_ref must be alphanumeric (optionally with '-' or '_')")
        return value


class PurchaseCreate(BaseModel):
    price: float = Field(..., gt=0, le=1_000_000)
    quantity: int = Field(default=1, ge=1, le=10_000)
    had_discount: bool = False
    category: str = Field(default="general", max_length=64)
    occurred_at: Optional[datetime] = None


class CustomerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_ref: str
    total_orders: int
    total_revenue: float
    avg_order_value: float
    first_purchase_at: Optional[datetime]
    last_purchase_at: Optional[datetime]
    price_sensitivity: float
    lifetime_value: float
    preferred_channel: str
    segment: SegmentType


class GeneratedOffer(BaseModel):
    offer_uid: str
    offer_type: OfferType
    value: float
    title: str
    score: float = Field(..., ge=0, le=1)
    expected_conversion: float = Field(..., ge=0, le=1)
    reason: str


class OfferGenerationResponse(BaseModel):
    customer_id: int
    external_ref: str
    segment: SegmentType
    price_sensitivity: float
    offers: list[GeneratedOffer]


class ApplyOfferRequest(BaseModel):
    order_reference: Optional[str] = Field(default=None, max_length=64)
    converted: bool = Field(default=True, description="Whether the offer led to a completed purchase")


class ApplyOfferResponse(BaseModel):
    offer_uid: str
    status: str
    applied_at: datetime


class OfferAnalyticsOut(BaseModel):
    customer_id: int
    total_offers_generated: int
    total_offers_applied: int
    conversion_rate: float


class ABTestGroupResult(BaseModel):
    group: str
    customers: int
    offers_generated: int
    offers_converted: int
    conversion_rate: float
    average_order_value: float
    estimated_margin_pct: float


class ABTestResponse(BaseModel):
    personalized: ABTestGroupResult
    mass_promotion: ABTestGroupResult
    conversion_uplift_pct: float
    margin_uplift_pct: float
    note: str


class DashboardSummary(BaseModel):
    total_customers: int
    total_offers_generated: int
    total_offers_applied: int
    overall_conversion_rate: float
    segment_distribution: dict[str, int]


class HealthCheck(BaseModel):
    status: str
    environment: str


# --- Offer optimization agent -------------------------------------------------

class OptimizationRecommendation(BaseModel):
    offer_type: OfferType
    value: float
    channel: ChannelType
    timing: TimingType
    expected_conversion: float = Field(..., ge=0, le=1)
    reasoning: str


class OptimizationResponse(BaseModel):
    customer_id: int
    segment: SegmentType
    price_sensitivity: float
    lifetime_value: float
    recommendations: list[OptimizationRecommendation]
    overall_strategy: str
    engine: str = Field(description="Which optimization engine produced the recommendations")


# --- Campaigns ----------------------------------------------------------------

class CampaignScheduleRequest(BaseModel):
    segment: SegmentType
    offer_type: OfferType
    channel: ChannelType = ChannelType.PUSH
    scheduled_for: Optional[datetime] = None


class CampaignScheduleResponse(BaseModel):
    campaign_id: str
    segment: SegmentType
    offer_type: OfferType
    channel: ChannelType
    scheduled_for: datetime
    status: str
    target_audience_size: int


class CampaignPerformanceResponse(BaseModel):
    campaign_id: str
    period_start: datetime
    period_end: datetime
    offers_generated: int
    offers_converted: int
    conversion_rate: float
    estimated_revenue: float
    segment_breakdown: dict[str, int]
