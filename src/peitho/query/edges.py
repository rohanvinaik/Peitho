"""peitho.query.edges — typed, conditional edge admissibility for the routing controller
(CONTROL_ARCHITECTURE.md §3.2). Which store→store / warehouse→store moves are allowed, and of what KIND.

The routing graph is directed and admissibility is a *rule*, not a given (THEORY.md §5–§6):
  - warehouses are one-way OUT (WH_OUT); to a satellite that out-move is a top-up (TOPUP, R3-B1);
  - dead / stagnant stock is pulled to the cognition hub for the operator to sort (TO_TRIAGE, R1);
  - good stock reallocates toward a throughput node (TO_SELL, R3);
  - a SoR/store item returns warehouse-ward only after its no-sale threshold (RETURN, R2/R7);
  - anything else — e.g. a plain store→store move not toward a SELL node — is BLOCKED.

This is the controller's FINER node model (SELL/TRIAGE/SOR/STORE/WAREHOUSE, a node carrying two roles), distinct
from the estimator's coarse `inventory.node_role` (RETAIL-vs-not). The `admissible` verdict is pure over
booleans (Detective-pinnable); the thin shell resolves a store pair + item state into those booleans.
Deterministic — no AI in the decision path.
"""

from __future__ import annotations

from ..network import active_network as _active_network

# Controller role model. The role SETS are DATA — they come from the active cassette's network.toml
# (peitho.network), where a node may hold more than one role (a node that is both a SELL sink and the
# TRIAGE hub the operator sorts at). WAREHOUSE/SELL are induced from the sales geometry; SOR (a sale-or-return
# contract) and TRIAGE (the operator's physical presence) are declared, since the sales data does not carry
# them. The verdict logic below is agnostic to which network is loaded.
_NET = _active_network()
WAREHOUSE = _NET.role_set("WAREHOUSE")  # source nodes — the zero-sales warehouses
SELL = _NET.role_set("SELL")  # the throughput sinks for good-stock reallocation
TRIAGE = _NET.role_set("TRIAGE")  # the cognition hub(s) for dead-stock pull-back
SOR = _NET.role_set("SOR")  # sale-or-return
STORE = _NET.role_set("STORE")  # ordinary retail nodes

# Edge kinds (named codes, never bare bools — each is a distinct fact for the router + the human).
WH_OUT = "WH_OUT"
TOPUP = "TOPUP"
TO_TRIAGE = "TO_TRIAGE"
TO_SELL = "TO_SELL"
RETURN = "RETURN"
BLOCKED = "BLOCKED"


def admissible(
    src_warehouse: bool,
    dst_sell: bool,
    dst_triage: bool,
    dst_warehouse: bool,
    dst_satellite: bool,
    stagnant: bool,
    past_return: bool,
) -> str:
    """The edge verdict for a src→dst move of an item in a given state. Pure over booleans.

    Precedence encodes the operator's rules: a warehouse source is one-way out (a top-up to a satellite);
    then dead stock to the hub; then good stock to a throughput node; then a conditional return; else
    blocked. `dst_satellite` = destination is an ordinary store or SoR node; `stagnant` = the item is dead
    at its source (R1); `past_return` = the item has crossed its no-sale threshold (R2/R7).
    """
    if src_warehouse:
        return TOPUP if dst_satellite else WH_OUT  # warehouse is one-way OUT; to a satellite it is a top-up
    if dst_triage and stagnant:
        return TO_TRIAGE  # dead stock -> the cognition hub for the operator's signal/noise sort (R1)
    if dst_sell:
        return TO_SELL  # good stock -> a throughput node (R3)
    if dst_warehouse and past_return:
        return RETURN  # SoR/store item returns warehouse-ward after the no-sale threshold (R2/R7)
    return BLOCKED  # e.g. a plain store->store move not toward a SELL node


def roles_of(store: str) -> frozenset:
    """The set of controller roles a store holds (a node -> {SELL, TRIAGE}). Empty for an unknown store. Pure."""
    out = set()
    if store in WAREHOUSE:
        out.add("WAREHOUSE")
    if store in SELL:
        out.add("SELL")
    if store in TRIAGE:
        out.add("TRIAGE")
    if store in SOR:
        out.add("SOR")
    if store in STORE:
        out.add("STORE")
    return frozenset(out)


def edge_kind(src: str, dst: str, stagnant: bool = False, past_return: bool = False) -> str:
    """Resolve a store pair + item state into an edge verdict, via `roles_of` + `admissible`. Thin shell."""
    return admissible(
        src_warehouse=src in WAREHOUSE,
        dst_sell=dst in SELL,
        dst_triage=dst in TRIAGE,
        dst_warehouse=dst in WAREHOUSE,
        dst_satellite=dst in (STORE | SOR),
        stagnant=stagnant,
        past_return=past_return,
    )
