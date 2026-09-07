"""Customer service layer: all DB access for customers, purchases, offers."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm_models import Customer, OfferRecord, Purchase
from app.models.schemas import CustomerCreate, PurchaseCreate, SegmentType
from app.services.elasticity import PriceSensitivityCalculator, PurchaseSignal
from app.services.segmentation import CustomerSignals, SegmentClassifier


class CustomerNotFoundError(Exception):
    pass


class DuplicateCustomerError(Exception):
    pass


class CustomerService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._elasticity_calculator = PriceSensitivityCalculator()
        self._segment_classifier = SegmentClassifier()

    def create_customer(self, payload: CustomerCreate) -> Customer:
        existing = self._db.scalar(select(Customer).where(Customer.external_ref == payload.external_ref))
        if existing is not None:
            raise DuplicateCustomerError(f"Customer '{payload.external_ref}' already exists")

        customer = Customer(external_ref=payload.external_ref, preferred_channel=payload.preferred_channel)
        self._db.add(customer)
        self._db.commit()
        self._db.refresh(customer)
        return customer

    def get_customer(self, customer_id: int) -> Customer:
        customer = self._db.get(Customer, customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"Customer with id={customer_id} not found")
        return customer

    def list_customers(self, limit: int = 100, offset: int = 0) -> list[Customer]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        stmt = select(Customer).order_by(Customer.id).limit(limit).offset(offset)
        return list(self._db.scalars(stmt))

    def record_purchase(self, customer_id: int, payload: PurchaseCreate) -> Customer:
        customer = self.get_customer(customer_id)
        occurred_at = payload.occurred_at or datetime.utcnow()
        purchase = Purchase(
            customer_id=customer.id,
            occurred_at=occurred_at,
            price=payload.price,
            quantity=payload.quantity,
            had_discount=payload.had_discount,
            category=payload.category,
        )
        self._db.add(purchase)

        order_value = payload.price * payload.quantity
        customer.total_orders += 1
        customer.total_revenue += order_value
        customer.avg_order_value = customer.total_revenue / customer.total_orders
        customer.lifetime_value = customer.total_revenue

        if customer.first_purchase_at is None or occurred_at < customer.first_purchase_at:
            customer.first_purchase_at = occurred_at
        if customer.last_purchase_at is None or occurred_at > customer.last_purchase_at:
            customer.last_purchase_at = occurred_at

        self._db.commit()
        self._recalculate_price_sensitivity(customer)
        self._db.commit()
        self._db.refresh(customer)
        return customer

    def _recalculate_price_sensitivity(self, customer: Customer) -> None:
        signals = [PurchaseSignal(price=p.price, quantity=p.quantity, had_discount=p.had_discount) for p in customer.purchases]
        customer.price_sensitivity = self._elasticity_calculator.calculate(signals)

    def get_segment(self, customer: Customer) -> SegmentType:
        signals = CustomerSignals(
            total_orders=customer.total_orders,
            lifetime_value=customer.lifetime_value,
            last_purchase_at=customer.last_purchase_at,
            price_sensitivity=customer.price_sensitivity,
        )
        return self._segment_classifier.classify(signals)

    def save_offer_records(self, customer_id: int, records: list[OfferRecord]) -> None:
        for record in records:
            record.customer_id = customer_id
            self._db.add(record)
        self._db.commit()

    def get_offer_by_uid(self, offer_uid: str) -> OfferRecord:
        record = self._db.scalar(select(OfferRecord).where(OfferRecord.offer_uid == offer_uid))
        if record is None:
            raise CustomerNotFoundError(f"Offer '{offer_uid}' not found")
        return record

    def mark_offer_applied(self, offer_uid: str, order_reference: str | None, converted: bool) -> OfferRecord:
        record = self.get_offer_by_uid(offer_uid)
        record.is_applied = True
        record.applied_at = datetime.utcnow()
        record.order_reference = order_reference
        record.converted = converted
        self._db.commit()
        self._db.refresh(record)
        return record

    def get_offer_analytics(self, customer_id: int) -> dict:
        stmt = select(OfferRecord).where(OfferRecord.customer_id == customer_id)
        records = list(self._db.scalars(stmt))
        total_generated = len(records)
        total_applied = sum(1 for r in records if r.is_applied)
        conversion_rate = round(total_applied / total_generated, 4) if total_generated else 0.0
        return {
            "customer_id": customer_id,
            "total_offers_generated": total_generated,
            "total_offers_applied": total_applied,
            "conversion_rate": conversion_rate,
        }

    def get_all_offer_records(self) -> list[OfferRecord]:
        return list(self._db.scalars(select(OfferRecord)))

    def get_dashboard_summary(self) -> dict:
        customers = self.list_customers(limit=500)
        all_offers = self.get_all_offer_records()

        segment_distribution: dict[str, int] = {}
        for customer in customers:
            segment = self.get_segment(customer).value
            segment_distribution[segment] = segment_distribution.get(segment, 0) + 1

        total_generated = len(all_offers)
        total_applied = sum(1 for o in all_offers if o.is_applied)
        overall_conversion = round(total_applied / total_generated, 4) if total_generated else 0.0

        return {
            "total_customers": len(customers),
            "total_offers_generated": total_generated,
            "total_offers_applied": total_applied,
            "overall_conversion_rate": overall_conversion,
            "segment_distribution": segment_distribution,
        }
