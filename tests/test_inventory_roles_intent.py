"""Hand-authored INTENT test for the grid-INDUCED coarse role model in peitho.lenses.inventory.

Pins that node roles are read off the DATA, not a declared list: store_sales projects per-store sales,
coarse_roles induces RETAIL/WAREHOUSE from it (a zero-sales node holding stock is the warehouse source),
and node_role reads that map — UNKNOWN for a store the data does not contain (node death).
"""

from peitho.grid import Cell, Grid
from peitho.lenses.inventory import coarse_roles, node_role, store_sales


def _grid():
    # two variants across a warehouse (WH: holds stock, sells nothing) and two selling stores
    return Grid(
        {
            ("ART", "RED", "40"): {
                "WH": Cell("WH", stock=50, sale_qty=0, recent_sales=0, nrv=0.0),
                "S1": Cell("S1", stock=2, sale_qty=9, recent_sales=5, nrv=100.0),
                "S2": Cell("S2", stock=0, sale_qty=4, recent_sales=1, nrv=40.0),
            },
            ("ART", "RED", "41"): {
                "WH": Cell("WH", stock=30, sale_qty=0, recent_sales=0, nrv=0.0),
                "S1": Cell("S1", stock=1, sale_qty=6, recent_sales=3, nrv=60.0),
            },
        }
    )


def test_store_sales_sums_window_sales_per_store():
    assert store_sales(_grid()) == {"WH": 0, "S1": 15, "S2": 4}  # 9+6 for S1; WH never sells


def test_coarse_roles_induces_warehouse_from_zero_sales():
    roles = coarse_roles(_grid())
    assert roles["WH"] == "WAREHOUSE"  # holds stock, sells nothing → the source
    assert roles["S1"] == "RETAIL"
    assert roles["S2"] == "RETAIL"


def test_node_role_reads_the_induced_map_and_deaths_are_unknown():
    coarse = coarse_roles(_grid())
    assert node_role("WH", coarse) == "WAREHOUSE"
    assert node_role("S1", coarse) == "RETAIL"
    assert node_role("GONE", coarse) == "UNKNOWN"  # a store absent from the data → node death
