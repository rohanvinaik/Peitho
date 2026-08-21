"""Hand-authored INTENT tests for peitho.ledgers — the domain-organized shadow ledgers.

Pins the assembly contract (not characterization): the operational domain is ONE ledger with the named
sections, each a projection of the same substrate; a section-builder's content is what the domain ledger
carries for it (no drift between the two). Runs on the bundled synthetic example — no real data.
"""

from __future__ import annotations

from peitho.grid import Cell, Grid
from peitho.ledgers import (
    build_by_item_section,
    build_by_sku_section,
    build_customer,
    build_item,
    build_item_clearance_section,
    build_manufacturer_section,
    build_network_section,
    build_operational,
    build_outliers_section,
    build_restock_section,
    build_routing_section,
    build_sale_digest_section,
    build_seasonal_section,
    build_shadow_section,
    build_store_clearance_section,
    build_suppliers_section,
)
from peitho.lenses import inventory
from peitho.lenses.price import load_price_grid
from peitho.source import load_grid

_OPERATIONAL_SECTIONS = {
    "domain",
    "stores",
    "routing",
    "manufacturer_orders",
    "suppliers",
    "vendor_mis",
    "store_clearance",
    "network",
}

_ITEM_SECTIONS = {
    "domain",
    "by_sku",
    "by_item",
    "shadow",
    "categories",
    "abc",
    "clearance",
    "seasonal",
    "sale_digest",
    "outliers",
    "restock",
}


def test_operational_ledger_is_one_domain_with_the_named_sections():
    op = build_operational()
    assert op["domain"] == "operational"
    assert set(op) == _OPERATIONAL_SECTIONS  # one ledger, all sections; a new metric is a new field here


def test_sections_match_their_builders_no_drift():
    # the domain ledger carries exactly what each section-builder produces — the ledger is composition, not
    # a re-derivation that could drift from the section
    grid = inventory.load_grid()  # the same roster-ordered load build_operational uses
    op = build_operational()
    assert op["routing"] == build_routing_section(grid)
    assert op["manufacturer_orders"] == build_manufacturer_section(grid)
    assert op["suppliers"] == build_suppliers_section()
    assert op["store_clearance"] == build_store_clearance_section()
    assert op["network"] == build_network_section()


def test_stores_section_is_store_performance_flat_plus_signed():
    op = build_operational()
    stores = op["stores"]
    assert stores["report"] == "store_performance"
    # each row pairs a flat fact with the signed-ternary read (the substrate, native to the row)
    assert all("revenue" in r and r["sales_position"] in ("above", "at", "below") for r in stores["stores"])


def test_routing_section_shape():
    # a small synthetic grid: a warehouse with spare + a selling store short of it → at least a routable frame
    grid = Grid(
        {
            ("A", "BLK", "40"): {
                "WH": Cell(
                    store="WH", stock=20, sale_qty=0, recent_sales=0, nrv=0.0, cogs=0.0, sls_age=(0, 0, 0, 0, 0)
                ),
                "S1": Cell(
                    store="S1", stock=0, sale_qty=8, recent_sales=6, nrv=4000.0, cogs=2400.0, sls_age=(6, 2, 0, 0, 0)
                ),
            }
        }
    )
    sec = build_routing_section(grid)
    assert set(sec) == {"summary", "transfers", "reorders", "reasoning"}
    assert set(sec["summary"]) >= {"moves", "units", "runs", "reorders", "target_cover_days"}


def test_item_ledger_is_one_domain_with_the_named_sections():
    it = build_item()
    assert it["domain"] == "item"
    assert set(it) == _ITEM_SECTIONS  # one ledger, all item sections; a new metric is a new field here


def test_item_sections_match_their_builders_no_drift():
    # the item ledger carries exactly what each section-builder produces — composition, not a re-derivation
    # that could drift. The digest/outliers sections read the SAME shadow the ledger assembles (blind men talk).
    grid = load_grid()
    price_grid = load_price_grid()
    it = build_item()
    shadow = build_shadow_section(grid)
    assert it["by_sku"] == build_by_sku_section(grid)
    assert it["by_item"] == build_by_item_section(grid)
    assert it["shadow"] == shadow
    assert it["clearance"] == build_item_clearance_section(price_grid)
    assert it["seasonal"] == build_seasonal_section(price_grid)
    assert it["sale_digest"] == build_sale_digest_section(shadow)
    assert it["outliers"] == build_outliers_section(shadow)
    assert it["restock"] == build_restock_section(grid)


def test_item_clearance_is_item_grain_only_no_store_part():
    # the store-grain clearing signal (clearing_store / peer_norm_depth / stores[]) is operational's, NOT item's
    clr = build_item()["clearance"]
    assert set(clr) == {"summary", "items"}
    assert set(clr["summary"]) == {"fresh_dump", "aged_clearance"}
    assert "clearing_store" not in clr and "stores" not in clr


def test_shadow_row_pairs_raw_facts_with_the_sell_dynamics_read():
    # flat-but-intelligent: each wide item row carries the raw identity/stock AND the movement (sell-dynamics)
    shadow = build_item()["shadow"]
    assert shadow, "the example grid must yield at least one item"
    row = shadow[0]
    assert "item" in row and "stock" in row and "movement" in row  # raw fact + the geometry read in one row
    assert "sell_through_pct" in row["movement"] and "margin_pct" in row["movement"]


def test_customer_ledger_is_one_domain_pseudonymous_and_airgap_safe():
    cu = build_customer()
    assert cu["domain"] == "customer"
    assert set(cu) == {"domain", "summary", "segments_detail", "nodes"}
    assert set(cu["summary"]) == {"persons", "active", "households", "segments", "rfm_baselines"}
    assert cu["segments_detail"]["report"] == "segment_mis"
    # airgap-safe: every structural node is a pseudonym + prefixes, never a name / mobile / full code
    for n in cu["nodes"]:
        assert n["node_id"].startswith("c:")
        assert "name" not in n and "mobile" not in n and "codes" not in n
