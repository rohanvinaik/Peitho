"""Hand-authored INTENT test for peitho.product — the raw-idiom -> informative-category deconvolution.

Pins the AGREED behaviour of the MACHINERY, over an EXPLICIT small taxonomy (so the test is independent
of whichever cassette is active): the category is recovered across BOTH lenses (+ article-code prefix),
gender/age extract to their own fields, raw is preserved, spelling is canonicalised, and an unknown token
passes through flagged (never guessed).
"""

from peitho.product import Taxonomy, extract_gender_age, resolve_token, translate_category, translate_taxonomy

# A minimal explicit vocabulary — enough to exercise every branch, tied to no company.
TAXO = Taxonomy(
    clusters=("Footwear", "Bags", "Care", "Apparel"),
    relation={
        "WALLET": ("Bags", "Wallet"),
        "SANDALS": ("Footwear", "Sandals"),
        "SOCKS/POLISH": ("Care", "Socks & Polish"),
        "SHIRT": ("Apparel", "Shirt"),
        "BALLERINAS": ("Footwear", "Ballet Flats"),
    },
    gender={"MENS": "M", "WOMENS": "F"},
    age={"GIRLS": "kids", "KIDS": "kids"},
    placeholder=frozenset({"BLANK", "COLOR", "FOOTWEAR", ""}),
    spelling_fixes={"BALLERANIS": "BALLERINAS"},
    prefix_map={"PX": "JEWELRY"},
)


def test_extract_gender_age_from_either_lens():
    g, a = TAXO.gender, TAXO.age
    assert extract_gender_age("WALLET", "MENS", g, a) == ("M", None)  # gender in subsection
    assert extract_gender_age("WOMENS", "SANDALS", g, a) == ("F", None)  # gender in section
    assert extract_gender_age("KIDS", "BS GIRLS", g, a) == (None, "kids")  # age via substring ('GIRLS')
    assert extract_gender_age("", "", g, a) == (None, None)


def _resolve(section, subsection, code):
    t = TAXO
    return resolve_token(section, subsection, code, t.relation, t.gender, t.age, t.placeholder, t.prefix_map)


def test_resolve_token_deconvolves_across_both_lenses():
    assert _resolve("WALLET", "MENS", "TE-1") == "WALLET"  # category in section (subsection is gender)
    assert _resolve("SOCKS/POLISH", "ACCESSORIES", "X") == "SOCKS/POLISH"  # category in section
    assert _resolve("WOMENS", "SANDALS", "A") == "SANDALS"  # category in subsection
    assert _resolve("ACCESSORIES", "BS MENS", "PX9001") == "JEWELRY"  # code-prefix override wins
    assert _resolve("", "", "") == ""  # nothing informative → empty


def test_translate_category_full_deconvolution_and_abstention():
    # a men's wallet: category from section, gender from subsection, raw preserved
    r = translate_category("WALLET", "MENS", "TE-1", TAXO)
    assert r["cluster"] == "Bags"
    assert r["sub_category"] == "Wallet"
    assert r["gender"] == "M"
    assert r["status"] == "resolved"
    assert r["raw"] == {"section": "WALLET", "subsection": "MENS"}  # raw is sacred

    # STRAPPY has no resolved type in this vocabulary -> flagged, NEVER guessed, gender still extracted
    s = translate_category("WOMENS", "STRAPPY", "S1", TAXO)
    assert s["status"] == "unadjudicated"
    assert s["cluster"] is None
    assert s["gender"] == "F"
    assert s["raw"]["subsection"] == "STRAPPY"


def test_translate_taxonomy_adds_category_and_preserves_raw_idempotently():
    raw = {"A1": {"section": "WALLET", "subsection": "MENS"}, "A2": {"section": "", "subsection": "STRAPPY"}}
    out = translate_taxonomy(raw, TAXO)
    assert out["A1"]["category"]["sub_category"] == "Wallet"
    assert out["A1"]["section"] == "WALLET"  # original fields carried through untouched
    assert out["A1"]["category"]["raw"] == {"section": "WALLET", "subsection": "MENS"}
    assert out["A2"]["category"]["status"] == "unadjudicated"
    # idempotent: re-running over the output's raw yields the same category
    raw2 = {k: {"section": v["section"], "subsection": v["subsection"]} for k, v in out.items()}
    again = translate_taxonomy(raw2, TAXO)
    assert again["A1"]["category"] == out["A1"]["category"]
    assert translate_taxonomy({}, TAXO) == {}


def test_active_taxonomy_default_used_when_cfg_omitted():
    """With no explicit cfg, the machinery reads the active cassette — exercised via the bundled example."""
    r = translate_category("", "", "")  # nothing resolves regardless of vocabulary
    assert r["status"] == "unadjudicated"
