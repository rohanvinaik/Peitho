"""Hand-authored INTENT test for peitho.query.regime — the base-vs-seasonal classifier (CONTROL_ARCHITECTURE
§4). The Detective synth suites characterize what the code does; this pins what it MUST mean: an article
recurring across financial years is BASE, a one-window article is SEASONAL, a history too shallow to judge
recurrence ABSTAINS (UNKNOWN) rather than guessing, and the photo trace MERGES article codes sharing a
byte-identical image so a re-minted / colourway style reads as one recurring identity, not two seasons.
"""

from peitho.query.regime import BASE, SEASONAL, UNKNOWN, article_fy_counts, classify, regime


def test_regime_verdict_is_recurrence_over_depth():
    assert regime(2, 3) == BASE  # present in 2 of 3 FYs -> a standing item
    assert regime(3, 3) == BASE
    assert regime(1, 3) == SEASONAL  # one window only -> a season bet
    assert regime(0, 3) == UNKNOWN  # never seen -> never assert a regime
    assert regime(1, 1) == UNKNOWN  # < 2 FYs on record -> recurrence is unjudgeable


def test_min_base_years_raises_the_bar():
    assert regime(2, 3, min_base_years=3) == UNKNOWN  # 2 < 3 and != 1 -> neither base nor seasonal
    assert regime(3, 3, min_base_years=3) == BASE


def test_standing_vs_season_bet():
    fy = {"2023-2024": ["STD"], "2024-2025": ["STD", "EVENT"], "2025-2026": ["STD"]}
    out = classify(fy, {})
    assert out["STD"] == BASE  # present all three years
    assert out["EVENT"] == SEASONAL  # one year only


def test_shallow_history_abstains_not_asserts():
    # a single FY on record: the article is present, but recurrence is unknowable -> UNKNOWN, not SEASONAL.
    assert classify({"2025-2026": ["X"]}, {}) == {"X": UNKNOWN}


def test_photo_trace_merges_recoded_style_across_years():
    # Same style, different article codes in different years, sharing ONE byte-identical photo -> both BASE.
    # This is the whole point of the photo trace: a code re-mint must not read as two separate seasons.
    fy = {"2024-2025": ["OLD_CODE"], "2025-2026": ["NEW_CODE"]}
    photo = {"OLD_CODE": "hashZ", "NEW_CODE": "hashZ"}
    assert classify(fy, photo) == {"OLD_CODE": BASE, "NEW_CODE": BASE}
    # Without the photo link they would each be one-window SEASONAL:
    assert classify(fy, {}) == {"OLD_CODE": SEASONAL, "NEW_CODE": SEASONAL}


def test_counts_union_fy_presence_over_shared_identity():
    counts = article_fy_counts({"a": ["P"], "b": ["Q"]}, {"P": "h", "Q": "h"})
    assert counts == {"P": 2, "Q": 2}  # shared photo -> one identity present in both FYs
