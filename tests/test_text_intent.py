"""Hand-authored INTENT tests for peitho.text — the shared SymbolicSpellCheck noisy-channel primitives.

Extracted alongside the functions themselves (from peitho.customer) so the pins live with their true home.
Paired with Detective's mutation-complete synth suites for text.py.
"""

from peitho.text import canon_map, fuzzy_fold, levenshtein


def test_levenshtein_edit_distance():
    assert levenshtein("cat", "cat") == 0
    assert levenshtein("cat", "cut") == 1
    assert levenshtein("Smit", "Smith") == 1
    assert levenshtein("kitten", "sitting") == 3


def test_fuzzy_fold_snaps_rare_to_common():
    corpus = {"Smith": 500, "Brown": 500}
    assert fuzzy_fold("Smit", corpus, max_dist=1, min_ratio=10) == "Smith"  # typo -> canonical
    assert fuzzy_fold("Smith", corpus, max_dist=1, min_ratio=10) == "Smith"  # canonical stays
    assert fuzzy_fold("Zzz", corpus, max_dist=1, min_ratio=10) == "Zzz"  # no neighbour -> unchanged


def test_canon_map_folds_a_vocabulary_to_canonical_spellings():
    # the whole-vocabulary fixed-point fold (used for subsection labels + product categories)
    corpus = {"SANDAL": 69, "SANDALS": 942, "SLIPERS": 8, "SLIPPERS": 510, "SLIPER": 3, "LOAFERS": 164}
    m = canon_map(corpus)
    assert m["SANDAL"] == "SANDALS"  # singular -> common plural (dist 1)
    assert m["SLIPERS"] == "SLIPPERS"  # missing-letter typo, dist 1 -> canonical
    assert m["SLIPER"] == "SLIPER"  # dist 2 from SLIPPERS -> deliberately NOT folded (max_dist=1)
    assert m["SANDALS"] == "SANDALS"  # already canonical, unchanged
    assert m["LOAFERS"] == "LOAFERS"  # no near neighbour -> left alone


def test_canon_map_resolves_fold_chains_to_a_fixed_point():
    # HAND BAGS -> HANDBAGS -> HANDBAG must collapse ALL the way, not stop at the intermediate
    m = canon_map({"HAND BAGS": 1, "HANDBAGS": 65, "HANDBAG": 381})
    assert m["HAND BAGS"] == "HANDBAG"  # transitive
    assert m["HANDBAGS"] == "HANDBAG"
