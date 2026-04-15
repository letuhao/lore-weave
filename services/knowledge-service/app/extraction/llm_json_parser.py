"""K17.3 — LLM JSON extraction wrapper with parse/validate retry.

Wraps `ProviderClient.chat_completion` (K17.2b) with:
  1. A single HTTP call to the LLM.
  2. `json.loads` on the response content.
  3. `schema.model_validate(parsed)` against a caller-supplied Pydantic
     model.
  4. One retry budget shared across three failure modes:
       - retry-eligible provider error (ProviderRateLimited,
         ProviderUpstreamError, ProviderTimeout) → repeat the same call
       - malformed JSON → send a fix-up turn asking the LLM to return
         valid JSON
       - schema-validation failure → send a fix-up turn citing the
         validation errors
  5. Non-retry provider errors (ProviderModelNotFound,
     ProviderAuthError, ProviderInvalidRequest, ProviderDecodeError)
     surface as ExtractionError(stage="provider") immediately.

Retry contract: ONE retry per invocation, not one retry per failure
mode. If the first HTTP call succeeds but the JSON fails to parse, we
spend the retry on a parse fix-up turn; if THAT succeeds HTTP-level
but also fails to parse, we raise ExtractionError. We do NOT chain
parse-retry → validate-retry. Total LLM call budget per invocation:
max 2.

The `outcome` metric label measures JSON QUALITY, not HTTP retry
count. A first-try JSON success where the HTTP call happened to hit
a 429 and retried is still `ok_first_try` — the `retry_total{reason}`
counter captures the HTTP retry separately.

Callers should pass a Pydantic BaseModel subclass that is the OUTER
wrapper shape of the expected response, e.g.:

    class EntityExtractionResponse(BaseModel):
        entities: list[EntityCandidate]

    result = await extract_json(
        EntityExtractionResponse,
        user_id=...,
        model_source="user_model",
        model_ref=...,
        system=load_prompt("entity_extraction_system", ...),
        user_prompt=load_prompt("entity_extraction_user", text=chunk),
        response_format={"type": "json_object"},
    )

Callers are encouraged to pass `response_format={"type": "json_object"}`
when their upstream provider supports it (OpenAI, some vLLM builds).
For providers that silently ignore `response_format` (Ollama, some
Anthropic routes), the prompt-level "return ONLY JSON" instruction
in the retry fix-up carries the load.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from app.clients.provider_client import (
    ChatCompletionResponse,
    ProviderAuthError,
    ProviderClient,
    ProviderDecodeError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUpstreamError,
    get_provider_client,
)
from app.logging_config import trace_id_var
from app.metrics import (
    llm_json_extraction_retry_total,
    llm_json_extraction_total,
)

__all__ = [
    "ExtractionError",
    "ExtractionStage",
    "extract_json",
]

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ExtractionStage = Literal[
    "retry_parse",
    "retry_validate",
    "provider",
    "provider_exhausted",
]

# Phase 3 review issue 4 — cap ValidationError text in fix-up prompts
# so a deeply nested error message doesn't blow the context budget.
_VALIDATION_ERROR_PROMPT_CAP = 1000


class ExtractionError(Exception):
    """Terminal failure from `extract_json`.

    Raised when the retry budget is exhausted or a non-retry provider
    error was encountered. `last_error` chains the underlying exception
    (ProviderError subclass, JSONDecodeError, or ValidationError).
    `raw_content` carries the last LLM output (even if malformed) so
    K16 job failure rows can persist it for post-mortem debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: ExtractionStage,
        trace_id: str | None = None,
        last_error: Exception | None = None,
        raw_content: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.trace_id = trace_id
        self.last_error = last_error
        self.raw_content = raw_content


# ── Message builders ─────────────────────────────────────────────────


def _build_initial_messages(
    system: str | None, user_prompt: str
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def _build_parse_retry_messages(
    system: str | None,
    user_prompt: str,
    bad_content: str,
    parse_error: str,
) -> list[dict[str, str]]:
    base = _build_initial_messages(system, user_prompt)
    base.append({"role": "assistant", "content": bad_content})
    base.append(
        {
            "role": "user",
            "content": (
                "The previous response could not be parsed as JSON. "
                f"Parser error: {parse_error}. "
                "Return ONLY the corrected JSON object — no prose, no "
                "code fences, no commentary. The JSON must match the "
                "schema requested in the original message."
            ),
        }
    )
    return base


def _build_validate_retry_messages(
    system: str | None,
    user_prompt: str,
    bad_content: str,
    validation_error: str,
) -> list[dict[str, str]]:
    base = _build_initial_messages(system, user_prompt)
    base.append({"role": "assistant", "content": bad_content})
    # Truncate overly-long ValidationError text to protect the
    # downstream context budget (Phase 3 review issue 4).
    if len(validation_error) > _VALIDATION_ERROR_PROMPT_CAP:
        validation_error = (
            validation_error[:_VALIDATION_ERROR_PROMPT_CAP] + "… (truncated)"
        )
    base.append(
        {
            "role": "user",
            "content": (
                "The previous response was valid JSON but did not "
                "match the requested schema. Validation errors: "
                f"{validation_error}. "
                "Return ONLY a corrected JSON object that matches the "
                "schema from the original message — no prose, no code "
                "fences, no commentary."
            ),
        }
    )
    return base


# ── Internal call-args bundle (Phase 3 review issue 3) ───────────────


@dataclass(frozen=True)
class _ChatCallArgs:
    """Parameters that don't change between the first attempt and the
    retry. Bundled so `extract_json` doesn't pass 10+ args through
    every internal helper.
    """

    user_id: str
    model_source: Literal["user_model", "platform_model"]
    model_ref: str
    temperature: float
    max_tokens: int | None
    response_format: dict[str, Any] | None


async def _call_chat(
    client: ProviderClient,
    call_args: _ChatCallArgs,
    messages: list[dict[str, str]],
) -> ChatCompletionResponse:
    return await client.chat_completion(
        user_id=call_args.user_id,
        model_source=call_args.model_source,
        model_ref=call_args.model_ref,
        messages=messages,
        response_format=call_args.response_format,
        temperature=call_args.temperature,
        max_tokens=call_args.max_tokens,
    )


# ── Metric helpers ───────────────────────────────────────────────────


def _inc_outcome(outcome: str) -> None:
    llm_json_extraction_total.labels(outcome=outcome).inc()


def _inc_retry(reason: str) -> None:
    llm_json_extraction_retry_total.labels(reason=reason).inc()


def _log_terminal_failure(
    stage: ExtractionStage,
    trace_id: str | None,
    last_error: Exception,
    model_source: str,
    model_ref: str,
) -> None:
    logger.warning(
        "llm_json_extraction outcome=%s stage=%s "
        "model_source=%s model_ref=%s trace_id=%s error=%s: %s",
        "failed",
        stage,
        model_source,
        model_ref,
        trace_id or "",
        type(last_error).__name__,
        str(last_error)[:500],
    )


# ── Public entry point ───────────────────────────────────────────────


async def extract_json(
    schema: type[T],
    *,
    user_id: str,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    system: str | None,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    client: ProviderClient | None = None,
) -> T:
    """Call LLM, parse content as JSON, validate against `schema`,
    retry once on failure.

    Returns a validated instance of `schema`. Raises `ExtractionError`
    on terminal failure (retries exhausted, or non-retry provider
    error). `client` is injectable for testing; production callers
    leave it `None` and the module-level singleton is used.
    """
    client = client or get_provider_client()
    trace_id = trace_id_var.get(None)
    call_args = _ChatCallArgs(
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )

    # ── First HTTP attempt (with provider-level retry) ────────────────
    #
    # R1 E1 DRY refactor — the three retry-eligible branches used to
    # be near-identical 17-line duplicates. Collapsed into a single
    # except that classifies the reason label and conditionally sleeps
    # for ProviderRateLimited.retry_after_s.

    response: ChatCompletionResponse
    initial_messages = _build_initial_messages(system, user_prompt)
    try:
        response = await _call_chat(client, call_args, initial_messages)
    except (ProviderRateLimited, ProviderUpstreamError, ProviderTimeout) as exc:
        if isinstance(exc, ProviderRateLimited):
            retry_reason = "rate_limited"
            # R1 E2 — `if exc.retry_after_s:` is intentionally falsy
            # for both None and 0.0. A server that sends
            # `Retry-After: 0` means "retry immediately" — skipping
            # sleep is correct, not a bug.
            retry_after = exc.retry_after_s
        elif isinstance(exc, ProviderUpstreamError):
            retry_reason = "upstream"
            retry_after = None
        else:
            retry_reason = "timeout"
            retry_after = None

        _inc_retry(retry_reason)
        if retry_after:
            await sleep_fn(retry_after)

        try:
            response = await _call_chat(client, call_args, initial_messages)
        except ProviderError as exc2:
            # R1 E3 — a retry that hits a non-retry provider error
            # (ProviderModelNotFound / ProviderAuthError / etc.) is
            # still bucketed as `provider_exhausted` for simplicity.
            # The edge case is rare in practice; if K17.9 golden-set
            # shows it matters, split the bucket then.
            _inc_outcome("provider_exhausted")
            _log_terminal_failure(
                "provider_exhausted", trace_id, exc2, model_source, model_ref
            )
            raise ExtractionError(
                f"extraction failed after {retry_reason} retry: {exc2}",
                stage="provider_exhausted",
                trace_id=trace_id,
                last_error=exc2,
            ) from exc2
    except (
        ProviderModelNotFound,
        ProviderAuthError,
        ProviderInvalidRequest,
        ProviderDecodeError,
    ) as exc:
        _inc_outcome("provider_non_retry")
        _log_terminal_failure(
            "provider", trace_id, exc, model_source, model_ref
        )
        raise ExtractionError(
            f"extraction failed: {exc}",
            stage="provider",
            trace_id=trace_id,
            last_error=exc,
        ) from exc

    # ── First HTTP response is in hand — parse and validate ───────────

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as exc:
        _inc_retry("parse")
        return await _do_fix_up(
            schema,
            client,
            call_args,
            _build_parse_retry_messages(
                system, user_prompt, response.content, str(exc)
            ),
            trace_id=trace_id,
            model_source=model_source,
            model_ref=model_ref,
        )

    try:
        validated = schema.model_validate(parsed)
    except ValidationError as exc:
        _inc_retry("validate")
        return await _do_fix_up(
            schema,
            client,
            call_args,
            _build_validate_retry_messages(
                system, user_prompt, response.content, str(exc)
            ),
            trace_id=trace_id,
            model_source=model_source,
            model_ref=model_ref,
        )

    _inc_outcome("ok_first_try")
    logger.debug(
        "llm_json_extraction outcome=ok_first_try "
        "model_source=%s model_ref=%s trace_id=%s",
        model_source,
        model_ref,
        trace_id or "",
    )
    return validated


# ── Fix-up helper (called after a parse or validate failure) ─────────


async def _do_fix_up(
    schema: type[T],
    client: ProviderClient,
    call_args: _ChatCallArgs,
    messages: list[dict[str, str]],
    *,
    trace_id: str | None,
    model_source: str,
    model_ref: str,
) -> T:
    """Single fix-up attempt. On ANY failure (provider, parse, or
    validate), raise `ExtractionError` — the retry budget is spent.

    Note: the `messages` list already includes the fix-up turn, so
    the caller builds the full conversation. We just issue the call
    and interpret the response.
    """
    try:
        response = await _call_chat(client, call_args, messages)
    except ProviderError as exc:
        _inc_outcome("provider_exhausted")
        _log_terminal_failure(
            "provider_exhausted", trace_id, exc, model_source, model_ref
        )
        raise ExtractionError(
            f"extraction fix-up failed with provider error: {exc}",
            stage="provider_exhausted",
            trace_id=trace_id,
            last_error=exc,
        ) from exc

    raw = response.content

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _inc_outcome("parse_exhausted")
        _log_terminal_failure(
            "retry_parse", trace_id, exc, model_source, model_ref
        )
        raise ExtractionError(
            f"extraction failed: retry still returned unparseable JSON: {exc}",
            stage="retry_parse",
            trace_id=trace_id,
            last_error=exc,
            raw_content=raw,
        ) from exc

    try:
        validated = schema.model_validate(parsed)
    except ValidationError as exc:
        _inc_outcome("validate_exhausted")
        _log_terminal_failure(
            "retry_validate", trace_id, exc, model_source, model_ref
        )
        raise ExtractionError(
            f"extraction failed: retry still failed schema validation: {exc}",
            stage="retry_validate",
            trace_id=trace_id,
            last_error=exc,
            raw_content=raw,
        ) from exc

    _inc_outcome("ok_after_retry")
    logger.info(
        "llm_json_extraction outcome=ok_after_retry "
        "model_source=%s model_ref=%s trace_id=%s",
        model_source,
        model_ref,
        trace_id or "",
    )
    return validated
