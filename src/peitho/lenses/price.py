"""peitho.lenses.price — the PRICE / discount / margin lens (destash noticing, pure data geometry).

Two CO-EQUAL grains, both the same significance primitive as the inventory watcher — a signed deviation
from a data-mined zero-mean:

  - STORE grain  : which store is running clearance? Each store's markdown depth vs the cross-store norm.
                   (a store marking down far deeper than the peer norm → a large +deviation → "that store is clearing".)
  - ITEM grain   : which specific items are being dumped? Each variant's markdown depth vs its store's own
                   normal depth. (An article at near-total markdown in a modest-norm store → a huge +deviation.) Carries
                   the variant's image URL — the item-photo system, engaged here.

Campaigns are AUTO-DETECTED from the discount structure (a store/item discounting above baseline). Grounding
those detections to real-world events (an oracle / a holiday/seasonal calendar) is a future
layer, deliberately not here. Temporal 'did the sale lift volume enough' comparison is Tier-2 (windowed OLAP
pulls); this lens is the cross-sectional snapshot on the landed grid.

Data source: the active cassette's per-store variant grid (via the data-input adapter, `peitho.source`).
No stochastic component; every number is the authoritative pull's own figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..geometry import deviation
from ..grid import Grid
from ..source import load_grid as _load_grid


def discount_depth(discount_amount: float, nrv: float) -> float | None:
    """Markdown depth: discount as % of the pre-discount (≈ list price) value = disc / (nrv + disc). None when
    there is no sale value to mark down. Pure over two numbers."""
    base = nrv + discount_amount
    if base <= 0:
        return None
    return round(discount_amount / base * 100, 2)


def margin_pct(profit: float, nrv: float) -> float | None:
    """Gross margin as % of realized value. None when there is no realized value. Pure."""
    if nrv <= 0:
        return None
    return round(profit / nrv * 100, 2)


def clearance_band(dev: float) -> str:
    """Named ordinal band from the discount deviation — never a bare bool. Total over any number.
    CLEARANCE : ≥ 2× the normal discount   PROMO : meaningfully above   NORMAL   FULL_PRICE : well below."""
    if dev >= 1.0:
        return "CLEARANCE"
    if dev >= 0.4:
        return "PROMO"
    if dev > -0.5:
        return "NORMAL"
    return "FULL_PRICE"


@dataclass
class StoreClearance:
    store: str
    depth: float  # aggregate markdown depth %
    deviation: float  # vs the cross-store norm
    band: str
    discount_given: float  # amount marked down
    margin_pct: float | None


@dataclass
class ClearedItem:
    variant: tuple
    store: str
    depth: float  # this item's markdown depth %
    deviation: float  # vs the store's normal depth
    band: str
    margin_pct: float | None
    units: int
    image: str
    age_days: int | None  # article vintage = days since first receipt (SKU-age proxy via first-receipt date)
    age_class: str  # AGED_CLEARANCE / FRESH_DUMP / NOT_DUMPED / AGE_UNKNOWN


def load_price_grid(grid_dir: str | None = None) -> Grid:
    """Load the per-store grid via the shared `peitho.grid` abstraction (which delegates to the active
    cassette's data-input adapter; glob order, as before)."""
    return _load_grid(grid_dir)


def mine_store_discount_baselines(grid: Grid) -> dict:
    """Each store's DEMAND-WEIGHTED aggregate markdown depth (Σdiscount / Σ(nrv+discount) over its sold
    cells) — the store's own normal markdown level, the zero-mean for both grains."""
    disc: dict = {}
    base: dict = {}
    for cells in grid.values():
        for store, c in cells.items():
            if c.sale_qty > 0:
                disc[store] = disc.get(store, 0.0) + c.discount_amount
                base[store] = base.get(store, 0.0) + c.nrv + c.discount_amount
    return {s: round(disc[s] / b * 100, 2) for s, b in base.items() if b > 0}


def store_clearance(grid: Grid) -> list:
    """STORE grain: each store's markdown depth and its deviation from the cross-store (peer) norm —
    auto-detecting which stores are running clearance. Sorted most-clearing first."""
    baselines = mine_store_discount_baselines(grid)
    if not baselines:
        return []
    peer_norm = median(baselines.values())
    tot_disc: dict = {}
    tot_nrv: dict = {}
    tot_prof: dict = {}
    for cells in grid.values():
        for store, c in cells.items():
            if c.sale_qty > 0:
                tot_disc[store] = tot_disc.get(store, 0.0) + c.discount_amount
                tot_nrv[store] = tot_nrv.get(store, 0.0) + c.nrv
                tot_prof[store] = tot_prof.get(store, 0.0) + c.profit
    out = []
    for store, depth in baselines.items():
        dev = deviation(depth, peer_norm)
        out.append(
            StoreClearance(
                store,
                depth,
                dev,
                clearance_band(dev),
                round(tot_disc[store], 0),
                margin_pct(tot_prof[store], tot_nrv[store]),
            )
        )
    out.sort(key=lambda s: -s.deviation)
    return out


def dump_age_class(band: str, age_days: int | None, aged_threshold_days: int = 365) -> str:
    """Is a deep markdown EXPECTED (old stock correctly clearing) or SUSPECT (fresh stock being dumped —
    mispriced/overbought)? Combines the clearance band with the article's age. Named codes, never a bool:
      NOT_DUMPED  : not a clearance/promo band — nothing to explain.
      AGE_UNKNOWN : no age landed for this article.
      AGED_CLEARANCE : dumped AND old (≥ threshold) — end-of-life clearance, correct.
      FRESH_DUMP     : dumped AND young (< threshold) — a fresh item at a deep cut. Usually NOT an error:
                       most are stock bought FOR an event (a seasonal/holiday peak) and marked down within
                       that sale window. Which are planned-seasonal vs a genuine mispricing is the deferred
                       campaign-grounding layer's call (the holiday/seasonal calendar).
    Threshold defaults to 365d (one seasonal cycle; new inventory each season) — a tunable knob. Pure.
    NB: age is the receipt-date *vintage* (first receipt); a restocked evergreen reads as old — the
    SKU-code registration age would separate those, but it is not reachable at scale from the backend."""
    if band not in ("CLEARANCE", "PROMO"):
        return "NOT_DUMPED"
    if age_days is None:
        return "AGE_UNKNOWN"
    return "AGED_CLEARANCE" if age_days >= aged_threshold_days else "FRESH_DUMP"


def load_article_ages(age_grid: str | None = None, today: str = "2026-08-15") -> dict:
    """{article: age_days} — the article's vintage — via the active cassette's data-input adapter
    (`peitho.source`), which owns the backend receipt-date parsing."""
    from .. import source

    return source.adapter().load_article_ages(age_grid, today)


def flag_cleared_items(
    grid: Grid,
    baselines: dict | None = None,
    min_deviation: float = 1.0,
    ages: dict | None = None,
    aged_threshold_days: int = 365,
) -> list:
    """ITEM grain: each sold, discounted variant whose markdown depth deviates above its store's normal
    depth — the specific items being dumped. Carries the item's image + SKU-age verdict (AGED_CLEARANCE vs
    FRESH_DUMP, from `ages` keyed by article). Sorted deepest-deviation first."""
    if baselines is None:
        baselines = mine_store_discount_baselines(grid)
    if ages is None:
        ages = {}
    out = []
    for variant, cells in grid.items():
        for store, c in cells.items():
            if c.sale_qty <= 0 or c.discount_amount <= 0:
                continue
            depth = discount_depth(c.discount_amount, c.nrv)
            if depth is None:
                continue
            dev = deviation(depth, baselines.get(store))
            if dev < min_deviation:
                continue
            band = clearance_band(dev)
            age_days = ages.get(variant[0])
            out.append(
                ClearedItem(
                    variant,
                    store,
                    depth,
                    dev,
                    band,
                    margin_pct(c.profit, c.nrv),
                    c.sale_qty,
                    c.image,
                    age_days,
                    dump_age_class(band, age_days, aged_threshold_days),
                )
            )
    out.sort(key=lambda i: -i.deviation)
    return out


@dataclass
class TasteVerdict:
    """One FRESH_DUMP verdict-event, stamped for the append-only taste ledger. The operator's gut annotating an
    item 'bad — dump it' at the store their eye is on (usually the store they are physically present at).
    `held_elsewhere` = the stores where the SAME variant is present (stocked / sold) but NOT being dumped:
    the cross-store posture that isolates TASTE ('cut where their eye is, held where it isn't') from CIRCUMSTANCE
    (damage / returns / a broken size-run would get cut everywhere). `conditional=True` marks that clean signal."""

    date: str
    variant: tuple
    store: str  # where the cut happened
    depth: float
    margin_pct: float | None
    age_days: int | None
    units: int
    image: str
    held_elsewhere: list  # stores holding the same variant full-price — taste isolated from circumstance
    conditional: bool  # held_elsewhere non-empty => the clean, circumstance-isolated taste signal


def taste_verdicts(
    grid: Grid,
    date: str,
    baselines: dict | None = None,
    ages: dict | None = None,
    min_deviation: float = 1.0,
    aged_threshold_days: int = 365,
) -> list:
    """The TASTE-VERDICT stream: every FRESH_DUMP item (a YOUNG variant cut well below its store's own markdown
    norm), stamped with `date` and its cross-store posture. This is the append-only LABELLED log the end-stage
    story engine (Genesis / Regenesis) later reads into the operator's implicit taste rules — the one dataset a
    retail business can't otherwise obtain, because the label ('good item vs dog') lives pre-verbally in a
    long-trained merchant's gut and they emit it physically, as a markdown, every time they walk the floor.

    NOT yet cleaned of the two confounds FRESH_DUMP conflates (see dump_age_class): the seasonal-planned dump
    (bought FOR an event, cut in-window) and pure circumstance (damage/returns). `conditional` flags the subset
    held full-price at another store — the cleanest isolation of judgment from circumstance available from a
    single snapshot (the cross-YEAR twin identity, for evergreens across the annual SKU refresh, is a further
    layer). Pure over the grid; the dated I/O emitter (export.export_taste_ledger) writes it."""
    items = flag_cleared_items(
        grid, baselines=baselines, min_deviation=min_deviation, ages=ages, aged_threshold_days=aged_threshold_days
    )
    out = []
    for it in items:
        if it.age_class != "FRESH_DUMP":
            continue
        held = sorted(
            store
            for store, c in grid.cells_for(it.variant).items()
            if store != it.store and c.discount_amount <= 0 and (c.stock > 0 or c.sale_qty > 0)
        )
        out.append(
            TasteVerdict(
                date, it.variant, it.store, it.depth, it.margin_pct, it.age_days, it.units, it.image, held, bool(held)
            )
        )
    return out


def report(top: int = 15) -> None:
    grid = load_price_grid()
    print("STORE grain — clearance activity (markdown depth vs peer norm):")
    for s in store_clearance(grid):
        m = f"{s.margin_pct:.0f}%" if s.margin_pct is not None else "—"
        print(
            f"  [{s.band:10}] {s.store}  depth={s.depth:>4.1f}%  dev={s.deviation:+.2f}  "
            f"${s.discount_given:>12,.0f} marked down  margin={m}"
        )
    ages = load_article_ages()
    items = flag_cleared_items(grid, ages=ages)
    fresh = sum(1 for i in items if i.age_class == "FRESH_DUMP")
    aged = sum(1 for i in items if i.age_class == "AGED_CLEARANCE")
    print(
        f"\nITEM grain — {len(items)} items being dumped (markdown ≫ store norm). SKU-age split: "
        f"{aged} AGED_CLEARANCE (end-of-life) · {fresh} FRESH_DUMP (likely event/seasonal). Top {top}:"
    )
    for i in items[:top]:
        art, col, size = i.variant
        m = f"{i.margin_pct:>4.0f}%" if i.margin_pct is not None else "   —"
        img = "📷" if i.image else "  "
        age = f"{i.age_days // 365}y" if i.age_days is not None else "  ?"
        print(
            f"  [{i.age_class:14}] {i.store}  {art} {col} {size}  markdown={i.depth:>4.0f}%  "
            f"margin={m}  age={age:>3}  sold={i.units:>3} {img}"
        )


if __name__ == "__main__":
    report()
