"""D-COMP-TRUNCATION-SURFACING — REAL capture tests (not stubbed).

The engine-router/assembly tests stub `stream_draft`/`diverge` whole, so they
prove the engine *maps* finish_reason→truncated but NOT that the real extraction
reads it off the wire. These exercise the actual code: `stream_draft` reads it off
the `DoneEvent`; `_one_draft` reads it off `job.result["finish_reason"]`.
"""

from __future__ import annotations

import uuid

from loreweave_llm.errors import LLMError
from loreweave_llm.models import DoneEvent, TokenEvent, UsageEvent

from app.engine.cowrite import stream_draft
from app.engine.select import _one_draft

_MODEL = str(uuid.uuid4())  # StreamRequest.model_ref must be a valid UUID


class _FakeSDK:
    def __init__(self, finish_reason: str | None):
        self._fr = finish_reason

    async def stream(self, req, *, user_id):
        yield TokenEvent(delta="Hello ")
        yield TokenEvent(delta="world.")
        yield UsageEvent(input_tokens=10, output_tokens=5)
        yield DoneEvent(finish_reason=self._fr)


async def _drain(sdk) -> dict:
    final: dict | None = None
    async for ev in stream_draft(
        sdk, user_id="u", model_source="user_model", model_ref=_MODEL,
        messages=[{"role": "user", "content": "x"}],
        prompt_token_estimate=10, max_output_tokens=100,
    ):
        if ev["type"] == "usage":
            final = ev
    assert final is not None
    return final


async def test_stream_draft_captures_length_finish_reason():
    final = await _drain(_FakeSDK("length"))
    assert final["metering"].finish_reason == "length"


async def test_stream_draft_captures_stop_finish_reason():
    final = await _drain(_FakeSDK("stop"))
    assert final["metering"].finish_reason == "stop"


async def test_stream_draft_none_finish_reason_when_absent():
    final = await _drain(_FakeSDK(None))
    assert final["metering"].finish_reason is None


# ── D-ENGINE-ERRORED-JOB-MARKED-COMPLETED — the terminal frame carries `error` ──
# so the router can fail (not complete-at-zero) a resolve failure. stream_draft
# ALWAYS yields a terminal usage frame even after an LLMError, so the error signal
# must ride that frame or the router marks the job completed with 0 tokens.

class _ResolveFailSDK:
    """Model never resolves — raises before any token (the observed bug shape)."""
    async def stream(self, req, *, user_id):
        raise LLMError("model_ref could not be resolved")
        yield  # pragma: no cover — make this an async generator


class _MidStreamFailSDK:
    """Yields real content, THEN errors — the taxonomy case the router keeps."""
    async def stream(self, req, *, user_id):
        yield TokenEvent(delta="partial ")
        yield TokenEvent(delta="prose")
        raise LLMError("stream dropped mid-flight")


async def test_stream_draft_error_no_content_flags_error_on_terminal_frame():
    final = await _drain(_ResolveFailSDK())
    assert final["error"] == "model_ref could not be resolved"
    assert final["text"] == ""  # zero content → the router must mark this FAILED
    assert final["metering"].output_tokens == 0


async def test_stream_draft_error_after_content_keeps_text():
    final = await _drain(_MidStreamFailSDK())
    assert final["error"] == "stream dropped mid-flight"
    assert final["text"] == "partial prose"  # non-empty → router keeps completed+truncated


async def test_stream_draft_clean_finish_has_no_error():
    final = await _drain(_FakeSDK("stop"))
    assert final["error"] is None


class _FakeJob:
    def __init__(self, result):
        self.status = "completed"
        self.result = result


class _FakeLLM:
    def __init__(self, finish_reason: str | None):
        self._fr = finish_reason

    async def submit_and_wait(self, **kw):
        result = {"messages": [{"content": "drafted prose"}]}
        if self._fr is not None:
            result["finish_reason"] = self._fr
        return _FakeJob(result)


async def test_one_draft_captures_finish_reason_from_job_result():
    cand = await _one_draft(
        _FakeLLM("length"), user_id="u", model_source="user_model", model_ref="m",
        messages=[{"role": "user", "content": "x"}], prompt_est=10, max_tokens=100,
        temperature=0.8, reasoning_effort=None, trace_id=None,
    )
    assert cand is not None and cand.metering.finish_reason == "length"


async def test_one_draft_none_finish_reason_when_absent():
    cand = await _one_draft(
        _FakeLLM(None), user_id="u", model_source="user_model", model_ref="m",
        messages=[{"role": "user", "content": "x"}], prompt_est=10, max_tokens=100,
        temperature=0.8, reasoning_effort=None, trace_id=None,
    )
    assert cand is not None and cand.metering.finish_reason is None
