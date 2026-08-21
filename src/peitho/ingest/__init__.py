"""Ingest — the SWKE port: Enumerate -> Pull -> Store (the Structure/LLM stage is DELETED).

The backend is a single authoritative structured source, so there is no parser stage and no
hallucination surface (DESIGN.md §4.1). Everything here stays strictly read-only (§9).
"""
