"""Hand-authored INTENT test for peitho.otp — the OTP signed-ternary atom, from intent not output.

Pins GEOMETRY.md #1-2 / Pattern 6a: a signed deviation off a bank's mined zero projects to {-1, 0, +1};
the informational ZERO is confident abstention (BOTH out-of-domain and at-the-norm), never a small
signal; and positions compose by INTERFERENCE — they sum, the zero contributing nothing.
"""

from peitho.otp import (
    AMBIGUOUS,
    CONSTRUCTIVE,
    DESTRUCTIVE,
    OPPOSE,
    ORTHOGONAL,
    SILENT,
    SUPPORT,
    interference,
    tally,
    ternary,
)


def test_signed_deviation_projects_to_ternary():
    assert ternary(0.5, 0.1) == SUPPORT  # above the norm by > tol
    assert ternary(-0.5, 0.1) == OPPOSE  # below by > tol


def test_informational_zero_is_both_out_of_domain_and_at_the_norm():
    assert ternary(None, 0.1) == ORTHOGONAL  # no data → out of domain → abstain
    assert ternary(0.0, 0.1) == ORTHOGONAL  # exactly at the norm → no signal
    assert ternary(0.05, 0.1) == ORTHOGONAL  # within the calibrated threshold → no signal


def test_threshold_is_exclusive_at_the_band_edge():
    # |dev| == tol is still the informational zero (strict >); just past it earns a position
    assert ternary(0.1, 0.1) == ORTHOGONAL
    assert ternary(-0.1, 0.1) == ORTHOGONAL
    assert ternary(0.1001, 0.1) == SUPPORT
    assert ternary(-0.1001, 0.1) == OPPOSE


def test_positions_compose_by_interference_and_zero_contributes_nothing():
    # Pattern 6a: an entity's bank positions SUM; the informational zero adds nothing (confident exclusion)
    assert sum([SUPPORT, ORTHOGONAL, OPPOSE]) == 0  # a support and an oppose cancel; the zero is inert
    assert sum([SUPPORT, SUPPORT, ORTHOGONAL]) == 2  # two supports, one abstention → +2 net
    assert sum([OPPOSE, OPPOSE, ORTHOGONAL, ORTHOGONAL]) == -2
    # the alphabet IS the ternary itself (so it composes), not a scored proxy
    assert (ORTHOGONAL, SUPPORT, OPPOSE) == (0, 1, -1)


def test_tally_counts_votes_with_the_zero_inert():
    assert tally([SUPPORT, SUPPORT, ORTHOGONAL, OPPOSE]) == (2, 1)  # zeros counted by neither
    assert tally([ORTHOGONAL, ORTHOGONAL]) == (0, 0)  # all silent


def test_interference_is_a_pattern_not_an_average():
    # banks agree in support → constructive → emit
    assert interference(supports=2, opposes=0, support_min=2, oppose_min=2) == CONSTRUCTIVE
    # banks agree against → destructive → reject
    assert interference(supports=0, opposes=2, support_min=2, oppose_min=2) == DESTRUCTIVE
    # a pile of supports does NOT outvote a floor of opposition — both firing is a disagreement → escalate
    assert interference(supports=3, opposes=2, support_min=2, oppose_min=2) == AMBIGUOUS
    # a mix below both floors is still a split → escalate (not silently averaged away)
    assert interference(supports=1, opposes=1, support_min=2, oppose_min=2) == AMBIGUOUS
    # no signal at all → silent (asymmetric emission: silence is the default)
    assert interference(supports=0, opposes=0, support_min=2, oppose_min=2) == SILENT
