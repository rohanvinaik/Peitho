"""INTEGRATION tests for the remaining lens I/O leaves + the routing plan branches — all path/param-driven,
so pinned over real tmp files or synthetic Grids. supplier purchase aggregation + the clearance article->supplier
edge; price article-age vintage (date-parse) + the demand-weighted markdown baseline; and plan_transfers
actually moving spare between stores AND flagging the uncoverable deficit as a supplier reorder.
"""

import peitho.lenses.inventory as inv
import peitho.lenses.price as price
import peitho.lenses.supplier as sup
from peitho.grid import Cell, Grid
from peitho.route import batch_transfers, plan_transfers


def test_find_live_shortages_default_min_cost_path():
    # no min_cost arg -> the _default_min_cost() I/O path (spatial placeholder when no matrix landed)
    grid = Grid({("A2", "RED", "38"): {"N8": Cell("N8", 0, 4, 4, 0.0)}})
    shorts = inv.find_live_shortages(grid)
    assert any(s.store == "N8" for s in shorts)


def test_store_clearance_empty_grid_is_empty():
    assert price.store_clearance(Grid({})) == []  # no sold cells -> no baselines -> no clearance rows


# The backend supplier-report readers (load_supplier_purchases / load_article_supplier) now live in the
# cassette's private adapter; their parsing is via the public source.parse_report_table (pinned in
# test_source_intent + test_supplier_intent) and exercised end-to-end by the behavior oracle.


def test_rank_suppliers_left_unsold_band():
    agg = {
        "ACME": {"sold": 160.0, "purchased": 200.0, "stock": 40.0, "profit": 5000.0},
        "GONE": {"sold": 0.0, "purchased": 300.0, "stock": 0.0, "profit": 0.0},  # 0 sold & 0 left
    }
    ranked = sup.rank_suppliers(agg, min_purchased=100.0)
    bands = {s.supplier: s.band for s in ranked}
    assert bands["GONE"] == "LEFT_UNSOLD"  # exited without a sale, not sitting as DEAD_STOCK


# load_article_ages now delegates to the cassette's private adapter (backend receipt-date parsing);
# it is exercised end-to-end by the behavior oracle, not the public suite.


def test_mine_store_discount_baselines_demand_weighted():
    grid = Grid(
        {
            ("A1", "BLK", "40"): {"N8": Cell("N8", 3, 10, 9, 9000.0, discount_amount=1000.0)},
            ("A2", "RED", "38"): {"N8": Cell("N8", 0, 0, 0, 0.0, discount_amount=500.0)},  # unsold -> excluded
        }
    )
    bl = price.mine_store_discount_baselines(grid)
    assert bl["N8"] == round(1000.0 / (9000.0 + 1000.0) * 100, 2)  # only the sold cell counts


def test_plan_transfers_moves_spare_and_flags_reorder():
    grid = Grid(
        {
            # N8 out & selling; N5 holds spare of the SAME variant -> a store->store transfer
            ("A1", "BLK", "40"): {"N8": Cell("N8", 0, 5, 5, 0.0), "N5": Cell("N5", 50, 1, 1, 0.0)},
            # N8 out & selling, nowhere holds spare -> a supplier reorder (unmet deficit)
            ("A2", "RED", "38"): {"N8": Cell("N8", 0, 5, 5, 0.0)},
        }
    )
    transfers, reorders = plan_transfers(grid, 30.0, min_cost={("N5", "N8"): 12.0})
    assert any(t.source == "N5" and t.dest == "N8" for t in transfers)
    assert any(r.store == "N8" and r.variant == ("A2", "RED", "38") for r in reorders)
    batches = batch_transfers(transfers)
    assert batches and batches[0].units >= 1
