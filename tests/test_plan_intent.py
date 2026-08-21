"""Hand-authored INTENT test for peitho.query.plan — the sense→plan→act composition (CONTROL_ARCHITECTURE.md).
Pins that build_plan composes every controller stage into one Plan: internal transfers (the flow), dead-stock
pull-backs (R1/R2), regime-gated base-stock supplier orders, and the pre-clear scaffold (dark without a
calendar, live with a sale date).
"""

import datetime

from peitho.grid import Cell, Grid
from peitho.query.plan import Plan, build_plan


def test_build_plan_composes_every_stage():
    grid = Grid(
        {
            ("SHORT", "RED", "40"): {
                "N1": Cell(
                    "N1", stock=0, sale_qty=100, recent_sales=100, nrv=1.0, sls_age=(100, 0, 0, 0, 0)
                ),  # SELL, short, hot recent
                "N4": Cell("N4", stock=5, sale_qty=0, recent_sales=0, nrv=0.0),  # small spare
            },
            ("DEAD", "BLUE", "41"): {"N5": Cell("N5", stock=3, sale_qty=0, recent_sales=0, nrv=0.0)},  # idle
        }
    )
    regimes = {"SHORT": "BASE", "DEAD": "BASE"}
    plan = build_plan(grid, regimes, min_cost={("N4", "N1"): 5})
    assert isinstance(plan, Plan)
    assert len(plan.transfers) >= 1  # N4 -> N1 internal move (the flow)
    assert any(a.rule == "R1" for a in plan.dead_stock)  # N5 idle -> pull to triage
    assert any(o.article == "SHORT" for o in plan.reorders)  # SHORT below base-stock -> supplier order
    assert plan.preclears == []  # no clearance calendar -> dark


def test_build_plan_preclears_when_a_sale_date_is_given():
    grid = Grid({("A", "RED", "40"): {"N4": Cell("N4", stock=5, sale_qty=100, recent_sales=10, nrv=1.0)}})
    plan = build_plan(
        grid,
        {"A": "BASE"},
        min_cost={},
        sale_date=datetime.date(2026, 8, 23),
        today=datetime.date(2026, 8, 18),  # 5 days out -> within horizon
        baselines={"N4": 0.1},
    )
    assert len(plan.preclears) == 1 and plan.preclears[0].rule == "R6"


def test_report_runs(capsys, monkeypatch):
    import peitho.query.plan as planmod

    grid = Grid({("A", "RED", "40"): {"N1": Cell("N1", stock=3, sale_qty=0, recent_sales=0, nrv=0.0)}})
    monkeypatch.setattr(planmod, "load_grid", lambda *a, **k: grid)
    monkeypatch.setattr(planmod, "article_regimes", lambda *a, **k: {"A": "BASE"})
    planmod.report()
    out = capsys.readouterr().out
    assert "Controller plan" in out and "transfers" in out and "preclears" in out
