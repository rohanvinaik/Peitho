"""Hand-authored INTENT test for peitho.route.plan_transfers_global — the globally-optimal routing pass
(CONTROL_ARCHITECTURE.md §6). Pins the two things the greedy got wrong: source capacity is respected (no
over-allocation across competing sinks), and the operator's admissibility policy is applied (a satellite
restocks from the warehouse only, never from another store; store spare flows only toward a SELL node).
The min-cost-flow OPTIMALITY itself is pinned in test_flow_intent.py; this pins the composition.
"""

from peitho.grid import Cell, Grid
from peitho.route import plan_transfers_global


def _grid(cells_by_store):
    v = ("ART", "RED", "40")
    return Grid({v: {s: Cell(s, **kw) for s, kw in cells_by_store.items()}})


def test_source_capacity_respected_across_competing_sinks():
    # WH warehouse has 3 spare; N1 and N2 each need 2 -> the greedy would ship 4, the flow caps at 3.
    g = _grid(
        {
            "WH": dict(stock=3, sale_qty=0, recent_sales=0, nrv=0.0),  # spare 3 (velocity 0 -> target 0)
            "N1": dict(stock=0, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0)),  # deficit 2 (SELL)
            "N2": dict(stock=0, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0)),  # deficit 2 (SELL)
        }
    )
    transfers, reorders = plan_transfers_global(g, 30.0, min_cost={("WH", "N1"): 5, ("WH", "N2"): 5})
    assert sum(t.qty for t in transfers) == 3  # WH's 3 spare, never 4 (the over-allocation bug)
    assert sum(r.qty for r in reorders) == 1  # 4 needed − 3 shipped = 1 unmet -> a reorder


def test_satellite_restocks_from_warehouse_not_from_a_store():
    # N4 (a plain STORE) has spare; N5 (a plain STORE) is short. store->store is BLOCKED -> N5 reorders,
    # even with N4's spare right there. Only the warehouse may restock a satellite (R3-B1).
    g = _grid(
        {
            "N4": dict(stock=5, sale_qty=0, recent_sales=0, nrv=0.0),  # spare 5 (STORE)
            "N5": dict(
                stock=0, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0)
            ),  # deficit 2 (STORE, a satellite)
        }
    )
    transfers, reorders = plan_transfers_global(g, 30.0, min_cost={("N4", "N5"): 5})
    assert transfers == []  # N4->N5 is BLOCKED (store->store, dst not a SELL node)
    assert sum(r.qty for r in reorders) == 2  # N5's whole deficit reorders


def test_store_spare_flows_to_a_sell_node():
    # A store's spare CAN reallocate toward a throughput SELL node (TO_SELL) — that edge is admissible.
    g = _grid(
        {
            "N4": dict(stock=5, sale_qty=0, recent_sales=0, nrv=0.0),  # spare 5 (STORE)
            "N1": dict(stock=0, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0)),  # deficit 2 (SELL)
        }
    )
    transfers, reorders = plan_transfers_global(g, 30.0, min_cost={("N4", "N1"): 5})
    assert sum(t.qty for t in transfers) == 2  # N4->N1 is TO_SELL, admissible
    assert reorders == []


def test_ignores_non_supply_non_demand_cells_and_uncosted_admissible_arcs():
    # WH warehouse with no stock (no spare, not a sink), a store exactly at target (no deficit), and a
    # store->SELL pair that IS admissible but has no known travel cost -> not routed; the deficit reorders.
    g = _grid(
        {
            "WH": dict(stock=0, sale_qty=0, recent_sales=0, nrv=0.0),  # warehouse, no spare, no demand
            "N5": dict(
                stock=2, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0)
            ),  # STORE exactly at target -> no deficit
            "N4": dict(stock=50, sale_qty=0, recent_sales=0, nrv=0.0),  # a spare source (STORE)
            "N1": dict(stock=0, sale_qty=5, recent_sales=5, nrv=1.0, sls_age=(5, 0, 0, 0, 0)),  # SELL, deficit 2
        }
    )
    transfers, reorders = plan_transfers_global(g, 30.0, min_cost={})  # admissible arcs are uncosted
    assert transfers == []  # N4->N1 admissible (TO_SELL) but no cost known -> skipped, not routed
    assert sum(r.qty for r in reorders) == 2  # N1's deficit becomes a reorder
