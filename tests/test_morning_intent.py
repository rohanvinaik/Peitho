"""Hand-authored INTENT test for peitho.morning — the good-morning report-router (#5). The band decision
(is_loud) carries its Detective suite; this pins the COMPOSITION from intent: each domain contributes exactly
one Route, LOUD (attention-worthy) domains sort ahead of QUIET, and the router never cross-ranks incomparable
magnitudes — it keeps the money/action-first domain order within each band (same discipline as the #1 digest).
"""

from peitho.morning import Route, is_loud, morning_routes, rank_routes


def test_is_loud_is_a_threshold_check():
    assert is_loud(200.0, 200.0) is True  # at the threshold -> loud
    assert is_loud(199.0, 200.0) is False


def test_rank_routes_puts_loud_first_keeping_order_not_magnitude():
    a = Route("sale", "r", "LOUD", "c", 5.0)
    b = Route("routing", "r", "QUIET", "c", 9.0)  # bigger magnitude, but QUIET -> stays last
    c = Route("suppliers", "r", "LOUD", "c", 1.0)
    assert [r.domain for r in rank_routes([a, b, c])] == ["sale", "suppliers", "routing"]


def test_morning_routes_composes_all_five_domains_loud_first():
    sale = [{"code": "biggest_bleed", "magnitude": 5000.0, "fields": {"item": "X", "color": "TEAL", "loss": 5000}}]
    routing = {"reorders": 200, "reorder_units": 300, "runs": 10}
    suppliers = {"bands": {"DEAD_STOCK": 11, "LEFT_UNSOLD": 2}}
    clearance = {"peer_norm_depth": 5.0, "clearing_store": {"store": "N8", "depth": 15.0, "deviation": 1.5}}
    seasonal = {"events": 5, "seasonal_items": 400}
    routes = morning_routes(sale, routing, suppliers, clearance, seasonal)
    assert len(routes) == 5
    assert {r.domain for r in routes} == {"sale", "routing", "suppliers", "clearance", "season"}
    assert all(r.band == "LOUD" for r in routes)  # every domain is out of norm today
    assert [r.domain for r in routes] == ["sale", "routing", "suppliers", "clearance", "season"]  # fixed order
    sale_route = next(r for r in routes if r.domain == "sale")
    assert sale_route.fields["loss"] == 5000 and sale_route.report == "title.sale_performance"


def test_morning_routes_marks_a_calm_morning_all_quiet():
    # nothing below cost, network self-covers, no dead suppliers, no store clearing, no seasonal event
    routes = morning_routes(
        [],
        {"reorder_units": 0, "reorders": 0, "runs": 0},
        {"bands": {}},
        {"clearing_store": None},
        {"events": 0, "seasonal_items": 0},
    )
    assert len(routes) == 5 and all(r.band == "QUIET" for r in routes)
