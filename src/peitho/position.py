"""peitho.position — the Entity Position Vector: the zeroth-order requirement of the data geometry.

`DATA_GEOMETRY_ARCHITECTURE` §3: "Every entity must have a **unique position** in the multi-dimensional
bank space. Without unique positions, the geometry is flat — a list, not a structure." Each dimension
(bank) carries a **signed** position (§3.1): a `sign` in the OTP ternary `{-1, 0, +1}` (direction from the
mined zero, via `otp.ternary`), a `depth` (distance from zero — the scalar magnitude, `GEOMETRY.md` #1),
and `path` nodes (the traversal from zero — the explainability). Banks are **concurrent independent
dimensions** (§3.4) — the entity is placed in each one separately, `ORTHOGONAL` where the bank abstains.

The invariant is the **Discrimination Guarantee** (§3.3): two semantically-different entities MUST have
different position vectors; a Hamming distance of 0 between their ternary signatures is a *structural*
break (too few dimensions / too shallow), fixed by adding dimensions — "never try to compensate with a
model." No statistics: positions are ternary coordinates, and discrimination is a Hamming count.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import otp
from .geometry import deviation


@dataclass(frozen=True)
class DimensionPosition:
    """One bank/dimension's signed position for an entity (§3.1: sign · depth · path · zero_state)."""

    dimension: str
    sign: int  # otp.ternary: +1 above the zero / -1 below / 0 the informational zero (orthogonal)
    depth: float  # distance from the zero — |signed deviation|, the scalar magnitude (GEOMETRY.md #1)
    zero_state: float | None  # the mined zero this position is measured against (the semantic mean, §3.2)
    path: tuple = ()  # the nodes traversed from zero → the explainability (§3.1); evidence for a deviation bank


def deviation_position(
    dimension: str, value: float | None, zero_state: float | None, tol: float, path: tuple = ()
) -> DimensionPosition:
    """Place an entity on a **deviation** bank: `sign = otp.ternary` of its signed deviation off the mined
    `zero_state`, `depth = |deviation|` (the scalar magnitude). Pure over the scalars. `value is None` or a
    missing/≤0 `zero_state` yields deviation 0.0 → the `ORTHOGONAL` informational zero (the bank abstains)."""
    dev = deviation(value, zero_state) if value is not None else 0.0
    return DimensionPosition(dimension, otp.ternary(dev, tol), abs(dev), zero_state, path)


def signature(positions: dict) -> tuple:
    """The entity's **ternary signature** — its coordinate in bank-space: the signs across dimensions in a
    fixed (sorted-by-dimension) order (§3.1/§3.4). This is the object the Discrimination Guarantee tests.
    Pure over `{dimension: DimensionPosition}`."""
    return tuple(positions[d].sign for d in sorted(positions))


def hamming(sig_a: tuple, sig_b: tuple) -> int:
    """Hamming distance between two ternary signatures — the number of dimensions on which two entities
    sit at different positions (§3.3). Pure over two equal-length int tuples."""
    return sum(1 for a, b in zip(sig_a, sig_b, strict=False) if a != b)


def discriminates(sig_a: tuple, sig_b: tuple) -> bool:
    """The **Discrimination Guarantee** (§3.3): do two entities occupy different positions? `True` iff their
    ternary signatures differ (Hamming > 0). A `False` for two entities that *should* differ is a structural
    break in the geometry — the fix is to add dimensions or deepen the hierarchy, never a model."""
    return hamming(sig_a, sig_b) > 0
