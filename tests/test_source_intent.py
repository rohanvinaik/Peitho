"""Hand-authored INTENT test for peitho.source.parse_report_table — the generic positional-report parser.

The Detective synth suite pins the structural branches (empty, missing columns, subtotal drop, first-wins,
blank key/value) mutation-complete over the default identity cast. This pins the `cast` branch Detective
cannot synthesise (a callable is not `--input`-expressible): a cast that coerces, and one that REJECTS the
value (dropping the row rather than crashing).
"""

from peitho.source import parse_report_table

_HEADER = ["total_mode", "item_code", "retail_price"]


def test_cast_coerces_the_value():
    rows = [_HEADER, [0, "A1", "1690.000"]]
    assert parse_report_table(rows, "item_code", "retail_price", float) == {"A1": 1690.0}


def test_cast_that_rejects_a_value_drops_the_row_not_crashes():
    rows = [_HEADER, [0, "A1", "not-a-number"], [0, "A2", "42.0"]]
    # float("not-a-number") raises ValueError → suppressed → A1 dropped, A2 kept
    assert parse_report_table(rows, "item_code", "retail_price", float) == {"A2": 42.0}


def test_str_strip_cast_trims_the_stored_value():
    rows = [["total_mode", "item_code", "supplier"], [0, "A1", "  ACME  "]]
    assert parse_report_table(rows, "item_code", "supplier", str.strip) == {"A1": "ACME"}
