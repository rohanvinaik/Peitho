"""report.render — the routing shadow-ledger → operator HTML report (pure, given the ledger).

The public renderer. Its reader is a shop operator, and its one job is: **what to move today, from where,
and why**. It consumes the flat `routing.json` shadow-ledger (the projection the node-network geometry
already computed) and turns it into a scannable page — the transfers grouped into physical runs
(source→dest), each move carrying the signed-ternary read that fired it, humanized. Nothing here decides
anything: the decisions were made upstream in the geometry; this is formatting, and it says so.

The structural decisions (`parse_reason`, `group_runs`) are pure over primitives so they pin cleanly; the
company-specific *presentation* (branding, the idiomatic layout) is NOT here — that stays in a private
cassette. `render_report` is pure over `(ledger, brand, title, as_of)`; the file I/O is `report.__init__`.
"""

from __future__ import annotations

from html import escape

from . import style


def parse_reason(reason: str | None) -> list:
    """A signature string (``"INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:accelerating"``) → the list of
    non-abstaining ``(bank, word)`` axes, in order. Neutral (``·``) axes and malformed/blank tokens are
    dropped. Pure over the string; ``None``/``""`` → ``[]``. This is the parse of the geometry's own
    ``noticer.describe`` output — the report never re-derives the read, only reads it back."""
    if not reason:
        return []
    out: list = []
    for tok in reason.split():
        bank, sep, word = tok.partition(":")
        if not sep or not word or word == style.NEUTRAL:
            continue
        out.append((bank, word))
    return out


def humanize_reason(reason: str | None) -> str:
    """A signature string → a flat operator clause (``"low cover, below target, selling fast"``). Empty when
    nothing fired (every axis abstained). Pure — composes ``parse_reason`` with the lexicon."""
    return ", ".join(style.humanize_token(b, w) for b, w in parse_reason(reason))


def group_runs(transfers: list) -> list:
    """Group the transfer list (already ordered source, dest, −qty) into physical **runs** keyed by
    ``(from_store, to_store)`` — the unit an operator actually executes (one trip per run). Each run carries
    its leg cost (the cheapest ``cost_min`` on the leg), total units, variant count, and its moves. Insertion
    order is preserved, so the ledger's sort survives. Pure over the list; ``[]`` → ``[]``."""
    runs: dict = {}
    order: list = []
    for t in transfers:
        key = (t.get("from_store"), t.get("to_store"))
        if key not in runs:
            runs[key] = {
                "from_store": key[0],
                "to_store": key[1],
                "leg_cost": t.get("cost_min"),
                "units": 0,
                "variants": 0,
                "moves": [],
            }
            order.append(key)
        run = runs[key]
        run["units"] += t.get("qty", 0) or 0
        run["variants"] += 1
        run["moves"].append(t)
        cost = t.get("cost_min")
        if cost is not None and (run["leg_cost"] is None or cost < run["leg_cost"]):
            run["leg_cost"] = cost
    return [runs[k] for k in order]


def _variant_label(move: dict) -> str:
    """A move's item as one line: ``"AX-1000 · Black · 42"`` with the resolved category appended when known.
    Pure over the move dict — proper-cases the colour, keeps the article code verbatim (it is the operator's
    own key)."""
    art = escape(str(move.get("article", "")))
    color = escape(str(move.get("color", "") or "").title())
    size = escape(str(move.get("size", "") or ""))
    bits = [b for b in (art, color, size) if b]
    line = " · ".join(bits)
    cat = style.prettify_category(move.get("category"))
    return f"{line} <span class='mute'>{escape(cat)}</span>" if cat else line


def _why_chips(reason: str | None) -> str:
    """The move's read as chips (``<span class=chip>low cover</span>…``), or an em dash when nothing fired.
    Pure over the reason string."""
    axes = parse_reason(reason)
    if not axes:
        return "<span class='mute'>—</span>"
    parts = []
    for b, w in axes:
        cls = style.bank_class(b)
        chip = f"chip chip-{cls}" if cls else "chip"
        parts.append(f"<span class='{chip}'>{escape(style.humanize_token(b, w))}</span>")
    return "".join(parts)


def _run_html(run: dict) -> str:
    """One run section: a source→dest heading with the leg cost + totals, then a table of its moves. Pure."""
    src = escape(str(run.get("from_store", "")))
    dst = escape(str(run.get("to_store", "")))
    cost = run.get("leg_cost")
    leg = f"{cost:g} min" if isinstance(cost, (int, float)) else ""
    head = (
        f"<h3>{src} &rarr; {dst}"
        f"<span class='leg'>{escape(leg)} · {run['units']} units / {run['variants']} variants</span></h3>"
    )
    rows = "".join(
        f"<tr><td>{_variant_label(m)}</td><td class='qty'>{escape(str(m.get('qty', '')))}</td>"
        f"<td class='why'>{_why_chips(m.get('reason'))}</td></tr>"
        for m in run.get("moves", [])
    )
    table = (
        "<div class='scroll'><table><thead><tr><th>Item</th><th>Qty</th><th>Why</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return f"<div class='run'>{head}{table}</div>"


def _reorders_html(reorders: list) -> str:
    """The supplier-reorder section (what to buy) — empty-state aware. Pure over the reorder list."""
    if not reorders:
        return "<p class='empty'>No reorders — the network can cover today's shortfalls from its own spare.</p>"
    rows = "".join(
        f"<tr><td>{escape(str(o.get('article', '')))} "
        f"<span class='mute'>{escape(style.prettify_category(o.get('category')))}</span></td>"
        f"<td class='qty'>{escape(str(o.get('qty', '')))}</td>"
        f"<td>{escape(str(o.get('regime', '') or ''))}</td>"
        f"<td class='why'>{escape(str(o.get('why', '') or ''))}</td></tr>"
        for o in reorders
    )
    return (
        "<div class='scroll'><table><thead><tr><th>Article</th><th>Qty</th><th>Regime</th><th>Why</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def _reasoning_html(reasoning: dict) -> str:
    """The audit surface — how many moves each signed-ternary read drove, humanized. This is where the operator
    checks the machine's logic. Pure over the ``{signature: count}`` map (already ordered most-common first)."""
    if not reasoning:
        return "<p class='empty'>No moves to explain.</p>"
    rows = "".join(
        f"<tr><td class='why'>{_why_chips(sig)}</td><td class='qty'>{escape(str(count))}</td></tr>"
        for sig, count in reasoning.items()
    )
    return (
        "<div class='scroll'><table><thead><tr><th>Read</th><th>Moves</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def render_report(ledger: dict, brand: str = "", title: str = "", as_of: str = "") -> str:
    """The whole operator report as an HTML document string. Pure over ``(ledger, brand, title, as_of)`` — the
    same ledger renders the same bytes, so it pins and diffs cleanly. Structure (SEMIOTICS §8/§20, parallel
    channels): the header + summary strip is the one-second skeleton; the run tables are the proof (a move
    runs or it does not); the read chips are the terse story. No prose makes a claim the ledger has not
    already computed."""
    summary = ledger.get("summary", {}) or {}
    transfers = ledger.get("transfers", []) or []
    reorders = ledger.get("reorders", []) or []
    reasoning = ledger.get("reasoning", {}) or {}
    runs = group_runs(transfers)

    moves = summary.get("moves", len(transfers))
    units = summary.get("units", "")
    n_runs = summary.get("runs", len(runs))
    cover = summary.get("target_cover_days", "")
    n_reord = summary.get("reorders", len(reorders))

    strip = [f"<b>{escape(str(moves))}</b> <span>moves</span>", f"<b>{escape(str(units))}</b> <span>units</span>"]
    strip.append(f"<b>{escape(str(n_runs))}</b> <span>runs</span>")
    if cover != "":
        strip.append(f"<span>cover target</span> <b>{escape(str(cover))}d</b>")
    if n_reord:
        strip.append(f"<b>{escape(str(n_reord))}</b> <span>reorders</span>")

    sub = " · ".join(b for b in (escape(brand), escape(as_of)) if b)
    head = (
        f"<header class='report'><h1>{escape(title) or 'Routing Report'}</h1>"
        f"<div class='sub'>What to move today, from where, and why{(' — ' + sub) if sub else ''}</div>"
        f"<div class='summary'>{''.join(strip)}</div></header>"
    )

    body = [f"<h2>Moves today <span class='count'>{escape(str(moves))}</span></h2>"]
    body.append("".join(_run_html(r) for r in runs) if runs else "<p class='empty'>Nothing to move today.</p>")
    body.append(f"<h2>Reorders <span class='count'>{escape(str(n_reord))}</span></h2>")
    body.append(_reorders_html(reorders))
    body.append("<h2>Why these moves</h2>")
    body.append(_reasoning_html(reasoning))

    footer = (
        f"<footer>{escape(brand or 'Peitho')} · data-geometry routing — a read-out of the stock structure, "
        f"not a model. Every figure traces to the shadow ledger.{(' · ' + escape(as_of)) if as_of else ''}</footer>"
    )
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title) or 'Routing Report'}</title><style>{style.CSS}</style></head>"
        f"<body><main>{head}{''.join(body)}{footer}</main></body></html>"
    )
