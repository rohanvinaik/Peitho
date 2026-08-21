"""Hand-authored INTENT test for peitho.banks — the bank position emitters, from intent not output.

Pins DATA_GEOMETRY_ARCHITECTURE §3.4: each bank places a cell at a signed-ternary COORDINATE off its own
mined zero (a deviation → {-1, 0, +1}), never a score. INVENTORY signs days-of-cover vs the cover
baseline; PRICE signs markdown depth vs the store markdown baseline (like-for-like scale).
"""

from peitho.banks import (
    INVENTORY,
    PRICE,
    VELOCITY,
    inventory_position,
    price_position,
    spatial_position,
    velocity_position,
)
from peitho.grid import Cell, Grid
from peitho.lenses.inventory import mine_store_velocity_baselines, recent_velocity
from peitho.otp import OPPOSE, ORTHOGONAL, SUPPORT


def _cell(stock, sale_qty, nrv=1000.0, discount_amount=0.0):
    return Cell(
        store="N8", stock=stock, sale_qty=sale_qty, recent_sales=sale_qty, nrv=nrv, discount_amount=discount_amount
    )


def test_inventory_position_signs_cover_off_the_mined_zero():
    # well-stocked selling cell → cover far above the mined baseline → surplus → SUPPORT
    p = inventory_position(_cell(stock=200, sale_qty=50), cover_zero=30.0, tol=0.1)
    assert p.dimension == INVENTORY and p.sign == SUPPORT
    # stocked-out selling cell → cover 0, below the baseline → deficit → OPPOSE
    assert inventory_position(_cell(stock=0, sale_qty=50), cover_zero=30.0, tol=0.1).sign == OPPOSE
    # stock but no velocity → cover undefined → the informational zero ("low on cover" doesn't apply)
    assert inventory_position(_cell(stock=40, sale_qty=0), cover_zero=30.0, tol=0.1).sign == ORTHOGONAL


def test_price_position_signs_markdown_off_the_mined_zero_like_for_like():
    # cell markdown ~33% (disc 50 on nrv 100) vs a 10% store norm → MORE marked down → SUPPORT
    hot = _cell(stock=5, sale_qty=1, nrv=100.0, discount_amount=50.0)
    p = price_position(hot, markdown_zero=10.0, tol=0.1)
    assert p.dimension == PRICE and p.sign == SUPPORT
    # no realized value → informational zero (the axis abstains)
    dead = _cell(stock=5, sale_qty=0, nrv=0.0, discount_amount=0.0)
    assert price_position(dead, markdown_zero=10.0, tol=0.1).sign == ORTHOGONAL


def test_spatial_position_signs_surplus_and_deficit_at_the_node():
    # selling cell, well stocked → spare above the coverage target → surplus → SUPPORT
    assert spatial_position(_cell(stock=200, sale_qty=50)).sign == SUPPORT
    # selling cell, stocked out → short of the ≥1-floor target → deficit → OPPOSE
    assert spatial_position(_cell(stock=0, sale_qty=50)).sign == OPPOSE
    # idle cell (not selling) → target 0, its stock is give-away-able spare → surplus → SUPPORT
    assert spatial_position(_cell(stock=40, sale_qty=0)).sign == SUPPORT
    # exactly at the ≥1 floor → neither spare nor deficit → the informational zero
    assert spatial_position(_cell(stock=1, sale_qty=50)).sign == ORTHOGONAL


def _vcell(sls_age):
    # a cell whose recent momentum is carried by its sales-age spectrum (velocity reads sls_age, not sale_qty)
    return Cell(store="N8", stock=5, sale_qty=sum(sls_age), recent_sales=sls_age[0], nrv=1000.0, sls_age=tuple(sls_age))


def test_velocity_position_signs_recent_rate_off_the_mined_tempo():
    # selling briskly (all mass in the most-recent band) vs a low mined tempo → accelerating → SUPPORT
    hot = _vcell((60, 0, 0, 0, 0))
    p = velocity_position(hot, velocity_zero=0.01, tol=0.1)
    assert p.dimension == VELOCITY and p.sign == SUPPORT
    # a dead cell — no recent sales → recent velocity 0, far below any positive tempo → fading → OPPOSE
    # (velocity's 0 is a real fading signal, NOT abstention — unlike INVENTORY's undefined-cover zero)
    assert velocity_position(_vcell((0, 0, 0, 0, 0)), velocity_zero=0.5, tol=0.1).sign == OPPOSE
    # exactly at the mined tempo → the informational zero (the axis abstains)
    at = _vcell((30, 0, 0, 0, 0))
    tempo = recent_velocity(at.sls_age)
    assert velocity_position(at, velocity_zero=tempo, tol=0.1).sign == ORTHOGONAL
    # no mined baseline → orthogonal
    assert velocity_position(hot, velocity_zero=None, tol=0.1).sign == ORTHOGONAL


def test_mine_store_velocity_baseline_is_the_demand_weighted_expected_recent_velocity():
    # the store's expected tempo weights each cell's recent velocity by its volume (the mover dominates)
    hot = Cell(store="N8", stock=5, sale_qty=60, recent_sales=60, nrv=1000.0, sls_age=(60, 0, 0, 0, 0))
    slow = Cell(store="N8", stock=5, sale_qty=20, recent_sales=0, nrv=1000.0, sls_age=(0, 0, 0, 0, 20))
    grid = Grid({("A", "BLK", "M"): {"N8": hot}, ("C", "BLK", "M"): {"N8": slow}})
    base = mine_store_velocity_baselines(grid)["N8"]
    expected = (recent_velocity(hot.sls_age) * 60 + recent_velocity(slow.sls_age) * 20) / 80
    assert base == round(expected, 4)
