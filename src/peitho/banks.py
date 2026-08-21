"""peitho.banks — each bank places an entity on its own independent signed dimension.

`DATA_GEOMETRY_ARCHITECTURE` §3.4: banks are **concurrent independent signed dimensions** — a bank reads
the entity's raw fact through its existing lens primitive and places the entity at a signed-ternary
position off its OWN mined zero (`position.deviation_position` → `otp.ternary`). Banks do NOT share
activation, and they do NOT fuse or average — each emits a **coordinate**; the decision (interference
*across* banks) is a separate step (Pattern 6a). A lens primitive + a signed deviation off a mined zero →
`{-1, 0, +1}`. No statistics, no scores: a coordinate on a signed dimension.
"""

from __future__ import annotations

from .grid import Cell
from .lenses.inventory import WINDOW_DAYS, cover_days, recent_velocity
from .lenses.price import discount_depth
from .otp import OPPOSE, ORTHOGONAL, SUPPORT
from .position import DimensionPosition, deviation_position
from .route import COVER_DAYS_DEFAULT, coverage_target, deficit_units, spare_units

INVENTORY = "INVENTORY"
PRICE = "PRICE"
SPATIAL = "SPATIAL"
VELOCITY = "VELOCITY"


def inventory_position(
    cell: Cell, cover_zero: float | None, tol: float, window_days: int = WINDOW_DAYS
) -> DimensionPosition:
    """Place a variant×store cell on the INVENTORY dimension: its **days-of-cover** vs the store×category
    mined cover baseline (the zero). `+1` = cover ABOVE the norm (surplus), `-1` = BELOW (deficit), `0` = at
    the norm OR no velocity (cover undefined → the informational zero: "low on cover" does not apply to a
    cell nothing sells). Reads `inventory.cover_days`; the sign is a deviation off the mined zero, not a score."""
    cover = cover_days(cell.stock, cell.sale_qty, window_days)
    return deviation_position(INVENTORY, cover, cover_zero, tol, path=(cell.store,))


def price_position(cell: Cell, markdown_zero: float | None, tol: float) -> DimensionPosition:
    """Place a variant×store cell on the PRICE dimension: its **markdown depth (%)** vs the store's mined
    demand-weighted markdown baseline (the zero — `mine_store_discount_baselines`). Uses the SAME quantity
    the baseline mines (`discount_depth`, ×100 to match its percentage scale — Serena-verified), so the
    deviation is like-for-like. `+1` = MORE marked down than the store norm, `-1` = LESS, `0` = at the norm
    OR no realized value (informational zero). `discount_depth` is the list-price-structural markdown,
    matching the base."""
    depth = discount_depth(cell.discount_amount, cell.nrv)
    depth_pct = depth * 100 if depth is not None else None
    return deviation_position(PRICE, depth_pct, markdown_zero, tol, path=(cell.store,))


def spatial_position(
    cell: Cell, cover_days_horizon: float = COVER_DAYS_DEFAULT, window_days: int = WINDOW_DAYS
) -> DimensionPosition:
    """Place a variant×store cell on the SPATIAL dimension: the node's **surplus(+)/deficit(−)** of this
    variant against its OWN coverage target (the "store itself" zero-state, §4). Reuses `route.coverage_target`
    (the ≥1-floor law) over the recency velocity + `route.spare_units`/`deficit_units`. `+1` = spare to give
    away, `-1` = short of target, `0` = at target (informational zero). The `depth` is the unit surplus/deficit;
    this is the node position the signed Bellman-Ford routing navigates over. No fractional deviation here —
    the spatial deviation IS the unit surplus/deficit (§4), so idle stock reads as surplus, not abstention."""
    vel = recent_velocity(cell.sls_age, window_days=window_days)
    target = coverage_target(vel, cover_days_horizon, cell.recent_sales > 0)
    spare = spare_units(cell.stock, target)
    if spare > 0:
        return DimensionPosition(SPATIAL, SUPPORT, float(spare), float(target), (cell.store,))
    deficit = deficit_units(cell.stock, target)
    if deficit > 0:
        return DimensionPosition(SPATIAL, OPPOSE, float(deficit), float(target), (cell.store,))
    return DimensionPosition(SPATIAL, ORTHOGONAL, 0.0, float(target), (cell.store,))


def velocity_position(
    cell: Cell, velocity_zero: float | None, tol: float, window_days: int = WINDOW_DAYS
) -> DimensionPosition:
    """Place a variant×store cell on the VELOCITY dimension: its **recent sale-rate** vs the store's mined
    expected recent velocity (the zero — `mine_store_velocity_baselines`). `+1` = ACCELERATING (selling faster
    than the store's demand-weighted tempo — a mover), `-1` = FADING (slower, incl. a dead cell whose recent
    velocity is 0 → a real fading signal, not abstention), `0` = at the tempo OR no mined baseline. The fourth
    orthogonal dimension: it splits situations the other three collapse (deficit+markdown: hot-discounted vs
    dying). A deviation off a mined zero, not a score."""
    vel = recent_velocity(cell.sls_age, window_days=window_days)
    return deviation_position(VELOCITY, vel, velocity_zero, tol, path=(cell.store,))
