"""peitho.text — shared deterministic text primitives (the SymbolicSpellCheck noisy-channel core).

Extracted from `peitho.customer` so more than one lens can reuse the same error-correction move: a rare
token (likely a typo) folds toward a much-more-common token within a small edit distance — the frequency
prior IS the redundancy that error-corrects it, the DNA move (see THEORY.md). The knobs (`max_dist`,
`min_ratio`, `canon_floor`) are tuned per caller over passes. Pure, stochastic-free, no I/O.

Consumers: `peitho.customer.fold_name` (first/last-name corpora) and `peitho.export` (subsection typos).
The primitive is corpus-agnostic — the caller supplies the frequency table for its own vocabulary.
"""

from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings (insert/delete/substitute = 1). Pure over two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fuzzy_fold(token: str, corpus: dict, max_dist: int = 1, min_ratio: int = 10, canon_floor: int = 1) -> str:
    """Fold a (likely-misspelled) token toward its canonical spelling using a frequency corpus —
    the noisy-channel correction. Returns the highest-frequency corpus token that is within `max_dist`
    edits, is at least `min_ratio`× more frequent than `token`'s OWN true frequency, and is itself
    common enough to be canonical (freq ≥ `canon_floor`); else returns `token` unchanged.

    `corpus` MUST be the FULL frequency table — `own` (the token's own frequency) is read from it, so a
    pre-filtered corpus would make `own`=0 for any sub-floor token and collapse the `min_ratio` guard to
    10×1 instead of 10×true_freq. `canon_floor` restricts only which tokens are eligible fold TARGETS.
    Pure over (str, dict)."""
    own = corpus.get(token, 0)
    threshold = min_ratio * max(own, 1)
    best = token
    best_freq = own
    for cand, freq in corpus.items():
        if freq >= canon_floor and freq >= threshold and freq > best_freq and levenshtein(token, cand) <= max_dist:
            best = cand
            best_freq = freq
    return best


def canon_map(corpus: dict, max_dist: int = 1, min_ratio: int = 3, canon_floor: int = 10) -> dict:
    """Fold a whole frequency vocabulary to canonical spellings via `fuzzy_fold`, resolved to a FIXED POINT
    so chains collapse fully (HAND BAGS -> HANDBAGS -> HANDBAG). {token: freq} -> {token: canonical}. Only
    single-edit plural/typo folds; a cycle in the fold graph (freq ties) is broken at the first repeat. The
    generic SSC vocabulary fold — used for subsection labels and product categories alike. Pure over dict."""
    direct = {s: fuzzy_fold(s, corpus, max_dist, min_ratio, canon_floor) for s in corpus}
    out: dict = {}
    for s in corpus:
        seen = {s}
        cur = s
        while direct.get(cur, cur) != cur and direct[cur] not in seen:
            cur = direct[cur]
            seen.add(cur)
        out[s] = cur
    return out
