"""WS-5.24 — coaching trends are gated on the numeric eval + date-windowed.

The load-bearing test is `test_trend_unavailable_until_gate_clears`: quarantine scores must
NEVER be trended (SD-7). A code-run GateStatus is always cleared=False, so trends are off.
"""
from __future__ import annotations

from datetime import date

from app.services.coaching_eval import GateStatus
from app.services.coaching_longitudinal import compute_trend

_NOT_CLEARED = GateStatus(False, "no_human_labels")
_CLEARED = GateStatus(True, "cleared")  # synthetic — a human milestone would produce this


def _scores():
    return [
        {"date": "2026-05-01", "score": 3},
        {"date": "2026-06-01", "score": 4},
        {"date": "2026-07-01", "score": 5},
    ]


def test_trend_unavailable_until_gate_clears():
    r = compute_trend(_scores(), gate=_NOT_CLEARED, today=date(2026, 7, 15))
    assert r.available is False
    assert r.reason == "quarantine_gate_not_cleared"
    assert r.points == []  # nothing trended while quarantined


def test_trend_available_and_directional_when_gate_cleared():
    r = compute_trend(_scores(), gate=_CLEARED, window_days=120, today=date(2026, 7, 15))
    assert r.available is True
    assert r.direction == "up"  # 3 → 5
    assert [p["date"] for p in r.points] == ["2026-05-01", "2026-06-01", "2026-07-01"]


def test_trend_is_date_windowed():
    r = compute_trend(_scores(), gate=_CLEARED, window_days=20, today=date(2026, 7, 15))
    # cutoff = 2026-06-25 → only 2026-07-01 survives the window (05-01 + 06-01 excluded)
    assert [p["date"] for p in r.points] == ["2026-07-01"]
    assert r.reason == "insufficient_points"  # <2 points in-window


def test_non_numeric_scores_ignored_for_direction():
    scores = [{"date": "2026-07-01", "score": None}, {"date": "2026-07-05", "score": 4}]
    r = compute_trend(scores, gate=_CLEARED, window_days=90, today=date(2026, 7, 15))
    assert r.available is True and r.reason == "insufficient_points"  # only 1 numeric point
