"""K17.2 — provider-registry BYOK LLM client.

Calls provider-registry's transparent proxy at
    POST /internal/proxy/v1/chat/completions?user_id=&model_source=&model_ref=
The proxy resolves the caller's BYOK credentials, rewrites the request
body's "model" field to the server-resolved provider model name (K17.2a),
and forwards to the upstream provider with the API key injected. This
module never sees the provider's API key.

Body size cap: provider-registry enforces a 4 MiB hard limit on JSON
request bodies (PROXY_BODY_TOO_LARGE → HTTP 413). Chat-completion bodies
are almost always under 100 KB even with context-stuffed prompts, so
hitting this cap means either:
  (a) an extractor is feeding a whole book at once — split the input,
  (b) known_entities substitution in a K17.1 prompt is pathologically
      large — cap it at the extractor layer,
  (c) a bug. This client classifies 413 as `ProviderUpstreamError` with
      an explicit "body too large" message so the cause is greppable in
      job-failure rows.

Unlike `glossary_client`, this client does NOT gracefully degrade. An
extraction call that can't reach the LLM must fail loudly so the K16
job state machine can quarantine the job and the K17.3 retry wrapper
can decide whether to retry. Graceful-degrade would produce empty
extraction results that look identical to a successful "this text
contained nothing extractable" — exactly the bug that motivated the
whole Pass 1 quarantine + Pass 2 validator pipeline in the first place.

Retry is NOT this layer's concern. K17.3 wraps this client with a
parse-validate-retry loop for JSON-mode extraction calls. The
exception hierarchy below is designed so K17.3 can whitelist
retry-eligible errors with a single `except` tuple:

    retry_on = (ProviderRateLimited, ProviderUpstreamError, ProviderTimeout)

Non-retry errors (`ProviderModelNotFound`, `ProviderAuthError`,
`ProviderInvalidRequest`, `ProviderDecodeError`) won't get better on
retry — the job should fail immediately.

Lifecycle: one `ProviderClient` per knowledge-service worker process,
constructed in the lifespan hook and closed on shutdown. Same
per-worker singleton pattern as `glossary_client` — see that module's
docstring for the rationale.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal, get_args

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.logging_config import trace_id_var
from app.metrics import (
    provider_chat_completion_duration_seconds,
    provider_chat_completion_total,
)

# K17.2b-R3 D1 — derive the runtime tuple from the Literal so a future
# edit that adds a new source to the Literal automatically updates
# local validation. Same pattern as K17.1-R2 ALLOWED_PROMPT_NAMES.
ModelSource = Literal["user_model", "platform_model"]
_VALID_MODEL_SOURCES: tuple[str, ...] = tuple(get_args(ModelSource))

__all__ = [
    "ProviderClient",
    "ChatCompletionResponse",
    "ChatCompletionUsage",
    "ProviderError",
    "ProviderInvalidRequest",
    "ProviderModelNotFound",
    "ProviderAuthError",
    "ProviderRateLimited",
    "ProviderUpstreamError",
    "ProviderTimeout",
    "ProviderDecodeError",
    "get_provider_client",
    "close_provider_client",
]

logger = logging.getLogger(__name__)


# ── K17.12 — Token-bucket rate limiter ───────────────────────────────


class _TokenBucket:
    """Simple per-user token-bucket rate limiter.

    max_rate: max calls per second per user.
    Each user gets their own bucket. Tokens refill continuously.
    Thread-safe within asyncio (single-threaded event loop).
    """

    def __init__(self, max_rate: float = 10.0) -> None:
        self._max_rate = max_rate
        # user_id → (tokens, last_refill_monotonic).
        # Grows unbounded — acceptable at hobby scale (few users).
        # For shared deployments, add a periodic sweep of entries
        # older than 1 minute.
        self._buckets: dict[str, tuple[float, float]] = {}

    async def acquire(self, user_id: str) -> None:
        """Wait until a token is available for this user."""
        now = time.monotonic()
        tokens, last = self._buckets.get(user_id, (self._max_rate, now))

        # Refill tokens based on elapsed time
        elapsed = now - last
        tokens = min(self._max_rate, tokens + elapsed * self._max_rate)

        if tokens < 1.0:
            # Wait for a token to become available
            wait = (1.0 - tokens) / self._max_rate
            await asyncio.sleep(wait)
            tokens = 1.0

        tokens -= 1.0
        self._buckets[user_id] = (tokens, time.monotonic())


# Module-level rate limiter shared by all ProviderClient instances.
_rate_limiter = _TokenBucket(max_rate=10.0)


# ── Exception hierarchy ───────────────────────────────────────────────

class ProviderError(Exception):
    """Base for every provider_client error.

    Carries `trace_id` (snapshotted at raise time) and `status_code`
    so K17.3 retry logic and K16 job failure rows can log without a
    second ContextVar lookup.
    """

    def __init__(
        self,
        message: str,
        *,
        trace_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.trace_id = trace_id
        self.status_code = status_code


class ProviderInvalidRequest(ProviderError):
    """Local validation failed before the HTTP call was issued.

    Caller bug — malformed args, empty messages, bad model_source.
    Non-retryable: retrying with the same args will always fail.
    """


class ProviderModelNotFound(ProviderError):
    """404 — model_source/model_ref did not resolve. Non-retryable."""


class ProviderAuthError(ProviderError):
    """401/403 — provider credentials rejected. Non-retryable."""


class ProviderRateLimited(ProviderError):
    """429 — retry with backoff.

    `retry_after_s` (K17.2b-R3 D8) is the upstream provider's
    requested backoff in seconds, parsed from the `Retry-After`
    response header. It is `None` when the header is absent or
    unparseable. K17.3 retry logic should prefer this value over
    its own exponential backoff when present — honoring upstream
    hints avoids pathological retry storms and banned keys.
    """

    def __init__(
        self,
        message: str,
        *,
        trace_id: str | None = None,
        status_code: int | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message, trace_id=trace_id, status_code=status_code)
        self.retry_after_s = retry_after_s


class ProviderUpstreamError(ProviderError):
    """5xx, 502 PROXY_UPSTREAM_ERROR, or connection error. Retry-eligible."""


class ProviderTimeout(ProviderError):
    """httpx.TimeoutException wrapper. Retry-eligible."""


class ProviderDecodeError(ProviderError):
    """2xx but body was missing `choices[0].message.content`. Non-retryable."""


# ── Response models ───────────────────────────────────────────────────

class ChatCompletionUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """Parsed response from provider-registry's chat completion proxy.

    Only `content` is guaranteed populated — it's the first choice's
    message content, which every OpenAI-compatible provider returns.
    `model` is echoed from the upstream's body (may differ from the
    resolved name in edge cases like LiteLLM routing).

    `raw` is the full upstream body. K17.9 golden-set harness and
    telemetry code MAY read from it; extractors (K17.4–K17.7) MUST
    NOT — they should consume only `content`. This is a convention,
    not enforced by code.
    """

    model_config = ConfigDict(extra="ignore")

    content: str
    model: str = ""
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
    raw: dict[str, Any] = Field(default_factory=dict)


# ── Client ────────────────────────────────────────────────────────────


class ProviderClient:
    """Thin async wrapper around httpx.AsyncClient for the BYOK proxy.

    One instance per knowledge-service worker process. Not thread-safe,
    but asyncio is single-threaded within a worker so that's fine.
    Construct in lifespan, close via `aclose()` on shutdown.
    """

    def __init__(
        self,
        *,
        base_url: str,
        internal_token: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,  # test hook only
    ) -> None:
        # K17.2b-R3 D12 — parse the base URL at construction time so
        # a misconfigured setting fails fast in the startup lifespan
        # hook (per the module docstring promise) rather than silently
        # constructing a client that errors on the first extraction
        # call. `httpx.URL` raises `httpx.InvalidURL` on garbage input.
        parsed = httpx.URL(base_url)
        if not parsed.scheme or not parsed.host:
            raise httpx.InvalidURL(
                f"provider_registry_internal_url missing scheme or host: {base_url!r}"
            )

        self._base_url = base_url.rstrip("/")
        # Separate connect and overall budgets: 5s to establish the
        # TCP+TLS handshake (fails fast when provider-registry is
        # down), full timeout_s for the read which covers LLM
        # generation time.
        timeout = httpx.Timeout(timeout_s, connect=5.0)
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"X-Internal-Token": internal_token},
            transport=transport,
        )

    async def aclose(self) -> None:
        if self._http.is_closed:
            return
        await self._http.aclose()

    async def chat_completion(
        self,
        *,
        user_id: str,
        model_source: Literal["user_model", "platform_model"],
        model_ref: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatCompletionResponse:
        """Invoke an OpenAI-shaped chat completion via the BYOK proxy.

        Args follow the OpenAI chat-completions schema. `response_format`
        is pass-through: K17.3+ callers that need JSON mode should pass
        `{"type": "json_object"}`; we do not enforce it at this layer
        because different providers (Ollama, vLLM) silently ignore it.

        The `model` field in the request body is overwritten server-side
        by provider-registry (K17.2a), so we send a placeholder that the
        proxy will rewrite before forwarding upstream.
        """
        trace_id = trace_id_var.get(None)
        outcome = "ok"  # mutated by the classifier below
        started = False
        start = 0.0

        try:
            # Local validation — raise as ProviderInvalidRequest so
            # K17.3 and K16 can catch the whole family with
            # `except ProviderError`.
            if model_source not in _VALID_MODEL_SOURCES:
                outcome = "invalid_request"
                raise ProviderInvalidRequest(
                    f"model_source must be one of {_VALID_MODEL_SOURCES}",
                    trace_id=trace_id,
                )
            if not model_ref:
                outcome = "invalid_request"
                raise ProviderInvalidRequest(
                    "model_ref is required",
                    trace_id=trace_id,
                )
            if not user_id:
                outcome = "invalid_request"
                raise ProviderInvalidRequest(
                    "user_id is required",
                    trace_id=trace_id,
                )
            if not messages:
                outcome = "invalid_request"
                raise ProviderInvalidRequest(
                    "messages must be non-empty",
                    trace_id=trace_id,
                )

            # K17.12 — rate limit before making the LLM call
            await _rate_limiter.acquire(user_id)

            # Build URL + body. The proxy rewrites `model` (K17.2a)
            # but OpenAI-schema clients reject a missing field, so we
            # send a placeholder string.
            url = f"{self._base_url}/internal/proxy/v1/chat/completions"
            params = {
                "user_id": user_id,
                "model_source": model_source,
                "model_ref": model_ref,
            }
            body: dict[str, Any] = {
                "model": "proxy-resolved",
                "messages": messages,
                "temperature": temperature,
            }
            if response_format is not None:
                body["response_format"] = response_format
            if max_tokens is not None:
                body["max_tokens"] = max_tokens

            headers: dict[str, str] = {}
            if trace_id:
                headers["X-Trace-Id"] = trace_id

            started = True
            start = time.perf_counter()
            try:
                resp = await self._http.post(
                    url, params=params, json=body, headers=headers
                )
            except httpx.TimeoutException as exc:
                outcome = "timeout"
                raise ProviderTimeout(
                    f"provider chat completion timed out: {exc}",
                    trace_id=trace_id,
                ) from exc
            except httpx.RequestError as exc:
                outcome = "upstream"
                raise ProviderUpstreamError(
                    f"provider chat completion request failed: {exc}",
                    trace_id=trace_id,
                ) from exc

            # Classify the HTTP status.
            status = resp.status_code
            if status == 404:
                outcome = "not_found"
                raise ProviderModelNotFound(
                    "model not found or inactive",
                    trace_id=trace_id,
                    status_code=status,
                )
            if status in (401, 403):
                outcome = "auth"
                raise ProviderAuthError(
                    f"provider auth failed: HTTP {status}",
                    trace_id=trace_id,
                    status_code=status,
                )
            if status == 429:
                outcome = "rate_limited"
                # K17.2b-R3 D8: honor upstream Retry-After when
                # present. Only the "delta-seconds" form is parsed;
                # HTTP-date form (RFC 7231) is rarer in LLM providers
                # and is intentionally ignored — K17.3 will fall back
                # to exponential backoff when retry_after_s is None.
                retry_after_s: float | None = None
                retry_after_raw = resp.headers.get("Retry-After")
                if retry_after_raw:
                    try:
                        retry_after_s = float(retry_after_raw.strip())
                        if retry_after_s < 0:
                            retry_after_s = None
                    except ValueError:
                        retry_after_s = None
                raise ProviderRateLimited(
                    "provider rate limited",
                    trace_id=trace_id,
                    status_code=status,
                    retry_after_s=retry_after_s,
                )
            if status == 413:
                # K17.2a-R3 (C12): provider-registry enforces a 4 MiB
                # hard cap on JSON bodies. Classify distinctly so the
                # failure reason is obvious in job-failure rows — this
                # almost always means the caller needs to split its
                # input rather than retry.
                outcome = "upstream"
                raise ProviderUpstreamError(
                    "provider rejected request: body too large "
                    "(PROXY_BODY_TOO_LARGE, 4 MiB cap)",
                    trace_id=trace_id,
                    status_code=status,
                )
            if status >= 500:
                outcome = "upstream"
                raise ProviderUpstreamError(
                    f"provider upstream error: HTTP {status}",
                    trace_id=trace_id,
                    status_code=status,
                )
            if status >= 400:
                # Any other 4xx — validation errors, unsupported
                # method, etc. Fold into upstream so the job fails
                # without retry.
                outcome = "upstream"
                raise ProviderUpstreamError(
                    f"provider rejected request: HTTP {status}",
                    trace_id=trace_id,
                    status_code=status,
                )

            # 2xx — decode body.
            try:
                body_json = resp.json()
            except ValueError as exc:
                outcome = "decode"
                raise ProviderDecodeError(
                    f"provider response was not JSON: {exc}",
                    trace_id=trace_id,
                    status_code=status,
                ) from exc

            # Issue 7 (Phase 3 review) + B5 (R1 review): 200 with an
            # `error` object is how some providers surface throttling
            # or downstream failures under LiteLLM. Re-classify by the
            # error shape.
            #
            # B5 fix: the earlier guard `"choices" not in body_json`
            # was wrong — a 200 with {"choices": [], "error": {...}}
            # would skip reclassification and raise ProviderDecodeError,
            # robbing K17.3 of its retry signal. Instead: if the body
            # carries a non-null error object, classify it first. If
            # the classification finds nothing actionable (empty error
            # dict), fall through to the normal choices-decoding path.
            if isinstance(body_json, dict):
                err_obj = body_json.get("error")
                if isinstance(err_obj, dict) and err_obj:
                    err_type = str(err_obj.get("type") or err_obj.get("code") or "")
                    err_msg = str(err_obj.get("message") or "")
                    if "rate" in err_type.lower() or "rate" in err_msg.lower():
                        outcome = "rate_limited"
                        raise ProviderRateLimited(
                            f"provider returned rate error in 200 body: {err_msg}",
                            trace_id=trace_id,
                            status_code=status,
                        )
                    outcome = "upstream"
                    raise ProviderUpstreamError(
                        f"provider returned error in 200 body: {err_msg or err_type}",
                        trace_id=trace_id,
                        status_code=status,
                    )

            choices = body_json.get("choices") if isinstance(body_json, dict) else None
            if not choices or not isinstance(choices, list):
                outcome = "decode"
                raise ProviderDecodeError(
                    "provider response missing choices",
                    trace_id=trace_id,
                    status_code=status,
                )
            first = choices[0] or {}
            message = first.get("message") or {}
            content = message.get("content")
            if not isinstance(content, str):
                outcome = "decode"
                raise ProviderDecodeError(
                    "provider response missing choices[0].message.content",
                    trace_id=trace_id,
                    status_code=status,
                )

            usage_obj = body_json.get("usage") if isinstance(body_json.get("usage"), dict) else {}
            return ChatCompletionResponse(
                content=content,
                model=str(body_json.get("model") or ""),
                usage=ChatCompletionUsage(**usage_obj),
                raw=body_json,
            )

        finally:
            # Counter fires on every path. Histogram fires only when
            # the HTTP attempt actually started — invalid_request fails
            # before the timer so observing a zero would be misleading.
            provider_chat_completion_total.labels(outcome=outcome).inc()
            elapsed: float | None = None
            if started:
                elapsed = time.perf_counter() - start
                provider_chat_completion_duration_seconds.labels(
                    outcome=outcome
                ).observe(elapsed)

            # K17.2b-R3 D7 — structured log so ops can correlate a
            # failing extraction back to trace_id + outcome + model_ref
            # without having to cross-reference metrics and exception
            # text. WARNING on failure (grep-friendly), DEBUG on
            # success (verbose only when explicitly enabled).
            if outcome == "ok":
                logger.debug(
                    "provider_chat_completion outcome=ok "
                    "model_source=%s model_ref=%s elapsed_s=%.3f trace_id=%s",
                    model_source,
                    model_ref,
                    elapsed if elapsed is not None else -1.0,
                    trace_id or "",
                )
            else:
                logger.warning(
                    "provider_chat_completion outcome=%s "
                    "model_source=%s model_ref=%s elapsed_s=%s trace_id=%s",
                    outcome,
                    model_source,
                    model_ref,
                    f"{elapsed:.3f}" if elapsed is not None else "n/a",
                    trace_id or "",
                )


# ── Module-level singleton ────────────────────────────────────────────

_client: ProviderClient | None = None


def get_provider_client() -> ProviderClient:
    global _client
    if _client is None:
        _client = ProviderClient(
            base_url=settings.provider_registry_internal_url,
            internal_token=settings.internal_service_token,
            timeout_s=settings.provider_client_timeout_s,
        )
    return _client


async def close_provider_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
