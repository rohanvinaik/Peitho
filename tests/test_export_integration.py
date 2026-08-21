"""INTEGRATION tests for peitho.export's I/O ORCHESTRATION shell — the export_*/load_* functions that open
landed backend JSON, group the grid, call the pinned pure builders, and json.dump. These are
`--input`-inexpressible (they read files / live data), so Detective correctly never converged them; this
pins their orchestration END-TO-END over tiny synthetic fixtures the way the real `report()` command runs —
a real Grid of Cells + minimal attr/taxo/age maps, one stubbed leaf-loader deep — asserting the written
JSON's shape and the returned summary. The pinned pure decisions each already carry their own Detective +
intent suites; here we characterize the glue that wires them to disk, closing the report-pipeline gap.

Only the file-READING leaf loaders are stubbed (load_grid / load_*_purchases / load_price_grid / …); the
compute they feed (translate_taxonomy, plan_transfers, rank_suppliers, store_clearance, taste_verdicts,
robust_price) runs FOR REAL, so these tests exercise the lens engines too, not just the export wrappers.
"""

import json

import peitho.export as ex
import peitho.lenses.price as price_mod
from peitho.grid import Cell, Grid


def _grid() -> Grid:
    # one article, two colourways-worth of sizes across two stores; A1/BLK/41 is sold below cost (nrv<cogs)
    return Grid(
        {
            ("A1", "BLK", "40"): {
                "N8": Cell("N8", stock=3, sale_qty=10, recent_sales=9, nrv=9000.0, cogs=5000.0, discounted_sale=4000.0),
                "N5": Cell("N5", stock=5, sale_qty=2, recent_sales=1, nrv=2000.0, cogs=1000.0, discounted_sale=0.0),
            },
            ("A1", "BLK", "41"): {
                "N8": Cell("N8", stock=0, sale_qty=4, recent_sales=4, nrv=200.0, cogs=900.0, discounted_sale=200.0),
            },
            ("A2", "RED", "38"): {
                "N5": Cell("N5", stock=7, sale_qty=0, recent_sales=0, nrv=0.0, cogs=0.0, discounted_sale=0.0),
            },
        }
    )


def _attrs() -> dict:
    return {
        "A1": {"image": "http://img/a1.jpg", "style": {"variety": "OXFORD", "brand": "EXAMPLE"}},
        "A2": {"image": None, "style": {"variety": "BALLERINA"}},
    }


def _taxo() -> dict:
    return {
        "A1": {"section": "MENS", "subsection": "FORMAL"},
        "A2": {"section": "WOMENS", "subsection": "BALLERINAS"},
    }


def _ages() -> dict:
    return {"A1": 730, "A2": 120}


def _stub_grid_loaders(mp):
    """The leaf loaders the taste-ledger export reads (module-level attrs on `ex`)."""
    mp.setattr(ex, "load_article_attributes", lambda: _attrs())
    mp.setattr(ex, "load_taxonomy", lambda: _taxo())
    mp.setattr(ex, "load_article_ages", lambda: _ages())


# The backend file-reading leaf loaders (load_article_attributes / load_taxonomy / load_clearance_article_fields)
# now live in a company cassette's PRIVATE adapter (peitho.source delegates to it); their parsing is exercised
# end-to-end by the behavior oracle, not the public suite. The grid-driven export assemblers below stub the
# loaders directly, so they stay backend-agnostic.


# ---- the grid-driven exports: assert the written JSON's shape + the record count/summary ----


def test_export_taste_ledger_writes_dated_file(tmp_path, monkeypatch):
    _stub_grid_loaders(monkeypatch)
    monkeypatch.setattr(price_mod, "load_price_grid", _grid)
    summary = ex.export_taste_ledger("2026-08-17", str(tmp_path))
    day_file = tmp_path / "2026-08-17.json"
    assert day_file.exists()
    written = json.loads(day_file.read_text())
    assert set(summary) == {"verdicts", "conditional", "by_store"}
    assert written["date"] == "2026-08-17"
