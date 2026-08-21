"""Hand-authored INTENT test for peitho.query.rules — the dead-stock pull-back engine (CONTROL_ARCHITECTURE.md
§5). Pins the operator's dead-stock rules: an unsold (IDLE_STOCK) item at a satellite is pulled to the N8
cognition hub (R1); at the sale-or-return node it returns warehouse-ward (R2); already at the hub or the
warehouse it is HELD; a selling item fires nothing. The evaluator emits exactly one justified Action per
fireable cell.
"""

from peitho.grid import Cell, Grid
from peitho.query.rules import (
    HOLD,
    NONE,
    PULL_TRIAGE,
    RETURN,
    dead_stock_actions,
    stagnant_action,
)


def test_stagnant_action_routes_dead_stock_by_node_role():
    assert stagnant_action("IDLE_STOCK", is_sor=False, is_triage_hub=False, is_warehouse=False) == PULL_TRIAGE
    assert stagnant_action("IDLE_STOCK", is_sor=True, is_triage_hub=False, is_warehouse=False) == RETURN
    assert stagnant_action("IDLE_STOCK", is_sor=False, is_triage_hub=True, is_warehouse=False) == HOLD  # at N8
    assert stagnant_action("IDLE_STOCK", is_sor=False, is_triage_hub=False, is_warehouse=True) == HOLD  # at WH
    assert stagnant_action("STOCKED", is_sor=False, is_triage_hub=False, is_warehouse=False) == NONE  # selling


def test_sor_return_beats_triage_when_both():
    # a node that were both SoR and the hub -> the SoR return rule wins (precedence).
    assert stagnant_action("IDLE_STOCK", is_sor=True, is_triage_hub=True, is_warehouse=False) == RETURN


def test_evaluator_emits_one_justified_action_per_dead_cell():
    # over the active cassette's network (example): N4=store, N3=SoR, N2=SELL, N1=TRIAGE hub. The PULL_TRIAGE
    # / RETURN destinations are the network's TRIAGE hub and WAREHOUSE, resolved from the cassette.
    from peitho.query.rules import RETURN_WAREHOUSE, TRIAGE_HUB

    v = ("ART1", "RED", "40")
    grid = Grid(
        {
            v: {
                "N4": Cell("N4", stock=3, sale_qty=0, recent_sales=0, nrv=0.0),  # idle at a store -> R1
                "N3": Cell("N3", stock=2, sale_qty=0, recent_sales=0, nrv=0.0),  # idle at SoR -> R2
                "N2": Cell("N2", stock=5, sale_qty=9, recent_sales=4, nrv=1.0),  # selling -> nothing
                "N1": Cell("N1", stock=1, sale_qty=0, recent_sales=0, nrv=0.0),  # idle at the hub -> HELD
            }
        }
    )
    by = {a.src: a for a in dead_stock_actions(grid)}
    assert set(by) == {"N4", "N3"}  # only the two movable dead cells emit
    assert by["N4"].kind == PULL_TRIAGE and by["N4"].dst == TRIAGE_HUB and by["N4"].qty == 3 and by["N4"].rule == "R1"
    assert by["N3"].kind == RETURN and by["N3"].dst == RETURN_WAREHOUSE and by["N3"].qty == 2 and by["N3"].rule == "R2"
