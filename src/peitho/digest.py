"""peitho.digest — the SIGNIFICANCE DIGEST: the few out-of-norm 'surprises' that earn the reader's attention.

Same primitive as every lens — a signed deviation from a data-mined zero-mean — but here the job is to SELECT
and RANK the most surprising signals into a short, reasoned closing summary. This is the harmonizing project's
shadow-ledger idea pointed at retail: extract rich (the lenses already did), then EMIT only the few that matter,
each carrying the norm it broke and the BASIS (how many data points back it) — so a surprise reads as
"X is far from your own normal (Y), and we're saying so on N observations", not a bare number.

DESCRIPTIVE, never prescriptive: it names what deviates from the shop's OWN norm; it never dictates an action.
Pure decision layer — the report renderer formats the `Surprise` objects; the language layer carries the words.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .geometry import deviation  # the shared significance primitive: signed fractional deviation from a baseline


@dataclass
class Surprise:
    """One out-of-norm finding. `code` keys the phrase catalog (`digest.<code>`); `magnitude` is the |significance|
    for cross-finding ranking (bigger = more surprising); `fields` fills the phrase template AND carries the basis
    (counts) so the emitted line can say how many observations back the claim."""

    code: str
    magnitude: float
    fields: dict = field(default_factory=dict)


def _below(m: dict) -> bool:
    """Sold below acquisition cost — the real, clean loss signal (nrv-cogs<0), not the list-price-noise markdown."""
    return bool(m.get("below_cost"))


def _loss(r: dict) -> float:
    """The margin given away on one item = units sold below cost × amount each is under cost. 0 when not below cost."""
    m = r["movement"]
    return (m.get("sold_window") or 0) * (m.get("below_cost_by") or 0)


def _group_hot(
    records: list, key_fn, code: str, label_key: str, shop_rate: float, min_group: int, min_deviation: float
) -> Surprise | None:
    """The subgroup whose below-cost SHARE deviates furthest ABOVE the shop-wide share — a category or supplier
    running hotter on loss than the shop as a whole. Groups thinner than `min_group` items are ignored (a
    3-item 'category' is noise, not a pattern), and the worst must clear `min_deviation` — a share only barely
    above the norm is NOT a surprise, and padding the digest with it betrays its promise. Returns the single
    genuinely-out-of-norm worst, or None. Pure."""
    groups: dict = {}
    for r in records:
        k = key_fn(r)
        if not k:
            continue
        g = groups.setdefault(k, [0, 0])  # [below_cost_count, total]
        g[1] += 1
        if _below(r["movement"]):
            g[0] += 1
    best = None
    for k, (b, n) in groups.items():
        if n < min_group or b == 0:
            continue
        dev = deviation(b / n, shop_rate)
        if dev >= min_deviation and (best is None or dev > best.magnitude):
            fields = {label_key: k, "pct": round(b / n * 100), "norm": round(shop_rate * 100), "count": b, "of": n}
            best = Surprise(code, dev, fields)
    return best


def sale_surprises(records: list, top: int = 3, min_group: int = 15, min_deviation: float = 1.0) -> list:
    """The sale report's digest — up to `top` findings, each a different LENS on where the shop is bleeding, in
    money-first order: (1) the single biggest below-cost loss, (2) the category running hottest on loss vs the
    shop norm, (3) the supplier likewise. Fixed-slot (one per lens), not cross-ranked, because a currency loss and a
    share-deviation are different scales — each is its own kind of surprise. A group finding must clear
    `min_deviation` (default 1.0 = at least DOUBLE the shop's below-cost rate) to count — otherwise it is dropped,
    so the digest never pads with a barely-above-norm non-surprise. Empty when nothing stands out. Pure over the
    shadow records."""
    below = [r for r in records if _below(r["movement"])]
    surprises: list = []
    if below:
        worst = max(below, key=_loss)
        if _loss(worst) > 0:
            m = worst["movement"]
            surprises.append(
                Surprise(
                    "biggest_bleed",
                    float(_loss(worst)),
                    {
                        "item": worst["item"]["article"],
                        "color": worst["item"]["color"],
                        "units": m.get("sold_window"),
                        "under": m.get("below_cost_by"),
                        "loss": round(_loss(worst)),
                    },
                )
            )
    shop_rate = (len(below) / len(records)) if records else 0.0
    groups = []
    for key_fn, code, label in (
        (lambda r: (r.get("category") or {}).get("cluster"), "category_hot", "category"),
        (lambda r: r.get("supplier"), "supplier_hot", "supplier"),
    ):
        s = _group_hot(records, key_fn, code, label, shop_rate, min_group, min_deviation)
        if s:
            groups.append(s)
    groups.sort(key=lambda s: -s.magnitude)  # strongest deviation first, so a top-N cap keeps the biggest surprise
    surprises.extend(groups)
    return surprises[:top]


def sale_winners(records: list, top: int = 1, min_velocity: float = 5.0, max_cover: float = 21.0) -> list:
    """The POSITIVE side of the sale picture: the standout fast mover(s) about to run dry — selling briskly
    (velocity_30d ≥ min_velocity units) yet with little shelf left (days_of_cover ≤ max_cover). The "this is
    working, reorder before it's gone" signal, so the digest isn't only a list of what's bleeding. Ranked
    most-urgent first (least cover, then fastest). Pure over the shadow records."""
    live = []
    for r in records:
        m = r["movement"]
        vel = m.get("velocity_30d") or 0
        cover = m.get("days_of_cover")
        # 0 ≤ cover ≤ max: selling briskly with little (but real) shelf left. Exclude NEGATIVE cover — that is an
        # oversold / negative-stock artifact, not a clean "reorder before it runs out" (it reads as "-3 days left").
        if vel >= min_velocity and cover is not None and 0 <= cover <= max_cover:
            live.append(r)
    live.sort(key=lambda r: (r["movement"]["days_of_cover"], -(r["movement"].get("velocity_30d") or 0)))
    out = []
    for r in live[:top]:
        m = r["movement"]
        out.append(
            Surprise(
                "top_mover",
                float(m.get("velocity_30d") or 0),
                {
                    "item": r["item"]["article"],
                    "color": r["item"]["color"],
                    "sold": m.get("velocity_30d"),
                    "cover": round(m["days_of_cover"]),
                },
            )
        )
    return out


def _peer(r: dict) -> str | None:
    """The PEER GROUP a hidden-hot / laggard is judged against — the finer SUB-CATEGORY (a niche item is judged
    against its own niche, so an over-performer surfaces regardless of absolute volume — the 'hidden' part),
    falling back to the broad cluster when the sub-category is unadjudicated."""
    c = r.get("category") or {}
    return c.get("sub_category") or c.get("cluster")


def sale_outliers(
    records: list,
    top: int | None = None,
    min_units: int = 3,
    min_stock: int = 40,
    min_group: int = 12,
    min_hot_deviation: float = 2.0,
    min_lag_deviation: float = 0.9,
) -> tuple:
    """The HIDDEN-HOT and LAGGARD surprises — why a data geometry beats a naive top-N. An item's recent SELL
    RATE (`velocity_30d`) is compared to its OWN sub-category's mined norm (the mean rate of a typical selling
    item in the niche), and the signed deviation is the surprise. The bars are SIGNIFICANCE, not arbitrary caps:
    **hidden hot** = selling ≥ `min_hot_deviation` (default 3× = 200% over) its niche on real sales
    (`min_units`), but BELOW the obvious-volume ceiling (the leaders a top-N already shows). **laggard** =
    selling under (1−`min_lag_deviation`) of its niche pace (default <10%) while holding real dead shelf
    (`min_stock`) — ranked by OPPORTUNITY COST (shelf × niche pace), because a laggard's deviation saturates at
    −100% and cannot rank them; the cost of the dead money in a moving niche can. Info-theoretic: the deviation
    is *information* about the store's structure, not a verdict. A peer thinner than `min_group` is not a norm;
    negative rates are returns/correction artifacts, not sales, and are dropped. `top=None` returns EVERY item
    that clears the bar (the count IS the finding). Pure over the shadow records."""
    grp: dict = {}  # peer -> [Σ velocity, n selling items] — the mean rate of a TYPICAL SELLING item in the niche
    for r in records:
        p, m = _peer(r), r["movement"]
        v, u = (m.get("velocity_30d") or 0), (m.get("sold_window") or 0)
        if p and v > 0 and u > 0:  # over SELLERS: dead stock would drag the norm to ~0 (everything looks hot);
            g = grp.setdefault(p, [0.0, 0])  # a simple mean (not demand-weighted) so one volume leader can't
            g[0] += v  # dominate the norm and mask a genuine niche over-performer
            g[1] += 1
    norm = {p: s / n for p, (s, n) in grp.items() if n > 0}
    counts = Counter(p for r in records if (p := _peer(r)))
    # the "obvious" ceiling: the operator already SEES the volume leaders on any top-N list, so a HIDDEN hot must
    # sit below them — the top decile of absolute units is "obvious", excluded from the hidden-hot surprise.
    sold_vals = sorted(u for r in records if (u := (r["movement"].get("sold_window") or 0)) > 0)
    obvious_cap = sold_vals[int(len(sold_vals) * 0.90)] if sold_vals else 0

    hot: list = []
    laggards: list = []
    for r in records:
        p, m = _peer(r), r["movement"]
        v, u = (m.get("velocity_30d") or 0), (m.get("sold_window") or 0)
        stock = (r.get("stock") or {}).get("total") or 0  # shadow stock is {total, by_location}
        if p is None or p not in norm or counts.get(p, 0) < min_group or v < 0 or u < 0:
            continue  # not a real peer group, or a returns/correction artifact
        dev = deviation(v, norm[p])
        fields = {
            "item": r["item"]["article"],
            "color": r["item"]["color"],
            "image": r.get("image"),  # the framed photo the report card carries
            "peer": p,
            "rate": round(v, 1),
            "norm": round(norm[p], 1),
            "units": u,
            "stock": stock,
            "of": counts.get(p, 0),
        }
        # HIDDEN hot: strong over-performance of its niche, on real sales, but NOT an obvious volume leader
        if dev >= min_hot_deviation and min_units <= u <= obvious_cap:
            hot.append(Surprise("hidden_hot", dev, fields))
        elif dev <= -min_lag_deviation and stock >= min_stock:
            laggards.append(Surprise("laggard", -dev, fields))  # near-dead in a moving niche, real shelf sitting
    hot.sort(key=lambda s: -s.magnitude)  # biggest over-performance first
    laggards.sort(key=lambda s: -(s.fields["stock"] * s.fields["norm"]))  # biggest dead-money-in-a-moving-niche first
    # top=None → EVERY item that clears the significance bar (the count is itself the finding); else the top-N
    return (hot, laggards) if top is None else (hot[:top], laggards[:top])
