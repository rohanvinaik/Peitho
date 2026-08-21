"""COMPUTE tests for peitho.lenses.inventory's shortage/baseline engine over a synthetic Grid — the demand-
weighted store baselines (the mined zero-mean), the live + graded shortage detection, and the taxonomy
reader. Pinned with min_cost={} so no spatial cost-matrix I/O is needed; the classification, cover, and
urgency decisions each run FOR REAL (they carry their own Detective suites; here we exercise the loops that
drive them over a whole grid). N8/N5 are RETAIL per the induced store-role map, so the stock-0/recent-demand
cell is a genuine LIVE_SHORTAGE.
"""

import peitho.lenses.inventory as inv
from peitho.grid import Cell, Grid


def _grid() -> Grid:
    return Grid(
        {
            ("A1", "BLK", "40"): {
                "N8": Cell("N8", stock=3, sale_qty=10, recent_sales=9, nrv=0.0),
                "N5": Cell("N5", stock=5, sale_qty=2, recent_sales=1, nrv=0.0),
            },
            # stock 0 at a RETAIL node with last-30d demand -> LIVE_SHORTAGE
            ("A1", "BLK", "41"): {"N8": Cell("N8", stock=0, sale_qty=4, recent_sales=4, nrv=0.0)},
        }
    )


def test_mine_store_baselines_is_demand_weighted_cover():
    bl = inv.mine_store_baselines(_grid())
    assert bl["N8"] == round(inv.WINDOW_DAYS * 3 / 10, 2)  # only the stock>0 & sold cell contributes
    assert bl["N5"] == round(inv.WINDOW_DAYS * 5 / 2, 2)


def test_find_live_shortages_catches_selling_stockout():
    shorts = inv.find_live_shortages(_grid(), min_cost={})
    assert any(s.store == "N8" and s.variant == ("A1", "BLK", "41") for s in shorts)


def test_find_graded_shortages_surfaces_cells_below_baseline():
    graded = inv.find_graded_shortages(_grid(), {"N8": 1000.0, "N5": 1000.0}, min_cost={}, min_urgency=0.4)
    assert graded and all(g.band in ("CRITICAL", "HIGH", "WATCH") for g in graded)
    assert all(g.priority >= 0 for g in graded)  # urgency × recent demand, ranked desc
    assert graded == sorted(graded, key=lambda g: -g.priority)


# load_article_sections now delegates to the cassette's private adapter; its parsing is oracle-covered.


def test_mine_category_baselines_keys_by_store_and_section():
    cb = inv.mine_category_baselines(_grid(), {"A1": "MENS"})
    assert ("N8", "MENS") in cb and cb[("N8", "MENS")] == round(inv.WINDOW_DAYS * 3 / 10, 2)
