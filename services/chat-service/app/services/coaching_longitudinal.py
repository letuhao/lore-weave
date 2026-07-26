"""WS-5.24 (spec 08 §C) — coaching longitudinal trends.

Trends are the LAST thing to light up, and ONLY after the numeric eval gate clears (a
human-rating milestone — SD-7). Until then every score is quarantine-tier (WS-5.22) and MUST
NOT be trended: a trend line over unvalidated scores manufactures false confidence. So this
helper is gated on `evaluate_gate(...).cleared` — which is False in any code run — and returns
`available=False` with the reason. Every longitudinal read is DATE-WINDOWED (WS-5.24: the
facts store is sized for a novel, not 3 years of work facts; an unbounded scan is a footgun).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

from app.services.coaching_eval import GateStatus


@dataclass(frozen=True)
class TrendResult:
    available: bool
    reason: str
    points: list[dict]           # [{date, score}] within the window (empty when unavailable)
    direction: str | None = None  # 'up' | 'down' | 'flat' when available


def _window(scores: list[dict], window_days: int, today: date) -> list[dict]:
    """Date-window the scores to [today - window_days, today] (WS-5.24 — never unbounded)."""
    cutoff = today - timedelta(days=max(1, window_days))
    out = []
    for s in scores:
        raw = (s.get("date") or "")[:10]
        try:
            d = date.fromisoformat(raw)
        except (ValueError, TypeError):
            continue
        if cutoff <= d <= today:
            out.append({"date": d.isoformat(), "score": s.get("score")})
    return sorted(out, key=lambda p: p["date"])


def compute_trend(
    scores: list[dict], *, gate: GateStatus, window_days: int = 90, today: date,
) -> TrendResult:
    """Return a trend ONLY when the numeric gate is CLEARED; otherwise `available=False`
    (quarantine — shown, never trended). Even when available, the window bounds the read."""
    if not gate.cleared:
        return TrendResult(False, "quarantine_gate_not_cleared", [])
    pts = _window(scores, window_days, today)
    numeric = [p for p in pts if isinstance(p["score"], (int, float)) and not isinstance(p["score"], bool)]
    if len(numeric) < 2:
        return TrendResult(True, "insufficient_points", pts)
    first, last = mean([numeric[0]["score"]]), mean([numeric[-1]["score"]])
    direction = "up" if last > first else "down" if last < first else "flat"
    return TrendResult(True, "ok", pts, direction=direction)
