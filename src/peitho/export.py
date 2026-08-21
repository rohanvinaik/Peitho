"""peitho.export — the machine-readable data-interchange layer.

The delivery *format* (a customer-facing PDF, a programmatic chat message, a new backend report) is an
opinion/idiom decision and belongs downstream. The *capacity* is a neutral, portable JSON representation that
ANY renderer or adapter consumes. This module builds the full inventory-by-SKU JSON purely from the LOCAL
landed data — no backend calls — composing the grid (stock × location), the taxonomy (category), the article
attributes (style), the age grid (vintage), and the product image URL.

Design: data ≠ presentation. One neutral JSON substrate → PDF / chat / backend-report / anything. The same
shape generalizes to location / customer / finance exports, cross-referenceable by their shared keys
(`article`, `store`, `customerCode`). Images are LINKS (URLs), never embedded, and front-anchored in each
record for visual reference. No stochastic component; every value is the authoritative pull's own figure.
"""

from __future__ import annotations

import json

from peitho.config import ROOT  # portable project root (env $PEITHO_ROOT or auto-detected) — no hardcoded path

from . import product  # the item-semantic category axis (informative, deconvolved; non-destructive)
from .lenses.price import load_article_ages  # article vintage = days since earliest receipt

OUT_OPERATIONAL = f"{ROOT}/data/export/operational.json"  # the operational-domain shadow ledger (peitho.ledgers)
OUT_ITEM = f"{ROOT}/data/export/item.json"  # the item-domain shadow ledger (peitho.ledgers): inventory + dynamics
# The former per-report exports (inventory_by_sku / by_item / shadow / restock / clearance / seasonal /
# sale_digest / outliers, and routing / manufacturer_orders / store_sales / suppliers) are RETIRED — their
# content is now SECTIONS of the two domain ledgers above, assembled by peitho.ledgers. See DESIGN.md §6.
OUT_MORNING = f"{ROOT}/data/export/morning.json"  # the good-morning report-router (digest-of-digests, #5)
OUT_TASTE_DIR = f"{ROOT}/data/export/taste_ledger"  # append-only, one dated day-file — accretes the taste stream
OUT_CUSTOMERS = f"{ROOT}/data/export/customers.json"  # pseudonymous structural node-network (NO name/mobile/code)
OUT_CUSTOMERS_KEY = f"{ROOT}/data/export/customers_identity.json"  # node_id → PII crosswalk (card-only, gated)


def build_sku_record(
    article: str,
    color: str,
    size: str,
    image: str | None,
    category: dict,
    style: dict,
    age_days: int | None,
    stock_by_location: dict,
) -> dict:
    """Assemble ONE portable per-SKU record. Image is front-anchored (right after the identity) for visual
    reference. `category` is the informative product category (deconvolved, raw preserved inside it) from
    `product.translate_taxonomy` — same shape the shadow uses. Pure over primitives + dicts."""
    return {
        "sku": {"article": article, "color": color, "size": size},
        "image": image,
        "category": category,
        "style": style,
        "age_days": age_days,
        "stock": {"total": sum(stock_by_location.values()), "by_location": dict(sorted(stock_by_location.items()))},
    }


def load_article_attributes(path: str | None = None) -> dict:
    """Per-article image + style attributes — via the active cassette's data-input adapter (`peitho.source`)."""
    from . import source

    return source.adapter().load_article_attributes(path)


def load_taxonomy(path: str | None = None) -> dict:
    """Raw {article: {section, subsection}} category lenses (pre-deconvolution) — via the adapter."""
    from . import source

    return source.adapter().load_taxonomy(path)


def load_clearance_article_fields(path: str | None = None) -> tuple:
    """(rsp_by_article, image_by_article) from the clearance report — via the adapter."""
    from . import source

    return source.adapter().load_clearance_article_fields(path)


def article_image_map(grid) -> dict:
    """{article: best image URL} unioned across every source the pull holds — the curated attribute file, the
    per-store drilldown (`Cell.image`), and the clearance article report. Priority: attributes (curated) →
    drilldown → clearance. Grid + I/O."""
    attrs = load_article_attributes()
    _rsp, clearance = load_clearance_article_fields()
    out: dict = {}
    for variant, cells in grid.items():  # drilldown images — the widest single source
        art = variant[0]
        if art in out:
            continue
        for c in cells.values():
            if c.image:
                out[art] = c.image
                break
    for art, a in attrs.items():  # the curated attribute image wins where present
        if a.get("image"):
            out[art] = a["image"]
    for art, url in clearance.items():  # the clearance report fills any remaining gap
        out.setdefault(art, url)
    return out


def canonical_articles(clusters: list) -> dict:
    """{article -> canonical article} for the image dedupe: every member of a same-photo cluster maps to the
    cluster's lexicographically-smallest article (a stable representative). Articles in no cluster are absent
    (callers fall back to the article itself). Pure over a list of article-number clusters."""
    canon: dict = {}
    for cluster in clusters:
        rep = min(cluster)
        for art in cluster:
            canon[art] = rep
    return canon


def article_style_ids(hashes: dict) -> dict:
    """{article -> style_id} where style_id = 'img:' + the first 8 hex of the image content hash, so articles
    sharing a photo (one STYLE across colourways) get the SAME style_id. Pure over {article: hash}."""
    return {art: f"img:{h[:8]}" for art, h in hashes.items()}


def build_item_record(
    article: str,
    color: str,
    style_id: str | None,
    image: str | None,
    category: dict,
    style: dict,
    age_days: int | None,
    size_stock: dict,
    stock_by_location: dict,
) -> dict:
    """Roll one colorway's per-size SKUs into ONE human-scale item: a design+color, its size availability, and
    total stock — the way a person would list 'items' (sizes are availability, not separate products). `style_id`
    links colourways of the same style (shared product photo). `category` is the informative product category
    (deconvolved, raw preserved inside) from `product.translate_taxonomy`. Identity (item + style_id) leads,
    image next for visual reference. Pure over primitives + dicts."""
    return {
        "item": {"article": article, "color": color},
        "style_id": style_id,
        "image": image,
        "category": category,
        "style": style,
        "age_days": age_days,
        "sizes": {
            "in_stock": sorted(s for s, q in size_stock.items() if q > 0),
            "by_size": dict(sorted(size_stock.items())),
        },
        "stock": {"total": sum(size_stock.values()), "by_location": dict(sorted(stock_by_location.items()))},
    }


def build_movement(
    velocity_30d: int,
    sold_window: int,
    stock_total: int,
    nrv: float,
    cogs: float,
    discounted_sale: float,
) -> dict:
    """The item's sell-dynamics on the CORRECT backend fields (the backend's pricing semantics): the obvious
    `discountAmount` "markdown" is structural MRP noise, so it is NOT used. `nrv` = net realized revenue,
    `discounted_sale` = revenue sold at a discount below standard (the direct "on sale" signal), `cogs` = cost.
    Emits: realized `sale_price` (asp), `on_sale_pct` (discounted-revenue share), REAL `margin_pct` (nrv−cogs),
    `below_cost`. Guards nrv≤0 (return noise) → None. Pure over six numbers."""
    denom = sold_window + stock_total
    return {
        "velocity_30d": velocity_30d,
        "sold_window": sold_window,
        "sell_through_pct": round(sold_window / denom * 100, 1) if denom else None,
        "days_of_cover": round(stock_total / (velocity_30d / 30), 1) if velocity_30d > 0 else None,
        "sale_price": round(nrv / sold_window) if sold_window > 0 and nrv > 0 else None,
        "on_sale_pct": round(discounted_sale / nrv * 100) if nrv > 0 else None,
        "margin_pct": round((nrv - cogs) / nrv * 100, 1) if nrv > 0 else None,
        "below_cost": (nrv - cogs) < 0 if nrv > 0 else None,
        # the clean, human-readable loss: $ per unit that the sale price sits BELOW acquisition cost
        "below_cost_by": round((cogs - nrv) / sold_window) if sold_window > 0 and 0 < nrv < cogs else None,
    }


def build_wide_item_record(
    article: str,
    color: str,
    style_id: str | None,
    image: str | None,
    category: dict,
    style: dict,
    age_days: int | None,
    size_stock: dict,
    stock_by_location: dict,
    movement: dict,
) -> dict:
    """The 'shadow JSON' item: the crystallized flat projection of the item-semantic + location + price geometry.
    Like `build_item_record` but with the informative product `category` (deconvolved, raw preserved inside it)
    and a flat `movement` sell-dynamics block — ONE record drives both a stock view and a sales-performance
    view. Identity (item + style_id) leads, image next for reference. Pure over primitives + dicts."""
    return {
        "item": {"article": article, "color": color},
        "style_id": style_id,
        "image": image,
        "category": category,
        "style": style,
        "age_days": age_days,
        "sizes": {
            "in_stock": sorted(s for s, q in size_stock.items() if q > 0),
            "by_size": dict(sorted(size_stock.items())),
        },
        "stock": {"total": sum(size_stock.values()), "by_location": dict(sorted(stock_by_location.items()))},
        "movement": movement,
    }


def export_taste_ledger(date: str, out_dir: str = OUT_TASTE_DIR) -> dict:
    """Emit ONE dated, APPEND-ONLY day-file of the taste-verdict stream (peitho.lenses.price.taste_verdicts):
    every FRESH_DUMP item visible in today's grid, stamped with the day + its cross-store posture — the labelled
    log the end-stage story engine (Genesis / Regenesis) later reads into the operator's implicit taste rules.

    Unlike the other exports this is NEVER a rebuild-overwrite of history: each day lands its own <date>.json and
    the directory ACCRETES, so consecutive days can be DIFFED into the genuine per-day cut-events (the grid window
    is cumulative Apr-1→snapshot, so a single file is 'FRESH_DUMP visible AS OF <date>', not 'cut ON <date>').
    Re-running a date is safe — deterministic over that grid. Carries the item image + informative category for the
    downstream reader. Returns the summary. I/O."""
    import os
    from collections import Counter

    from .lenses.price import load_price_grid, taste_verdicts

    grid = load_price_grid()
    ages = load_article_ages()
    verdicts = taste_verdicts(grid, date, ages=ages)
    attrs = load_article_attributes()
    cats = product.translate_taxonomy(load_taxonomy())
    rows = [
        {
            "date": v.date,
            "variant": {"article": v.variant[0], "color": v.variant[1], "size": v.variant[2]},
            "image": v.image or attrs.get(v.variant[0], {}).get("image"),
            "category": cats.get(v.variant[0], {}).get("category"),
            "store": v.store,
            "depth": v.depth,
            "margin_pct": v.margin_pct,
            "age_days": v.age_days,
            "units": v.units,
            "held_elsewhere": v.held_elsewhere,
            "conditional": v.conditional,
        }
        for v in verdicts
    ]
    out = {
        "date": date,
        "summary": {
            "verdicts": len(rows),
            # held full-price elsewhere = taste isolated from circumstance (the clean training signal)
            "conditional": sum(1 for v in verdicts if v.conditional),
            "by_store": dict(Counter(v.store for v in verdicts)),
        },
        "verdicts": sorted(rows, key=lambda r: (r["store"], -r["units"])),
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(f"{out_dir}/{date}.json", "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out["summary"]


def export_morning(out_path: str = OUT_MORNING) -> dict:
    """The 'good morning' report-router (peitho.morning) — the digest-of-digests (#5). Reads the domain
    ledgers already exported (the operational ledger's routing / suppliers / store-clearance summaries + the
    item ledger's sale-digest / seasonal summaries) and routes the operator's attention: one ranked line per
    domain, LOUD ones first, each pointing at the report that carries the detail. Returns the summary. I/O —
    expects the domain ledgers to have been written first; any missing summary degrades to QUIET, never a crash."""
    import os
    from dataclasses import asdict

    from .morning import morning_routes

    def load(path, default):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return default

    op = load(OUT_OPERATIONAL, {})
    item = load(OUT_ITEM, {})
    sale = item.get("sale_digest", {}).get("surprises", [])
    routing = op.get("routing", {}).get("summary", {})
    suppliers = op.get("suppliers", {}).get("summary", {})
    clearance = op.get("store_clearance", {})  # the store-grain clearing signal (clearing_store, peer_norm_depth)
    seasonal = item.get("seasonal", {}).get("summary", {})
    routes = morning_routes(sale, routing, suppliers, clearance, seasonal)
    loud = [r for r in routes if r.band == "LOUD"]
    out = {
        "summary": {"loud": len(loud), "quiet": len(routes) - len(loud)},
        "routes": [asdict(r) for r in routes],
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out["summary"]
