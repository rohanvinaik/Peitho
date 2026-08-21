"""peitho.noticer — the anomaly FIELD over the grid: every cell's ternary signature, surfaced wide.

`DATA_GEOMETRY_ARCHITECTURE` §3 (Entity Position Vector) + Pattern 6a (asymmetric emission). For each
variant×store cell the three banks (INVENTORY need, PRICE markdown, SPATIAL surplus/deficit) each place it
at a signed-ternary COORDINATE off its own mined zero; the cell's **signature** is that coordinate in
bank-space `(INVENTORY, PRICE, SPATIAL)`. The noticer surfaces every cell whose signature is not all-zero
(asymmetric emission: silence is the default — a cell with no bank opinion is dropped), and groups the rest
by signature. Each distinct non-zero signature IS an anomaly class (the Discrimination Guarantee: cells that
differ in bank-space differ in signature), so the natural taxonomy falls out for free.

Deliberately NOT here: `tally`/`interference`. Pattern 6a interference needs the banks oriented toward one
question ("restock?") before their signs can be counted against each other; summing unoriented banks
("does surplus agree with markdown?" — agree on WHAT?) is the incommensurate-averaging error. Orientation is
a per-capability CONSUMER step (restock is the first consumer, built on top of this field). The noticer keeps
the raw, discrimination-preserving signature field so cells that are useless for restock stay available as
input surfaces for other capabilities. No statistics, no scores: a coordinate, an emission rule, a grouping.
"""

from __future__ import annotations

from dataclasses import dataclass

from .banks import (
    INVENTORY,
    PRICE,
    SPATIAL,
    VELOCITY,
    inventory_position,
    price_position,
    spatial_position,
    velocity_position,
)
from .grid import Cell, Grid
from .lenses.inventory import mine_store_baselines, mine_store_velocity_baselines
from .lenses.price import mine_store_discount_baselines
from .position import signature

# The default informational-zero band for the two DEVIATION banks (INVENTORY, PRICE). `deviation` is
# FRACTIONAL ((value − zero)/zero), so this is unit-free: a cell within ±10% of its store's mined norm has
# no opinion on that axis. A fixed sensible band, deterministic — NOT a mined statistic. Per-bank calibration
# (a tighter/looser band, or one mined per section) is a documented refinement, passed in per call.
DEFAULT_TOL: float = 0.10

# The signature order — sorted(bank constants), matching `position.signature`'s fixed ordering
# (INVENTORY < PRICE < SPATIAL < VELOCITY).
DIMS: tuple = (INVENTORY, PRICE, SPATIAL, VELOCITY)

# Mechanical rendering of each axis sign — the literal meaning the bank docstrings assign to +1/-1/0, NOT an
# invented narrative. `·` is the informational zero (that axis abstains).
VOCAB: dict = {
    INVENTORY: {1: "surplus", -1: "deficit", 0: "·"},  # cover vs the store's mined cover norm
    PRICE: {1: "marked-down", -1: "full-price", 0: "·"},  # markdown depth vs the store's mined markdown norm
    SPATIAL: {1: "spare", -1: "short", 0: "·"},  # unit surplus/deficit vs the node's own coverage target
    VELOCITY: {1: "accelerating", -1: "fading", 0: "·"},  # recent sale-rate vs the store's mined tempo
}

# Emission verdict (asymmetric emission, Pattern 6a): a cell is FLAGGED iff at least one bank has an opinion.
FLAGGED = "FLAGGED"
SILENT = "SILENT"


def emission(sig: tuple) -> str:
    """Asymmetric-emission verdict for a cell's ternary signature: `FLAGGED` if ANY bank is non-zero (the
    cell sits off the norm on at least one axis → an anomaly worth surfacing), else `SILENT` (every bank
    abstains → drop; silence is the default, never emitted). Pure over the signature tuple — the go-wide
    rule: any anomaly, not just the restock-shaped ones."""
    return FLAGGED if any(s != 0 for s in sig) else SILENT


def axis_word(dimension: str, sign: int) -> str:
    """The literal meaning of one bank's sign (`VOCAB`): e.g. INVENTORY `-1` → "deficit", PRICE `+1` →
    "marked-down", any `0` → "·" (abstains). A mechanical lookup, not an interpretation. Pure over
    `(dimension, sign)`."""
    return VOCAB[dimension][sign]


def describe(sig: tuple) -> str:
    """Render a signature as a legible, mechanical label — one `DIM:word` token per axis, in signature order
    (e.g. `INVENTORY:deficit PRICE:· SPATIAL:short`). Pure over the signature tuple. This names the anomaly
    CLASS by what the geometry says, imputing no story the consumer hasn't asked for."""
    return " ".join(f"{d}:{axis_word(d, s)}" for d, s in zip(DIMS, sig, strict=True))


@dataclass(frozen=True)
class Anomaly:
    """One surfaced (variant × store) cell: its signature (the anomaly class), the mechanical label, and the
    full bank positions — `depth` retained, so the magnitude is not discarded and a consumer can orient/rank."""

    variant: object
    store: str
    signature: tuple
    label: str
    positions: dict  # {dimension: DimensionPosition}


def cell_positions(
    cell: Cell,
    cover_zero: float | None,
    markdown_zero: float | None,
    velocity_zero: float | None,
    inv_tol: float = DEFAULT_TOL,
    price_tol: float = DEFAULT_TOL,
    vel_tol: float = DEFAULT_TOL,
) -> dict:
    """Build one cell's full bank position vector `{dimension: DimensionPosition}` — the four concurrent
    independent coordinates off the cell's store zeros. Keyed by the bank constants so `signature` orders them
    canonically. Pure over the cell + its store's mined zeros; the banks do the placing, this only gathers."""
    return {
        INVENTORY: inventory_position(cell, cover_zero, inv_tol),
        PRICE: price_position(cell, markdown_zero, price_tol),
        SPATIAL: spatial_position(cell),
        VELOCITY: velocity_position(cell, velocity_zero, vel_tol),
    }


def notice(
    grid: Grid, inv_tol: float = DEFAULT_TOL, price_tol: float = DEFAULT_TOL, vel_tol: float = DEFAULT_TOL
) -> list:
    """The anomaly field over the whole grid: mine each store's zeros once, then for every variant×store cell
    build its signature and keep it iff it is FLAGGED (asymmetric emission — silent cells are dropped).
    Returns the list of `Anomaly`. The I/O shell (loops the grid); the decisions it makes are the pinned pure
    functions above. Go-wide: this is EVERY off-norm cell, restock-shaped or not."""
    cover_zeros = mine_store_baselines(grid)
    markdown_zeros = mine_store_discount_baselines(grid)
    velocity_zeros = mine_store_velocity_baselines(grid)
    flagged: list = []
    for variant, cells in grid.items():
        for store, cell in cells.items():
            positions = cell_positions(
                cell,
                cover_zeros.get(store),
                markdown_zeros.get(store),
                velocity_zeros.get(store),
                inv_tol,
                price_tol,
                vel_tol,
            )
            sig = signature(positions)
            if emission(sig) == FLAGGED:
                flagged.append(Anomaly(variant, store, sig, describe(sig), positions))
    return flagged


def class_distribution(anomalies: list) -> list:
    """Group a flagged field by signature — the natural anomaly taxonomy — as `(signature, label, count)`,
    most-common first. Each row is one class of off-norm cell; the non-restock rows are the input surfaces
    kept alive for other capabilities. Pure over the list of `Anomaly`."""
    counts: dict = {}
    labels: dict = {}
    for a in anomalies:
        counts[a.signature] = counts.get(a.signature, 0) + 1
        labels[a.signature] = a.label
    return sorted(((sig, labels[sig], count) for sig, count in counts.items()), key=lambda t: -t[2])
