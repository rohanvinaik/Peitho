"""Hand-authored INTENT test for peitho.resolve — the resolving layer POC (routing), from intent.

Pins the two interfaces. Interface 1 (traversal): a demand-live deficit with reachable surplus resolves to
ROUTE (a transfer); an isolated one resolves to ORDER (a reorder); each cell carries its position signature.
Interface 2 (the position gate): ROUTE is always kept; a fading, non-core, isolated ORDER drops; the core /
base-inventory escape hatch protects a fading core item from the drop. (Real spatial network; PEITHO_ROOT.)
"""

from peitho.grid import Cell, Grid
from peitho.resolve import DROP, KEEP, ORDER, ROUTE, ResolvedSignal, gate, resolve_routing


def _cell(store, stock, sale_qty):
    return Cell(
        store=store, stock=stock, sale_qty=sale_qty, recent_sales=sale_qty, nrv=1000.0, sls_age=(sale_qty, 0, 0, 0, 0)
    )


# signatures are 4-tuples (INVENTORY, PRICE, SPATIAL, VELOCITY); VELOCITY -1 = fading
_FADING = (-1, 0, 0, -1)
_LIVE = (-1, 0, 0, 1)


def test_gate_keeps_route_drops_fading_order_and_honours_the_core_escape_hatch():
    assert gate(ROUTE, _FADING, is_core=False) == KEEP  # moving existing stock is cheap+reversible → always kept
    assert gate(ORDER, _FADING, is_core=False) == DROP  # fading, non-core reorder → not a live decision
    assert gate(ORDER, _FADING, is_core=True) == KEEP  # CORE / base inventory → the escape hatch protects it
    assert gate(ORDER, _LIVE, is_core=False) == KEEP  # an accelerating reorder is live → kept
    assert gate(ORDER, None, is_core=False) == KEEP  # no signature to assess → conservative keep


def test_resolve_routing_routes_a_reachable_deficit_and_carries_the_signature():
    # N1 sells and is stocked out (a demand-live deficit); WH (warehouse) holds surplus reachable to N1
    grid = Grid(
        {("A1", "BLK", "38"): {"N1": _cell("N1", stock=0, sale_qty=40), "WH": _cell("WH", stock=500, sale_qty=0)}}
    )
    resolved = resolve_routing(grid, regimes={})  # no core items in this fixture
    assert resolved and all(isinstance(r, ResolvedSignal) for r in resolved)
    sink = [r for r in resolved if r.store == "N1"]
    assert sink, "the reachable deficit at N1 must be resolved"
    r = sink[0]
    assert r.action == ROUTE  # reachable surplus → the traversal resolves it to a transfer
    assert r.variant == ("A1", "BLK", "38") and r.qty > 0
    assert r.signature is not None and len(r.signature) == 4  # carries the geometry's granular position read


def test_resolve_routing_orders_an_isolated_live_deficit():
    # a demand-live, not-fading deficit with NO surplus anywhere → the traversal finds no route → ORDER, kept
    grid = Grid({("Z9", "TAN", "40"): {"N1": _cell("N1", stock=0, sale_qty=30)}})
    resolved = resolve_routing(grid, regimes={})
    assert resolved and all(r.action == ORDER for r in resolved)  # nothing reachable → all resolve to ORDER
