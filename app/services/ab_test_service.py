"""A/B test analytics: personalized offers vs mass promotion."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orm_models import Customer, OfferRecord
from app.models.schemas import ABTestGroupResult, ABTestResponse

_PERSONALIZED_MARGIN_IMPACT_PCT = -3.0
_MASS_PROMOTION_MARGIN_IMPACT_PCT = -10.0

_METHODOLOGY_NOTE = (
    "Расчёт выполнен на синтетическом наборе данных и демонстрирует методику измерения "
    "эффекта персонализации. Для реальных бизнес-решений требуется пилотный эксперимент "
    "на фактических данных с контрольной группой."
)


class ABTestService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _group_result(self, is_control: bool, label: str, margin_pct: float) -> ABTestGroupResult:
        generated = self._db.scalar(
            select(func.count(OfferRecord.id)).where(OfferRecord.is_control_group == is_control)
        ) or 0
        converted = self._db.scalar(
            select(func.count(OfferRecord.id)).where(
                OfferRecord.is_control_group == is_control, OfferRecord.converted.is_(True)
            )
        ) or 0
        customers = self._db.scalar(
            select(func.count(func.distinct(OfferRecord.customer_id))).where(
                OfferRecord.is_control_group == is_control
            )
        ) or 0
        avg_order = self._db.scalar(
            select(func.avg(Customer.avg_order_value)).where(
                Customer.id.in_(
                    select(OfferRecord.customer_id).where(OfferRecord.is_control_group == is_control)
                )
            )
        ) or 0.0

        return ABTestGroupResult(
            group=label,
            customers=customers,
            offers_generated=generated,
            offers_converted=converted,
            conversion_rate=round(converted / generated, 4) if generated else 0.0,
            average_order_value=round(float(avg_order), 2),
            estimated_margin_pct=margin_pct,
        )

    def run(self) -> ABTestResponse:
        personalized = self._group_result(False, "personalized", _PERSONALIZED_MARGIN_IMPACT_PCT)
        mass = self._group_result(True, "mass_promotion", _MASS_PROMOTION_MARGIN_IMPACT_PCT)

        if mass.conversion_rate > 0:
            uplift = (personalized.conversion_rate - mass.conversion_rate) / mass.conversion_rate * 100
        else:
            uplift = 0.0

        return ABTestResponse(
            personalized=personalized,
            mass_promotion=mass,
            conversion_uplift_pct=round(uplift, 1),
            margin_uplift_pct=round(_PERSONALIZED_MARGIN_IMPACT_PCT - _MASS_PROMOTION_MARGIN_IMPACT_PCT, 1),
            note=_METHODOLOGY_NOTE,
        )
