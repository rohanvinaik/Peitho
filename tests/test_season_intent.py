"""Hand-authored INTENT test for peitho.lenses.season — the one-off vs seasonal coherence deduction (#4). The
pure decisions carry their own Detective suites; this pins, from intent, the load-bearing promise the whole
reframe rests on: a LARGE, CROSS-STORE, CONSISTENT-DEPTH cohort is imputed a coordinated SEASONAL event, while
an idiosyncratic single-store cut falls out as the ONE-OFF residue. `deduce_seasonal_events` is the
--input-inexpressible aggregation (a ClearedItem list + a category callable), so it's characterized here.
"""

from peitho.lenses.price import ClearedItem
from peitho.lenses.season import age_cohort, cohort_consistency, deduce_seasonal_events, is_seasonal_cohort


def _item(article, store, depth, age):
    return ClearedItem((article, "BLK", "40"), store, depth, 1.0, "CLEARANCE", 20.0, 3, "", age, "AGED_CLEARANCE")


def test_age_cohort_bands_the_vintage():
    assert age_cohort(None) == "UNKNOWN"
    assert age_cohort(100) == "CURRENT"
    assert age_cohort(300) == "LATE_SEASON"
    assert age_cohort(500) == "CARRYOVER"
    assert age_cohort(900) == "AGED"


def test_cohort_consistency_rewards_one_policy_depth():
    assert cohort_consistency([30.0, 30.0, 30.0]) == 1.0  # a single coordinated policy rate
    assert cohort_consistency([]) == 1.0  # trivially consistent
    assert cohort_consistency([10.0, 90.0]) < 0.5  # scattered idiosyncratic cuts


def test_is_seasonal_needs_all_three_signals():
    assert is_seasonal_cohort(10, 4, 0.8) is True
    assert is_seasonal_cohort(5, 4, 0.8) is False  # too few articles — not a cohort
    assert is_seasonal_cohort(10, 2, 0.8) is False  # single-ish store — a local spree, not coordinated
    assert is_seasonal_cohort(10, 4, 0.3) is False  # scattered depth — not a policy rate


def test_deduce_splits_coordinated_cohort_from_idiosyncratic_residue():
    cat = {f"SUM-{i}": "Open Footwear" for i in range(10)}
    cat["ODD"] = "Bags"

    def category_of(a):
        return cat.get(a)

    # a coordinated Open-Footwear cohort: 10 articles, ~30% consistent depth, across 4 stores -> SEASONAL
    cohort = [_item(f"SUM-{i}", store, 30.0 + (i % 2), 500) for i in range(10) for store in ("N8", "N5", "N3", "N2")]
    # one idiosyncratic single-store deep cut in a different category -> ONE-OFF residue
    oneoff = [_item("ODD", "N8", 70.0, 500)]

    res = deduce_seasonal_events(cohort + oneoff, category_of)
    assert len(res["events"]) == 1
    ev = res["events"][0]
    assert ev.category == "Open Footwear" and ev.articles == 10 and ev.stores == 4
    assert all(v[0].startswith("SUM-") for v in res["seasonal_variants"])  # the whole cohort reads seasonal
    assert ("ODD", "BLK", "40") in res["one_off_variants"]  # the lone deep cut stays a one-off
