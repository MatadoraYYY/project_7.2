"""Synthetic data generator. Run: python -m scripts.seed_synthetic_data

Cohorts are calibrated so that every segment defined in the classifier is
actually represented in the dataset - including ``vip``, which requires at
least 10 orders and a lifetime value above 50,000 rubles.
"""

import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from faker import Faker

from app.core.database import db_session, init_db
from app.core.logging_config import configure_logging, get_logger
from app.models.orm_models import Customer, Purchase
from app.services.customer_service import CustomerService

configure_logging()
logger = get_logger(__name__)
fake = Faker("ru_RU")
Faker.seed(20260911)
random.seed(20260911)

_CATEGORIES = ("electronics", "apparel", "home", "beauty", "sports", "books")
_CHANNELS = ("push", "email", "sms", "telegram")


@dataclass(frozen=True)
class Cohort:
    """A group of customers sharing a purchasing pattern."""

    name: str
    size: int
    order_count: tuple[int, int]
    price_range: tuple[float, float]
    quantity_range: tuple[int, int]
    discount_probability: float
    days_since_last: tuple[int, int]
    discount_quantity_bonus: int = 0


# Order volumes and price bands are chosen so the resulting lifetime values
# straddle the VIP threshold instead of clustering far below it.
_COHORTS: tuple[Cohort, ...] = (
    Cohort("new_user", size=25, order_count=(0, 0), price_range=(0, 0),
           quantity_range=(0, 0), discount_probability=0.0, days_since_last=(0, 0)),

    Cohort("vip", size=20, order_count=(12, 22), price_range=(4500, 9000),
           quantity_range=(1, 3), discount_probability=0.15, days_since_last=(1, 12)),

    Cohort("loyal_insensitive", size=30, order_count=(4, 9), price_range=(1200, 3000),
           quantity_range=(1, 2), discount_probability=0.3, days_since_last=(2, 20)),

    Cohort("price_sensitive", size=35, order_count=(5, 14), price_range=(700, 2200),
           quantity_range=(1, 2), discount_probability=0.55, days_since_last=(1, 22),
           discount_quantity_bonus=3),

    Cohort("dormant", size=40, order_count=(2, 10), price_range=(900, 3500),
           quantity_range=(1, 3), discount_probability=0.4, days_since_last=(35, 210)),
)


def _build_purchases(cohort: Cohort, now: datetime) -> list[dict]:
    order_count = random.randint(*cohort.order_count)
    if order_count == 0:
        return []

    idle_days = random.randint(*cohort.days_since_last)
    last_purchase = now - timedelta(days=idle_days)
    purchases: list[dict] = []

    for index in range(order_count):
        had_discount = random.random() < cohort.discount_probability
        quantity = random.randint(*cohort.quantity_range)
        if had_discount:
            quantity += random.randint(0, cohort.discount_quantity_bonus)

        purchases.append({
            "occurred_at": last_purchase - timedelta(days=index * random.randint(5, 30)),
            "price": round(random.uniform(*cohort.price_range), 2),
            "quantity": max(1, quantity),
            "had_discount": had_discount,
            "category": random.choice(_CATEGORIES),
        })

    return purchases


def seed(reset: bool = False) -> None:
    init_db()
    now = datetime.now()

    with db_session() as db:
        existing = db.query(Customer).count()
        if existing and not reset:
            logger.info("Database already contains %s customers, skipping seed", existing)
            return
        if existing and reset:
            db.query(Purchase).delete()
            db.query(Customer).delete()
            db.commit()
            logger.info("Removed %s existing customers before re-seeding", existing)

        service = CustomerService(db)
        created = 0
        cohort_totals: dict[str, int] = {}

        for cohort in _COHORTS:
            for _ in range(cohort.size):
                customer = Customer(
                    external_ref=f"anon-{fake.uuid4()[:8]}-{fake.uuid4()[:4]}",
                    preferred_channel=random.choice(_CHANNELS),
                )
                db.add(customer)
                db.flush()

                for purchase in _build_purchases(cohort, now):
                    db.add(Purchase(customer_id=customer.id, **purchase))

                db.flush()
                service._recalculate_profile(customer)
                created += 1

            cohort_totals[cohort.name] = cohort.size

        db.commit()
        logger.info("Seeded %s customers across cohorts: %s", created, cohort_totals)

        distribution: dict[str, int] = {}
        for customer in db.query(Customer).all():
            segment = service.get_segment(customer).value
            distribution[segment] = distribution.get(segment, 0) + 1
        logger.info("Resulting segment distribution: %s", distribution)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed synthetic customers and purchase history.")
    parser.add_argument("--reset", action="store_true", help="Delete existing customers and re-seed from scratch")
    return parser.parse_args()


if __name__ == "__main__":
    seed(reset=_parse_args().reset)
