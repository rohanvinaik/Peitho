"""query — the pull NL surface: NL request -> typed query plan -> execution (DESIGN.md §5, §7).

The seam is `GSE.resolve -> ModelAtlas.navigate -> execution`. Execution reads the local
node-network encodings (`peitho.lenses`) for the interpretive/geometry part, and calls the backend's
exposed endpoints for the exact figures a report quotes (the source of record) — there is no local
SQL warehouse (see DESIGN.md §3, THEORY.md Storage). Parameters bind from GSE's resolved typed
fields, never string-interpolated from raw message text (injection closed by construction).

Deferred until access lands; the retail axes/vocabulary are designed from real data, not guessed.
"""
