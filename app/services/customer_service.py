"""Customer profile operations and derived metrics."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm_models import Customer, Purchase
from app.models.schemas import SegmentType
from app.services.elasticity import PriceSensitivityCalculator, PurchaseSignal
from app.services.segmentation import CustomerSignals, SegmentClassifier


class CustomerService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._elasticity = PriceSensitivityCalculator()
        self._classifier = SegmentClassifier()

    def get_by_id(self, customer_id: int) -> Customer | None:
        return self._db.get(Customer, customer_id)

    def get_by_external_ref(self, external_ref: str) -> Customer | None:
        return self._db.scalar(select(Customer).where(Customer.external_ref == external_ref))

    def list_customers(self, limit: int = 50, offset: int = 0) -> list[Customer]:
        stmt = select(Customer).order_by(Customer.id).limit(limit).offset(offset)
        return list(self._db.scalars(stmt))

    def create(self, external_ref: str, preferred_channel: str = "push") -> Customer:
        customer = Customer(external_ref=external_ref, preferred_channel=preferred_channel)
        self._db.add(customer)
        self._db.commit()
        self._db.refresh(customer)
        return customer

    def add_purchase(self, customer: Customer, price: float, quantity: int, had_discount: bool,
                     category: str, occurred_at: datetime | None = None) -> Purchase:
        purchase = Purchase(
            customer_id=customer.id,
            occurred_at=occurred_at or datetime.utcnow(),
            price=price,
            quantity=quantity,
            had_discount=had_discount,
            category=category,
        )
        self._db.add(purchase)
        self._db.flush()
        self._recalculate_profile(customer)
        self._db.commit()
        self._db.refresh(purchase)
        return purchase

    def _recalculate_profile(self, customer: Customer) -> None:
        purchases = list(self._db.scalars(select(Purchase).where(Purchase.customer_id == customer.id)))
        if not purchases:
            return

        revenue = sum(p.price * p.quantity for p in purchases)
        customer.total_orders = len(purchases)
        customer.total_revenue = revenue
        customer.avg_order_value = revenue / len(purchases)
        customer.lifetime_value = revenue
        customer.first_purchase_at = min(p.occurred_at for p in purchases)
        customer.last_purchase_at = max(p.occurred_at for p in purchases)
        customer.price_sensitivity = self._elasticity.calculate(
            [PurchaseSignal(price=p.price, quantity=p.quantity, had_discount=p.had_discount) for p in purchases]
        )
        customer.updated_at = datetime.utcnow()

    def get_segment(self, customer: Customer) -> SegmentType:
        return self._classifier.classify(CustomerSignals(
            total_orders=customer.total_orders,
            lifetime_value=customer.lifetime_value,
            last_purchase_at=customer.last_purchase_at,
            price_sensitivity=customer.price_sensitivity,
        ))

    def days_since_last_purchase(self, customer: Customer) -> int | None:
        if customer.last_purchase_at is None:
            return None
        return max((datetime.utcnow() - customer.last_purchase_at).days, 0)
