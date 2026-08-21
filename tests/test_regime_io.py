"""Tests for peitho.query.regime's orchestration + CLI shell.

The per-FY history loaders (fy_dirs / load_fy_articles / load_photo_hash) now live in the cassette's private
data-input adapter; their file parsing is exercised end-to-end by the behavior oracle. The pure regime
decisions (regime / article_fy_counts / classify) are Detective-pinned in test_regime_intent. Here we pin the
COMPOSITION — that article_regimes wires the loaders into classify — and the CLI report, both by stubbing the
loaders so the chain runs off toy data with no file I/O.
"""

from peitho.query import regime


def test_article_regimes_composes_loaders_and_classify(monkeypatch):
    # A present across all 3 FYs -> BASE; B in one window -> SEASONAL. No photo identity -> article identity.
    monkeypatch.setattr(
        regime,
        "load_fy_articles",
        lambda *a, **k: {"2023-2024": ["A"], "2024-2025": ["A"], "2025-2026": ["A", "B"]},
    )
    monkeypatch.setattr(regime, "load_photo_hash", lambda *a, **k: {})
    labels = regime.article_regimes()
    assert labels["A"] == regime.BASE  # present across all 3 FYs
    assert labels["B"] == regime.SEASONAL  # one FY only


def test_report_prints_the_split(capsys, monkeypatch):
    monkeypatch.setattr(
        regime, "load_fy_articles", lambda *a, **k: {"2023-2024": ["A"], "2024-2025": ["A"], "2025-2026": ["A", "B"]}
    )
    monkeypatch.setattr(regime, "article_regimes", lambda *a, **k: {"A": regime.BASE, "B": regime.SEASONAL})
    regime.report()
    out = capsys.readouterr().out
    assert "FYs on record: 3" in out and "BASE" in out and "SEASONAL" in out


def test_report_handles_empty_history(capsys, monkeypatch):
    monkeypatch.setattr(regime, "load_fy_articles", lambda *a, **k: {})
    regime.report()
    assert "no multi-year history landed" in capsys.readouterr().out
