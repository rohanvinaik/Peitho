"""peitho.query.flow — an exact min-cost transportation solver (CONTROL_ARCHITECTURE.md §6).

The routing controller ships SPARE from source nodes to fill DEFICITS at sink nodes, over the admissible
edges (`query.edges`), at least total travel cost. That is the classical **transportation problem** — a
bipartite min-cost flow. This module solves it *exactly and optimally* by successive shortest paths (SSP)
with a Bellman-Ford (SPFA) shortest-path on the residual graph — the same negative-weight-capable traversal
`GEOMETRY.md §3` chose, here doing real work.

Why exact, not greedy: the greedy per-cell allocation never decrements a source's spare across competing
sinks, so it over-commits a source (measured: 362 (variant,source) pairs / 552 units over-allocated). A
true min-cost flow respects source capacities globally and is provably optimal. The transportation LP is
totally unimodular, so the optimum is integral — integer unit flows fall out with no rounding.

Zero dependencies, pure Python, deterministic — no AI, no library. Instances here are tiny (a handful of
nodes), so SSP is instant; correctness is pinned by Detective AND checked against a brute-force optimum in
the tests.
"""

from __future__ import annotations

from collections import defaultdict, deque


def min_cost_flow(supplies: dict, demands: dict, arc_cost: dict) -> dict:  # pylint: disable=too-many-branches,too-many-statements
    # ^ exact successive-shortest-paths min-cost-flow solver — irreducible essential complexity (Bellman-Ford
    #   relaxation + augmenting-path trace + residual update are one algorithm); Detective-verified optimal.
    """Optimal min-cost transportation of spare → deficit. Pure over three dicts.

    `supplies` = {node: units available}; `demands` = {node: units needed}; `arc_cost` = {(src, dst): cost}
    for the ADMISSIBLE arcs only (an arc absent from this map cannot carry flow). Returns {(src, dst): qty}
    — an integer min-cost flow. Unmet demand is `demands[d]` minus the flow the caller sums into `d`
    (there may be too little admissible supply); this function only reports the flows it sends.
    """
    # Residual graph as a parallel edge list; forward edge at even index, its reverse at the odd sibling.
    idx: dict = {}

    def nid(x) -> int:
        if x not in idx:
            idx[x] = len(idx)
        return idx[x]

    source_node, sink_node = nid("__S"), nid("__T")
    graph: dict = defaultdict(list)  # node -> [edge indices]
    edges: list = []  # each: [to, residual_cap, cost]

    def add_edge(u: int, v: int, cap: int, cost: int) -> None:
        graph[u].append(len(edges))
        edges.append([v, cap, cost])
        graph[v].append(len(edges))
        edges.append([u, 0, -cost])  # reverse: 0 cap, negated cost

    for s, sup in supplies.items():
        if sup > 0:
            add_edge(source_node, nid(("s", s)), sup, 0)
    for d, dem in demands.items():
        if dem > 0:
            add_edge(nid(("d", d)), sink_node, dem, 0)
    arc_edge: dict = {}  # (src,dst) -> forward edge index, for reading the flow back out
    for (s, d), w in arc_cost.items():
        if supplies.get(s, 0) > 0 and demands.get(d, 0) > 0:
            arc_edge[(s, d)] = len(edges)
            add_edge(nid(("s", s)), nid(("d", d)), min(supplies[s], demands[d]), w)

    n = len(idx)
    while True:  # successive shortest (min-cost) augmenting paths
        dist: list = [None] * n
        dist[source_node] = 0
        from_edge: list = [-1] * n
        in_queue = [False] * n
        q: deque = deque([source_node])
        in_queue[source_node] = True
        while q:  # SPFA (Bellman-Ford with a queue) — residual reverse edges carry negative cost
            u = q.popleft()
            in_queue[u] = False
            du = dist[u]
            for ei in graph[u]:
                to, cap, cost = edges[ei]
                if cap > 0 and (dist[to] is None or du + cost < dist[to]):
                    dist[to] = du + cost
                    from_edge[to] = ei
                    if not in_queue[to]:
                        q.append(to)
                        in_queue[to] = True
        if dist[sink_node] is None:
            break  # no augmenting path left -> optimal
        # bottleneck along the found path, then augment
        bottleneck = None
        v = sink_node
        while v != source_node:
            ei = from_edge[v]
            cap = edges[ei][1]
            bottleneck = cap if bottleneck is None else min(bottleneck, cap)
            v = edges[ei ^ 1][0]  # walk to the forward edge's tail via its reverse sibling
        v = sink_node
        while v != source_node:
            ei = from_edge[v]
            edges[ei][1] -= bottleneck
            edges[ei ^ 1][1] += bottleneck
            v = edges[ei ^ 1][0]

    out: dict = {}
    for (s, d), ei in arc_edge.items():
        used = min(supplies[s], demands[d]) - edges[ei][1]  # original cap − residual = flow sent
        if used > 0:
            out[(s, d)] = used
    return out
