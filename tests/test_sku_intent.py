"""Hand-authored INTENT tests for peitho.sku — the retailer-SKU wormhole + photo-hash dedupe.

Pins the agreed decode rules (sku_code = {FY}{p|P}{seq}) and the byte-hash clustering, paired with
Detective's synth suites.
"""

from peitho.sku import age_years, cluster_by_hash, parse_sku


def test_parse_sku_wormhole_decode():
    assert parse_sku("26p500") == (26, 500)  # FY2026, registration #500
    assert parse_sku("23P1") == (23, 1)  # uppercase P, FY2023
    assert parse_sku("25p10") == (25, 10)
    assert parse_sku("XX-AB12345N") == (None, None)  # manufacturer article code, NOT the wormhole
    assert parse_sku("") == (None, None)
    assert parse_sku("26500") == (None, None)  # no p/P separator


def test_age_years_from_registration_fy():
    assert age_years(23, 26) == 3  # a 23p item in FY26 = 3-year-old (long-lived clearance)
    assert age_years(26, 26) == 0  # registered this year
    assert age_years(None, 26) is None  # undecoded -> no age


def test_cluster_by_hash_groups_shared_content():
    # items sharing a content hash cluster together; singletons drop; largest first
    clusters = cluster_by_hash({"a": "h1", "b": "h1", "c": "h1", "d": "h2", "e": "h2", "f": "h3"})
    assert clusters == [["a", "b", "c"], ["d", "e"]]  # h3 singleton excluded, sorted by size
    assert cluster_by_hash({}) == []
    assert cluster_by_hash({"x": "h9"}) == []  # a lone item is not a cluster
