"""peitho.restock — the first ORIENTED consumer of the anomaly field: the restock decision (Pattern 6a).

The noticer surfaces the wide anomaly field (every off-norm cell, un-oriented). A *capability* consumes that
field by orienting the banks toward ONE question and running OTP ternary interference. This is that consumer,
and the question is: **should this cell be restocked (reorder / route units in)?** This is the ONLY place
`otp.tally` / `otp.interference` fire — on a single oriented question, never on the raw field.

ORIENTATION (toward "restock?") — Rohan's significance call; built explicit so it is one edit to change:
  · INVENTORY  deficit(−1) → SUPPORT   (cover below the store norm → a reason to reorder)
               surplus(+1) → OPPOSE    (plenty already)
  · SPATIAL    short(−1)   → SUPPORT   (below the node's own coverage target → needs units)
               spare(+1)   → OPPOSE    (has give-away units — route, don't order)
  · PRICE      full-price(−1) → SUPPORT (a healthy full-margin line worth keeping stocked)
               marked-down(+1) → OPPOSE (being actively cleared → a reason NOT to reorder)
  · VELOCITY   accelerating(+1) → SUPPORT (selling faster than the store tempo → reorder the winner)
               fading(−1)       → OPPOSE  (below tempo / dead → let it die, do not reorder)
The first three banks coincide (each encodes "+1 = a reason not to restock"); VELOCITY breaks that shape
(+1 = accelerating = a reason TO restock) — which is exactly why each row is reasoned independently and kept
per-dimension, never collapsed to a single negation. VELOCITY is the dimension that splits the classes the
other three collapse (deficit+markdown: hot-discounted-stockout vs clearance-dying), per SUBSTRATE_LAWS L8.

FLOORS (`support_min`, `oppose_min`) — also Rohan's calibration: how many supporting / opposing voices the
pattern needs. Default 2 / 2 (ruled 2026-08-20): two voices to call a reorder, and TWO opposers to veto — so a
lone fading vote (VELOCITY is `-1` on ~88% of the field) does NOT sink an otherwise-strong reorder, but two
reasons against (e.g. spare + fading, or surplus + being-cleared) do. This is what lets VELOCITY *discriminate*
(split the collapsed class) without *over-vetoing*: the target `(-1,1,0,·)` resolves hot→RESTOCK / steady→ESCALATE
/ dead→HOLD. Tune per behavior wanted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .banks import INVENTORY, PRICE, SPATIAL, VELOCITY
from .noticer import DIMS, Anomaly
from .otp import (
    AMBIGUOUS,
    CONSTRUCTIVE,
    DESTRUCTIVE,
    OPPOSE,
    ORTHOGONAL,
    SILENT,
    SUPPORT,
    interference,
    tally,
)

# The restock orientation: raw bank sign → its vote on "restock?". Per-dimension and explicit (see module
# docstring for the reasoning of each row); +1 raw is "a reason not to restock" for all three banks today.
RESTOCK_ORIENTATION: dict = {
    INVENTORY: {-1: SUPPORT, 0: ORTHOGONAL, 1: OPPOSE},  # deficit → reorder; surplus → don't
    SPATIAL: {-1: SUPPORT, 0: ORTHOGONAL, 1: OPPOSE},  # short of own target → needs units; spare → route it
    PRICE: {-1: SUPPORT, 0: ORTHOGONAL, 1: OPPOSE},  # full-price → keep stocked; being cleared → don't reorder
    VELOCITY: {1: SUPPORT, 0: ORTHOGONAL, -1: OPPOSE},  # accelerating → reorder the winner; fading → let it die
}

# The significance floors (Rohan's calibration — see module docstring).
DEFAULT_SUPPORT_MIN: int = 2
DEFAULT_OPPOSE_MIN: int = 2

# Restock-domain names for the four interference verdicts (the consumer speaks restock, not raw OTP).
RESTOCK = "RESTOCK"  # CONSTRUCTIVE — the banks agree it is short & worth reordering
HOLD = "HOLD"  # DESTRUCTIVE — the banks agree against (plenty, or being cleared)
ESCALATE = "ESCALATE"  # AMBIGUOUS — the banks disagree (e.g. short of something being cleared) → operator decides
IGNORE = "IGNORE"  # SILENT — no oriented signal survives (a lone weak voice)

_VERDICT: dict = {CONSTRUCTIVE: RESTOCK, DESTRUCTIVE: HOLD, AMBIGUOUS: ESCALATE, SILENT: IGNORE}


def orient(dimension: str, sign: int) -> int:
    """Orient one bank's raw signed-ternary sign toward the restock question (`RESTOCK_ORIENTATION`): returns
    the bank's `SUPPORT`/`OPPOSE`/`ORTHOGONAL` VOTE on "restock?". Pure over `(dimension, sign)`. This is the
    step that turns un-oriented coordinates into commensurate votes so interference is meaningful."""
    return RESTOCK_ORIENTATION[dimension][sign]


def restock_votes(sig: tuple) -> tuple:
    """Orient a full cell signature (in `DIMS` order) into its three restock votes. Pure over the signature."""
    return tuple(orient(d, s) for d, s in zip(DIMS, sig, strict=True))


def restock_decision(sig: tuple, support_min: int = DEFAULT_SUPPORT_MIN, oppose_min: int = DEFAULT_OPPOSE_MIN) -> str:
    """The oriented Pattern 6a verdict for a cell signature: orient → `tally` the supporting/opposing votes →
    `interference` → the restock-domain name. `RESTOCK` / `HOLD` / `ESCALATE` / `IGNORE`. Pure over the
    signature + floors. THIS is where interference finally fires — on the single restock question."""
    supports, opposes = tally(list(restock_votes(sig)))
    return _VERDICT[interference(supports, opposes, support_min, oppose_min)]


@dataclass(frozen=True)
class RestockItem:
    """One cell's restock verdict, carrying the anomaly it came from (signature, label, positions retained)."""

    variant: object
    store: str
    signature: tuple
    decision: str
    anomaly: Anomaly


def restock_plan(anomalies: list, support_min: int = DEFAULT_SUPPORT_MIN, oppose_min: int = DEFAULT_OPPOSE_MIN) -> list:
    """Decide every anomaly in the field, keeping only the ACTIONABLE ones — `RESTOCK` (reorder now) and
    `ESCALATE` (operator judgment) — and dropping `HOLD`/`IGNORE`. The oriented consumer narrows the wide field
    to a restock work-list. The I/O shell over the field; the decision is the pinned `restock_decision`."""
    plan: list = []
    for a in anomalies:
        decision = restock_decision(a.signature, support_min, oppose_min)
        if decision in (RESTOCK, ESCALATE):
            plan.append(RestockItem(a.variant, a.store, a.signature, decision, a))
    return plan
