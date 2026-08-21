"""Hand-authored INTENT tests for peitho.query.significance — the controller's noise-removal stage.
Pins the classical decisions from intent: opposing flows net out (no cross-cycling), a per-move velocity gate
keeps only items the destination sells fast enough to be worth a trip, and a per-run gate drops trips too thin
to justify the drive — resolving the flow's raw flood into the sparse, significant set.
"""

from peitho.grid import Cell, Grid
from peitho.query.significance import (
    MOVE_DROP_SLOW,
    MOVE_KEEP,
    RUN_DROP_THIN,
    RUN_KEEP,
    move_verdict,
    net_transfers,
    run_verdict,
    significant_moves,
)
from peitho.route import Transfer

_V = ("X", "RED", "40")


def test_move_verdict_velocity_gate():
    assert move_verdict(0.10, 0.05) == MOVE_KEEP  # sells fast enough → worth covering
    assert move_verdict(0.05, 0.05) == MOVE_KEEP  # at the threshold → kept
    assert move_verdict(0.01, 0.05) == MOVE_DROP_SLOW  # ultra-slow tail → accepted stockout


def test_run_verdict_units_gate():
    assert run_verdict(3, 3) == RUN_KEEP  # at the threshold → worth the drive
    assert run_verdict(2, 3) == RUN_DROP_THIN  # a straggler → not worth a trip


def test_net_transfers_cancels_opposing_flows_to_the_remainder():
    # A→B 5 and B→A 2 → net 3 in the dominant A→B direction
    out = net_transfers([Transfer(_V, "B", "A", 5, 1.0), Transfer(_V, "A", "B", 2, 1.0)])
    assert len(out) == 1
    assert (out[0].source, out[0].dest, out[0].qty) == ("A", "B", 3)


def test_net_transfers_full_cancel_drops_and_passthrough_otherwise():
    assert net_transfers([Transfer(_V, "B", "A", 3, 1.0), Transfer(_V, "A", "B", 3, 1.0)]) == []  # cancel
    solo = net_transfers([Transfer(_V, "B", "A", 5, 1.0)])
    assert len(solo) == 1 and solo[0].qty == 5  # no opposing flow → unchanged


def test_significant_moves_drops_slow_items_keeps_fast():
    grid = Grid(
        {
            ("FAST", "R", "40"): {
                "N8": Cell("N8", stock=0, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0))
            },  # ~0.067/d recency
            ("SLOW", "R", "40"): {
                "N8": Cell("N8", stock=0, sale_qty=1, recent_sales=1, nrv=1.0, sls_age=(1, 0, 0, 0, 0))
            },  # ~0.013/d
        }
    )
    transfers = [
        Transfer(("FAST", "R", "40"), "N8", "N3", 4, 1.0),
        Transfer(("SLOW", "R", "40"), "N8", "N3", 4, 1.0),
    ]
    out = significant_moves(transfers, grid, min_velocity=0.05, min_run_units=3)
    assert [t.variant[0] for t in out] == ["FAST"]  # the slow item's cover falls out at the velocity gate


def test_significant_moves_drops_a_thin_run():
    grid = Grid({("FAST", "R", "40"): {"N8": Cell("N8", stock=0, sale_qty=10, recent_sales=5, nrv=1.0)}})
    transfers = [Transfer(("FAST", "R", "40"), "N8", "N3", 1, 1.0)]  # fast item, but only 1 unit on the trip
    assert significant_moves(transfers, grid, min_velocity=0.05, min_run_units=3) == []  # run too thin
