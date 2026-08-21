"""INTEGRATION tests for the two export I/O shells the routing/ledger suites don't drive: the multi-source
article→image union, and the 'good morning' digest-of-digests router. Both are file/ledger orchestrators,
pinned here on synthetic fixtures for the output shape (the pure builders they call are pinned elsewhere).
"""

import json

import peitho.export as export
from peitho.grid import Cell, Grid


def test_article_image_map_unions_drilldown_attributes_and_clearance(monkeypatch):
    grid = Grid(
        {
            ("A1", "BLK", "40"): {"N1": Cell("N1", 1, 1, 1, 1.0, image="drill1.jpg")},
            ("A1", "BLK", "41"): {"N1": Cell("N1", 1, 1, 1, 1.0, image="drill1b.jpg")},  # same article → 2nd is skipped
            ("A2", "RED", "38"): {"N1": Cell("N1", 1, 1, 1, 1.0)},  # no drilldown image on this cell
        }
    )
    monkeypatch.setattr(export, "load_article_attributes", lambda: {"A2": {"image": "attr2.jpg"}})
    monkeypatch.setattr(export, "load_clearance_article_fields", lambda: ({}, {"A3": "clear3.jpg"}))
    m = export.article_image_map(grid)
    assert m["A1"] == "drill1.jpg"  # drilldown image (first variant wins; the second same-article variant is skipped)
    assert m["A2"] == "attr2.jpg"  # no drilldown → the curated attribute image fills it
    assert m["A3"] == "clear3.jpg"  # neither drilldown nor attribute → the clearance report fills the remaining gap


def test_export_morning_routes_a_loud_digest(tmp_path, monkeypatch):
    op = tmp_path / "op.json"
    item = tmp_path / "item.json"
    op.write_text(
        json.dumps(
            {
                "routing": {"summary": {"reorders": 5, "reorder_units": 40, "runs": 3}},
                "suppliers": {"summary": {"bands": {"DEAD_STOCK": 2, "LEFT_UNSOLD": 1}}},
                "store_clearance": {
                    "clearing_store": {"store": "N8", "depth": 15.0, "deviation": 1.5},
                    "peer_norm_depth": 5.0,
                },
            }
        )
    )
    item.write_text(
        json.dumps(
            {
                "sale_digest": {
                    "surprises": [{"code": "biggest_bleed", "magnitude": 5000.0, "fields": {"loss": 5000}}]
                },
                "seasonal": {"summary": {"events": 3, "seasonal_items": 400}},
            }
        )
    )
    monkeypatch.setattr(export, "OUT_OPERATIONAL", str(op))
    monkeypatch.setattr(export, "OUT_ITEM", str(item))
    out = tmp_path / "morning.json"
    summary = export.export_morning(str(out))
    assert out.exists() and set(summary) == {"loud", "quiet"} and summary["loud"] >= 1


def test_export_morning_degrades_to_quiet_when_the_ledgers_are_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "OUT_OPERATIONAL", str(tmp_path / "absent-op.json"))
    monkeypatch.setattr(export, "OUT_ITEM", str(tmp_path / "absent-item.json"))
    summary = export.export_morning(str(tmp_path / "m.json"))  # FileNotFoundError → {} default → every domain QUIET
    assert summary["loud"] == 0 and summary["quiet"] >= 1
