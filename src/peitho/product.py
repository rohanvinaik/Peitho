"""peitho.product — the Item-Semantic node-network's category axis: raw shop idiom → informative analytics.

The backend's `section`/`subsection` are TWO INCONSISTENT lenses — the true category lives in *either*
field (subsection=MENS + section=WALLET is a wallet; subsection=ACCESSORIES + section=SOCKS/POLISH is
care), and gender/age also hide inside them. So the category is recovered by a **deconvolution across
both lenses + the article-code prefix**, not a field lookup.

This module is the MACHINERY only — the deconvolution logic. The category vocabulary itself (which
tokens name which cluster/sub-category, the gender/age tokens, the spelling fixes, the code-prefix
overrides) is a per-company fact and lives in the active cassette's `taxonomy.toml`, loaded into a
`Taxonomy` config. So the same deconvolution serves any retailer; only the plugged-in vocabulary
differs.

Design invariants (the flywheel):
- **Raw is sacred** — the untouched `section`/`subsection` are always carried through (never mutated).
- **Analytical is derived + inherently informative** — clean names ("Men's Wallet", "Ballet Flats").
- **Bidirectional / idempotent** — re-runnable anytime; an unknown token passes through flagged
  `unadjudicated` (never guessed, never dropped) — the adjudication worklist.

The leaf decisions (`resolve_token`, `extract_gender_age`) are pure over primitive maps so they stay
mutation-pinnable; the orchestrators unpack the `Taxonomy`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from . import cassette as _cassette  # config source; it does not import us back (dependency inversion)
from .text import canon_map  # shared fixed-point SSC vocabulary fold (spelling canonicalization)


@dataclass(frozen=True)
class Taxonomy:
    """A company's category vocabulary — the plugged-in data the deconvolution runs over. Built from the
    active cassette's `taxonomy.toml`. All fields are plain maps/sets so the leaf decisions that consume
    them stay expressible and pinnable."""

    clusters: tuple = ()
    relation: dict = field(default_factory=dict)  # token -> (cluster, sub_category)
    gender: dict = field(default_factory=dict)  # token -> gender code (e.g. "M"/"F")
    age: dict = field(default_factory=dict)  # substring token -> age label (e.g. "kids")
    placeholder: frozenset = frozenset()  # non-category filler labels (carry no category signal)
    spelling_fixes: dict = field(default_factory=dict)  # curated dist>=2 typo fixes the SSC fold can't reach
    prefix_map: dict = field(default_factory=dict)  # article-code prefix -> forced category token


def taxonomy_from_cassette(cas=None) -> Taxonomy:
    """Build a `Taxonomy` from a cassette's `taxonomy.toml` (the active cassette when `cas` is None). TOML
    relation values arrive as 2-element arrays → coerced to tuples. Missing sections default empty, so a
    cassette with no taxonomy yields a Taxonomy that resolves nothing (everything → unadjudicated)."""
    cas = cas or _cassette.active()
    t = cas.taxonomy
    relation = {k: tuple(v) for k, v in (t.get("relation") or {}).items()}
    return Taxonomy(
        clusters=tuple(t.get("clusters") or ()),
        relation=relation,
        gender=dict(t.get("gender") or {}),
        age=dict(t.get("age") or {}),
        placeholder=frozenset(t.get("placeholder") or ()),
        spelling_fixes=dict(t.get("spelling_fixes") or {}),
        prefix_map=dict(t.get("prefix_map") or {}),
    )


@lru_cache(maxsize=1)
def active_taxonomy() -> Taxonomy:
    """The process-shared taxonomy for the active cassette. Prefer `cassette.reset()` to swap cassettes
    in-process (it clears this cache too — see the registration below)."""
    return taxonomy_from_cassette()


_cassette.register_cache_clearer(active_taxonomy.cache_clear)  # reset() clears our cache (dependency inversion)


def extract_gender_age(section: str, subsection: str, gender: dict, age: dict) -> tuple[str | None, str | None]:
    """Recover (gender, age_group) from whichever raw field carries a gender/age token (substring-aware
    for age, so 'BS KIDS' -> kids). Neither is a category — they extract to their own fields. Pure over
    two strings + the gender/age maps."""
    g: str | None = None
    a: str | None = None
    for f in (section, subsection):
        u = (f or "").strip().upper()
        if not u:
            continue
        if g is None and u in gender:
            g = gender[u]
        if a is None:
            for tok, label in age.items():
                if tok in u:
                    a = label
                    break
    return g, a


def resolve_token(
    section: str,
    subsection: str,
    article_code: str,
    relation: dict,
    gender: dict,
    age: dict,
    placeholder: frozenset,
    prefix_map: dict,
) -> str:
    """The raw value that NAMES the category — deconvolved across both lenses + the code prefix. A code
    prefix in `prefix_map` forces its token (e.g. a jewelry code line). Otherwise the field whose value is
    a KNOWN category (gender/age excluded) wins, handling the two-lens inconsistency; failing that, the
    first informative-but-unknown token (for provenance → unadjudicated). Returns '' when nothing
    resolves. Pure over the strings + the vocabulary maps."""
    code = (article_code or "").strip().upper()
    for prefix in sorted(prefix_map, key=len, reverse=True):  # longest (most specific) prefix wins, not dict order
        if code.startswith(prefix):
            return prefix_map[prefix]
    fields = [(subsection or "").strip().upper(), (section or "").strip().upper()]
    for u in fields:  # a value that is a KNOWN category (not a gender/age token) wins
        if u and u not in gender and u not in age and u in relation:
            return u
    for u in fields:  # else the first informative-but-unknown token (for provenance -> unadjudicated)
        if u and u not in gender and u not in age and u not in placeholder:
            return u
    return ""


def translate_category(section: str, subsection: str, article_code: str = "", cfg: Taxonomy | None = None) -> dict:
    """Deconvolve the raw taxonomy into the informative analytical category, preserving raw. Returns
    {cluster, sub_category, gender, age_group, status, raw}; status is 'resolved' or 'unadjudicated'
    (unknown token passes through flagged, never guessed). `cfg` defaults to the active cassette's
    taxonomy. Pure given `cfg`."""
    cfg = cfg or active_taxonomy()
    g, a = extract_gender_age(section, subsection, cfg.gender, cfg.age)
    token = resolve_token(
        section, subsection, article_code, cfg.relation, cfg.gender, cfg.age, cfg.placeholder, cfg.prefix_map
    )
    entry = cfg.relation.get(token)
    cluster, sub = entry if entry else (None, None)
    return {
        "cluster": cluster,
        "sub_category": sub,
        "gender": g,
        "age_group": a,
        "status": "resolved" if entry else "unadjudicated",
        "raw": {"section": section or None, "subsection": subsection or None},
    }


def translate_taxonomy(taxo: dict, cfg: Taxonomy | None = None) -> dict:
    """Add an informative analytical `category` to each article's taxonomy entry, NON-destructively — the
    product node-network's category axis. Spelling-canonicalizes the raw section/subsection via the shared
    SSC fold (`text.canon_map`) BEFORE the deconvolution, but preserves the ORIGINAL raw. Idempotent.
    Takes {article: {section, subsection}}, returns the same with a `category` dict added. `cfg` defaults
    to the active cassette's taxonomy. Pure given `cfg` — the caller supplies the raw taxonomy (no I/O)."""
    cfg = cfg or active_taxonomy()
    corpus: Counter = Counter()
    for t in taxo.values():
        for f in ("section", "subsection"):
            v = (t.get(f) or "").strip().upper()
            if v:
                corpus[v] += 1
    canon = canon_map(dict(corpus))  # spelling canon over the full raw-token vocabulary (SSC, dist 1)

    def cx(v: str | None) -> str:
        u = (v or "").strip().upper()
        folded = canon.get(u, u)  # SSC fold first
        return cfg.spelling_fixes.get(folded, folded)  # then the curated dist>=2 typo fixes

    out: dict = {}
    for art, t in taxo.items():
        sec, sub = t.get("section"), t.get("subsection")
        cat = translate_category(cx(sec), cx(sub), art, cfg)
        cat["raw"] = {"section": sec, "subsection": sub}  # ORIGINAL raw, not the spelling-canon form
        out[art] = {**t, "category": cat}
    return out
