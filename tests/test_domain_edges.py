"""DOMAIN-KNOWLEDGE edge cases — the HUMAN half of the two-step. These pin behaviour that an AST-based
mutation tester (neither Detective's --input synthesis NOR mutmut) can reach on its own, because the
distinguishing input requires domain semantics a structural tool has no way to know: that a spell-fold
threshold scales with a token's OWN corpus frequency. Detective correctly flags these as its "modulo N
unproven-equivalent" residue; supplying the input is the human's job, per the discipline.
"""

from peitho.text import fuzzy_fold


def test_fuzzy_fold_threshold_scales_with_the_tokens_own_frequency():
    # threshold = min_ratio * max(own, 1): with own=2 a fold target needs freq >= 10*2 = 20. A 15-freq
    # neighbour is NOT dominant enough (mutate the * to / and 15 >= 10/2=5 would wrongly fold it).
    assert fuzzy_fold("COLORS", {"COLORS": 2, "COLOR": 15}) == "COLORS"
    assert fuzzy_fold("COLORS", {"COLORS": 2, "COLOR": 25}) == "COLOR"  # a genuinely dominant neighbour DOES win
