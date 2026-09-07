"""Offer simulation script. Run: python -m scripts.simulate_offer_cycle"""

import random

from app.core.database import db_session, init_db
from app.core.logging_config import configure_logging, get_logger
from app.models.orm_models import Customer, OfferRecord
from app.services.customer_service import CustomerService
from app.services.offer_engine import OfferContext, PersonalOfferEngine

configure_logging()
logger = get_logger(__name__)

_PERSONALIZED_CONVERSION_PROBABILITY = 0.16
_MASS_PROMOTION_CONVERSION_PROBABILITY = 0.08
_engine = PersonalOfferEngine(top_n=3)


def simulate() -> None:
    init_db()
    with db_session() as db:
        service = CustomerService(db)
        customers = db.query(Customer).all()

        for customer in customers:
            segment = service.get_segment(customer)
            context = OfferContext(cart_total=customer.avg_order_value or 0)
            offers = _engine.generate_offers(segment, customer.price_sensitivity, context)

            is_control_group = random.random() < 0.5
            conversion_probability = _MASS_PROMOTION_CONVERSION_PROBABILITY if is_control_group else _PERSONALIZED_CONVERSION_PROBABILITY

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


if __name__ == "__main__":
    simulate()
