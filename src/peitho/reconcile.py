"""peitho.reconcile — reconstruct the operator's ACTUAL inter-store transfers from two dated stock snapshots.

The oracle/baseline: what they really move, recovered from the data (no self-report). Per (variant, store),
from two CUMULATIVE snapshots, the stock-flow identity gives their net move:

    end_stock − begin_stock = received − sent − sales     ⇒     received − sent = Δstock + Δsales

Aggregated per VARIANT across stores, internal transfers cancel, so the network sum of `received − sent`
is the *external* change: 0 ⇒ the variant moved only between stores (a pure manual transfer), >0 ⇒ a supplier
arrival, <0 ⇒ a return/removal. The conserved (=0) variants are the clean transfer signal. No AI — deterministic
arithmetic over the landed per-store drilldown (`stockQty`, cumulative `saleQty`). The comparison of these
actuals against the controller's recommendation lives in `reconcile.compare` (the back-run validation).
"""

from __future__ import annotations

import datetime
import json
import os
from collections import defaultdict

FLOW_TRANSFER = "TRANSFER"  # network-conserved — the variant moved only between stores (their manual transfer)
FLOW_SUPPLIER = "SUPPLIER_IN"  # net external inflow — a supplier arrival dominates
FLOW_RETURN = "RETURN_OUT"  # net external outflow — returns / removals dominate


def net_received(stock_begin: int, stock_end: int, sale_begin: int, sale_end: int) -> int:
    """Units a (variant, store) NET received over the interval, from two CUMULATIVE snapshots — the stock-flow
    identity `received − sent = Δstock + Δsales`. Positive = net in, negative = net out. Pure over four ints."""
    return (stock_end - stock_begin) + (sale_end - sale_begin)


def flow_class(variant_net_total: int) -> str:
    """Classify a variant's flow by its network-summed `net_received`: 0 ⇒ TRANSFER (conserved — moved only
    between stores); >0 ⇒ SUPPLIER_IN (net arrival); <0 ⇒ RETURN_OUT (net removal). Pure over one int."""
    if variant_net_total == 0:
        return FLOW_TRANSFER
    return FLOW_SUPPLIER if variant_net_total > 0 else FLOW_RETURN


AGREE_MATCH = "MATCH"  # model & operator moved this (variant, store) leg the SAME direction
AGREE_OPPOSITE = "OPPOSITE"  # opposite directions
AGREE_MODEL_ONLY = "MODEL_ONLY"  # the model recommended a move here; the operator made none
AGREE_OPERATOR_ONLY = "OPERATOR_ONLY"  # the operator moved here; the model recommended nothing
AGREE_NONE = "NONE"

SELL_SOLD = "SOLD"  # the item the operator moved IN sold at the destination after — demand materialized (signal)
SELL_SAT = "SAT"  # no post-move sales at the destination — possibly vibes / idiom
SELL_NA = "NA"  # not a receive (nothing was moved in to judge)

# gap SEVERITY a suggested move targets at its destination (validates the model covers REAL gaps)
GAP_HARD = "HARD_STOCKOUT"  # dest sold this item in the last 30d and is now at ZERO stock — a lost sale in progress
GAP_SOFT = "SOFT_BELOW"  # dest has recent demand but still some stock, below target cover
GAP_NONE = "NO_DEMAND"  # no recent demand at dest — the model should not fire here
# realized OUTCOME of a suggested move over the span. A 'no sale' is NOT a miss: the window is short and a
# high-volume mover's copies sell elsewhere (coverage, not failure) — the operator's own high-volume nuance.
OUT_REALIZED = "REALIZED_DEST"  # sold AT the destination within the span — demand realized at the exact node
OUT_ELSEWHERE = "LIVE_ELSEWHERE"  # sold elsewhere in the network — the item is live (multi-copy: coverage, not miss)
OUT_HIVOL_PENDING = "HIVOL_PENDING"  # no span sale yet, but a HIGH-volume mover — window too short, not a miss
OUT_SLOW_PENDING = "SLOW_PENDING"  # no span sale, a slow-but-real mover — plausible, pending
OUT_NO_SIGNAL = "NO_SIGNAL"  # no demand signal at all — a move to scrutinize


def leg_agreement(rec_net: int, actual_net: int) -> str:
    """Classify one (variant, store) leg by whether the model's recommended net and the operator's actual net
    point the same way. Each net is + (received), − (sent), or 0 (untouched). Pure over two ints:
    both move ⇒ MATCH / OPPOSITE; only the model ⇒ MODEL_ONLY; only the operator ⇒ OPERATOR_ONLY; neither ⇒ NONE."""
    if rec_net != 0 and actual_net != 0:
        return AGREE_MATCH if (rec_net > 0) == (actual_net > 0) else AGREE_OPPOSITE
    if rec_net != 0:
        return AGREE_MODEL_ONLY
    if actual_net != 0:
        return AGREE_OPERATOR_ONLY
    return AGREE_NONE


def move_verdict(received: int, sold_after: int) -> str:
    """For a (variant, store) the operator moved stock INTO, did it sell after? SOLD (demand materialized — real
    signal) vs SAT (no post-move sales — possibly vibes). Only a receive is judged; otherwise NA. Pure."""
    if received <= 0:
        return SELL_NA
    return SELL_SOLD if sold_after > 0 else SELL_SAT


def gap_severity(dest_stock: int, dest_recent: int) -> str:
    """Severity of the gap a suggested move targets at its destination — HARD (sold in the last 30d, now
    zero stock: a lost sale in progress), SOFT (recent demand, below-target but not out), or NONE (no recent
    demand — the model should not be firing here). Pure over two scalars; named codes, not a bool."""
    if dest_recent <= 0:
        return GAP_NONE
    if dest_stock <= 0:
        return GAP_HARD
    return GAP_SOFT


def move_outcome(dest_sold: int, net_sold: int, window_vol: int, hi_threshold: int) -> str:
    """Classify a suggested move's realized OUTCOME over the span. A 'no sale' is NOT a miss: over a short
    window most items don't turn, and for a high-volume mover a no-dest-sale is coverage (its copies sold
    elsewhere prove the demand), not failure. Pure over four scalars; named codes because REALIZED / live-
    elsewhere / high-vol-pending / slow-pending / no-signal are materially different facts, not one bool."""
    if dest_sold > 0:
        return OUT_REALIZED
    if net_sold > 0:
        return OUT_ELSEWHERE
    if window_vol >= hi_threshold:
        return OUT_HIVOL_PENDING
    if window_vol > 0:
        return OUT_SLOW_PENDING
    return OUT_NO_SIGNAL


def _daily_dir(date: str, root: str | None = None) -> str:
    """The dated daily-snapshot grid directory, resolved by the active cassette's adapter (owns the layout)."""
    from .source import adapter

    return adapter().daily_grid_dir(date, root)


def load_snapshot(date: str, root: str | None = None) -> dict:
    """{(article, color, size, store): (stockQty, saleQty)} from the dated daily snapshot — via the active
    cassette's data-input adapter (`peitho.source`), which owns the backend field parsing + snapshot paths."""
    from .source import adapter

    return adapter().load_snapshot(date, root)


def reconstruct(begin_date: str, end_date: str, root: str | None = None) -> dict:
    """Reconstruct the operator's actual moves between two dated snapshots. Returns:
      {"moves":   {(article,color,size): {store: net_received}}}  — per conserved (pure-transfer) variant,
       "store_net": {store: net units across all transfers}       — net receiver(+)/sender(−) per store,
       "counts":  {"transfer": n, "supplier": n, "return": n},
       "units":   {"transfer": u, "supplier": u, "return": u}}
    I/O shell; the decisions live in `net_received` / `flow_class`.
    """
    a = load_snapshot(begin_date, root)
    b = load_snapshot(end_date, root)

    per_variant: dict = defaultdict(dict)  # (article,color,size) -> {store: net_received}
    for k in set(a) | set(b):
        art, col, sz, st = k
        s0, q0 = a.get(k, (0, 0))
        s1, q1 = b.get(k, (0, 0))
        nr = net_received(s0, s1, q0, q1)
        if nr != 0:
            per_variant[(art, col, sz)][st] = nr

    moves: dict = {}
    store_net: dict = defaultdict(int)
    counts = {"transfer": 0, "supplier": 0, "return": 0}
    units = {"transfer": 0, "supplier": 0, "return": 0}
    for variant, sn in per_variant.items():
        cls = flow_class(sum(sn.values()))
        moved = sum(v for v in sn.values() if v > 0)  # units that arrived somewhere
        if cls == FLOW_TRANSFER:
            counts["transfer"] += 1
            units["transfer"] += moved
            moves[variant] = sn
            for st, v in sn.items():
                store_net[st] += v
        elif cls == FLOW_SUPPLIER:
            counts["supplier"] += 1
            units["supplier"] += sum(sn.values())
        else:
            counts["return"] += 1
            units["return"] += -sum(sn.values())

    return {"moves": moves, "store_net": dict(store_net), "counts": counts, "units": units}


def recommended_net(grid, min_velocity: float, min_run_units: int) -> dict:
    """The controller's recommended per (variant, store) net move on a begin-state grid (its significant set):
    {(article, color, size): {store: net (+recv / −send)}}. Shell over `build_plan`."""
    from .query.plan import build_plan
    from .query.regime import article_regimes

    plan = build_plan(grid, article_regimes(), min_velocity=min_velocity, min_run_units=min_run_units)
    rec: dict = defaultdict(dict)
    for t in plan.transfers:
        rec[t.variant][t.dest] = rec[t.variant].get(t.dest, 0) + t.qty
        rec[t.variant][t.source] = rec[t.variant].get(t.source, 0) - t.qty
    return {v: dict(sn) for v, sn in rec.items()}


def validate(begin_date, end_date, min_velocity, min_run_units, root=None, grid_dir=None) -> dict:
    """Back-run the controller on the begin-state and adjudicate against the operator's ACTUAL moves + what SOLD —
    the vibes-vs-signal test. Returns per-store direction agreement, item overlap, leg classification
    (`leg_agreement`), and the did-it-sell verdict (`move_verdict`) on their moves vs the store baseline. Shell.
    """
    from .lenses.inventory import load_grid

    a = load_snapshot(begin_date, root)
    b = load_snapshot(end_date, root)
    raw_net: dict = defaultdict(dict)
    span_sales: dict = defaultdict(dict)
    for k in set(a) | set(b):
        art, col, sz, st = k
        s0, q0 = a.get(k, (0, 0))
        s1, q1 = b.get(k, (0, 0))
        nr = net_received(s0, s1, q0, q1)
        if nr != 0:
            raw_net[(art, col, sz)][st] = nr
        if q1 - q0:
            span_sales[(art, col, sz)][st] = q1 - q0
    actual = {v: sn for v, sn in raw_net.items() if flow_class(sum(sn.values())) == FLOW_TRANSFER}

    grid = load_grid(grid_dir=grid_dir or _daily_dir(begin_date, root))
    rec = recommended_net(grid, min_velocity, min_run_units)

    legs = {AGREE_MATCH: 0, AGREE_OPPOSITE: 0, AGREE_MODEL_ONLY: 0, AGREE_OPERATOR_ONLY: 0}
    all_legs = {(v, st) for v, sn in rec.items() for st in sn} | {(v, st) for v, sn in actual.items() for st in sn}
    for v, st in all_legs:
        cls = leg_agreement(rec.get(v, {}).get(st, 0), actual.get(v, {}).get(st, 0))
        if cls in legs:  # pragma: no branch  (an all_legs pair is nonzero on ≥1 side, so cls is never AGREE_NONE)
            legs[cls] += 1

    def receives_sold(net_map):  # of a side's RECEIVE legs, did the item sell at the destination after?
        sold = {SELL_SOLD: 0, SELL_SAT: 0}
        for v, sn in net_map.items():
            for st, net in sn.items():
                vd = move_verdict(net, span_sales.get(v, {}).get(st, 0))
                if vd in sold:
                    sold[vd] += 1
        return sold

    operator_sold = receives_sold(actual)  # their EXECUTED receives
    model_sold = receives_sold(rec)  # the model's recommended receives (MOSTLY UNEXECUTED — dest-rate confounded)

    # execution-independent SELECTION quality: of the variants each side SELECTED, fraction that sold ANYWHERE
    var_net_sales: dict = defaultdict(int)
    for v, sn in span_sales.items():
        var_net_sales[v] = sum(sn.values())
    base_variants = {(art, col, sz) for (art, col, sz, st), (s1, _q1) in b.items() if s1 > 0}

    def sel_rate(variants):
        vs = list(variants)
        return round(sum(1 for v in vs if var_net_sales.get(v, 0) > 0) / len(vs), 4) if vs else 0.0

    def store_net(d):
        out: dict = defaultdict(int)
        for _v, sn in d.items():
            for st, n in sn.items():
                out[st] += n
        return out

    rs, as_ = store_net(rec), store_net(actual)
    dir_agree = sum(1 for st in set(rs) | set(as_) if (rs.get(st, 0) > 0) == (as_.get(st, 0) > 0))
    osold = operator_sold[SELL_SOLD] + operator_sold[SELL_SAT]
    msold = model_sold[SELL_SOLD] + model_sold[SELL_SAT]
    return {
        "begin": begin_date,
        "end": end_date,
        "gate": {"min_velocity": min_velocity, "min_run_units": min_run_units},
        "model_units": sum(max(0, n) for sn in rec.values() for n in sn.values()),
        "operator_units": sum(max(0, n) for sn in actual.values() for n in sn.values()),
        "overlap": {"model": len(rec), "operator": len(actual), "both": len(set(rec) & set(actual))},
        "legs": legs,
        "direction": {st: {"model": rs.get(st, 0), "operator": as_.get(st, 0)} for st in sorted(set(rs) | set(as_))},
        "dir_agree_stores": [dir_agree, len(set(rs) | set(as_))],
        "sell": {
            "operator_receives": operator_sold,
            "operator_dest_sold_rate": round(operator_sold[SELL_SOLD] / osold, 4) if osold else 0.0,
            "model_receives": model_sold,
            "model_dest_sold_rate": round(model_sold[SELL_SOLD] / msold, 4) if msold else 0.0,
            # the FAIR (execution-independent) comparison — did each side's SELECTED variants sell anywhere?
            "operator_selection_soldrate": sel_rate(actual),
            "model_selection_soldrate": sel_rate(rec),
            "baseline_selection_soldrate": sel_rate(base_variants),
        },
    }


def outcome_profile(begin_date, end_date, root=None, grid_dir=None, hi_threshold=20) -> dict:
    """Profile the controller's suggested moves for `begin_date` by the GAP each targets (`gap_severity`)
    and its realized OUTCOME by `end_date` (`move_outcome`) — the re-runnable validation that the routing
    covers real, live supply gaps. NOT 3-day sell-through (a window that short makes 'didn't sell' the
    calendar, not a miss). The per-store `dest_units` is the operator-vs-model concentration signal. I/O shell.
    """
    from .lenses.inventory import load_grid
    from .query.plan import build_plan
    from .query.regime import article_regimes

    grid = load_grid(grid_dir=grid_dir or _daily_dir(begin_date, root))
    moves = build_plan(grid, article_regimes()).transfers

    a = load_snapshot(begin_date, root)
    b = load_snapshot(end_date, root)
    span: dict = defaultdict(dict)
    net_span: dict = defaultdict(int)
    for k in set(a) | set(b):
        art, col, sz, st = k
        _s0, q0 = a.get(k, (0, 0))
        _s1, q1 = b.get(k, (0, 0))
        d = q1 - q0
        if d:
            span[(art, col, sz)][st] = d
            net_span[(art, col, sz)] += d
    window_vol: dict = defaultdict(int)
    for v, cells in grid.items():
        window_vol[v] = sum(c.sale_qty for c in cells.values())

    gaps: dict = defaultdict(int)
    outcomes: dict = defaultdict(int)
    model_dest: dict = defaultdict(int)
    for t in moves:
        c = grid.cell(t.variant, t.dest)
        gaps[gap_severity(c.stock if c else 0, c.recent_sales if c else 0)] += 1
        dest_sold = span.get(t.variant, {}).get(t.dest, 0)
        outcomes[move_outcome(dest_sold, net_span[t.variant], window_vol[t.variant], hi_threshold)] += 1
        model_dest[t.dest] += t.qty

    return {
        "begin": begin_date,
        "end": end_date,
        "moves": len(moves),
        "units": sum(t.qty for t in moves),
        "hi_threshold": hi_threshold,
        "gap_severity": dict(gaps),
        "outcome": dict(outcomes),
        "dest_units": dict(model_dest),
    }


def export_outcome_profile(begin_date, end_date, out_path, root=None, grid_dir=None, hi_threshold=20) -> dict:
    """Persist `outcome_profile` to JSON (the re-runnable gap-coverage validation). I/O shell."""
    prof = outcome_profile(begin_date, end_date, root=root, grid_dir=grid_dir, hi_threshold=hi_threshold)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(prof, fh, indent=2)
    return prof


def stock_management(begin_date, end_date, root=None) -> dict:
    """Store + warehouse STOCK-MOVEMENT statement over the interval, from the two dated snapshots via the
    stock-flow identity: per node — opening, inward, outward, sold, closing (they balance by construction),
    plus the conserved inter-store transfer tally (`reconstruct`). The professionals' "variance" is ≡ 0 here
    (a physical audit count is external data, not derivable from the snapshot arithmetic) and "pending
    transactions" need the transaction-detail pull — both surfaced as null with a note. Shell over `load_snapshot`
    / `net_received` / `reconstruct`."""
    a = load_snapshot(begin_date, root)
    b = load_snapshot(end_date, root)
    rows: dict = defaultdict(lambda: {"opening": 0, "inward": 0, "outward": 0, "sold": 0, "closing": 0})
    for k in set(a) | set(b):
        _art, _col, _sz, st = k
        s0, q0 = a.get(k, (0, 0))
        s1, q1 = b.get(k, (0, 0))
        r = rows[st]
        r["opening"] += s0
        r["closing"] += s1
        r["sold"] += max(0, q1 - q0)
        nr = net_received(s0, s1, q0, q1)
        if nr > 0:
            r["inward"] += nr
        elif nr < 0:
            r["outward"] += -nr

    rec = reconstruct(begin_date, end_date, root)
    xfer_in: dict = defaultdict(int)
    xfer_out: dict = defaultdict(int)
    for _v, sn in rec["moves"].items():  # conserved (pure inter-store) transfers only
        for st, net in sn.items():  # sn carries only nr != 0 legs (per_variant), so net is never 0 here
            if net > 0:
                xfer_in[st] += net
            else:
                xfer_out[st] += -net

    stores = []
    for st in sorted(rows, key=lambda s: -rows[s]["closing"]):
        r = rows[st]
        stores.append(
            {
                "store": st,
                "opening_units": r["opening"],
                "inward_units": r["inward"],  # ALL inflow (inter-store + supplier receipts)
                "outward_units": r["outward"],
                "transfer_in_units": xfer_in.get(st, 0),  # the conserved inter-store subset of inward
                "transfer_out_units": xfer_out.get(st, 0),
                "sold_units": r["sold"],
                # the residual of the identity closing = opening + inward − outward − sold: it equals the units
                # whose CUMULATIVE sales fell between snapshots — returns / voids / corrections (the real,
                # data-level "variance" the professionals asked for; a physical-audit variance is external).
                "returns_adjustments": r["closing"] - (r["opening"] + r["inward"] - r["outward"] - r["sold"]),
                "closing_units": r["closing"],
            }
        )
    return {
        "begin": begin_date,
        "end": end_date,
        "stores": stores,
        "variance_note": "returns_adjustments = units whose cumulative sales fell (returns/voids); a physical "
        "stock-audit variance would need an external count",
        "pending_note": "pending/uncleared transactions need the transaction-detail pull (not yet landed)",
    }


def export_stock_management(begin_date, end_date, out_path, root=None) -> dict:
    """Persist `stock_management` to JSON — the data floor for the stock-management report. I/O shell."""
    sm = stock_management(begin_date, end_date, root=root)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(sm, fh, indent=2)
    return sm


def calibrate_gate(grid, target_units: float, min_run_units: int = 2) -> float:
    """Find the `min_velocity` whose significance-gated flow on `grid` is closest to `target_units` (the
    operator's per-day move scale). Sweeps a coarse velocity ladder — the common-scale calibration. Shell."""
    from .query.significance import significant_moves
    from .route import COVER_DAYS_DEFAULT, plan_transfers_global

    raw, _ = plan_transfers_global(grid, COVER_DAYS_DEFAULT)
    best_mv, best_diff = 0.05, None
    for mv in (0.05, 0.03, 0.02, 0.014, 0.01, 0.007, 0.005, 0.003, 0.001):
        u = sum(t.qty for t in significant_moves(raw, grid, min_velocity=mv, min_run_units=min_run_units))
        diff = abs(u - target_units)
        if best_diff is None or diff < best_diff:
            best_mv, best_diff = mv, diff
    return best_mv


def export_validation(begin_date: str, end_date: str, out_path: str, root: str | None = None) -> dict:
    """Calibrate the model's gate to the operator's per-day move scale, back-run + adjudicate (`validate`), and
    write the dated validation JSON — the persistent oracle-vs-model comparison the operator runs frequently.
    Returns a compact summary. I/O."""
    from .lenses.inventory import load_grid

    r = reconstruct(begin_date, end_date, root)
    operator_units = sum(v for sn in r["moves"].values() for v in sn.values() if v > 0)
    days = max(1, (datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(begin_date)).days)
    grid_dir = _daily_dir(begin_date, root)
    mv = calibrate_gate(load_grid(grid_dir=grid_dir), operator_units / days)
    v = validate(begin_date, end_date, mv, 2, root=root, grid_dir=grid_dir)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(v, fh, ensure_ascii=False, indent=2)
    return {"gate": v["gate"], "dir_agree": v["dir_agree_stores"], "sell": v["sell"]}


def export_reconciliation(begin_date: str, end_date: str, out_path: str, root: str | None = None) -> dict:
    """Reconstruct + write the actual-moves reconciliation to JSON (the variant tuple-keys flattened to
    `article|color|size` strings for serialization). Returns the counts. I/O — the dated oracle file the
    validation report reads."""
    r = reconstruct(begin_date, end_date, root)
    doc = {
        "begin": begin_date,
        "end": end_date,
        "counts": r["counts"],
        "units": r["units"],
        "store_net": r["store_net"],
        "moves": {"|".join(v): sn for v, sn in r["moves"].items()},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return r["counts"]


def report() -> None:
    """CLI: `python -m peitho.reconcile <begin> <end>` — the actual-transfers reconstruction over two days."""
    import sys

    begin, end = (sys.argv[1], sys.argv[2]) if len(sys.argv) >= 3 else ("2026-08-16", "2026-08-19")
    r = reconstruct(begin, end)
    c, u = r["counts"], r["units"]
    print(f"Actual moves {begin} → {end}:")
    print(f"  pure inter-store TRANSFERS: {c['transfer']:,} variants · {u['transfer']:,} units")
    print(f"  supplier arrivals: {c['supplier']:,} variants (+{u['supplier']:,} units)")
    print(f"  returns/removals:  {c['return']:,} variants (−{u['return']:,} units)")
    print("  per-store net (+ receiver / − sender):")
    for st in sorted(r["store_net"], key=lambda s: r["store_net"][s]):
        print(f"     {st:>3}: {r['store_net'][st]:+d}")


if __name__ == "__main__":
    report()
