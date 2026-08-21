"""Hand-authored INTENT test for peitho.cassette — the pluggable company cassette loader.

Pins, from intent (not characterization): the env-vs-default source decision, manifest-field defaulting,
directory resolution, the lazy TOML accessors, data_root resolution (cassette-relative vs shared root),
and the process-cached active() singleton. A synthetic cassette is written to a tmpdir so the test owns
no real company data.
"""

from __future__ import annotations

import textwrap

import pytest

from peitho import cassette as C


def _write_cassette(root, manifest: str, **files: str):
    """Write a minimal cassette dir (manifest.toml + any named .toml bodies) and return its path."""
    d = root / "cass"
    d.mkdir()
    (d / "manifest.toml").write_text(textwrap.dedent(manifest))
    for name, body in files.items():
        (d / f"{name}.toml").write_text(textwrap.dedent(body))
    return d


def test_cassette_source_env_vs_default():
    assert C.cassette_source(None) == "DEFAULT"
    assert C.cassette_source("") == "DEFAULT"
    assert C.cassette_source("   ") == "DEFAULT"  # blank/whitespace is not a real override
    assert C.cassette_source("/opt/cass") == "ENV"
    assert C.cassette_source(" /opt/cass ") == "ENV"


def test_manifest_value_present_blank_missing_and_unknown_key():
    defaults = {"brand": "Example Retailer", "currency": "USD"}
    # present, non-blank → the cassette's value wins
    assert C.manifest_value({"brand": "Acme"}, "brand", defaults) == "Acme"
    # blank string → treated as absent → the default
    assert C.manifest_value({"brand": "   "}, "brand", defaults) == "Example Retailer"
    # key missing from the manifest → the default
    assert C.manifest_value({}, "currency", defaults) == "USD"
    # a field the core does not pre-declare → the key echoes back (never a silent None)
    assert C.manifest_value({}, "unknown_field", defaults) == "unknown_field"
    # a non-string value (e.g. a number/list) passes through untouched
    assert C.manifest_value({"nodes": 9}, "nodes", defaults) == 9


def test_resolve_cassette_dir_env_overrides_default():
    assert C.resolve_cassette_dir(None) == C.DEFAULT_CASSETTE
    assert C.resolve_cassette_dir("") == C.DEFAULT_CASSETTE
    assert str(C.resolve_cassette_dir("/opt/acme")) == "/opt/acme"


def test_missing_cassette_dir_raises():
    with pytest.raises(FileNotFoundError):
        C.Cassette("/no/such/cassette/dir")


def test_load_cassette_reads_manifest_and_lazy_sections(tmp_path):
    d = _write_cassette(
        tmp_path,
        """
        id = "acme"
        brand = "Acme Footwear"
        adapter = "adapter"
        """,
        taxonomy="""
        clusters = ["Open", "Closed"]
        """,
    )
    cas = C.load_cassette(d)
    assert cas.field("id") == "acme"
    assert cas.field("brand") == "Acme Footwear"
    # an undeclared manifest field falls back to the agnostic default
    assert cas.field("currency") == "USD"
    # lazy sections: taxonomy present, network absent → empty mapping (not an error)
    assert cas.taxonomy == {"clusters": ["Open", "Closed"]}
    assert cas.network == {}


def test_data_root_relative_to_cassette_vs_shared_root(tmp_path):
    # a cassette that ships its own data → data_root resolves INSIDE the cassette dir
    d = _write_cassette(tmp_path, 'id = "x"\ndata_root = "data"\n')
    assert C.load_cassette(d).data_root == d / "data"
    # a cassette with no data_root → the shared $PEITHO_ROOT/data (a company build reads data in place)
    d2 = tmp_path / "cass2"
    d2.mkdir()
    (d2 / "manifest.toml").write_text('id = "y"\n')
    assert C.load_cassette(d2).data_root.name == "data"
    assert C.load_cassette(d2).data_root != d / "data"


def test_active_is_cached_and_env_resolved(tmp_path, monkeypatch):
    d = _write_cassette(tmp_path, 'id = "envcass"\n')
    monkeypatch.setenv("PEITHO_CASSETTE", str(d))
    C.active.cache_clear()
    first = C.active()
    assert first.field("id") == "envcass"
    assert C.active() is first  # process-cached: same instance
    C.active.cache_clear()


def test_bundled_example_cassette_loads():
    """The shipped default cassette parses and declares the fields the core reads."""
    ex = C.load_cassette(C.DEFAULT_CASSETTE)
    assert ex.field("id") == "example"
    assert ex.field("adapter")  # non-empty adapter package name
    assert ex.data_root == C.DEFAULT_CASSETTE / "data"


def test_reset_couples_the_network_and_taxonomy_caches(tmp_path, monkeypatch):
    """reset() must clear the network/taxonomy caches too — clearing active() alone leaves them stale
    (they derive from the cassette). Swapping $PEITHO_CASSETTE + reset() flips the induced network."""
    from peitho import network

    d = _write_cassette(
        tmp_path,
        'id = "swap"\n',
        network='nodes = ["Z1", "Z2"]\n[roles]\nZ1 = ["WAREHOUSE"]\nZ2 = ["SELL"]\n',
    )
    C.reset()  # baseline: whatever the env resolves to (the bundled example by default)
    base_nodes = network.active_network().nodes
    monkeypatch.setenv("PEITHO_CASSETTE", str(d))
    C.reset()  # swap + coordinated clear
    assert network.active_network().nodes == ("Z1", "Z2")  # the network cache followed the swap
    assert network.active_network().nodes != base_nodes
    monkeypatch.undo()  # restore $PEITHO_CASSETTE first, then rebuild the caches for the rest of the suite
    C.reset()
