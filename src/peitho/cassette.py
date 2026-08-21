"""peitho.cassette — the pluggable company cassette: the domain plug-in for the agnostic core.

The core (grid, lenses, banks, noticer, route, resolve, digest) carries ZERO company knowledge. Every
domain fact — the node network seeds, the product taxonomy, the data-input adapter, the branding —
lives in a *cassette*: a directory the core loads at runtime. This is the same env-override pattern as
`config.ROOT` (`$PEITHO_ROOT`), applied to the domain instead of the filesystem:

  1. ``$PEITHO_CASSETTE`` if set (the plugged-in company build), else
  2. the bundled ``cassettes/example`` — a synthetic generic retailer, so a fresh checkout runs the
     decision core and a demo with no private data.

A cassette is pure data + a thin adapter::

    cassettes/<name>/
      manifest.toml     # id, brand, currency, locale, adapter module, report title, language register
      network.toml      # node seeds: labels/zones, role overrides, edge-weight source, calibration params
      taxonomy.toml     # clusters + category_relation + gender/age/spelling maps
      adapter/          # a python package: raw backend files -> canonical records (the SourceAdapter)
      branding/         # logo(s), report title
      data/             # example cassette only: a small synthetic dataset

The accessors are lazy (a report that never touches the taxonomy never parses it), and the whole thing
is process-cached behind ``active()`` so one load is shared. ``load_cassette(path)`` builds a fresh,
uncached instance for tests.
"""

from __future__ import annotations

import os
import tomllib
from functools import cached_property, lru_cache
from pathlib import Path

from peitho.config import ROOT  # the DATA root ($PEITHO_ROOT or auto-detected) — used for data_root only


def _repo_root() -> Path:
    """The repository root — where the bundled `cassettes/` live. Resolved from THIS file's location (walk up
    to the pyproject.toml), NOT from $PEITHO_ROOT: PEITHO_ROOT points at the DATA volume, but the bundled
    example cassette ships with the CODE. Conflating them would lose the default cassette whenever the data
    volume is mounted elsewhere."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[2]  # pragma: no cover  (fallback: the shipped tree always has a pyproject.toml above)


DEFAULT_CASSETTE: Path = _repo_root() / "cassettes" / "example"

# Manifest fields the core reads, with agnostic defaults so a minimal manifest still loads.
_MANIFEST_DEFAULTS: dict = {
    "id": "example",
    "brand": "Example Retailer",
    "currency": "USD",
    "locale": "en",
    "language": "en",  # report language register (the core default is English; a cassette may override)
    "report_title": "Inventory Report",
    "adapter": "adapter",  # the python package inside the cassette that implements the SourceAdapter
}


def cassette_source(env_value: str | None) -> str:
    """Named decision: does the active cassette come from the env override or the bundled default?
    ``"ENV"`` when ``$PEITHO_CASSETTE`` is set to a non-blank value, else ``"DEFAULT"``. Pure over the
    raw env string (``None`` or blank/whitespace → default)."""
    return "ENV" if (env_value or "").strip() else "DEFAULT"


def manifest_value(manifest: dict, key: str, defaults: dict | None = None) -> object:
    """The effective value of a manifest field: the cassette's value when present and non-blank, else the
    agnostic default, else the raw key back (for a field the core does not pre-declare). Pure over the
    manifest dict + key — the single place manifest defaulting is decided, so it is pinnable."""
    if defaults is None:
        defaults = _MANIFEST_DEFAULTS
    v = manifest.get(key)
    if isinstance(v, str) and not v.strip():
        v = None
    if v is not None:
        return v
    return defaults.get(key, key)


def resolve_cassette_dir(env_value: str | None, default: Path = DEFAULT_CASSETTE) -> Path:
    """The cassette directory to load — ``$PEITHO_CASSETTE`` (expanded) when set, else the bundled
    default. Returns an unchecked Path so the caller can raise a clear not-found error at load time."""
    if env_value and env_value.strip():  # == cassette_source(env_value) == "ENV"; inlined so the type narrows
        return Path(env_value).expanduser()
    return default


class Cassette:
    """A loaded company cassette. Parses ``manifest.toml`` eagerly (cheap); network/taxonomy/adapter/
    branding load lazily on first access. Never mutates the cassette on disk."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        if not self.path.is_dir():
            raise FileNotFoundError(f"cassette directory not found: {self.path}")
        self.manifest = self._read_toml("manifest.toml")

    def _read_toml(self, name: str) -> dict:
        """Parse a cassette TOML file; a missing optional file is an empty mapping (a cassette need not
        declare every section). I/O + parse only."""
        p = self.path / name
        if not p.exists():
            return {}
        with open(p, "rb") as f:
            return tomllib.load(f)

    def field(self, key: str) -> object:
        """An effective manifest field (cassette value or agnostic default) — see ``manifest_value``."""
        return manifest_value(self.manifest, key)

    @cached_property
    def network(self) -> dict:
        """The node-network seed data (labels/zones, role overrides, edge-weight source, calibration).
        Consumed by ``peitho.network``; empty until a cassette declares ``network.toml``."""
        return self._read_toml("network.toml")

    @cached_property
    def taxonomy(self) -> dict:
        """The product-taxonomy data (clusters, category_relation, gender/age/spelling maps). Consumed by
        ``peitho.product``; empty until a cassette declares ``taxonomy.toml``."""
        return self._read_toml("taxonomy.toml")

    @cached_property
    def data_root(self) -> Path:
        """Where this cassette's landed data lives. A cassette may set ``data_root`` in its manifest
        (relative paths resolve inside the cassette, for the self-contained example); default is the
        shared ``$PEITHO_ROOT/data`` so a company build reads the airgapped data in place."""
        raw = self.manifest.get("data_root")
        if raw:
            p = Path(str(raw)).expanduser()
            return p if p.is_absolute() else (self.path / p)
        return Path(ROOT) / "data"

    @cached_property
    def adapter(self):
        """This cassette's data-input adapter — a module implementing the ``peitho.source.SourceAdapter``
        contract (the ``load_*`` readers that turn the backend's raw files into canonical records). Imported
        by PATH from ``<cassette>/<manifest.adapter>/`` under a unique module name, so two cassettes' adapter
        packages never collide in ``sys.modules``. The public core delegates every raw read here; the
        backend-specific parsing lives only in a company cassette (private)."""
        import importlib.util
        import sys

        name = str(self.field("adapter"))
        init = self.path / name / "__init__.py"
        if not init.exists():
            raise FileNotFoundError(f"cassette adapter package not found: {init}")
        mod_name = f"peitho_cassette_{self.field('id')}_{name}"
        spec = importlib.util.spec_from_file_location(
            mod_name, str(init), submodule_search_locations=[str(self.path / name)]
        )
        if (
            spec is None or spec.loader is None
        ):  # pragma: no cover  (importlib returns a real spec for a valid __init__.py)
            raise ImportError(f"cannot load cassette adapter package: {init}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    def __repr__(self) -> str:
        return f"Cassette(id={self.field('id')!r}, path={self.path})"


def load_cassette(path: Path | str | None = None) -> Cassette:
    """Build a fresh, UNCACHED cassette — from ``path`` if given, else the env-resolved directory. Tests
    point this at a synthetic cassette dir; the app uses ``active()`` for the process-shared instance."""
    if path is None:
        path = resolve_cassette_dir(os.environ.get("PEITHO_CASSETTE"))
    return Cassette(path)


@lru_cache(maxsize=1)
def active() -> Cassette:
    """The process-shared active cassette (env-resolved once). To swap ``$PEITHO_CASSETTE`` in-process, call
    ``reset()`` (NOT ``active.cache_clear()`` alone — the network/taxonomy caches derive from the cassette
    and must be cleared together)."""
    return load_cassette()


_CACHE_CLEARERS: list = []


def register_cache_clearer(clear) -> None:
    """A module whose state is DERIVED from the active cassette (its network, its taxonomy) registers its
    cache-clear callable here. This is dependency INVERSION: the cassette never imports its consumers — they
    register with it — so there is no import cycle, and ``reset()`` can clear everything cassette-derived."""
    if clear not in _CACHE_CLEARERS:
        _CACHE_CLEARERS.append(clear)


def reset() -> None:
    """Clear EVERY cassette-derived cache — the active cassette AND every config mined from it (the node
    network, the taxonomy). Clearing ``active()`` alone leaves those stale, so a mid-process ``$PEITHO_CASSETTE``
    swap must go through here."""
    active.cache_clear()
    for clear in _CACHE_CLEARERS:
        clear()
