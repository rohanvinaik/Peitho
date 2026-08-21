"""Hand-authored INTENT test for peitho.stats — the robust-consensus price (harmonizer shadow-ledger pattern)."""

from peitho.stats import robust_price, weighted_median


def test_weighted_median_resists_minority_outlier():
    assert weighted_median([(83, 4), (500, 1)]) == 83  # plurality of units at 83, the $500 doesn't drag it
    assert weighted_median([(100, 1)]) == 100
    assert weighted_median([]) is None


def test_robust_price_consensus_and_split_flag():
    # the L24 case: 4 units at $83, 1 at $500 -> consensus $83 (not the misleading $166 mean), flagged split
    price, split = robust_price([(83, 3), (83, 1), (500, 1)])
    assert price == 83
    assert split is True  # top 500 >= 2 × the 83 consensus -> two regimes hidden by the blend
    # a single price regime -> no split
    _, s2 = robust_price([(1430, 10), (1400, 5)])
    assert s2 is False
    assert robust_price([]) == (None, False)  # nothing sold -> no price
