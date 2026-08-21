"""peitho.resolve — the RESOLVING LAYER (proof-of-concept: routing).

`GEOMETRY.md` "The resolving layer": significance is resolved from the wide raw bank-field BY STRUCTURE —
network-native, hierarchical, never a flat threshold. This is the ROUTING POC, built on the two interfaces
that exist today (the third, the hierarchical Jordan-vs-Jordan comparison across independent network
traversals, needs the §10/§11 multi-network substrate and is deferred):

  1. **Top-down network traversal.** The spatial network (`route.plan_transfers_global`'s signed Bellman-Ford
     / min-cost flow) resolves each demand-live deficit's ACTION: reachable surplus → `ROUTE` (a transfer);
     isolated → `ORDER` (a supplier reorder). No cutoff — the graph traversal IS the resolution, and it
     already drops the non-demand-live noise the raw field carries.
  2. **The granular position space.** Each resolved cell carries its full signed-ternary SIGNATURE (the
     noticer field), so the resolution is conditioned on the whole non-flat read, not a collapsed scalar.

The claim under test (validated by the three-oracle cross-evaluation): traversal + position resolve the wide
geometry field to the tight, demand-live routing-significant set NATIVELY — the resolving layer the flat
estimator could only fake with a momentum gate, and at higher operator-recall.
"""

from __future__ import annotations

from dataclasses import dataclass

from .banks import VELOCITY
from .grid import Grid
from .noticer import DIMS, notice
from .otp import OPPOSE
from .query.regime import BASE
from .route import COVER_DAYS_DEFAULT, plan_transfers_global

ROUTE = "ROUTE"  # the spatial traversal found reachable surplus → a transfer resolves the deficit
ORDER = "ORDER"  # the deficit is isolated (no reachable surplus) → a supplier reorder resolves it

# the position-gate verdicts (interface 2): a resolved signal is a live decision, or it drops
KEEP = "KEEP"
DROP = "DROP"

_VEL = DIMS.index(VELOCITY)  # the VELOCITY slot in a cell's signed-ternary signature (fading = OPPOSE)


def gate(action: str, signature: tuple | None, is_core: bool) -> str:
    """The POSITION gate (interface 2): resolve, on the granular signature, whether a traversal-resolved
    signal is a live decision (`KEEP`) or drops (`DROP`). `ROUTE` — moving EXISTING stock, cheap and
    reversible — is always kept. An `ORDER` (a supplier reorder) DROPs when the VELOCITY position is fading (a
    dying line: reordering more from the supplier is the wrong call), UNLESS the full-signature ESCAPE HATCH
    protects it: a **core** item (BASE / kept year-on-year as base inventory) is struck only by high-level
    decision, never by a velocity dip. A cell with no signature (the traversal flagged it, the noticer did
    not) is kept — can't assess, so don't drop. Pure over `(action, signature|None, is_core)`, named codes.
    The escape hatch reads the *full* signature, so it extends beyond the core case as more protections are found."""
    if action == ROUTE:
        return KEEP
    if is_core:
        return KEEP  # the core / base-inventory escape hatch — high-level strike only, never a velocity dip
    if signature is None:
        return KEEP  # traversal flagged it but the field is silent — can't assess → conservative keep
    if signature[_VEL] == OPPOSE:
        return DROP  # fading, non-core, isolated → not a live reorder
    return KEEP


@dataclass(frozen=True)
class ResolvedSignal:
    """One deficit the resolving layer surfaces: the traversal-resolved ACTION (ROUTE/ORDER), the geometry's
    granular position SIGNATURE at that cell (`None` if the cell is noticer-silent), and `core` — whether the
    full-signature escape hatch protected it (a BASE / year-on-year item)."""

    variant: tuple
    store: str
    action: str
    qty: int
    signature: tuple | None
    label: str | None
    core: bool = False


def resolve_routing(
    grid: Grid, target_cover_days: float = COVER_DAYS_DEFAULT, floor_units: int = 1, regimes: dict | None = None
) -> list:
    """Resolve the geometry's significance to the tight routing-significant set, network-native. Interface 1
    (spatial TRAVERSAL, `plan_transfers_global`) decides ROUTE vs ORDER per demand-live deficit; interface 2
    (the granular POSITION `gate`) keeps or drops it on the full signed-ternary signature, with the core /
    base-inventory escape hatch (`regimes` = `article_regimes`, BASE = core). The wide raw field is resolved
    by structure — no flat gate. Returns the KEPT resolved signals. I/O shell; the traversal, the signatures,
    and the `gate` are each pinned."""
    if regimes is None:
        from .query.regime import article_regimes

        regimes = article_regimes()
    transfers, reorders = plan_transfers_global(grid, target_cover_days, floor_units=floor_units)
    sig_by_cell = {(a.variant, a.store): a for a in notice(grid)}

    def resolved(variant, store, action, qty):
        a = sig_by_cell.get((variant, store))
        sig = a.signature if a else None
        is_core = regimes.get(variant[0]) == BASE
        if gate(action, sig, is_core) == DROP:
            return None
        return ResolvedSignal(variant, store, action, qty, sig, a.label if a else None, is_core)

    out: list = []
    for t in transfers:
        out.append(resolved(t.variant, t.dest, ROUTE, t.qty))
    for r in reorders:
        out.append(resolved(r.variant, r.store, ORDER, r.qty))
    return [r for r in out if r is not None]
