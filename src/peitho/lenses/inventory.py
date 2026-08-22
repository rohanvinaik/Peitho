"""peitho.lenses.inventory — the INVENTORY watcher (pure data geometry, no AI).

Two views, both pure data geometry (no AI, no stochastic component):
  - LIVE shortages — a variant stocked out at a *selling* node with *recent* demand (a lost sale right
    now). Hard-rule, no tuned threshold: stock==0 AND recent sales.
  - GRADED urgency — a cell running *below its store's own baseline cover* while selling, catching
    'about to stock out' before it does. The baseline (the zero-mean) is MINED FROM THE DATA — each
    store's median days-of-cover among its healthy selling cells — never hand-set.

Governing invariant (THEORY.md): the geometry *notices*; every number emitted is the authoritative pull's
own figure. Significance is a signed deviation from a data-mined zero-mean.

Data source: the active cassette's per-store variant grid (via the data-input adapter, `peitho.source`);
the default pull window is a current-FY-to-date span of WINDOW_DAYS.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from peitho import network as _network  # the data-induced node network (roster + roles from the cassette)

from ..grid import Grid
from ..source import load_grid as _load_grid
from . import spatial

# Store roles — DATA, from the active cassette's network (peitho.network). The coarse RETAIL/WAREHOUSE
# split is induced from the sales geometry: a node that holds stock but sells ~nothing is a WAREHOUSE
# source, every node that sells is a RETAIL sink (the transfer SINKS). This reproduces the hand-mined
# model exactly and re-derives it whenever the data changes (a warehouse that starts selling flips role).
_NS = _network.active_network()
_WH = _NS.warehouse_nodes()
# In ROSTER order (not sorted): this is the historical store-load order load_grid relies on — the grid's
# variant insertion order (and thus every downstream tie-break) follows it.
RETAIL = tuple(n for n in _NS.nodes if n not in _WH)  # selling nodes — the transfer SINKS
WAREHOUSE = tuple(n for n in _NS.nodes if n in _WH)  # zero-sales source(s): holds stock, all spare
# Routing sources are NOT a fixed set: plan_transfers gives from ANY node holding spare — including a retail
# store with surplus (→ store-to-store reconciliation). The warehouse is never a transfer DESTINATION: its
# velocity is ~0 → target 0 → it reserves nothing and can never register a deficit. (This replaced a dead
# `SOURCE_NODES` constant that wrongly implied a fixed warehouse-only source set.)
# The default pull-window span in days (a real cassette can set its own reporting window).
WINDOW_DAYS = 120


def store_sales(grid: Grid) -> dict:
    """Per-store total window sales across every variant — the signal the coarse role is INDUCED from (a
    node that never sells is a warehouse source). I/O-free projection over the grid."""
    sales: dict = {}
    for _v, cells in grid.items():
        for store, c in cells.items():
            sales[store] = sales.get(store, 0) + (c.sale_qty or 0)
    return sales


def coarse_roles(grid: Grid) -> dict:
    """The grid-INDUCED coarse role map {store: RETAIL|WAREHOUSE} — signed-ternary role induction over each
    store's total sales (peitho.network). Computed once per grid, then handed to `node_role`. I/O-free."""
    return _network.induce_coarse_roles(store_sales(grid))


def node_role(store: str, coarse: dict) -> str:
    """The store's coarse role, read from the grid-induced `coarse` map (`coarse_roles`): RETAIL / WAREHOUSE
    for a node the data classifies, UNKNOWN for a store absent from the data (dead / never landed — the
    node-death case). Pure over (store, map)."""
    return coarse.get(store, "UNKNOWN")


def classify_cell(stock: int, recent_sales: int, total_sales: int, role: str) -> str:
    """The pure inventory decision for one variant×store cell → a named status code.

    Total function over scalars (Detective-pinnable). Named codes, never a bare bool, because
    'stocked out and selling' and 'stocked out but dead' are different facts, not one truthy check.

      LIVE_SHORTAGE : stock==0 at a selling node with demand in the last 30 days  → act now
      STALE_OUT     : stock==0, sold this window but not recently                 → low priority
      EMPTY         : stock==0, never sold this window                            → ignore
      IDLE_STOCK    : stock>0 but never sold this window                          → surplus / destash candidate
      STOCKED       : stock>0 and sold                                            → healthy
    """
    if stock <= 0:
        if recent_sales > 0 and role == "RETAIL":
            return "LIVE_SHORTAGE"
        if total_sales > 0:
            return "STALE_OUT"
        return "EMPTY"
    if total_sales <= 0:
        return "IDLE_STOCK"
    return "STOCKED"


def velocity(sale_qty: int, window_days: int) -> float:
    """Units sold per day over the window. 0.0 when the window is empty (no division by zero)."""
    if window_days <= 0:
        return 0.0
    return sale_qty / window_days


# --- the sales-age velocity SPECTRUM: multi-horizon demand from the native sales-age ladder ---
# The drilldown gives sales bucketed by how-many-days-ago: (<=30, 31-60, 61-90, 91-120, >=121). The first
# four span 30 days each; the fifth (>=121) spans the window tail. A single window average COLLAPSES this —
# it cannot tell a fresh mover (mass in band 0) from a fader (mass in the old bands), which is exactly the
# distinction the operator reads by hand (their winners sit in the recent tail, below the flat-window gate).
# Recency weights are a TUNABLE POLICY (calibrate on feedback), never a fit — they favour recent demand
# without discarding the stable long-run signal. recent→old.
RECENCY_WEIGHTS_DEFAULT = (0.40, 0.25, 0.20, 0.10, 0.05)


def band_rates(sls_age, window_days: int = WINDOW_DAYS) -> tuple:
    """Per-band sells-per-day (NON-cumulative), recent→old: each 30-day sales-age bucket over its own 30-day
    span, and the >=121 tail over (window_days − 120). When window_days ≤ 120 the tail span is ≤ 0 — the
    >=121 band is OUT of window and contributes 0 (never a units/1-day inflation). The raw horizon signal.
    Pure over a 5-sequence + scalar; a fader and a fresh mover are distinguishable here, which `velocity`
    alone cannot do."""
    b = (tuple(int(x) for x in sls_age)[:5] + (0, 0, 0, 0, 0))[:5]
    tail = window_days - 120
    spans = (30, 30, 30, 30, tail)
    return tuple(b[i] / spans[i] if spans[i] > 0 else 0.0 for i in range(5))


def velocity_by_horizon(sls_age, window_days: int = WINDOW_DAYS) -> dict:
    """Cumulative sells-per-day at each sales-age horizon — the velocity ladder {30,60,90,120,window}→rate.
    The 30d rate is recent momentum; the widest equals `velocity(sum(sls_age), window)`. Pure."""
    b = (tuple(int(x) for x in sls_age)[:5] + (0, 0, 0, 0, 0))[:5]
    out: dict = {}
    cum = 0
    for i, h in enumerate((30, 60, 90, 120)):
        cum += b[i]
        out[h] = cum / h
    cum += b[4]
    out[window_days] = cum / window_days if window_days > 0 else 0.0
    return out


def recent_velocity(sls_age, weights=RECENCY_WEIGHTS_DEFAULT, window_days: int = WINDOW_DAYS) -> float:
    """Recency-weighted demand rate across the sales-age spectrum — the routing velocity signal. Weights
    recent bands higher so a fresh mover clears the gate while a fader (mass only in old bands, zero recent)
    does not — which a flat window average conflates. Weights are a tunable POLICY, not a fit. Pure over a
    5-sequence + weights + scalar."""
    r = band_rates(sls_age, window_days)
    w = (tuple(float(x) for x in weights)[:5] + (0.0, 0.0, 0.0, 0.0, 0.0))[:5]
    sw = sum(w)
    if sw <= 0:
        return 0.0
    return sum(r[i] * w[i] for i in range(5)) / sw


def cover_days(stock: int, sale_qty: int, window_days: int) -> float | None:
    """Days of stock remaining at the window's average velocity. None when there is no velocity
    (nothing sold → cover is undefined, not infinite). Pure over three scalars."""
    v = velocity(sale_qty, window_days)
    if v <= 0:
        return None
    return round(stock / v, 2)


def urgency_score(cover: float | None, baseline: float | None) -> float:
    """Graded shortage urgency in [0,1]: 1.0 at stockout (cover 0), 0.0 at/above the mined baseline
    cover, linear between. 0.0 when cover is undefined (not selling) or the baseline is unusable.
    Signed deviation below the data-mined zero-mean, clamped. Pure over two numbers."""
    if cover is None or baseline is None or baseline <= 0:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - cover / baseline)), 4)


def urgency_band(urgency: float) -> str:
    """Ordinal band for the report — named codes, never a bare bool. Total over any number."""
    if urgency >= 0.8:
        return "CRITICAL"
    if urgency >= 0.6:
        return "HIGH"
    if urgency >= 0.4:
        return "WATCH"
    return "OK"


@dataclass
class Shortage:
    variant: tuple  # (article, color, size)
    store: str  # the selling store that is stocked out
    recent_sales: int  # live demand signal
    window_sales: int
    surplus: list = field(default_factory=list)  # cost-ranked [(store, stock, role, cost_min)]


def load_grid(grid_dir: str | None = None) -> Grid:
    """Load the per-store grid via the shared `peitho.grid` abstraction (which delegates to the active
    cassette's data-input adapter), preserving inventory's historical store-list load order
    (RETAIL + WAREHOUSE). `grid_dir` overrides the adapter's default location when given."""
    return _load_grid(grid_dir, stores=list(RETAIL + WAREHOUSE))


def _default_min_cost() -> dict:
    """The SPATIAL backbone's all-pairs travel-cost, computed once. Placeholder costs today; swaps for
    a routing-API matrix without touching this module."""
    return spatial.all_pairs_min_cost(list(spatial.NODES), spatial.cost_matrix())


def rank_surplus(dest: str, sources: list, min_cost: dict) -> list:
    """Order surplus source cells [(store, stock, role)] by TRAVEL COST to `dest` (cheapest first),
    ties by larger stock then store name. Returns [(store, stock, role, cost), ...]. Pure over list+dict.
    (Role is carried for the human to judge 'don't deplete a seller'; the cost is what ranks.)"""
    scored = [(s, stk, role, min_cost.get((s, dest), float("inf"))) for (s, stk, role) in sources]
    scored.sort(key=lambda t: (t[3], -t[1], t[0]))
    return scored


def find_live_shortages(grid: Grid, min_cost: dict | None = None) -> list:
    """Every LIVE_SHORTAGE cell, each paired with the surplus nodes cost-ranked by travel to it.

    Pure over the loaded grid + cost matrix. Surplus = any node holding stock of the variant,
    ordered cheapest-to-move-from first (the SPATIAL backbone). Cells ranked by recent demand.
    """
    if min_cost is None:
        min_cost = _default_min_cost()
    coarse = coarse_roles(grid)  # grid-induced role map, once per grid
    out = []
    for variant, cells in grid.items():
        for store, c in cells.items():
            status = classify_cell(c.stock, c.recent_sales, c.sale_qty, node_role(store, coarse))
            if status != "LIVE_SHORTAGE":
                continue
            sources = [(s, o.stock, node_role(s, coarse)) for s, o in cells.items() if o.stock > 0]
            surplus = rank_surplus(store, sources, min_cost)
            out.append(Shortage(variant, store, c.recent_sales, c.sale_qty, surplus))
    out.sort(key=lambda s: -s.recent_sales)
    return out


def mine_store_baselines(grid: Grid, window_days: int = WINDOW_DAYS) -> dict:
    """The zero-mean, MINED FROM DATA: each store's DEMAND-WEIGHTED days-of-cover — total stock ÷
    total sell-rate over its selling cells (= window_days · Σstock / Σsold). This is the store's own
    aggregate operating norm; a cell's cover below it is the graded shortage signal.

    Why demand-weighted, not a plain median: a plain median cover is degenerate here — dominated by
    slow-movers (a '1 in stock, 1 sold in 137d' cell has cover=137), which inflates the baseline and
    flags everything faster as critical. Weighting by demand collapses to the aggregate cover, which
    reflects the stock that actually moves. (Per-section/seasonal baselines from history are a refinement.)
    """
    stock: dict = defaultdict(int)
    sold: dict = defaultdict(int)
    for cells in grid.values():
        for store, c in cells.items():
            if c.stock > 0 and c.sale_qty > 0:
                stock[store] += c.stock
                sold[store] += c.sale_qty
    return {s: round(window_days * stock[s] / sold[s], 2) for s in sold if sold[s] > 0}


def mine_store_velocity_baselines(grid: Grid, weights=RECENCY_WEIGHTS_DEFAULT, window_days: int = WINDOW_DAYS) -> dict:
    """The VELOCITY zero-mean, MINED FROM DATA: each store's DEMAND-WEIGHTED expected recent velocity —
    Σ(recent_velocity·units) ÷ Σ(units) over its selling cells. This is the recent per-day tempo experienced
    by the store's average sold unit; a cell selling faster than it is accelerating (a mover), slower is
    fading. Demand-weighted for the same reason as `mine_store_baselines`: a plain mean is dominated by the
    mass of near-zero cells and would read almost everything as "hot". (Per-section calibration is a refinement.)
    """
    num: dict = defaultdict(float)
    den: dict = defaultdict(int)
    for cells in grid.values():
        for store, c in cells.items():
            if c.sale_qty > 0:
                num[store] += recent_velocity(c.sls_age, weights, window_days) * c.sale_qty
                den[store] += c.sale_qty
    return {s: round(num[s] / den[s], 4) for s in den if den[s] > 0}


def load_article_sections(taxonomy: str | None = None) -> dict:
    """{article: section} — the merchandise section per article — via the active cassette's adapter."""
    from .. import source

    return source.adapter().load_article_sections(taxonomy)


def mine_category_baselines(grid: Grid, sections: dict, window_days: int = WINDOW_DAYS) -> dict:
    """The zero-mean at a FINER grain: demand-weighted days-of-cover per **(store, SECTION)** (DESIGN §5:
    store×category), so a cell is judged against its OWN category's norm rather than the store's fast/slow-
    blended average — a slow-category item is no longer flagged 'critical' merely for being below a store
    average dominated by fast movers. Articles absent from the taxonomy → section '?' (they fall back to the
    store baseline at lookup). (The full DESIGN target adds a SEASON dimension — deferred, ties to the
    campaign-grounding layer.)"""
    stock: dict = defaultdict(int)
    sold: dict = defaultdict(int)
    for variant, cells in grid.items():
        key_sec = sections.get(variant[0], "?")
        for store, c in cells.items():
            if c.stock > 0 and c.sale_qty > 0:
                stock[(store, key_sec)] += c.stock
                sold[(store, key_sec)] += c.sale_qty
    return {k: round(window_days * stock[k] / sold[k], 2) for k in sold if sold[k] > 0}


@dataclass
class GradedShortage:
    variant: tuple
    store: str
    cover: float | None  # days of stock left (0 = out)
    urgency: float  # [0,1], signed deviation below the mined baseline
    band: str  # CRITICAL / HIGH / WATCH
    recent_sales: int  # last-30-day demand
    priority: float  # urgency × recent demand — what to act on first
    surplus: list = field(default_factory=list)


def find_graded_shortages(
    grid: Grid,
    baselines: dict,
    min_cost: dict | None = None,
    window_days: int = WINDOW_DAYS,
    min_urgency: float = 0.4,
    category_baselines: dict | None = None,
    sections: dict | None = None,
) -> list:
    """Retail cells with live demand running below their store's baseline cover — a superset of the
    hard stockout view that also catches 'about to stock out'. Ranked by urgency × recent demand;
    each shortage's surplus sources cost-ranked (cheapest-to-move-from first) via the SPATIAL backbone.
    `min_urgency` is the band floor to surface (0.4 = WATCH), not the zero-mean (that is mined).
    """
    if min_cost is None:
        min_cost = _default_min_cost()
    coarse = coarse_roles(grid)  # grid-induced role map, once per grid
    out = []
    for variant, cells in grid.items():
        for store, c in cells.items():
            if node_role(store, coarse) != "RETAIL" or c.recent_sales <= 0:
                continue
            cover = cover_days(c.stock, c.sale_qty, window_days)
            # finer (store, section) baseline when supplied, else the store baseline; sparse categories
            # (or articles absent from the taxonomy) fall back to the store baseline.
            if category_baselines is not None and sections is not None:
                bl = category_baselines.get((store, sections.get(variant[0], "?"))) or baselines.get(store)
            else:
                bl = baselines.get(store)
            u = urgency_score(cover, bl)
            if u < min_urgency:
                continue
            sources = [(s, o.stock, node_role(s, coarse)) for s, o in cells.items() if o.stock > 0 and s != store]
            surplus = rank_surplus(store, sources, min_cost)
            out.append(
                GradedShortage(
                    variant,
                    store,
                    cover,
                    u,
                    urgency_band(u),
                    c.recent_sales,
                    round(u * c.recent_sales, 3),
                    surplus,
                )
            )
    out.sort(key=lambda s: -s.priority)
    return out


def report(top: int = 25) -> None:
    grid = load_grid()
    baselines = mine_store_baselines(grid)
    sections = load_article_sections()
    cat_baselines = mine_category_baselines(grid, sections)
    graded = find_graded_shortages(grid, baselines, category_baselines=cat_baselines, sections=sections)
    routable = [g for g in graded if g.surplus]
    bands = Counter(g.band for g in graded)
    print(f"Baseline: per (store×section) — {len(cat_baselines)} mined, per-store fallback (DESIGN §5 refinement).")
    print(f"Graded shortages (retail, live demand, below baseline): {len(graded)}  {dict(bands)}")
    print(f"  routable (surplus elsewhere): {len(routable)}\n")
    print(f"Top {top} by priority (urgency × recent demand):")
    for g in routable[:top]:
        art, col, size = g.variant
        src = ", ".join(f"{st}:{q}({role[0]},{cost:.0f}m)" for st, q, role, cost in g.surplus[:4])
        if g.cover == 0:
            cov = "OUT"
        elif g.cover is not None:
            cov = f"{g.cover:.0f}d"
        else:
            cov = "—"
        print(f"  [{g.band:8}] {g.store}  {art} {col} {size}  cover={cov} sold30d={g.recent_sales:>3}  ← {src}")


if __name__ == "__main__":
    report()
