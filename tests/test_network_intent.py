"""Hand-authored INTENT test for peitho.network — the data-induced, role-typed node network.

Pins the AGREED behaviour of the signed-ternary role induction (a zero-sales node is a WAREHOUSE source,
a selling node is a RETAIL sink; the mined zero is the median of the sellers), node birth/death (an absent
node is simply absent from the induced map), and the NetworkState role accessors. The Detective synth
suites pin the pure numeric decisions mutation-complete; this file pins the intent behind them.
"""

from peitho.network import (
    NetworkState,
    coarse_role,
    induce_coarse_roles,
    mine_sales_zero,
    sells_position,
)


def test_sells_position_signed_ternary_off_the_mined_zero():
    assert sells_position(0.0, 10.0, floor=0.0) == -1  # sells nothing → a source (warehouse)
    assert sells_position(-3.0, 10.0, floor=0.0) == -1  # a correction/return, still ≤ floor → source
    assert sells_position(5.0, 10.0, floor=0.0) == 0  # sells, but below the typical node → ordinary
    assert sells_position(20.0, 10.0, floor=0.0) == 1  # sells well above the mined typical → a sink


def test_mine_sales_zero_is_the_median_of_sellers_only():
    assert mine_sales_zero({}) == 0.0  # nothing sells → no zero
    assert mine_sales_zero({"w": 0}) == 0.0  # a lone non-seller → still no zero
    assert mine_sales_zero({"a": 10}) == 10.0  # one seller
    assert mine_sales_zero({"a": 10, "b": 20}) == 15.0  # even → mean of the two middles
    assert mine_sales_zero({"a": 10, "b": 20, "c": 30}) == 20.0  # odd → the middle
    assert mine_sales_zero({"a": -5, "b": 10}) == 10.0  # negatives (returns) are not sellers → excluded


def test_coarse_role_source_vs_sink():
    assert coarse_role(0.0, 10.0, floor=0.0) == "WAREHOUSE"  # ≤ floor → source
    assert coarse_role(5.0, 10.0, floor=0.0) == "RETAIL"  # sells → sink
    assert coarse_role(20.0, 10.0, floor=0.0) == "RETAIL"  # a top seller is still a RETAIL sink (coarse)


def test_induce_coarse_roles_and_node_birth_death():
    # one warehouse (sells nothing) + three selling nodes → warehouse is the source, the rest are sinks
    roles = induce_coarse_roles({"WH": 0, "A": 30, "B": 17, "C": 5})
    assert roles == {"WH": "WAREHOUSE", "A": "RETAIL", "B": "RETAIL", "C": "RETAIL"}
    # node DEATH: a node absent from the data is absent from the induced map (never fabricated as live)
    assert "GONE" not in induce_coarse_roles({"A": 30})
    # node BIRTH: a new node that appears with sales is induced RETAIL with no code change
    assert induce_coarse_roles({"A": 30, "NEW": 4})["NEW"] == "RETAIL"


def test_networkstate_role_accessors():
    ns = NetworkState(
        nodes=("WH", "N1", "N2", "N3"),
        roles={
            "WH": frozenset({"WAREHOUSE"}),
            "N1": frozenset({"SELL", "TRIAGE"}),
            "N2": frozenset({"SELL"}),
            "N3": frozenset({"SOR"}),
        },
    )
    assert ns.warehouse_nodes() == frozenset({"WH"})
    assert ns.retail_nodes() == frozenset({"N1", "N2", "N3"})  # every non-warehouse roster node
    assert ns.role_set("SELL") == frozenset({"N1", "N2"})
    assert ns.role_set("TRIAGE") == frozenset({"N1"})
    assert ns.role_set("SOR") == frozenset({"N3"})
