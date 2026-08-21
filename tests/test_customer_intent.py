"""Hand-authored INTENT tests for peitho.customer — the harmonization rules, from the operator's spec.

These pin the AGREED behavior (name-split rules, mobile canonicalization, the customerCode wormhole, the
gender decode, the merge-vs-household name match). Paired with Detective's mutation-complete synth suites;
where Detective leaves candidate-equivalent (undecidable) mutants, these carry the specification.
"""

from peitho.customer import (
    bill_store,
    build_customer_nodes,
    canonicalize_mobile,
    clean_record,
    customer_rfm,
    customer_segment,
    decode_customer_code,
    extract_title,
    fold_name,
    gender_label,
    mine_rfm_baselines,
    name_class,
    names_match,
    normalize_name,
    resolve_identities,
    split_name,
)


def test_normalize_name_whitespace_case_and_initials():
    assert normalize_name("j.r.  SMITH") == "J.R. Smith"  # initials stay upper, word titlecased, ws collapsed
    assert normalize_name("SMITH") == "Smith"
    assert normalize_name("john  adams") == "John Adams"
    assert normalize_name("") == ""


def test_extract_title_canonicalizes_and_strips():
    assert extract_title("Mr John Miller") == ("MR", "John Miller")
    assert extract_title("MRS. Susan") == ("MRS", "Susan")
    assert extract_title("Miss Emma") == ("MS", "Emma")  # MISS -> MS
    assert extract_title("Prof Adams") == ("DR", "Adams")  # PROF -> DR
    assert extract_title("John") == (None, "John")  # no title
    assert extract_title("") == (None, "")


def test_split_name_house_rules():
    assert split_name("J.R. Smith") == ("J.R.", "Smith")  # initials + surname
    assert split_name("J R Smith") == ("J R", "Smith")  # spaced initials + surname
    assert split_name("John Miller") == ("John", "Miller")  # two words -> first/last
    assert split_name("John Robert Miller") == ("John", "Robert Miller")  # first word, rest = lname
    assert split_name("John") == ("John", "")  # single token -> fname only
    assert split_name("R") == ("R", "")  # single char -> fname only (flagged by name_class)
    assert split_name("") == ("", "")


def test_canonicalize_mobile_strips_prefix_and_validates():
    assert canonicalize_mobile("5551234567") == "5551234567"  # already canonical (10 digits)
    assert canonicalize_mobile("+1 555 123 4567") == "5551234567"  # strip country code, keep the last 10
    assert canonicalize_mobile("(555) 123-4567") == "5551234567"  # strip separators/punctuation
    assert canonicalize_mobile("9999999999") is None  # all-same junk
    assert canonicalize_mobile("1234") is None  # too short
    assert canonicalize_mobile("") is None
    assert canonicalize_mobile(None) is None


def test_decode_customer_code_wormhole():
    assert decode_customer_code("AC0000012345") == ("AC", 12345)  # store prefix + ordinal
    assert decode_customer_code("AH0000000001") == ("AH", 1)
    assert decode_customer_code("000000000000") == (None, None)  # walk-in / no real code
    assert decode_customer_code("junk") == (None, None)
    assert decode_customer_code("") == (None, None)


def test_gender_label_decoded_confidence_aware():
    assert gender_label(2) == "FEMALE"  # code 2 = female, high confidence
    assert gender_label(2.0) == "FEMALE"  # real data is float
    assert gender_label(1) == "MALE_SOFT"  # code 1 = male but soft (default-contaminated)
    assert gender_label(0) == "UNSPECIFIED"  # 0 = unspecified default
    assert gender_label(3) == "UNSPECIFIED"  # rare/other
    assert gender_label(None) == "UNSPECIFIED"
    assert gender_label("") == "UNSPECIFIED"


def test_name_class_flags_walkins_and_quirks():
    assert name_class("John") == "REAL"
    assert name_class("J.R. Smith") == "REAL"
    assert name_class(".") == "PLACEHOLDER"
    assert name_class("CASH") == "PLACEHOLDER"
    assert name_class("123") == "PLACEHOLDER"
    assert name_class("R") == "SINGLE_CHAR"  # the one-char-name quirk — kept but flagged
    assert name_class("") == "EMPTY"
    assert name_class("   ") == "EMPTY"


def test_names_match_merge_vs_household():
    assert names_match("John", "JOHN") == "MATCH"  # same person (case-insensitive)
    assert names_match("R.K.", "r.k.") == "MATCH"
    assert names_match("John", "Susan") == "NO_MATCH"  # family / shared phone -> household, not merge
    assert names_match("John", ".") == "UNKNOWN"  # placeholder -> can't judge
    assert names_match("", "Susan") == "UNKNOWN"


def test_bill_store_prefix():
    assert bill_store("AH-26-0128") == "AH"  # store = 2-letter bill-number prefix
    assert bill_store("AE01127000ND") == "AE"
    assert bill_store("") == "?"
    assert bill_store("12-345") == "?"  # non-alpha prefix


def test_customer_rfm_aggregates_visits():
    bills = [
        {"date": "2026-01-10T00:00:00", "bill_no": "AH-1", "amount": 2000.0, "cancelled": False},
        {"date": "2026-07-16T00:00:00", "bill_no": "AB-2", "amount": 3000.0, "cancelled": False},
        {"date": "2026-08-01T00:00:00", "bill_no": "AH-9", "amount": 500.0, "cancelled": True},  # excluded
    ]
    r = customer_rfm(bills, today="2026-08-15")
    assert r["frequency"] == 2  # cancelled excluded
    assert r["monetary"] == 5000.0
    assert r["last_visit"] == "2026-07-16"
    assert r["recency_days"] == 30  # 2026-07-16 -> 2026-08-15
    assert r["stores"] == ["AB", "AH"]  # multi-store, sorted
    assert customer_rfm([], today="2026-08-15")["frequency"] == 0  # no bills


def test_fold_name_applies_ssc_across_tokens():
    # fold_name (customer's name-specific consumer of the shared fuzzy_fold) corrects every word token
    assert fold_name("Smit Miler", {"Smith": 500, "Miller": 300}, 1, 10) == "Smith Miller"


def test_clean_record_composes_harmonizers():
    r = clean_record(
        {
            "name": "Mr John Miller",
            "mobile": "05551234567",
            "customerCode": "AC0000012345",
            "gender": 2.0,
            "created": "2026-01-01",
        }
    )
    assert r["title"] == "MR"
    assert (r["fname"], r["lname"]) == ("John", "Miller")
    assert r["mobile"] == "5551234567"  # country/trunk prefix stripped
    assert r["store"] == "AC"  # wormhole decode
    assert r["gender"] == "FEMALE"


def test_resolve_identities_merge_vs_household():
    # two re-registrations of one person (same mobile, same name, typo) + one family member (same mobile)
    recs = [
        {
            "code": "AC1",
            "mobile": "5551234567",
            "fname": "John",
            "lname": "Miller",
            "nclass": "REAL",
            "gender": "MALE_SOFT",
            "store": "AC",
            "ordinal": 1,
            "created": "2024-01-01",
        },
        {
            "code": "AH2",
            "mobile": "5551234567",
            "fname": "Jon",
            "lname": "Miller",
            "nclass": "REAL",
            "gender": "UNSPECIFIED",
            "store": "AH",
            "ordinal": 2,
            "created": "2025-01-01",
        },
        {
            "code": "AC3",
            "mobile": "5551234567",
            "fname": "Susan",
            "lname": "Miller",
            "nclass": "REAL",
            "gender": "FEMALE",
            "store": "AC",
            "ordinal": 3,
            "created": "2026-01-01",
        },
    ]
    corpus = {"John": 2000, "Miller": 1200, "Susan": 1000}
    res = resolve_identities(recs, corpus, corpus, max_dist=1, min_ratio=10, canon_floor=1)
    s = res["stats"]
    assert s["persons"] == 2  # John (merged from 2) + Susan
    assert s["records_merged_away"] == 1  # Jon folded into John
    assert s["households"] == 1  # John + Susan share the mobile, different names
    john = next(p for p in res["persons"] if p["name"].startswith("John"))
    assert set(john["codes"]) == {"AC1", "AH2"}  # both registrations linked for order-linking


def test_resolve_identities_abstains_on_placeholder_names():
    # the abstention tier (ternary 0): placeholder/empty names can't identify a person, so on a shared mobile
    # they neither merge into anyone nor form a household — each stays its own unresolved person.
    recs = [
        {
            "code": "A",
            "mobile": "5551234567",
            "fname": "John",
            "lname": "Miller",
            "nclass": "REAL",
            "gender": "UNSPECIFIED",
            "store": "AC",
            "ordinal": 1,
            "created": "2024",
        },
        {
            "code": "B",
            "mobile": "5551234567",
            "fname": ".",
            "lname": "",
            "nclass": "PLACEHOLDER",
            "gender": "UNSPECIFIED",
            "store": "AH",
            "ordinal": 2,
            "created": "2025",
        },
        {
            "code": "C",
            "mobile": "5551234567",
            "fname": ".",
            "lname": "",
            "nclass": "PLACEHOLDER",
            "gender": "UNSPECIFIED",
            "store": "AC",
            "ordinal": 3,
            "created": "2026",
        },
    ]
    corpus = {"John": 2000, "Miller": 1200}
    s = resolve_identities(recs, corpus, corpus, max_dist=1, min_ratio=10, canon_floor=1)["stats"]
    assert s["persons"] == 3  # John + two SEPARATE unresolved placeholders
    assert s["records_merged_away"] == 0  # the two '.' records did NOT merge into one
    assert s["households"] == 0  # placeholders form NO household with the real person


def test_conservative_intersection_is_stricter_than_any_single_setting():
    # 'Jon' folds to 'Ron' at dist 1, but retargets to the much-commoner 'Jones' at dist 2 — so a loose
    # single pass MERGES Jon/Ron, while the intersection (which must also agree under the d=2 pass) does NOT.
    recs = [
        {
            "code": "A",
            "mobile": "5551234567",
            "fname": "Jon",
            "lname": "",
            "nclass": "REAL",
            "gender": "UNSPECIFIED",
            "store": "AC",
            "ordinal": 1,
            "created": "2024",
        },
        {
            "code": "B",
            "mobile": "5551234567",
            "fname": "Ron",
            "lname": "",
            "nclass": "REAL",
            "gender": "UNSPECIFIED",
            "store": "AC",
            "ordinal": 2,
            "created": "2025",
        },
    ]
    corpus = {"Ron": 200, "Jones": 5000}
    single = resolve_identities(recs, corpus, corpus, max_dist=1, min_ratio=10, canon_floor=1)
    assert single["stats"]["persons"] == 1  # loose single pass merges Jon->Ron
    inter = resolve_identities(recs, corpus, corpus, settings=[(1, 10, 1), (2, 10, 1)])
    assert inter["stats"]["persons"] == 2  # intersection: d=2 retargets Jon->Jones, settings disagree -> no merge


def test_build_customer_nodes_pools_bills_across_merged_codes():
    # a merged person with two customerCodes: their RFM must pool bills from BOTH (the payoff of the merge)
    persons = [
        {
            "codes": ["AC1", "AH2"],
            "merged": 2,
            "mobile": "5551234567",
            "name": "John Miller",
            "store": "AC",
            "gender": "MALE_SOFT",
            "created": "2024-01-01",
            "household": None,
        }
    ]
    bills = {
        "AC1": [{"date": "2026-01-10", "bill_no": "AC-1", "amount": 2000.0, "cancelled": False}],
        "AH2": [{"date": "2026-07-16", "bill_no": "AH-2", "amount": 3000.0, "cancelled": False}],
    }
    nodes = build_customer_nodes(persons, bills, today="2026-08-15")
    assert nodes[0]["rfm"]["frequency"] == 2  # bills from BOTH codes pooled
    assert nodes[0]["rfm"]["monetary"] == 5000.0
    assert nodes[0]["rfm"]["last_visit"] == "2026-07-16"
    assert nodes[0]["name"] == "John Miller"  # identity preserved alongside RFM


# --- RFM segmentation: named segments from signed deviation vs the mined population median ---
def _node(freq, monetary, recency):
    return {"rfm": {"frequency": freq, "monetary": monetary, "recency_days": recency}}


def test_mine_rfm_baselines_medians_over_active_only():
    # inactive persons (frequency 0) must NOT drag the norms down — baselines are over ACTIVE nodes only
    nodes = [_node(0, 0.0, None), _node(2, 3000.0, 180), _node(4, 5000.0, 100), _node(6, 1000.0, 200)]
    b = mine_rfm_baselines(nodes)
    assert b == {"recency_days": 180, "frequency": 4, "monetary": 3000.0}  # median of the 3 active, not all 4
    assert mine_rfm_baselines([_node(0, 0.0, None)]) == {"recency_days": None, "frequency": None, "monetary": None}


def test_customer_segment_named_bands_from_deviation():
    base = {"recency_days": 180, "frequency": 2, "monetary": 3000.0}

    def seg(f, m, r, **kw):
        return customer_segment({"frequency": f, "monetary": m, "recency_days": r}, base, **kw)

    assert seg(0, 0.0, None) == "INACTIVE"  # no valid purchase
    assert seg(10, 10000.0, 90) == "CHAMPION"  # above-norm buyer AND more recent than norm
    assert seg(10, 10000.0, 400) == "AT_RISK"  # above-norm buyer BUT overdue (recency >> 2x median) — retain signal
    assert seg(10, 10000.0, 180) == "LOYAL"  # above-norm buyer, recency ordinary
    assert seg(1, 1000.0, 60) == "NEW"  # recent, at/below the median visit count — early relationship
    assert seg(1, 500.0, 400) == "LOST"  # below-norm value AND overdue
    assert seg(2, 3000.0, 180) == "REGULAR"  # right at the norms
    # the overdue threshold is tunable: a 9-month gap counts as overdue only when overdue_at is lowered to fit
    assert seg(10, 10000.0, 270) == "LOYAL"  # 270d not overdue at the default 1.0 (needs >358d)
    assert seg(10, 10000.0, 270, overdue_at=0.5) == "AT_RISK"  # lower the bar → 9-month gap now reads as lapsing
