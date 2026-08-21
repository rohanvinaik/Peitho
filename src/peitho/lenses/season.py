"""peitho.lenses.season — the SEASONAL-EVENT deduction (the harmonizing coherence layer, pure data geometry).

The native clearance report is broken (list-price-noise markdowns, phantom frozen-stock inflating it to a large
fraction of inventory), so we do NOT match it — we IMPUTE what a seasonal sale IS from the discount geometry,
then split the on-sale population into the two disjoint phenomena the operator manages differently:

  SEASONAL — a planned, coordinated end-of-season event: a LARGE cohort cohering on category × vintage, marked
             at a CONSISTENT depth (a policy rate, not scattered cuts), COORDINATED across the store network.
  ONE_OFF  — the operator's spontaneous hand: an isolated, idiosyncratic (often single-store) deep cut on fresh
             stock — the taste signal. The scattered residue once the seasonal cohorts are lifted out.

No timestamps are needed: the coherence lives in the cross-sectional STRUCTURE. `price.dump_age_class` already
flags FRESH_DUMP vs AGED_CLEARANCE per item; this layer is that docstring's deferred "planned-seasonal vs
idiosyncratic mispricing" call, resolved by data geometry rather than a holiday calendar. No AI, no stochastic
step — every threshold is a transparent, tunable knob, and each pure decision returns a named code.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median


def age_cohort(age_days: int | None) -> str:
    """The vintage band an article belongs to — 'which season's stock'. A seasonal event clears ONE intake
    cohort, so binning the age (days since first receipt) groups a season's stock together. Coarse fiscal-cycle
    bands (one intake ≈ one season). None → UNKNOWN. Named codes, never a raw number. Pure over an int|None."""
    if age_days is None:
        return "UNKNOWN"
    if age_days < 180:
        return "CURRENT"  # this season's intake
    if age_days < 365:
        return "LATE_SEASON"  # sold through most of one cycle
    if age_days < 730:
        return "CARRYOVER"  # a year-plus old
    return "AGED"


def cohort_consistency(depths: list) -> float:
    """How CONSISTENT the markdown depths are within a cohort — the "policy rate vs scattered cuts" signal.
    1.0 = every item cut to the same depth (a coordinated policy); → 0 = depths all over the place (a spree of
    idiosyncratic decisions). Defined as 1 − coefficient of variation (std ÷ mean), clamped to [0, 1]; fewer
    than 2 usable depths is trivially consistent (1.0); a non-positive mean → 0.0. Pure over a list of numbers.
    """
    ds = [d for d in depths if d is not None]
    if len(ds) < 2:
        return 1.0
    mean = sum(ds) / len(ds)
    if mean <= 0:
        return 0.0
    var = sum((d - mean) ** 2 for d in ds) / len(ds)
    cv = (var**0.5) / mean
    return max(0.0, min(1.0, 1.0 - cv))


def is_seasonal_cohort(
    articles: int,
    stores: int,
    consistency: float,
    min_articles: int = 8,
    min_stores: int = 3,
    min_consistency: float = 0.6,
) -> bool:
    """Does a (category × vintage) discount cohort read as a coordinated SEASONAL EVENT, or as idiosyncratic
    one-offs? Seasonal requires ALL THREE: LARGE (≥ `min_articles` distinct articles), CROSS-STORE (≥
    `min_stores`), and CONSISTENT depth (≥ `min_consistency`). A big single-store cut is still a one-off spree;
    a scattered-depth cluster is not a policy. The thresholds are transparent knobs, tuned against real output.
    Pure over three numbers."""
    return articles >= min_articles and stores >= min_stores and consistency >= min_consistency


@dataclass
class SeasonalEvent:
    """One imputed seasonal-sale event — the latent policy the broken clearance report never recorded, reconstructed
    from the coherent cohort: its scope (category × vintage, how many articles across how many stores) and its
    imputed policy rate (the typical markdown depth). `consistency` is how tightly the cohort holds that rate."""

    category: str
    vintage: str
    articles: int
    stores: int
    units: int
    typical_depth: float
    consistency: float


def deduce_seasonal_events(cleared: list, category_of, **thresholds) -> dict:
    """Cluster the discounted items over (category-cluster × age-cohort); each coherent cluster — large,
    cross-store, consistent-depth — is an imputed SEASONAL EVENT (carrying its scope + policy rate); the
    scattered residue falls out as ONE-OFFs. `cleared` is a list of price.ClearedItem; `category_of(article)`
    returns its category cluster. Returns {events, seasonal_variants, one_off_variants} — the split the two
    sale reports render (full = seasonal, curated = one-off). Composes the pinned pure decisions; the aggregation
    is the impure shell over the item list."""
    groups: dict = defaultdict(list)
    for i in cleared:
        groups[(category_of(i.variant[0]), age_cohort(i.age_days))].append(i)
    events: list = []
    seasonal: set = set()
    for (cat, vintage), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        articles = len({i.variant[0] for i in items})
        stores = len({i.store for i in items})
        depths = [i.depth for i in items]
        cons = cohort_consistency(depths)
        if is_seasonal_cohort(articles, stores, cons, **thresholds):
            usable = [d for d in depths if d is not None]
            events.append(
                SeasonalEvent(
                    category=cat or "?",
                    vintage=vintage,
                    articles=articles,
                    stores=stores,
                    units=sum(i.units for i in items),
                    typical_depth=round(median(usable), 1) if usable else 0.0,
                    consistency=round(cons, 2),
                )
            )
            seasonal |= {i.variant for i in items}
    all_variants = {i.variant for i in cleared}
    return {
        "events": sorted(events, key=lambda e: -e.articles),
        "seasonal_variants": seasonal,
        "one_off_variants": all_variants - seasonal,
    }
