"""Hand-authored INTENT tests for peitho.report — the operator's daily routing report.

The Detective synth suites pin what the pure decisions DO (characterization); these pin what they should
MEAN (intent), and drive the whole renderer end-to-end through the real `build_report` on a synthetic
ledger. The load-bearing intents: the geometry's raw `BANK:word` tokens NEVER reach the operator (they are
humanized), untrusted ledger values are HTML-escaped, the report survives both colour schemes, and the
empty states read cleanly.
"""

from __future__ import annotations

import json

from peitho.report import build_report, render
from peitho.report.render import group_runs, humanize_reason, parse_reason
from peitho.report.style import humanize_token, prettify_category

# A small synthetic routing SECTION — the shape carried at operational.json["routing"], hand-built so the
# test owns no real data. render_report operates on this section directly; build_report reads it out of the
# operational-domain ledger.
_LEDGER = {
    "summary": {"moves": 3, "units": 6, "runs": 2, "reorders": 0, "reorder_units": 0, "target_cover_days": 14},
    "transfers": [
        {
            "article": "AX-1",
            "color": "BLACK",
            "size": "42",
            "image": None,
            "category": {
                "cluster": "Footwear",
                "sub_category": "Sandals",
                "gender": "F",
                "age_group": None,
                "status": "resolved",
            },
            "from_store": "WH",
            "to_store": "N1",
            "qty": 3,
            "cost_min": 15.0,
            "reason": "INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:accelerating",
        },
        {
            "article": "AX-2",
            "color": "TAN",
            "size": "40",
            "image": None,
            "category": None,
            "from_store": "WH",
            "to_store": "N1",
            "qty": 2,
            "cost_min": 15.0,
            "reason": "INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:·",
        },
        {
            "article": "AX-3",
            "color": "BLACK",
            "size": "38",
            "image": None,
            "category": None,
            "from_store": "N3",
            "to_store": "N2",
            "qty": 1,
            "cost_min": 40.0,
            "reason": None,
        },
    ],
    "reorders": [],
    "reasoning": {
        "INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:·": 2,
        "INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:accelerating": 1,
    },
}


# --- the pure decisions, from intent -------------------------------------------------------------


def test_parse_reason_drops_neutral_and_malformed():
    assert parse_reason("INVENTORY:deficit PRICE:· SPATIAL:short") == [("INVENTORY", "deficit"), ("SPATIAL", "short")]
    assert parse_reason("") == []
    assert parse_reason(None) == []
    assert parse_reason("nocolon X:") == []  # no separator, and empty word → both dropped


def test_humanize_reason_and_token():
    assert humanize_reason("INVENTORY:deficit VELOCITY:accelerating") == "low cover, selling fast"
    assert humanize_reason("PRICE:·") == ""  # a pure-abstain read says nothing
    # an unknown position is never dropped or crashed — it degrades to a readable fallback
    assert humanize_token("MOOD", "spicy") == "mood spicy"


def test_prettify_category_gender_age_and_cluster_only():
    assert prettify_category({"sub_category": "Sandals", "gender": "F"}) == "Women's Sandals"
    assert prettify_category({"sub_category": "Sneakers", "age_group": "kids"}) == "Kids' Sneakers"  # age outranks
    assert prettify_category({"cluster": "Footwear"}) == "Footwear"
    assert prettify_category(None) == "" and prettify_category({}) == ""


def test_group_runs_groups_by_leg_and_sums():
    runs = group_runs(_LEDGER["transfers"])
    assert [(r["from_store"], r["to_store"]) for r in runs] == [("WH", "N1"), ("N3", "N2")]
    wh = runs[0]
    assert wh["units"] == 5 and wh["variants"] == 2 and wh["leg_cost"] == 15.0


# --- the whole report, from intent ---------------------------------------------------------------


def test_render_report_is_operator_facing_and_safe():
    html = render.render_report(_LEDGER, brand="Test Retail", title="Daily Report", as_of="2026-01-02")
    # the point is in the header
    assert "What to move today" in html and "Daily Report" in html and "2026-01-02" in html
    # summary skeleton
    assert "<b>3</b>" in html and "moves" in html
    # one run section per physical leg
    assert html.count("class='run'") == 2
    # the geometry's RAW tokens never reach the operator; the humanized phrase does
    assert "INVENTORY:" not in html and "SPATIAL:" not in html
    assert "low cover" in html and "below target" in html and "selling fast" in html
    # each bank's chip carries its stable colour class (color-as-mnemonic)
    assert "chip-inv" in html and "chip-spatial" in html and "chip-velocity" in html
    # a read that fully abstained shows an em dash, not an empty cell
    assert "—" in html
    # one consistent white ground — the corporate-report standard, no dark-mode auto-switch
    assert "prefers-color-scheme" not in html and "--bg:#ffffff" in html
    # empty reorders reads as a clean sentence, not a blank
    assert "No reorders" in html


def test_render_report_escapes_untrusted_values():
    poisoned = {
        "transfers": [
            {
                "article": "<script>evil</script>",
                "color": "x",
                "size": "1",
                "from_store": "A",
                "to_store": "B",
                "qty": 1,
                "cost_min": 1.0,
                "reason": None,
            }
        ],
        "summary": {},
        "reorders": [],
        "reasoning": {},
    }
    html = render.render_report(poisoned, brand="B", title="T")
    assert "<script>evil</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_report_writes_html_end_to_end(tmp_path):
    """The real command path: a synthetic OPERATIONAL ledger on disk → build_report (no refresh) → a written
    HTML file. build_report renders the ledger's `routing` section."""
    ledger = tmp_path / "operational.json"
    ledger.write_text(json.dumps({"domain": "operational", "routing": _LEDGER}), encoding="utf-8")
    out = tmp_path / "report.html"
    written = build_report(out_path=str(out), ledger_path=str(ledger), refresh=False, as_of="2026-01-03")
    assert written == str(out) and out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("<!doctype html>") and "What to move today" in body and "low cover" in body
