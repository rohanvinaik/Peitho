"""Hand-authored INTENT test for peitho.query.flow.min_cost_flow — the exact transportation solver
(CONTROL_ARCHITECTURE.md §6). Beyond the Detective characterization, this pins OPTIMALITY: the solver's
flow matches a brute-force optimum (max-flow, then min-cost) on a seeded battery of small instances, and on
hand-crafted cases including the competition case the greedy over-allocates.
"""

import itertools
import random
from collections import defaultdict

from peitho.query.flow import min_cost_flow


def _brute(sup, dem, cost):
    """Brute-force optimum over all integer arc allocations: (max_flow, -min_cost)."""
    arcs = list(cost)
    caps = [min(sup[s], dem[d]) for (s, d) in arcs]
    best = None
    for x in itertools.product(*[range(c + 1) for c in caps]):
        os_, id_, c, f = defaultdict(int), defaultdict(int), 0, 0
        for i, (s, d) in enumerate(arcs):
            os_[s] += x[i]
            id_[d] += x[i]
            c += x[i] * cost[(s, d)]
            f += x[i]
        if any(os_[s] > sup[s] for s in os_) or any(id_[d] > dem[d] for d in id_):
            continue
        cand = (f, -c)
        if best is None or cand > best:
            best = cand
    return best


def _solved(sup, dem, cost):
    fl = min_cost_flow(sup, dem, cost)
    return (sum(fl.values()), -sum(q * cost[a] for a, q in fl.items()))


def test_competition_respects_source_capacity():
    # two short stores, one spare source that can't cover both -> the greedy over-allocates; the flow caps it.
    flow = min_cost_flow({"S": 3}, {"A": 2, "B": 2}, {("S", "A"): 1, ("S", "B"): 1})
    assert sum(flow.values()) == 3  # only 3 spare -> never ships 4 (the over-allocation bug the flow fixes)


def test_prefers_cheaper_source():
    flow = min_cost_flow({"cheap": 2, "dear": 5}, {"X": 3}, {("cheap", "X"): 1, ("dear", "X"): 9})
    assert flow[("cheap", "X")] == 2 and flow[("dear", "X")] == 1  # fill from cheap first, dear for the rest


def test_unmet_when_supply_short():
    flow = min_cost_flow({"S": 1}, {"X": 5}, {("S", "X"): 2})
    assert flow == {("S", "X"): 1}  # 1 shipped; the caller reads 4 unmet -> a reorder


def test_no_admissible_arc_ships_nothing():
    assert min_cost_flow({"S": 3}, {"X": 2}, {}) == {}  # inadmissible pair carries no flow


def test_matches_brute_force_optimum_on_random_battery():
    random.seed(20260818)
    for _ in range(1500):
        ns, nd = random.randint(1, 3), random.randint(1, 3)
        sup = {f"s{i}": random.randint(1, 5) for i in range(ns)}
        dem = {f"d{j}": random.randint(1, 5) for j in range(nd)}
        cost = {
            (f"s{i}", f"d{j}"): random.randint(1, 9) for i in range(ns) for j in range(nd) if random.random() < 0.75
        }
        assert _solved(sup, dem, cost) == _brute(sup, dem, cost)


def test_ignores_zero_entries_and_dangling_arcs():
    # defensive guards: a 0-unit supply/demand and an arc whose endpoints aren't live carry no flow.
    flow = min_cost_flow({"a": 0, "b": 3}, {"x": 0, "y": 2}, {("a", "x"): 1, ("b", "y"): 1, ("z", "y"): 5})
    assert flow == {("b", "y"): 2}  # only the live b->y pair moves
