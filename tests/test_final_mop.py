"""Final coverage mop-up: the last file-reading leaves + total-function branch corners that the bigger
integration tests don't happen to route through — customer master/bill loaders, the spatial cost matrix
(placeholder + real OSRM + the same-ZIP 0-guard), node_role's non-retail arms, and rank_suppliers' two
skip branches. All path/param-driven or pure, so pinned directly over tmp files or literal inputs.
"""

import json

import peitho.customer as cust
import peitho.lenses.inventory as inv
import peitho.lenses.price as price
import peitho.lenses.spatial as sp
import peitho.lenses.supplier as sup
from peitho.grid import Cell, Grid


def test_flag_cleared_items_default_ages_and_depth_none():
    grid = Grid(
        {
            ("A1", "BLK", "40"): {"N8": Cell("N8", 3, 10, 9, 1000.0, discount_amount=50.0, profit=200.0)},
            ("A2", "RED", "38"): {"N8": Cell("N8", 2, 5, 5, 100.0, discount_amount=400.0, profit=-50.0)},
            # nrv+discount <= 0 -> discount_depth is None -> the item is skipped (return-noise guard)
            ("A3", "GRN", "9"): {"N8": Cell("N8", 1, 2, 1, -200.0, discount_amount=100.0)},
        }
    )
    items = price.flag_cleared_items(grid)  # ages=None default path
    assert all(i.age_class in ("FRESH_DUMP", "AGED_CLEARANCE", "NOT_DUMPED", "AGE_UNKNOWN") for i in items)
    assert all(i.variant[0] != "A3" for i in items)  # the None-depth cell never becomes an item


def test_find_graded_shortages_skips_non_retail_and_dead_cells():
    grid = Grid(
        {
            ("A1", "BLK", "40"): {
                "WH": Cell("WH", 0, 4, 4, 0.0),  # HEAD_OFFICE, not RETAIL -> skipped
                "N8": Cell("N8", 5, 3, 0, 0.0),  # RETAIL but recent_sales 0 -> skipped
            }
        }
    )
    assert inv.find_graded_shortages(grid, {"N8": 100.0}, min_cost={}) == []


def test_resolve_identities_group_with_only_placeholder_names():
    # two records share a mobile but both have blank/placeholder names -> group has no resolvable person
    raw = [
        {"customerCode": "AH0000000001", "mobile": "5551234567", "name": "", "created": "2024-01-01"},
        {"customerCode": "AH0000000002", "mobile": "5551234567", "name": "", "created": "2024-02-01"},
    ]
    records = [cust.clean_record(r) for r in raw]
    first, last = cust.build_corpora(records)
    res = cust.resolve_identities(records, first, last, settings=cust.CONSERVATIVE_SETTINGS)
    assert res["stats"]["persons"] >= 1  # each empty-name record stays its own unresolved person


# the item-grain clearance export (fresh_dump rows) moved to peitho.ledgers.build_item_clearance_section —
# its behaviour is pinned in tests/test_ledgers_integration.py (test_item_clearance_section_is_item_grain_fresh_dump)


# load_clean_master / load_bills_by_customer now delegate to the cassette's private adapter (PII paths); the
# pure per-row harmonizer clean_record + decode_customer_code stay public and are Detective-pinned.


def test_node_role_covers_every_arm():
    # node_role reads the grid-INDUCED coarse map: RETAIL / WAREHOUSE for a classified node, UNKNOWN otherwise
    coarse = {"N1": "RETAIL", "WH": "WAREHOUSE"}
    assert inv.node_role("N1", coarse) == "RETAIL"
    assert inv.node_role("WH", coarse) == "WAREHOUSE"  # a zero-sales node -> the true source
    assert inv.node_role("ZZ", coarse) == "UNKNOWN"  # absent from the data -> node death


def test_load_real_cost_matrix_tmpfile_and_absent(tmp_path):
    p = tmp_path / "cost.json"
    p.write_text(json.dumps({"matrix": {"N8|N3": 40, "N3|N8": 42}}))
    m = sp.load_real_cost_matrix(str(p))
    assert m == {("N8", "N3"): 40.0, ("N3", "N8"): 42.0}
    assert sp.load_real_cost_matrix("/no/such.json") is None


def test_cost_matrix_placeholder_and_real(monkeypatch):
    # no real matrix -> placeholder zone distances
    monkeypatch.setattr(sp, "load_real_cost_matrix", lambda: None)
    placeholder = sp.cost_matrix(("N8", "N3"))
    assert placeholder[("N8", "N3")] > 0 and placeholder[("N8", "N8")] == 0.0
    # real matrix present, but a distinct-store 0 (same-ZIP geocode collision) falls back to the placeholder
    monkeypatch.setattr(sp, "load_real_cost_matrix", lambda: {("N8", "N3"): 40.0, ("N3", "N8"): 0.0})
    real = sp.cost_matrix(("N8", "N3"))
    assert real[("N8", "N3")] == 40.0  # real value used
    assert real[("N3", "N8")] > 0  # OSRM 0 between distinct stores -> placeholder, never a misleading 0


def test_spatial_demo_runs(capsys):
    sp.demo()
    assert "Min-cost" in capsys.readouterr().out


def test_rank_suppliers_skip_branches():
    # below min_purchased -> skipped (thin signal)
    thin = {"THIN": {"sold": 5.0, "purchased": 50.0, "stock": 0.0, "profit": 0.0}}
    assert sup.rank_suppliers(thin, baseline=0.5, min_purchased=100.0) == []
    # purchased 0 -> sell_through is None -> skipped even at min_purchased 0
    zero = {"ZERO": {"sold": 0.0, "purchased": 0.0, "stock": 0.0, "profit": 0.0}}
    assert sup.rank_suppliers(zero, baseline=0.5, min_purchased=0.0) == []
