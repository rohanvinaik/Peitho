"""peitho.query.plan — the sense→plan→act composition, the top of the controller (CONTROL_ARCHITECTURE.md).

Composes the controller's stages over ONE state estimate into a single justified Plan:
  - **transfers** — internal cross-store moves (the min-cost flow, §6, `route.plan_transfers_global`);
  - **dead_stock** — R1/R2 pull-backs to the triage hub / warehouse (`query.rules`);
  - **reorders** — regime-gated base-stock supplier orders (`query.supply`);
  - **preclears** — R6 anticipatory pre-clears (`query.preclear`; a scaffold, dark without the clearance calendar).

Each item carries its own `rule`/`why` — the decision-provenance log (DESIGN.md §7). Reconciliation: the
min-cost flow's per-cell *unmet* reorders are subsumed by the regime-gated base-stock supplier orders (§7),
which are the network-wide, seasonal-aware supplier signal — so the Plan carries the latter and drops the
former. Pure I/O composition; the decisions all live in the stages it calls. No AI in the decision path.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from ..lenses.inventory import load_grid
from ..route import COVER_DAYS_DEFAULT, plan_transfers_global
from .preclear import preclear_actions
from .regime import article_regimes
from .rules import dead_stock_actions
from .significance import MIN_RUN_UNITS_DEFAULT, MIN_VELOCITY_DEFAULT, significant_moves
from .supply import supply_plan


@dataclass(frozen=True)
class Plan:
    """The controller's full decision for one state estimate. Every list's items carry their own rule/why."""

    transfers: list  # route.Transfer — internal moves (min-cost flow, §6)
    dead_stock: list  # rules.Action — R1/R2 pull-backs (§5)
    reorders: list  # supply.SupplyOrder — base-stock supplier orders, regime-gated (§7)
    preclears: list  # rules.Action — R6 anticipatory pre-clears (§8; dark without the clearance calendar)


def build_plan(
    grid,
    regimes: dict,
    min_cost: dict | None = None,
    target_cover_days: float = COVER_DAYS_DEFAULT,
    sale_date: datetime.date | None = None,
    today: datetime.date | None = None,
    baselines: dict | None = None,
    min_velocity: float = MIN_VELOCITY_DEFAULT,
    min_run_units: int = MIN_RUN_UNITS_DEFAULT,
) -> Plan:
    """Compose the controller stages over `grid` + `regimes` into one Plan. I/O shell — every decision lives
    in the stage it calls. The min-cost flow's raw moves pass through `significance.significant_moves` (net →
    velocity-gate → run-gate) so `Plan.transfers` is the SPARSE significant set, not the raw flood.
    `sale_date`/`today`/`baselines` feed the pre-clear scaffold (no `sale_date` → dark).
    """
    transfers, _ = plan_transfers_global(grid, target_cover_days, min_cost)
    transfers = significant_moves(transfers, grid, min_velocity, min_run_units)  # noise-removal → the sparse set
    return Plan(
        transfers=transfers,
        dead_stock=dead_stock_actions(grid),
        reorders=supply_plan(grid, regimes),
        preclears=preclear_actions(grid, baselines or {}, sale_date=sale_date, today=today),
    )


def report() -> None:
    """CLI: `python -m peitho.query.plan` — the full controller plan over the landed grid."""
    plan = build_plan(load_grid(), article_regimes())
    print("Controller plan (sense → plan → act):")
    print(f"  transfers  — internal moves (min-cost flow) : {len(plan.transfers):>6,}")
    print(f"  dead_stock — R1/R2 pull-backs               : {len(plan.dead_stock):>6,}")
    print(f"  reorders   — base-stock supplier orders     : {len(plan.reorders):>6,}")
    print(f"  preclears  — R6 (dark without a clearance calendar) : {len(plan.preclears):>6,}")


if __name__ == "__main__":
    report()
