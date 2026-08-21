"""Hand-authored INTENT tests for peitho.lenses.spatial.

zone_of (store→zone, from postal codes) and edge_minutes (the placeholder zone distances) are domain
FACTS Detective correctly declines to invent; this file asserts them. all_pairs_min_cost and rank_sources
are Detective-pinned; the end-to-end test here pins the routing intent (nearest source ranks first).
"""

from peitho.lenses.spatial import (
    NODES,
    all_pairs_min_cost,
    edge_minutes,
    load_real_cost_matrix,
    rank_sources,
    zone_of,
)


def _placeholder_matrix():
    # build from edge_minutes directly, so tests never depend on the gitignored real OSRM file
    return {(a, b): edge_minutes(a, b) for a in NODES for b in NODES}


def test_zone_of_from_postal_codes():
    # the active cassette's network is the bundled example (WH,N1→ZONE_A; N2,N3→ZONE_B; N4→ZONE_C)
    assert zone_of("N1") == "ZONE_A"
    assert zone_of("WH") == "ZONE_A"  # same zone as N1
    assert zone_of("N2") == "ZONE_B"
    assert zone_of("N3") == "ZONE_B"
    assert zone_of("N4") == "ZONE_C"
    assert zone_of("nonsense") == "UNKNOWN"


def test_edge_minutes_placeholder_geography():
    assert edge_minutes("N1", "N1") == 0.0  # same store
    assert edge_minutes("N2", "N3") == 15.0  # same zone (two ZONE_B nodes)
    assert edge_minutes("WH", "N1") == 15.0  # same zone — zone-level in the placeholder
    assert edge_minutes("N1", "N2") == 40.0  # ZONE_A ↔ ZONE_B
    assert edge_minutes("N2", "N1") == 40.0  # symmetric (placeholder)
    assert edge_minutes("N1", "N4") == 70.0  # ZONE_A ↔ ZONE_C


def test_rank_sources_prefers_the_nearest():
    mc = all_pairs_min_cost(list(NODES), _placeholder_matrix())
    ranked = rank_sources("N1", ["WH", "N2", "N4"], mc)
    assert [s for s, _ in ranked] == ["WH", "N2", "N4"]  # same-zone → ZONE_B → ZONE_C
    assert ranked[0] == ("WH", 15.0)  # placeholder value (real OSRM differs)


def test_load_real_cost_matrix_absent_is_none():
    # when the OSRM matrix file is absent, loader returns None and cost_matrix falls back to placeholder
    assert load_real_cost_matrix("/no/such/cost_matrix.json") is None
