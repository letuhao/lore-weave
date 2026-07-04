"""T6 D6 — the compaction summary prompt is FACT-PRESERVING EXTRACTIVE.

A lossy prose summary silently drops load-bearing facts. D6 requires the summary
to lead with an explicit verbatim FACTS block (the system of record) before prose,
and to keep names EXACT. These deterministic checks pin the contract; the live
smoke (docs/eval) proves a planted fact actually survives.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

import pytest

from app.services.compact_service import (
    _SUMMARY_SYSTEM_PROMPT,
    SummaryTruncatedError,
    summarize_for_compaction,
    transcript_of,
)


def test_prompt_is_two_section_extractive():
    p = _SUMMARY_SYSTEM_PROMPT
    assert "FACTS:" in p and "SYNOPSIS:" in p
    # the load-bearing categories the FACTS block must enumerate
    for cat in ("Entities", "Decisions", "Established", "Open threads"):
        assert cat in p, cat


def test_prompt_forbids_name_paraphrase_and_reasoning():
    p = _SUMMARY_SYSTEM_PROMPT.lower()
    assert "verbatim" in p
    assert "never" in p and "paraphrase" in p  # names must stay exact
    assert "do not reason aloud" in p


class _FakeClient:
    """A loreweave_llm.Client stand-in whose stream yields the given events."""

    def __init__(self, events):
        self._events = events

    def __call__(self, *a, **k):  # Client(...) constructor
        return self

    async def aclose(self):
        pass

    def stream(self, request):
        events = self._events

        async def _gen():
            for ev in events:
                yield ev

        return _gen()


@pytest.mark.asyncio
async def test_truncated_summary_raises_not_stored(monkeypatch):
    """audit HIGH-1: a summary cut off at max_tokens (finish_reason='length') must
    RAISE (so callers degrade honestly) rather than return a partial with its tail
    silently gone."""
    from loreweave_llm import DoneEvent, TokenEvent

    import app.services.compact_service as cs

    fake = _FakeClient([TokenEvent(delta="FACTS:\n- Entities: Lâm"), DoneEvent(finish_reason="length")])
    monkeypatch.setattr(cs, "Client", fake)
    with pytest.raises(SummaryTruncatedError):
        await summarize_for_compaction(
            [{"role": "user", "content": "hi"}],
            model_source="user_model", model_ref="00000000-0000-4000-8000-000000000001", user_id="00000000-0000-4000-8000-000000000002",
        )


@pytest.mark.asyncio
async def test_complete_summary_returned(monkeypatch):
    """A clean stop returns the text (no false truncation trip)."""
    from loreweave_llm import DoneEvent, TokenEvent

    import app.services.compact_service as cs

    fake = _FakeClient([TokenEvent(delta="FACTS:\n- Entities: Lâm Uyển"), DoneEvent(finish_reason="stop")])
    monkeypatch.setattr(cs, "Client", fake)
    out = await summarize_for_compaction(
        [{"role": "user", "content": "hi"}],
        model_source="user_model", model_ref="00000000-0000-4000-8000-000000000001", user_id="00000000-0000-4000-8000-000000000002",
    )
    assert "Lâm Uyển" in out


def test_transcript_of_compact_tool_call_turn():
    # a prose-less tool-call turn is represented compactly (not dropped)
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "story_search"}},
            {"function": {"name": "memory_search"}},
        ]},
    ]
    t = transcript_of(msgs)
    assert "user: hi" in t
    assert "(called story_search, memory_search)" in t
