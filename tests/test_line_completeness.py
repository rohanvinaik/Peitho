"""Line/branch-completeness tests — the last reachable arms the pinned decision suites and the shell
integration tests don't happen to route through: the thin adapter delegators, the two CLI demo printers,
and a handful of branch corners (opposing-flow netting, the reconcile flow classes, corpus tokenization,
the no-mobile person, segment recency, resolve's default-regimes + drop). All pure or synthetic-fixture.
"""

import os

import peitho.customer as cust
import peitho.reconcile as reconcile
from peitho.grid import Cell, Grid
from peitho.source import adapter, load_grid


# --- thin adapter delegators (one call each; the example cassette returns its empty/procedural shapes) ---
def test_adapter_delegators_run_on_the_example_cassette():
    from peitho import sku
    from peitho.lenses import inventory
    from peitho.query import regime

    assert regime.fy_dirs() == []  # no multi-year history in the example
    assert sku.load_article_images() == {}  # no image files in the example
    assert isinstance(inventory.load_article_sections(), dict)  # {article: section}


# --- the two CLI demo printers (smoke, on the example cassette) ---
def test_route_report_demo_prints_a_plan(capsys):
    from peitho import route

    route.report()
    out = capsys.readouterr().out
    assert "Transfer plan" in out and "runs (cheapest first)" in out


def test_inventory_report_demo_prints_graded_shortages(capsys):
    from peitho.lenses import inventory

    inventory.report()
    out = capsys.readouterr().out
    assert "Graded shortages" in out


# --- opposing-flow netting: the second-direction-dominates remainder (significance line 70) ---
def test_net_transfers_emits_the_reverse_remainder_when_the_second_direction_dominates():
    from peitho.query.significance import net_transfers
    from peitho.route import Transfer

    v = ("A", "BLK", "40")
    # Transfer(variant, DEST, SOURCE, qty, cost). Insert the weaker A→B first, then the dominant B→A, so the
    # first key iterated yields n < 0 → the reverse-remainder branch.
    out = net_transfers([Transfer(v, "B", "A", 2, 1.0), Transfer(v, "A", "B", 5, 1.0)])
    assert len(out) == 1 and out[0].qty == 3  # 5 − 2 remainder in the dominant B→A direction
    assert (out[0].dest, out[0].source) == ("A", "B")


# --- the reconcile flow classes: transfer + supplier + return in one interval ---
def _write(root, date, records):
    d = adapter().daily_grid_dir(date, root)
    os.makedirs(d, exist_ok=True)
    for st, rows in records.items():
        import json

        recs = [{"article": a, "color": c, "size": s, "stock": k, "sale": q} for (a, c, s, k, q) in rows]
        with open(f"{d}/{st}.json", "w") as fh:
            json.dump({"rows": recs}, fh)


def test_reconstruct_classifies_transfer_supplier_and_return(tmp_path):
    root = str(tmp_path)
    _write(
        root,
        "2026-05-01",
        {
            "N3": [("X", "R", "40", 5, 0)],
            "N1": [("X", "R", "40", 0, 0)],  # X: N3→N1 conserved transfer
            "N2": [("Y", "B", "41", 0, 0)],  # Y: supplier arrival
            "N4": [("Z", "G", "42", 5, 0)],  # Z: return / removal
        },
    )
    _write(
        root,
        "2026-05-02",
        {
            "N3": [("X", "R", "40", 3, 0)],
            "N1": [("X", "R", "40", 2, 0)],
            "N2": [("Y", "B", "41", 5, 0)],
            "N4": [("Z", "G", "42", 0, 0)],
        },
    )
    r = reconcile.reconstruct("2026-05-01", "2026-05-02", root)
    assert r["counts"] == {"transfer": 1, "supplier": 1, "return": 1}
    # stock_management over the same interval exercises the transfer-out attribution (the N3 sender)
    sm = reconcile.stock_management("2026-05-01", "2026-05-02", root=root)
    by = {row["store"]: row for row in sm["stores"]}
    assert by["N3"]["transfer_out_units"] == 2 and by["N1"]["transfer_in_units"] == 2


# --- customer: corpus tokenization + the no-mobile person ---
def test_build_corpora_counts_only_multichar_alpha_tokens():
    first, last = cust.build_corpora([{"fname": "John Robert", "lname": "Smith"}, {"fname": "A", "lname": "X1"}])
    assert first == {"John": 1, "Robert": 1}  # "A" (len 1) and non-alpha tokens dropped
    assert last == {"Smith": 1}  # "X1" is not alphabetic → dropped


def test_resolve_identities_keeps_a_no_mobile_record_as_its_own_person():
    recs = [
        {
            "code": "A",
            "mobile": None,
            "fname": "John",
            "lname": "Smith",
            "nclass": "REAL",
            "gender": "UNSPECIFIED",
            "store": "AC",
            "ordinal": 1,
            "created": "2024",
        }
    ]
    res = cust.resolve_identities(recs, {"John": 10}, {"Smith": 10}, max_dist=1, min_ratio=10, canon_floor=1)
    assert res["stats"]["persons"] == 1  # a record with no mobile cannot be pooled → its own person


# --- mis: the segment recency accumulation (recency_days present) ---
def test_segment_mis_averages_recency_over_nodes_with_a_recency():
    from peitho.mis import segment_mis

    nodes = [
        {"segment": "LOYAL", "rfm": {"monetary": 100.0, "frequency": 3, "recency_days": 10}},
        {"segment": "LOYAL", "rfm": {"monetary": 200.0, "frequency": 5, "recency_days": None}},  # no recency
    ]
    table = segment_mis(nodes)
    assert table["report"] == "segment_mis"
    loyal = next(r for r in table["segments"] if r["segment"] == "LOYAL")
    assert loyal["customers"] == 2 and loyal["avg_recency_days"] == 10  # averaged over the one with a recency


# --- resolve: the default-regimes path + the gate's drop arm ---
def test_resolve_routing_defaults_regimes_and_returns_kept_signals():
    from peitho.resolve import resolve_routing

    out = resolve_routing(load_grid())  # regimes=None → article_regimes(); weak deficits gate to DROP
    assert isinstance(out, list)


# --- config + cassette housekeeping ---
def test_config_detect_root_honours_the_env_override(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("PEITHO_ROOT", str(tmp_path))
    from peitho import config

    importlib.reload(config)
    try:
        assert str(config._detect_root()) == str(tmp_path.resolve())
    finally:
        monkeypatch.delenv("PEITHO_ROOT", raising=False)
        importlib.reload(config)


def test_cassette_repr_and_cache_clearer_registration():
    from peitho import cassette

    assert "Cassette(id=" in repr(cassette.active())

    def _clearer():
        pass

    cassette.register_cache_clearer(_clearer)
    cassette.register_cache_clearer(_clearer)  # same callable again → the already-registered no-op branch


def test_cassette_adapter_missing_package_raises(tmp_path):
    import pytest

    from peitho.cassette import Cassette

    (tmp_path / "manifest.toml").write_text('id = "t"\nadapter = "myadapter"\n')
    c = Cassette(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        _ = c.adapter  # no myadapter/__init__.py under the cassette → FileNotFoundError


def test_customer_rfm_counts_a_bill_with_no_date():
    r = cust.customer_rfm([{"date": "", "amount": 100.0, "bill_no": "AB-1", "cancelled": False}], today="2026-08-15")
    assert r["monetary"] == 100.0 and r["last_visit"] is None  # amount counts; a dateless bill adds no visit date


def test_sale_surprises_skips_a_below_cost_item_with_zero_loss():
    from peitho.digest import sale_surprises

    recs = [
        {
            "item": {"article": "A", "color": "B"},
            "movement": {"below_cost": True, "sold_window": 0, "below_cost_by": 50},
        }
    ]
    s = sale_surprises(recs)
    assert not any(x.code == "biggest_bleed" for x in s)  # 0 units × under-cost = 0 loss → not a bleed surprise


def test_notice_skips_a_silent_cell(capsys):
    from peitho.noticer import notice

    # a real anomaly in store N1, and an all-zero cell in its OWN store N9 (its norms mine to zero → the cell
    # sits at (0,0,0,0) → SILENT → the emit gate's non-FLAGGED arm drops it)
    g = Grid(
        {
            ("A", "B", "40"): {"N1": Cell("N1", 0, 5, 5, 1000.0, cogs=600.0, sls_age=(5, 0, 0, 0, 0))},
            ("Z", "Z", "0"): {"N9": Cell("N9", 0, 0, 0, 0.0)},
        }
    )
    out = notice(g)
    assert len(out) == 1 and out[0].store == "N1"  # only the flagged cell; the silent N9 cell is dropped


def test_resolve_routing_drops_a_fading_isolated_reorder():
    from peitho.resolve import resolve_routing

    # a fast seller sets N1's velocity norm high; a short, fading, isolated item resolves to ORDER and the
    # position gate DROPs it (non-core + fading velocity → not a live reorder)
    g = Grid(
        {
            ("HOT", "BLK", "40"): {"N1": Cell("N1", 10, 40, 20, 8000.0, cogs=4000.0, sls_age=(20, 10, 6, 3, 1))},
            ("COLD", "RED", "38"): {"N1": Cell("N1", 0, 6, 1, 1200.0, cogs=700.0, sls_age=(1, 1, 1, 2, 1))},
        }
    )
    kept = resolve_routing(g)
    assert not any(k.variant[0] == "COLD" for k in kept)  # the fading (velocity −1) isolated ORDER gated to DROP


def test_network_from_cassette_resolves_a_relative_matrix_path(tmp_path):
    from peitho import network

    class _FakeCas:
        data_root = tmp_path
        network = {
            "nodes": ["WH", "N1"],
            "zones": {"WH": "ZONE_A", "N1": "ZONE_A"},
            "roles": {"N1": ["SELL"]},
            "weights": {"matrix": "cost.json", "zone_minutes": {"ZONE_A|ZONE_A": 0.0}},
        }

    ns = network.network_from_cassette(_FakeCas())  # relative matrix → resolved under data_root (lines 78-80)
    assert ns.nodes == ("WH", "N1") and ns.role_set("SELL") == frozenset({"N1"})


def test_manufacturer_section_scores_a_base_regime_reorder(monkeypatch):
    from peitho import ledgers
    from peitho.query.regime import BASE

    monkeypatch.setattr(ledgers, "article_regimes", lambda: {"SH": BASE})  # mark the item core → reorderable
    g = Grid(
        {
            ("SH", "RED", "38"): {
                "N1": Cell("N1", 0, 8, 5, 1600.0, cogs=900.0, sls_age=(5, 2, 1, 0, 0)),
                "N2": Cell("N2", 0, 8, 5, 1600.0, cogs=900.0, sls_age=(5, 2, 1, 0, 0)),
                "N3": Cell("N3", 0, 8, 5, 1600.0, cogs=900.0, sls_age=(5, 2, 1, 0, 0)),
            }
        }
    )
    sec = ledgers.build_manufacturer_section(g)
    assert sec["summary"]["core_orders"] >= 1  # a BASE-regime multi-store shortfall scored as a core supplier order


def test_build_seasonal_section_imputes_events_over_cleared_items(monkeypatch):
    from peitho import ledgers

    monkeypatch.setattr(ledgers, "load_article_ages", lambda: {"A1": 400, "A2": 50, "A3": 50})
    g = Grid(
        {
            # A1 heavily marked down among full-price peers → flagged as cleared → category_of is invoked
            ("A1", "BLK", "40"): {
                "N1": Cell(
                    "N1",
                    3,
                    10,
                    2,
                    5000.0,
                    discount_amount=3000.0,
                    cogs=2000.0,
                    discounted_sale=3000.0,
                    fresh_sale=2000.0,
                )
            },
            ("A2", "RED", "38"): {
                "N1": Cell(
                    "N1", 5, 10, 3, 5000.0, discount_amount=100.0, cogs=2000.0, discounted_sale=100.0, fresh_sale=4900.0
                )
            },
            ("A3", "GRN", "41"): {
                "N1": Cell(
                    "N1", 5, 10, 3, 5000.0, discount_amount=100.0, cogs=2000.0, discounted_sale=100.0, fresh_sale=4900.0
                )
            },
        }
    )
    sec = ledgers.build_seasonal_section(g)
    assert set(sec) == {"summary", "events", "seasonal_items"}


def test_inventory_report_formats_an_unknown_cover(monkeypatch, capsys):
    from peitho.lenses import inventory

    gs = inventory.GradedShortage(
        variant=("A", "B", "40"),
        store="N1",
        cover=None,  # unknown cover → the "—" formatting arm
        urgency=1.0,
        band="RED",
        recent_sales=2,
        priority=1.0,
        surplus=[("WH", 5, "WAREHOUSE", 10.0)],
    )
    monkeypatch.setattr(inventory, "find_graded_shortages", lambda *a, **k: [gs])
    inventory.report()
    assert "—" in capsys.readouterr().out  # a routable shortage with cover None renders the em-dash


def test_build_outliers_section_rows_a_hidden_hot():
    from peitho import ledgers

    # a ≥12-item peer where one item sells far above its niche rate on modest volume → a hidden-hot surprise,
    # so the _row renderer runs over it
    recs = [
        {
            "item": {"article": f"P{i}", "color": "B"},
            "category": {"cluster": "Footwear", "sub_category": "Shoes"},
            "stock": {"total": 50},
            "movement": {"velocity_30d": 2, "sold_window": 6},
        }
        for i in range(11)
    ]
    recs.append(
        {
            "item": {"article": "HOT", "color": "B"},
            "category": {"cluster": "Footwear", "sub_category": "Shoes"},
            "stock": {"total": 50},
            "movement": {"velocity_30d": 12, "sold_window": 4},
        }
    )
    sec = ledgers.build_outliers_section(recs)
    assert sec["summary"]["hidden_hot"] >= 1 and sec["hidden_hot"]  # the _row renderer ran over the hidden hot
