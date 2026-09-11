"""Offer simulation script. Run: python -m scripts.simulate_offer_cycle

The script is idempotent: it only populates offer records when the table is
empty, so repeated service restarts do not inflate the A/B test numbers.
Pass --reset to discard existing records and simulate a fresh cycle.
"""

import argparse
import random

from app.core.database import db_session, init_db
from app.core.logging_config import configure_logging, get_logger
from app.models.orm_models import Customer, OfferRecord
from app.services.customer_service import CustomerService
from app.services.offer_engine import OfferContext, PersonalOfferEngine

configure_logging()
logger = get_logger(__name__)
random.seed(20260911)

_PERSONALIZED_CONVERSION_PROBABILITY = 0.16
_MASS_PROMOTION_CONVERSION_PROBABILITY = 0.08
_engine = PersonalOfferEngine(top_n=3)


def simulate(reset: bool = False) -> None:
    init_db()
    with db_session() as db:
        existing_count = db.query(OfferRecord).count()

        if existing_count and not reset:
            logger.info("Database already contains %s offer records, skipping simulation", existing_count)
            return

        if existing_count and reset:
            db.query(OfferRecord).delete()
            db.commit()
            logger.info("Removed %s existing offer records before re-simulating", existing_count)

        service = CustomerService(db)
        customers = db.query(Customer).all()

        for customer in customers:
            segment = service.get_segment(customer)
            context = OfferContext(cart_total=customer.avg_order_value or 0)
            offers = _engine.generate_offers(
                segment=segment,
                price_sensitivity=customer.price_sensitivity,
                context=context,
                lifetime_value=customer.lifetime_value,
            )

            is_control_group = random.random() < 0.5
            conversion_probability = (
                _MASS_PROMOTION_CONVERSION_PROBABILITY if is_control_group
                else _PERSONALIZED_CONVERSION_PROBABILITY
            )

            for offer in offers:
                converted = random.random() < conversion_probability
                db.add(OfferRecord(
                    offer_uid=offer.offer_uid,
                    customer_id=customer.id,
                    offer_type=offer.offer_type.value,
                    value=offer.value,
                    segment_at_generation=segment.value,
                    score=offer.score,
                    is_control_group=is_control_group,
                    is_applied=converted,
                    converted=converted,
                ))

        db.commit()
        logger.info("Simulated offers for %s customers", len(customers))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate a personalized offer cycle on seeded customers.")
    parser.add_argument("--reset", action="store_true", help="Delete existing offer records and simulate a fresh cycle")
    return parser.parse_args()


if __name__ == "__main__":
    simulate(reset=_parse_args().reset)
