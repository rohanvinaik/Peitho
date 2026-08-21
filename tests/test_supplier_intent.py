"""Hand-authored INTENT tests for peitho.lenses.supplier — the supplier sell-through lens."""

from peitho.lenses.supplier import sell_through, supplier_band
from peitho.source import parse_report_table


def test_sell_through_ratio():
    assert sell_through(89, 100) == 0.89  # sold 89 of 100 purchased
    assert sell_through(0, 100) == 0.0  # bought, sold nothing = dead stock
    assert sell_through(200, 100) == 2.0  # drawing down earlier-window stock
    assert sell_through(5, 0) is None  # nothing purchased -> undefined, not 0


def test_supplier_band_ordinal_from_deviation():
    assert supplier_band(0.5) == "STRONG_SELLER"  # well above the norm
    assert supplier_band(0.0) == "NORMAL"  # at the peer norm
    assert supplier_band(-0.3) == "SLOW"  # below
    assert supplier_band(-0.8) == "DEAD_STOCK"  # ≥50% below the norm — stop buying
    assert supplier_band(0.15) == "STRONG_SELLER"  # boundary
    assert supplier_band(-0.5) == "DEAD_STOCK"  # boundary (not > -0.5)


def test_supplier_band_dead_stock_vs_left_unsold():
    # In the deadest band, "sitting" and "gone without a sale" are DIFFERENT facts — not one code.
    assert supplier_band(-0.8, stock_left=500, sold=0) == "DEAD_STOCK"  # 0 sold, stock REMAINS -> sitting
    assert supplier_band(-0.8, stock_left=0, sold=0) == "LEFT_UNSOLD"  # 0 sold, 0 remains -> exited unsold (RTV/xfer)
    assert supplier_band(-0.8, stock_left=0, sold=50) == "DEAD_STOCK"  # SOME sold -> still dead-stock
    assert supplier_band(-0.8) == "DEAD_STOCK"  # no stock/sold info -> back-compatible pure ordinal
    # the split only applies in the deadest band, never above it
    assert supplier_band(0.5, stock_left=0, sold=0) == "STRONG_SELLER"


def test_article_supplier_map_flattens_vender_wise_grouped_report():
    # the per-article→supplier edge is parsed by the public parse_report_table; the backend column names
    # ("item_code", "supplier") are supplied by the cassette's adapter. Detail rows total_mode==0 carry
    # supplier+article on EVERY row; subtotals total_mode==1 drop; first non-blank supplier per article wins.
    rows = [
        ["total_mode", "org_rowno", "supplier", "item_code", "color"],  # header (row 0)
        [0, 1, "A.T. Exports", "ATB006511F", "BLACK"],  # detail
        [0, 2, "A.T. Exports", "ATB006511F", "TAN"],  # same article, 2nd colour/loc — same supplier
        [1, 3, "A.T. Exports Total", "ATB006511F Total", None],  # article subtotal — dropped
        [0, 4, "", "ORPHAN-1", "RED"],  # blank supplier (unassigned legacy stock) — skipped
        [0, 5, "B.Corp", "BX-99", "BLUE"],  # another supplier
        [1, 6, "Grand Total", None, None],  # grand total — dropped
    ]
    m = parse_report_table(rows, "item_code", "supplier", str.strip)
    assert m == {"ATB006511F": "A.T. Exports", "BX-99": "B.Corp"}
    assert parse_report_table([], "item_code", "supplier") == {}  # no data
    assert parse_report_table([["total_mode", "x"]], "item_code", "supplier") == {}  # missing cols -> empty
