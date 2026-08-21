"""peitho.stats — quick robust consensus over noisy observations (ported from the harmonizing project).

The harmonizer's shadow-ledger / emission pattern (Kaggle_Killer/competitions/harmonizing): accumulate all the
noisy observations, then EMIT the robust consensus while suppressing the minority outlier — precision at
emission, not at extraction. Applied here to per-unit prices: a backend item's realized price is a blend across
per-(store,size) cells, and a plain average misleads when the distribution is bimodal (e.g. 4 units at $83 +
1 unit at $500 → mean $166, which no customer ever paid). The weighted median emits the consensus the
*plurality of units* actually transacted at ($83), and a split flag marks where the blend hides two regimes.

Pure, deterministic, no I/O. Not the harmonizer's proteomics code (domain-specific) — its *pattern*.
"""

from __future__ import annotations


def weighted_median(pairs: list) -> float | None:
    """The weighted median of [(value, weight), …] — the robust consensus that resists a minority outlier.
    None on empty input. Pure over a list of (number, number) pairs."""
    pairs = [(v, w) for v, w in pairs if w > 0]
    if not pairs:
        return None
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc * 2 >= total:
            return v
    return pairs[-1][0]  # pragma: no cover — unreachable: last element makes acc==total, so 2*acc>=total fires


def robust_price(pairs: list, split_ratio: float = 2.0) -> tuple:
    """Emit the robust consensus price + a SPLIT flag from per-cell (price, units) observations. The consensus
    is the unit-weighted median (the price the plurality of units went at); SPLIT is True when the top price is
    ≥ `split_ratio`× the consensus — the blend hides two price regimes and a single number would mislead.
    Returns (consensus_or_None, is_split). Pure over a list of (price, units) pairs."""
    valid = [(v, w) for v, w in pairs if w > 0 and v > 0]
    if not valid:
        return (None, False)
    med = weighted_median(valid)
    top = max(v for v, _ in valid)
    split = med is not None and med > 0 and top >= split_ratio * med
    return (round(med) if med is not None else None, bool(split))
