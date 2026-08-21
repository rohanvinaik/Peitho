"""Hand-authored INTENT test for route.coverage_target — the calibrated coverage law (CONTROL_ARCHITECTURE
§6, calibrated 2026-08-18 from the landed grid). A node *selling* a SKU holds at least 1 (the ≥1 coverage
floor — the load-bearing law, since velocity×horizon rounds to 0 for the ultra-slow ~97% of the core); a node
*not* selling it holds only the velocity-scaled level (0 if it never sells it), so its stock floods freely.
"""

from peitho.route import coverage_target


def test_selling_node_holds_at_least_one():
    assert coverage_target(0.01, 14, selling=True) == 1  # ultra-slow but live → floor lifts to 1
    assert coverage_target(0.0, 14, selling=True) == 1  # sold recently, ~0 velocity → still keep 1
    assert coverage_target(1.0, 1.0, selling=True) == 1  # base already 1; floor agrees (returns int 1, not None)


def test_non_selling_node_gives_freely():
    assert coverage_target(0.0, 14, selling=False) == 0  # never sells it here → all stock is spare
    assert coverage_target(0.2, 14, selling=False) == 3  # round(0.2×14)=3, no floor applied


def test_fast_mover_scales_above_the_floor():
    assert coverage_target(0.5, 14, selling=True) == 7  # round(0.5×14)=7 — velocity carries it above 1
