"""peitho.query.rules — the controller's dead-stock / pull-back rule engine (CONTROL_ARCHITECTURE.md §5).

Forward-chaining production rules over the state estimate. This module carries the rules that get STAGNANT
stock OUT of the network — **R1** (pull dead stock to the cognition hub for the operator to sort) and **R2**
(return a sale-or-return item warehouse-ward after it fails to sell). The reallocation + reorder rules
(R3/R4) already live in `route.py` (the transfer layer, upgrading to a min-cost flow); the anticipatory
pre-clear (R6) is its own later pass. Each fired action carries its justification (the decision-provenance
log — DESIGN.md §7).

Signal note — what feeds "stagnant" (and what it misses): read from `inventory.classify_cell == IDLE_STOCK`
(stock on hand, ZERO sales across the pull window), a defensible proxy for the operator's "several months of
no sale" because the window already exceeds that span. The precise per-item shelf-ageing buckets are NOT in
the local `grid.Cell` (only `recent_sales`/window `sale_qty` are), so a day-exact threshold is a deferred
signal-enrichment, not available here. Deterministic — no AI in the path.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..lenses.inventory import classify_cell, coarse_roles, node_role
from . import edges

# Action kinds (named codes — each a distinct move the actuator serializes).
PULL_TRIAGE = "PULL_TRIAGE"
RETURN = "RETURN"
HOLD = "HOLD"  # stagnant but already at the hub/source — nothing to move (not emitted)
NONE = "NONE"  # not stagnant — no dead-stock action

# The pull-to-triage / SoR-return DESTINATIONS are network facts — the sole TRIAGE hub and WAREHOUSE from
# the active cassette (edges role sets, sourced from peitho.network), never a hardcoded store code.
TRIAGE_HUB = next(iter(sorted(edges.TRIAGE)), "")  # the cognition hub a pull-to-triage targets
RETURN_WAREHOUSE = next(iter(sorted(edges.WAREHOUSE)), "")  # the warehouse a SoR return targets


@dataclass(frozen=True)
class Action:
    """One controller action + its justification. `rule` names the firing rule (R1/R2); `why` is the
    human-readable signal that fired it (the audit surface on which the operator checks the machine)."""

    kind: str
    article: str
    color: str
    size: str
    src: str
    dst: str
    qty: int
    rule: str
    why: str


def stagnant_action(status: str, is_sor: bool, is_triage_hub: bool, is_warehouse: bool) -> str:
    """The dead-stock verdict for one cell. Pure over (str, bool, bool, bool).

    Fires only on IDLE_STOCK (stock on hand, no window sales). A sale-or-return node returns its dead stock
    warehouse-ward (R2); dead stock already sitting at the triage hub or the warehouse is HELD (nowhere to
    move it); otherwise a satellite/store's dead stock is pulled to the cognition hub for the operator's sort (R1).
    """
    if status != "IDLE_STOCK":
        return NONE  # not stagnant -> no dead-stock action
    if is_sor:
        return RETURN  # SoR item unsold -> return warehouse-ward (R2)
    if is_triage_hub or is_warehouse:
        return HOLD  # already at the hub / the source -> nothing to move
    return PULL_TRIAGE  # stagnant at a satellite/store -> pull to the cognition hub to sort (R1)


def dead_stock_actions(grid) -> list:
    """Fire R1/R2 over every cell of the grid → [Action], each with its justification. I/O-shell over a Grid.

    Uses `classify_cell` for the stagnation status and the finer `edges` role sets to route the action; the
    `stagnant_action` verdict decides kind. HOLD/NONE verdicts emit nothing.
    """
    coarse = coarse_roles(grid)  # grid-induced role map, once per grid
    out: list = []
    for variant, cells in grid.items():
        article, color, size = variant
        for store, c in cells.items():
            status = classify_cell(c.stock, c.recent_sales, c.sale_qty, node_role(store, coarse))
            kind = stagnant_action(
                status,
                is_sor=store in edges.SOR,
                is_triage_hub=store in edges.TRIAGE,
                is_warehouse=store in edges.WAREHOUSE,
            )
            if kind == PULL_TRIAGE:
                out.append(
                    Action(
                        PULL_TRIAGE,
                        article,
                        color,
                        size,
                        store,
                        TRIAGE_HUB,
                        c.stock,
                        "R1",
                        f"IDLE_STOCK {c.stock}u at {store} → {TRIAGE_HUB} triage",
                    )
                )
            elif kind == RETURN:
                out.append(
                    Action(
                        RETURN,
                        article,
                        color,
                        size,
                        store,
                        RETURN_WAREHOUSE,
                        c.stock,
                        "R2",
                        f"SoR IDLE_STOCK {c.stock}u at {store} → {RETURN_WAREHOUSE}",
                    )
                )
    return out
