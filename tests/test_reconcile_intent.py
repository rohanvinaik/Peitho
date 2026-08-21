"""Hand-authored INTENT tests for peitho.reconcile — reconstructing the operator's actual inter-store transfers.
Pins the stock-flow identity, the conservation classifier, and the end-to-end reconstruction over a synthetic
two-snapshot fixture: a conserved move (N4→N8) is isolated as a transfer; a stock gain with no matching sender
is a supplier arrival."""

import json
import os

from peitho.reconcile import (
    AGREE_MATCH,
    AGREE_MODEL_ONLY,
    AGREE_NONE,
    AGREE_OPERATOR_ONLY,
    AGREE_OPPOSITE,
    FLOW_RETURN,
    FLOW_SUPPLIER,
    FLOW_TRANSFER,
    GAP_HARD,
    GAP_NONE,
    GAP_SOFT,
    OUT_ELSEWHERE,
    OUT_HIVOL_PENDING,
    OUT_NO_SIGNAL,
    OUT_REALIZED,
    OUT_SLOW_PENDING,
    SELL_NA,
    SELL_SAT,
    SELL_SOLD,
    flow_class,
    gap_severity,
    leg_agreement,
    move_outcome,
    move_verdict,
    net_received,
    outcome_profile,
    reconstruct,
    stock_management,
    validate,
)


def test_leg_agreement_classifies_model_vs_operator():
    assert leg_agreement(3, 5) == AGREE_MATCH  # both receive
    assert leg_agreement(-2, -4) == AGREE_MATCH  # both send
    assert leg_agreement(3, -4) == AGREE_OPPOSITE  # model says receive, the operator sent
    assert leg_agreement(3, 0) == AGREE_MODEL_ONLY  # model recommends, the operator made no move
    assert leg_agreement(0, -4) == AGREE_OPERATOR_ONLY  # the operator moved, model silent
    assert leg_agreement(0, 0) == AGREE_NONE


def test_move_verdict_did_it_sell():
    assert move_verdict(2, 5) == SELL_SOLD  # moved stock in, and it sold at the destination
    assert move_verdict(2, 0) == SELL_SAT  # moved in, sat unsold
    assert move_verdict(-2, 5) == SELL_NA  # a send, not a receive — nothing to judge
    assert move_verdict(0, 5) == SELL_NA


def test_gap_severity_grades_the_destination_shortfall():
    assert gap_severity(dest_stock=0, dest_recent=5) == GAP_HARD  # sold recently, now out — lost sale live
    assert gap_severity(dest_stock=3, dest_recent=5) == GAP_SOFT  # recent demand, below target but not out
    assert gap_severity(dest_stock=0, dest_recent=0) == GAP_NONE  # no recent demand → model shouldn't fire


def test_move_outcome_no_sale_is_not_a_miss_for_a_high_volume_mover():
    """The operator's own nuance: a high-volume item that didn't sell AT this dest in 3 days is coverage, not
    failure — its copies sold elsewhere prove the demand, and the window is far too short to turn most items."""
    assert move_outcome(dest_sold=2, net_sold=5, window_vol=40, hi_threshold=20) == OUT_REALIZED
    assert move_outcome(dest_sold=0, net_sold=5, window_vol=40, hi_threshold=20) == OUT_ELSEWHERE  # sold elsewhere
    assert move_outcome(dest_sold=0, net_sold=0, window_vol=40, hi_threshold=20) == OUT_HIVOL_PENDING  # NOT a miss
    assert move_outcome(dest_sold=0, net_sold=0, window_vol=5, hi_threshold=20) == OUT_SLOW_PENDING
    assert move_outcome(dest_sold=0, net_sold=0, window_vol=0, hi_threshold=20) == OUT_NO_SIGNAL  # scrutinize


def test_net_received_is_the_stock_flow_identity():
    assert net_received(10, 8, 100, 105) == 3  # stock −2, sales +5 → net received 3
    assert net_received(5, 5, 50, 50) == 0  # nothing moved, nothing sold
    assert net_received(5, 3, 20, 20) == -2  # stock dropped 2, no sales → net sent 2


def test_flow_class_by_network_conservation():
    assert flow_class(0) == FLOW_TRANSFER  # conserved → pure inter-store transfer
    assert flow_class(5) == FLOW_SUPPLIER  # net inflow → supplier arrival
    assert flow_class(-3) == FLOW_RETURN  # net outflow → return / removal


def _write(root, date, records):
    """records = {store: [(article, color, size, stock, sale), ...]}"""
    from peitho.source import adapter

    d = adapter().daily_grid_dir(date, root)  # write where the active cassette's adapter reads
    for st, rows in records.items():
        os.makedirs(d, exist_ok=True)
        recs = [{"article": a, "color": c, "size": s, "stock": k, "sale": q} for (a, c, s, k, q) in rows]
        with open(f"{d}/{st}.json", "w") as fh:
            json.dump({"rows": recs}, fh)


def test_reconstruct_isolates_a_conserved_transfer_from_a_supplier_arrival(tmp_path):
    root = str(tmp_path)
    # X: N3 5→3 (sent 2), N1 0→2 (received 2) — conserved TRANSFER. Y: N4 3→8, no sender — SUPPLIER arrival.
    _write(
        root,
        "2026-01-01",
        {"N3": [("X", "RED", "40", 5, 0)], "N1": [("X", "RED", "40", 0, 0)], "N4": [("Y", "BLU", "41", 3, 0)]},
    )
    _write(
        root,
        "2026-01-02",
        {"N3": [("X", "RED", "40", 3, 0)], "N1": [("X", "RED", "40", 2, 0)], "N4": [("Y", "BLU", "41", 8, 0)]},
    )
    r = reconstruct("2026-01-01", "2026-01-02", root=root)
    assert r["counts"]["transfer"] == 1 and r["units"]["transfer"] == 2
    assert r["counts"]["supplier"] == 1 and r["units"]["supplier"] == 5
    assert r["moves"][("X", "RED", "40")] == {"N3": -2, "N1": 2}  # the conserved move, per store
    assert r["store_net"] == {"N3": -2, "N1": 2}  # Y (supplier) excluded from the transfer tally


def _write_full(root, date, records):
    """records = {store: [(article, color, size, stock, sale, recent30), ...]} — includes the recent sales-age
    band the routing velocity reads, so the back-run shells run realistically."""
    from peitho.source import adapter

    d = adapter().daily_grid_dir(date, root)  # write where the active cassette's adapter reads
    for st, rows in records.items():
        os.makedirs(d, exist_ok=True)
        recs = [
            {"article": a, "color": c, "size": s, "stock": k, "sale": q, "recent30": r30}
            for (a, c, s, k, q, r30) in rows
        ]
        with open(f"{d}/{st}.json", "w") as fh:
            json.dump({"rows": recs}, fh)


def test_validate_and_outcome_profile_run_end_to_end(tmp_path):
    """The persistent back-run shells execute over synthetic snapshots — a fast mover short at a selling node
    (N8) with spare at the warehouse (WH). Characterizes the shape of validate() / outcome_profile()."""
    root = str(tmp_path)
    _write_full(root, "2026-02-01", {"N1": [("X", "RED", "40", 0, 5, 5)], "WH": [("X", "RED", "40", 10, 0, 0)]})
    _write_full(root, "2026-02-04", {"N1": [("X", "RED", "40", 0, 8, 5)], "WH": [("X", "RED", "40", 10, 0, 0)]})

    v = validate("2026-02-01", "2026-02-04", 0.03, 2, root=root)
    assert {"gate", "legs", "sell", "overlap", "direction"} <= set(v)
    assert {"operator_selection_soldrate", "model_selection_soldrate", "baseline_selection_soldrate"} <= set(v["sell"])

    p = outcome_profile("2026-02-01", "2026-02-04", root=root)
    assert p["moves"] >= 0 and {"gap_severity", "outcome", "dest_units"} <= set(p)


def test_stock_management_statement_balances_over_a_clean_transfer(tmp_path):
    """The stock-movement statement: a conserved N4→N8 transfer, no sales. Every node's identity closes
    (closing = opening + inward − outward − sold + returns) and the transfer is attributed both sides."""
    root = str(tmp_path)
    _write(root, "2026-03-01", {"N3": [("X", "RED", "40", 5, 0)], "N1": [("X", "RED", "40", 0, 0)]})
    _write(root, "2026-03-02", {"N3": [("X", "RED", "40", 3, 0)], "N1": [("X", "RED", "40", 2, 0)]})
    sm = stock_management("2026-03-01", "2026-03-02", root=root)
    by = {r["store"]: r for r in sm["stores"]}
    assert by["N3"]["outward_units"] == 2 and by["N3"]["transfer_out_units"] == 2
    assert by["N1"]["inward_units"] == 2 and by["N1"]["transfer_in_units"] == 2
    for r in sm["stores"]:
        assert r["returns_adjustments"] == 0
        assert r["closing_units"] == (
            r["opening_units"] + r["inward_units"] - r["outward_units"] - r["sold_units"] + r["returns_adjustments"]
        )


def test_reconstruct_nets_sales_before_calling_a_drop_a_send(tmp_path):
    root = str(tmp_path)
    # Z at N1: stock 10→4, but sold 6 (cumulative 20→26) → net_received = −6 + 6 = 0, NOT a send. No transfer.
    _write(root, "2026-01-01", {"N1": [("Z", "TAN", "42", 10, 20)]})
    _write(root, "2026-01-02", {"N1": [("Z", "TAN", "42", 4, 26)]})
    r = reconstruct("2026-01-01", "2026-01-02", root=root)
    assert r["moves"] == {} and r["store_net"] == {}  # the whole drop is explained by sales — no move
