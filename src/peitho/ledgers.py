"""peitho.ledgers — the domain-organized shadow ledgers (DESIGN.md §6).

One ledger per semantic domain, each the de-dimensionalized read of the substrate for that domain — flat,
parseable JSON whose rows carry both the raw facts and the signed-ternary geometry reads. A report is a
subset of one ledger, a join across two, or a metric over atomics from several; adding one is adding fields
here and re-running, never a new file. This replaces the earlier per-report exports (routing.json,
suppliers.json, …), which fragmented one domain across many files.

Each `build_<domain>` composes section-builders over a single grid load (so a domain is one pass); the
section-builders are pure over `(grid, …)` and return content dicts — the I/O is only the final write.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict
from statistics import median

from . import network, product
from .export import (
    OUT_CUSTOMERS,
    OUT_CUSTOMERS_KEY,
    OUT_ITEM,
    OUT_OPERATIONAL,
    article_image_map,
    article_style_ids,
    build_item_record,
    build_movement,
    build_sku_record,
    build_wide_item_record,
    canonical_articles,
    load_article_attributes,
    load_clearance_article_fields,
    load_taxonomy,
)
from .grid import Grid
from .lenses import inventory, season, supplier
from .lenses.price import flag_cleared_items, load_article_ages, load_price_grid, store_clearance
from .mis import abc_summary, category_mis, segment_mis, store_performance, vendor_mis
from .noticer import class_distribution, notice
from .query.regime import BASE, article_regimes
from .query.significance import significant_moves
from .query.supply import supply_plan
from .route import (
    COVER_DAYS_DEFAULT,
    MFR_KEEP,
    MFR_MIN_MOMENTUM,
    MFR_MIN_STORES,
    MFR_MIN_SUPPLIER_ITEMS,
    SUPPLIER_ORDER,
    batch_transfers,
    manufacturer_significant,
    plan_transfers_global,
    reorder_priority,
    supplier_worth_ordering,
)
from .sku import article_image_hashes, dedupe_articles
from .source import load_grid
from .stats import robust_price

# --- operational-domain section builders (pure over the grid where possible; no I/O) ---------------


def build_routing_section(grid: Grid, target_cover_days: float = COVER_DAYS_DEFAULT) -> dict:
    """The routing section: the min-cost transfer plan (noise-removed to the significant set) + the
    regime-gated reorders + the geometry's aggregated reasoning. Each move carries the destination cell's
    signed-ternary read. Pure over the grid; identical content to the former routing.json."""
    transfers, _ = plan_transfers_global(grid, target_cover_days)
    transfers = significant_moves(transfers, grid)
    reorders = supply_plan(grid, article_regimes())
    batches = batch_transfers(transfers)
    cats = product.translate_taxonomy(load_taxonomy())
    imgs = article_image_map(grid)
    reasons = {(a.variant, a.store): a.label for a in notice(grid)}

    def enrich(variant):
        art = variant[0]
        return {
            "article": art,
            "color": variant[1],
            "size": variant[2],
            "image": imgs.get(art),
            "category": cats.get(art, {}).get("category"),
        }

    moves = [
        {
            **enrich(t.variant),
            "from_store": t.source,
            "to_store": t.dest,
            "qty": t.qty,
            "cost_min": round(t.cost, 1),
            "reason": reasons.get((t.variant, t.dest)),
        }
        for t in transfers
    ]
    reord = [
        {
            "article": o.article,
            "qty": o.qty,
            "regime": o.regime,
            "why": o.why,
            "image": imgs.get(o.article),
            "category": cats.get(o.article, {}).get("category"),
        }
        for o in reorders
    ]
    return {
        "summary": {
            "moves": len(transfers),
            "units": sum(t.qty for t in transfers),
            "runs": len(batches),
            "reorders": len(reorders),
            "reorder_units": sum(r.qty for r in reorders),
            "target_cover_days": target_cover_days,
        },
        "transfers": sorted(moves, key=lambda x: (x["from_store"], x["to_store"], -x["qty"])),
        "reorders": sorted(reord, key=lambda x: -x["qty"]),
        "reasoning": dict(Counter(m["reason"] or "unflagged" for m in moves).most_common()),
    }


def build_manufacturer_section(grid: Grid, target_cover_days: float = COVER_DAYS_DEFAULT) -> dict:
    """The manufacturer-order priority section: the reachable-vs-naive DIFFERENTIAL — demand no internal
    transfer can cover, aggregated per variant, scored by momentum, core/seasonal split, per-supplier basket
    floor. Pure over the grid; identical content to the former manufacturer_orders.json."""
    from .lenses.supplier import load_article_supplier

    transfers, reorders = plan_transfers_global(grid, target_cover_days)
    net_sls: dict = defaultdict(lambda: [0, 0, 0, 0, 0])
    for _v, cells in grid.items():
        for c in cells.values():
            for i in range(5):
                net_sls[_v][i] += c.sls_age[i]
    agg: dict = defaultdict(lambda: {"qty": 0, "stores": {}})
    for o in reorders:
        agg[o.variant]["qty"] += o.qty
        agg[o.variant]["stores"][o.store] = agg[o.variant]["stores"].get(o.store, 0) + o.qty

    cats = product.translate_taxonomy(load_taxonomy())
    suppliers = load_article_supplier()
    regimes = article_regimes()
    imgs = article_image_map(grid)
    orders = []
    for variant, a in agg.items():
        momentum = inventory.recent_velocity(tuple(net_sls[variant]))
        art = variant[0]
        regime = regimes.get(art, "UNKNOWN")
        n_stores = len(a["stores"])
        sig = manufacturer_significant(n_stores, momentum, MFR_MIN_STORES, MFR_MIN_MOMENTUM)
        orders.append(
            {
                "article": art,
                "color": variant[1],
                "size": variant[2],
                "unmet_qty": a["qty"],
                "momentum_per_day": round(momentum, 4),
                "priority": reorder_priority(a["qty"], momentum),
                "short_stores": dict(sorted(a["stores"].items(), key=lambda x: -x[1])),
                "supplier": suppliers.get(art),
                "regime": regime,
                "reorderable": regime == BASE,
                "significant": sig == MFR_KEEP,
                "image": imgs.get(art),
                "category": cats.get(art, {}).get("category"),
            }
        )
    orders.sort(key=lambda x: (not x["reorderable"], -x["priority"]))

    transfer_units = sum(t.qty for t in transfers)
    differential_units = sum(o.qty for o in reorders)
    naive_units = transfer_units + differential_units
    core = [o for o in orders if o["reorderable"]]
    core_sig = [o for o in core if o["significant"]]
    sup_items: dict = defaultdict(int)
    for o in core_sig:
        sup_items[o["supplier"]] += 1
    for o in core_sig:
        o["supplier_order"] = supplier_worth_ordering(sup_items[o["supplier"]]) == SUPPLIER_ORDER
    suppliers_order = [s for s, n in sup_items.items() if supplier_worth_ordering(n) == SUPPLIER_ORDER]
    order_items = [o for o in core_sig if o["supplier_order"]]
    return {
        "summary": {
            "orders": len(orders),
            "unmet_units": differential_units,
            "core_orders": len(core),
            "core_unmet_units": sum(o["unmet_qty"] for o in core),
            "core_significant": len(core_sig),
            "core_significant_units": sum(o["unmet_qty"] for o in core_sig),
            "suppliers_significant": len(sup_items),
            "min_supplier_items": MFR_MIN_SUPPLIER_ITEMS,
            "suppliers_worth_ordering": len(suppliers_order),
            "suppliers_below_basket": len(sup_items) - len(suppliers_order),
            "order_items": len(order_items),
            "order_units": sum(o["unmet_qty"] for o in order_items),
            "target_cover_days": target_cover_days,
        },
        "split": {
            "naive_demand_units": naive_units,
            "transfer_addressable_units": transfer_units,
            "manufacturer_only_units": differential_units,
            "manufacturer_only_pct": round(differential_units / naive_units, 4) if naive_units else 0.0,
        },
        "orders": orders,
    }


def build_suppliers_section(min_purchased: float = 200.0) -> dict:
    """The supplier sell-through section: each supplier's sell-through vs the data-mined peer-median (band +
    signed deviation). Reads the supplier purchase feed (empty until pulled). Identical content to the former
    suppliers.json."""
    agg = supplier.load_supplier_purchases()
    baseline = supplier.mine_supplier_baseline(agg)
    ranked = supplier.rank_suppliers(agg, baseline, min_purchased)
    rows = [
        {
            "supplier": s.supplier,
            "band": s.band,
            "sell_through": s.sell_through,
            "deviation": round(s.deviation, 4),
            "purchased": round(s.purchased),
            "sold": round(s.sell_through * s.purchased),
            "stock_left": round(s.stock_left),
            "profit": round(s.profit),
        }
        for s in ranked
    ]
    return {
        "summary": {
            "peer_norm_sell_through": round(baseline, 4) if baseline is not None else None,
            "suppliers": len(ranked),
            "min_purchased": min_purchased,
            "bands": dict(Counter(s.band for s in ranked)),
        },
        "suppliers": rows,
    }


def build_store_clearance_section() -> dict:
    """The STORE-grain clearance section: which store is running markdowns deeper than its peers (the
    relative, MRP-robust store deviation) — count, depth-vs-peer-norm, band. The item-grain clearance
    (which items are dumped, over what age) lives in the item ledger. Reads the price grid."""
    grid = load_price_grid()
    stores = store_clearance(grid)  # most-clearing (highest deviation) first
    clearing = stores[0] if stores and stores[0].band in ("PROMO", "CLEARANCE") else None
    return {
        "peer_norm_depth": round(median([s.depth for s in stores]), 2) if stores else None,
        "clearing_store": (
            {"store": clearing.store, "depth": clearing.depth, "deviation": round(clearing.deviation, 2)}
            if clearing
            else None
        ),
        "stores": [
            {
                "store": s.store,
                "depth": s.depth,
                "deviation": round(s.deviation, 4),
                "band": s.band,
                "discount_given": s.discount_given,
                "margin_pct": s.margin_pct,
            }
            for s in stores
        ],
    }


def build_network_section() -> dict:
    """The node-network section: the roster, each node's role set, its zone, and the edge-weight source —
    the operational geometry the routing runs over, as flat config. Read from the active cassette's network."""
    net = network.active_network()
    return {
        "nodes": list(net.nodes),
        "zones": dict(net.zones),
        "roles": {n: sorted(r) for n, r in net.roles.items()},
        "weights_source": net.weights_source,
    }


# --- the operational domain ledger -----------------------------------------------------------------


def build_operational(target_cover_days: float = COVER_DAYS_DEFAULT) -> dict:
    """The company-operational domain ledger — locations, stock, store performance, routing, manufacturer
    and supplier performance, and store-grain clearance — assembled over a single grid load. Each section
    pairs the flat operational facts with the geometry reads native to the same ledger."""
    from .lenses.supplier import load_article_supplier

    grid = inventory.load_grid()  # the roster store-order (RETAIL+WAREHOUSE) the order-sensitive routing needs
    supplier_of = load_article_supplier().get  # article → vendor, for the sales-side vendor MIS
    return {
        "domain": "operational",
        "stores": store_performance(grid),
        "routing": build_routing_section(grid, target_cover_days),
        "manufacturer_orders": build_manufacturer_section(grid, target_cover_days),
        "suppliers": build_suppliers_section(),
        "vendor_mis": vendor_mis(grid, supplier_of),
        "store_clearance": build_store_clearance_section(),
        "network": build_network_section(),
    }


def export_operational(out_path: str = OUT_OPERATIONAL, target_cover_days: float = COVER_DAYS_DEFAULT) -> dict:
    """Write the operational-domain ledger. I/O shell over `build_operational`; returns a compact summary."""
    ledger = build_operational(target_cover_days)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    return {
        "stores": len(ledger["stores"]["stores"]),
        "routing_moves": ledger["routing"]["summary"]["moves"],
        "manufacturer_orders": ledger["manufacturer_orders"]["summary"]["orders"],
    }


# --- item-domain section builders (pure over the grid where possible; no I/O) -----------------------


def build_by_sku_section(grid: Grid) -> list:
    """Per-SKU inventory records: one row per (article, colour, size) with image/category/style/age + stock by
    location. Raw grain — no same-photo merge. Identical content to the former inventory_by_sku.json."""
    attrs = load_article_attributes()
    taxo = product.translate_taxonomy(load_taxonomy())  # non-destructive: raw preserved + informative category
    ages = load_article_ages()
    records = []
    for (article, color, size), cells in grid.items():
        info = attrs.get(article, {})
        tax = taxo.get(article, {})
        stock_by = {store: c.stock for store, c in cells.items() if c.stock > 0}
        records.append(
            build_sku_record(
                article,
                color,
                size,
                info.get("image"),
                tax.get("category", {}),
                info.get("style", {}),
                ages.get(article),
                stock_by,
            )
        )
    records.sort(key=lambda r: (r["sku"]["article"], str(r["sku"]["color"]), str(r["sku"]["size"])))
    return records


def build_by_item_section(grid: Grid) -> list:
    """Human-scale items: SKUs rolled to (article, colour) — sizes become an availability list, same-photo
    articles collapsed to a canonical rep within a colour. Identical content to the former inventory_by_item.json."""
    attrs = load_article_attributes()
    taxo = product.translate_taxonomy(load_taxonomy())
    ages = load_article_ages()
    canon = canonical_articles(dedupe_articles())
    style_of = article_style_ids(article_image_hashes())
    groups: dict = defaultdict(lambda: {"size_stock": defaultdict(int), "by_loc": defaultdict(int), "arts": set()})
    for (article, color, size), cells in grid.items():
        g = groups[(canon.get(article, article), color)]
        g["arts"].add(article)
        g["size_stock"][size] += sum(c.stock for c in cells.values())
        for store, c in cells.items():
            if c.stock > 0:
                g["by_loc"][store] += c.stock
    records = []
    for (_canon_art, color), g in groups.items():
        article = min(g["arts"])
        info = attrs.get(article, {})
        tax = taxo.get(article, {})
        records.append(
            build_item_record(
                article,
                color,
                style_of.get(article),
                info.get("image"),
                tax.get("category", {}),
                info.get("style", {}),
                ages.get(article),
                dict(g["size_stock"]),
                dict(g["by_loc"]),
            )
        )
    records.sort(key=lambda r: (r["item"]["article"], str(r["item"]["color"])))
    return records


def build_shadow_section(grid: Grid) -> list:
    """The wide, crystallized item projection: informative category + the flat sell-dynamics `movement` block +
    supplier/rsp, one record per (article, colour). Identical content to the former inventory_shadow.json."""
    from .lenses.supplier import load_article_supplier

    attrs = load_article_attributes()
    cats = product.translate_taxonomy(load_taxonomy())
    ages = load_article_ages()
    canon = canonical_articles(dedupe_articles())
    style_of = article_style_ids(article_image_hashes())
    art_sup = load_article_supplier()
    art_rsp, art_img = load_clearance_article_fields()
    groups: dict = defaultdict(
        lambda: {
            "size_stock": defaultdict(int),
            "by_loc": defaultdict(int),
            "arts": set(),
            "sold": 0,
            "vel": 0,
            "nrv": 0.0,
            "cogs": 0.0,
            "disc_sale": 0.0,
            "prices": [],  # per-cell (realized price, units) — for the robust-consensus price (bimodal-safe)
        }
    )
    for (article, color, size), cells in grid.items():
        g = groups[(canon.get(article, article), color)]
        g["arts"].add(article)
        g["size_stock"][size] += sum(c.stock for c in cells.values())
        for store, c in cells.items():
            if c.stock > 0:
                g["by_loc"][store] += c.stock
            g["sold"] += c.sale_qty
            g["vel"] += c.recent_sales
            g["nrv"] += c.nrv
            g["cogs"] += c.cogs
            g["disc_sale"] += c.discounted_sale
            if c.sale_qty > 0 and c.nrv > 0:
                g["prices"].append((c.nrv / c.sale_qty, c.sale_qty))
    records = []
    for (_canon_art, color), g in groups.items():
        article = min(g["arts"])
        info = attrs.get(article, {})
        stock_total = sum(g["size_stock"].values())
        movement = build_movement(g["vel"], g["sold"], stock_total, g["nrv"], g["cogs"], g["disc_sale"])
        movement["sale_price_robust"], movement["price_split"] = robust_price(g["prices"])
        rec = build_wide_item_record(
            article,
            color,
            style_of.get(article),
            info.get("image") or next((art_img[a] for a in sorted(g["arts"]) if a in art_img), None),
            cats.get(article, {}).get("category"),
            info.get("style", {}),
            ages.get(article),
            dict(g["size_stock"]),
            dict(g["by_loc"]),
            movement,
        )
        rec["supplier"] = next((art_sup[a] for a in sorted(g["arts"]) if a in art_sup), None)
        rec["rsp"] = next((art_rsp[a] for a in sorted(g["arts"]) if a in art_rsp), None)
        records.append(rec)
    records.sort(key=lambda r: (r["item"]["article"], str(r["item"]["color"])))
    return records


def build_restock_section(grid: Grid) -> dict:
    """The GEOMETRY's shadow ledger: the signed-ternary noticer/restock field, flat — the actionable slice
    (RESTOCK now, ESCALATE for the operator) + the full anomaly taxonomy. Same content as the former restock.json."""
    from .restock import ESCALATE, HOLD, IGNORE, RESTOCK, restock_decision, restock_plan

    field = notice(grid)
    cats = product.translate_taxonomy(load_taxonomy())
    imgs = article_image_map(grid)

    def enrich(item):
        art = item.variant[0]
        return {
            "article": art,
            "color": item.variant[1],
            "size": item.variant[2],
            "image": imgs.get(art),
            "category": cats.get(art, {}).get("category"),
            "store": item.store,
            "decision": item.decision,
            "signature": list(item.signature),
            "label": item.anomaly.label,
        }

    plan = restock_plan(field)
    restock_items = sorted((enrich(i) for i in plan if i.decision == RESTOCK), key=lambda x: (x["store"], x["article"]))
    escalate_items = sorted(
        (enrich(i) for i in plan if i.decision == ESCALATE), key=lambda x: (x["store"], x["article"])
    )
    dec = Counter(restock_decision(a.signature) for a in field)
    classes = [
        {"signature": list(sig), "label": label, "count": count, "decision": restock_decision(sig)}
        for sig, label, count in class_distribution(field)
    ]
    return {
        "summary": {
            "flagged": len(field),
            "restock": dec[RESTOCK],
            "escalate": dec[ESCALATE],
            "hold": dec[HOLD],
            "ignore": dec[IGNORE],
            "classes": len(classes),
        },
        "restock": restock_items,
        "escalate": escalate_items,
        "anomaly_classes": classes,
    }


def build_item_clearance_section(price_grid: Grid, top_items: int = 40) -> dict:
    """The ITEM-grain clearance: the margin-led FRESH_DUMP illustration (young stock cut deep, biggest loss
    first) + the fresh-vs-aged counts. The store-grain clearing signal lives in operational.store_clearance.
    Identical content to the item half of the former clearance.json."""
    ages = load_article_ages()
    items = flag_cleared_items(price_grid, ages=ages)
    fresh = [i for i in items if i.age_class == "FRESH_DUMP"]
    aged = [i for i in items if i.age_class == "AGED_CLEARANCE"]
    fresh.sort(key=lambda i: i.margin_pct if i.margin_pct is not None else 0)  # biggest loss first (real signal)
    attrs = load_article_attributes()
    cats = product.translate_taxonomy(load_taxonomy())

    def item_row(i):
        art = i.variant[0]
        return {
            "article": art,
            "color": i.variant[1],
            "size": i.variant[2],
            "image": i.image or attrs.get(art, {}).get("image"),
            "category": cats.get(art, {}).get("category"),
            "store": i.store,
            "margin_pct": i.margin_pct,
            "age_days": i.age_days,
            "age_class": i.age_class,
            "units": i.units,
            "depth": i.depth,  # absolute markdown % — carried, never headlined (MRP noise)
        }

    return {
        "summary": {"fresh_dump": len(fresh), "aged_clearance": len(aged)},
        "items": [item_row(i) for i in fresh[:top_items]],  # margin-led illustration, not exhaustive
    }


def build_seasonal_section(price_grid: Grid) -> dict:
    """Impute the seasonal-sale events and split the on-sale population into SEASONAL (coordinated cohorts) vs
    ONE-OFF (idiosyncratic residue). Emitted at (article, colour) grain to join the shadow. Identical content
    to the former seasonal.json."""
    cats = product.translate_taxonomy(load_taxonomy())
    cleared = flag_cleared_items(price_grid, ages=load_article_ages())

    def category_of(article):
        return (cats.get(article, {}).get("category") or {}).get("cluster")

    res = season.deduce_seasonal_events(cleared, category_of)
    seasonal_items = sorted({(v[0], v[1]) for v in res["seasonal_variants"]})
    return {
        "summary": {
            "events": len(res["events"]),
            "seasonal_items": len(seasonal_items),
            "one_off_variants": len(res["one_off_variants"]),
        },
        "events": [asdict(e) for e in res["events"]],
        "seasonal_items": seasonal_items,
    }


def build_sale_digest_section(shadow_records: list, top: int = 3) -> dict:
    """The sale report's significance digest — the few out-of-norm surprises (biggest bleed · strongest loss
    pattern · the fast mover about to run dry). Reads the shadow SECTION in-memory (the blind men talking).
    Identical content to the former sale_digest.json."""
    from .digest import sale_surprises, sale_winners

    findings = sale_surprises(shadow_records, top=top - 1) + sale_winners(shadow_records, top=1)
    return {"surprises": [asdict(s) for s in findings]}


def build_outliers_section(shadow_records: list) -> dict:
    """The hidden-hot / laggard surprise floor: items whose recent sell-rate deviates furthest from their own
    sub-category's mined norm. Reads the shadow SECTION in-memory. Identical content to the former outliers.json."""
    from .digest import sale_outliers

    hot, laggards = sale_outliers(shadow_records)

    def _row(s):
        return {"over_pct": round(s.magnitude * 100), **s.fields}

    return {
        "summary": {"hidden_hot": len(hot), "laggards": len(laggards), "records": len(shadow_records)},
        "hidden_hot": [_row(s) for s in hot],
        "laggards": [_row(s) for s in laggards],
    }


# --- the item domain ledger ------------------------------------------------------------------------


def build_item() -> dict:
    """The item domain ledger — everything worth knowing about items: their inventory (per-SKU and rolled to
    human-scale items), the wide crystallized projection with sell-dynamics, the item-grain clearance, the
    seasonal split, the sale digest + outliers (read off the same shadow), and the signed-ternary restock
    field. Assembled over one stock-grid load + one price-grid load; the digest/outliers sections read the
    shadow section in-memory rather than a file."""
    grid = load_grid()  # adapter default order — the order the former item exports used
    price_grid = load_price_grid()
    shadow = build_shadow_section(grid)
    cats = product.translate_taxonomy(load_taxonomy())

    def category_of(article: str):
        return (cats.get(article, {}).get("category") or {}).get("cluster")

    return {
        "domain": "item",
        "by_sku": build_by_sku_section(grid),
        "by_item": build_by_item_section(grid),
        "shadow": shadow,
        "categories": category_mis(grid, category_of),  # conventional category-performance table
        "abc": abc_summary(grid),  # the Pareto ABC breakdown (the vital few)
        "clearance": build_item_clearance_section(price_grid),
        "seasonal": build_seasonal_section(price_grid),
        "sale_digest": build_sale_digest_section(shadow),
        "outliers": build_outliers_section(shadow),
        "restock": build_restock_section(grid),
    }


def export_item(out_path: str = OUT_ITEM) -> dict:
    """Write the item-domain ledger. I/O shell over `build_item`; returns a compact summary."""
    ledger = build_item()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    return {
        "by_sku": len(ledger["by_sku"]),
        "items": len(ledger["shadow"]),
        "restock_flagged": ledger["restock"]["summary"]["flagged"],
    }


# --- customer-domain section builders (separable-PII by construction) ------------------------------


def _customer_pseudonym(node: dict, salt: str) -> str:
    """A stable, non-reversible node id for a resolved person: salted SHA-256 of the mobile (the identity anchor),
    or of a name+created+store+codes fallback for the no-mobile singletons. Stable across rebuilds (same salt →
    same id, so the network is longitudinally joinable) yet carries no identifier itself. Pure over (node, salt)."""
    import hashlib

    key = node["mobile"] or f"{node['name']}|{node.get('created')}|{node['store']}|{','.join(map(str, node['codes']))}"
    return "c:" + hashlib.sha256(f"{salt}|{key}".encode()).hexdigest()[:12]


def _resolve_customer_network(today: str, salt: str, emit_identity: bool) -> tuple:
    """Resolve the customer master → (pseudonymous structural nodes, RFM baselines, identity crosswalk). One
    resolve pass feeds both projections; the identity crosswalk (node_id→PII) is built ONLY when emit_identity.
    Composes the pinned pipeline (resolve_identities → build_customer_nodes) + the mined RFM segment."""
    from . import customer as cust

    records = cust.load_clean_master()
    first, last = cust.build_corpora(records)
    persons = cust.resolve_identities(records, first, last, settings=cust.CONSERVATIVE_SETTINGS)["persons"]
    bills = cust.load_bills_by_customer()
    nodes = cust.build_customer_nodes(persons, bills, today=today)
    baselines = cust.mine_rfm_baselines(nodes)

    structural, identity = [], []
    for n in nodes:
        nid = _customer_pseudonym(n, salt)
        reg_stores = sorted({p for code in n["codes"] if (p := cust.decode_customer_code(code)[0])})
        structural.append(
            {
                "node_id": nid,
                "segment": cust.customer_segment(n["rfm"], baselines),
                "reg_stores": reg_stores,  # cross-store registration footprint (wormhole) — prefixes, no ordinal
                "home_store": n["store"],
                "gender": n["gender"],
                "created": n["created"],
                "household_id": n["household"],  # cluster id (shared mobile, distinct names) — non-identifying
                "merged": n["merged"],  # re-registrations collapsed into this person
                "rfm": n["rfm"],
            }
        )
        if emit_identity:
            identity.append({"node_id": nid, "name": n["name"], "mobile": n["mobile"], "codes": n["codes"]})

    structural.sort(key=lambda r: (-(r["rfm"]["monetary"] or 0), r["node_id"]))
    return structural, baselines, identity


def _customer_ledger(structural: list, baselines: dict) -> dict:
    """Wrap the resolved structural nodes into the customer domain ledger — the pseudonymous, airgap-safe read."""
    return {
        "domain": "customer",
        "summary": {
            "persons": len(structural),
            "active": sum(1 for r in structural if r["rfm"]["frequency"] > 0),
            "households": len({r["household_id"] for r in structural if r["household_id"] is not None}),
            "segments": dict(Counter(r["segment"] for r in structural)),
            "rfm_baselines": baselines,
        },
        "segments_detail": segment_mis(structural),  # the conventional per-segment rollup table
        "nodes": structural,
    }


# --- the customer domain ledger --------------------------------------------------------------------


def build_customer(today: str = "2026-08-15") -> dict:
    """The customer domain ledger — the resolved customer node-network, PSEUDONYMOUS and STRUCTURAL: node_id +
    registration-store footprint + home store + gender + created + household + RFM + mined segment. Carries NO
    name, NO mobile, NO full customerCode — only the decoded store-PREFIXES (the cross-store wormhole signal),
    never the re-identifying ordinal. Airgap-safe on its own. (Salt: $PEITHO_PII_SALT, card-only.)"""
    salt = os.environ.get("PEITHO_PII_SALT", "peitho-default-unsalted")
    structural, baselines, _ = _resolve_customer_network(today, salt, emit_identity=False)
    return _customer_ledger(structural, baselines)


def export_customer(
    out_path: str = OUT_CUSTOMERS,
    today: str = "2026-08-15",
    emit_identity: bool = False,
    identity_path: str = OUT_CUSTOMERS_KEY,
) -> dict:
    """Write the customer domain ledger — SEPARABLE-PII by construction (minimize exposure, not availability).
    The always-on customers.json is pseudonymous + structural. The re-identification crosswalk (node_id → name /
    mobile / full codes) is written ONLY when emit_identity=True, to a SEPARATE card-only file, so a named cohort
    is always a deliberate join — never the default render. I/O shell over the resolve. Returns the summary."""
    salt = os.environ.get("PEITHO_PII_SALT", "peitho-default-unsalted")
    structural, baselines, identity = _resolve_customer_network(today, salt, emit_identity)
    ledger = _customer_ledger(structural, baselines)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    if emit_identity:
        identity.sort(key=lambda r: r["node_id"])
        os.makedirs(os.path.dirname(identity_path), exist_ok=True)
        with open(identity_path, "w", encoding="utf-8") as fh:
            json.dump(identity, fh, ensure_ascii=False, indent=2)
    return ledger["summary"]


# --- the domain-ledger build entry point -----------------------------------------------------------


def report() -> None:
    """Build every domain shadow ledger — the operational, item, and customer domains — and print a one-line
    summary of each. The `python -m peitho.ledgers` entry point; the source of the JSON the reporters consume.
    The customer ledger is pseudonymous + airgap-safe; the node_id→PII crosswalk is NOT written here (gated)."""
    op = export_operational()
    it = export_item()
    cu = export_customer()
    print(f"Operational ledger → {OUT_OPERATIONAL}  ({op['stores']} stores, {op['routing_moves']:,} routing moves)")
    print(f"Item ledger        → {OUT_ITEM}  ({it['items']:,} items, {it['restock_flagged']:,} flagged)")
    print(f"Customer ledger    → {OUT_CUSTOMERS}  ({cu['persons']:,} persons, {cu['active']:,} active)")


if __name__ == "__main__":
    report()
