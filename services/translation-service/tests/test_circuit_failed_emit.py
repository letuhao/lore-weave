"""S3c-2b — chapter.translation_failed emit on provider circuit-open.

When a chapter fails because the S3a circuit is open, the worker emits a
per-chapter failure event so campaign-service auto-pauses. Emit is circuit-open-
only + best-effort.
"""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.workers.chapter_worker import (
    _emit_chapter_failed_if_circuit_open,
    _TransientError,
)

CHAP = uuid4()
MSG = {
    "user_id": str(uuid4()),
    "book_id": str(uuid4()),
    "chapter_id": str(CHAP),
    "target_language": "vi",
}


def _outbox_calls(fake_pool):
    return [c for c in fake_pool.execute.call_args_list
            if len(c.args) > 1 and c.args[1] == "chapter.translation_failed"]


async def test_emits_on_circuit_open(fake_pool):
    # structured code (not message substring) drives detection.
    exc = _TransientError("provider_error_LLM_CIRCUIT_OPEN", code="LLM_CIRCUIT_OPEN")
    await _emit_chapter_failed_if_circuit_open(fake_pool, MSG, CHAP, exc)
    calls = _outbox_calls(fake_pool)
    assert len(calls) == 1
    payload = json.loads(calls[0].args[4])
    assert payload["error_code"] == "LLM_CIRCUIT_OPEN"
    assert payload["chapter_id"] == str(CHAP)
    assert payload["target_language"] == "vi"


async def test_no_emit_for_other_errors(fake_pool):
    await _emit_chapter_failed_if_circuit_open(
        fake_pool, MSG, CHAP, _TransientError("rate limited", code="LLM_RATE_LIMITED"))
    assert _outbox_calls(fake_pool) == []


async def test_no_emit_when_code_absent(fake_pool):
    # a non-provider transient (book-service down) has no code → no emit, even if
    # the message coincidentally mentions the string.
    await _emit_chapter_failed_if_circuit_open(
        fake_pool, MSG, CHAP, _TransientError("book-service down LLM_CIRCUIT_OPEN"))
    assert _outbox_calls(fake_pool) == []


async def test_best_effort_never_raises(fake_pool):
    fake_pool.execute.side_effect = RuntimeError("db down")
    await _emit_chapter_failed_if_circuit_open(
        fake_pool, MSG, CHAP, _TransientError("x", code="LLM_CIRCUIT_OPEN"))


async def test_handle_chapter_message_wires_emit_on_circuit_open(fake_pool, mocker):
    # WIRING (S3a lesson): a circuit-open transient failure flowing through
    # handle_chapter_message actually emits chapter.translation_failed — a removed
    # call in the except block would slip past the isolated-helper tests above.
    from app.workers import chapter_worker as cw

    mocker.patch.object(cw, "_process_chapter", new_callable=AsyncMock,
                        side_effect=cw._TransientError("boom", code="LLM_CIRCUIT_OPEN"))
    mocker.patch.object(cw, "_fail_chapter_idempotent", new_callable=AsyncMock)
    mocker.patch.object(cw, "_emit_chapter_done", new_callable=AsyncMock)
    mocker.patch.object(cw, "_check_job_completion", new_callable=AsyncMock)
    mocker.patch.object(cw, "record_stage")

    msg = {"job_id": str(uuid4()), **MSG}
    with pytest.raises(cw._TransientError):  # handler re-raises for the retry ladder
        await cw.handle_chapter_message(msg, fake_pool, AsyncMock(), object(), 0)
    assert _outbox_calls(fake_pool), "circuit-open must emit chapter.translation_failed via the handler"
