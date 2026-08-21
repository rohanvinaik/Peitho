"""peitho.mis — conventional management-information reports, as projections of the one substrate.

The routine business reports an operator expects — store performance, stock movement, vendor MIS, the
standard KPIs — built NOT as a separate raw-compute path but as additional shadow-ledger projections of
the same node-network substrate the routing / restock / outlier systems already read. Every row carries
two things at once: the **flat facts** a conventional stats package gives (units, revenue, turnover,
sell-through, the period breakdown), and — from the same substrate, for free — the **signed-ternary
position off a mined zero** (below / at / above the norm) that a flat report structurally cannot produce.

That pairing is the point. A business keeps its ordinary processes and gets its ordinary reports trivially
out of this; the geometry's intelligence (which store, which vendor, which line is anomalous) is native to
the very same substrate, not a bolt-on. The substrate subsumes the conventional schema rather than sitting
beside it — the flywheel that validates the approach: if the boring reports fall out for free, the
apparatus underneath is doing real, general work.

Discipline: the flat facts are descriptive projections; the only "significance" here is the signed-ternary
position off a mined zero (`position.deviation_position` over `network.mine_sales_zero`, the same primitive
the banks use — symmetric `+1 above / −1 below / 0 at-norm`), never a fused `[0,1]` health score. These
decisions are pure and pinned; the aggregation is I/O.
"""

from __future__ import annotations

from . import network
from .grid import Grid
from .lenses import inventory
from .noticer import DEFAULT_TOL
from .position import deviation_position


def turnover(units_sold: int, units_held: int) -> float:
    """Stock-turn: units sold over units currently held (the classic inventory-turnover ratio, at the
    grain measured). `0` held with sales → the sold count itself (everything on hand moved and more);
    `0`/`0` → `0.0`. Pure over two ints — a descriptive ratio, not a verdict."""
    if units_held <= 0:
        return float(units_sold)
    return round(units_sold / units_held, 3)


def margin_pct(revenue: float, cogs: float) -> float | None:
    """Gross margin as a percentage of revenue: `(revenue − cogs) / revenue × 100`. `None` when there is
    no revenue to take a margin on (undefined, not zero). Pure over two floats."""
    if revenue <= 0:
        return None
    return round((revenue - cogs) / revenue * 100, 1)


def sell_through_pct(units_sold: int, units_held: int) -> float | None:
    """Sell-through: units sold as a percentage of everything that passed through (sold + still held, the
    available proxy when receipts are not landed). `None` when nothing passed through. Pure over two ints."""
    total = units_sold + units_held
    if total <= 0:
        return None
    return round(units_sold / total * 100, 1)


def gmroi(gross_margin: float, avg_inventory_cost: float) -> float | None:
    """Gross-Margin Return On Inventory Investment: gross margin earned per unit of inventory value held at
    cost (`gross_margin / avg_inventory_cost`) — the classic retail capital-efficiency ratio. `None` when no
    inventory is held (undefined, not zero). Pure over two floats; a descriptive ratio, not a verdict."""
    if avg_inventory_cost <= 0:
        return None
    return round(gross_margin / avg_inventory_cost, 2)


def contribution_pct(part: float, whole: float) -> float | None:
    """A part's share of the whole, as a percentage (`part / whole × 100`) — a store's share of chain revenue,
    a vendor's or a category's share of sales. `None` when the whole is empty (undefined). Pure over two floats."""
    if whole <= 0:
        return None
    return round(part / whole * 100, 1)


def markup_pct(retail: float, cost: float) -> float | None:
    """Markup on cost: `(retail − cost) / cost × 100` — margin expressed on the cost base, distinct from
    `margin_pct` (which is on revenue). `None` when there is no cost base. Pure over two floats."""
    if cost <= 0:
        return None
    return round((retail - cost) / cost * 100, 1)


def avg_selling_price(revenue: float, units: int) -> float | None:
    """Average selling price (ASP): realized revenue per unit sold (`revenue / units`). `None` when nothing
    sold (undefined). Pure over a float and an int."""
    if units <= 0:
        return None
    return round(revenue / units)


def age_bucket(age_days: int | None) -> str:
    """The conventional shelf-age band, by fixed operational day-thresholds — a business CONVENTION, not a
    mined-zero significance read: FRESH ≤30, CURRENT ≤90, AGING ≤180, STALE ≤365, DEAD >365; UNKNOWN when the
    age is missing. Pure over an int-or-None → a named string code."""
    if age_days is None:
        return "UNKNOWN"
    if age_days <= 30:
        return "FRESH"
    if age_days <= 90:
        return "CURRENT"
    if age_days <= 180:
        return "AGING"
    if age_days <= 365:
        return "STALE"
    return "DEAD"


def cover_band(days_of_cover: float | None) -> str:
    """The conventional stock-cover band, by fixed operational thresholds — a business CONVENTION, not a mined
    significance read: STOCKOUT ≤0, FAST ≤14 days, HEALTHY ≤60, SLOW ≤180, OVERSTOCK >180; UNKNOWN when cover
    is undefined. Pure over a float-or-None → a named string code."""
    if days_of_cover is None:
        return "UNKNOWN"
    if days_of_cover <= 0:
        return "STOCKOUT"
    if days_of_cover <= 14:
        return "FAST"
    if days_of_cover <= 60:
        return "HEALTHY"
    if days_of_cover <= 180:
        return "SLOW"
    return "OVERSTOCK"


def abc_class(cumulative_revenue_pct: float) -> str:
    """The Pareto ABC class from an item's position in the cumulative-revenue curve (items ranked high→low
    revenue): A while the running cumulative share is ≤80%, B ≤95%, C the long tail beyond — the standard
    80/95 cuts. A descriptive Pareto bucketing, not a significance read. Pure over a float."""
    if cumulative_revenue_pct <= 80.0:
        return "A"
    if cumulative_revenue_pct <= 95.0:
        return "B"
    return "C"


def store_performance(grid: Grid) -> dict:
    """The store-performance report as a substrate projection: per selling node, the flat facts (units,
    revenue, cost, stock held, turnover, margin, sell-through, and the sales-age period breakdown that
    proxies MTD/YTD until bill-level dates land) AND the signed-ternary SALES position off the mined
    store-revenue zero — `+1` a node selling above the typical node, `−1` below, `0` at the norm. The
    position reuses the exact substrate primitives (`network.mine_sales_zero` for the norm +
    `position.deviation_position` for the signed read) the banks run on, so the "which stores are anomalous"
    read is native, not re-derived.

    I/O-free aggregation over the grid; the pinned decisions it composes do the deciding."""
    coarse = inventory.coarse_roles(grid)
    agg: dict = {}
    for _variant, cells in grid.items():
        for store, c in cells.items():
            if inventory.node_role(store, coarse) != "RETAIL":
                continue  # the stock/warehouse nodes are the stock report's subject, not sales
            a = agg.setdefault(store, {"units": 0, "revenue": 0.0, "cogs": 0.0, "stock": 0, "age": [0, 0, 0, 0, 0]})
            a["units"] += c.sale_qty
            a["revenue"] += c.nrv
            a["cogs"] += c.cogs
            a["stock"] += c.stock
            for i in range(5):
                a["age"][i] += c.sls_age[i]

    revenue_by_store = {st: a["revenue"] for st, a in agg.items()}
    zero = network.mine_sales_zero(revenue_by_store)  # the mined median store revenue — the substrate zero
    total_revenue = sum(a["revenue"] for a in agg.values())  # the chain total, for each store's contribution share
    _SIGN = {1: "above", -1: "below", 0: "at"}

    def _row(st: str, a: dict) -> dict:
        gross_margin = a["revenue"] - a["cogs"]
        avg_unit_cost = a["cogs"] / a["units"] if a["units"] else 0.0  # sold-cost proxy for the held inventory
        inventory_cost = a["stock"] * avg_unit_cost
        return {
            "store": st,
            "units_sold": a["units"],
            "revenue": round(a["revenue"]),
            "cogs": round(a["cogs"]),
            "margin_pct": margin_pct(a["revenue"], a["cogs"]),
            "stock_held": a["stock"],
            "turnover": turnover(a["units"], a["stock"]),
            "sell_through_pct": sell_through_pct(a["units"], a["stock"]),
            "avg_selling_price": avg_selling_price(a["revenue"], a["units"]),
            "revenue_share_pct": contribution_pct(a["revenue"], total_revenue),  # store's % of chain revenue
            "gmroi": gmroi(gross_margin, inventory_cost),  # margin per unit of inventory held at cost (proxy)
            "by_age_days": a["age"],  # [<=30, 31-60, 61-90, 91-120, >=121] — the MTD/YTD proxy
            "recent_30d_units": a["age"][0],
            # the substrate read, free from the same primitives the router uses:
            "sales_position": _SIGN[deviation_position("SALES", a["revenue"], zero, DEFAULT_TOL).sign],
        }

    rows = [_row(st, a) for st, a in sorted(agg.items(), key=lambda kv: -kv[1]["units"])]  # sort on typed int units
    return {
        "report": "store_performance",
        "norm_revenue": round(zero),  # the mined store-revenue zero the positions are read against
        "stores": rows,
        "notes": (
            "by_age_days = units sold in the 30/60/90/120/121+ day windows (the MTD/YTD proxy until "
            "bill-level dates land). sales_position is the signed-ternary read off the mined norm — the same "
            "substrate primitive the routing geometry uses, here at store grain. Targets, when supplied by "
            "the cassette, add a target-vs-achievement position alongside this one."
        ),
    }


def category_mis(grid: Grid, category_of) -> dict:
    """The conventional category-performance table as a substrate projection: per product category (cluster),
    the units, revenue, cost, gross margin, turnover, sell-through, distinct items, and share of chain revenue —
    aggregated over the grid, ranked by revenue. `category_of(article)` returns the cluster label (or None →
    'unadjudicated'). I/O-free aggregation; the pinned KPI functions do the arithmetic."""
    agg: dict = {}
    for (article, _color, _size), cells in grid.items():
        cat = category_of(article) or "unadjudicated"
        a = agg.setdefault(cat, {"units": 0, "revenue": 0.0, "cogs": 0.0, "stock": 0, "articles": set()})
        a["articles"].add(article)
        for c in cells.values():
            a["units"] += c.sale_qty
            a["revenue"] += c.nrv
            a["cogs"] += c.cogs
            a["stock"] += c.stock
    total_revenue = sum(a["revenue"] for a in agg.values())
    rows = [
        {
            "category": cat,
            "items": len(a["articles"]),
            "units_sold": a["units"],
            "revenue": round(a["revenue"]),
            "cogs": round(a["cogs"]),
            "gross_margin": round(a["revenue"] - a["cogs"]),
            "margin_pct": margin_pct(a["revenue"], a["cogs"]),
            "stock_held": a["stock"],
            "turnover": turnover(a["units"], a["stock"]),
            "sell_through_pct": sell_through_pct(a["units"], a["stock"]),
            "revenue_share_pct": contribution_pct(a["revenue"], total_revenue),
        }
        for cat, a in sorted(agg.items(), key=lambda kv: -kv[1]["revenue"])
    ]
    return {"report": "category_mis", "categories": rows}


def vendor_mis(grid: Grid, supplier_of, top_skus: int = 5) -> dict:
    """The conventional vendor MIS as a substrate projection: per supplier, the units, revenue, cost, gross
    margin, turnover, sell-through, distinct items, share of chain revenue, and the top SKUs by revenue —
    aggregated over the grid. `supplier_of(article)` returns the vendor (or None → the item is skipped: no known
    supplier is not a vendor line). I/O-free aggregation; this is the sales-side vendor view, distinct from the
    purchase-feed sell-through in the operational ledger's `suppliers` section."""
    agg: dict = {}
    for (article, _color, _size), cells in grid.items():
        vendor = supplier_of(article)
        if not vendor:
            continue
        a = agg.setdefault(
            vendor, {"units": 0, "revenue": 0.0, "cogs": 0.0, "stock": 0, "articles": set(), "sku_rev": {}}
        )
        a["articles"].add(article)
        for c in cells.values():
            a["units"] += c.sale_qty
            a["revenue"] += c.nrv
            a["cogs"] += c.cogs
            a["stock"] += c.stock
            a["sku_rev"][article] = a["sku_rev"].get(article, 0.0) + c.nrv
    total_revenue = sum(a["revenue"] for a in agg.values())
    rows = []
    for vendor, a in sorted(agg.items(), key=lambda kv: -kv[1]["revenue"]):
        top = sorted(a["sku_rev"].items(), key=lambda kv: -kv[1])[:top_skus]
        rows.append(
            {
                "vendor": vendor,
                "items": len(a["articles"]),
                "units_sold": a["units"],
                "revenue": round(a["revenue"]),
                "cogs": round(a["cogs"]),
                "gross_margin": round(a["revenue"] - a["cogs"]),
                "margin_pct": margin_pct(a["revenue"], a["cogs"]),
                "stock_held": a["stock"],
                "turnover": turnover(a["units"], a["stock"]),
                "sell_through_pct": sell_through_pct(a["units"], a["stock"]),
                "revenue_share_pct": contribution_pct(a["revenue"], total_revenue),
                "top_skus": [{"article": art, "revenue": round(r)} for art, r in top],
            }
        )
    return {"report": "vendor_mis", "vendors": rows}


def abc_summary(grid: Grid, top_a: int = 50) -> dict:
    """The Pareto ABC breakdown as a substrate projection: rank articles by revenue (high→low), walk the
    cumulative-revenue curve, and class each A (≤80% cumulative) · B (≤95%) · C (the long tail) via `abc_class`.
    Returns the per-class item counts + revenue share, and the vital-few A list (capped). I/O-free aggregation."""
    rev: dict = {}
    for (article, _color, _size), cells in grid.items():
        rev[article] = rev.get(article, 0.0) + sum(c.nrv for c in cells.values())
    ranked = sorted(rev.items(), key=lambda kv: -kv[1])
    total = sum(r for _a, r in ranked) or 1.0
    counts = {"A": 0, "B": 0, "C": 0}
    class_rev = {"A": 0.0, "B": 0.0, "C": 0.0}
    a_items: list = []
    cumulative = 0.0
    for article, r in ranked:
        cumulative += r
        cls = abc_class(cumulative / total * 100)
        counts[cls] += 1
        class_rev[cls] += r
        if cls == "A" and len(a_items) < top_a:
            a_items.append(
                {"article": article, "revenue": round(r), "cumulative_pct": round(cumulative / total * 100, 1)}
            )
    return {
        "report": "abc_summary",
        "counts": counts,
        "revenue_share_pct": {cls: contribution_pct(class_rev[cls], total) for cls in ("A", "B", "C")},
        "a_items": a_items,
    }


def segment_mis(nodes: list) -> dict:
    """The conventional customer-segment table as a substrate projection: per mined RFM segment, the customer
    count, share of the base, and the average monetary / frequency / recency — over the pseudonymous customer
    nodes. The segment itself is the mined-deviation read (the geometry); this is the descriptive rollup of it.
    I/O-free aggregation."""
    agg: dict = {}
    for n in nodes:
        seg = n["segment"]
        r = n["rfm"]
        a = agg.setdefault(seg, {"count": 0, "monetary": 0.0, "frequency": 0, "recency_sum": 0.0, "recency_n": 0})
        a["count"] += 1
        a["monetary"] += r.get("monetary") or 0
        a["frequency"] += r.get("frequency") or 0
        if r.get("recency_days") is not None:
            a["recency_sum"] += r["recency_days"]
            a["recency_n"] += 1
    total = len(nodes)
    rows = [
        {
            "segment": seg,
            "customers": a["count"],
            "share_pct": contribution_pct(a["count"], total),
            "avg_monetary": round(a["monetary"] / a["count"]) if a["count"] else None,
            "avg_frequency": round(a["frequency"] / a["count"], 1) if a["count"] else None,
            "avg_recency_days": round(a["recency_sum"] / a["recency_n"]) if a["recency_n"] else None,
        }
        for seg, a in sorted(agg.items(), key=lambda kv: -kv[1]["count"])
    ]
    return {"report": "segment_mis", "segments": rows}
