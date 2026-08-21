"""store — the immutable local landing zone + provenance ledger (DESIGN.md §3, §6).

Holds: the immutable raw snapshot archive (Parquet/JSONL, one file per pull, never edited) and the
provenance/shadow ledger (endpoint+params, ts, row count, payload hash, high-water cursor). This is
NOT a SQL/query engine — there is no local DuckDB. The authoritative query engine is the backend's own
SQL, reached on demand through its exposed endpoints (the source of record).

The intelligence substrate — the redundant node-network encodings built over this landing — lives
in `peitho.lenses`. The landing survives because mutable state (stock/price/cost) is overwritten
remotely and un-snapshotted history is unrecoverable (§3.3); the encodings are rebuilt from it.

Nothing here can be designed until real payload shapes are seen (DESIGN.md §13, Gate 0).
No local SQL — see DESIGN.md §3 and THEORY.md (Storage).
"""
