"""peitho.query.preclear — the anticipatory pre-clearance rule R6 (CONTROL_ARCHITECTURE.md §8).

**SCAFFOLD (2026-08-18).** The operator's R6: before an end-of-season/clearance sale, route already-good-sellers
to a throughput SELL node to clear them at FULL margin *before* the sale forces the extra markdown. Acting on a
KNOWN future constraint (the sale date) — anticipatory / model-predictive control.

The PURE decisions here are fully built and Detective-pinned: `high_sale_propensity` ("would this sell
anyway?" — at or above its baseline velocity) and `should_preclear` (the gate: high propensity AND the sale
is imminent AND the item is not already at a SELL node). The ORCHESTRATOR is a scaffold, DARK until its
inputs land — with `sale_date=None` it emits nothing.

DEFERRED INPUTS (why this is a scaffold, not a live pass — tracked for the pre-clear PR):
  1. The SALE CALENDAR — the dated clearance windows. Operator-supplied, passed as `sale_date`; no calendar
     source yet, so the pass is dark until one is provided.
  2. The INCREMENTAL clearance discount (the operator's incremental sale cut) — the saved-margin headline. NOT
     measurable from the snapshot: it is a temporal/dynamics quantity (the source feed defers it to the daily
     pull) and an operator sale-policy input. The measured snapshot markdown is the TOTAL off-list-price
     markdown, a different, larger number (it bakes in the baseline inflated-list-price discount).
  3. Destination selection — the full version routes each pre-clear to the nearest/best SELL node via the
     min-cost flow (`query.flow`); the scaffold emits a placeholder SELL node.
  4. The propensity baseline + threshold — a per-store velocity baseline and `min_deviation` want calibration.

Deterministic — no AI in the decision path. Reuses the controller's Action record (`query.rules.Action`).
"""

from __future__ import annotations

import datetime

from ..geometry import deviation
from ..lenses.inventory import WINDOW_DAYS, coarse_roles, node_role, velocity
from . import edges
from .rules import Action

PRECLEAR = "PRECLEAR"
# scaffold: a placeholder SELL node (the TRIAGE hub) from the active cassette's network — not a hardcoded
# code; the full pass will pick the nearest SELL node via the flow.
_SCAFFOLD_DEST = next(iter(sorted(edges.TRIAGE)), "") or next(iter(sorted(edges.SELL)), "")


def high_sale_propensity(velocity_per_day: float, baseline_per_day: float, min_deviation: float = 0.0) -> bool:
    """Would this item sell anyway? True when its velocity is at or above baseline (signed deviation ≥
    `min_deviation`) — the 'good seller' the operator clears BEFORE the sale rather than discounting. Pure."""
    return deviation(velocity_per_day, baseline_per_day) >= min_deviation


def should_preclear(high_propensity: bool, days_to_sale: int, horizon_days: int, at_sell_node: bool) -> bool:
    """The R6 gate: pre-clear a would-sell-anyway item when the sale is imminent (0 ≤ days_to_sale ≤
    `horizon_days`) and it is NOT already at a SELL node (where it would clear at full margin). Pure."""
    if not high_propensity or at_sell_node:
        return False
    return 0 <= days_to_sale <= horizon_days


def preclear_actions(
    grid,
    baselines: dict,
    sale_date: datetime.date | None = None,
    today: datetime.date | None = None,
    horizon_days: int = 14,
    min_deviation: float = 0.0,
    window_days: int = WINDOW_DAYS,
) -> list:
    """SCAFFOLD — the anticipatory pre-clear pass (R6). DARK until the clearance calendar lands: returns [] when
    `sale_date` is None. Given a sale date, emits PRECLEAR Actions for good-sellers with stock that are not
    yet at a SELL node. `baselines` = {store: baseline_velocity} (the propensity reference). See the module
    docstring for the deferred inputs. I/O shell over a Grid.
    """
    if sale_date is None:
        return []  # no clearance calendar -> nothing to anticipate (the scaffold's dark path)
    today = today or datetime.date.today()
    days = (sale_date - today).days
    coarse = coarse_roles(grid)  # grid-induced role map, once per grid
    out: list = []
    for variant, cells in grid.items():
        article, color, size = variant
        for store, c in cells.items():
            if node_role(store, coarse) != "RETAIL" or c.stock <= 0:
                continue
            v = velocity(c.sale_qty, window_days)
            propensity = high_sale_propensity(v, baselines.get(store, 0.0), min_deviation)
            if should_preclear(propensity, days, horizon_days, at_sell_node=store in edges.SELL):
                out.append(
                    Action(
                        PRECLEAR,
                        article,
                        color,
                        size,
                        store,
                        _SCAFFOLD_DEST,
                        c.stock,
                        "R6",
                        f"good seller (v={v:.2f}/d) → pre-clear to {_SCAFFOLD_DEST} before clearance in {days}d",
                    )
                )
    return out
