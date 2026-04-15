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

Retry contract: the HTTP-retry budget and the JSON-retry budget are
independent; each is capped at 1 retry. The maximum total LLM call
count per `extract_json` invocation is therefore THREE:

  1. Initial HTTP call (always)
  2. Optional HTTP retry if the initial call raised a retry-eligible
     provider error (ProviderRateLimited / ProviderUpstreamError /
     ProviderTimeout). Honors Retry-After for rate limiting.
  3. Optional JSON fix-up retry if the response from step 1 or step 2
     failed to parse as JSON OR failed Pydantic validation.

We do NOT chain parse-retry → validate-retry within the JSON-retry
budget: if the fix-up call itself returns unparseable or invalid-shape
JSON, we raise ExtractionError immediately. The "one retry" is one
fix-up turn, not one retry per failure mode on the same turn.

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
import re
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

# R3 F6 — cap LLM-echoed content in retry prompts so a pathological
# response (entire chapter echoed back) cannot double the retry's
# context size and blow past the proxy's 4 MiB body cap.
_BAD_CONTENT_PROMPT_CAP = 8000

# R3 F9 — LLMs frequently wrap JSON in markdown code fences even when
# asked not to. Local models (Ollama, LM Studio) do this routinely
# regardless of `response_format`. Strip common fence patterns before
# `json.loads` on BOTH first attempt and retry so we don't burn the
# fix-up retry budget on a pure-formatting issue.
#
# Patterns handled:
#   ```json\n{...}\n```
#   ```\n{...}\n```
#   ```json{...}```          (no leading newline, some models)
# Matches the first fenced block only — trailing text (e.g. "Here is
# the JSON:" prose after the fence) is left to the LLM prompt to
# discourage rather than the parser to handle.
_CODE_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)


def _strip_code_fences(content: str) -> str:
    """Return the content inside the first ```...``` block, or the
    original content if no fence is found. Whitespace-trimmed.

    R3 F9. Handles the common "LLM ignored the instructions and wrapped
    its JSON in a markdown fence" failure mode without burning a retry.
    """
    stripped = content.strip()
    match = _CODE_FENCE_RE.search(stripped)
    if match:
        return match.group(1).strip()
    return stripped


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


def _cap_bad_content(bad_content: str) -> str:
    """R3 F6 — cap LLM-echoed content so the retry prompt can't blow
    the context budget on a pathological echo. 8 KB is generous for
    any realistic JSON response; anything longer is almost certainly
    the LLM echoing its entire input back."""
    if len(bad_content) > _BAD_CONTENT_PROMPT_CAP:
        return bad_content[:_BAD_CONTENT_PROMPT_CAP] + "… (previous response truncated)"
    return bad_content


def _build_parse_retry_messages(
    system: str | None,
    user_prompt: str,
    bad_content: str,
    parse_error: str,
) -> list[dict[str, str]]:
    base = _build_initial_messages(system, user_prompt)
    base.append({"role": "assistant", "content": _cap_bad_content(bad_content)})
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
    base.append({"role": "assistant", "content": _cap_bad_content(bad_content)})
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
    # R3 F8 — collapse newlines so Pydantic ValidationError (which is
    # multi-line) still produces a single grep-friendly log line.
    error_line = str(last_error)[:500].replace("\n", " ").replace("\r", " ")
    logger.warning(
        "llm_json_extraction outcome=%s stage=%s "
        "model_source=%s model_ref=%s trace_id=%s error=%s: %s",
        "failed",
        stage,
        model_source,
        model_ref,
        trace_id or "",
        type(last_error).__name__,
        error_line,
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
        retry_after: float | None = None
        if isinstance(exc, ProviderRateLimited):
            retry_reason = "rate_limited"
            # R1 E2 — `if retry_after:` is intentionally falsy for both
            # None and 0.0. A server that sends `Retry-After: 0` means
            # "retry immediately" — skipping sleep is correct.
            retry_after = exc.retry_after_s
        elif isinstance(exc, ProviderUpstreamError):
            retry_reason = "upstream"
        elif isinstance(exc, ProviderTimeout):
            retry_reason = "timeout"
        else:
            # R3 F3 — unreachable today (flat provider-error hierarchy,
            # the except tuple explicitly enumerates the three types)
            # but guards against a future refactor that makes one class
            # inherit from another and silently drops into the wrong
            # elif branch. Raises loudly instead of misclassifying.
            raise AssertionError(
                f"unexpected retry-eligible provider error class: "
                f"{type(exc).__name__}"
            ) from exc

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

    first_attempt_content = response.content
    cleaned = _strip_code_fences(first_attempt_content)  # R3 F9
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        _inc_retry("parse")
        return await _do_fix_up(
            schema,
            client,
            call_args,
            _build_parse_retry_messages(
                system, user_prompt, first_attempt_content, str(exc)
            ),
            trace_id=trace_id,
            model_source=model_source,
            model_ref=model_ref,
            first_attempt_content=first_attempt_content,
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
                system, user_prompt, first_attempt_content, str(exc)
            ),
            trace_id=trace_id,
            model_source=model_source,
            model_ref=model_ref,
            first_attempt_content=first_attempt_content,
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
    first_attempt_content: str,
) -> T:
    """Single fix-up attempt. On ANY failure (provider, parse, or
    validate), raise `ExtractionError` — the retry budget is spent.

    Note: the `messages` list already includes the fix-up turn, so
    the caller builds the full conversation. We just issue the call
    and interpret the response.

    R3 F2/F4 — `first_attempt_content` is threaded through so a
    provider-exhausted fix-up raise still populates
    `ExtractionError.raw_content` with the original bad output. Without
    this, the debugging context is lost: operators see "fix-up hit a
    502" but have no record of what the first attempt returned.
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
            raw_content=first_attempt_content,  # R3 F2/F4
        ) from exc

    raw = response.content
    cleaned = _strip_code_fences(raw)  # R3 F9

    try:
        parsed = json.loads(cleaned)
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
