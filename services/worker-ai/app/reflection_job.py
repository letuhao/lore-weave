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
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol

from app import safety_floor
from app.clients import KnowledgeUnavailable

logger = logging.getLogger(__name__)


class _FactRecaller(Protocol):
    async def recall_facts_range(
        self, *, user_id: str, book_id: str, date_from: str, date_to: str, limit: int = ...,
        fail_closed: bool = ...,
    ) -> list[dict]: ...


class _DiaryWriter(Protocol):
    async def write_diary_entry(
        self, *, book_id: str, owner_user_id: str, entry_date: str, entry_zone: str,
        body: str, title: str | None, journal_kind: str, language: str,
    ) -> "dict[str, Any] | None": ...


# WS-5.5 — the CLOSED detector enum. The phrasing LLM (later) may only name a pattern whose
# code is in this set; a code outside it is REJECTED (not softened) — enforcement, not a
# prompt. Deterministic detectors emit these codes directly.
DETECTOR_CODES: frozenset[str] = frozenset({"journaling_gap", "co_occurrence", "recurring_theme"})

# WS-5.6 — English stopwords the co-occurrence detector ignores so a "recurring theme" is a
# real content word, not "the"/"and". Small + deterministic (no NLP dependency).
_STOPWORDS: frozenset[str] = frozenset(
    "the a an and or but of to in on at for with my me i we our it that this is was were be been "
    "had has have do did done not no so if then than too very just also more most some any all as "
    "up out day today week work working got get getting felt feel feeling really".split()
)


def validate_detector_code(code: str) -> None:
    """WS-5.5 — raise on a detector_code outside the closed set (the guard the phrasing step
    runs against its LLM output, so a hallucinated pattern name never surfaces)."""
    if code not in DETECTOR_CODES:
        raise ValueError(f"detector_code {code!r} is not in the closed set {sorted(DETECTOR_CODES)}")


@dataclass(frozen=True)
class ReflectionPattern:
    """A surfaced pattern. `evidence_refs` is REQUIRED — a pattern with none is dropped
    before it ever reaches the user (no LLM-invented observations). `pattern_key` is
    PERIOD-INDEPENDENT (WS-5.6): it identifies the SAME pattern across weeks so a dismissal
    tombstones it permanently, not just for the period it was first seen."""

    detector_code: str
    summary: str
    evidence_refs: tuple[str, ...]
    pattern_key: str = ""

    def __post_init__(self):
        validate_detector_code(self.detector_code)  # WS-5.5 — no out-of-enum code ever exists


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
        pattern_key="journaling_gap",  # period-independent (same concept each week)
    )


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", (text or "").lower()) if w not in _STOPWORDS}


def _co_occurrence(notes: list[dict], min_days: int = 2) -> list[ReflectionPattern]:
    """WS-5.2 — a deterministic recurring-theme detector over the week's reflection_notes:
    a content word appearing in went_well/to_improve on ≥ min_days DISTINCT days is a theme.
    Evidence = the concrete dates (no refs ⇒ no pattern). pattern_key is the term so a
    dismissal tombstones that theme across weeks (WS-5.6)."""
    term_days: dict[str, set[str]] = {}
    for n in notes:
        d = (n.get("entry_date") or "")[:10]
        if not d:
            continue
        for term in _tokenize(n.get("went_well", "")) | _tokenize(n.get("to_improve", "")):
            term_days.setdefault(term, set()).add(d)
    out: list[ReflectionPattern] = []
    for term, days in sorted(term_days.items()):
        if len(days) >= min_days:
            out.append(ReflectionPattern(
                detector_code="co_occurrence",
                summary=f"'{term}' recurred in your notes on {len(days)} days this week.",
                evidence_refs=tuple(sorted(days)),
                pattern_key=f"co_occurrence:{term}",
            ))
    return out


async def reflect_week(
    *,
    user_id: str,
    book_id: str,
    week_start: str,
    week_end: str,
    knowledge_client: _FactRecaller,
    away_days: frozenset[str] = frozenset(),
    notes: list[dict] | None = None,
    dismissed_pattern_keys: frozenset[str] = frozenset(),
) -> ReflectionResult:
    """Recall the week → SAFETY-SCREEN (fail-closed short-circuit) → deterministic detectors.
    `notes` = the week's reflection_notes (WS-5.1 substrate) for the co-occurrence detector;
    `dismissed_pattern_keys` = the user's tombstoned pattern_keys, dropped AT DETECTION (WS-5.6)
    so a dismissed pattern never resurfaces as a "new" row each period. Never raises for content
    reasons. P2 (D-REFLECTION-FACTS-RECALL-FAIL-CLOSED): the facts recall is fail-CLOSED
    (`fail_closed=True`) — a transport/non-200 raises `KnowledgeUnavailable` (the facts feed the Gate-3
    safety screen below, so a blip must retry, not write an under-screened reflection). The orchestrator
    turns that into a retryable status; a genuinely empty week still returns []."""
    raw = await knowledge_client.recall_facts_range(
        user_id=user_id, book_id=book_id, date_from=week_start, date_to=week_end,
        fail_closed=True,
    )
    notes = notes or []

    # ── Gate 3 (X-2, SEALED) — the safety FLOOR runs BEFORE any pattern is surfaced. The
    # week's emotional content (facts AND the user's own reflection notes) is screened
    # deterministically; a trip short-circuits fail-closed: no patterns, no draft, a plain
    # acknowledgement instead (WS-5.12). The acknowledgement is NEVER written into the KG.
    combined = "\n".join(
        [str(f.get("content") or "") for f in raw]
        + [f"{n.get('went_well', '')} {n.get('to_improve', '')}" for n in notes]
    )
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
    candidates: list[ReflectionPattern] = []
    gap = _journaling_gap(raw, week_start, week_end, away_days)
    if gap is not None:
        candidates.append(gap)
    candidates.extend(_co_occurrence(notes))

    # ── WS-5.6 — tombstone drop AT DETECTION (before any phrasing LLM), on the
    # PERIOD-INDEPENDENT pattern_key: a dismissed pattern is gone for good, not re-minted
    # as a fresh row next period.
    kept = [p for p in candidates if p.pattern_key not in dismissed_pattern_keys]
    # ── WS-5.14 — clinical/diagnostic deny-list: a pattern whose text uses clinical vocab is
    # DROPPED, not softened (a coach describes, never diagnoses). Applies here + will apply to
    # the LLM phrasing step's output when that lands.
    patterns = [p for p in kept if not safety_floor.contains_clinical_language(p.summary)]
    return ReflectionResult(status="reflected", patterns=patterns)


# WS-5.3 — Socratic scaffolding prompts. DESCRIPTIVE, never a judgement or a score.
_SOCRATIC_PROMPTS = (
    "What felt like your best work this week, and what made it possible?",
    "Where did your time go versus where you wanted it to go?",
    "What's one small thing you'd change about next week?",
)


def render_reflection_draft(result: ReflectionResult) -> str:
    """WS-5.3 — a PULL-only weekly reflection DRAFT (P3-D3). Descriptive, not a score: it
    lays out the week's observed patterns (each with its own evidence) + Socratic prompts for
    the user to reflect against. An EMPTY week (no patterns) is a valid, good output — the
    draft simply invites reflection without inventing findings. On a safety short-circuit it
    returns ONLY the acknowledgement (no patterns, no prompts)."""
    if result.status == "safety_short_circuit":
        return result.acknowledgement or ""
    lines = ["## Weekly reflection", ""]
    if result.patterns:
        lines.append("A few things stood out this week:")
        for p in result.patterns:
            lines.append(f"- {p.summary}")
        lines.append("")
    else:
        lines.append("Nothing specific stood out in the data this week — a calm week is a good week.")
        lines.append("")
    lines.append("Some questions to sit with:")
    lines.extend(f"- {q}" for q in _SOCRATIC_PROMPTS)
    return "\n".join(lines)


async def run_weekly_reflection(
    *,
    user_id: str,
    book_id: str,
    week_start: str,
    week_end: str,
    entry_zone: str,
    language: str,
    knowledge_client: _FactRecaller,
    book_client: _DiaryWriter,
    away_days: frozenset[str] = frozenset(),
    notes: list[dict] | None = None,
    dismissed_pattern_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """D-REFLECTION-WIRE — the live weekly-reflection ORCHESTRATOR (mirrors roll_up_week):
    reflect_week (recall → SAFETY screen → deterministic detectors) → render a descriptive
    draft → write it as a `journal_kind='reflection'` diary entry (get-or-REPLACE per week,
    draft-into-inbox). On a safety short-circuit it writes NOTHING (the acknowledgement is
    FE-surfaced once, never persisted as a KG fact — WS-5.12). Never raises for content reasons.
    Returns {reflected | safety_short_circuit | error}."""
    try:
        result = await reflect_week(
            user_id=user_id, book_id=book_id, week_start=week_start, week_end=week_end,
            knowledge_client=knowledge_client, away_days=away_days,
            notes=notes or [], dismissed_pattern_keys=dismissed_pattern_keys,
        )
    except KnowledgeUnavailable as exc:
        # P2 (D-REFLECTION-FACTS-RECALL-FAIL-CLOSED) — facts recall failed while feeding the fail-closed
        # safety screen; un-ACK for retry (the consumer honours retryable) rather than write a reflection
        # that screened fewer facts. Same fail-closed posture the notes fetch already has.
        logger.warning("weekly-reflection user=%s: facts recall unavailable (%s) — retryable", user_id, exc)
        return {"status": "error", "reason": "facts_recall_unavailable", "retryable": True,
                "week_start": week_start, "week_end": week_end}
    if result.status == "safety_short_circuit":
        logger.info("weekly-reflection short-circuit user=%s category=%s", user_id, result.safety_category)
        return {"status": "safety_short_circuit", "category": result.safety_category,
                "week_start": week_start, "week_end": week_end}

    # An empty week is a VALID output — render_reflection_draft invites reflection without
    # inventing findings, so we always write the (get-or-replace) draft.
    draft = render_reflection_draft(result)
    written = await book_client.write_diary_entry(
        book_id=book_id, owner_user_id=user_id, entry_date=week_end, entry_zone=entry_zone,
        body=draft, title=f"Weekly reflection · {week_start} – {week_end}",
        journal_kind="reflection", language=language,
    )
    if written is None or written.get("error"):
        return {"status": "error", "reason": "write_failed", "retryable": True}
    return {"status": "reflected", "week_start": week_start, "week_end": week_end,
            "patterns": len(result.patterns), "chapter_id": written.get("chapter_id")}
