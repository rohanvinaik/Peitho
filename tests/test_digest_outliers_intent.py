"""Hand-authored INTENT test for peitho.digest.sale_outliers — the hidden-hot / laggard surprise.

Pins the info-theoretic surprise: an item's sell RATE vs its own niche's typical-seller norm. HIDDEN hot =
strong over-performer of its niche on real sales but NOT an obvious volume leader; LAGGARD = real shelf in a
moving niche selling far below; returns/correction artifacts (negative units) and one-unit flukes are dropped.
"""

from peitho.digest import sale_outliers


def _rec(article, sub, vel, sold, stock):
    return {
        "item": {"article": article, "color": "X"},
        "category": {"sub_category": sub, "cluster": "Footwear"},
        "movement": {"velocity_30d": vel, "sold_window": sold, "sell_through_pct": 50.0},
        "stock": {"total": stock},
    }


def test_sale_outliers_finds_niche_overperformers_and_shelf_sitters():
    # a realistic niche: many typical sellers at a low rate (so the mean reflects a typical item), plus the cases
    recs = [_rec(f"BASE{i}", "Sandals", 3, 3, 5) for i in range(15)]
    recs += [
        _rec("HIDDEN", "Sandals", 12, 6, 3),  # 6u modest, 12/mo ≈ 2× the ~6.5 niche mean → hidden hot
        _rec("OBVIOUS", "Sandals", 40, 50, 5),  # 50u = an obvious volume leader → excluded from HIDDEN by the cap
        _rec("DEAD", "Sandals", 0, 0, 8),  # real shelf, sold nothing, niche moves → laggard
        _rec("RETURN", "Sandals", -5, -2, 4),  # negative units = a returns/correction artifact → dropped
        _rec("FLUKE", "Sandals", 20, 1, 2),  # 1 unit → below the basis floor → not a hidden hot
    ]
    hot, lag = sale_outliers(recs, min_units=2, min_stock=2, min_group=2, min_hot_deviation=0.5, min_lag_deviation=0.5)
    hot_items = {s.fields["item"] for s in hot}
    lag_items = {s.fields["item"] for s in lag}

    assert "HIDDEN" in hot_items  # the modest niche over-performer surfaces (the structure a top-N hides)
    assert "OBVIOUS" not in hot_items  # the volume leader is excluded — it is not "hidden"
    assert "FLUKE" not in hot_items  # a one-unit sale is not a surprise
    assert "DEAD" in lag_items  # real shelf sitting while its niche moves
    assert "RETURN" not in hot_items and "RETURN" not in lag_items  # the artifact is never a finding
    assert all(s.magnitude > 0 for s in hot + lag)  # magnitude is the |deviation| for ranking


def test_sale_outliers_excludes_the_obvious_leader_in_a_small_seller_set():
    # when few items sold, the top-decile percentile index used to land on the MAX, so the obvious ceiling
    # excluded nothing and the single biggest seller leaked in as a 'hidden' hot. The largest volume leader
    # must stay excluded regardless of how few items sold.
    recs = [_rec(f"BASE{i}", "Sandals", 3, 3, 5) for i in range(5)]
    recs.append(_rec("LEADER", "Sandals", 40, 50, 5))  # 50u = the obvious volume leader AND a rate over-performer
    hot, _ = sale_outliers(recs, min_units=2, min_stock=2, min_group=2, min_hot_deviation=0.5, min_lag_deviation=0.5)
    assert "LEADER" not in {s.fields["item"] for s in hot}  # the obvious volume leader is never a "hidden" hot
