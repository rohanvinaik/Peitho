"""Hand-authored INTENT test for peitho.query.edges — the typed edge admissibility (CONTROL_ARCHITECTURE.md
§3.2). Pins the operator's routing rules at the store level over the active cassette's network (the bundled
example: WH=warehouse, N1=SELL+TRIAGE flagship, N2=SELL, N3=SOR, N4=STORE): warehouses are one-way OUT (a
top-up to a satellite), dead stock goes to the TRIAGE hub, good stock goes to a throughput node, the
warehouse-return edge opens only past the no-sale threshold, and everything else is blocked — with the
flagship's dual SELL/TRIAGE role disambiguated by whether the item is stagnant.
"""

from peitho.query import edges as e


def test_roles_flagship_is_both_sell_and_triage():
    assert e.roles_of("N1") == frozenset({"SELL", "TRIAGE"})  # the flagship carries two roles
    assert e.roles_of("WH") == frozenset({"WAREHOUSE"})
    assert e.roles_of("N3") == frozenset({"SOR"})
    assert e.roles_of("N4") == frozenset({"STORE"})
    assert e.roles_of("ZZ") == frozenset()  # unknown store -> no roles


def test_warehouse_is_one_way_out():
    assert e.edge_kind("WH", "N4") == e.TOPUP  # warehouse -> satellite store = a top-up (R3-B1)
    assert e.edge_kind("WH", "N1") == e.WH_OUT  # warehouse -> sell node = plain out


def test_dead_stock_to_the_hub_good_stock_to_a_seller():
    assert e.edge_kind("N3", "N1", stagnant=True) == e.TO_TRIAGE  # dead -> the triage hub to sort (R1)
    assert e.edge_kind("N3", "N1", stagnant=False) == e.TO_SELL  # same dest, live stock -> a seller
    assert e.edge_kind("N3", "N2") == e.TO_SELL  # good stock -> throughput node (R3)


def test_return_edge_opens_only_past_the_threshold():
    assert e.edge_kind("N3", "WH", past_return=True) == e.RETURN  # SoR return after no-sale (R2/R7)
    assert e.edge_kind("N3", "WH", past_return=False) == e.BLOCKED  # closed until the threshold


def test_plain_store_to_store_is_blocked():
    assert e.edge_kind("N4", "N3") == e.BLOCKED  # store -> plain store, not toward a SELL node
