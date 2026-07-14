"""WS-5.2/5.3 (spec 08 §A) — the weekly REFLECTION pipeline.

Reflection is descriptive, not a score (§0): it surfaces the user's OWN patterns with
evidence refs — an empty week is a valid, good output. This is deliberately gated by the
Gate-3 safety FLOOR BEFORE any pattern is surfaced (X-2): the reflection draft carries
emotional content, so a distressed week must short-circuit fail-closed — no patterns, no
draft — and offer a plain acknowledgement instead. The floor gates reflection, not only
the scorer.

Detectors here are DETERMINISTIC and emit candidates WITH evidence refs; a candidate with
no refs is dropped (never an LLM-invented pattern). Only the two detectors that HAVE
substrate today are built: journaling-gap (diary dates) here; co-occurrence lands with the
reflection_notes substrate (WS-5.1).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol

from app import safety_floor

logger = logging.getLogger(__name__)


class _FactRecaller(Protocol):
    async def recall_facts_range(
        self, *, user_id: str, book_id: str, date_from: str, date_to: str, limit: int = ...,
    ) -> list[dict]: ...


@dataclass(frozen=True)
class ReflectionPattern:
    """A surfaced pattern. `evidence_refs` is REQUIRED — a pattern with none is dropped
    before it ever reaches the user (no LLM-invented observations)."""

    detector_code: str
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass
class ReflectionResult:
    status: str  # 'reflected' | 'safety_short_circuit' | 'no_substrate'
    patterns: list[ReflectionPattern] = field(default_factory=list)
    safety_category: str | None = None
    acknowledgement: str | None = None


# Plain, non-clinical, non-judgmental acknowledgements (WS-5.12). Shown once, dismissible,
# NEVER written into the KG as a fact about the user. i18n resolves the real copy; these are
# the fallback English strings + the resource pointer key.
_ACK: dict[str, str] = {
    safety_floor.CAT_SELF_HARM: (
        "It sounds like this has been really heavy lately. You don't have to carry it alone — "
        "if you're thinking about harming yourself, please reach out to a crisis line or someone you trust."
    ),
    safety_floor.CAT_DISTRESS: (
        "This week reads as a genuinely hard one. It's okay to step back and get support — "
        "reflection can wait until things feel steadier."
    ),
    safety_floor.CAT_HARASSMENT_ABUSE: (
        "What you described sounds serious and it is not okay. If you feel unsafe, consider reaching "
        "out to someone you trust or a support service — this isn't something you have to handle alone."
    ),
}


def _acknowledgement(category: str | None) -> str:
    return _ACK.get(category or "", _ACK[safety_floor.CAT_DISTRESS])


def _week_days(week_start: str, week_end: str) -> list[str]:
    d0 = date.fromisoformat(week_start)
    d1 = date.fromisoformat(week_end)
    out, d = [], d0
    while d <= d1:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _fact_day(f: dict) -> str | None:
    raw = f.get("event_date_iso") or f.get("event_date")
    if not raw:
        return None
    return str(raw)[:10]


def _journaling_gap(
    facts: list[dict], week_start: str, week_end: str, away_days: frozenset[str],
) -> ReflectionPattern | None:
    """Deterministic: days in [week_start, week_end] with NO diary fact and NOT declared-away.
    Evidence = the concrete gap dates (no refs ⇒ no pattern). A fully-journaled or fully-away
    week yields nothing — a valid, good output."""
    logged = {d for f in facts if (d := _fact_day(f))}
    gaps = [d for d in _week_days(week_start, week_end) if d not in logged and d not in away_days]
    if not gaps:
        return None
    return ReflectionPattern(
        detector_code="journaling_gap",
        summary=f"{len(gaps)} day(s) this week had no diary entry.",
        evidence_refs=tuple(gaps),  # concrete dates = the evidence
    )


async def reflect_week(
    *,
    user_id: str,
    book_id: str,
    week_start: str,
    week_end: str,
    knowledge_client: _FactRecaller,
    away_days: frozenset[str] = frozenset(),
) -> ReflectionResult:
    """Recall the week → SAFETY-SCREEN (fail-closed short-circuit) → deterministic detectors.
    Never raises for content reasons; a transport failure propagates to the caller's status."""
    raw = await knowledge_client.recall_facts_range(
        user_id=user_id, book_id=book_id, date_from=week_start, date_to=week_end,
    )

    # ── Gate 3 (X-2, SEALED) — the safety FLOOR runs BEFORE any pattern is surfaced.
    # The week's emotional content is screened deterministically; a trip short-circuits
    # fail-closed: no patterns, no draft, a plain acknowledgement instead (WS-5.12). The
    # acknowledgement is NEVER written into the KG as a fact about the user.
    combined = "\n".join(str(f.get("content") or "") for f in raw)
    verdict = safety_floor.screen(combined)
    if verdict.tripped:
        logger.info(
            "reflection short-circuit (safety floor) user=%s category=%s reason=%s",
            user_id, verdict.category, verdict.reason,
        )
        return ReflectionResult(
            status="safety_short_circuit",
            safety_category=verdict.category,
            acknowledgement=_acknowledgement(verdict.category),
        )

    # ── Deterministic detectors (evidence refs; no refs ⇒ dropped) ────────────
    patterns: list[ReflectionPattern] = []
    gap = _journaling_gap(raw, week_start, week_end, away_days)
    if gap is not None:
        patterns.append(gap)
    # co-occurrence detector lands with the reflection_notes substrate (WS-5.1).
    return ReflectionResult(status="reflected", patterns=patterns)
