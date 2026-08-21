"""peitho.lenses.spatial — the SPATIAL backbone (the Sisyphean routing graph).

The store/warehouse nodes and the cost-weighted edges between them. Routing = min-cost path
(all-pairs shortest path over the small graph), so a route can go *through a hub* — real travel
time is NOT metric in geographic distance, so the cheapest way from A to C may pass through B.
`rank_sources` orders surplus origins by real travel cost to a shortage store — turning the inventory
watcher's flat "← nearest nodes" into "← cheapest-to-move-from first".

⚠️ COST MATRIX PROVENANCE — the edge weights are a TRANSPARENT PLACEHOLDER, not calibrated travel
times. They are rough business-hours drive-minutes derived from the stores' geographic zones
(STORE_ZONE, from the locations file). Replace with a routing-API matrix (OSRM free, or Google
Distance Matrix with traffic). The graph STRUCTURE and routing below are independent of the values;
only the numbers get better. Until then, treat absolute costs as ordinal, not exact.
"""

from __future__ import annotations

import json
import os

from peitho import network as _network

# The node network is DATA — it plugs in via the active cassette (peitho.network), not a hardcoded list.
# Nodes, zones, zone-distances and the measured-matrix path all come from the cassette's network.toml;
# the graph machinery below (edge_minutes, cost_matrix, all_pairs_min_cost, rank_sources) is agnostic to
# which network is loaded. See peitho.network for node birth/death, role induction and weight calibration.
_NS = _network.active_network()
NODES = _NS.nodes  # the roster; the LIVE subset (birth/death) is induced per-grid in peitho.network
STORE_ZONE = _NS.zones  # node -> geographic zone
_ZONE_MIN = _NS.zone_minutes  # (zone_a, zone_b) -> placeholder drive-minutes (symmetric)
INTRA_ZONE_MIN = _NS.intra_zone_min  # within a zone (e.g. two malls in one city)
SAME_STORE_MIN = _NS.same_store_min
# A measured (e.g. OSRM) drive-time matrix when the cassette declares one, else "" → the placeholder.
_COST_FILE = str(_NS.matrix_path) if _NS.matrix_path else ""


def zone_of(store: str) -> str:
    """A store's geographic zone (domain fact from its location). Total over any string."""
    return STORE_ZONE.get(store, "UNKNOWN")


def edge_minutes(a: str, b: str) -> float:
    """Placeholder drive-minutes between two stores, from their zones. Symmetric; same store → 0,
    same zone → INTRA_ZONE_MIN. Pure over two store codes."""
    if a == b:
        return float(SAME_STORE_MIN)
    za, zb = zone_of(a), zone_of(b)
    if za == zb:
        return float(INTRA_ZONE_MIN)
    return float(_ZONE_MIN.get((za, zb)) or _ZONE_MIN.get((zb, za)) or INTRA_ZONE_MIN)


def load_real_cost_matrix(path: str = _COST_FILE) -> dict | None:
    """Load the OSRM-sourced drive-time matrix {(a,b): minutes} if it exists, else None. I/O only."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        m = json.load(f).get("matrix", {})
    return {tuple(k.split("|")): float(v) for k, v in m.items()}


def cost_matrix(nodes: tuple = NODES) -> dict:
    """The node×node cost matrix {(a,b): minutes}. Prefers the real OSRM matrix when present
    (asymmetric, traffic-free drive-times); falls back to the placeholder zone distances.

    Same-zone geocode collision guard: OSRM gives 0 min between two DISTINCT stores that share an exact
    location (two co-located stores in one area). A printed '0 min' for a real move reads as 'no move needed', so for
    distinct stores the OSRM value is 0 we fall back to the placeholder zone-distance (its domain knowledge —
    e.g. two co-located stores ≈15 min), keeping real OSRM everywhere it is meaningful."""
    real = load_real_cost_matrix()
    if not real:
        return {(a, b): edge_minutes(a, b) for a in nodes for b in nodes}
    out = {}
    for a in nodes:
        for b in nodes:
            if a == b:
                out[(a, b)] = 0.0
                continue
            r = real.get((a, b))
            out[(a, b)] = r if (r and r > 0) else edge_minutes(a, b)  # never a misleading 0 between distinct stores
    return out


def all_pairs_min_cost(nodes: list, edges: dict) -> dict:
    """Floyd–Warshall min-cost between every ordered pair, so a route may pass through a hub.
    `edges[(a,b)]` is the direct cost; missing pairs are unreachable (inf). Pure over list + dict."""
    INF = float("inf")
    dist = {(a, b): (0.0 if a == b else edges.get((a, b), INF)) for a in nodes for b in nodes}
    for k in nodes:
        for i in nodes:
            dik = dist[(i, k)]
            if dik == INF:
                continue
            for j in nodes:
                alt = dik + dist[(k, j)]
                if alt < dist[(i, j)]:
                    dist[(i, j)] = alt
    return dist


def rank_sources(dest: str, sources: list, min_cost: dict) -> list:
    """Order surplus source stores by min travel cost to `dest` (cheapest first), ties broken by
    source name for determinism. Returns [(source, cost), ...]. Pure over a list + dict."""
    scored = [(s, min_cost.get((s, dest), float("inf"))) for s in sources]
    scored.sort(key=lambda t: (t[1], t[0]))
    return scored


def demo() -> None:
    nodes = list(NODES)
    mc = all_pairs_min_cost(nodes, cost_matrix())
    for target in nodes[:2]:  # illustrate min-cost sourcing to the first couple of nodes in the active network
        print(f"Min-cost (drive-min) from each source to a {target} ({zone_of(target)}) shortage:")
        for s, c in rank_sources(target, [n for n in nodes if n != target], mc):
            print(f"  {s} ({zone_of(s):12}) → {target} : {c:.0f} min")
        print()


if __name__ == "__main__":
    demo()
