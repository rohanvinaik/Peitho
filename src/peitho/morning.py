"""peitho.morning — the "good morning" report-router: the digest-of-digests (#5, pure data geometry).

The operator runs several reports. This one-pager reads each report's OWN headline signal and routes their attention:
which report to open today, and the one-line why. It composes the significance digests the other lenses already
computed — the sale's biggest below-cost bleed, the routing reorder gap the network can't self-cover, dead /
left-unsold suppliers, the store clearing deepest against its peers, and the imputed seasonal event (#4) — into
a single ranked glance: the "shape of the day".

DESCRIPTIVE: it names what deviates and points at the report that carries the detail; it never instructs. Like
the sale digest it is FIXED-SLOT — one line per domain, never cross-ranking incomparable magnitudes (a $ loss
and a supplier count are different scales), only sorting LOUD (needs attention today) ahead of QUIET. No AI, no
stochastic step; each attention threshold is a transparent, tunable knob.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Route:
    """One domain's morning line: the report to open, whether it is LOUD (needs attention today) or QUIET, the
    headline phrase code + its fields, and the magnitude the LOUD/QUIET decision turned on."""

    domain: str
    report: str  # the report's title key (title.*) — what to open for the detail
    band: str  # LOUD / QUIET
    code: str  # the morning phrase key
    magnitude: float
    fields: dict = field(default_factory=dict)


def is_loud(magnitude: float, threshold: float) -> bool:
    """A domain routes the operator's attention today iff its headline signal clears its own attention threshold —
    the single decision the whole router turns on, a signed check against a transparent per-domain knob. Pure
    over two numbers."""
    return magnitude >= threshold


def rank_routes(routes: list) -> list:
    """The morning order: LOUD domains first (open these today), QUIET after — each group KEEPING the given
    money/action-first domain order, never cross-ranking incomparable magnitudes (a $ loss vs a supplier count
    are different scales, exactly as the sale digest uses fixed slots). Pure, stable over a list of Route."""
    return [r for r in routes if r.band == "LOUD"] + [r for r in routes if r.band != "LOUD"]


def _band(magnitude: float, threshold: float) -> str:
    return "LOUD" if is_loud(magnitude, threshold) else "QUIET"


def morning_routes(
    sale_surprises: list,
    routing: dict,
    suppliers: dict,
    clearance: dict,
    seasonal: dict,
    min_reorder: int = 200,
    min_dead: int = 1,
    min_events: int = 1,
) -> list:
    """Compose the five domain summaries into the "good morning" attention router — one Route per domain, LOUD
    ones first. Pure over the already-computed summaries (the lenses did the significance work; this only routes
    attention). Each domain's magnitude vs its threshold decides LOUD vs QUIET; `rank_routes` orders them."""
    routes = []

    # SALE — the biggest below-cost bleed (the money signal); loud whenever one exists
    bleed = next((s for s in sale_surprises if s.get("code") == "biggest_bleed"), None)
    if bleed:
        f = bleed["fields"]
        routes.append(
            Route(
                "sale",
                "title.sale_performance",
                "LOUD",
                "morning.sale",
                float(f.get("loss") or 0),
                {"item": f.get("item"), "color": f.get("color"), "loss": f.get("loss")},
            )
        )
    else:
        routes.append(Route("sale", "title.sale_performance", "QUIET", "morning.sale_quiet", 0.0, {}))

    # STOCK MOVEMENT — the reorder gap the network can't cover from spare
    ru = routing.get("reorder_units") or 0
    routes.append(
        Route(
            "routing",
            "title.stock_movement",
            _band(ru, min_reorder),
            "morning.routing",
            float(ru),
            {"reorders": routing.get("reorders"), "units": ru, "runs": routing.get("runs")},
        )
    )

    # SUPPLIERS — dead + left-unsold
    bands = suppliers.get("bands") or {}
    dead, left = bands.get("DEAD_STOCK", 0), bands.get("LEFT_UNSOLD", 0)
    routes.append(
        Route(
            "suppliers",
            "title.suppliers",
            _band(dead + left, min_dead),
            "morning.suppliers",
            float(dead + left),
            {"dead": dead, "left": left},
        )
    )

    # CLEARANCE — the store clearing above its peers (or quiet if none is)
    cs = clearance.get("clearing_store")
    if cs:
        routes.append(
            Route(
                "clearance",
                "title.clearance",
                "LOUD",
                "morning.clearance",
                float(cs.get("deviation") or 0),
                {
                    "store": cs.get("store"),
                    "depth": round(cs.get("depth") or 0),
                    "norm": round(clearance.get("peer_norm_depth") or 0),
                },
            )
        )
    else:
        routes.append(Route("clearance", "title.clearance", "QUIET", "morning.clearance_quiet", 0.0, {}))

    # SEASON — the imputed end-of-season event (#4)
    ev = seasonal.get("events") or 0
    routes.append(
        Route(
            "season",
            "title.sale_full",
            _band(ev, min_events),
            "morning.season",
            float(ev),
            {"events": ev, "items": seasonal.get("seasonal_items")},
        )
    )

    return rank_routes(routes)
