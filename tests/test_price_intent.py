"""Hand-authored INTENT tests for peitho.lenses.price — the destash significance.

Both grains (store + item) share one primitive: deviation from a mined baseline. These pin its intent
plus the markdown / margin / band semantics. Pairs with Detective's mutation-complete synth suite.
"""

from peitho.grid import Cell, Grid
from peitho.lenses.price import clearance_band, discount_depth, dump_age_class, margin_pct, taste_verdicts


def test_discount_depth_is_markdown_off_pre_discount_value():
    assert discount_depth(0, 100) == 0.0  # nothing marked down
    assert discount_depth(100, 100) == 50.0  # $100 off a $200 pre-discount value → 50%
    assert discount_depth(940, 60) == 94.0  # the 94%-markdown dump
    assert discount_depth(0, 0) is None  # no sale value → undefined, not 0


def test_margin_pct_goes_negative_below_cost():
    assert margin_pct(50, 100) == 50.0
    assert margin_pct(-60, 10) == -600.0  # sold below cost — the dead-stock dump
    assert margin_pct(5, 0) is None


def test_clearance_band_is_ordinal():
    assert clearance_band(1.0) == "CLEARANCE"
    assert clearance_band(0.4) == "PROMO"
    assert clearance_band(0.0) == "NORMAL"
    assert clearance_band(-0.6) == "FULL_PRICE"


def test_dump_age_class_separates_aged_clearance_from_fresh_dump():
    assert dump_age_class("CLEARANCE", 8 * 365, 365) == "AGED_CLEARANCE"  # 8yr item clearing = correct
    assert dump_age_class("CLEARANCE", 30, 365) == "FRESH_DUMP"  # brand-new at deep cut = suspect
    assert dump_age_class("PROMO", 400, 365) == "AGED_CLEARANCE"  # promo band counts too
    assert dump_age_class("NORMAL", 4000, 365) == "NOT_DUMPED"  # not a clearance/promo -> nothing to explain
    assert dump_age_class("CLEARANCE", None, 365) == "AGE_UNKNOWN"  # no age landed
    assert dump_age_class("CLEARANCE", 365, 365) == "AGED_CLEARANCE"  # exactly at the one-season threshold


# --- the taste-verdict stream: the append-only crown-jewel signal ---
# A bulk normal-priced seller sets N8's own markdown norm LOW, so the target's deep cut deviates ≫ 2× → CLEARANCE.
def _target_grid(held_full_price: bool):
    """Grid with one deep-cut young TARGET at N8; a sibling cell at N3 either holds full price or also dumps."""
    gg_disc = 0.0 if held_full_price else 90.0
    return Grid(
        {
            ("BULK", "BLACK", "9"): {"N8": Cell("N8", 0, 100, 0, 1000.0, discount_amount=100.0, profit=300.0)},
            ("TGT", "GOLD", "8"): {
                "N8": Cell("N8", 0, 1, 0, 10.0, discount_amount=90.0, profit=-80.0),  # 90% off, sold at a loss
                "N3": Cell("N3", 5, 0, 0, 0.0, discount_amount=gg_disc),  # stocked; held full-price or also cut
            },
        }
    )


def test_taste_verdicts_flags_only_fresh_dumps_held_elsewhere():
    # young (< one season) deep cut at N8, held full-price at N3 → a clean, circumstance-isolated taste verdict
    v = taste_verdicts(_target_grid(held_full_price=True), "2026-08-15", ages={"TGT": 30})
    assert [x.variant for x in v] == [("TGT", "GOLD", "8")]  # the bulk normal seller is NOT a verdict
    assert v[0].store == "N8" and v[0].held_elsewhere == ["N3"] and v[0].conditional is True


def test_taste_verdicts_excludes_aged_and_marks_non_isolated_cuts():
    grid = _target_grid(held_full_price=True)
    # an AGED deep cut (≥ one season) is end-of-life clearance, NOT taste → excluded from the stream entirely
    assert taste_verdicts(grid, "2026-08-15", ages={"TGT": 800}) == []
    # young, but the same variant is ALSO dumped at N3 → circumstance not isolated → conditional False
    v = taste_verdicts(_target_grid(held_full_price=False), "2026-08-15", ages={"TGT": 30})
    assert len(v) == 1 and v[0].conditional is False and v[0].held_elsewhere == []
