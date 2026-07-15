"""WS-5.2/5.3 — the weekly reflection pipeline, with the Gate-3 safety short-circuit.

The load-bearing test is `test_distress_week_short_circuits`: a week whose diary content
trips the safety floor yields NO patterns and NO draft — only a plain acknowledgement — and
that acknowledgement is never returned as a KG fact.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import pytest as _pytest

from app.reflection_job import (
    DETECTOR_CODES, ReflectionPattern, ReflectionResult,
    reflect_week, render_reflection_draft, validate_detector_code,
)


class _Recaller:
    def __init__(self, facts):
        self.recall_facts_range = AsyncMock(return_value=facts)


def _fact(content, day):
    return {"content": content, "event_date": day}


@pytest.mark.asyncio
async def test_distress_week_short_circuits():
    facts = [
        _fact("Shipped the auth module.", "2026-07-06"),
        _fact("I don't know how much longer I can do this.", "2026-07-08"),  # no keyword — pattern trips
    ]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        knowledge_client=_Recaller(facts),
    )
    assert res.status == "safety_short_circuit"
    assert res.safety_category == "distress"
    assert res.acknowledgement and "support" in res.acknowledgement.lower()
    assert res.patterns == []  # NO pattern surfacing past the floor


@pytest.mark.asyncio
async def test_clean_week_surfaces_journaling_gap_with_evidence():
    facts = [_fact("Shipped auth.", "2026-07-06"), _fact("Fixed bugs.", "2026-07-07")]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        knowledge_client=_Recaller(facts),
    )
    assert res.status == "reflected"
    gap = next(p for p in res.patterns if p.detector_code == "journaling_gap")
    # Mon+Tue logged → Wed..Sun (5) are gaps; evidence = the concrete dates
    assert set(gap.evidence_refs) == {"2026-07-08", "2026-07-09", "2026-07-10", "2026-07-11", "2026-07-12"}
    assert gap.evidence_refs, "a pattern with no evidence refs must never be surfaced"


@pytest.mark.asyncio
async def test_away_days_excluded_from_gap():
    facts = [_fact("Shipped auth.", "2026-07-06")]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-08",
        knowledge_client=_Recaller(facts),
        away_days=frozenset({"2026-07-07", "2026-07-08"}),  # declared away → not a gap
    )
    assert res.status == "reflected"
    assert res.patterns == []  # every non-away day logged


@pytest.mark.asyncio
async def test_fully_journaled_week_is_a_valid_empty_result():
    facts = [_fact(f"day {d}", f"2026-07-{d:02d}") for d in range(6, 13)]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        knowledge_client=_Recaller(facts),
    )
    assert res.status == "reflected"
    assert res.patterns == []  # nothing to surface is a good output, not a failure


@pytest.mark.asyncio
async def test_self_harm_category_gets_its_acknowledgement():
    facts = [_fact("honestly I want to die most days", "2026-07-06")]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        knowledge_client=_Recaller(facts),
    )
    assert res.status == "safety_short_circuit"
    assert res.safety_category == "self_harm"
    assert "crisis" in res.acknowledgement.lower() or "trust" in res.acknowledgement.lower()


# ── WS-5.2 co-occurrence · WS-5.5 closed-enum guard · WS-5.6 tombstone ────────
def _note(day, well="", improve=""):
    return {"entry_date": day, "went_well": well, "to_improve": improve}


@pytest.mark.asyncio
async def test_co_occurrence_surfaces_recurring_theme_with_date_evidence():
    facts = [_fact(f"day {d}", f"2026-07-{d:02d}") for d in range(6, 13)]  # fully journaled → no gap
    notes = [
        _note("2026-07-06", improve="too many meetings broke my focus"),
        _note("2026-07-08", improve="meetings again ate the morning"),
        _note("2026-07-10", well="finally protected focus, no meetings"),
    ]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        knowledge_client=_Recaller(facts), notes=notes,
    )
    keys = {p.pattern_key for p in res.patterns}
    assert "co_occurrence:meetings" in keys  # 3 days
    theme = next(p for p in res.patterns if p.pattern_key == "co_occurrence:meetings")
    assert set(theme.evidence_refs) == {"2026-07-06", "2026-07-08", "2026-07-10"}
    assert "the" not in keys and "co_occurrence:the" not in keys  # stopwords ignored


@pytest.mark.asyncio
async def test_dismissed_pattern_is_dropped_at_detection():
    facts = [_fact(f"day {d}", f"2026-07-{d:02d}") for d in range(6, 13)]
    notes = [_note("2026-07-06", improve="meetings"), _note("2026-07-08", improve="meetings")]
    res = await reflect_week(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        knowledge_client=_Recaller(facts), notes=notes,
        dismissed_pattern_keys=frozenset({"co_occurrence:meetings"}),  # user tombstoned it
    )
    assert all(p.pattern_key != "co_occurrence:meetings" for p in res.patterns)  # never resurfaces


def test_reflection_draft_is_descriptive_with_patterns_and_prompts():
    res = ReflectionResult(status="reflected", patterns=[
        ReflectionPattern("journaling_gap", "2 day(s) had no diary entry.", ("2026-07-08", "2026-07-09"), "journaling_gap"),
    ])
    draft = render_reflection_draft(res)
    assert "no diary entry" in draft            # the pattern is described
    assert "questions to sit with" in draft.lower()  # Socratic prompts present
    assert "score" not in draft.lower()         # descriptive, never a score


def test_empty_week_draft_is_valid_and_invites_reflection():
    draft = render_reflection_draft(ReflectionResult(status="reflected", patterns=[]))
    assert "calm week" in draft.lower()          # empty = good output, not a failure
    assert "questions to sit with" in draft.lower()


def test_short_circuit_draft_is_only_the_acknowledgement():
    res = ReflectionResult(status="safety_short_circuit", safety_category="distress", acknowledgement="take care of yourself")
    draft = render_reflection_draft(res)
    assert draft == "take care of yourself"      # no patterns, no prompts past the floor


def test_closed_enum_guard_rejects_unknown_detector_code():
    assert "journaling_gap" in DETECTOR_CODES
    with _pytest.raises(ValueError):
        validate_detector_code("hallucinated_pattern")
    with _pytest.raises(ValueError):
        ReflectionPattern(detector_code="not_a_code", summary="x", evidence_refs=("d",))  # __post_init__ guards


# ── D-REFLECTION-WIRE — the live orchestrator writes a 'reflection' entry / short-circuits ──
class _FakeBook:
    def __init__(self):
        self.writes = []
    async def write_diary_entry(self, **kw):
        self.writes.append(kw)
        return {"chapter_id": "refl-1"}


from app.reflection_job import run_weekly_reflection  # noqa: E402


@pytest.mark.asyncio
async def test_run_weekly_reflection_writes_a_reflection_draft():
    facts = [_fact("Shipped auth.", "2026-07-06"), _fact("Fixed bugs.", "2026-07-07")]
    book = _FakeBook()
    out = await run_weekly_reflection(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        entry_zone="UTC", language="en",
        knowledge_client=_Recaller(facts), book_client=book,
    )
    assert out["status"] == "reflected"
    assert len(book.writes) == 1
    w = book.writes[0]
    assert w["journal_kind"] == "reflection"        # get-or-replace per week
    assert w["entry_date"] == "2026-07-12"
    assert "questions to sit with" in w["body"].lower()  # the descriptive Socratic draft


@pytest.mark.asyncio
async def test_run_weekly_reflection_short_circuits_and_writes_nothing():
    distress = [_fact("I don't know how much longer I can do this", "2026-07-08")]
    book = _FakeBook()
    out = await run_weekly_reflection(
        user_id="u1", book_id="b1", week_start="2026-07-06", week_end="2026-07-12",
        entry_zone="UTC", language="en",
        knowledge_client=_Recaller(distress), book_client=book,
    )
    assert out["status"] == "safety_short_circuit" and out["category"] == "distress"
    assert book.writes == []  # NOTHING written on a distressed week
