"""Hand-authored INTENT test for peitho.export — the portable per-SKU record shape."""

from peitho.export import (
    article_style_ids,
    build_item_record,
    build_movement,
    build_sku_record,
    build_wide_item_record,
    canonical_articles,
)
from peitho.ledgers import _customer_pseudonym  # the customer-domain pseudonymizer now lives with its ledger


def test_customer_pseudonym_is_stable_salted_and_prefixed():
    # a hash is opaque to input-synthesis (Detective can't pin it); its CONTRACT is what matters and is hand-pinned:
    node = {"mobile": "5551234567", "name": "X", "created": "2024-01-01", "store": "N8", "codes": ["AH0000000001"]}
    a = _customer_pseudonym(node, "salt1")
    assert a.startswith("c:") and len(a) == 2 + 12  # 'c:' + 12 hex of the salted sha256
    assert _customer_pseudonym(node, "salt1") == a  # STABLE: same node+salt → same id (longitudinally joinable)
    assert _customer_pseudonym(node, "salt2") != a  # SALT-SENSITIVE: the salt actually participates
    # a no-mobile person falls back to name+created+store+codes and is still stable + prefixed
    nm = {"mobile": None, "name": "Y", "created": "2024-02-02", "store": "N3", "codes": ["AC0000000009"]}
    b = _customer_pseudonym(nm, "salt1")
    assert b.startswith("c:") and _customer_pseudonym(nm, "salt1") == b
    assert b != a  # a different person → a different pseudonym


def test_build_movement_uses_correct_fields_not_mrp_noise():
    # nrv=9500 realized, cogs=5000 cost, 3800 of the revenue was sold at a discount; 95 units sold
    m = build_movement(22, 95, 154, 9500.0, 5000.0, 3800.0)
    assert m["velocity_30d"] == 22
    assert m["sold_window"] == 95
    assert m["sell_through_pct"] == 38.2  # 95 / (95+154)
    assert m["days_of_cover"] == 210.0  # 154 / (22/30)
    assert m["sale_price"] == 100  # asp = nrv/sold = 9500/95
    assert m["on_sale_pct"] == 40  # discounted_sale / nrv = 3800/9500 (the DIRECT "on sale" signal)
    assert m["margin_pct"] == 47.4  # REAL margin (nrv-cogs)/nrv = 4500/9500 — NOT the discountAmount noise
    assert m["below_cost"] is False
    assert m["below_cost_by"] is None  # profitable -> not under cost


def test_build_movement_below_cost_and_return_noise():
    # sold below cost: realized 900 < cost 8500 -> below_cost, real margin deeply negative
    m = build_movement(0, 7, 0, 900.0, 8500.0, 900.0)
    assert m["below_cost"] is True
    assert m["margin_pct"] == round((900 - 8500) / 900 * 100, 1)  # ~ -844.4 (kept in substrate, NOT reported)
    assert m["below_cost_by"] == round((8500 - 900) / 7)  # the CLEAN figure: $1086/unit under cost
    assert m["on_sale_pct"] == 100  # all revenue was discounted
    # return noise: aggregate nrv <= 0 -> every price/ratio guards to None
    z = build_movement(0, 1, 0, -10.0, 960.0, 3180.0)
    assert z["sale_price"] is None and z["on_sale_pct"] is None and z["margin_pct"] is None
    assert z["below_cost"] is None


def test_build_wide_item_record_is_stock_plus_movement_in_one():
    cat = {"cluster": "Closed Footwear", "sub_category": "Shoes", "status": "resolved"}
    mv = {"velocity_30d": 3, "margin_pct": 40.0}
    r = build_wide_item_record(
        "A1", "BLK", "img:x", "http://i", cat, {"variety": "DERBY"}, 730, {"40": 5, "41": 0}, {"N8": 5}, mv
    )
    assert list(r.keys())[1] == "style_id"  # identity leads
    assert r["category"]["cluster"] == "Closed Footwear"  # informative category, not raw idiom
    assert r["movement"] is mv  # the sell-dynamics block rides on the same record
    assert r["sizes"]["in_stock"] == ["40"]  # 41 out of stock excluded
    assert r["stock"]["total"] == 5


def test_build_sku_record_schema_and_front_anchored_image():
    # category is now the informative product category (deconvolved, raw preserved), passed through verbatim
    cat = {"cluster": "Closed Footwear", "sub_category": "Shoes", "raw": {"section": "MENS", "subsection": "FORMAL"}}
    r = build_sku_record(
        "A1",
        "BLK",
        "40",
        "http://img",
        cat,
        {"variety": "OXFORD", "brand": "EXAMPLE"},
        730,
        {"N5": 2, "N8": 5},
    )
    assert r["sku"] == {"article": "A1", "color": "BLK", "size": "40"}
    assert list(r.keys())[1] == "image"  # image is FRONT-ANCHORED (right after the identity)
    assert r["image"] == "http://img"
    assert r["category"] is cat  # the informative category rides through untouched
    assert r["category"]["raw"] == {"section": "MENS", "subsection": "FORMAL"}  # raw idiom preserved inside
    assert r["style"]["variety"] == "OXFORD"
    assert r["age_days"] == 730
    assert r["stock"]["total"] == 7  # 2 + 5
    assert r["stock"]["by_location"] == {"N5": 2, "N8": 5}  # sorted by store


def test_build_sku_record_handles_missing_fields():
    r = build_sku_record("A2", "", "", None, {}, {}, None, {})
    assert r["image"] is None
    assert r["category"] == {}  # no taxonomy -> empty category, not a {section:None} idiom stub
    assert r["stock"] == {"total": 0, "by_location": {}}
    assert r["age_days"] is None


def test_build_item_record_rolls_sizes_into_availability():
    # one colorway with its sizes rolled up: sizes become an availability list, not separate rows
    r = build_item_record(
        "A1",
        "BLK",
        "img:3f9a1c2d",
        "http://img",
        {"cluster": "Flats", "sub_category": "Ballerinas", "raw": {"section": "WOMENS", "subsection": "BALLERINAS"}},
        {"variety": "ROUND"},
        730,
        {"38/7": 5, "39/8": 0, "40/9": 3},
        {"N8": 8},
    )
    assert r["item"] == {"article": "A1", "color": "BLK"}
    assert r["category"]["cluster"] == "Flats"  # informative category, raw idiom preserved inside
    assert r["style_id"] == "img:3f9a1c2d"  # colourway link (shared product photo)
    assert list(r.keys())[1] == "style_id"  # identity (item + style_id) leads
    assert list(r.keys())[2] == "image"  # image next, for visual reference
    assert r["sizes"]["in_stock"] == ["38/7", "40/9"]  # 39/8 out of stock is excluded from availability
    assert r["sizes"]["by_size"] == {"38/7": 5, "39/8": 0, "40/9": 3}  # full run kept, sorted
    assert r["stock"]["total"] == 8  # 5 + 0 + 3


def test_canonical_articles_maps_same_photo_cluster_to_one_representative():
    # image dedupe: every member of a same-photo cluster points at the lexicographically-smallest article
    canon = canonical_articles([["NS-721", "NS-721L", "NS-721M"], ["BL-A", "BL-B"]])
    assert canon["NS-721L"] == "NS-721"
    assert canon["NS-721"] == "NS-721"  # the representative maps to itself
    assert canon["BL-B"] == "BL-A"
    assert "SOLO" not in canon  # an article in no cluster is absent (caller falls back to itself)


def test_article_style_ids_share_across_a_common_photo_hash():
    # two articles sharing an image content hash get the SAME style_id (one style, two colourways)
    ids = article_style_ids({"BL-NLSAQ": "3f9a1c2d55", "BL-NLSNBL": "3f9a1c2d55", "OTHER": "aabbccdd99"})
    assert ids["BL-NLSAQ"] == ids["BL-NLSNBL"] == "img:3f9a1c2d"  # first 8 hex, shared
    assert ids["OTHER"] == "img:aabbccdd"
