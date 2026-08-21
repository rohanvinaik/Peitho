"""Hand-authored INTENT test for peitho.query.preclear — the anticipatory pre-clear R6 SCAFFOLD
(CONTROL_ARCHITECTURE.md §8). Pins the pure decisions (would-sell-anyway propensity; the imminent-sale gate)
and the scaffold's two paths: DARK without a clearance calendar, and emitting PRECLEAR for a good-seller not yet
at a SELL node when a sale date is given.
"""

import datetime

from peitho.grid import Cell, Grid
from peitho.query.preclear import (
    PRECLEAR,
    high_sale_propensity,
    preclear_actions,
    should_preclear,
)


def test_high_sale_propensity_is_at_or_above_baseline():
    assert high_sale_propensity(5.0, 4.0) is True  # above baseline -> would sell anyway
    assert high_sale_propensity(4.0, 4.0) is True  # exactly at baseline
    assert high_sale_propensity(2.0, 4.0) is False  # below baseline
    assert high_sale_propensity(5.0, 4.0, min_deviation=0.5) is False  # +25% < the +50% threshold


def test_should_preclear_gate():
    assert should_preclear(True, days_to_sale=5, horizon_days=14, at_sell_node=False) is True
    assert should_preclear(False, 5, 14, False) is False  # not a good seller
    assert should_preclear(True, 5, 14, at_sell_node=True) is False  # already at a SELL node
    assert should_preclear(True, 20, 14, False) is False  # sale too far off
    assert should_preclear(True, -1, 14, False) is False  # sale already passed
    assert should_preclear(True, 0, 14, False) is True  # sale is today


def test_scaffold_is_dark_without_a_calendar():
    grid = Grid({("A", "RED", "40"): {"N4": Cell("N4", stock=5, sale_qty=100, recent_sales=10, nrv=1.0)}})
    assert preclear_actions(grid, baselines={"N4": 0.1}) == []  # no sale_date -> the scaffold is dark


def test_emits_preclear_for_a_good_seller_before_the_sale():
    # N4 (a store, not a SELL node) holds a good seller; the sale is 5 days out -> pre-clear it.
    # WH (zero sales -> induced WAREHOUSE, not RETAIL) and a zero-stock cell are both skipped.
    grid = Grid(
        {
            ("A", "RED", "40"): {
                "N4": Cell("N4", stock=5, sale_qty=100, recent_sales=10, nrv=1.0),  # good seller -> pre-clear
                "WH": Cell("WH", stock=9, sale_qty=0, recent_sales=0, nrv=1.0),  # zero sales -> warehouse, skipped
                "N5": Cell("N5", stock=0, sale_qty=100, recent_sales=10, nrv=1.0),  # no stock -> skipped
            }
        }
    )
    acts = preclear_actions(
        grid,
        baselines={"N4": 0.1},
        sale_date=datetime.date(2026, 8, 23),
        today=datetime.date(2026, 8, 18),
        horizon_days=14,
    )
    assert len(acts) == 1 and acts[0].kind == PRECLEAR and acts[0].rule == "R6" and acts[0].src == "N4"


def test_no_preclear_when_already_at_a_sell_node():
    # N1 is a SELL node -> a good seller there already clears at full margin; nothing to anticipate.
    grid = Grid({("A", "RED", "40"): {"N1": Cell("N1", stock=5, sale_qty=100, recent_sales=10, nrv=1.0)}})
    acts = preclear_actions(
        grid, baselines={"N1": 0.1}, sale_date=datetime.date(2026, 8, 23), today=datetime.date(2026, 8, 18)
    )
    assert acts == []
