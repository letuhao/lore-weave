"""The real generation LLM seam (RAID C14) — binds C11's ``CompleteFn`` to
provider-registry ``POST /internal/llm/stream``.

C11 (``app.generation.generate``) deferred the real LLM binding to orchestration
(exactly as C10 deferred its embed binding), taking the completion as an injected
``CompleteFn`` so tests stay deterministic. This module is the ONE place that
wires the real call: it streams a chat completion from provider-registry and
collects the token deltas into the full generated text.

Like the embed seam, the model is resolved by a provider-registry ``model_ref``
(a ``user_model`` UUID) read off the :class:`StrategyContext` — NO model NAME is
ever passed. The generating model (a Classical-Chinese-strong model served over
LM Studio) is referenced only by its registry ref.

SSE contract (provider-registry stream_handler.go): the response is an SSE stream
of ``event: token`` frames carrying ``{"event":"token","delta":"…"}``, optional
``event: reasoning`` frames (thinking output — NOT part of the answer, dropped),
terminated by ``event: done`` (or ``event: error``). We collect the ``token``
deltas in order into the final text.

JIT tolerance: the first call to a cold LM Studio model can be slow (model load);
the timeout is generous and the demo wrapper retries. NO retry logic here — the
seam is a single streaming call; retry/backoff is the caller's (demo) concern.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app import metrics
from app.jobs.tokens import TokenUsage, UsageMeter, estimate_tokens
from app.strategies.base import StrategyContext

__all__ = [
    "CompletionSeamError",
    "MODEL_SOURCE",
    "make_complete_fn",
    "collect_stream_text",
    "collect_stream_usage",
]

#: provider-registry model source — ``user_model`` resolves a BYOK user_model row
#: by its UUID. A SOURCE selector, NOT a model name (no model id appears here).
MODEL_SOURCE: str = "user_model"


class CompletionSeamError(RuntimeError):
    """A generation completion call failed (transport / upstream / SSE error)."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def collect_stream_text(sse_text: str) -> str:
    """Collect the ``token`` deltas from a provider-registry SSE body into text.

    Parses ``event: <name>\\ndata: <json>\\n\\n`` frames. Concatenates the
    ``delta`` of every ``token`` frame in order; ignores ``reasoning`` (thinking
    output, not the answer) and ``usage`` frames; raises on an ``error`` frame.
    Tolerant of blank lines + multi-line frames."""
    parts: list[str] = []
    event_name: str | None = None
    data_lines: list[str] = []

    def _flush() -> None:
        nonlocal event_name, data_lines
        if event_name is None and not data_lines:
            return
        raw = "\n".join(data_lines).strip()
        try:
            payload: dict[str, Any] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        kind = event_name or payload.get("event")
        if kind == "token":
            delta = payload.get("delta")
            if isinstance(delta, str):
                parts.append(delta)
        elif kind == "error":
            msg = payload.get("message") or payload.get("code") or "stream error"
            raise CompletionSeamError(f"LLM stream error: {msg}")
        event_name = None
        data_lines = []

    for line in sse_text.splitlines():
        if line == "":
            _flush()
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    _flush()  # final frame without a trailing blank line
    return "".join(parts)


def collect_stream_usage(sse_text: str) -> TokenUsage | None:
    """Parse the LLM stream's ``event: usage`` frame into a :class:`TokenUsage`.

    The provider-registry stream emits one terminal ``usage`` frame carrying
    ``{"input_tokens": …, "output_tokens": …, "reasoning_tokens": …?}`` (C1 token
    metering, DEFERRED-052). Reasoning tokens FOLD INTO output — matching how the
    platform bills reasoning at the output rate (provider-registry stream_billing).
    Returns ``None`` when no usage frame is present (provider omitted it) so the
    caller can fall back to a char-based estimate. Tolerant of blank/partial lines.
    """
    found: TokenUsage | None = None
    event_name: str | None = None
    data_lines: list[str] = []

    def _flush() -> None:
        nonlocal event_name, data_lines, found
        if event_name is None and not data_lines:
            return
        raw = "\n".join(data_lines).strip()
        try:
            payload: dict[str, Any] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        kind = event_name or payload.get("event")
        if kind == "usage":
            # Clamp to >= 0: a buggy/hostile upstream must never REDUCE metered
            # spend with negative counts (the cap is a safety control).
            inp = max(0, int(payload.get("input_tokens", 0) or 0))
            out = max(0, int(payload.get("output_tokens", 0) or 0))
            reasoning = max(0, int(payload.get("reasoning_tokens", 0) or 0))
            found = TokenUsage(input_tokens=inp, output_tokens=out + reasoning)
        event_name = None
        data_lines = []

    for line in sse_text.splitlines():
        if line == "":
            _flush()
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    _flush()
    return found


def make_complete_fn(
    *,
    provider_registry_base_url: str,
    internal_token: str,
    timeout_s: float = 180.0,
    meter: UsageMeter | None = None,
):
    """Build a real C11 ``CompleteFn`` over provider-registry ``/internal/llm/stream``.

    The returned ``async (prompt, context) -> str`` submits a single-message chat
    completion (the schema-governed Chinese generation prompt), streams the
    response, and returns the concatenated token text. ``context.model_ref`` is
    the generating user_model id (resolved by provider-registry); ``context.user_id``
    scopes the BYOK lookup. NO model name is sent — only the ref.

    The timeout is generous to tolerate a cold (JIT-loading) LM Studio model on
    the first call; the demo wrapper additionally retries on a retryable error.

    ``meter`` (C1 / DEFERRED-052): when supplied, the REAL token usage of each
    completion is recorded into it for the per-job cost-cap reconcile — harvested
    from the stream's ``usage`` frame, or (when the provider omits it) ESTIMATED
    from the prompt (input) + collected text (output) via the platform
    char-convention so generation is ALWAYS metered. The return type is unchanged
    (``str``) — metering is a side effect on the meter, NOT a contract change, so
    the fabrication/recook seams + every test stub are unaffected.
    """

    base = provider_registry_base_url.rstrip("/")

    async def _complete(prompt: str, context: StrategyContext) -> str:
        # C18 — count the real LLM completion call by outcome (NO model name in
        # the label; the model is resolved by model_ref at runtime).
        try:
            text, usage = await _complete_inner(prompt, context)
        except Exception:
            metrics.llm_calls_total.labels(outcome="error").inc()
            raise
        metrics.llm_calls_total.labels(outcome="ok").inc()
        if meter is not None:
            # Real usage frame when present AND informative; else the platform
            # char-estimate of prompt (input) + generated text (output). A frame
            # that is absent (None) OR present-but-empty (total == 0, e.g. a
            # provider that emits `event: usage` without counts) is NOT a real
            # measurement — fall back to the estimate so a gap is NEVER metered
            # as 0 tokens (which would silently weaken the cost-cap, DEFERRED-052).
            if usage is not None and usage.total > 0:
                meter.add(usage)
            else:
                meter.add(
                    TokenUsage(
                        input_tokens=estimate_tokens(prompt),
                        output_tokens=estimate_tokens(text),
                    )
                )
        return text

    async def _complete_inner(
        prompt: str, context: StrategyContext
    ) -> tuple[str, TokenUsage | None]:
        if not context.model_ref:
            raise CompletionSeamError(
                "StrategyContext.model_ref is required for generation "
                "(resolve the project's generation model via provider-registry)"
            )
        url = f"{base}/internal/llm/stream"
        body = {
            "operation": "chat",
            "model_source": MODEL_SOURCE,
            "model_ref": context.model_ref,
            "messages": [{"role": "user", "content": prompt}],
        }
        # ensure_ascii=False so the Chinese prompt travels as genuine UTF-8.
        content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "X-Internal-Token": internal_token,
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {"user_id": context.user_id}
        timeout = httpx.Timeout(timeout_s, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    url, headers=headers, params=params, content=content
                )
        except httpx.TimeoutException as exc:
            raise CompletionSeamError(
                f"timeout calling {url}: {exc}", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise CompletionSeamError(
                f"connection error calling {url}: {exc}", retryable=True
            ) from exc
        if resp.status_code != 200:
            retryable = resp.status_code in (429, 502, 503, 504)
            raise CompletionSeamError(
                f"POST {url} failed ({resp.status_code}): {resp.text[:300]}",
                retryable=retryable,
            )
        text = collect_stream_text(resp.text)
        if not text.strip():
            raise CompletionSeamError(
                "LLM stream produced no token text (empty completion)",
                retryable=True,
            )
        # Harvest the terminal usage frame (None when the provider omits it; the
        # caller then estimates from prompt+text — DEFERRED-052).
        usage = collect_stream_usage(resp.text)
        return text, usage

    return _complete
