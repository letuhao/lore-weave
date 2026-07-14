"""WS-5.2/5.3 — the weekly reflection pipeline, with the Gate-3 safety short-circuit.

The load-bearing test is `test_distress_week_short_circuits`: a week whose diary content
trips the safety floor yields NO patterns and NO draft — only a plain acknowledgement — and
that acknowledgement is never returned as a KG fact.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.reflection_job import ReflectionResult, reflect_week


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
