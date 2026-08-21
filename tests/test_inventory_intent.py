"""Hand-authored INTENT test for peitho.lenses.inventory — the per-(store, section) baseline aggregation
and the sales-age velocity SPECTRUM (band_rates / velocity_by_horizon / recent_velocity)."""

from peitho.grid import Cell, Grid
from peitho.lenses.inventory import (
    band_rates,
    mine_category_baselines,
    recent_velocity,
    velocity,
    velocity_by_horizon,
)


def test_mine_category_baselines_groups_by_store_and_section():
    # two articles in one store, different sections, different velocity -> distinct category baselines
    grid = Grid(
        {
            ("A1", "BLK", "40"): {"N8": Cell("N8", stock=10, sale_qty=10, recent_sales=1, nrv=100.0)},
            ("A2", "BLK", "40"): {"N8": Cell("N8", stock=20, sale_qty=5, recent_sales=1, nrv=100.0)},
        }
    )
    sections = {"A1": "MENS", "A2": "WOMENS"}
    bl = mine_category_baselines(grid, sections, window_days=137)
    assert bl[("N8", "MENS")] == 137.0  # demand-weighted cover = 137 * 10/10
    assert bl[("N8", "WOMENS")] == 548.0  # 137 * 20/5
    # an article absent from the taxonomy falls into section '?'
    g2 = Grid({("A3", "BLK", "40"): {"N8": Cell("N8", stock=5, sale_qty=5, recent_sales=1, nrv=100.0)}})
    assert ("N8", "?") in mine_category_baselines(g2, {}, window_days=137)


# --- the velocity SPECTRUM: the whole reason it exists is to separate a fresh mover from a fader ---


def test_recent_velocity_ranks_fresh_mover_above_fader_of_equal_total():
    """THE imputed rationale: 3 units sold recently must outrank 3 units sold >120 days ago — a flat window
    average scores them identically (both 3/137). The fresh mover clears a sane gate; the fader does not."""
    fresh = recent_velocity((3, 0, 0, 0, 0), window_days=137)  # all mass in the <=30 band
    fader = recent_velocity((0, 0, 0, 0, 3), window_days=137)  # all mass in the >=121 tail
    assert fresh > fader
    # flat velocity is blind to the difference — both spectra total 3 units, so both collapse to the same rate
    assert velocity(sum((3, 0, 0, 0, 0)), 137) == velocity(sum((0, 0, 0, 0, 3)), 137)
    # and the gap straddles a reasonable gate: fresh in, fader out
    assert fresh >= 0.03 > fader


def test_recent_velocity_zero_weights_is_zero_not_crash():
    assert recent_velocity((3, 1, 0, 0, 0), weights=(0, 0, 0, 0, 0), window_days=137) == 0.0


def test_velocity_by_horizon_widest_horizon_equals_flat_window_velocity():
    """The ladder's widest rung is exactly the old signal — the spectrum GENERALISES velocity, never
    contradicts it. And the 30d rung is pure recent momentum."""
    sa = (1, 2, 3, 4, 5)
    spec = velocity_by_horizon(sa, window_days=137)
    assert spec[137] == velocity(sum(sa), 137)  # widest == flat velocity over the total
    assert spec[30] == 1 / 30  # recent momentum = band-0 units / 30d


def test_band_rates_localises_mass_to_its_age_band():
    assert band_rates((3, 0, 0, 0, 0), window_days=137)[0] == 3 / 30  # recent band
    assert band_rates((0, 0, 0, 0, 3), window_days=137)[4] == 3 / 17  # >=121 tail over (137-120)
