"""Hand-authored INTENT test for peitho.query.supply — the regime-switched supply sizer (CONTROL_ARCHITECTURE.md
§7). Pins the sizing laws and — the load-bearing integration — that SEASONAL articles get NO reorder (the
window closes before it lands) while BASE/UNKNOWN replenish to base-stock over the lead-time+review interval.
"""

from peitho.grid import Cell, Grid
from peitho.query.supply import (
    base_stock_level,
    critical_fractile,
    regime_order,
    reorder_qty,
    supply_plan,
)


def test_base_stock_level_covers_the_protection_interval():
    assert base_stock_level(2.0, 30, 30, 0) == 120  # 2/day over (lead 30 + review 30) days
    assert base_stock_level(2.0, 30, 30, 10) == 130  # + safety stock


def test_reorder_qty_restores_to_the_level():
    assert reorder_qty(position=40, base_stock=120) == 80
    assert reorder_qty(position=120, base_stock=120) == 0  # already at the level
    assert reorder_qty(position=200, base_stock=120) == 0  # above it -> no order


def test_critical_fractile_is_the_newsvendor_ratio():
    assert critical_fractile(9.0, 1.0) == 0.9  # underage dominates -> high service level
    assert critical_fractile(1.0, 1.0) == 0.5
    assert critical_fractile(0.0, 0.0) == 0.0  # degenerate costs -> 0


def test_regime_order_suppresses_seasonal():
    assert regime_order("SEASONAL", position=5, base_stock=20) == 0  # take the hit, no in-season reorder
    assert regime_order("BASE", position=5, base_stock=20) == 15  # replenish to base-stock
    assert regime_order("UNKNOWN", position=5, base_stock=20) == 15  # conservatively replenish


def test_supply_plan_orders_base_not_seasonal():
    grid = Grid(
        {
            ("BASEART", "RED", "40"): {"N8": Cell("N8", stock=5, sale_qty=100, recent_sales=10, nrv=1.0)},
            ("SEASART", "BLUE", "41"): {"N8": Cell("N8", stock=5, sale_qty=100, recent_sales=10, nrv=1.0)},
        }
    )
    regimes = {"BASEART": "BASE", "SEASART": "SEASONAL"}
    by = {o.article: o for o in supply_plan(grid, regimes, lead_time_days=30, review_days=30)}
    assert set(by) == {"BASEART"}  # only the base article is ordered; the seasonal one is suppressed
    assert by["BASEART"].qty > 0 and by["BASEART"].regime == "BASE"
