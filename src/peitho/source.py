"""peitho.source — the data-input adapter contract: how the agnostic core gets canonical records.

The core carries NO knowledge of any backend's schema, field names, file layout, or data paths. It asks
the active cassette's *adapter* for already-normalized canonical records — the ``Grid`` of per-store
variant cells, the article attribute / taxonomy / age maps, the supplier and customer records — and never
sees a raw backend key. A company's backend integration (which fields map to which canonical value, where
the files live, how the SKU/customer codes are shaped) lives entirely in that cassette's adapter package,
so the public core reveals nothing about any specific backend product.

``SourceAdapter`` documents the methods the core delegates to (a structural Protocol — an adapter just
needs to provide them). ``adapter()`` returns the active cassette's adapter module. The bundled example
cassette ships a small PROCEDURAL synthetic adapter, so a fresh checkout runs the demo with no real data.
"""

from __future__ import annotations

import contextlib
from typing import Protocol, runtime_checkable

from .grid import Grid


def parse_report_table(rows: list, key_col: str, value_col: str, cast=lambda v: v) -> dict:
    """Flatten a positional REPORT table (row 0 = the column-name header) into ``{key_col value: value_col
    value}`` over its DETAIL rows (``total_mode == 0``; subtotal/grand-total rows are ``total_mode != 0`` and
    dropped). First non-blank value per key wins; ``cast`` coerces the value (e.g. ``float`` for a price,
    ``str.strip`` for a label). Empty when the required columns are absent — never a crash. Pure over the rows
    + column names: which backend columns to read is the ADAPTER's business (it passes the names); the parse
    itself is company-agnostic, so it stays in the public core and is mutation-pinnable."""
    if not rows:
        return {}
    header = [str(x) for x in rows[0]]
    if not all(c in header for c in ("total_mode", key_col, value_col)):
        return {}
    tm, ki, vi = header.index("total_mode"), header.index(key_col), header.index(value_col)
    out: dict = {}
    for r in rows[1:]:
        if r[tm] != 0:  # subtotal / grand-total row — not a detail line
            continue
        k, v = r[ki], r[vi]
        if not (isinstance(k, str) and k.strip()) or k in out:  # blank key, or first value already won
            continue
        if v in (None, "") or (isinstance(v, str) and not v.strip()):  # blank value
            continue
        with contextlib.suppress(ValueError, TypeError):  # a cast that rejects the value drops the row
            out[k] = cast(v)
    return out


@runtime_checkable
class SourceAdapter(Protocol):
    """The canonical-record contract a cassette's adapter implements. Every method returns records already
    in the core's neutral shape; the backend-specific parsing happens inside the adapter, out of the core."""

    def load_grid(self, grid_dir: str | None = None, stores: list | None = None) -> Grid:
        """The authoritative per-store × variant grid (stock, sales, the sales-age spectrum, price fields)."""

    def load_taxonomy(self, path: str | None = None) -> dict:
        """{article: {"section": str|None, "subsection": str|None}} — the raw category lenses (pre-deconvolution)."""

    def load_article_attributes(self, path: str | None = None) -> dict:
        """{article: {"image": str, "style": {...}}} — per-article image + descriptive style attributes."""

    def load_clearance_article_fields(self, path: str | None = None) -> tuple:
        """(rsp_by_article, image_by_article) from the clearance report — ({}, {}) when absent."""

    def load_article_ages(self, age_grid: str | None = None, today: str = "2026-08-15") -> dict:
        """{article: age_days} — each article's shelf age from its earliest purchase-receipt date."""

    def load_article_supplier(self, path: str | None = None) -> dict:
        """{article: supplier} — the per-article manufacturer edge; empty until the supplier report is pulled."""

    def load_supplier_purchases(self, purchase_glob: str | None = None) -> dict:
        """{supplier: {sold, purchased, stock, profit}} — aggregated purchase receipts per supplier."""

    def load_article_sections(self, taxonomy: str | None = None) -> dict:
        """{article: section} — the merchandise section (broad category) per article."""

    def load_article_images(self, grid_dir: str | None = None) -> dict:
        """{article: image filename} — the article's image reference from the landed data."""

    def article_image_hashes(self, grid_dir: str | None = None, image_dir: str | None = None) -> dict:
        """{article: content-hash} — the image byte-hash (same photo = same style) for present images."""

    def fy_dirs(self, history_dir: str | None = None) -> list:
        """The financial-year subdirectories of the per-store history landing, sorted."""

    def load_fy_articles(self, history_dir: str | None = None) -> dict:
        """{fy_name: [article present that FY]} — the per-year article existence sets for the regime split."""

    def load_photo_hash(self, history_dir: str | None = None, image_dir: str | None = None) -> dict:
        """{article: content-hash} unioned across all FY history dirs — the cross-year photo identity."""

    def load_bills_by_customer(self, bill_dir: str | None = None) -> dict:
        """{customerCode: [bill, …]} — landed bill headers grouped by customer (PII; empty until pulled)."""

    def load_clean_master(self, customer_dir: str | None = None) -> list:
        """Harmonized customer master node records (PII; empty until pulled)."""

    def sample_sku_globs(self) -> tuple:
        """The landed detail-dir glob patterns that carry SKU-code line-item samples (the SKU-wormhole demo)."""

    def sample_sku_key(self) -> str:
        """The backend's SKU-code field name in those sample files (the core walks for it; canonical 'sku_code')."""

    def daily_grid_dir(self, date: str, root: str | None = None) -> str:
        """The per-store grid directory for a dated daily snapshot (the reconciliation back-run reads it)."""

    def load_snapshot(self, date: str, root: str | None = None) -> dict:
        """{(article, color, size, store): (stock, sale)} from a dated daily snapshot."""


def adapter() -> SourceAdapter:
    """The active cassette's data-input adapter (see ``peitho.cassette``). The single seam through which
    the core reads landed data — swap the cassette, swap the backend, no core change."""
    from . import cassette

    return cassette.active().adapter


def load_grid(grid_dir: str | None = None, stores: list | None = None) -> Grid:
    """The authoritative per-store variant grid — delegated to the active cassette's data-input adapter,
    which owns the backend's field parsing, file layout and data paths. ``grid_dir`` (an explicit override,
    e.g. a daily snapshot dir) and ``stores`` (the load-order roster) pass through. The core never sees a raw
    backend key — it receives canonical ``Cell``s. The constructor lives here, with the I/O seam, so
    ``peitho.grid`` stays a pure leaf abstraction (``Cell`` + ``Grid``) that imports nothing from the core."""
    return adapter().load_grid(grid_dir, stores)
