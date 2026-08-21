"""peitho.geometry — the shared significance primitive.

`deviation(value, baseline)` is THE core move of the whole system (THEORY.md): significance is a *signed
fractional deviation from a data-mined zero-mean*. It is reused verbatim across lenses — the price lens
(store + item grains) and the supplier lens both score against their own mined baseline with it. Extracted
here once it had a second consumer module, so no lens depends on another lens merely to borrow the primitive.

(`inventory.urgency_score` is a *related but distinct* function — the same idea, clamped to [0,1] as an
urgency — and stays in inventory; it would move here only if it gained a second consumer.)
"""

from __future__ import annotations


def deviation(value: float | None, baseline: float | None) -> float:
    """The significance primitive: signed fractional deviation from the baseline, (value − baseline) / baseline.
    Positive = above the norm, negative = below. 0.0 when either is missing or the baseline ≤ 0 (unusable).
    Pure over two numbers."""
    if value is None or baseline is None or baseline <= 0:
        return 0.0
    return round((value - baseline) / baseline, 4)
