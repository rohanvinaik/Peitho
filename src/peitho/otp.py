"""peitho.otp — Orthogonal Ternary Projection: the signed-ternary substrate of the data geometry.

`GEOMETRY.md` #1 ("hierarchical **signed-ternary** encoding, with scalar magnitude: `+1` = toward/yes,
`-1` = away/no, `0` = out-of-domain / orthogonal — where honest abstention lives") and #2 ("zero-point
at the semantic mean; a position is a **signed deviation from the norm**"), realized as the
`DATA_GEOMETRY_ARCHITECTURE` Genesis atom (OTP) and its Pattern 6a ("convert each bank to `{+1, 0, -1}`
by a **calibrated per-bank threshold**, then decide by **interference**").

The atom: an entity's position on a bank is a signed-ternary value `{-1, 0, +1}` off that bank's mined
zero-mean (`geometry.deviation`). `+1` = above the norm by enough to matter, `-1` = below, `0` = the
**informational zero** — orthogonal / no signal (at the norm, or out of domain). The zero is confident
**exclusion** (this axis has no opinion), not missing data: because positions compose by **interference**
(Pattern 6a — the ternary values sum), a `0` contributes nothing and so concentrates the decision on the
non-zero banks (the Monty-Hall move). No statistics, no averaging — a threshold into three named states,
pure and Detective-pinnable. This is the atom every bank and the entity position vector are built on.
"""

from __future__ import annotations

# The OTP ternary alphabet (GEOMETRY.md #1). Integers on purpose: an entity's positions compose by
# INTERFERENCE (Pattern 6a — they sum), and the informational zero (0) contributes nothing to that sum.
SUPPORT: int = 1  # +1 — above the mined zero by more than the bank's threshold (surplus / urgent / eroded…)
OPPOSE: int = -1  # -1 — below the mined zero by more than the threshold
ORTHOGONAL: int = 0  # 0 — the informational zero: orthogonal / no signal (at the norm, or out of domain)


def ternary(deviation: float | None, tol: float) -> int:
    """Project a signed deviation from a bank's mined zero onto the OTP ternary `{-1, 0, +1}`.

    Pure over `(float | None, float)`. The **informational zero** (`ORTHOGONAL`, 0) covers two
    honest-abstention cases: `deviation is None` (no data for this entity on this bank — out of domain)
    and `|deviation| <= tol` (at the norm, within the bank's calibrated threshold). A deviation strictly
    above `+tol` is `SUPPORT` (+1); strictly below `-tol` is `OPPOSE` (-1). The zero is thus a confident
    "this axis has no opinion", never a fabricated small signal — which is exactly what lets the positions
    of many banks compose by interference (a summed 0 excludes nothing and inflates nothing).
    """
    if deviation is None:
        return ORTHOGONAL
    if deviation > tol:
        return SUPPORT
    if deviation < -tol:
        return OPPOSE
    return ORTHOGONAL


# ---- interference (Pattern 6a): the set-valued verdict from an entity's ternary VOTES ---------------------
# The decision is the INTERFERENCE of the ternary positions, never their average. Constructive (banks agree
# +) emits; destructive (banks agree −) rejects; a split is the escalate signal; all-orthogonal is silence.
CONSTRUCTIVE = "CONSTRUCTIVE"  # ≥ support_min supports and no destructive floor → the banks agree → emit
DESTRUCTIVE = "DESTRUCTIVE"  # ≥ oppose_min opposes → the banks agree against → reject
AMBIGUOUS = "AMBIGUOUS"  # supports AND opposes both present → the banks DISAGREE → escalate / disambiguate
SILENT = "SILENT"  # neither (every bank orthogonal) → drop (asymmetric emission: silence is the default)


def tally(votes: list) -> tuple[int, int]:
    """Count `(supports, opposes)` — the `+1` and `-1` votes — across an entity's oriented bank positions.
    The `0`s (informational zero) are inert and counted by neither: silence excludes nothing and inflates
    nothing (the Monty-Hall move). Pure over a list of ints."""
    return sum(1 for v in votes if v > 0), sum(1 for v in votes if v < 0)


def interference(supports: int, opposes: int, support_min: int, oppose_min: int) -> str:
    """OTP ternary interference (Pattern 6a): the set-valued emission verdict from the counts of supporting
    (`+1`) and opposing (`-1`) bank votes. `CONSTRUCTIVE` when supports reach `support_min` and opposition
    does not reach its floor (the banks agree → emit); `DESTRUCTIVE` when opposes reach `oppose_min` (agree
    against → reject); `AMBIGUOUS` when both fire, or a mix sits below both floors (the banks DISAGREE — the
    escalate/disambiguate signal); `SILENT` when neither (all orthogonal → drop). Named codes over four ints,
    pure and Detective-pinnable. This is interference, not an average: the verdict is which pattern the
    ternary votes form, and a single opposing bank can veto a pile of weak supports."""
    constructive = supports >= support_min
    destructive = opposes >= oppose_min
    if constructive and destructive:
        return AMBIGUOUS
    if destructive:
        return DESTRUCTIVE
    if constructive:
        return CONSTRUCTIVE
    if supports > 0 and opposes > 0:
        return AMBIGUOUS
    return SILENT
