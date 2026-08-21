"""INTEGRATION tests for peitho.ledgers — the operational-domain section builders + the export_operational
I/O shell. The section-builders are the content logic that REPLACED the retired per-report export_routing /
export_suppliers / export_manufacturer_orders; like those, they open/assemble/dump over live data and are
`--input`-inexpressible, so Detective correctly never converges them. These characterize their behaviour over
tiny synthetic fixtures (a real Grid of Cells), and one test drives export_operational end-to-end to disk the
way `python -m peitho.report` refreshes it. The pure decisions each already carry their own Detective + intent
suites; here we pin the glue that projects the substrate into the flat domain ledger.
"""

import json

import peitho.ledgers as led
import peitho.lenses.supplier as sup_mod
from peitho.grid import Cell, Grid
from peitho.route import COVER_DAYS_DEFAULT


def _grid() -> Grid:
    # one article, sizes across two stores; A1/BLK/41 is sold below cost (nrv<cogs)
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


def test_routing_section_summary_and_target(monkeypatch):
    # build_routing_section is pure over the grid; assert the summary shape + the calibrated coverage horizon
    monkeypatch.setattr(led, "load_taxonomy", dict)
    monkeypatch.setattr(led, "article_image_map", lambda g: {})
    sec = led.build_routing_section(_grid())
    assert set(sec) == {"summary", "transfers", "reorders", "reasoning"}
    assert set(sec["summary"]) == {"moves", "units", "runs", "reorders", "reorder_units", "target_cover_days"}
    assert sec["summary"]["target_cover_days"] == COVER_DAYS_DEFAULT
    assert isinstance(sec["transfers"], list) and isinstance(sec["reorders"], list)


def test_routing_section_reorders_are_regime_gated(monkeypatch):
    """The routing reorders are the regime-gated supply_plan (the controller's purchasing decision), NOT the
    flow's per-cell unmet signal. An article far below base-stock must surface as a regime-tagged order —
    carrying `regime`/`why` (SupplyOrder), never the old flow-`Reorder`'s `store` field."""
    import peitho.query.regime as reg_mod

    grid = Grid({("Z1", "BLK", "40"): {"N8": Cell("N8", stock=0, sale_qty=50, recent_sales=20, nrv=1.0)}})
    monkeypatch.setattr(led, "load_taxonomy", dict)
    monkeypatch.setattr(led, "article_image_map", lambda g: {})
    monkeypatch.setattr(reg_mod, "article_regimes", lambda *a, **k: {"Z1": "BASE"})
    monkeypatch.setattr(led, "article_regimes", lambda *a, **k: {"Z1": "BASE"})
    sec = led.build_routing_section(grid)
    reorders = sec["reorders"]
    assert reorders, "an article at 0 stock, far below base-stock, must produce a supply_plan reorder"
    assert all("regime" in r and "store" not in r for r in reorders)


def test_suppliers_section_ranks_purchases(monkeypatch):
    agg = {
        "ACME": {"sold": 160.0, "purchased": 200.0, "stock": 40.0, "profit": 5000.0},  # moves
        "BETA": {"sold": 10.0, "purchased": 300.0, "stock": 290.0, "profit": -200.0},  # sits
    }
    monkeypatch.setattr(sup_mod, "load_supplier_purchases", lambda: agg)
    sec = led.build_suppliers_section()
    assert sec["summary"]["suppliers"] == 2 and sec["summary"]["min_purchased"] == 200.0
    assert {r["supplier"] for r in sec["suppliers"]} == {"ACME", "BETA"}
    assert all("sell_through" in r and "band" in r for r in sec["suppliers"])


def test_export_operational_writes_all_sections(tmp_path, monkeypatch):
    # the I/O shell end-to-end: export_operational assembles every section over ONE grid load and writes the
    # single domain file — the way `python -m peitho.report` refreshes it. Leaf loaders stubbed; compute real.
    import peitho.lenses.inventory as inv_mod

    monkeypatch.setattr(inv_mod, "load_grid", lambda *a, **k: _grid())  # == led.inventory.load_grid
    monkeypatch.setattr(led, "load_price_grid", lambda: _grid())  # store_clearance section
    monkeypatch.setattr(led, "load_taxonomy", dict)
    monkeypatch.setattr(led, "article_image_map", lambda g: {})
    monkeypatch.setattr(sup_mod, "load_supplier_purchases", dict)  # empty supplier feed
    monkeypatch.setattr(sup_mod, "load_article_supplier", dict)  # manufacturer section
    out = tmp_path / "operational.json"
    summary = led.export_operational(str(out))
    written = json.loads(out.read_text())
    assert written["domain"] == "operational"
    assert set(written) == {
        "domain",
        "stores",
        "routing",
        "manufacturer_orders",
        "suppliers",
        "vendor_mis",
        "store_clearance",
        "network",
    }
    assert set(summary) == {"stores", "routing_moves", "manufacturer_orders"}


# ---- item-domain section builders (ported from the retired per-report export tests) ----


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


def _stub_item_loaders(mp):
    """The leaf loaders the item section-builders share (module-level attrs on `ledgers`)."""
    mp.setattr(led, "load_article_attributes", _attrs)
    mp.setattr(led, "load_taxonomy", _taxo)
    mp.setattr(led, "load_article_ages", _ages)
    mp.setattr(led, "dedupe_articles", list)  # []
    mp.setattr(led, "article_image_hashes", dict)  # {}


def test_by_sku_section_one_record_per_sku(monkeypatch):
    _stub_item_loaders(monkeypatch)
    recs = led.build_by_sku_section(_grid())
    assert len(recs) == 3  # one per (article, color, size)
    assert [r["sku"]["article"] for r in recs] == ["A1", "A1", "A2"]  # sorted by identity
    first = recs[0]
    assert first["sku"] == {"article": "A1", "color": "BLK", "size": "40"}
    assert first["image"] == "http://img/a1.jpg"  # front-anchored
    assert first["category"]["raw"] == {"section": "MENS", "subsection": "FORMAL"}  # translate_taxonomy ran for real
    assert first["age_days"] == 730
    assert first["stock"] == {"total": 8, "by_location": {"N5": 5, "N8": 3}}
    assert recs[1]["stock"] == {"total": 0, "by_location": {}}  # A1/BLK/41 N8=0 excluded


def test_by_item_section_rolls_sizes_into_one_item(monkeypatch):
    _stub_item_loaders(monkeypatch)
    recs = led.build_by_item_section(_grid())
    assert len(recs) == 2  # (A1,BLK) and (A2,RED)
    a1 = recs[0]
    assert a1["item"] == {"article": "A1", "color": "BLK"}
    assert a1["sizes"]["in_stock"] == ["40"]  # size 41 has 0 stock -> not available
    assert a1["sizes"]["by_size"] == {"40": 8, "41": 0}
    assert a1["stock"]["total"] == 8


def test_shadow_section_carries_movement_and_supplier(monkeypatch):
    _stub_item_loaders(monkeypatch)
    monkeypatch.setattr(sup_mod, "load_article_supplier", lambda: {"A1": "ACME"})
    monkeypatch.setattr(led, "load_clearance_article_fields", lambda: ({"A1": 1999.0}, {}))
    recs = led.build_shadow_section(_grid())
    assert len(recs) == 2
    a1 = next(r for r in recs if r["item"]["article"] == "A1")
    mv = a1["movement"]
    assert mv["velocity_30d"] == 14 and mv["sold_window"] == 16  # summed across the group's cells
    assert mv["below_cost"] is False  # nrv 11200 > cogs 6900
    assert "sale_price_robust" in mv and "price_split" in mv  # robust_price ran for real
    assert a1["supplier"] == "ACME" and a1["rsp"] == 1999.0


def test_item_clearance_section_is_item_grain_fresh_dump(monkeypatch):
    cleared = Grid(
        {
            ("A1", "BLK", "40"): {"N8": Cell("N8", 3, 10, 9, 1000.0, discount_amount=50.0, profit=200.0)},
            ("A2", "RED", "38"): {"N8": Cell("N8", 2, 5, 5, 100.0, discount_amount=400.0, profit=-50.0)},
        }
    )
    monkeypatch.setattr(led, "load_article_ages", lambda: {"A2": 100})  # young -> FRESH_DUMP
    monkeypatch.setattr(led, "load_article_attributes", dict)
    monkeypatch.setattr(led, "load_taxonomy", dict)
    sec = led.build_item_clearance_section(cleared)
    assert set(sec) == {"summary", "items"}  # item-grain only — no store part (that is operational's)
    assert set(sec["summary"]) == {"fresh_dump", "aged_clearance"}
    assert sec["summary"]["fresh_dump"] >= 1 and sec["items"]  # the item_row closure ran


def test_sale_digest_section_reads_shadow_in_memory():
    # the blind men talk: the digest reads the shadow SECTION directly (no file), same records as before
    shadow_records = [
        {
            "item": {"article": "X", "color": "BLK"},
            "category": {"cluster": "Shoes"},
            "supplier": "ACME",
            "movement": {
                "below_cost": True,
                "below_cost_by": 120,
                "sold_window": 5,
                "velocity_30d": 2,
                "days_of_cover": 40,
            },
        },
        {
            "item": {"article": "Y", "color": "RED"},
            "category": {"cluster": "Sandals"},
            "supplier": "BETA",
            "movement": {
                "below_cost": False,
                "below_cost_by": None,
                "sold_window": 3,
                "velocity_30d": 30,
                "days_of_cover": 2,
            },
        },
    ]
    sec = led.build_sale_digest_section(shadow_records)
    codes = {s["code"] for s in sec["surprises"]}
    assert "biggest_bleed" in codes  # X is the below-cost bleed
    assert "top_mover" in codes  # Y is fast + low cover -> the winner


def _restock_cell(store, stock, sale_qty):
    return Cell(
        store=store, stock=stock, sale_qty=sale_qty, recent_sales=sale_qty, nrv=1000.0, sls_age=(sale_qty, 0, 0, 0, 0)
    )


def test_restock_section_projects_the_field_to_a_flat_shadow_ledger(monkeypatch):
    grid = Grid(
        {
            ("ART1", "BLK", "M"): {
                "N8": _restock_cell("N8", stock=0, sale_qty=40),  # stocked-out selling cell → a real anomaly
                "N5": _restock_cell("N5", stock=400, sale_qty=40),  # well-stocked selling cell
            }
        }
    )
    monkeypatch.setattr(led, "load_taxonomy", dict)
    monkeypatch.setattr(led, "article_image_map", lambda g: {})
    sec = led.build_restock_section(grid)
    assert set(sec) >= {"summary", "restock", "escalate", "anomaly_classes"}
    s = sec["summary"]
    # the decisions PARTITION the whole flagged field (every cell decided exactly once)
    assert s["restock"] + s["escalate"] + s["hold"] + s["ignore"] == s["flagged"]
    assert s["classes"] == len(sec["anomaly_classes"])
    for rec in sec["restock"] + sec["escalate"]:
        assert {"article", "color", "size", "store", "decision", "signature", "label"} <= set(rec)
        assert len(rec["signature"]) == 4
    for cls in sec["anomaly_classes"]:
        assert cls["decision"] in ("RESTOCK", "HOLD", "ESCALATE", "IGNORE")
        assert len(cls["signature"]) == 4


def test_export_item_writes_all_sections(tmp_path, monkeypatch):
    # the I/O shell end-to-end: export_item assembles every section over one stock-grid + one price-grid load
    # and writes the single domain file — the way `python -m peitho.export` refreshes it.
    import peitho.lenses.inventory as inv_mod

    monkeypatch.setattr(inv_mod, "load_grid", lambda *a, **k: _grid())  # == led.load_grid source
    monkeypatch.setattr(led, "load_grid", lambda *a, **k: _grid())
    monkeypatch.setattr(led, "load_price_grid", lambda: _grid())
    _stub_item_loaders(monkeypatch)
    monkeypatch.setattr(led, "load_clearance_article_fields", lambda: ({}, {}))
    monkeypatch.setattr(led, "article_image_map", lambda g: {})
    monkeypatch.setattr(sup_mod, "load_article_supplier", dict)
    out = tmp_path / "item.json"
    summary = led.export_item(str(out))
    written = json.loads(out.read_text())
    assert written["domain"] == "item"
    assert set(written) == {
        "domain",
        "by_sku",
        "by_item",
        "shadow",
        "categories",
        "abc",
        "clearance",
        "seasonal",
        "sale_digest",
        "outliers",
        "restock",
    }
    assert set(summary) == {"by_sku", "items", "restock_flagged"}


def test_report_builds_all_domain_ledgers(monkeypatch, capsys):
    # ledgers.report() (python -m peitho.ledgers) builds every domain ledger and prints a one-line summary of
    # each. The ledger exports read live data, so stub them and assert the orchestration + order.
    calls = []
    monkeypatch.setattr(
        led, "export_operational", lambda: calls.append("operational") or {"stores": 7, "routing_moves": 3}
    )
    monkeypatch.setattr(
        led, "export_item", lambda: calls.append("item") or {"by_sku": 9, "items": 5, "restock_flagged": 2}
    )
    monkeypatch.setattr(led, "export_customer", lambda: calls.append("customer") or {"persons": 4, "active": 3})
    led.report()
    assert calls == ["operational", "item", "customer"]  # operational → item → customer
    out = capsys.readouterr().out
    assert "Operational ledger" in out and "Item ledger" in out and "Customer ledger" in out
