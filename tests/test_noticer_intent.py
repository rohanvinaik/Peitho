"""Hand-authored INTENT test for peitho.noticer — the anomaly field, from intent not output.

Pins the go-wide ruling (ANY anomaly, not just restock-shaped) + Pattern 6a asymmetric emission:
a cell is surfaced iff at least one bank has an opinion (its signature is non-zero); an all-orthogonal
cell is silent and dropped; each distinct signature is its own anomaly class, and the non-restock classes
are kept as surfaces, not filtered away. Signatures are 4-tuples in DIMS order (INVENTORY, PRICE, SPATIAL,
VELOCITY) since VELOCITY joined as the fourth orthogonal dimension.
"""

from peitho.grid import Cell, Grid
from peitho.noticer import (
    DIMS,
    FLAGGED,
    INVENTORY,
    PRICE,
    SILENT,
    SPATIAL,
    VELOCITY,
    Anomaly,
    axis_word,
    class_distribution,
    describe,
    emission,
    notice,
)


def test_emission_flags_any_off_norm_axis_and_drops_the_silent_cell():
    assert emission((0, 0, 0, 0)) == SILENT  # every bank abstains → not an anomaly → dropped
    assert emission((-1, 0, 0, 0)) == FLAGGED  # a single deficit is enough — go wide
    assert emission((0, 0, 0, 1)) == FLAGGED  # a velocity-only opinion (accelerating) still surfaces
    assert emission((0, 0, -1, 0)) == FLAGGED  # spatial-only opinion still surfaces
    assert emission((1, -1, 1, -1)) == FLAGGED  # a mixed signature is one class, not averaged away


def test_axis_word_is_the_literal_sign_meaning_not_a_score():
    assert axis_word(INVENTORY, -1) == "deficit"
    assert axis_word(INVENTORY, 1) == "surplus"
    assert axis_word(PRICE, 1) == "marked-down"
    assert axis_word(SPATIAL, -1) == "short"
    assert axis_word(VELOCITY, 1) == "accelerating"
    assert axis_word(VELOCITY, -1) == "fading"
    assert axis_word(SPATIAL, 0) == "·"  # the informational zero renders as abstention


def test_describe_labels_a_class_mechanically_in_signature_order():
    # a hard reorder: short of cover, at the markdown norm, unroutable, still selling briskly
    assert describe((-1, 0, -1, 1)) == "INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:accelerating"
    # clearable dead stock — the archetypal NON-restock surface we keep on purpose
    assert describe((1, 1, 1, -1)) == "INVENTORY:surplus PRICE:marked-down SPATIAL:spare VELOCITY:fading"


def _cell(store, stock, sale_qty, nrv=1000.0, discount_amount=0.0):
    return Cell(
        store=store,
        stock=stock,
        sale_qty=sale_qty,
        recent_sales=sale_qty,
        nrv=nrv,
        discount_amount=discount_amount,
        sls_age=(sale_qty, 0, 0, 0, 0),
    )


def test_notice_surfaces_off_norm_cells_over_a_tiny_grid_and_drops_silent():
    # Two stores, one variant. N8 is stocked out and selling (deficit); N5 is well stocked and selling.
    grid = Grid(
        {
            ("ART1", "BLK", "M"): {
                "N8": _cell("N8", stock=0, sale_qty=40),
                "N5": _cell("N5", stock=400, sale_qty=40),
            }
        }
    )
    flagged = notice(grid)
    stores = {a.store for a in flagged}
    # the stocked-out selling cell MUST surface (a real anomaly on inventory/spatial)
    assert "N8" in stores
    # every surfaced item is a real Anomaly whose signature is its positions in DIMS order (all four banks)
    for a in flagged:
        assert isinstance(a, Anomaly)
        assert a.signature == tuple(a.positions[d].sign for d in DIMS)
        assert len(a.signature) == 4
        assert emission(a.signature) == FLAGGED


def test_class_distribution_is_the_natural_taxonomy_most_common_first():
    a = Anomaly("v1", "N8", (-1, 0, -1, 1), describe((-1, 0, -1, 1)), {})
    b = Anomaly("v2", "N5", (-1, 0, -1, 1), describe((-1, 0, -1, 1)), {})
    c = Anomaly("v3", "N4", (1, 1, 1, -1), describe((1, 1, 1, -1)), {})
    dist = class_distribution([a, b, c])
    # two classes, the (-1,0,-1,1) reorder class first (count 2), the clearance class second (count 1)
    assert dist[0][0] == (-1, 0, -1, 1) and dist[0][2] == 2
    assert dist[1][0] == (1, 1, 1, -1) and dist[1][2] == 1
    assert dist[0][1] == "INVENTORY:deficit PRICE:· SPATIAL:short VELOCITY:accelerating"
