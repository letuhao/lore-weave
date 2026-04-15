"""K17.3 — llm_json_parser unit tests.

Uses a hand-rolled FakeProviderClient (not httpx.MockTransport) because
the tests want to:
  1. Assert which kwargs the wrapper passed to `chat_completion`
  2. Queue multi-step responses (first call / retry call)
  3. Inspect the retry fix-up messages that the builders constructed

The fake implements the same duck-typed surface as `ProviderClient`
but doesn't touch HTTP at all.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from pydantic import BaseModel, Field

from app.clients.provider_client import (
    ChatCompletionResponse,
    ChatCompletionUsage,
    ProviderAuthError,
    ProviderClient,
    ProviderDecodeError,
    ProviderInvalidRequest,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUpstreamError,
)
from app.extraction.llm_json_parser import (
    ExtractionError,
    extract_json,
)


# ── Fake client + helpers ─────────────────────────────────────────────


class FakeProviderClient:
    """Duck-typed stand-in for ProviderClient.

    Pre-seed `responses` with a queue of response objects or exceptions.
    Each `chat_completion` call pops the head and either returns it or
    raises it. `calls` records every invocation's kwargs for assertion.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Any] = []

    def queue_response(self, content: str, model: str = "test-model") -> None:
        self.responses.append(
            ChatCompletionResponse(
                content=content,
                model=model,
                usage=ChatCompletionUsage(),
                raw={},
            )
        )

    def queue_exception(self, exc: Exception) -> None:
        self.responses.append(exc)

    async def chat_completion(self, **kwargs: Any) -> ChatCompletionResponse:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError(
                f"FakeProviderClient ran out of queued responses "
                f"(already had {len(self.calls)} calls)"
            )
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _client_kwarg(fake: FakeProviderClient) -> ProviderClient:
    # The real ProviderClient type is what extract_json expects, but
    # FakeProviderClient satisfies the duck-typed interface. Cast for
    # mypy / runtime type-check silence.
    return cast(ProviderClient, fake)


class Entity(BaseModel):
    name: str
    kind: str
    confidence: float = Field(ge=0.0, le=1.0)


class EntityExtractionResponse(BaseModel):
    entities: list[Entity]


_VALID_JSON = '{"entities":[{"name":"Alice","kind":"person","confidence":0.9}]}'
_BAD_JSON = "this is not json at all {"
_WRONG_SHAPE_JSON = '{"entities":[{"name":"Alice","kind":"person","confidence":5.0}]}'  # confidence > 1


_DEFAULT_CALL = {
    "user_id": "u-1",
    "model_source": "user_model",
    "model_ref": "11111111-1111-1111-1111-111111111111",
    "system": "You are an extractor.",
    "user_prompt": "Extract entities from: Alice is a person.",
}


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_first_try():
    fake = FakeProviderClient()
    fake.queue_response(_VALID_JSON)
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(result.entities) == 1
    assert result.entities[0].name == "Alice"
    assert len(fake.calls) == 1


# ── Parse retry ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_retry_succeeds():
    fake = FakeProviderClient()
    fake.queue_response(_BAD_JSON)
    fake.queue_response(_VALID_JSON)
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_parse_retry_exhausted():
    fake = FakeProviderClient()
    fake.queue_response(_BAD_JSON)
    fake.queue_response(_BAD_JSON)  # second call also bad
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "retry_parse"
    assert excinfo.value.raw_content == _BAD_JSON
    assert len(fake.calls) == 2


# ── Validate retry ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_retry_succeeds():
    fake = FakeProviderClient()
    fake.queue_response(_WRONG_SHAPE_JSON)  # confidence > 1 fails Pydantic
    fake.queue_response(_VALID_JSON)
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_validate_retry_exhausted():
    fake = FakeProviderClient()
    fake.queue_response(_WRONG_SHAPE_JSON)
    fake.queue_response(_WRONG_SHAPE_JSON)
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "retry_validate"
    assert excinfo.value.raw_content == _WRONG_SHAPE_JSON
    assert len(fake.calls) == 2


# ── Provider retry ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limited_retry_with_retry_after():
    fake = FakeProviderClient()
    fake.queue_exception(
        ProviderRateLimited("slow down", retry_after_s=10.0, status_code=429)
    )
    fake.queue_response(_VALID_JSON)

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
        sleep_fn=fake_sleep,
    )
    assert isinstance(result, EntityExtractionResponse)
    assert slept == [10.0]
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_rate_limited_retry_without_retry_after_does_not_sleep():
    fake = FakeProviderClient()
    fake.queue_exception(
        ProviderRateLimited("slow down", retry_after_s=None, status_code=429)
    )
    fake.queue_response(_VALID_JSON)

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
        sleep_fn=fake_sleep,
    )
    assert isinstance(result, EntityExtractionResponse)
    assert slept == []
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_rate_limited_retry_after_zero_does_not_sleep():
    # R1 E9 regression — `retry_after_s=0.0` is a legitimate upstream
    # signal meaning "retry immediately". The conditional
    # `if retry_after:` correctly treats it as falsy. A future change
    # that switches to `if retry_after is not None:` would call
    # `sleep_fn(0.0)` — technically harmless but adds an event-loop
    # scheduling hop and would surprise future-me. This test guards
    # against the regression.
    fake = FakeProviderClient()
    fake.queue_exception(
        ProviderRateLimited("slow down", retry_after_s=0.0, status_code=429)
    )
    fake.queue_response(_VALID_JSON)

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
        sleep_fn=fake_sleep,
    )
    assert isinstance(result, EntityExtractionResponse)
    assert slept == []  # no sleep for retry_after_s=0


@pytest.mark.asyncio
async def test_upstream_error_retry_succeeds():
    fake = FakeProviderClient()
    fake.queue_exception(
        ProviderUpstreamError("502", status_code=502)
    )
    fake.queue_response(_VALID_JSON)
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_timeout_retry_succeeds():
    fake = FakeProviderClient()
    fake.queue_exception(ProviderTimeout("timeout"))
    fake.queue_response(_VALID_JSON)
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)


@pytest.mark.asyncio
async def test_provider_retry_exhausted():
    fake = FakeProviderClient()
    fake.queue_exception(ProviderUpstreamError("502-a"))
    fake.queue_exception(ProviderUpstreamError("502-b"))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider_exhausted"
    assert len(fake.calls) == 2


# ── Non-retry provider errors ────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_retry_model_not_found_fails_immediately():
    fake = FakeProviderClient()
    fake.queue_exception(ProviderModelNotFound("not found", status_code=404))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider"
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_non_retry_auth_error_fails_immediately():
    fake = FakeProviderClient()
    fake.queue_exception(ProviderAuthError("bad key", status_code=401))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider"
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_non_retry_invalid_request_fails_immediately():
    fake = FakeProviderClient()
    fake.queue_exception(ProviderInvalidRequest("bad args"))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider"
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_non_retry_decode_error_fails_immediately():
    fake = FakeProviderClient()
    fake.queue_exception(ProviderDecodeError("no choices"))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider"
    assert len(fake.calls) == 1


# ── Fix-up prompt construction ───────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_retry_prompt_contains_bad_content_and_error():
    fake = FakeProviderClient()
    fake.queue_response(_BAD_JSON)
    fake.queue_response(_VALID_JSON)
    await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    retry_messages = fake.calls[1]["messages"]
    # Expected shape: system, user, assistant (bad content), user (fix-up)
    assert retry_messages[0]["role"] == "system"
    assert retry_messages[1]["role"] == "user"
    assert retry_messages[2]["role"] == "assistant"
    assert retry_messages[2]["content"] == _BAD_JSON
    assert retry_messages[3]["role"] == "user"
    assert "could not be parsed as JSON" in retry_messages[3]["content"]
    assert "Return ONLY" in retry_messages[3]["content"]


@pytest.mark.asyncio
async def test_validate_retry_prompt_contains_bad_content_and_validation_error():
    fake = FakeProviderClient()
    fake.queue_response(_WRONG_SHAPE_JSON)
    fake.queue_response(_VALID_JSON)
    await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    retry_messages = fake.calls[1]["messages"]
    assert retry_messages[2]["role"] == "assistant"
    assert retry_messages[2]["content"] == _WRONG_SHAPE_JSON
    assert retry_messages[3]["role"] == "user"
    assert "did not match" in retry_messages[3]["content"]
    assert "confidence" in retry_messages[3]["content"]  # Pydantic error text mentions the field


# ── Message shape ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_try_messages_include_system_when_set():
    fake = FakeProviderClient()
    fake.queue_response(_VALID_JSON)
    await extract_json(
        EntityExtractionResponse,
        user_id="u-1",
        model_source="user_model",
        model_ref="11111111-1111-1111-1111-111111111111",
        system="You are an extractor.",
        user_prompt="Do it.",
        client=_client_kwarg(fake),
    )
    messages = fake.calls[0]["messages"]
    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": "You are an extractor."}
    assert messages[1] == {"role": "user", "content": "Do it."}


@pytest.mark.asyncio
async def test_first_try_messages_omit_system_when_none():
    fake = FakeProviderClient()
    fake.queue_response(_VALID_JSON)
    await extract_json(
        EntityExtractionResponse,
        user_id="u-1",
        model_source="user_model",
        model_ref="11111111-1111-1111-1111-111111111111",
        system=None,
        user_prompt="Do it.",
        client=_client_kwarg(fake),
    )
    messages = fake.calls[0]["messages"]
    assert len(messages) == 1
    assert messages[0] == {"role": "user", "content": "Do it."}


@pytest.mark.asyncio
async def test_response_format_passed_through():
    fake = FakeProviderClient()
    fake.queue_response(_VALID_JSON)
    await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        response_format={"type": "json_object"},
        client=_client_kwarg(fake),
    )
    assert fake.calls[0]["response_format"] == {"type": "json_object"}


# ── ExtractionError.raw_content capture ──────────────────────────────


# ── R3 regressions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_r3_f9_code_fenced_json_parsed_without_retry():
    # R3 F9: LLMs (especially local ones) often wrap JSON in markdown
    # code fences even when instructed not to. The client must strip
    # fences on BOTH first attempt and retry so we don't burn retries
    # on pure formatting issues.
    fake = FakeProviderClient()
    fake.queue_response(f"```json\n{_VALID_JSON}\n```")
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(result.entities) == 1
    # Crucially: only ONE call. The fence was stripped on the first
    # attempt; no retry was burned.
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_r3_f9_code_fenced_json_without_json_language_tag():
    # Some providers emit ``` without the "json" language tag.
    fake = FakeProviderClient()
    fake.queue_response(f"```\n{_VALID_JSON}\n```")
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_r3_f9_code_fence_stripped_on_retry_path_too():
    # If the first attempt is REALLY bad (not even fence-wrapped) but
    # the retry returns fence-wrapped JSON, we still accept it.
    fake = FakeProviderClient()
    fake.queue_response(_BAD_JSON)
    fake.queue_response(f"```json\n{_VALID_JSON}\n```")
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_r3_f2_raw_content_captured_on_parse_retry_provider_exhausted():
    # R3 F2/F4: when the first attempt returns bad JSON and the fix-up
    # call raises a provider error, ExtractionError.raw_content must
    # carry the FIRST attempt's content, not None. Without this fix,
    # operators lose the debugging signal for "what did the LLM say
    # before the fix-up call errored out?".
    fake = FakeProviderClient()
    fake.queue_response("this is definitely not json")
    fake.queue_exception(ProviderUpstreamError("502 on fix-up", status_code=502))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider_exhausted"
    assert excinfo.value.raw_content == "this is definitely not json"
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_r3_f4_raw_content_captured_on_validate_retry_provider_exhausted():
    # Same F2/F4 story for the validate retry path.
    fake = FakeProviderClient()
    fake.queue_response(_WRONG_SHAPE_JSON)
    fake.queue_exception(ProviderTimeout("timeout on fix-up"))
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.stage == "provider_exhausted"
    assert excinfo.value.raw_content == _WRONG_SHAPE_JSON
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_r3_f6_bad_content_capped_in_parse_retry_prompt():
    # R3 F6: pathological LLM echo (entire chapter echoed back) must
    # be capped in the retry prompt so it can't blow the context
    # budget. Cap is 8000 chars.
    fake = FakeProviderClient()
    pathological = "NOT JSON " * 2000  # ~18000 chars of garbage
    fake.queue_response(pathological)
    fake.queue_response(_VALID_JSON)
    result = await extract_json(
        EntityExtractionResponse,
        **_DEFAULT_CALL,
        client=_client_kwarg(fake),
    )
    assert isinstance(result, EntityExtractionResponse)

    # Inspect the retry prompt: the assistant turn (bad_content) must
    # be capped at 8000 chars + a truncation suffix.
    retry_messages = fake.calls[1]["messages"]
    assistant_turn = retry_messages[2]
    assert assistant_turn["role"] == "assistant"
    assert len(assistant_turn["content"]) < len(pathological)
    assert "truncated" in assistant_turn["content"].lower()


@pytest.mark.asyncio
async def test_raw_content_captured_on_parse_exhaustion():
    fake = FakeProviderClient()
    fake.queue_response(_BAD_JSON)
    fake.queue_response("still not json {")
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert excinfo.value.raw_content == "still not json {"


@pytest.mark.asyncio
async def test_raw_content_captured_on_validate_exhaustion():
    fake = FakeProviderClient()
    fake.queue_response(_WRONG_SHAPE_JSON)
    fake.queue_response('{"entities":[{"name":"Bob","kind":"person","confidence":2.5}]}')
    with pytest.raises(ExtractionError) as excinfo:
        await extract_json(
            EntityExtractionResponse,
            **_DEFAULT_CALL,
            client=_client_kwarg(fake),
        )
    assert "Bob" in (excinfo.value.raw_content or "")


# ── Sanity: default sleep_fn is asyncio.sleep ────────────────────────


def test_default_sleep_fn_is_asyncio_sleep():
    import inspect
    sig = inspect.signature(extract_json)
    assert sig.parameters["sleep_fn"].default is asyncio.sleep
