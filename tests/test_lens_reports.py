"""SMOKE tests for every lens/module `report()` CLI printer + config root detection. These __main__ demo
printers are --input-inexpressible (they load landed data and print), so no synthesis tool writes them;
here we stub each module's file-reading leaves, call report() over realistic synthetic shapes, and assert it
runs to a non-empty print. Cheap, but real: a report() that KeyErrors / divides-by-None on the true data
shape is a live regression these catch — the compute they wrap (segments, clearance, routing) runs for real.
"""

import peitho.config as cfg
import peitho.customer as cust
import peitho.export as ex  # noqa: F401  (kept parallel with the export report path; unused import is fine)
import peitho.lenses.inventory as inv
import peitho.lenses.price as price
import peitho.lenses.supplier as sup
import peitho.route as route
import peitho.sku as sku
from peitho.grid import Cell, Grid


def _grid() -> Grid:
    return Grid(
        {
            ("A1", "BLK", "40"): {
                "N8": Cell("N8", 3, 10, 9, 9000.0, cogs=5000.0, discounted_sale=4000.0, discount_amount=1000.0),
                "N5": Cell("N5", 50, 1, 1, 2000.0, cogs=1000.0),
            },
            ("A1", "BLK", "41"): {"N8": Cell("N8", 0, 4, 4, 200.0, cogs=900.0, discounted_sale=200.0)},
        }
    )


def test_sku_report_runs(monkeypatch, capsys):
    monkeypatch.setattr(sku, "dedupe_articles", lambda: [["A1", "A2"]])
    monkeypatch.setattr(sku, "load_sample_skus", lambda *a, **k: {"26p100", "23p5"})
    sku.report()
    out = capsys.readouterr().out
    assert "DEDUPE" in out and "WORMHOLE" in out


def test_inventory_report_runs(monkeypatch, capsys):
    # A1@N8 is far below the (A9-inflated) N8 baseline and N5 holds spare of it -> a ROUTABLE graded shortage,
    # so the report's routable loop runs, not just the header.
    routable = Grid(
        {
            ("A1", "BLK", "40"): {"N8": Cell("N8", 1, 10, 9, 0.0), "N5": Cell("N5", 50, 1, 1, 0.0)},
            ("A9", "BLK", "1"): {"N8": Cell("N8", 100, 5, 1, 0.0)},  # inflates N8 baseline
        }
    )
    monkeypatch.setattr(inv, "load_grid", lambda: routable)
    # both A1 and A9 are MENS so the (N8,MENS) baseline is set by the big A9 cell -> A1 sits far below it
    monkeypatch.setattr(inv, "load_article_sections", lambda taxonomy=None: {"A1": "MENS", "A9": "MENS"})
    monkeypatch.setattr(inv, "_default_min_cost", lambda: {})
    inv.report()
    assert "shortages" in capsys.readouterr().out


def test_supplier_report_runs(monkeypatch, capsys):
    agg = {
        "ACME": {"sold": 160.0, "purchased": 200.0, "stock": 40.0, "profit": 5000.0},
        "BETA": {"sold": 0.0, "purchased": 300.0, "stock": 0.0, "profit": -100.0},  # 0 sold & 0 left -> LEFT_UNSOLD
    }
    monkeypatch.setattr(sup, "load_supplier_purchases", lambda: agg)
    sup.report()
    out = capsys.readouterr().out
    assert "SUPPLIER" in out and "LEFT_UNSOLD" in out


def test_price_report_runs(monkeypatch, capsys):
    # A2@N8 is marked down far above N8's own (A1-set) markdown norm -> a flagged cleared item, so the report's
    # item loop runs, not just the store-grain header.
    cleared = Grid(
        {
            ("A1", "BLK", "40"): {"N8": Cell("N8", 3, 10, 9, 1000.0, discount_amount=50.0, profit=200.0)},
            ("A2", "RED", "38"): {"N8": Cell("N8", 2, 5, 5, 100.0, discount_amount=400.0, profit=-50.0)},
        }
    )
    monkeypatch.setattr(price, "load_price_grid", lambda: cleared)
    monkeypatch.setattr(price, "load_article_ages", lambda: {"A2": 400})
    price.report()
    assert "STORE grain" in capsys.readouterr().out


def test_route_report_runs(monkeypatch, capsys):
    # N8 out & selling, N5 holds spare of the same variant -> a real transfer, so the report's run loop prints
    moving = Grid({("A1", "BLK", "40"): {"N8": Cell("N8", 0, 5, 5, 0.0), "N5": Cell("N5", 50, 1, 1, 0.0)}})
    monkeypatch.setattr(inv, "load_grid", lambda: moving)
    monkeypatch.setattr(route, "_default_min_cost", lambda: {("N5", "N8"): 12.0})
    route.report()
    assert "Transfer plan" in capsys.readouterr().out


def test_customer_report_runs(monkeypatch, capsys):
    raw = [
        {
            "customerCode": "AH0000000001",
            "mobile": "5551234567",
            "name": "MR JOHN SMITH",
            "gender": "M",
            "created": "2024-01-15",
        },
        {
            "customerCode": "AC0000000009",
            "mobile": "5559998888",
            "name": "MIKE BROWN",
            "gender": "M",
            "created": "2025-06-01",
        },
    ]
    monkeypatch.setattr(cust, "load_clean_master", lambda: [cust.clean_record(r) for r in raw])
    cust.report()
    assert "CUSTOMER identity resolution" in capsys.readouterr().out


def test_detect_root_walks_up_to_pyproject(monkeypatch):
    # with the env override removed, _detect_root walks up from the module to the pyproject.toml dir
    monkeypatch.delenv("PEITHO_ROOT", raising=False)
    root = cfg._detect_root()
    assert (root / "pyproject.toml").exists()


def test_detect_root_structural_fallback(monkeypatch):
    # no env AND no pyproject.toml anywhere up the tree (an installed-wheel deploy) -> the structural fallback:
    # src/peitho/config.py -> peitho -> src -> project root (three parents up)
    monkeypatch.delenv("PEITHO_ROOT", raising=False)
    monkeypatch.setattr(cfg.Path, "exists", lambda self: False)
    assert cfg._detect_root() == cfg.Path(cfg.__file__).resolve().parents[2]
