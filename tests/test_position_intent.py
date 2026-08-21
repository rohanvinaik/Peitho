"""Hand-authored INTENT test for peitho.position — the Entity Position Vector, from intent not output.

Pins DATA_GEOMETRY_ARCHITECTURE §3: each entity is a signed-ternary position across banks off mined
zeros; the ternary SIGNATURE is its coordinate; and the DISCRIMINATION GUARANTEE (§3.3) is Hamming > 0
between semantically-different entities — a Hamming of 0 is a structural break, not a tuning problem.
"""

from peitho.otp import OPPOSE, ORTHOGONAL, SUPPORT
from peitho.position import DimensionPosition, deviation_position, discriminates, hamming, signature


def test_deviation_position_signs_off_the_mined_zero():
    # cover 45 vs a mined zero of 30 → above the norm → SUPPORT; depth is the |deviation| (scalar magnitude)
    p = deviation_position("INVENTORY", value=45.0, zero_state=30.0, tol=0.1)
    assert p.sign == SUPPORT
    assert p.depth == abs((45.0 - 30.0) / 30.0)  # 0.5
    assert p.zero_state == 30.0
    assert deviation_position("INVENTORY", value=15.0, zero_state=30.0, tol=0.1).sign == OPPOSE


def test_no_data_or_at_the_norm_is_the_informational_zero():
    assert deviation_position("PRICE", value=None, zero_state=0.2, tol=0.1).sign == ORTHOGONAL  # abstain
    assert deviation_position("PRICE", value=0.21, zero_state=0.2, tol=0.1).sign == ORTHOGONAL  # within tol


def test_signature_is_the_ternary_coordinate_in_fixed_order():
    positions = {
        "PRICE": DimensionPosition("PRICE", OPPOSE, 0.4, 0.2),
        "INVENTORY": DimensionPosition("INVENTORY", SUPPORT, 0.5, 30.0),
        "SPATIAL": DimensionPosition("SPATIAL", ORTHOGONAL, 0.0, None),
    }
    # sorted by dimension name → INVENTORY, PRICE, SPATIAL
    assert signature(positions) == (SUPPORT, OPPOSE, ORTHOGONAL)


def test_discrimination_guarantee_is_hamming_over_the_signature():
    a = (SUPPORT, OPPOSE, ORTHOGONAL)
    b = (SUPPORT, ORTHOGONAL, OPPOSE)  # differs on 2 dimensions
    assert hamming(a, b) == 2
    assert discriminates(a, b) is True
    # two entities at the SAME signature are NOT discriminated — a structural break (§3.3), not a tuning knob
    assert hamming(a, a) == 0
    assert discriminates(a, a) is False
