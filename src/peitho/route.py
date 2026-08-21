"""peitho.route — the routing DECISION: turn detected shortages into a concrete transfer PLAN.

Composes the two lenses — inventory (where's short / where's spare) and spatial (travel cost) — into the
actual math: how many units to move, from which node, batched into runs. Pure data geometry; no AI, no
stochastic step; every number traces to the authoritative pull.

The elegance (and the "don't deplete a seller" rule, built in — this is #4): ONE integer target per node,
    target = round(velocity × target_cover_days)
makes every node for a given variant either SHORT (stock < target → a deficit) or SPARE (stock > target →
give-away-able). A deficit pulls from spare, cheapest-first. A source only ever gives its SPARE — the stock
ABOVE its own target — so no node is taken below its own need. A pure source (a warehouse/HO, velocity 0)
has target 0, so all its stock is spare. Detection, sourcing, and the depletion guard are one rule.

`target_cover_days` is the REORDER HORIZON — days of cover to hold. It is the one knob that wants a real
lead-time; until then it is an explicit parameter, never a hidden default.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .grid import Grid
from .lenses import inventory, spatial
from .query import edges
from .query.flow import min_cost_flow

# The edge kinds that FILL a live deficit (CONTROL_ARCHITECTURE.md §6): a warehouse reaches any node
# (WH_OUT / TOPUP); a store or SoR reaches only a throughput SELL node (TO_SELL). A satellite is thus
# restockable from the warehouse only, and store→store is admissible solely toward a SELL node — the
# operator's R3/R3-B1 policy, applied here as the transportation graph's arc set.
_FILL_KINDS = frozenset({edges.WH_OUT, edges.TOPUP, edges.TO_SELL})


COVER_DAYS_DEFAULT = 14  # calibrated 2026-08-18 from the landed grid: the fast movers hold ~2-3wk of cover,
# and the >=1 coverage floor governs the ultra-slow ~97% of the variant×store core (velocity×H rounds to 0
# there). 30d was pre-positioning a month for the rare fast mover; 14d is the lean end the mover data supports.


def target_stock(velocity: float, target_cover_days: float) -> int:
    """The integer reorder point: units to hold = round(velocity × horizon). A pure source (velocity 0)
    holds 0 → all its stock is spare. Pure over two numbers."""
    return round(velocity * target_cover_days)


def deficit_units(stock: int, target: int) -> int:
    """Units short of the target (0 if at/above it). Pure."""
    return max(0, target - stock)


def spare_units(stock: int, target: int) -> int:
    """Units above the target — give-away-able without dropping below own need. Pure."""
    return max(0, stock - target)


def coverage_target(velocity: float, target_cover_days: float, selling: bool) -> int:
    """The coverage target for one (variant×store) cell (CONTROL_ARCHITECTURE §6; calibrated 2026-08-18).

    A node that is *selling* this SKU (recent demand) holds **at least 1** — the "≥1 of each demanded SKU"
    coverage floor, the load-bearing law: at variant×store granularity ~97% of the selling core is ultra-slow,
    so `round(velocity × horizon)` rounds to 0 and, without the floor, a demanded SKU that sells out gets no
    replenishment at all. A node *not* selling this SKU holds only the raw velocity-based level (0 if it never
    sells it), so its stock is fully available to flood elsewhere — the warehouse and slack stores give freely.
    Pure over two numbers + a bool.
    """
    base = target_stock(velocity, target_cover_days)
    return max(1, base) if selling else base


def reorder_priority(unmet_units: int, momentum: float) -> float:
    """Manufacturer-order priority for a variant the network CANNOT cover from internal spare (the reachable-
    vs-naive differential — a reorder). Rank by the lost-sales RATE it represents: unmet units × recent demand
    momentum (units/day). High unmet of a fast mover orders first; a lone straggler of a slow item waits.
    Pure over an int + a float — the clean upstream signal, distinct from what routing can already solve."""
    return round(unmet_units * momentum, 4)


MFR_KEEP = "KEEP"  # a manufacturer gap worth ordering (systemic across stores, or a fast mover)
MFR_DROP_ONEOFF = "DROP_ONEOFF"  # a single slow item out at one store — the one-off noise tail (~81% of gaps)
MFR_MIN_MOMENTUM = 0.05  # sells/day floor for a SINGLE-store gap to be worth an order (matches routing significance)
MFR_MIN_STORES = 2  # short at ≥ this many stores ⇒ a SYSTEMIC gap, kept regardless of momentum


def manufacturer_significant(n_stores: int, momentum: float, min_stores: int, min_momentum: float) -> str:
    """Is a manufacturer gap worth an order, or one-off noise? KEEP if SYSTEMIC (short at ≥ min_stores — a
    network-wide pattern, not chance) OR a FAST MOVER (momentum ≥ min_momentum, worth ordering even at one
    store); else DROP_ONEOFF (a lone slow item at a single store — the long tail). Deviation from the one-off
    baseline, so a comprehensive list can cover every supplier above the floor without the noise. Pure."""
    if n_stores >= min_stores:
        return MFR_KEEP
    if momentum >= min_momentum:
        return MFR_KEEP
    return MFR_DROP_ONEOFF


# The per-SUPPLIER basket floor (above the per-variant manufacturer_significant gate). A manufacturer order
# carries fixed overhead — the call, the minimum order quantity, the freight — so a lone significant item does
# not justify placing one. Rohan's ruling 2026-08-20 ("at least a few items"); tunable.
MFR_MIN_SUPPLIER_ITEMS = 3
SUPPLIER_ORDER = "SUPPLIER_ORDER"  # enough significant items to justify placing the supplier order now
SUPPLIER_HOLD = "SUPPLIER_HOLD"  # a real gap, but the basket is too thin to be worth a call yet — hold


def supplier_worth_ordering(n_items: int, min_items: int = MFR_MIN_SUPPLIER_ITEMS) -> str:
    """Is a SUPPLIER's basket of significant gaps worth placing an order, or too thin to bother? Because a
    manufacturer order carries fixed overhead (call + minimum order quantity + freight), a lone significant
    item does not justify one: `SUPPLIER_ORDER` iff the supplier has ≥ `min_items` significant items, else
    `SUPPLIER_HOLD` — a real gap held until the basket fills or it turns systemic. Pure over two ints; the
    per-supplier floor that sits above the per-variant `manufacturer_significant` gate."""
    return SUPPLIER_ORDER if n_items >= min_items else SUPPLIER_HOLD


def allocate(need: int, sources: list) -> tuple:
    """Greedily fill `need` from cost-sorted sources [(node, spare, cost)], cheapest first.
    Returns (plan, unmet): plan = [(node, qty), ...]; unmet > 0 means a supplier order is needed for
    the remainder. Pure over an int + a list."""
    plan = []
    for node, spare, _cost in sources:
        take = min(need, spare)  # 0 once need is met — the guard below skips it
        if take > 0:
            plan.append((node, take))
            need -= take
    return plan, need


@dataclass
class Transfer:
    variant: tuple  # (article, color, size)
    dest: str  # short store
    source: str  # where it ships from
    qty: int  # units to move
    cost: float


@dataclass
class Reorder:
    variant: tuple  # (article, color, size)
    store: str  # the short store
    qty: int  # units the network could NOT cover from spare → the supplier-reorder signal  # drive-minutes source→dest


@dataclass
class Batch:
    source: str
    dest: str
    cost: float  # drive-minutes for the run
    units: int  # total units across all variants in this run
    transfers: list  # [Transfer]


def _default_min_cost() -> dict:
    return spatial.all_pairs_min_cost(list(spatial.NODES), spatial.cost_matrix())


def plan_transfers(
    grid: Grid,
    target_cover_days: float,
    min_cost: dict | None = None,
    window_days: int = inventory.WINDOW_DAYS,
) -> tuple:
    """For every retail cell short of its reorder point with recent demand, allocate the deficit from the
    cheapest nodes that hold SPARE of that variant. Returns (transfers, reorders): the internal moves AND the
    per-cell UNMET deficit the network can't cover from spare — the supplier-reorder signal (elimination one
    level up, THEORY.md). `target_cover_days` = reorder horizon.

    NOTE: this greedy per-cell allocation is the documented local MVP; the LIVE pass is
    `plan_transfers_global` — an exact min-cost flow that finds the globally optimal assignment and applies
    the edge-admissibility policy (CONTROL_ARCHITECTURE.md §6). This greedy fills short cells in grid order
    from a shared per-variant spare pool: feasible (a source is never over-committed) but order-dependent,
    not cost-optimal.
    """
    if min_cost is None:
        min_cost = _default_min_cost()
    coarse = inventory.coarse_roles(grid)  # grid-induced role map, once per grid
    out = []
    reorders = []
    for variant, cells in grid.items():
        # A source's spare is a FINITE pool shared across every short sink of this variant: once one store
        # draws from it, only the remainder is available to the next. The old code recomputed spare per-sink
        # from o.stock, so it offered the same units to every competing sink — a 5-spare node could be told
        # to ship 10, and the deficit covered twice on paper never surfaced as a reorder.
        spare_pool = {
            s: spare_units(
                o.stock,
                target_stock(inventory.velocity(o.sale_qty, window_days), target_cover_days),
            )
            for s, o in cells.items()
        }
        for store, c in cells.items():
            if inventory.node_role(store, coarse) != "RETAIL" or c.recent_sales <= 0:
                continue
            tgt = target_stock(inventory.velocity(c.sale_qty, window_days), target_cover_days)
            need = deficit_units(c.stock, tgt)
            if need <= 0:
                continue
            sources = [
                (s, spare_pool[s], min_cost.get((s, store), float("inf")))
                for s in cells
                if s != store and spare_pool[s] > 0
            ]
            sources.sort(key=lambda t: (t[2], -t[1], t[0]))
            plan, unmet = allocate(need, sources)
            for node, qty in plan:
                out.append(Transfer(variant, store, node, qty, min_cost.get((node, store), float("inf"))))
                spare_pool[node] -= qty  # consume the shared pool → no double-allocation across sinks
            if unmet > 0:  # no internal spare left → reorder from the supplier
                reorders.append(Reorder(variant, store, unmet))
    return out, reorders


def plan_transfers_global(  # pylint: disable=too-many-branches
    # ^ min-cost-flow orchestration per variant: classify supply/demand, build admissible arcs, route, emit
    #   the unmet-demand reorder signal — the branches are the essential stages, not incidental complexity.
    grid: Grid,
    target_cover_days: float,
    min_cost: dict | None = None,
    window_days: int = inventory.WINDOW_DAYS,
    floor_units: int = 0,
) -> tuple:
    """The GLOBALLY-OPTIMAL routing pass (CONTROL_ARCHITECTURE.md §6): for each variant, solve the
    transportation problem — ship SPARE to fill DEFICITS at least total travel cost — under the `edges`
    admissibility policy, via an exact min-cost flow. Fixes the greedy `plan_transfers`'s source
    over-allocation (a source's spare is a hard capacity here) and applies the operator's source-type rules
    (satellites restock from the warehouse only; store spare flows only toward a SELL node). Returns
    (transfers, reorders) — same shape as the greedy. `target_cover_days` = reorder horizon.

    `floor_units` is the coverage FLOOR — the TWO-TIER fill. Tier 1 gives every demanded store its floor
    (min(deficit, floor_units)) FIRST, so the scarce spare spreads across stores before the near hubs are
    topped up; because a store's gap count IS its share of demand, spreading the floor makes the allocation
    gap-proportional rather than proximity-greedy (pure min-cost starves distant stores to reorders). Tier 2
    min-costs the remaining spare into the deeper deficits — pure efficiency. `floor_units=0` = single-pass
    legacy behaviour. The floor is a bootstrap: as stock distributes over days the deficits shrink and Tier 2
    (efficiency) dominates → steady state.
    """
    if min_cost is None:
        min_cost = _default_min_cost()
    out: list = []
    reorders: list = []
    for variant, cells in grid.items():
        supplies: dict = {}
        demands: dict = {}
        for store, c in cells.items():
            # size the reserve by recency-weighted demand (sales-age spectrum), so fresh movers hold coverage
            # and faders round toward the floor — the diluted window average over-reserves stale stock.
            vel = inventory.recent_velocity(c.sls_age, window_days=window_days)
            tgt = coverage_target(vel, target_cover_days, c.recent_sales > 0)
            spare = spare_units(c.stock, tgt)
            if spare > 0:
                supplies[store] = spare
            elif store not in edges.WAREHOUSE and c.recent_sales > 0:
                need = deficit_units(c.stock, tgt)
                if need > 0:
                    demands[store] = need
        if not demands:
            continue
        # admissible arcs only (the operator's R3 policy), and only those with a real travel cost
        arc_cost: dict = {}
        for s in supplies:
            for d in demands:
                if edges.edge_kind(s, d) in _FILL_KINDS:
                    w = min_cost.get((s, d), float("inf"))
                    if w != float("inf"):
                        arc_cost[(s, d)] = w
        # TWO-TIER: tier 1 = the coverage floor (spread ≥`floor_units` to every gap), tier 2 = surplus by
        # min-cost. floor_units=0 collapses to one pass (legacy). Each tier is a min-cost flow over the spare
        # still REMAINING after the previous tier — so the floor is filled before any store is topped past it.
        if floor_units > 0:
            tier_demands = [
                {d: min(need, floor_units) for d, need in demands.items()},  # tier 1: the floor
                {d: need - min(need, floor_units) for d, need in demands.items()},  # tier 2: surplus
            ]
        else:
            tier_demands = [dict(demands)]
        received: dict = defaultdict(int)
        remaining = dict(supplies)
        for tier in tier_demands:
            tier = {d: n for d, n in tier.items() if n > 0}
            ac = {(s, d): c for (s, d), c in arc_cost.items() if remaining.get(s, 0) > 0 and d in tier}
            if not tier or not ac:
                continue
            for (s, d), qty in min_cost_flow(remaining, tier, ac).items():
                out.append(Transfer(variant, d, s, qty, min_cost.get((s, d), float("inf"))))
                received[d] += qty
                remaining[s] -= qty
        for d, need in demands.items():
            unmet = need - received[d]
            if unmet > 0:  # no admissible spare left → the supplier-reorder signal
                reorders.append(Reorder(variant, d, unmet))
    return out, reorders


def batch_transfers(transfers: list) -> list:
    """Group transfers into (source→dest) runs — one trip, many variants — cheapest runs first."""
    by: dict = defaultdict(list)
    for t in transfers:
        by[(t.source, t.dest)].append(t)
    batches = [Batch(s, d, ts[0].cost, sum(t.qty for t in ts), ts) for (s, d), ts in by.items()]
    batches.sort(key=lambda b: (b.cost, -b.units))
    return batches


def report(target_cover_days: float = 30.0, top: int = 15) -> None:
    grid = inventory.load_grid()
    transfers, reorders = plan_transfers_global(grid, target_cover_days)
    batches = batch_transfers(transfers)
    units = sum(t.qty for t in transfers)
    print(f"Reorder horizon (target_cover_days) = {target_cover_days:g}  [the lead-time knob]")
    print(f"Transfer plan: {len(transfers)} moves, {units} units, {len(batches)} store→store runs.")
    reorder_units = sum(r.qty for r in reorders)
    print(f"Supplier reorders: {len(reorders)} cells, {reorder_units} units the network can't cover from spare.\n")
    print(f"Top {top} runs (cheapest first):")
    for b in batches[:top]:
        variants = len(b.transfers)
        print(f"  {b.source}→{b.dest}  {b.cost:.0f}m  {b.units:>3} units / {variants:>3} variants")


if __name__ == "__main__":
    report()
