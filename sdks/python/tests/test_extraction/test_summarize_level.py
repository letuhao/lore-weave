"""P3 — tests for summarize_level extractor (D7)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from loreweave_extraction import LevelSummary, summarize_level
from loreweave_extraction.errors import ExtractionError


class _FakeJob:
    """Minimal Job-shaped object the SDK returns from submit_and_wait."""
    def __init__(self, result: dict):
        self.result = result


def _ok_response(text: str, usage: dict | None = None) -> _FakeJob:
    """Build a fake Job whose .result mirrors the chat-aggregator
    shape that provider-registry produces for `summarize_level` (and
    every default-aggregator op)."""
    return _FakeJob({
        "messages": [{"role": "assistant", "content": text}],
        "usage": usage or {"input_tokens": 100, "output_tokens": 50},
    })


def _sys_msg_from_call(llm):
    """Pull the system-prompt string out of the captured submit_and_wait
    call. Matches the corrected SDK contract: messages live under
    `input["messages"]`, not as a top-level kwarg."""
    return llm.submit_and_wait.call_args.kwargs["input"]["messages"][0]["content"]


async def test_summarize_level_chapter_happy_path():
    """Chapter level, happy path: well-formed JSON response."""
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _ok_response(
        '{"summary_text": "A young hero discovers their lineage and faces an ancient evil with the help of newfound allies."}'
    )
    out = await summarize_level(
        level="chapter",
        child_texts=["Scene 1 text.", "Scene 2 text."],
        entity_names=["Alice", "Bob"],
        user_id="u-1",
        project_id="p-1",
        model_source="user_model",
        model_ref="m-1",
        llm_client=llm,
    )
    assert isinstance(out, LevelSummary)
    assert "ancient evil" in out.summary_text
    assert out.token_usage == {"input_tokens": 100, "output_tokens": 50}
    # Prompt was invoked with the right operation tag.
    call_kwargs = llm.submit_and_wait.call_args.kwargs
    assert call_kwargs["operation"] == "summarize_level"
    # project_id rides on job_meta (not a top-level kwarg) per LLMClient
    # contract caught by session-67 cont.3 live smoke.
    assert call_kwargs["job_meta"]["project_id"] == "p-1"
    # Footgun disable PINNED (no_thinking_fields): a reasoning model must not spend
    # the 1024-token budget on hidden thinking → empty → ExtractionError. If this
    # goes red, the **_NO_THINKING spread was dropped and the footgun re-opened.
    assert call_kwargs["input"]["chat_template_kwargs"]["thinking"] is False
    assert call_kwargs["input"]["reasoning_effort"] == "none"
    # Level substituted into the prompt — messages live under input[].
    sys_msg = _sys_msg_from_call(llm)
    assert "chapter" in sys_msg.lower()
    assert "Alice" in sys_msg  # entity name passed through


async def test_summarize_level_strips_markdown_code_fence():
    """LLMs often wrap JSON in ```json fences; extractor must strip."""
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _ok_response(
        '```json\n{"summary_text": "The Master watches as the disciple completes the trial."}\n```'
    )
    out = await summarize_level(
        level="part",
        child_texts=["Chapter 1 summary.", "Chapter 2 summary."],
        entity_names=["The Master"],
        user_id="u-1", project_id="p-1",
        model_source="user_model", model_ref="m-1",
        llm_client=llm,
    )
    assert "Master watches" in out.summary_text


async def test_summarize_level_rejects_empty_child_texts():
    llm = AsyncMock()
    with pytest.raises(ValueError, match="child_texts must not be empty"):
        await summarize_level(
            level="chapter",
            child_texts=[],
            entity_names=["x"],
            user_id="u", project_id="p",
            model_source="user_model", model_ref="m",
            llm_client=llm,
        )
    llm.submit_and_wait.assert_not_called()


async def test_summarize_level_rejects_unknown_level():
    llm = AsyncMock()
    with pytest.raises(ValueError, match="unknown level"):
        await summarize_level(
            level="bogus",  # type: ignore[arg-type]
            child_texts=["x"],
            entity_names=[],
            user_id="u", project_id="p",
            model_source="user_model", model_ref="m",
            llm_client=llm,
        )


async def test_summarize_level_truncates_long_child_texts():
    """Joined input > 8000 chars is truncated; LLM still called."""
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _ok_response(
        '{"summary_text": "A long book with many themes and many characters across its narrative arc."}'
    )
    huge = ["x" * 5000, "y" * 5000]  # 10k joined > 8000 cap
    out = await summarize_level(
        level="book",
        child_texts=huge,
        entity_names=[],
        user_id="u", project_id="p",
        model_source="user_model", model_ref="m",
        llm_client=llm,
    )
    assert isinstance(out, LevelSummary)
    sys_msg = _sys_msg_from_call(llm)
    # Truncation marker present.
    assert "[...truncated]" in sys_msg
    # Total prompt size sanely bounded.
    assert len(sys_msg) < 10000


async def test_summarize_level_raises_extraction_error_on_llm_failure():
    llm = AsyncMock()
    llm.submit_and_wait.side_effect = RuntimeError("gateway 500")
    with pytest.raises(ExtractionError) as exc_info:
        await summarize_level(
            level="chapter",
            child_texts=["x"],
            entity_names=[],
            user_id="u", project_id="p",
            model_source="user_model", model_ref="m",
            llm_client=llm,
        )
    # Stage = "provider" — the SDK wrapper's transient retries already
    # exhausted before reaching us (corrected session-67 cont.3).
    assert exc_info.value.stage == "provider"


async def test_summarize_level_raises_on_malformed_json():
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _ok_response("not valid json {{{")
    with pytest.raises(ExtractionError, match="not JSON"):
        await summarize_level(
            level="chapter",
            child_texts=["x"],
            entity_names=[],
            user_id="u", project_id="p",
            model_source="user_model", model_ref="m",
            llm_client=llm,
        )


async def test_summarize_level_raises_on_missing_summary_text():
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _ok_response('{"wrong_field": "..."}')
    with pytest.raises(ExtractionError, match="missing summary_text"):
        await summarize_level(
            level="chapter",
            child_texts=["x"],
            entity_names=[],
            user_id="u", project_id="p",
            model_source="user_model", model_ref="m",
            llm_client=llm,
        )


async def test_summarize_level_caps_entity_names_in_prompt():
    """Spec D7: max 30 entity names included in prompt."""
    llm = AsyncMock()
    llm.submit_and_wait.return_value = _ok_response(
        '{"summary_text": "Generic summary of the chapter."}'
    )
    many = [f"Entity{i}" for i in range(100)]
    await summarize_level(
        level="chapter",
        child_texts=["x"],
        entity_names=many,
        user_id="u", project_id="p",
        model_source="user_model", model_ref="m",
        llm_client=llm,
    )
    sys_msg = _sys_msg_from_call(llm)
    # First 30 included, 31st onward excluded.
    assert "Entity0" in sys_msg
    assert "Entity29" in sys_msg
    assert "Entity30" not in sys_msg  # capped at _MAX_ENTITY_NAMES=30
