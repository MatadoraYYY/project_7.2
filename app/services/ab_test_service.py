"""A/B test analytics: personalized vs. mass-promotion control group."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm_models import Customer, OfferRecord

_MASS_PROMO_MARGIN_IMPACT_PCT = -10.0
_PERSONALIZED_MARGIN_IMPACT_PCT = -3.0


class ABTestService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def compute_comparison(self) -> dict:
        personalized_group = self._aggregate_group(is_control_group=False)
        mass_group = self._aggregate_group(is_control_group=True)

        conversion_uplift_pct = self._safe_uplift_pct(personalized_group["conversion_rate"], mass_group["conversion_rate"])
        margin_uplift_pct = round(_PERSONALIZED_MARGIN_IMPACT_PCT - _MASS_PROMO_MARGIN_IMPACT_PCT, 2)

        return {
            "personalized": personalized_group,
            "mass_promotion": mass_group,
            "conversion_uplift_pct": conversion_uplift_pct,
            "margin_uplift_pct": margin_uplift_pct,
            "note": (
                "Расчёт выполнен на синтетическом наборе данных и демонстрирует методику "
                "измерения эффекта персонализации. Для реальных бизнес-решений требуется "
                "пилотный эксперимент на фактических данных с контрольной группой."
            ),
        }

    def _aggregate_group(self, is_control_group: bool) -> dict:
        stmt = select(OfferRecord).where(OfferRecord.is_control_group == is_control_group)
        records = list(self._db.scalars(stmt))

        customer_ids = {r.customer_id for r in records}
        generated = len(records)
        converted = sum(1 for r in records if r.converted)
        conversion_rate = round(converted / generated, 4) if generated else 0.0

        avg_order_value = self._average_order_value(customer_ids)
        margin_pct = _MASS_PROMO_MARGIN_IMPACT_PCT if is_control_group else _PERSONALIZED_MARGIN_IMPACT_PCT

        return {
            "group": "mass_promotion" if is_control_group else "personalized",
            "customers": len(customer_ids),
            "offers_generated": generated,
            "offers_converted": converted,
            "conversion_rate": conversion_rate,
            "average_order_value": avg_order_value,
            "estimated_margin_pct": margin_pct,
        }

    def _average_order_value(self, customer_ids: set[int]) -> float:
        if not customer_ids:
            return 0.0
        stmt = select(Customer).where(Customer.id.in_(customer_ids))
        customers = list(self._db.scalars(stmt))
        if not customers:
            return 0.0
        return round(sum(c.avg_order_value for c in customers) / len(customers), 2)

    @staticmethod
    def _safe_uplift_pct(new_rate: float, baseline_rate: float) -> float:
        if baseline_rate <= 0:
            return 0.0
        return round(((new_rate - baseline_rate) / baseline_rate) * 100, 2)
