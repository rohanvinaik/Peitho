"""INTEGRATION tests for the report DELIVERY shell (peitho.report) — the operator-facing JSON→HTML pipeline.

The pure render is unit-pinned in test_render_intent; this drives the whole I/O shell end-to-end on the
bundled example cassette (procedural synthetic data, no files): refresh the operational ledger → render its
routing section → write the operator HTML. This is the "verify through the real command" guarantee for the
one artifact an operator actually opens.
"""

import peitho.report as report
from peitho.report import build_report, main
from peitho.report.render import render_report


def test_build_report_end_to_end_on_example_cassette(tmp_path):
    out = tmp_path / "routing_report.html"
    ledger = tmp_path / "operational.json"
    path = build_report(out_path=str(out), ledger_path=str(ledger), as_of="2026-08-15")
    assert path == str(out) and out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<html" in html.lower()  # a real HTML document
    assert "2026-08-15" in html  # the as_of stamp rendered through
    assert ledger.exists()  # refresh=True regenerated the operational ledger it rendered from


def test_build_report_no_refresh_renders_an_existing_ledger(tmp_path):
    ledger = tmp_path / "op.json"
    build_report(out_path=str(tmp_path / "a.html"), ledger_path=str(ledger), as_of="2026-08-15")  # writes the ledger
    out2 = tmp_path / "b.html"
    path = build_report(out_path=str(out2), ledger_path=str(ledger), refresh=False, as_of="2026-08-15")
    assert path == str(out2) and out2.exists()  # rendered the existing ledger without regenerating


def test_build_report_defaults_as_of_to_today(tmp_path):
    out = tmp_path / "r.html"
    build_report(out_path=str(out), ledger_path=str(tmp_path / "op.json"))  # as_of=None → date.today()
    assert out.exists()


def test_default_out_path_lands_under_the_reports_root():
    # the lazy I/O-config default (honoured on a cassette/env swap)
    assert report._default_out().endswith("routing_report.html")


def test_build_report_uses_the_default_out_when_none(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "_default_out", lambda: str(tmp_path / "routing_report.html"))
    path = build_report(ledger_path=str(tmp_path / "op.json"), as_of="2026-08-15")  # out_path=None → _default_out()
    assert path == str(tmp_path / "routing_report.html")


def test_main_prints_where_the_report_landed(capsys, monkeypatch):
    monkeypatch.setattr(report, "build_report", lambda: "/somewhere/routing_report.html")
    main()
    assert "routing report" in capsys.readouterr().out.lower()


def test_dunder_main_module_is_importable():
    import peitho.report.__main__  # noqa: F401  # covers the module-level `from . import main`


def test_render_shows_the_buy_section_when_the_network_cannot_self_cover():
    # the example cassette self-covers (0 reorders), so the reorder section + its summary chip only render on
    # a ledger that carries reorders — pin that branch here on a synthetic routing ledger
    ledger = {
        "summary": {"moves": 1, "units": 3, "runs": 1, "reorders": 2, "reorder_units": 9, "target_cover_days": 30},
        "transfers": [
            {
                "article": "A1",
                "color": "BLK",
                "size": "40",
                "from_store": "WH",
                "to_store": "N1",
                "qty": 3,
                "cost_min": 15.0,
                "reason": "below target",
                "image": None,
                "category": {"cluster": "Footwear", "sub_category": "Shoes"},
            }
        ],
        "reorders": [
            {
                "article": "A2",
                "qty": 6,
                "regime": "BASE",
                "why": "no internal cover",
                "image": None,
                "category": {"cluster": "Footwear", "sub_category": "Boots"},
            },
            {"article": "A3", "qty": 3, "regime": "BASE", "why": "shortfall", "image": None, "category": None},
        ],
        "reasoning": {"below target": 1},
    }
    html = render_report(ledger, brand="Acme Retail", title="Routing Report", as_of="2026-08-15")
    assert "A2" in html and "A3" in html  # the reorder rows rendered (_reorders_html non-empty branch)
    assert "reorders" in html.lower()  # the summary strip's reorder chip (the n_reord branch)
