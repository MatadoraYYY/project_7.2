"""Rule-based, deterministic customer segmentation."""

from dataclasses import dataclass
from datetime import datetime

from app.core.config import get_settings
from app.models.schemas import SegmentType

settings = get_settings()


@dataclass(frozen=True)
class CustomerSignals:
    total_orders: int
    lifetime_value: float
    last_purchase_at: datetime | None
    price_sensitivity: float
    now: datetime | None = None

    @property
    def reference_time(self) -> datetime:
        return self.now or datetime.utcnow()

    @property
    def days_since_last_purchase(self) -> int | None:
        if self.last_purchase_at is None:
            return None
        delta = self.reference_time - self.last_purchase_at
        return max(delta.days, 0)


class SegmentClassifier:
    def classify(self, signals: CustomerSignals) -> SegmentType:
        if signals.total_orders <= 0:
            return SegmentType.NEW_USER

        days_idle = signals.days_since_last_purchase
        if days_idle is not None and days_idle >= settings.dormant_days_threshold:
            return SegmentType.DORMANT

        if signals.total_orders >= settings.vip_min_orders and signals.lifetime_value >= settings.vip_ltv_threshold:
            return SegmentType.VIP

        if signals.price_sensitivity >= 1.2:
            return SegmentType.PRICE_SENSITIVE

        return SegmentType.REPEAT_BUYER
