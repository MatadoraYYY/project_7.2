"""Synthetic data seeding script. Run: python -m scripts.seed_synthetic_data"""

import random
from datetime import datetime, timedelta

from faker import Faker

from app.core.database import db_session, init_db
from app.core.logging_config import configure_logging, get_logger
from app.models.orm_models import Customer, Purchase

configure_logging()
logger = get_logger(__name__)
fake = Faker("ru_RU")

NUM_CUSTOMERS = 150
CATEGORIES = ["water", "snacks", "coffee", "beverages", "accessories"]


def _generate_purchase_history(now: datetime) -> list[Purchase]:
    num_purchases = random.choice([0, 0, 1, 2, 3, 5, 8, 12, 20])
    purchases: list[Purchase] = []
    base_price = round(random.uniform(30, 150), 2)
    for _ in range(num_purchases):
        days_ago = random.randint(0, 180)
        had_discount = random.random() < 0.4
        price = base_price * (0.8 if had_discount else 1.0)
        quantity = random.choice([1, 1, 1, 2, 3])
        purchases.append(Purchase(occurred_at=now - timedelta(days=days_ago), price=round(price, 2), quantity=quantity, had_discount=had_discount, category=random.choice(CATEGORIES)))
    return purchases


def seed() -> None:
    init_db()
    now = datetime.utcnow()

    with db_session() as db:
        existing_count = db.query(Customer).count()
        if existing_count > 0:
            logger.info("Database already contains %s customers, skipping seed", existing_count)
            return

        for _ in range(NUM_CUSTOMERS):
            customer = Customer(external_ref=f"anon-{fake.unique.uuid4()[:12]}", preferred_channel=random.choice(["push", "email", "sms", "telegram"]))
            purchases = _generate_purchase_history(now)
            customer.purchases = purchases

            if purchases:
                total_revenue = sum(p.price * p.quantity for p in purchases)
                customer.total_orders = len(purchases)
                customer.total_revenue = round(total_revenue, 2)
                customer.avg_order_value = round(total_revenue / len(purchases), 2)
                customer.lifetime_value = customer.total_revenue
                customer.first_purchase_at = min(p.occurred_at for p in purchases)
                customer.last_purchase_at = max(p.occurred_at for p in purchases)

                discounted = [p for p in purchases if p.had_discount]
                full_price = [p for p in purchases if not p.had_discount]
                if discounted and full_price and len(purchases) >= 3:
                    avg_disc_qty = sum(p.quantity for p in discounted) / len(discounted)
                    avg_full_qty = sum(p.quantity for p in full_price) / len(full_price)
                    uplift = (avg_disc_qty - avg_full_qty) / avg_full_qty if avg_full_qty else 0
                    customer.price_sensitivity = max(0.3, min(2.0, 0.7 + uplift))
                else:
                    customer.price_sensitivity = 0.7

            db.add(customer)

        db.commit()
        logger.info("Seeded %s synthetic customers", NUM_CUSTOMERS)


if __name__ == "__main__":
    seed()
