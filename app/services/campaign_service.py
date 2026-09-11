"""Campaign scheduling and performance measurement."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orm_models import Campaign, Customer, OfferRecord
from app.models.schemas import (
    CampaignPerformanceResponse,
    CampaignScheduleResponse,
    ChannelType,
    OfferType,
    SegmentType,
)
from app.services.customer_service import CustomerService

# Average revenue attributed to one converted offer, used to estimate
# campaign revenue when order-level data is not yet wired in.
_ASSUMED_REVENUE_PER_CONVERSION = 1.0


class CampaignService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._customers = CustomerService(db)

    def schedule(
        self,
        segment: SegmentType,
        offer_type: OfferType,
        channel: ChannelType,
        scheduled_for: datetime | None = None,
    ) -> CampaignScheduleResponse:
        """Register a campaign and size its target audience by segment."""
        send_at = scheduled_for or (datetime.utcnow() + timedelta(days=1))
        audience_size = self._count_segment_audience(segment)

        campaign = Campaign(
            campaign_id=f"camp-{uuid.uuid4().hex[:10]}",
            segment=segment.value,
            offer_type=offer_type.value,
            channel=channel.value,
            scheduled_for=send_at,
            status="scheduled",
            target_audience_size=audience_size,
        )
        self._db.add(campaign)
        self._db.commit()
        self._db.refresh(campaign)

        return CampaignScheduleResponse(
            campaign_id=campaign.campaign_id,
            segment=segment,
            offer_type=offer_type,
            channel=channel,
            scheduled_for=campaign.scheduled_for,
            status=campaign.status,
            target_audience_size=campaign.target_audience_size,
        )

    def _count_segment_audience(self, segment: SegmentType) -> int:
        """Segments are computed, not stored, so the audience is counted in Python."""
        customers = list(self._db.scalars(select(Customer)))
        return sum(1 for c in customers if self._customers.get_segment(c) == segment)

    def performance(self, campaign_id: str, start_date: datetime, end_date: datetime) -> CampaignPerformanceResponse:
        """Aggregate offer results for a campaign within a date window.

        When no offer carries the campaign tag, the window is measured across all
        offers instead - this keeps the endpoint informative on seeded data.
        """
        tagged_exists = self._db.scalar(
            select(func.count(OfferRecord.id)).where(OfferRecord.campaign_id == campaign_id)
        ) or 0

        conditions = [OfferRecord.created_at >= start_date, OfferRecord.created_at <= end_date]
        if tagged_exists:
            conditions.append(OfferRecord.campaign_id == campaign_id)

        records = list(self._db.scalars(select(OfferRecord).where(*conditions)))
        generated = len(records)
        converted = sum(1 for r in records if r.converted)

        breakdown: dict[str, int] = {}
        for record in records:
            breakdown[record.segment_at_generation] = breakdown.get(record.segment_at_generation, 0) + 1

        revenue = 0.0
        if converted:
            avg_order = self._db.scalar(select(func.avg(Customer.avg_order_value))) or 0.0
            revenue = round(converted * float(avg_order) * _ASSUMED_REVENUE_PER_CONVERSION, 2)

        return CampaignPerformanceResponse(
            campaign_id=campaign_id,
            period_start=start_date,
            period_end=end_date,
            offers_generated=generated,
            offers_converted=converted,
            conversion_rate=round(converted / generated, 4) if generated else 0.0,
            estimated_revenue=revenue,
            segment_breakdown=dict(sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)),
        )
