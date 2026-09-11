"""Offer persistence, application and per-customer analytics."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orm_models import Customer, OfferRecord
from app.models.schemas import GeneratedOffer, OfferAnalyticsOut, SegmentType


class OfferService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def persist_offers(self, customer: Customer, segment: SegmentType, offers: list[GeneratedOffer],
                       is_control_group: bool = False, campaign_id: str | None = None) -> None:
        for offer in offers:
            self._db.add(OfferRecord(
                offer_uid=offer.offer_uid,
                customer_id=customer.id,
                offer_type=offer.offer_type.value,
                value=offer.value,
                segment_at_generation=segment.value,
                score=offer.score,
                is_control_group=is_control_group,
                campaign_id=campaign_id,
            ))
        self._db.commit()

    def get_by_uid(self, offer_uid: str) -> OfferRecord | None:
        return self._db.scalar(select(OfferRecord).where(OfferRecord.offer_uid == offer_uid))

    def apply_offer(self, record: OfferRecord, order_reference: str | None, converted: bool) -> OfferRecord:
        record.is_applied = True
        record.applied_at = datetime.utcnow()
        record.order_reference = order_reference
        record.converted = converted
        self._db.commit()
        self._db.refresh(record)
        return record

    def customer_analytics(self, customer_id: int) -> OfferAnalyticsOut:
        generated = self._db.scalar(
            select(func.count(OfferRecord.id)).where(OfferRecord.customer_id == customer_id)
        ) or 0
        applied = self._db.scalar(
            select(func.count(OfferRecord.id)).where(
                OfferRecord.customer_id == customer_id, OfferRecord.is_applied.is_(True)
            )
        ) or 0
        return OfferAnalyticsOut(
            customer_id=customer_id,
            total_offers_generated=generated,
            total_offers_applied=applied,
            conversion_rate=round(applied / generated, 4) if generated else 0.0,
        )
