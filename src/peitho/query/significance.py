"""peitho.query.significance — the controller's noise-removal stage (CONTROL_ARCHITECTURE).

The min-cost flow produces the *complete* set of admissible coverage moves — with the ≥1 coverage floor that
is thousands of mostly single-unit moves. That raw set is not what the operator acts on: the classical-AI
controller must resolve it into the **sparse, significant set** worth a stock-boy's day (the operator's spec:
"resolve the recommended inter-node moves to remove the noise and keep only the correct sparse control-flow
moves to sustain sufficient stock"). Three deterministic decisions, no model:

  1. `net_transfers` — cancel opposing same-variant flows (A→B and B→A) to the dominant remainder, so no
     cross-cycling survives regardless of how the flow produced the moves;
  2. `move_verdict` (A) — a per-move VELOCITY gate: keep a coverage move only if the destination sells that
     item fast enough to be worth a trip; the ultra-slow tail falls out (accepted stockout under "maximal
     efficiency — sometimes a shoe runs out");
  3. `run_verdict` (B) — a per-run gate: keep a source→dest run only if it carries enough total units to be
     worth the drive, so a lone straggler to a store no one is otherwise visiting falls out.

The thresholds are the policy knobs the operator calibrates on feedback (seeded from the landed data, below).
"""

from __future__ import annotations

from collections import defaultdict

# calibrated 2026-08-19 from the landed grid (see the significance calibration) — the tunable policy knobs.
MIN_VELOCITY_DEFAULT = 0.05  # units/day at the destination: ≈ selling at least ~1 every 3 weeks to be worth a trip
MIN_RUN_UNITS_DEFAULT = 3  # a source→dest run must carry at least this many units to justify the drive

MOVE_KEEP = "KEEP"
MOVE_DROP_SLOW = "DROP_SLOW"  # the destination sells this item too slowly to be worth a coverage trip
RUN_KEEP = "KEEP"
RUN_DROP_THIN = "DROP_THIN"  # the run carries too little to justify the drive


def move_verdict(velocity: float, min_velocity: float) -> str:
    """(A) Per-move velocity gate: KEEP if the destination's sell-rate for the item clears `min_velocity` — a
    high-volume item worth sustaining — else DROP_SLOW (the ultra-slow tail, an accepted stockout). Pure."""
    return MOVE_KEEP if velocity >= min_velocity else MOVE_DROP_SLOW


def run_verdict(run_units: int, min_run_units: int) -> str:
    """(B) Per-run gate: KEEP a source→dest run if it carries at least `min_run_units` total units — worth the
    drive — else DROP_THIN (a straggler no one would make a trip for). Pure over two ints."""
    return RUN_KEEP if run_units >= min_run_units else RUN_DROP_THIN


def net_transfers(transfers: list) -> list:
    """Cancel opposing same-variant flows: if variant V moves A→B AND B→A, net to the dominant direction's
    remainder (drop when they fully cancel). Makes 'no cross-cycling' structural regardless of how the flow
    produced the moves. Pure over a list of `route.Transfer`; returns new Transfers with the netted quantities.
    """
    from ..route import Transfer

    total: dict = defaultdict(int)
    rep: dict = {}
    for t in transfers:
        k = (t.variant, t.source, t.dest)
        total[k] += t.qty
        rep[k] = t
    out: list = []
    seen: set = set()
    for (v, a, b), q in total.items():
        if (v, a, b) in seen:
            continue
        seen.add((v, a, b))
        seen.add((v, b, a))
        n = q - total.get((v, b, a), 0)
        if n > 0:  # A→B dominates; emit the remainder with the A→B cost
            out.append(Transfer(v, b, a, n, rep[(v, a, b)].cost))
        elif n < 0:  # B→A dominates
            out.append(Transfer(v, a, b, -n, rep[(v, b, a)].cost))
        # n == 0 → fully cancel; drop
    return out


def significant_moves(
    transfers: list,
    grid,
    min_velocity: float = MIN_VELOCITY_DEFAULT,
    min_run_units: int = MIN_RUN_UNITS_DEFAULT,
    window_days: int | None = None,
) -> list:
    """Resolve the flow's raw coverage moves into the sparse significant set (net → velocity-gate → run-gate).
    I/O shell over the grid (for the destination sell-rate); every decision lives in `move_verdict` /
    `run_verdict`. Returns the surviving `route.Transfer`s — the moves the controller judges worth acting on.
    """
    from ..lenses import inventory

    wd = window_days if window_days is not None else inventory.WINDOW_DAYS
    cell_of = {(v, s): c for v, cells in grid.items() for s, c in cells.items()}

    kept_a: list = []
    for t in net_transfers(transfers):  # (A) velocity gate per move, on the destination's sell-rate
        c = cell_of.get((t.variant, t.dest))
        # recency-weighted demand (the sales-age spectrum), NOT the flat window average: a fresh mover at
        # the destination clears the gate, a fader does not — the same distinction the operator reads by hand.
        vel = inventory.recent_velocity(c.sls_age, window_days=wd) if c else 0.0
        if move_verdict(vel, min_velocity) == MOVE_KEEP:
            kept_a.append(t)

    run_units: dict = defaultdict(int)  # (B) run gate — group by (source, dest), drop thin runs
    for t in kept_a:
        run_units[(t.source, t.dest)] += t.qty
    return [t for t in kept_a if run_verdict(run_units[(t.source, t.dest)], min_run_units) == RUN_KEEP]
