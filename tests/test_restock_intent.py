"""Hand-authored INTENT test for peitho.restock — the oriented restock consumer, from intent not output.

Pins the orientation (raw bank sign → restock vote) and the Pattern 6a verdict on the ONE question
"restock?": banks agreeing short → RESTOCK, agreeing plenty/being-cleared → HOLD, disagreeing → ESCALATE,
a lone weak voice → IGNORE. This is the layer where tally/interference fire — on oriented votes only.
Signatures are 4-tuples in DIMS order (INVENTORY, PRICE, SPATIAL, VELOCITY).
"""

from peitho.banks import INVENTORY, PRICE, SPATIAL, VELOCITY
from peitho.noticer import Anomaly
from peitho.otp import OPPOSE, ORTHOGONAL, SUPPORT
from peitho.restock import (
    ESCALATE,
    HOLD,
    IGNORE,
    RESTOCK,
    RestockItem,
    orient,
    restock_decision,
    restock_plan,
    restock_votes,
)


def test_orient_turns_raw_signs_into_restock_votes():
    # deficit / short are reasons TO reorder → SUPPORT; surplus / spare are reasons NOT to → OPPOSE
    assert orient(INVENTORY, -1) == SUPPORT and orient(INVENTORY, 1) == OPPOSE
    assert orient(SPATIAL, -1) == SUPPORT and orient(SPATIAL, 1) == OPPOSE
    # PRICE flips the intuition: full-price(-1) is healthy → SUPPORT; marked-down(+1) is being cleared → OPPOSE
    assert orient(PRICE, -1) == SUPPORT and orient(PRICE, 1) == OPPOSE
    # VELOCITY breaks the shared shape: accelerating(+1) → SUPPORT the reorder; fading(-1) → OPPOSE
    assert orient(VELOCITY, 1) == SUPPORT and orient(VELOCITY, -1) == OPPOSE
    # the informational zero stays orthogonal on every bank
    assert orient(INVENTORY, 0) == ORTHOGONAL and orient(VELOCITY, 0) == ORTHOGONAL


def test_restock_votes_orients_a_full_signature_in_dims_order():
    # hard reorder: deficit, full-price, short, accelerating → all four SUPPORT the reorder
    assert restock_votes((-1, -1, -1, 1)) == (SUPPORT, SUPPORT, SUPPORT, SUPPORT)
    # clearable dead stock: surplus, marked-down, spare, fading → all four OPPOSE
    assert restock_votes((1, 1, 1, -1)) == (OPPOSE, OPPOSE, OPPOSE, OPPOSE)


def test_restock_decision_is_oriented_interference_not_an_average():
    # four voices short & healthy & moving → the banks agree → RESTOCK
    assert restock_decision((-1, -1, -1, 1)) == RESTOCK
    # four voices plenty/cleared/dead → agree against → HOLD
    assert restock_decision((1, 1, 1, -1)) == HOLD
    # a lone healthy full-price signal, nothing else → 1 support, below the floor → IGNORE
    assert restock_decision((0, -1, 0, 0)) == IGNORE


def test_velocity_splits_the_deficit_plus_markdown_collapse():
    # THE motivating case (SUBSTRATE_LAWS L8). At the ruled floors (support_min=2, oppose_min=2) VELOCITY
    # resolves the old (-1,1,0) collapse three distinct ways — the discrimination the fourth dimension buys:
    #   dying clearance (fading): INV support, PRICE oppose, VEL oppose → 1 support / 2 oppose → HOLD
    assert restock_decision((-1, 1, 0, -1)) == HOLD
    #   hot line discounted into a stockout (accelerating): INV + VEL support vs the lone PRICE oppose →
    #   2 support / 1 oppose, one opposer no longer vetoes → RESTOCK (reorder the winner)
    assert restock_decision((-1, 1, 0, 1)) == RESTOCK
    #   steady (at-tempo): 1 support / 1 oppose, neither floor reached → the banks are split → ESCALATE
    assert restock_decision((-1, 1, 0, 0)) == ESCALATE


def test_floors_are_tunable_significance_knobs():
    # raise the support floor so two voices are no longer enough → the hard reorder falls to IGNORE
    assert restock_decision((-1, 0, -1, 0), support_min=3, oppose_min=1) == IGNORE
    # at the default floor of 2 the same cell is a clean RESTOCK
    assert restock_decision((-1, 0, -1, 0)) == RESTOCK


def _anom(store, sig):
    return Anomaly("v", store, sig, "label", {})


def test_restock_plan_keeps_only_actionable_and_carries_the_anomaly():
    field = [
        _anom("N8", (-1, -1, -1, 1)),  # RESTOCK — kept
        _anom("N5", (1, 1, 1, -1)),  # HOLD — dropped
        _anom("N4", (-1, 1, 0, 0)),  # ESCALATE (deficit + marked-down, steady tempo) — kept
        _anom("N6", (0, -1, 0, 0)),  # IGNORE — dropped
    ]
    plan = restock_plan(field)
    kept = {(i.store, i.decision) for i in plan}
    assert kept == {("N8", RESTOCK), ("N4", ESCALATE)}
    for item in plan:
        assert isinstance(item, RestockItem)
        assert item.anomaly.signature == item.signature  # the source anomaly is carried, not discarded
