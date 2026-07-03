"""Tests for the single-shot structured-generate helper (loreweave_llm.structured).

Covers the shared plumbing every non-agentic generate engine used to hand-roll:
reasoning-off-by-default (the empty-prose footgun disable), the submit boilerplate,
the messages[0].content dig, empty-content / failed-job / transport error mapping,
and the tolerant JSON extractor.
"""
from __future__ import annotations

import pytest

from loreweave_llm import (
    GenerateResult,
    StructuredGenerateError,
    parse_json_object,
    structured_generate,
)


class _Job:
    def __init__(self, status="completed", content=None, error_code=None):
        self.status = status
        self.error = type("E", (), {"code": error_code})() if error_code else None
        self.result = {"messages": [{"content": content}]} if content is not None else None


class _Fake:
    """Captures the kwargs the helper sends and returns a canned job."""

    def __init__(self, job=None, raises=None):
        self._job = job or _Job(content='{"ok": true}')
        self._raises = raises
        self.seen: dict = {}

    async def submit_and_wait(self, **kw):
        self.seen = kw
        if self._raises:
            raise self._raises
        return self._job


# ── parse_json_object ──

def test_parse_clean_object():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_fenced_and_prose():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go:\n{"a": 1}\nEnjoy!') == {"a": 1}


def test_parse_non_json_raises():
    with pytest.raises(StructuredGenerateError):
        parse_json_object("sorry, no")


def test_parse_non_object_raises():
    with pytest.raises(StructuredGenerateError):
        parse_json_object("[1, 2, 3]")


# ── structured_generate ──

@pytest.mark.asyncio
async def test_happy_disables_thinking_by_default():
    fake = _Fake(job=_Job(content="hello world"))
    res = await structured_generate(
        fake,
        user_id="u",
        model_ref="m1",
        messages=[{"role": "user", "content": "hi"}],
        max_output_tokens=512,
    )
    assert isinstance(res, GenerateResult)
    assert res.content == "hello world"
    # the footgun disable: reasoning="none" ⇒ chat_template_kwargs.thinking is False
    assert fake.seen["input"]["chat_template_kwargs"]["thinking"] is False
    assert fake.seen["input"]["chat_template_kwargs"]["enable_thinking"] is False
    assert fake.seen["input"]["max_tokens"] == 512
    assert fake.seen["operation"] == "chat"
    assert fake.seen["model_source"] == "user_model"
    assert fake.seen["model_ref"] == "m1"


@pytest.mark.asyncio
async def test_graded_effort_enables_thinking():
    fake = _Fake(job=_Job(content="x"))
    await structured_generate(
        fake, user_id="u", model_ref="m", messages=[{"role": "user", "content": "hi"}],
        max_output_tokens=64, reasoning="high",
    )
    assert fake.seen["input"]["chat_template_kwargs"]["thinking"] is True
    assert fake.seen["input"]["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_empty_content_raises_clear_error():
    fake = _Fake(job=_Job(content="   "))
    with pytest.raises(StructuredGenerateError, match="empty response"):
        await structured_generate(
            fake, user_id="u", model_ref="m", messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=64,
        )


@pytest.mark.asyncio
async def test_failed_job_raises_with_code():
    fake = _Fake(job=_Job(status="failed", error_code="LLM_UPSTREAM_ERROR"))
    with pytest.raises(StructuredGenerateError, match="LLM_UPSTREAM_ERROR"):
        await structured_generate(
            fake, user_id="u", model_ref="m", messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=64,
        )


@pytest.mark.asyncio
async def test_transport_error_wrapped():
    fake = _Fake(raises=RuntimeError("boom"))
    with pytest.raises(StructuredGenerateError, match="LLM call failed"):
        await structured_generate(
            fake, user_id="u", model_ref="m", messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=64,
        )


@pytest.mark.asyncio
async def test_no_prompt_content_raises_before_call():
    fake = _Fake()
    with pytest.raises(StructuredGenerateError, match="no prompt content"):
        await structured_generate(
            fake, user_id="u", model_ref="m",
            messages=[{"role": "system", "content": "   "}],
            max_output_tokens=64,
        )
    assert fake.seen == {}  # never reached the client
