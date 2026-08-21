"""peitho.customer — harmonize the customer master into clean node-network identities (pure data geometry).

Grounded in the profiled shape of a customer master:
- node key = `customerCode` — a registration-store prefix + ordinal (a cross-store identity signal, like the
  SKU registration code): it records WHERE a person first registered and in what order, never a reusable name
- `mobile` (the clean, near-universal identity anchor) = the dedupe/join key — how account-linking actually
  works in practice (a live phone number + verbal name confirmation), so mobile-anchored / name-disambiguated
  is the correct identity primitive
- the name field is WEAK — usually a single token; it cannot anchor identity, only disambiguates within a
  shared-mobile cluster (same name -> same person -> MERGE; different name -> household -> KEEP + household edge)

This module is the pure-decision layer (below, Detective-pinned). The aggregation/impute layer (RFM, last-visit,
stores-visited from the bill headers) and the mobile-dedupe/household resolver compose these primitives. No
stochastic component; every output is a deterministic function of the input record.
"""

from __future__ import annotations

import datetime
import re
from statistics import median

from .geometry import deviation  # the significance primitive: signed fractional deviation from a mined baseline
from .text import fuzzy_fold  # the SymbolicSpellCheck noisy-channel core (shared; see peitho.text)

# leading honorifics embedded in the name field; stripping them de-noises + gives a gender cross-signal.
# This is the generic set; a locale-specific set is cassette config (see OPERATIONS.md), not core.
_TITLE = re.compile(r"^(MRS|MISS|MR|MS|DR|PROF|M/S)\b\.?\s*", re.I)
_TITLE_CANON = {
    "MR": "MR",
    "MRS": "MRS",
    "MS": "MS",
    "MISS": "MS",
    "DR": "DR",
    "PROF": "DR",
    "M/S": "M/S",
}
# placeholder / walk-in junk in the name field ('.', CASH, CUSTOMER, digits, NA)
_PLACEHOLDER = re.compile(r"^(cash|generic|customer|cust|n\.?a\.?|test|x+|\.+|-+|\d+)$", re.I)


def _is_initial(tok: str) -> bool:
    """A name token that is an initial rather than a word: 'R', 'R.', 'R.K.' — not 'Raj'. Pure over a string."""
    if len(tok) == 1 and tok.isalpha():
        return True
    return bool(re.fullmatch(r"([A-Za-z]\.){1,3}", tok)) or bool(re.fullmatch(r"[A-Za-z]\.", tok))


def normalize_name(raw: str) -> str:
    """Collapse whitespace, strip, and case-normalize a name: word tokens -> Titlecase, initial tokens -> UPPER
    (so 'j.r.  SMITH ' -> 'J.R. Smith'). Total over any string; '' for blank. Pure."""
    if not raw:
        return ""
    out = []
    for tok in raw.split():
        out.append(tok.upper() if _is_initial(tok) else tok[:1].upper() + tok[1:].lower())
    return " ".join(out)


def extract_title(raw: str) -> tuple:
    """Split a leading honorific off the name: 'Mr John' -> ('MR', 'John'). Returns (title_code|None, rest).
    Title canonicalized (MISS->MS, PROF->DR). No title -> (None, stripped raw). Pure."""
    if not raw:
        return (None, "")
    m = _TITLE.match(raw)
    if not m:
        return (None, raw.strip())
    title = _TITLE_CANON.get(m.group(1).upper().rstrip("."), m.group(1).upper())
    return (title, raw[m.end() :].strip())


def split_name(raw: str) -> tuple:
    """Split a (title-stripped) name into (fname, lname) per the house rules:
      'J.R. Smith' / 'J R Smith'  -> ('J.R.'|'J R', 'Smith')    (leading initials = fname, surname = lname)
      'John Miller'               -> ('John', 'Miller')          (two words -> first/last)
      'John Robert Miller'        -> ('John', 'Robert Miller')   (first word, rest = lname)
      'John' / 'J'                -> ('John'|'J', '')            (single token -> fname only)
    Total over any string; ('', '') for blank. Pure."""
    toks = raw.split() if raw else []
    if not toks:
        return ("", "")
    if len(toks) == 1:
        return (toks[0], "")
    lead = 0
    while lead < len(toks) and _is_initial(toks[lead]):
        lead += 1
    if 0 < lead < len(toks):  # leading initials + a trailing surname
        return (" ".join(toks[:lead]), " ".join(toks[lead:]))
    if len(toks) == 2:
        return (toks[0], toks[1])
    return (toks[0], " ".join(toks[1:]))


def canonicalize_mobile(raw) -> str | None:
    """Reduce a raw phone value to a canonical 10-digit national number, or None if it isn't one. Strips
    non-digits and any leading country/trunk prefix (keeping the last 10 digits) and rejects all-same-digit
    junk. Pure over str/number."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) < 10:
        return None
    national = digits[-10:]  # the last 10 digits = the national number, dropping any country/trunk prefix
    if len(set(national)) == 1:  # all-same-digit junk (0000000000, 9999999999)
        return None
    return national


def decode_customer_code(code) -> tuple:
    """Decode the customerCode `<prefix><ordinal>` -> (store_prefix, ordinal): 'AB0000012345' -> ('AB', 12345).
    Prefix = registration store (locality proxy); ordinal = registration sequence. (None, None) if not the shape.
    Pure over a string."""
    m = re.fullmatch(r"([A-Za-z]{2})(\d+)", str(code or "").strip())
    if not m:
        return (None, None)
    return (m.group(1).upper(), int(m.group(2)))


def gender_label(code) -> str:
    """Map the numeric gender code to a named, confidence-aware label (never a bare bool). Decoded via title
    cross-reference: 2 = Female (high-confidence, rarely defaulted); 1 = Male but soft (code 1 is partly a
    registration default); 0 / 3 / missing = unspecified. Pure over str/number/None."""
    if code in (None, ""):
        return "UNSPECIFIED"
    try:
        c = int(float(code))
    except (TypeError, ValueError):
        return "UNSPECIFIED"
    if c == 2:
        return "FEMALE"
    if c == 1:
        return "MALE_SOFT"
    return "UNSPECIFIED"


def name_class(raw: str) -> str:
    """Classify the name field before it is trusted as a person: EMPTY (blank), PLACEHOLDER (cash/./digits/NA —
    a walk-in, not a person), SINGLE_CHAR (a lone letter — the one-char-name quirk, kept but flagged), or REAL.
    Named codes, never a bool. Pure over any string."""
    s = (raw or "").strip()
    if not s:
        return "EMPTY"
    if _PLACEHOLDER.fullmatch(s):
        return "PLACEHOLDER"
    toks = s.split()
    if len(toks) == 1 and len(toks[0]) == 1:
        return "SINGLE_CHAR"
    return "REAL"


def names_match(a: str, b: str) -> str:
    """The merge-vs-household disambiguator (exact tier): MATCH if the two names normalize equal, NO_MATCH if
    they clearly differ, UNKNOWN if either is empty/placeholder (can't judge). Fuzzy/typo matching is layered on
    top at aggregation time via SymbolicSpellCheck; this pure tier is the deterministic floor. Named codes. Pure."""
    if name_class(a) in ("EMPTY", "PLACEHOLDER") or name_class(b) in ("EMPTY", "PLACEHOLDER"):
        return "UNKNOWN"
    return "MATCH" if normalize_name(a) == normalize_name(b) else "NO_MATCH"


# The SymbolicSpellCheck noisy-channel core (levenshtein + fuzzy_fold) now lives in `peitho.text` so the
# same error-correction move is shared with the export subsection normalizer. `fold_name` (below) applies
# it to name tokens against the first/last-name corpora.


# ---------------------------------------------------------------------------
# Aggregation layer: RFM + visits from the bill headers.
# Groups bills by customerCode -> the customer<->transaction edge the master lacks.
# ---------------------------------------------------------------------------


def bill_store(bill_no) -> str:
    """Selling store = the 2-letter store prefix of the bill number, e.g. 'AB-26-0128' -> 'AB'. '?' if
    absent/malformed. Pure over a string."""
    p = str(bill_no or "").strip()[:2].upper()
    return p if len(p) == 2 and p.isalpha() else "?"


def _days_between(d_from: str, d_to: str) -> int | None:
    """Whole days from d_from to d_to (ISO 'YYYY-MM-DD' prefixes), or None if either is unparseable. Pure."""
    try:
        a = datetime.date.fromisoformat(str(d_from)[:10])
        b = datetime.date.fromisoformat(str(d_to)[:10])
    except (ValueError, TypeError):
        return None
    return (b - a).days


def customer_rfm(bills: list, today: str) -> dict:
    """Aggregate one customer's bills into RFM + visit facts. bills = [{date, bill_no, amount, cancelled}, …].
    Returns {last_visit, recency_days, frequency, monetary, stores}. Cancelled bills excluded; returns (negative
    totals) net into monetary. `today` is the reference date (passed in, keeping this pure). Pure over a list."""
    dates = []
    monetary = 0.0
    stores = set()
    freq = 0
    for b in bills:
        if b.get("cancelled"):
            continue
        d = str(b.get("date") or "")[:10]
        if d:
            dates.append(d)
        monetary += float(b.get("amount") or 0)
        stores.add(bill_store(b.get("bill_no")))
        freq += 1
    last = max(dates) if dates else None
    return {
        "last_visit": last,
        "recency_days": _days_between(last, today) if last else None,
        "frequency": freq,
        "monetary": round(monetary, 2),
        "stores": sorted(stores),
    }


def mine_rfm_baselines(nodes: list) -> dict:
    """The zero-means the segment deviates from: population MEDIANS of each RFM axis over ACTIVE nodes
    (frequency > 0). Inactive persons (registered, no valid purchase) are excluded so they don't drag the
    norms down. Median (not mean) because monetary/frequency are heavily right-skewed. Pure over the nodes."""
    active = [n["rfm"] for n in nodes if n["rfm"]["frequency"] > 0 and n["rfm"]["recency_days"] is not None]
    if not active:
        return {"recency_days": None, "frequency": None, "monetary": None}
    return {
        "recency_days": median(r["recency_days"] for r in active),
        "frequency": median(r["frequency"] for r in active),
        "monetary": median(r["monetary"] for r in active),
    }


def customer_segment(rfm: dict, baselines: dict, valuable_at: float = 0.5, overdue_at: float = 1.0) -> str:
    """Named RFM segment from each axis's SIGNED DEVIATION vs the population median (the significance primitive,
    not arbitrary quintiles). Named codes, never a score. The operationally load-bearing split is AT_RISK
    (valuable but overdue — the retain signal) vs LOST (low value AND overdue). Thresholds tunable:
      INACTIVE : no valid purchase on record (frequency 0 / no last visit).
      CHAMPION : above-norm buyer (freq+spend) AND more recent than the norm.
      AT_RISK  : above-norm buyer BUT overdue (recency ≫ the median gap) — was valuable, slipping away.
      LOYAL    : above-norm buyer, recency ordinary.
      NEW      : recent but at-or-below the median visit count — early in the relationship.
      LOST     : below-norm value AND overdue.
      REGULAR  : everyone around the norms.
    `value` sums the frequency + monetary deviations; `lapse` is the recency deviation (+ = more overdue). Pure."""
    if rfm["frequency"] <= 0 or rfm["recency_days"] is None:
        return "INACTIVE"
    rmed, fmed, mmed = baselines["recency_days"], baselines["frequency"], baselines["monetary"]
    lapse = deviation(rfm["recency_days"], rmed)  # + = more days since last visit than the median (overdue)
    value = deviation(rfm["frequency"], fmed) + deviation(rfm["monetary"], mmed)
    overdue = lapse >= overdue_at
    recent = lapse <= -0.25
    valuable = value >= valuable_at
    if valuable and recent:
        return "CHAMPION"
    if valuable and overdue:
        return "AT_RISK"
    if valuable:
        return "LOYAL"
    if recent and rfm["frequency"] <= (fmed or 0):
        return "NEW"
    if overdue:
        return "LOST"
    return "REGULAR"


def load_bills_by_customer(bill_dir: str | None = None) -> dict:
    """Landed bill headers grouped by real customerCode — via the active cassette's data-input adapter
    (`peitho.source`). {customerCode: [bill, …]}."""
    from . import source

    return source.adapter().load_bills_by_customer(bill_dir)


# ---------------------------------------------------------------------------
# Identity resolution: clean the master, build the two name corpora, and dedupe
# mobile-anchored / name-disambiguated (merge same-person, household-link family).
# ---------------------------------------------------------------------------


def clean_record(raw_rec: dict) -> dict:
    """Apply the pure harmonizers to one raw customer-master record -> a clean node record. Pure over a dict."""
    title, rest = extract_title(normalize_name(raw_rec.get("name") or ""))
    fname, lname = split_name(rest)
    store, ordinal = decode_customer_code(raw_rec.get("customerCode"))
    return {
        "code": raw_rec.get("customerCode"),
        "mobile": canonicalize_mobile(raw_rec.get("mobile")),
        "title": title,
        "fname": fname,
        "lname": lname,
        "nclass": name_class(rest),
        "gender": gender_label(raw_rec.get("gender")),
        "store": store,
        "ordinal": ordinal,
        "created": str(raw_rec.get("created") or "")[:10],
    }


def load_clean_master(customer_dir: str | None = None) -> list:
    """The harmonized customer master node records — via the active cassette's data-input adapter. The pure
    per-row harmonizer (`clean_record`) stays in the core; the adapter owns the file layout + PII paths."""
    from . import source

    return source.adapter().load_clean_master(customer_dir)


def build_corpora(records: list) -> tuple:
    """Frequency corpora of first- and last-name TOKENS from cleaned records (the SSC grounding). Titles are
    already stripped. Returns (first_freq, last_freq). Pure over a list."""
    first: dict = {}
    last: dict = {}
    for r in records:
        for t in r["fname"].split():
            if len(t) > 1 and t.isalpha():
                first[t] = first.get(t, 0) + 1
        for t in r["lname"].split():
            if len(t) > 1 and t.isalpha():
                last[t] = last.get(t, 0) + 1
    return first, last


def fold_name(name: str, corpus: dict, max_dist: int = 1, min_ratio: int = 10, canon_floor: int = 1) -> str:
    """Fold every word token of a name toward its canonical spelling via the FULL corpus (initials/short
    tokens pass through). `canon_floor` restricts fold targets. Pure over (str, dict)."""
    return " ".join(
        fuzzy_fold(t, corpus, max_dist, min_ratio, canon_floor) if (len(t) > 1 and t.isalpha()) else t
        for t in name.split()
    )


# conservative default: merge two records only if they fold together under EVERY one of these settings
# (the INTERSECTION of the knob sweep — the merges all settings agree on). Because fuzzy_fold snaps to the
# highest-frequency neighbour, a looser max_dist can retarget a fold and BREAK a cluster a stricter one made,
# so the clusterings are not nested — the intersection must be computed, not taken from one setting.
CONSERVATIVE_SETTINGS = [(1, 10, 5), (1, 20, 5), (2, 10, 5), (2, 5, 5), (1, 10, 2)]


def resolve_identities(
    records: list,
    first_corpus: dict,
    last_corpus: dict,
    max_dist: int = 1,
    min_ratio: int = 10,
    canon_floor: int = 5,
    settings: list | None = None,
) -> dict:
    """Mobile-anchored, name-disambiguated identity resolution. Groups by canonical mobile; within a
    shared-mobile cluster, folds names (SSC) and collapses matching-name records into ONE person (merge),
    while distinct-name records stay separate + are linked as a household. Records without a canonical
    mobile are kept as singleton persons. Returns {persons, stats}.

    Single setting via (max_dist, min_ratio, canon_floor). Pass `settings` = a list of such triples to take
    the CONSERVATIVE INTERSECTION: two records merge only if they fold together under *every* setting."""
    folds = settings or [(max_dist, min_ratio, canon_floor)]
    # keep the FULL corpora (fuzzy_fold reads own-frequency from them); `fl` restricts fold TARGETS only.
    canon = [(first_corpus, last_corpus, d, r, fl) for (d, r, fl) in folds]

    # fold_name is PURE and the (corpus, knobs) are fixed within each setting, so a given name string folds
    # to the same canonical form for every record. Memoize per setting (fname/lname cached separately) so the
    # ~27k distinct name tokens are folded once each instead of once per record — transparent, provably
    # behaviour-identical (the real-data re-run + resolve pins prove it), turns the O(records) pass into O(distinct).
    _fmemo: list = [{} for _ in canon]
    _lmemo: list = [{} for _ in canon]

    def _fold_cached(cache: dict, name: str, corpus: dict, d: int, rr: int, fl: int) -> str:
        if name not in cache:
            cache[name] = fold_name(name, corpus, d, rr, fl)
        return cache[name]

    by_mobile: dict = {}
    no_mobile = []
    for r in records:
        if r["mobile"]:
            by_mobile.setdefault(r["mobile"], []).append(r)
        else:
            no_mobile.append(r)

    def make_person(recs: list, mobile, household_id=None) -> dict:
        recs = sorted(recs, key=lambda r: r.get("created") or "")
        head = recs[0]
        return {
            "codes": [r["code"] for r in recs],
            "merged": len(recs),
            "mobile": mobile,
            "name": f"{head['fname']} {head['lname']}".strip(),
            "store": head["store"],
            "gender": next((r["gender"] for r in recs if r["gender"] != "UNSPECIFIED"), "UNSPECIFIED"),
            "created": head["created"],
            "household": household_id,
        }

    persons = []
    households = 0
    merged_records = 0
    hh_id = 0
    for mobile, group in by_mobile.items():
        # ABSTENTION (the ternary 0, made concrete): a record whose name cannot identify a person — empty or
        # a placeholder like '.'/'CASH' (name_class ∈ {EMPTY, PLACEHOLDER}) — is NEITHER merged into anyone
        # NOR counted as a distinct household member. We cannot judge, so it stays its own unresolved person.
        for r in group:
            if r["nclass"] in ("EMPTY", "PLACEHOLDER"):
                persons.append(make_person([r], mobile))
        resolvable = [r for r in group if r["nclass"] not in ("EMPTY", "PLACEHOLDER")]
        if not resolvable:
            continue
        if len(resolvable) == 1:
            persons.append(make_person(resolvable, mobile))
            continue
        clusters: dict = {}
        for r in resolvable:
            # key = how this record folds under EVERY setting; two records share a key only if they merge
            # under all of them (the intersection). One setting -> a length-1 tuple (ordinary single-pass).
            key = tuple(
                (
                    _fold_cached(_fmemo[i], r["fname"], fc, d, rr, fl),
                    _fold_cached(_lmemo[i], r["lname"], lc, d, rr, fl),
                )
                for i, (fc, lc, d, rr, fl) in enumerate(canon)
            )
            clusters.setdefault(key, []).append(r)
        this_hh = None
        if len(clusters) > 1:  # >1 distinct RESOLVABLE person on the mobile = a household
            households += 1
            hh_id += 1
            this_hh = hh_id
        for recs in clusters.values():
            if len(recs) > 1:
                merged_records += len(recs) - 1
            persons.append(make_person(recs, mobile, this_hh))
    persons.extend(make_person([r], None) for r in no_mobile)

    return {
        "persons": persons,
        "stats": {
            "input_records": len(records),
            "persons": len(persons),
            "records_merged_away": merged_records,
            "households": households,
            "no_mobile_singletons": len(no_mobile),
        },
    }


def build_customer_nodes(persons: list, bills_by_customer: dict, today: str) -> list:
    """Join RFM/visit facts onto each resolved person by pooling the bills of ALL its merged customerCodes —
    the payoff of the merge: one person's whole purchase history, even across re-registrations. Each node =
    identity + household + RFM. I/O-free join over already-loaded structures."""
    nodes = []
    for p in persons:
        bills = [b for code in p["codes"] for b in bills_by_customer.get(str(code), [])]
        nodes.append({**p, "rfm": customer_rfm(bills, today)})
    return nodes


def report() -> None:
    records = load_clean_master()
    first, last = build_corpora(records)
    res = resolve_identities(records, first, last, settings=CONSERVATIVE_SETTINGS)
    s = res["stats"]
    print("CUSTOMER identity resolution (mobile-anchored, SSC name-disambiguated; CONSERVATIVE intersection):")
    print(f"  input master records : {s['input_records']:,}")
    print(f"  distinct persons     : {s['persons']:,}")
    print(f"  records merged away  : {s['records_merged_away']:,} (same person, re-registered)")
    print(f"  households formed    : {s['households']:,} (shared mobile, different names)")
    print(f"  no-mobile singletons : {s['no_mobile_singletons']:,}")
    print(f"  first-name corpus    : {len(first):,} tokens · last-name corpus: {len(last):,} tokens")


if __name__ == "__main__":
    report()
