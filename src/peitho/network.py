"""peitho.network — the node-network machinery: a data-induced, calibrated, role-typed graph.

The generic "styrofoam box". A retailer's store/warehouse graph plugs in as cassette data; the machinery
here is company-agnostic:

- **Node birth / death.** The live node set is INDUCED from the data — a node present in the grid is
  live; a node absent (closed, re-coded, destocked, a frozen legacy location) is dead. So the
  frozen-legacy exclusion needs no separate blocklist: a node that stopped landing simply stops being
  induced. See `induce_nodes`.
- **Role induction, abstaining where the data is silent.** A node's coarse role is read off the sales
  geometry: a node that holds stock but sells ~nothing is a WAREHOUSE source; a node that sells is a
  RETAIL sink. This is a signed-ternary position against a mined zero (`sells_position`), the same
  primitive as every bank — never a statistic, never a learned model. Finer roles that are NOT in the
  sales data — a sale-or-return CONTRACT, the operator's physical TRIAGE presence — are declared by the
  cassette; the geometry ABSTAINS on them rather than fabricating a role from distance.
- **Weight calibration.** Edge cost comes from a measured drive-time matrix when the cassette points at
  one, else a transparent zone-distance placeholder. Calibration is *using measured data*, not fitting.

`active_network()` is the cassette-declared baseline (roster, zones, roles, weight source) — its role
sets are the frozen OUTPUT of running the induction over the landed data, re-derivable whenever the data
changes. `build_network(grid)` returns the live subset for a specific grid and validates the declared
roles against that grid's geometry, surfacing any drift. Routing (min-cost) runs over whatever network
the data + cassette induce, in `peitho.lenses.spatial`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import cassette as _cassette  # config source; it does not import us back (dependency inversion)

ROLES = ("WAREHOUSE", "SELL", "TRIAGE", "SOR", "STORE")


@dataclass(frozen=True)
class NetworkState:
    """A resolved node network. `roles` is the FINE controller model (node -> its role set); the coarse
    RETAIL/WAREHOUSE model used by the inventory watcher is derived from it (a node whose only source
    role is WAREHOUSE is a source; everything else on the roster is a selling node)."""

    nodes: tuple = ()
    zones: dict = field(default_factory=dict)  # node -> zone label
    roles: dict = field(default_factory=dict)  # node -> frozenset[role]
    zone_minutes: dict = field(default_factory=dict)  # (zone_a, zone_b) -> drive minutes (symmetric)
    intra_zone_min: float = 15.0
    same_store_min: float = 0.0
    matrix_path: Path | None = None  # a measured drive-time matrix, if the cassette declares one
    weights_source: str = "placeholder"  # "osrm" | "placeholder"

    def warehouse_nodes(self) -> frozenset:
        """Nodes acting as a warehouse/source (a WAREHOUSE role in the fine model)."""
        return frozenset(n for n, r in self.roles.items() if "WAREHOUSE" in r)

    def retail_nodes(self) -> frozenset:
        """Selling nodes — every roster node that is not purely a warehouse source."""
        wh = self.warehouse_nodes()
        return frozenset(n for n in self.nodes if n not in wh)

    def role_set(self, role: str) -> frozenset:
        """The nodes holding a given fine role (e.g. SELL, SOR, TRIAGE)."""
        return frozenset(n for n, r in self.roles.items() if role in r)


def network_from_cassette(cas=None) -> NetworkState:
    """Build a NetworkState from a cassette's `network.toml`. Zone-minute keys are written "ZONE_A|ZONE_B"
    (TOML has no tuple keys) and split back to tuples here. A missing weight matrix → the placeholder."""
    cas = cas or _cassette.active()
    net = cas.network
    zone_minutes = {}
    for k, v in (net.get("weights", {}).get("zone_minutes") or {}).items():
        a, b = k.split("|")
        zone_minutes[(a, b)] = float(v)
    weights = net.get("weights", {})
    matrix_rel = weights.get("matrix")
    matrix_path = None
    if matrix_rel:
        p = Path(str(matrix_rel)).expanduser()
        matrix_path = p if p.is_absolute() else (cas.data_root / p)
    roles = {n: frozenset(rs) for n, rs in (net.get("roles") or {}).items()}
    return NetworkState(
        nodes=tuple(net.get("nodes") or ()),
        zones=dict(net.get("zones") or {}),
        roles=roles,
        zone_minutes=zone_minutes,
        intra_zone_min=float(weights.get("intra_zone_min", 15)),
        same_store_min=float(weights.get("same_store_min", 0)),
        matrix_path=matrix_path,
        weights_source=str(weights.get("source", "placeholder")),
    )


@lru_cache(maxsize=1)
def active_network() -> NetworkState:
    """The process-shared network for the active cassette. Prefer `cassette.reset()` to swap cassettes
    in-process (it clears this cache too — see the registration below)."""
    return network_from_cassette()


_cassette.register_cache_clearer(active_network.cache_clear)  # reset() clears our cache (dependency inversion)


# --------------------------------------------------------------------------------------------------
# Induction — the data-driven layer. These derive the network FROM a grid, so node birth/death and role
# calibration re-run whenever the data changes; their frozen output is what a cassette's network.toml
# stores. All pure, all signed-ternary geometry (mined zero → signed position), never a statistic.
# --------------------------------------------------------------------------------------------------


def sells_position(node_sales: float, zero: float, floor: float = 0.0) -> int:
    """A node's signed-ternary position on the SELLS axis, against a mined sales-zero. -1 = a source
    (sells at/below the floor — a warehouse that holds stock and moves ~nothing), +1 = a throughput sink
    (sells above the mined typical node), 0 = an ordinary selling node. Pure over floats — the same
    signed-deviation primitive as every bank; there is no statistic and no threshold-fitting here."""
    if node_sales <= floor:
        return -1  # confident exclusion: this node does not sell → a source, not a sink
    return 1 if node_sales > zero else 0


def mine_sales_zero(sales_by_node: dict) -> float:
    """The mined 'typical selling node' — the median sales among nodes that actually sell (a node that
    sells nothing would drag a mean toward zero and make every seller look hot; the median of sellers is
    the honest zero). Pure over a {node: sales} mapping; 0.0 when nothing sells."""
    sellers = sorted(v for v in sales_by_node.values() if v and v > 0)
    if not sellers:
        return 0.0
    mid = len(sellers) // 2
    return float(sellers[mid] if len(sellers) % 2 else (sellers[mid - 1] + sellers[mid]) / 2)


def coarse_role(node_sales: float, zero: float, floor: float = 0.0) -> str:
    """The coarse role of ONE node from its sales geometry: a node selling at/below the floor is a
    WAREHOUSE source (signed-ternary position -1), any node that sells is a RETAIL sink. Pure over floats —
    the single per-node decision `induce_coarse_roles` maps over the network, extracted so it is pinnable."""
    return "WAREHOUSE" if sells_position(node_sales, zero, floor) < 0 else "RETAIL"


def induce_coarse_roles(sales_by_node: dict, floor: float = 0.0) -> dict:
    """The coarse RETAIL/WAREHOUSE role for every node, induced from sales against the mined zero. Reproduces
    a hand-curated coarse model when one exists — the re-runnable form of that mining (node birth/death is
    implicit: a node absent from the data is absent here). I/O-free map over `coarse_role`."""
    zero = mine_sales_zero(sales_by_node)
    return {node: coarse_role(sales or 0.0, zero, floor) for node, sales in sales_by_node.items()}
