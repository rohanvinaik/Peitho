"""peitho.grid — the shared data abstraction over the per-store variant grid.

SICP means-of-abstraction: ONE representation of the authoritative per-store × variant grid — the `Cell`
value and the `Grid` selectors (`variants / cells_for / cell / items / values`), so the lenses are CLIENTS
of the grid rather than three parsers of one file with a row-type each. One `Cell` carries every lens's
fields (each lens reads its own subset); the extra fields are harmless projections of the same row.

This module is a pure LEAF: it imports nothing from the core. The `load_grid` constructor that reads a grid
from the active cassette lives with the I/O seam in `peitho.source` (a `Grid` is what the adapter returns),
which keeps the data abstraction free of any dependency on the loader.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Cell:
    """One (variant × store) row of the authoritative grid — the union of every lens's projected fields.
    The inventory fields are required; the price-only fields default (so a lens that ignores them, and
    inventory-style 5-arg construction, both work)."""

    store: str
    stock: int
    sale_qty: int  # over the window
    recent_sales: int  # units sold in the last 30 days (== sls_age[0]; kept for existing consumers)
    nrv: float  # net realized revenue (gross, incl tax); nrv == fresh_sale + discounted_sale
    discount_amount: float = 0.0  # ⚠ list-price-structural gap, NOT a sale signal — see the backend pricing semantics
    profit: float = 0.0  # ⚠ diverges from nrv-cogs; prefer nrv-cogs for the below-cost test
    cogs: float = 0.0  # cost of goods sold (below-cost test = nrv - cogs < 0)
    fresh_sale: float = 0.0  # revenue sold at STANDARD price
    discounted_sale: float = 0.0  # revenue sold at a discount below standard — THE direct "on sale" signal
    image: str = ""
    # --- sales-age SPECTRUM (native drilldown ladder; the multi-horizon velocity signal) ---
    # units sold bucketed by how many days ago the sale happened: (<=30, 31-60, 61-90, 91-120, >=121).
    # Recent bands are momentum; the sum is the whole-window signal. See lenses.inventory.velocity_by_horizon.
    sls_age: tuple = (0, 0, 0, 0, 0)
    avg_sale_age: float = 0.0  # mean days-ago of this cell's sales — a recency centroid
    stock_age: tuple = (0, 0, 0, 0, 0)  # CURRENT stock by age bucket — freshness of what is on hand
    days_of_stock: float = 0.0  # cover at current velocity (None → 0.0)


class Grid:
    """The per-store variant grid with selectors. Wraps {variant: {store: Cell}} behind an abstraction
    boundary; lenses query it rather than reaching into the raw dict."""

    def __init__(self, cells: dict):
        self._cells = cells

    def variants(self):
        """The variant keys (article, color, size)."""
        return self._cells.keys()

    def cells_for(self, variant) -> dict:
        """{store: Cell} for one variant (empty if absent)."""
        return self._cells.get(variant, {})

    def cell(self, variant, store) -> Cell | None:
        """The single Cell for a (variant, store), or None."""
        return self._cells.get(variant, {}).get(store)

    def items(self):
        """Iterate (variant, {store: Cell}) — the whole grid."""
        return self._cells.items()

    def values(self):
        """Iterate the per-variant {store: Cell} maps."""
        return self._cells.values()

    def __len__(self):
        return len(self._cells)
