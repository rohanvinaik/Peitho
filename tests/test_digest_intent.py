"""Hand-authored INTENT tests for peitho.digest — the significance digest (out-of-norm 'surprises').

Pins the load-bearing promises: the biggest bleed is the max loss (units × $-under-cost); a group surprise
(category/supplier) only surfaces when it is GENUINELY out of norm (clears min_deviation), never padded; and
nothing below cost → no surprises.
"""

from peitho.digest import sale_surprises, sale_winners


def _rec(art, below, under=0, sold=0, cat=None, sup=None):
    return {
        "item": {"article": art, "color": "BLACK"},
        "category": {"cluster": cat} if cat else {},
        "supplier": sup,
        "movement": {"below_cost": below, "below_cost_by": under, "sold_window": sold},
    }


def test_biggest_bleed_is_max_units_times_under_cost():
    recs = [_rec("A", True, under=100, sold=2), _rec("B", True, under=50, sold=10), _rec("C", False)]
    s = sale_surprises(recs)  # A loss=200, B loss=500 -> B wins; no groups (cat/sup None)
    assert s[0].code == "biggest_bleed"
    assert s[0].fields["item"] == "B" and s[0].fields["loss"] == 500


def test_group_surprise_surfaces_only_when_genuinely_out_of_norm():
    # HOT supplier 100% below cost against a low shop rate -> huge deviation -> surfaces, with its basis
    recs = [_rec(f"H{i}", True, under=10, sold=1, sup="HOT") for i in range(5)]
    recs += [_rec(f"O{i}", i < 2, under=10, sold=1, sup="OTHER") for i in range(20)]  # 2/20 below
    s = sale_surprises(recs, min_group=5)
    hot = next((x for x in s if x.code == "supplier_hot"), None)
    assert hot is not None and hot.fields["supplier"] == "HOT" and hot.fields["pct"] == 100 and hot.fields["of"] == 5


def test_barely_above_norm_is_dropped_not_padded():
    # 30% vs a ~25% shop rate -> deviation ~0.2, below the 1.0 bar -> NO group surprise, only the bleed
    recs = [_rec(f"A{i}", i < 3, under=10, sold=1, sup="MILD") for i in range(10)]  # 3/10
    recs += [_rec(f"B{i}", i < 2, under=10, sold=1, sup="MILD2") for i in range(10)]  # 2/10
    s = sale_surprises(recs, min_group=5)
    assert all(x.code not in ("supplier_hot", "category_hot") for x in s)
    assert s and s[0].code == "biggest_bleed"


def test_nothing_below_cost_means_no_surprises():
    assert sale_surprises([_rec("A", False), _rec("B", False)]) == []


def test_thin_groups_are_ignored():
    # a 100%-below supplier with only 2 items is noise, not a pattern (< min_group)
    recs = [_rec(f"H{i}", True, under=10, sold=1, sup="TINY") for i in range(2)]
    recs += [_rec(f"O{i}", False, sup="BIG") for i in range(30)]
    s = sale_surprises(recs, min_group=15)
    assert all(x.code != "supplier_hot" for x in s)


def _wrec(art, vel, cover):
    return {"item": {"article": art, "color": "BLACK"}, "movement": {"velocity_30d": vel, "days_of_cover": cover}}


def test_sale_winner_is_fast_low_positive_cover_only():
    recs = [
        _wrec("SLOW", 3, 5),  # velocity below the bar -> excluded
        _wrec("OVERSOLD", 20, -3),  # NEGATIVE cover (oversold artifact) -> excluded, never "-3 days left"
        _wrec("DEEP", 10, 60),  # plenty of cover -> not about to run out -> excluded
        _wrec("WIN1", 8, 2),  # fast, low positive cover -> a winner
        _wrec("WIN2", 30, 0),  # fastest, 0 cover (just ran out) -> the MOST urgent winner
    ]
    w = sale_winners(recs, top=1)
    assert len(w) == 1 and w[0].code == "top_mover"
    assert w[0].fields["item"] == "WIN2" and w[0].fields["cover"] == 0  # least cover ranks first
