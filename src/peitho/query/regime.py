"""peitho.query.regime — the base-vs-seasonal regime classifier (CONTROL_ARCHITECTURE.md §4).

The controller runs two control laws (THEORY.md §7): (s,S)/base-stock for **base** items that recur and
can be reordered, and newsvendor for **seasonal** items that appear for one window and cannot. So the first
thing the controller must decide, per article, is *which regime it is in* — and the data-geometry answer is
recurrence across financial years: **base items persist across FYs; seasonal items appear in one.**

Identity is the byte-identical product photo where an image is cached (the photo trace — `sku.py`), which
merges the same style sold under different manufacturer article codes across years; where no image is on
disk it falls back to the stable manufacturer `article` code itself, so image-cache gaps never *drop* an
article (they only forgo the cross-code merge). The article code is the stable field (the retailer
the SKU code rotates each FY; the manufacturer article code does not — `sku.py`).

Data reality (verified 2026-08-16): the only endpoint carrying article+image (the article-image endpoint)
windows real data back ~3 FYs (2023-24 → now); older windows are a frozen degenerate floor and the
purchase-history endpoint (7 FYs) has no article dimension. So the recurrence signal is bounded at the
**3 landed FYs**, which is enough to separate a standing item (present across the three) from a season
bet (present in one).

No AI, no stochastic step. The pure decisions below are Detective-pinnable; the I/O shell loads the landed
per-FY article+image and composes. Run with `PEITHO_ROOT` pointed at the data volume.
"""

from __future__ import annotations

BASE = "BASE"
SEASONAL = "SEASONAL"
UNKNOWN = "UNKNOWN"


# ---- pure decisions (Detective-pinnable) -----------------------------------------------------------------


def regime(fy_count: int, total_fy: int, min_base_years: int = 2) -> str:
    """Base vs seasonal from how many financial years an identity appears in. Pure, total over ints.

    `fy_count` = number of FYs the identity was present in; `total_fy` = number of FYs on record.
    Returns UNKNOWN when the history is too shallow to judge recurrence (< 2 FYs) or the identity was
    never seen (`fy_count` < 1); BASE when it recurs (>= `min_base_years`); SEASONAL when it appears in
    exactly one window.
    """
    if total_fy < 2:
        return UNKNOWN  # not enough history to judge recurrence at all
    if fy_count >= min_base_years:
        return BASE  # recurs across years -> a standing item
    if fy_count == 1:
        return SEASONAL  # one window only -> a season bet
    return UNKNOWN  # fy_count <= 0 -> not seen (degenerate); never assert a regime


def article_fy_counts(fy_articles: dict, photo_hash: dict) -> dict:
    """{article: number-of-FYs-its-identity-appears-in}. Pure over dicts.

    `fy_articles` = {fy_name: [article present that FY]}; `photo_hash` = {article: image content-hash}
    for the articles whose image is cached. Identity is the photo-hash where known (so the same style sold
    under different article codes across years counts as one recurring identity) else the article code itself.
    An identity's FY set is the union over all articles that map to it, so a photo shared across colourways
    or across a code re-mint pools their presence.
    """
    identity_fys: dict = {}
    for fy, articles in fy_articles.items():
        for art in articles:
            identity = photo_hash.get(art, art)
            identity_fys.setdefault(identity, set()).add(fy)
    counts: dict = {}
    for articles in fy_articles.values():
        for art in articles:
            counts[art] = len(identity_fys[photo_hash.get(art, art)])
    return counts


def classify(fy_articles: dict, photo_hash: dict, min_base_years: int = 2) -> dict:
    """{article: regime-code} — compose `article_fy_counts` with the `regime` verdict. Pure over dicts.

    `total_fy` is read from the number of FY keys present, so a two-FY history and a three-FY history judge
    recurrence against their own depth.
    """
    total_fy = len(fy_articles)
    counts = article_fy_counts(fy_articles, photo_hash)
    return {art: regime(n, total_fy, min_base_years) for art, n in counts.items()}


# ---- I/O shell (hand-intent tested) ----------------------------------------------------------------------


def fy_dirs(history_dir: str | None = None) -> list:
    """The financial-year subdirectories of the per-store history landing — via the active cassette's adapter."""
    from .. import source

    return source.adapter().fy_dirs(history_dir)


def load_fy_articles(history_dir: str | None = None) -> dict:
    """{fy_name: [distinct article present that FY]} from the landed history — via the adapter."""
    from .. import source

    return source.adapter().load_fy_articles(history_dir)


def load_photo_hash(history_dir: str | None = None, image_dir: str | None = None) -> dict:
    """{article: image content-hash} across all FYs — via the adapter (which uses the article-image hashes)."""
    from .. import source

    return source.adapter().load_photo_hash(history_dir, image_dir)


def article_regimes(history_dir: str | None = None, image_dir: str | None = None, min_base_years: int = 2) -> dict:
    """{article: regime-code} over the landed history — the classifier's I/O entry point. Reads via the
    adapter (fy article-sets + photo hashes), then applies the pure `classify` decision."""
    fy_articles = load_fy_articles(history_dir)
    photo_hash = load_photo_hash(history_dir, image_dir)
    return classify(fy_articles, photo_hash, min_base_years)


def report() -> None:
    """CLI: `python -m peitho.query.regime` — the regime split over the landed history."""
    fy_articles = load_fy_articles()
    if not fy_articles:
        print("no multi-year history landed for the active cassette — set PEITHO_ROOT to the data volume.")
        return
    labels = article_regimes()
    counts = {BASE: 0, SEASONAL: 0, UNKNOWN: 0}
    for code in labels.values():
        counts[code] += 1
    total = len(labels)
    print(f"FYs on record: {len(fy_articles)}  ({', '.join(sorted(fy_articles))})")
    print(f"articles classified: {total:,}")
    for code in (BASE, SEASONAL, UNKNOWN):
        n = counts[code]
        pct = (100 * n / total) if total else 0.0
        print(f"  {code:9s} {n:>6,}  ({pct:4.1f}%)")


if __name__ == "__main__":
    report()
