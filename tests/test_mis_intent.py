"""Hand-authored INTENT tests for peitho.mis — the conventional MIS reports as substrate projections.

The Detective synth suites pin what the KPI decisions DO; these pin what they MEAN, and check the
load-bearing property of the whole layer: each report row carries the flat business facts AND the
signed-ternary position off a mined norm (the geometry read), from the same substrate — never a fused score.
"""

from __future__ import annotations

from peitho.grid import Cell, Grid
from peitho.mis import (
    abc_class,
    abc_summary,
    age_bucket,
    avg_selling_price,
    category_mis,
    contribution_pct,
    cover_band,
    gmroi,
    margin_pct,
    markup_pct,
    segment_mis,
    sell_through_pct,
    store_performance,
    turnover,
    vendor_mis,
)


def test_turnover_intent():
    assert turnover(10, 5) == 2.0  # sold twice what is held
    assert turnover(5, 0) == 5.0  # nothing held but sold five — everything on hand moved and then some
    assert turnover(0, 0) == 0.0  # nothing sold, nothing held


def test_margin_pct_intent():
    assert margin_pct(100.0, 60.0) == 40.0  # 40% gross margin
    assert margin_pct(100.0, 0.0) == 100.0  # no cost → full margin
    assert margin_pct(0.0, 10.0) is None  # no revenue → margin undefined, not zero


def test_sell_through_pct_intent():
    assert sell_through_pct(5, 5) == 50.0  # half of what passed through sold
    assert sell_through_pct(10, 0) == 100.0  # everything sold
    assert sell_through_pct(0, 0) is None  # nothing passed through → undefined


def _cell(store, stock, sold, revenue, cogs):
    return Cell(
        store=store, stock=stock, sale_qty=sold, recent_sales=sold, nrv=revenue, cogs=cogs, sls_age=(sold, 0, 0, 0, 0)
    )


def test_store_performance_pairs_flat_facts_with_the_signed_read():
    # three selling stores (all induce as RETAIL): a high, a middling, a low seller
    grid = Grid(
        {
            ("A", "BLK", "40"): {
                "HI": _cell("HI", stock=10, sold=100, revenue=100000.0, cogs=60000.0),
                "MID": _cell("MID", stock=10, sold=50, revenue=50000.0, cogs=30000.0),
                "LO": _cell("LO", stock=10, sold=10, revenue=10000.0, cogs=6000.0),
            }
        }
    )
    rep = store_performance(grid)
    assert rep["report"] == "store_performance"
    by_store = {r["store"]: r for r in rep["stores"]}
    assert set(by_store) == {"HI", "MID", "LO"}

    # the flat business facts are present per store
    hi = by_store["HI"]
    assert hi["units_sold"] == 100 and hi["revenue"] == 100000 and hi["margin_pct"] == 40.0
    assert hi["turnover"] == turnover(100, 10) and hi["sell_through_pct"] == sell_through_pct(100, 10)

    # AND the signed-ternary read off the mined norm — the geometry, native to the same row
    assert hi["sales_position"] == "above"  # the top seller is above the mined store norm
    assert by_store["LO"]["sales_position"] == "below"  # the laggard is below it
    assert all(r["sales_position"] in ("above", "at", "below") for r in rep["stores"])
    # the norm the positions are read against is reported, so the read is auditable
    assert isinstance(rep["norm_revenue"], int)
    # the enriched conventional facts ride on the same row
    assert hi["revenue_share_pct"] is not None and hi["avg_selling_price"] == 1000  # 100000/100
    assert "gmroi" in hi


# --- the new conventional scalar KPIs (each Detective-pinned; here their MEANING) ---


def test_new_scalar_kpis_intent():
    assert gmroi(4000.0, 8000.0) == 0.5  # $0.50 margin per $1 inventory at cost
    assert gmroi(4000.0, 0.0) is None  # no inventory held → undefined
    assert contribution_pct(25.0, 100.0) == 25.0
    assert contribution_pct(1.0, 0.0) is None  # no whole → undefined
    assert markup_pct(150.0, 100.0) == 50.0  # 50% markup ON COST (distinct from margin on revenue)
    assert markup_pct(150.0, 0.0) is None
    assert avg_selling_price(1000.0, 8) == 125  # ASP = revenue / units, rounded
    assert avg_selling_price(1000.0, 0) is None  # nothing sold → undefined


def test_age_bucket_thresholds():
    assert [age_bucket(x) for x in (None, 10, 90, 180, 365, 400)] == [
        "UNKNOWN",
        "FRESH",
        "CURRENT",
        "AGING",
        "STALE",
        "DEAD",
    ]


def test_cover_band_thresholds():
    assert [cover_band(x) for x in (None, 0, 14, 60, 180, 1000)] == [
        "UNKNOWN",
        "STOCKOUT",
        "FAST",
        "HEALTHY",
        "SLOW",
        "OVERSTOCK",
    ]


def test_abc_class_pareto_cuts():
    assert [abc_class(x) for x in (50.0, 80.0, 90.0, 95.0, 99.0)] == ["A", "A", "B", "B", "C"]


# --- the rollup aggregators (I/O-free over the grid / nodes) ---


def _cat_of(article):
    return {"A": "Shoes", "B": "Shoes", "C": "Bags"}.get(article)


def _sup_of(article):
    return {"A": "ACME", "B": "ACME", "C": "BETA"}.get(article)


def _mis_grid():
    return Grid(
        {
            ("A", "BLK", "40"): {"N8": _cell("N8", stock=5, sold=100, revenue=100000.0, cogs=60000.0)},
            ("B", "RED", "39"): {"N8": _cell("N8", stock=5, sold=20, revenue=20000.0, cogs=12000.0)},
            ("C", "TAN", "M"): {"N8": _cell("N8", stock=5, sold=5, revenue=5000.0, cogs=3000.0)},
        }
    )


def test_category_mis_rolls_by_cluster_with_shares():
    rep = category_mis(_mis_grid(), _cat_of)
    assert rep["report"] == "category_mis"
    by = {r["category"]: r for r in rep["categories"]}
    assert set(by) == {"Shoes", "Bags"}
    assert by["Shoes"]["units_sold"] == 120 and by["Shoes"]["revenue"] == 120000 and by["Shoes"]["items"] == 2
    assert rep["categories"][0]["category"] == "Shoes"  # ranked by revenue
    assert round(sum(r["revenue_share_pct"] for r in rep["categories"])) == 100


def test_vendor_mis_top_skus_and_skips_unknown_vendor():
    rep = vendor_mis(_mis_grid(), _sup_of)
    by = {r["vendor"]: r for r in rep["vendors"]}
    assert set(by) == {"ACME", "BETA"}
    assert by["ACME"]["top_skus"][0]["article"] == "A"  # ACME's biggest SKU by revenue
    assert by["ACME"]["items"] == 2
    # an article with no known supplier is not a vendor line
    solo = Grid({("Z", "x", "1"): {"N8": _cell("N8", 1, 1, 100.0, 50.0)}})
    assert vendor_mis(solo, lambda a: None)["vendors"] == []


def test_abc_summary_pareto_breakdown():
    rep = abc_summary(_mis_grid())
    assert rep["report"] == "abc_summary"
    assert sum(rep["counts"].values()) == 3  # every article classed
    assert rep["counts"]["A"] >= 1
    assert rep["a_items"][0]["article"] == "A"  # the vital-few leader


def test_segment_mis_rolls_by_segment():
    nodes = [
        {"segment": "CHAMPION", "rfm": {"monetary": 8000, "frequency": 5, "recency_days": 10}},
        {"segment": "CHAMPION", "rfm": {"monetary": 6000, "frequency": 3, "recency_days": 20}},
        {"segment": "DORMANT", "rfm": {"monetary": 500, "frequency": 1, "recency_days": 300}},
    ]
    rep = segment_mis(nodes)
    by = {r["segment"]: r for r in rep["segments"]}
    assert by["CHAMPION"]["customers"] == 2 and by["CHAMPION"]["avg_monetary"] == 7000
    assert by["CHAMPION"]["avg_recency_days"] == 15
    assert round(sum(r["share_pct"] for r in rep["segments"])) == 100
