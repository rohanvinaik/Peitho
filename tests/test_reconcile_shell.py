"""INTEGRATION tests for the reconcile back-run I/O shells — the ``export_*`` persisting wrappers, the gate
calibrator, and the CLI ``report()``. Writes two dated daily snapshots the active (example) adapter reads,
runs each shell end-to-end, and asserts the written artifact + its summary shape. The pure reconstruction /
conservation classifier is pinned in test_reconcile_intent; this covers the file-writing orchestrators.
"""

import json
import os
import sys

import peitho.reconcile as reconcile


def _write_full(root, date, records):
    from peitho.source import adapter

    d = adapter().daily_grid_dir(date, root)
    os.makedirs(d, exist_ok=True)
    for st, rows in records.items():
        recs = [
            {"article": a, "color": c, "size": s, "stock": k, "sale": q, "recent30": r30}
            for (a, c, s, k, q, r30) in rows
        ]
        with open(f"{d}/{st}.json", "w") as fh:
            json.dump({"rows": recs}, fh)


def _two_days(root):
    # a fast mover selling at N1, spare at the warehouse — a real interval for the back-run to reconstruct
    _write_full(root, "2026-02-01", {"N1": [("X", "RED", "40", 0, 5, 5)], "WH": [("X", "RED", "40", 10, 0, 0)]})
    _write_full(root, "2026-02-04", {"N1": [("X", "RED", "40", 0, 8, 5)], "WH": [("X", "RED", "40", 10, 0, 0)]})


def test_export_outcome_profile_writes_the_gap_coverage_json(tmp_path):
    _two_days(str(tmp_path))
    out = tmp_path / "outcome.json"
    prof = reconcile.export_outcome_profile("2026-02-01", "2026-02-04", str(out), root=str(tmp_path))
    assert out.exists() and "moves" in prof
    assert json.loads(out.read_text())["moves"] == prof["moves"]  # persisted == returned


def test_export_stock_management_writes_the_movement_statement(tmp_path):
    _two_days(str(tmp_path))
    out = tmp_path / "sm.json"
    sm = reconcile.export_stock_management("2026-02-01", "2026-02-04", str(out), root=str(tmp_path))
    assert out.exists() and sm["stores"] and {"begin", "end", "stores"} <= set(sm)


def test_export_validation_calibrates_the_gate_and_writes(tmp_path):
    _two_days(str(tmp_path))
    out = tmp_path / "val.json"
    summary = reconcile.export_validation("2026-02-01", "2026-02-04", str(out), root=str(tmp_path))
    assert out.exists() and {"gate", "dir_agree", "sell"} <= set(summary)


def test_export_reconciliation_writes_the_actual_moves_flattened(tmp_path):
    _two_days(str(tmp_path))
    out = tmp_path / "rec.json"
    counts = reconcile.export_reconciliation("2026-02-01", "2026-02-04", str(out), root=str(tmp_path))
    assert out.exists() and {"transfer", "supplier", "return"} <= set(counts)
    doc = json.loads(out.read_text())
    assert all("|" in k for k in doc["moves"])  # variant tuples flattened to article|color|size for JSON


def test_calibrate_gate_returns_a_velocity_from_the_swept_ladder():
    from peitho.source import load_grid

    mv = reconcile.calibrate_gate(load_grid(), target_units=5.0)  # procedural example grid
    assert mv in (0.05, 0.03, 0.02, 0.014, 0.01, 0.007, 0.005, 0.003, 0.001)


def test_cli_report_prints_the_reconstruction(capsys, monkeypatch):
    monkeypatch.setattr(
        reconcile,
        "reconstruct",
        lambda begin, end: {
            "counts": {"transfer": 1, "supplier": 1, "return": 0},
            "units": {"transfer": 2, "supplier": 5, "return": 0},
            "store_net": {"N1": 2, "N3": -2},
        },
    )
    monkeypatch.setattr(sys, "argv", ["prog", "2026-02-01", "2026-02-04"])
    reconcile.report()
    out = capsys.readouterr().out
    assert "TRANSFERS" in out and "N1" in out and "N3" in out  # header + per-store net printed
