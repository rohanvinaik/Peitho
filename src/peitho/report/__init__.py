"""report — render + deliver the operator's daily routing report.

The public delivery surface. `build_report` is the thin I/O shell: it refreshes the routing shadow-ledger
(`export.export_routing`), reads it back, renders it through the pure `report.render`, and writes the HTML
where the operator will open it. The company-specific *idiomatic* presentation (a brand's own layout, its
language register) stays in a private cassette; this generic renderer produces a clean, dual-mode report
that fits any retailer plugged into the core.

Run it on the active cassette::

    python -m peitho.report            # → the report HTML on whatever cassette is plugged in

Report generation is the shared core; a real deployment adds thin delivery adapters (email, a mini-site)
around this same rendered artifact — the render is the invariant, the channel is what varies.
"""

from __future__ import annotations

import json
import os

from . import render

__all__ = ["build_report", "render"]


def _default_out() -> str:
    """Where the rendered report lands by default — ``<reports>/routing_report.html`` under the data root.
    Read lazily (not at import) so a cassette/env swap is honoured. I/O-config only."""
    from ..config import REPORTS

    return str(REPORTS / "routing_report.html")


def build_report(
    out_path: str | None = None, ledger_path: str | None = None, refresh: bool = True, as_of: str | None = None
) -> str:
    """Refresh the operational ledger, render its routing section, and write the operator report. Returns
    the written path.

    ``refresh`` regenerates the operational-domain ledger from the active cassette's live grid first (the
    default — a daily report should reflect today); pass ``False`` to render an existing ledger as-is.
    ``as_of`` stamps the report date (defaults to today). Brand + title come from the active cassette's
    manifest, so the same renderer wears any company's name. I/O shell around the pure ``render.render_report``.
    """
    from .. import cassette
    from ..ledgers import OUT_OPERATIONAL, export_operational

    ledger_path = ledger_path or OUT_OPERATIONAL
    if refresh or not os.path.exists(ledger_path):
        export_operational(ledger_path)
    with open(ledger_path, encoding="utf-8") as fh:
        operational = json.load(fh)
    ledger = operational["routing"]  # the report renders the routing section of the operational ledger

    if as_of is None:
        from datetime import date

        as_of = date.today().isoformat()

    cas = cassette.active()
    html = render.render_report(
        ledger, brand=str(cas.field("brand")), title=str(cas.field("report_title")), as_of=as_of
    )

    out_path = out_path or _default_out()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


def main() -> None:
    """CLI entry: build the report on the active cassette and print where it landed."""
    path = build_report()
    print(f"Wrote routing report → {path}")


if __name__ == "__main__":
    main()
