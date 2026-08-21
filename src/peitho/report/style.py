"""report.style — the shared editorial chassis for the rendered report (the place the voice lives).

One module holds every cross-report presentation decision, so the report reads as a single editorial
process rather than as ad-hoc string-building: the white-ground stylesheet (the corporate-report
standard — one consistent look across screen, print, and paste-into-a-deck, so the artifact never
reads differently in different contexts), the proper-casing of raw keys so no slug leaks into a label,
and the lexicon that turns the geometry's
mechanical `BANK:word` tokens into a flat operator phrase. The functions here are pure formatting over
primitives; the structural decisions live in `report.render`.

The visual register is "commercial data": a white ground, blue hierarchy with transparency, and muted
pastel data accents keyed one-to-one to the four banks (color as a stable mnemonic — the reader learns
the map once, then reads every chip through it). Muted, never vivid; the eye goes to the numbers.
"""

from __future__ import annotations

NEUTRAL = "·"  # the informational zero in a signature token (that axis abstains) — see noticer.VOCAB

# The operator lexicon: one flat phrase per (bank, mechanical-word) pair the geometry can emit
# (noticer.VOCAB is the source of the words). Deliberately terse and non-editorializing — the report is
# a reference artifact, not a pitch. An unknown pair is never dropped or guessed; it degrades to a
# readable "bank word" fallback (humanize_token), the same abstain-don't-fabricate discipline the banks use.
REASON_LEXICON: dict = {
    ("INVENTORY", "deficit"): "low cover",
    ("INVENTORY", "surplus"): "over-covered",
    ("PRICE", "marked-down"): "discounted",
    ("PRICE", "full-price"): "full price",
    ("SPATIAL", "short"): "below target",
    ("SPATIAL", "spare"): "surplus to give",
    ("VELOCITY", "accelerating"): "selling fast",
    ("VELOCITY", "fading"): "slowing",
}

# Each bank's stable chip colour class (color-as-mnemonic): the same hue always means the same dimension
# across every chip in the report. An unknown bank → the neutral chip. Keyed to the bank constant.
BANK_CLASS: dict = {"INVENTORY": "inv", "PRICE": "price", "SPATIAL": "spatial", "VELOCITY": "velocity"}

_GENDER: dict = {"M": "Men's", "F": "Women's"}


def humanize_token(bank: str, word: str) -> str:
    """One signature token → a flat operator phrase. A known ``(bank, word)`` maps through ``REASON_LEXICON``;
    an unknown pair degrades to ``"bank word"`` (lower-cased bank), never dropped and never a crash — the
    geometry may grow a position this lexicon has not learned yet, and it must still render. Pure over the pair."""
    phrase = REASON_LEXICON.get((bank, word))
    if phrase:
        return phrase
    return f"{bank.lower()} {word}".strip()


def bank_class(bank: str) -> str:
    """A bank's chip colour-class token (``"inv"``/``"price"``/``"spatial"``/``"velocity"``), or ``""`` for
    an unknown bank → the neutral chip. Pure over the bank string."""
    return BANK_CLASS.get(bank, "")


def prettify_category(cat: dict | None) -> str:
    """A resolved category dict → a proper-cased display label (``"Women's Sandals"``, ``"Kids' Sneakers"``,
    or just ``"Footwear"`` when only the cluster resolved). Age outranks gender for the prefix (a kids' line is
    named by age, not gender); an unresolved/empty category → ``""``. Pure over the dict — the one place a raw
    taxonomy slug is turned into something an operator would actually write."""
    if not cat:
        return ""
    sub = (cat.get("sub_category") or cat.get("cluster") or "").strip()
    age = (cat.get("age_group") or "").strip()
    gender = (cat.get("gender") or "").strip().upper()
    prefix = (age.capitalize() + "'") if age else _GENDER.get(gender, "")
    if not sub:
        return prefix.rstrip("'")
    return f"{prefix} {sub}".strip()


# The editorial stylesheet. Register moves (SEMIOTICS_OF_COMMUNICATION §5, §10): a humanist system font,
# left-aligned bold headings (magazine register, not centered-science), thin rules, an open frame, a
# monospace metadata footer. "Commercial data" palette: white ground, blue hierarchy with transparency,
# muted pastel bank chips. A single white ground — the corporate-report standard, so the artifact reads
# the same on screen, in print, and pasted into a deck. Tables scroll inside their own container so the
# page body never scrolls sideways on a phone.
CSS = """
:root {
  --bg:#ffffff; --panel:#f4f8fe; --ink:#1f2a44; --mute:#6a7690; --rule:#e4eaf4;
  --accent:#2f6fd6; --accent-soft:rgba(47,111,214,.09); --accent-line:rgba(47,111,214,.55);
  --chip:#eef2f9; --chip-ink:#55617a;
  --inv-bg:#e4edfd;   --inv-ink:#2b5599;   --price-bg:#ebe6f8;  --price-ink:#59489f;
  --spatial-bg:#dbeef1; --spatial-ink:#2b7580; --velocity-bg:#f7ecda; --velocity-ink:#976529;
  --mono:ui-monospace,"SF Mono",Menlo,Monaco,"DejaVu Sans Mono",monospace;
}
* { box-sizing:border-box; }
body {
  margin:0; padding:2.4rem 1.4rem 3rem; background:var(--bg); color:var(--ink);
  font-family:"Avenir Next","Segoe UI",system-ui,-apple-system,"Helvetica Neue",sans-serif;
  font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
main { max-width:60rem; margin:0 auto; }
header.report { border-bottom:2px solid var(--accent-line); padding-bottom:1rem; margin-bottom:1.6rem; }
header.report h1 { font-size:1.55rem; font-weight:700; margin:0 0 .2rem; letter-spacing:-.01em; color:var(--accent); }
header.report .sub { color:var(--mute); font-size:.95rem; }
.summary { display:flex; flex-wrap:wrap; gap:.5rem 1rem; margin:.9rem 0 0; padding:.6rem .9rem;
  background:var(--accent-soft); border-radius:.55rem; font-variant-numeric:tabular-nums; }
.summary b { font-weight:700; color:var(--ink); } .summary span { color:var(--mute); }
h2 { font-size:1.05rem; font-weight:700; text-align:left; margin:2.1rem 0 .4rem;
  padding-bottom:.3rem; border-bottom:1px solid var(--rule); }
h2 .count { color:var(--accent); font-weight:700; font-size:.9rem; }
.run { margin:1rem 0; padding:.85rem 1rem; background:var(--panel); border:1px solid var(--rule);
  border-radius:.6rem; }
.run h3 { font-size:.98rem; font-weight:700; margin:0 0 .4rem; display:flex; flex-wrap:wrap; gap:.5rem;
  align-items:baseline; color:var(--accent); }
.run h3 .leg { color:var(--mute); font-weight:400; font-size:.85rem; font-family:var(--mono); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:.92rem; }
th, td { text-align:left; padding:.34rem .7rem .34rem 0; border-bottom:1px solid var(--rule);
  vertical-align:top; white-space:nowrap; }
th { color:var(--mute); font-weight:600; font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; }
tr:last-child td { border-bottom:none; }
td.qty { font-variant-numeric:tabular-nums; font-weight:700; }
td.why { white-space:normal; }
.chip { display:inline-block; background:var(--chip); color:var(--chip-ink); border-radius:999px;
  padding:.06rem .6rem; margin:0 .28rem .22rem 0; font-size:.8rem; font-weight:500; }
.chip-inv { background:var(--inv-bg); color:var(--inv-ink); }
.chip-price { background:var(--price-bg); color:var(--price-ink); }
.chip-spatial { background:var(--spatial-bg); color:var(--spatial-ink); }
.chip-velocity { background:var(--velocity-bg); color:var(--velocity-ink); }
.mute { color:var(--mute); }
.empty { color:var(--mute); margin:.4rem 0; }
footer { margin-top:2.6rem; padding-top:.8rem; border-top:1px solid var(--rule);
  color:var(--mute); font-family:var(--mono); font-size:.76rem; }
"""
