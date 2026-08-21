"""Guard for the data-input adapter CONTRACT + the end-to-end composition.

The pure decisions are each mutation-pinned in isolation; this file guards the thing isolation cannot — that
the pieces still compose when one feeds another. It asserts the bundled example adapter satisfies the whole
SourceAdapter protocol (so a future adapter that drops a delegated method fails HERE, not at runtime), and
that the full pipeline (grid → taxonomy → routing → noticer → resolve) runs on the synthetic example with no
real data — the fresh-clone guarantee.
"""

from peitho import product, source
from peitho.noticer import notice
from peitho.query.significance import significant_moves
from peitho.resolve import resolve_routing
from peitho.route import plan_transfers_global
from peitho.source import SourceAdapter, adapter, load_grid


def test_example_adapter_satisfies_the_full_protocol():
    a = adapter()
    assert isinstance(a, SourceAdapter)  # structural: all protocol methods present on the adapter module
    missing = [m for m in dir(SourceAdapter) if not m.startswith("_") and not callable(getattr(a, m, None))]
    assert missing == [], f"example adapter is missing delegated methods: {missing}"


def test_full_pipeline_composes_on_the_example_cassette():
    # every chain from the grid through the geometry runs on the procedural synthetic data — no real data, no files
    g = load_grid()
    assert len(list(g.variants())) > 0
    taxo = product.translate_taxonomy(source.adapter().load_taxonomy())
    assert any(t["category"]["status"] == "resolved" for t in taxo.values())  # deconvolution composes
    transfers, _reorders = plan_transfers_global(g, 7.0, floor_units=1)
    _ = significant_moves(transfers, g)  # flow → significance composes without error
    assert notice(g)  # the signed-ternary noticer field is non-empty
    assert resolve_routing(g, regimes={}) is not None  # the resolving layer composes end-to-end
