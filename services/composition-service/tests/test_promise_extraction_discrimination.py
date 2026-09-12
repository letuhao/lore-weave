"""T9 — "no promises tracked" must not mean "the extraction failed".

WHY THIS EXISTS. ``extract_tracked_promises`` returned ``[]`` for three unrelated situations: the
spec genuinely declares no promises, the LLM call errored, and the response was truncated or
unparseable. All three became one downstream code, ``no_tracked_promises`` — so a feature nobody
had configured and a feature that had just broken were the same string to every caller, including
the UI. A 2026-09-06 human-sim run hit the empty case and could not tell which it was without
reading a job row out of the database.

That is a silent-failure-reported-as-a-clean-empty-result: the same shape as the response-cap and
save-on-blur defects this remediation exists to close, not a copy problem.
"""
from __future__ import annotations

import pytest

from app.engine import promise_audit


class _Llm:
    """Stands in for LLMClient — `_chat` is patched, so this is never really called."""


@pytest.mark.asyncio
async def test_genuine_emptiness_is_reported_as_a_successful_extraction(monkeypatch):
    """A spec that declares no promises is a legitimate, SUCCESSFUL answer."""
    async def _chat(*_a, **_k):
        return '{"promises": []}'
    monkeypatch.setattr(promise_audit, "_chat", _chat)

    promises, ok = await promise_audit.extract_tracked_promises_ex(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan",
    )
    assert promises == []
    assert ok is True, "an empty spec was reported as a failed extraction"


@pytest.mark.asyncio
async def test_a_failed_call_is_reported_as_a_failure(monkeypatch):
    """`_chat` returns None for an LLM error AND for a truncated/unusable response."""
    async def _chat(*_a, **_k):
        return None
    monkeypatch.setattr(promise_audit, "_chat", _chat)

    promises, ok = await promise_audit.extract_tracked_promises_ex(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan",
    )
    assert promises == []
    assert ok is False, "a failed extraction was indistinguishable from an empty spec"


@pytest.mark.asyncio
async def test_unparseable_content_is_a_failure_not_an_empty_spec(monkeypatch):
    """The third collapsed path: the model answered, but not with usable JSON."""
    async def _chat(*_a, **_k):
        return "I'm afraid I can't do that."
    monkeypatch.setattr(promise_audit, "_chat", _chat)

    promises, ok = await promise_audit.extract_tracked_promises_ex(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan",
    )
    assert promises == []
    assert ok is False


@pytest.mark.asyncio
async def test_promises_are_returned_with_ok_true(monkeypatch):
    async def _chat(*_a, **_k):
        return '{"promises": ["the sealed grimoire", "the debt to the sect"]}'
    monkeypatch.setattr(promise_audit, "_chat", _chat)

    promises, ok = await promise_audit.extract_tracked_promises_ex(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan",
    )
    assert promises == ["the sealed grimoire", "the debt to the sect"]
    assert ok is True


@pytest.mark.asyncio
async def test_the_list_only_wrapper_still_behaves_for_callers_that_cannot_act_on_it(monkeypatch):
    """The eval harness skips the book either way, so its contract is unchanged."""
    async def _chat(*_a, **_k):
        return None
    monkeypatch.setattr(promise_audit, "_chat", _chat)

    assert await promise_audit.extract_tracked_promises(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan",
    ) == []


@pytest.mark.asyncio
async def test_quality_report_emits_the_two_codes_distinctly(monkeypatch):
    """The end-to-end property: two causes, two codes.

    This is the assertion that would have caught the original defect — the engine-level
    discrimination is worthless if the report collapses it again one call later.
    """
    from app.engine import quality_report

    async def _ok_empty(*_a, **_k):
        return [], True

    async def _failed(*_a, **_k):
        return [], False

    monkeypatch.setattr(quality_report, "extract_tracked_promises_ex", _ok_empty)
    empty = await quality_report.build_promise_coverage(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan", book_text="prose",
    )

    monkeypatch.setattr(quality_report, "extract_tracked_promises_ex", _failed)
    broken = await quality_report.build_promise_coverage(
        _Llm(), user_id="u", model_source="user_model", model_ref="m",
        premise="p", plan_text="plan", book_text="prose",
    )

    assert empty["error"] == "no_tracked_promises"
    assert broken["error"] == "promise_extraction_failed"
    assert empty["error"] != broken["error"], (
        "a configured-but-empty book and a broken extraction report the same code again"
    )
