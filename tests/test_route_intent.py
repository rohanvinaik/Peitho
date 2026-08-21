"""Hand-authored INTENT test for peitho.route — the supplier-reorder signal.

Pins that plan_transfers surfaces the UNMET deficit (what the network can't cover from internal spare) as
the supplier-reorder recommendation, rather than dropping it.
"""

from peitho.grid import Cell
from peitho.route import (
    MFR_DROP_ONEOFF,
    MFR_KEEP,
    SUPPLIER_HOLD,
    SUPPLIER_ORDER,
    manufacturer_significant,
    plan_transfers,
    reorder_priority,
    supplier_worth_ordering,
)


def test_supplier_basket_floor_holds_thin_baskets():
    """A manufacturer order carries fixed overhead, so a supplier needs >= a few significant items to be worth
    placing one: >= the floor ORDERs; below it HOLDs (a real gap, not yet worth a call)."""
    assert supplier_worth_ordering(3, min_items=3) == SUPPLIER_ORDER  # exactly the floor → worth it
    assert supplier_worth_ordering(5, min_items=3) == SUPPLIER_ORDER
    assert supplier_worth_ordering(2, min_items=3) == SUPPLIER_HOLD  # a thin basket → held
    assert supplier_worth_ordering(1, min_items=3) == SUPPLIER_HOLD  # a lone item never justifies an order


def test_reorder_priority_ranks_by_lost_sales_rate():
    """The manufacturer-order signal ranks the unmet (reachable-vs-naive differential) by the lost-sales RATE
    it represents — unmet × momentum. A big shortage of a fast mover outranks a bigger shortage of a slow one."""
    assert reorder_priority(9, 1.1) > reorder_priority(11, 0.2)  # fast-mover shortage first, despite fewer units
    assert reorder_priority(0, 1.1) == 0.0  # nothing unmet → no order
    assert reorder_priority(5, 0.0) == 0.0  # no recent demand → not urgent


def test_manufacturer_significant_drops_the_one_off_noise_tail():
    """Comprehensive above a baseline: a gap short at ≥2 stores is SYSTEMIC (kept even if slow); a single-store
    fast mover is kept; a single slow item at one store is the one-off tail (~81%) and drops out."""
    assert manufacturer_significant(3, 0.02, 2, 0.05) == MFR_KEEP  # systemic across 3 stores, even though slow
    assert manufacturer_significant(1, 0.10, 2, 0.05) == MFR_KEEP  # one store, but a fast mover
    assert manufacturer_significant(1, 0.02, 2, 0.05) == MFR_DROP_ONEOFF  # one slow item, one store → noise
    assert manufacturer_significant(2, 0.0, 2, 0.05) == MFR_KEEP  # exactly the systemic threshold


def test_plan_transfers_surfaces_supplier_reorders_when_no_spare():
    # a single retail store short of target, with NO other node holding spare -> the deficit can't be
    # transferred internally, so it must surface as a supplier reorder (not vanish).
    grid = {("ART-1", "BLACK", "40"): {"N8": Cell("N8", stock=0, sale_qty=100, recent_sales=10, nrv=1000.0)}}
    transfers, reorders = plan_transfers(grid, target_cover_days=30.0, min_cost={})
    assert transfers == []  # nothing to move — no node has spare
    assert len(reorders) == 1  # the unmet deficit becomes the supplier signal
    assert reorders[0].store == "N8"
    assert reorders[0].qty > 0
    assert reorders[0].variant == ("ART-1", "BLACK", "40")


def test_greedy_fills_from_spare_using_default_cost_matrix():
    # omit min_cost -> exercises the default OSRM/placeholder cost matrix; a spare store fills a short store,
    # and a source holding NO spare is never offered.
    grid = {
        ("A", "RED", "40"): {
            "N8": Cell("N8", stock=0, sale_qty=9, recent_sales=5, nrv=1.0),  # short (RETAIL sink)
            "N3": Cell("N3", stock=50, sale_qty=0, recent_sales=0, nrv=0.0),  # spare source
            "N1": Cell("N1", stock=0, sale_qty=0, recent_sales=0, nrv=0.0),  # no spare, no demand -> skipped
        }
    }
    transfers, _ = plan_transfers(grid, target_cover_days=30.0)  # default min_cost
    assert sum(t.qty for t in transfers) > 0  # N3's spare covers N8's deficit
    assert all(t.source == "N3" for t in transfers)  # N1 (no spare) is never a source


def test_greedy_skips_non_selling_and_no_recent_demand_cells():
    # a warehouse cell (zero window sales -> INDUCED WAREHOUSE, not a RETAIL sink) and a retail cell with no
    # recent demand are both skipped as sinks. node_role is induced from the grid: a node that never sells is
    # the warehouse source, so the warehouse case necessarily carries zero sales.
    grid = {
        ("A", "RED", "40"): {
            "WH": Cell("WH", stock=0, sale_qty=0, recent_sales=0, nrv=1.0),  # zero sales -> WAREHOUSE, not a sink
            "N2": Cell("N2", stock=0, sale_qty=100, recent_sales=0, nrv=1.0),  # retail but no recent demand
        }
    }
    transfers, reorders = plan_transfers(grid, target_cover_days=30.0, min_cost={})
    assert transfers == [] and reorders == []  # neither cell qualifies as a shortage sink


def test_greedy_shares_a_finite_source_across_competing_sinks():
    # REGRESSION: two retail stores short of the SAME variant must not both be filled from a source's full
    # spare — the spare is a finite per-variant pool. Before the fix, N3's 5 spare was recomputed per-sink
    # and offered whole to each (told to ship 10), and the covered-twice deficit never surfaced as a reorder.
    grid = {
        ("A", "BLK", "M"): {
            # sale_qty 20 over the default window -> target round(20/120*30)=5, stock 0 -> each store needs 5
            "N8": Cell("N8", stock=0, sale_qty=20, recent_sales=5, nrv=1.0),
            "N5": Cell("N5", stock=0, sale_qty=20, recent_sales=5, nrv=1.0),
            "N3": Cell("N3", stock=5, sale_qty=0, recent_sales=0, nrv=0.0),  # the ONLY source: exactly 5 spare
        }
    }
    transfers, reorders = plan_transfers(
        grid, target_cover_days=30.0, min_cost={("N3", "N8"): 10.0, ("N3", "N5"): 12.0}
    )
    assert sum(t.qty for t in transfers if t.source == "N3") == 5  # never 10 — a source can't over-ship its spare
    assert sum(r.qty for r in reorders) == 5  # the deficit N3 can't cover surfaces honestly as a reorder
