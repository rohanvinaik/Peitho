"""Hand-authored INTENT test for peitho.geometry — the shared significance primitive."""

from peitho.geometry import deviation


def test_deviation_is_signed_fraction_from_baseline():
    assert deviation(12, 6) == 1.0  # 2× the norm → +1.0
    assert deviation(6, 6) == 0.0  # at the norm
    assert deviation(3, 6) == -0.5  # half the norm
    assert deviation(10, None) == 0.0  # no baseline → 0, not a crash
    assert deviation(10, 0) == 0.0  # unusable baseline → 0
