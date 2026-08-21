"""peitho.config — the single source of truth for filesystem roots.

Kills the hardcoded ``/Users/rohanvinaik/Projects/Peitho`` that had been pasted into ~38 files, which pinned
the whole system to one machine. ``ROOT`` resolves, in order:

  1. ``$PEITHO_ROOT`` if set (deploy/CI override), else
  2. the project root auto-detected by walking up from this file to the dir containing ``pyproject.toml``, else
  3. a structural fallback (``src/peitho/config.py`` → three parents up = project root).

Every landed/derived data path derives from ``ROOT`` so a checkout anywhere — a CI runner, a server, another
laptop — needs no code change. ``ROOT`` is a **str** (not ``Path``) so the existing ``f"{ROOT}/data/…"`` and
``ROOT + "…"`` call sites are drop-in; the ``Path``-typed sub-roots below are for new code.
"""

from __future__ import annotations

import os
from pathlib import Path


def _detect_root() -> Path:
    env = os.environ.get("PEITHO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[2]  # src/peitho/config.py -> peitho -> src -> project root


ROOT: str = str(_detect_root())  # str for drop-in f-string / concat compatibility with existing call sites

# Canonical subtrees — derive paths from these, never re-hardcode ROOT.
DATA = Path(ROOT) / "data"
EXPORT = DATA / "export"
REPORTS = EXPORT / "reports"
RECON = DATA / "recon"
ASSETS = Path(ROOT) / "assets"

# The sanctioned backend access token (a live credential; gitignored). Overridable for deploy.
FRESH_TOKEN = os.environ.get("PEITHO_FRESH_TOKEN", str(RECON / "fresh_token.json"))
