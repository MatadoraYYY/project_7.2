"""Price sensitivity (elasticity) estimation from purchase history."""

from dataclasses import dataclass

from app.core.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class PurchaseSignal:
    price: float
    quantity: int
    had_discount: bool


class PriceSensitivityCalculator:
    def __init__(self, min_bound: float | None = None, max_bound: float | None = None) -> None:
        self._min_bound = min_bound if min_bound is not None else settings.elasticity_min
        self._max_bound = max_bound if max_bound is not None else settings.elasticity_max
        if self._min_bound >= self._max_bound:
            raise ValueError("min_bound must be strictly less than max_bound")

    def calculate(self, purchases: list[PurchaseSignal]) -> float:
        if len(purchases) < 3:
            return 0.7

        discounted = [p for p in purchases if p.had_discount]
        full_price = [p for p in purchases if not p.had_discount]

        if not discounted or not full_price:
            return 0.7

        avg_qty_discounted = sum(p.quantity for p in discounted) / len(discounted)
        avg_qty_full_price = sum(p.quantity for p in full_price) / len(full_price)

        if avg_qty_full_price <= 0:
            return 0.7

        demand_uplift_ratio = (avg_qty_discounted - avg_qty_full_price) / avg_qty_full_price
        raw_score = 0.7 + demand_uplift_ratio
        return self._clip(raw_score)

    def _clip(self, value: float) -> float:
        return max(self._min_bound, min(self._max_bound, value))
