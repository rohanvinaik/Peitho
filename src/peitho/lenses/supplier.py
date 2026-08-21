"""peitho.lenses.supplier — the SUPPLIER sell-through lens (which suppliers' goods MOVE vs SIT).

Same significance primitive as every other lens — a signed deviation from a data-mined zero-mean — pointed
at each supplier's sell-through (units sold ÷ units purchased). The zero-mean is the peer-median sell-through
(mined, not assumed); a supplier far below it is a dead-stock supplier ("stop buying from them"), far above
is a strong seller. Built on the landed purchase-receipt feed (receipt grain, several fiscal years), which
carries a supplier field + sold/purchased/stock/profit per receipt. No stochastic component.

NB: `rank_suppliers` etc. are the SUPPLIER grain ("which suppliers should we buy more/less from"). The per-
ARTICLE→supplier edge ("who supplies article X") — once "not landed" — now comes from the supplier report
via `load_article_supplier` (`article_supplier_map`), wired into the shadow export.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..geometry import deviation  # the shared significance primitive (signed deviation from baseline)


def sell_through(sold: float, purchased: float) -> float | None:
    """Sell-through = units sold ÷ units purchased over the window. None when nothing was purchased (undefined,
    not zero). >1 means drawing down stock bought in an earlier window. Pure over two numbers."""
    if purchased <= 0:
        return None
    return round(sold / purchased, 4)


def supplier_band(dev: float, stock_left: float | None = None, sold: float | None = None) -> str:
    """Named ordinal band from a supplier's sell-through deviation vs the peer norm — never a bare bool.
    STRONG_SELLER : ≥15% above norm   NORMAL   SLOW : below   DEAD_STOCK : ≥50% below norm.

    In the deadest band, DEAD_STOCK asserts a specific retail fact — *goods are sitting unsold*. That is only
    true when stock REMAINS. When nothing sold AND nothing remains (`sold<=0` and `stock_left<=0`), the goods
    did not sit — they LEFT the store without a sale (return-to-vendor / inter-entity transfer / receipt
    misattribution), a distinct phenomenon that must not be collapsed into DEAD_STOCK → `LEFT_UNSOLD`.
    `stock_left`/`sold` are optional; omitted, the band is the pure sell-through ordinal (back-compatible). Pure."""
    if dev >= 0.15:
        return "STRONG_SELLER"
    if dev > -0.15:
        return "NORMAL"
    if dev > -0.5:
        return "SLOW"
    if sold is not None and sold <= 0 and stock_left is not None and stock_left <= 0:
        return "LEFT_UNSOLD"  # 0 sold AND 0 remains — exited without a sale, NOT sitting
    return "DEAD_STOCK"  # sitting unsold (stock remains, or it moved a little then went dead)


@dataclass
class SupplierScore:
    supplier: str
    sell_through: float
    deviation: float  # vs the peer-median sell-through
    band: str
    purchased: float
    stock_left: float
    profit: float


def load_supplier_purchases(purchase_glob: str | None = None) -> dict:
    """Per-supplier purchase aggregates {supplier: {sold, purchased, stock, profit}} — via the active
    cassette's data-input adapter (`peitho.source`)."""
    from .. import source

    return source.adapter().load_supplier_purchases(purchase_glob)


def load_article_supplier(path: str | None = None) -> dict:
    """{article: supplier} from the backend's supplier report — via the adapter. Empty until pulled. The
    generic flatten lives in `peitho.source.parse_report_table`; the backend column names are in the adapter."""
    from .. import source

    return source.adapter().load_article_supplier(path)


def mine_supplier_baseline(agg: dict) -> float | None:
    """The zero-mean: the PEER-MEDIAN sell-through across suppliers who actually purchased. None if none did."""
    sts = [st for d in agg.values() if (st := sell_through(d["sold"], d["purchased"])) is not None]
    return median(sts) if sts else None


def rank_suppliers(agg: dict, baseline: float | None = None, min_purchased: float = 0.0) -> list:
    """Score each supplier by its sell-through deviation from the peer norm, worst (deadest stock) first.
    Skips suppliers below `min_purchased` (thin signal)."""
    if baseline is None:
        baseline = mine_supplier_baseline(agg)
    out = []
    for s, d in agg.items():
        if d["purchased"] < min_purchased:
            continue
        st = sell_through(d["sold"], d["purchased"])
        if st is None:
            continue
        dev = deviation(st, baseline)
        band = supplier_band(dev, d["stock"], d["sold"])  # stock+sold split DEAD_STOCK vs LEFT_UNSOLD
        out.append(SupplierScore(s, st, dev, band, d["purchased"], d["stock"], d["profit"]))
    out.sort(key=lambda x: x.deviation)
    return out


def report(top: int = 12, min_purchased: float = 200.0) -> None:
    agg = load_supplier_purchases()
    baseline = mine_supplier_baseline(agg)
    ranked = rank_suppliers(agg, baseline, min_purchased)
    dead = sum(1 for s in ranked if s.band == "DEAD_STOCK")
    left = sum(1 for s in ranked if s.band == "LEFT_UNSOLD")
    print(
        f"SUPPLIER lens — sell-through vs peer-median norm ({baseline:.0%}). {len(ranked)} suppliers "
        f"(purchased ≥ {min_purchased:.0f}); {dead} DEAD_STOCK (sitting), {left} LEFT_UNSOLD (gone). Worst {top}:"
    )
    for s in ranked[:top]:
        print(
            f"  [{s.band:13}] {s.supplier[:30]:30} sell-through={s.sell_through:>5.0%}  dev={s.deviation:+.2f}  "
            f"purchased={s.purchased:>6.0f}  stock-left={s.stock_left:>6.0f}  ${s.profit:>12,.0f}"
        )


if __name__ == "__main__":
    report()
