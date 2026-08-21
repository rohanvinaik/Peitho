"""Example data-input adapter — a small PROCEDURAL synthetic backend for the bundled Northwind cassette.

Generates a deterministic in-memory grid over the example network (WH + N1..N5) with NO data files and no
randomness, so a fresh checkout runs the demo with zero private data. WH holds stock but never sells (so
the role induction reads it as the warehouse source); the satellites sell at varying rates with some
stockouts, giving the router real shortages to resolve. Implements peitho.source.SourceAdapter.
"""

from __future__ import annotations

from peitho.grid import Cell, Grid

_NODES = ("WH", "N1", "N2", "N3", "N4", "N5")
_ARTICLES = tuple(f"AX-{1000 + i}" for i in range(8))
_COLORS = ("BLACK", "TAN")
_SIZES = ("38", "40", "42")


def load_grid(grid_dir: str | None = None, stores: list | None = None) -> Grid:
    """A deterministic synthetic per-store variant grid. `stores` filters to those nodes (else all six).
    `grid_dir` is ignored — this adapter is procedural, not file-backed."""
    nodes = [n for n in _NODES if stores is None or n in stores]
    cells: dict = {}
    for ai, art in enumerate(_ARTICLES):
        for ci, col in enumerate(_COLORS):
            for si, sz in enumerate(_SIZES):
                per: dict = {}
                for ni, node in enumerate(nodes):
                    if node == "WH":
                        stock, sale, recent = 20, 0, 0  # the warehouse: holds stock, never sells
                    else:
                        base = ai + ci + si + ni
                        sale = (base * 3) % 13
                        recent = sale // 2
                        stock = (base * 2) % 7  # some zero → live shortages for the router
                    sls = (recent, max(sale - recent, 0), 0, 0, 0)
                    per[node] = Cell(
                        store=node,
                        stock=stock,
                        sale_qty=sale,
                        recent_sales=recent,
                        nrv=float(sale * 500),
                        cogs=float(sale * 300),
                        fresh_sale=float(sale * 400),
                        discounted_sale=float(sale * 100),
                        sls_age=sls,
                    )
                cells[(art, col, sz)] = per
    return Grid(cells)


# synthetic per-article records, keyed to the example taxonomy tokens so the deconvolution resolves them
_SECTIONS = ("SANDALS", "SHOES", "SHOES", "SANDALS", "BAG", "BELT", "SNEAKERS", "DRESS")
_GENDERS = ("WOMENS", "MENS", "WOMENS", "MENS", "WOMENS", "MENS", "KIDS", "WOMENS")


def load_taxonomy(path: str | None = None) -> dict:
    """Synthetic raw {article: {section, subsection}} — the category token in section, gender in subsection."""
    return {art: {"section": _SECTIONS[i], "subsection": _GENDERS[i]} for i, art in enumerate(_ARTICLES)}


def load_article_attributes(path: str | None = None) -> dict:
    """Synthetic per-article attributes — no image / style enrichment in the example."""
    return {art: {"image": None, "style": {}} for art in _ARTICLES}


def load_clearance_article_fields(path: str | None = None) -> tuple:
    """No clearance report in the example."""
    return {}, {}


def load_article_ages(age_grid: str | None = None, today: str = "2026-08-15") -> dict:
    """Synthetic per-article vintage (days) — a deterministic spread so the age-driven signals have variety."""
    return {art: 90 + i * 45 for i, art in enumerate(_ARTICLES)}


def load_article_supplier(path: str | None = None) -> dict:
    """Synthetic per-article supplier edge — two example manufacturers alternating across the articles."""
    return {art: ("Northwind Supply" if i % 2 else "Cascade Makers") for i, art in enumerate(_ARTICLES)}


def load_supplier_purchases(purchase_glob: str | None = None) -> dict:
    """No purchase-receipt feed in the example."""
    return {}


def load_article_sections(taxonomy: str | None = None) -> dict:
    """Synthetic {article: section} — the merchandise section (the category token) per article."""
    return {art: _SECTIONS[i] for i, art in enumerate(_ARTICLES)}


def load_article_images(grid_dir: str | None = None) -> dict:
    """No image files in the example (procedural)."""
    return {}


def article_image_hashes(grid_dir: str | None = None, image_dir: str | None = None) -> dict:
    """No image content-hashes in the example."""
    return {}


def fy_dirs(history_dir: str | None = None) -> list:
    """No multi-year history in the example."""
    return []


def load_fy_articles(history_dir: str | None = None) -> dict:
    """No multi-year history in the example — every article reads as a single-year (SEASONAL/UNKNOWN) line."""
    return {}


def load_photo_hash(history_dir: str | None = None, image_dir: str | None = None) -> dict:
    """No cross-year photo hashes in the example."""
    return {}


def load_bills_by_customer(bill_dir: str | None = None) -> dict:
    """No customer/bill PII in the example."""
    return {}


def load_clean_master(customer_dir: str | None = None) -> list:
    """No customer master in the example."""
    return []


def sample_sku_globs() -> tuple:
    """No SKU-code samples in the example."""
    return ()


def sample_sku_key() -> str:
    """The canonical SKU-code field name (unused — the example ships no samples)."""
    return "sku_code"


def daily_grid_dir(date: str, root: str | None = None) -> str:
    """The daily-snapshot directory for a date — a generic layout (no vendor-specific path segments)."""
    from peitho.config import ROOT

    return f"{root or ROOT}/data/daily/{date}"


def load_snapshot(date: str, root: str | None = None) -> dict:
    """{(article, color, size, store): (stock, sale)} from a dated daily snapshot (defensive sum). The example
    reads a generic per-store snapshot ({store}.json with a `rows` list of canonical fields); a real cassette's
    adapter maps its own backend's snapshot schema into this same shape."""
    import json
    import os
    from collections import defaultdict

    from peitho.network import active_network

    base = daily_grid_dir(date, root)
    out: dict = defaultdict(lambda: (0, 0))
    for st in active_network().nodes:
        path = f"{base}/{st}.json"
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            rows = json.load(fh).get("rows", [])
        for r in rows:
            k = (r["article"], r.get("color", ""), r.get("size", ""), st)
            ps, pq = out[k]
            out[k] = (ps + (r.get("stock", 0) or 0), pq + (r.get("sale", 0) or 0))
    return dict(out)
