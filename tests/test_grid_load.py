"""INTEGRATION test for peitho.grid + the example data-input adapter — the per-store grid the lenses sit on.

The backend file-parsing now lives in a company cassette's PRIVATE adapter (it is exercised end-to-end by
the behavior oracle, not the public suite). The bundled example cassette ships a PROCEDURAL synthetic
adapter; this pins its deterministic shape, the `stores` filter, and the pure Grid selectors.
"""

from peitho.grid import Cell, Grid
from peitho.source import load_grid


def test_example_adapter_grid_shape():
    g = load_grid()  # active example cassette -> procedural synthetic grid (no files)
    assert isinstance(g, Grid)
    variants = list(g.variants())
    assert len(variants) == 48  # 8 articles x 2 colors x 3 sizes
    # WH is the warehouse: holds stock, never sells (so the role induction reads it as the source)
    assert sum(g.cell(v, "WH").sale_qty for v in variants if "WH" in g.cells_for(v)) == 0
    # the satellites do sell
    assert sum(g.cell(v, "N1").sale_qty for v in variants if "N1" in g.cells_for(v)) > 0


def test_example_adapter_stores_filter():
    g = load_grid(stores=["WH", "N1"])
    assert {s for v in g.variants() for s in g.cells_for(v)} == {"WH", "N1"}


def test_grid_selectors_over_a_hand_built_grid():
    # the Grid abstraction is pure/public — pin its selectors independent of any adapter
    g = Grid({("A1", "BLK", "40"): {"N8": Cell("N8", stock=5, sale_qty=3, recent_sales=2, nrv=1000.0, cogs=600.0)}})
    assert len(g) == 1
    c = g.cell(("A1", "BLK", "40"), "N8")
    assert c.stock == 5 and c.sale_qty == 3 and c.recent_sales == 2 and c.cogs == 600.0
    assert list(g.variants()) == [("A1", "BLK", "40")]
