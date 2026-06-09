"""A2-S3b — run_canon_reflect orchestration (fake knowledge + llm).

Proves the glue end-to-end (without a live stack): a draft naming a `gone` cast
member → fact_for_check snapshot → symbolic guard → judge confirms → revise →
re-check on the revised (Kai-free) prose → resolved.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from loreweave_llm.models import DoneEvent, TokenEvent, UsageEvent

from app.engine.canon_reflect import run_canon_reflect


class _FakeKnowledge:
    """fact_for_check → a snapshot where the cast's Kai is gone at P."""
    def __init__(self, snapshot):
        self._snap = snapshot
        self.calls: list[dict] = []

    async def fact_for_check(self, *, project_id, at_order, glossary_entity_ids=None, entity_ids=None):
        self.calls.append({"at_order": at_order, "glossary_entity_ids": glossary_entity_ids})
        return self._snap


class _FakeSDK:
    """stream() yields the REVISED prose (no 'Kai') + a usage frame, and a
    DoneEvent carrying the model stop reason when `finish_reason` is set (the
    revise-path truncation surface)."""
    def __init__(self, revised_text, finish_reason=None):
        self._revised = revised_text
        self._finish_reason = finish_reason

    async def stream(self, req, *, user_id):
        yield TokenEvent(delta=self._revised)
        yield UsageEvent(input_tokens=10, output_tokens=7)
        if self._finish_reason is not None:
            yield DoneEvent(finish_reason=self._finish_reason)


class _FakeLLM:
    """submit_and_wait → judge confirms the violation; .sdk → revise stream."""
    def __init__(self, revised_text, finish_reason=None):
        self.sdk = _FakeSDK(revised_text, finish_reason)

    async def submit_and_wait(self, **kwargs):
        return SimpleNamespace(
            status="completed",
            result={"messages": [{"content":
                '{"verdicts":[{"entity_id":"e-kai","violated":true,"why":"acts"}]}'}]},
        )


def _snapshot():
    return {"at_order": 5_000_000, "entities": [
        {"entity_id": "e-kai", "glossary_entity_id": "g-kai", "name": "Kai",
         "canonical_name": "kai", "status": "gone"}],
        "relations": [], "events": []}


@pytest.mark.asyncio
async def test_reflect_repairs_seeded_contradiction():
    knowledge = _FakeKnowledge(_snapshot())
    llm = _FakeLLM("The sword lay still in the empty, silent hall.")  # no 'Kai'
    drafter, critic = str(uuid4()), str(uuid4())
    final, result, revise_tokens = await run_canon_reflect(
        knowledge=knowledge, llm=llm, user_id=uuid4(), project_id=uuid4(),
        cast_glossary_ids=["g-kai"], scene_sort_order=5,
        draft="Kai drew his sword and charged the gate.",
        packed_prompt="<canon>...</canon>", profile=SimpleNamespace(source_language="en", voice=""),
        drafter_source="user_model", drafter_ref=drafter,
        judge_source="user_model", judge_ref=critic,  # distinct → judge runs
        prompt_estimate=100, max_output_tokens=512, max_iters=1,
    )
    assert "Kai" not in final            # the gone character was revised out
    assert result.resolved is True       # no hard violation remains
    assert result.status == "checked"    # the guard actually ran
    assert result.iterations == 1
    assert revise_tokens == 7            # the revise pass metered
    # a clean (non-"length") revise leaves no truncation signal — the non-default
    # contrast for the truncating-revise test below.
    assert result.revise_finish_reason is None
    # the snapshot was fetched at sort_order × stride = 5_000_000.
    assert knowledge.calls[0]["at_order"] == 5_000_000
    assert knowledge.calls[0]["glossary_entity_ids"] == ["g-kai"]


@pytest.mark.asyncio
async def test_reflect_surfaces_truncated_revise_pass():
    # The repair itself hits the token cap: the revise stream ends with
    # finish_reason="length". run_canon_reflect must surface that on the result so
    # the engine ORs it into the job's `truncated` flag (a cut-off repair is NOT a
    # silent green even though the original winner draft was complete).
    knowledge = _FakeKnowledge(_snapshot())
    llm = _FakeLLM("The sword lay still in the empty hall and", finish_reason="length")
    final, result, revise_tokens = await run_canon_reflect(
        knowledge=knowledge, llm=llm, user_id=uuid4(), project_id=uuid4(),
        cast_glossary_ids=["g-kai"], scene_sort_order=5,
        draft="Kai drew his sword and charged the gate.",
        packed_prompt="<canon>...</canon>", profile=SimpleNamespace(source_language="en", voice=""),
        drafter_source="user_model", drafter_ref=str(uuid4()),
        judge_source="user_model", judge_ref=str(uuid4()),  # distinct → judge runs
        prompt_estimate=100, max_output_tokens=512, max_iters=1,
    )
    assert result.iterations == 1                      # a revise pass ran
    assert result.revise_finish_reason == "length"     # and it truncated → surfaced


@pytest.mark.asyncio
async def test_reflect_skips_without_position():
    # no scene_sort_order → can't position the check → advisory no-op (no fetch).
    knowledge = _FakeKnowledge(_snapshot())
    llm = _FakeLLM("x")
    final, result, revise_tokens = await run_canon_reflect(
        knowledge=knowledge, llm=llm, user_id=uuid4(), project_id=uuid4(),
        cast_glossary_ids=["g-kai"], scene_sort_order=None,
        draft="Kai acts.", packed_prompt="", profile=SimpleNamespace(source_language="en", voice=""),
        drafter_source="user_model", drafter_ref="d", judge_source="user_model", judge_ref="c",
        prompt_estimate=10, max_output_tokens=128, max_iters=1,
    )
    # dirty data (no position) must NOT be a silent green — status says so.
    assert final == "Kai acts." and result.resolved and knowledge.calls == []
    assert result.status == "skipped_no_position"


@pytest.mark.asyncio
async def test_reflect_no_cast_is_skipped_no_cast():
    knowledge = _FakeKnowledge(_snapshot())
    llm = _FakeLLM("x")
    final, result, _ = await run_canon_reflect(
        knowledge=knowledge, llm=llm, user_id=uuid4(), project_id=uuid4(),
        cast_glossary_ids=[], scene_sort_order=5,  # cast empty
        draft="A quiet scene.", packed_prompt="", profile=SimpleNamespace(source_language="en", voice=""),
        drafter_source="user_model", drafter_ref="d", judge_source="user_model", judge_ref="c",
        prompt_estimate=10, max_output_tokens=128, max_iters=1,
    )
    assert result.status == "skipped_no_cast" and knowledge.calls == []


@pytest.mark.asyncio
async def test_reflect_degraded_when_knowledge_unavailable():
    # fact_for_check returns None (knowledge outage) → verified nothing → degraded.
    knowledge = _FakeKnowledge(None)
    llm = _FakeLLM("x")
    final, result, _ = await run_canon_reflect(
        knowledge=knowledge, llm=llm, user_id=uuid4(), project_id=uuid4(),
        cast_glossary_ids=["g-kai"], scene_sort_order=5,
        draft="Kai charged.", packed_prompt="", profile=SimpleNamespace(source_language="en", voice=""),
        drafter_source="user_model", drafter_ref="d", judge_source="user_model", judge_ref="c",
        prompt_estimate=10, max_output_tokens=128, max_iters=1,
    )
    assert result.status == "degraded" and result.resolved is True


@pytest.mark.asyncio
async def test_reflect_symbolic_only_when_judge_not_distinct():
    # judge_ref == drafter_ref → no distinct judge → symbolic-only → advisory
    # (confirmed None) → NOT auto-revised (no hard) → resolved, no revise.
    knowledge = _FakeKnowledge(_snapshot())
    llm = _FakeLLM("should-not-be-used")
    final, result, revise_tokens = await run_canon_reflect(
        knowledge=knowledge, llm=llm, user_id=uuid4(), project_id=uuid4(),
        cast_glossary_ids=["g-kai"], scene_sort_order=5,
        draft="Kai charged.", packed_prompt="", profile=SimpleNamespace(source_language="en", voice=""),
        drafter_source="user_model", drafter_ref="same",
        judge_source="user_model", judge_ref="same",  # NOT distinct
        prompt_estimate=10, max_output_tokens=128, max_iters=1,
    )
    assert final == "Kai charged."        # symbolic-only → advisory → no revise
    assert result.resolved and revise_tokens == 0
