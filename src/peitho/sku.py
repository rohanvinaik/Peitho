"""peitho.sku — the SKU identity system: photo-hash DEDUPE + the retailer-SKU registration WORMHOLE.

Two data-geometry views of item identity, grounded in the data. No AI, no stochastic step.

WORMHOLE (retailer-SKU registration ordinal)
  Where a backend mints a retailer SKU (a `sku_code`) as {two-digit fiscal year}{p|P}{sequential
  registration number}, reset each fiscal-year start, the code carries free structure: `<FY>p<seq>`. The FY
  prefix is the item's AGE (exact — an item whose code names an older FY yet is still selling is a genuine
  long-lived/clearance item); the sequence is its registration order within the year. This is the retailer
  SKU — NOT the manufacturer article, which is a different field with its own format. Calendar date within a
  year needs a mint-rate model (deferred); FY-level age is exact.

DEDUPE (photo-hash — the byte-identity efficiency hack)
  The same physical product, photographed once, is often referenced by multiple files as byte-identical reuse.
  One O(n) md5 pass buckets them — the efficiency hack: no O(n²) pairwise compare, no model, deterministic.
  Perceptual hashing (re-compressed copies) is a later refinement; deps can be added if the byte-identical
  yield proves insufficient.

DATA STATUS: where the grid carries `article` + image but not the retailer `sku_code`, the full per-item
wormhole + cross-YEAR SKU dedupe need a sku_code pull (the product master) + prior-year images. The pure
cores below are correct and ready; the reports run on what is landed and flag the gap.
"""

from __future__ import annotations

import glob
import json
import re
from collections import Counter, defaultdict


def parse_sku(sku: str) -> tuple:
    """Decode a retailer SKU (sku_code) into (fy, seq): the two-digit fiscal year and the sequential
    registration number, from the `{FY}{p|P}{seq}` scheme (reset each fiscal-year start). `07p42` → (7, 42).
    The FY is the item's age; the sequence is its registration order within the year. Returns (None, None)
    when the string is not a retailer SKU (e.g. a manufacturer article code in a different format). Pure over
    a string.
    """
    m = re.match(r"^(\d{2})[pP](\d+)$", sku.strip())
    if not m:
        return (None, None)
    return (int(m.group(1)), int(m.group(2)))


def age_years(fy: int | None, current_fy: int) -> int | None:
    """Item age in years from its registration FY. None when the FY is unknown. Pure over two ints."""
    if fy is None:
        return None
    return current_fy - fy


def cluster_by_hash(item_hashes: dict) -> list:
    """Group items that share a content hash into identity clusters. {item: hash} → [[items], …] for every
    hash with more than one member (the deduped groups), largest first. Pure over a dict."""
    by: dict = defaultdict(list)
    for item, h in item_hashes.items():
        by[h].append(item)
    return sorted((sorted(v) for v in by.values() if len(v) > 1), key=len, reverse=True)


def _fname(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def load_article_images(grid_dir: str | None = None) -> dict:
    """{article: image filename} from the grid's Image URLs — via the active cassette's data-input adapter."""
    from . import source

    return source.adapter().load_article_images(grid_dir)


def article_image_hashes(grid_dir: str | None = None, image_dir: str | None = None) -> dict:
    """{article: content-hash} for every article whose image file is present — via the adapter (backend
    image I/O). The pure dedupe clustering (`cluster_by_hash`) stays in the core."""
    from . import source

    return source.adapter().article_image_hashes(grid_dir, image_dir)


def dedupe_articles(grid_dir: str | None = None, image_dir: str | None = None) -> list:
    """Distinct articles that share a byte-identical photo — one STYLE (often across colorways). Combines the
    adapter's image hashes (I/O) with the pure `cluster_by_hash` decision. Largest cluster first."""
    return cluster_by_hash(article_image_hashes(grid_dir, image_dir))


def load_sample_skus(globs: tuple = (), key: str = "sku_code") -> set:
    """The SKUs present in the given landed detail dirs — a recursive walk for `key` values. `globs` (the
    sample-dir patterns) and `key` (the backend's SKU field) are both supplied by the adapter; empty globs →
    empty set. A demo/sample helper (used only by report()); not a production path."""
    skus: set = set()

    def walk(x):
        if isinstance(x, dict):
            if x.get(key):
                skus.add(x[key])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for pat in globs:
        for f in glob.glob(pat, recursive=True):
            try:
                with open(f, encoding="utf-8") as fh:
                    walk(json.load(fh))
            except (OSError, ValueError):  # unreadable file / bad JSON — skip it, keep sweeping
                pass
    return skus


def report() -> None:
    # DEDUPE (real, on current-FY images)
    clusters = dedupe_articles()
    linked = sum(len(c) for c in clusters)
    print(
        f"DEDUPE (photo-hash, byte-identical): {len(clusters)} product groups linking {linked} distinct "
        f"articles as the same product (current-FY images)."
    )
    for c in clusters[:5]:
        print(f"  same product: {', '.join(c[:5])}{' …' if len(c) > 5 else ''}")

    # WORMHOLE (SKU code — on the landed samples)
    from .source import adapter

    current_fy = 26  # the current 2-digit fiscal year (the SKU-code FY prefix)
    skus = load_sample_skus(adapter().sample_sku_globs(), adapter().sample_sku_key())
    decoded = [(parse_sku(s), s) for s in skus]
    ok = [(fy, seq, s) for (fy, seq), s in decoded if fy is not None]
    by_age = Counter(age_years(fy, current_fy) for fy, _, _ in ok)
    print(f"\nWORMHOLE (SKU code {{FY}}p{{seq}}): decoded {len(ok)}/{len(skus)} landed SKUs.")
    print(f"  age (yrs) distribution: {dict(sorted(by_age.items()))}  (higher = older/longer-lived stock)")
    for fy, seq, s in sorted(ok)[:4]:
        print(f"  {s:12} → FY20{fy}, age {age_years(fy, current_fy)}yr, registration #{seq}")
    print("\n  ⚠ full per-item age needs a sku_code pull; the pure decode is ready.")


if __name__ == "__main__":
    report()
