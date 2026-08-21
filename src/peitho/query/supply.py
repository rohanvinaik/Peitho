"""peitho.query.supply — the regime-switched supply sizer (CONTROL_ARCHITECTURE.md §7).

Given the state estimate + each article's regime (`query.regime`), decide the SUPPLIER order. **BASE** items
get (s,S) base-stock replenishment — order up to cover demand over the protection interval (lead time +
review); **SEASONAL** items get NO in-season reorder (the fashion window closes before it lands — the operator
takes the hit and learns for next year, THEORY.md §7), so their unmet demand is accepted, not ordered.
UNKNOWN is treated as base (conservatively replenished) — note the first-year-item caveat (a genuinely new
base item reads SEASONAL until it recurs; that is an operator-flag against the default, not this module's job).

The **newsvendor critical fractile** is provided for next-season INTAKE sizing (a single bet placed at season
start) — advisory, and its overage cost (the measured clearance depth) is a knob here, not yet measured.

Supplier orders are ARTICLE/style-level (a style ships as a size run), aggregating the network's position.
The lead time (the manufacturer lead), review period, and safety stock are **explicit knobs, never hidden
defaults**; they want per-supplier calibration. Pure decisions Detective-pinned; the orchestrator is the I/O
shell. Deterministic — no AI in the decision path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..lenses.inventory import WINDOW_DAYS, velocity
from .regime import SEASONAL


def base_stock_level(velocity_per_day: float, lead_time_days: float, review_days: float, safety: int = 0) -> int:
    """The order-up-to level S: expected demand over the protection interval (lead time + review) + safety
    stock. Pure over the rate and the interval knobs."""
    return round(velocity_per_day * (lead_time_days + review_days)) + safety


def reorder_qty(position: int, base_stock: int) -> int:
    """Units to order to restore base-stock: `max(0, S − position)`, where position is on-hand + in-transit.
    Zero when already at/above the level. Pure over two ints."""
    return max(0, base_stock - position)


def critical_fractile(underage_cost: float, overage_cost: float) -> float:
    """The newsvendor critical ratio `Cu / (Cu + Co)` — the optimal service level for a single-shot seasonal
    bet, where Cu = the cost of a lost sale (underage) and Co = the markdown conceded on unsold stock
    (overage = the clearance depth). 0.0 when the costs are degenerate (non-positive sum). Pure."""
    denom = underage_cost + overage_cost
    if denom <= 0:
        return 0.0
    return underage_cost / denom


def regime_order(regime: str, position: int, base_stock: int) -> int:
    """The regime-gated supplier order. SEASONAL gets NO in-season reorder (you cannot restock a season
    before it ends — take the hit); BASE and UNKNOWN replenish to base-stock. Pure over (str, int, int)."""
    if regime == SEASONAL:
        return 0  # the window closes before a reorder lands — accepted loss, not an order
    return reorder_qty(position, base_stock)


@dataclass(frozen=True)
class SupplyOrder:
    """One article-level supplier-order recommendation + its justification."""

    article: str
    qty: int
    regime: str
    why: str


def supply_plan(
    grid,
    regimes: dict,
    lead_time_days: float = 30.0,
    review_days: float = 30.0,
    safety: int = 0,
    window_days: int = WINDOW_DAYS,
) -> list:
    """Per-article base-stock supplier orders, regime-gated. I/O shell over a Grid + {article: regime}.

    Aggregates the network's position (total stock) and velocity (total window sales) per article, sizes the
    base-stock level, and emits a `SupplyOrder` for each BASE/UNKNOWN article below its level. SEASONAL
    articles are suppressed. `lead_time_days` defaults to the operator's stated manufacturer lead — an
    explicit knob wanting per-supplier calibration, never a silent assumption.
    """
    stock: dict = defaultdict(int)
    sales: dict = defaultdict(int)
    for variant, cells in grid.items():
        article = variant[0]
        for c in cells.values():
            stock[article] += c.stock
            sales[article] += c.sale_qty
    out: list = []
    for article, position in stock.items():
        v = velocity(sales[article], window_days)
        level = base_stock_level(v, lead_time_days, review_days, safety)
        regime = regimes.get(article, "UNKNOWN")
        qty = regime_order(regime, position, level)
        if qty > 0:
            out.append(
                SupplyOrder(article, qty, regime, f"position {position} < base-stock {level} (v={v:.2f}/d, {regime})")
            )
    return out
