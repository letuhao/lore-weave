"""WS-1.8 (spec 06) — the journal distiller ORCHESTRATOR.

Connects the three pieces built separately: the chat-service day-window READ (§Q10 input), the
pure map-reduce CORE (distiller.py), and the book-service diary-entry WRITE (§Q10 output). This is
the read → distill → write flow for ONE (user, diary, local-day), with the model call injected so
it is fully unit-testable with fakes.

Deliberately thin and side-effect-honest: it never fabricates success. Each terminal state is
explicit — written / no_entry (low-signal, §Q11) / oversized (giant paste to attach, §T38) /
kept (a post-confirm day → the caller supplements) / retryable failure — so the trigger layer
(the "End my day" endpoint + the bounded catch-up sweep, built next) can act on it and the home
strip can show it. The durable per-chunk checkpoint store (§Q5) and the SDK/model resolution are
the remaining wiring around this orchestrator.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.distiller import (
    GIANT_PASTE_CHARS,
    WINDOW_CHARS,
    DayMessage,
    LLMCall,
    distill_day,
)

logger = logging.getLogger(__name__)

# The distiller's reduce needs a raised budget (§Q4); the map's fact list can be sizable on a busy
# chunk. 4096 gives a non-reasoning model ample room for the whole fact list + the reduced entry
# (a real map used ~600 tokens; a busy day is larger).
#
# ⚠️ REASONING-MODEL CAVEAT (live-smoke finding 2026-07-12): a local Gemma-4-26b "a4b" variant
# IGNORES our `thinking:False`/`enable_thinking:False` kwargs and emits its ENTIRE output as
# `reasoning_content`, leaving `content` EMPTY and hitting finish_reason=length — at ANY budget
# (it burned all 4096 as reasoning_tokens and never wrote the JSON). So max_tokens does NOT rescue
# a reasoning model; the proper fix is Q8 dedicated-distill-model resolution to a NON-reasoning
# model. A non-reasoning model (Qwen2.5) works — see the enum-repair in `_extract_json_object` for
# the OTHER local-model quirk this smoke found (unquoted enum values).
DISTILL_MAX_TOKENS = 4096


class _LLMSubmitter(Protocol):
    async def submit_and_wait(
        self, *, user_id: str, operation: str, model_source: str, model_ref: str,
        input: dict[str, Any], trace_id: str | None = ...,
    ) -> Any: ...


def _chat_text(result: dict[str, Any] | None) -> str:
    """Extract the assistant text from a completed chat job's result. The provider-registry chat
    result carries content at result['messages'][0]['content'] (NOT result['content'])."""
    result = result or {}
    messages = result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        return messages[0].get("content") or ""
    return result.get("content") or ""


def make_distill_llm(
    llm_client: _LLMSubmitter,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
    max_tokens: int = DISTILL_MAX_TOKENS,
    trace_id: str | None = None,
) -> LLMCall:
    """Adapt the worker-ai LLMClient (→ provider-registry, the sanctioned gateway) into the pure
    core's `LLMCall`. The distiller's prompt is a single user message; the map/reduce instructions
    are embedded in it and the map wraps content in a DATA envelope, so no separate system message
    is needed. Raises on a non-completed job so map_chunk/reduce_entry degrade (a failed map chunk
    contributes no facts; a failed reduce writes no entry) rather than fabricating output.

    thinking=False suppresses reasoning mode on thinking-capable local models (the burns-max-tokens
    trap) — harmless when the model has no such flag."""

    async def _call(prompt: str) -> str:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "text"},
                "temperature": 0.2,
                "max_tokens": max_tokens,
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            trace_id=trace_id,
        )
        status = getattr(job, "status", None)
        if status != "completed":
            raise RuntimeError(f"distill chat job status={status} error={getattr(job, 'error', None)}")
        return _chat_text(getattr(job, "result", None))

    return _call


class _ChatReader(Protocol):
    async def get_day_window(
        self, *, user_id: str, book_id: str, local_date: str, limit: int,
    ) -> tuple[list[dict[str, Any]], bool] | None: ...


class _DiaryWriter(Protocol):
    async def write_diary_entry(
        self, *, book_id: str, owner_user_id: str, entry_date: str, entry_zone: str,
        body: str, title: str | None, journal_kind: str, language: str,
    ) -> dict[str, Any] | None: ...


class _FactQueuer(Protocol):
    async def queue_diary_facts(
        self, *, user_id: str, book_id: str, entry_date: str, facts: list[dict],
    ) -> dict[str, Any]: ...


async def distill_and_write(
    *,
    user_id: str,
    book_id: str,
    entry_date: str,
    entry_zone: str,
    language: str,
    llm: LLMCall,
    chat_client: _ChatReader,
    book_client: _DiaryWriter,
    knowledge_client: "_FactQueuer | None" = None,
    limit: int = 5000,
    giant_paste_threshold: int = GIANT_PASTE_CHARS,
    window: int = WINDOW_CHARS,
) -> dict[str, Any]:
    """Distill one local day into the user's diary. Returns a status dict the trigger layer acts on.

    status ∈ {written, no_entry, oversized, kept, error}. Never raises; a transport failure is a
    retryable 'error', not an exception, so one bad day doesn't crash the worker loop."""
    read = await chat_client.get_day_window(
        user_id=user_id, book_id=book_id, local_date=entry_date, limit=limit,
    )
    if read is None:
        # Transport / non-200 — the day is unknown, not empty. Retry, never write an empty entry.
        return {"status": "error", "reason": "day_window_unavailable", "retryable": True,
                "entry_date": entry_date}
    raw_messages, truncated = read
    messages = [DayMessage.from_api(m) for m in raw_messages]

    outcome = await distill_day(
        messages, language, llm,
        giant_paste_threshold=giant_paste_threshold, window=window,
    )

    # A COMPUTE failure (a provider/model outage during map or reduce) is RETRYABLE — never a
    # dropped day. This must be checked BEFORE the no-entry branch so an outage that yielded no facts
    # is not mistaken for a low-signal day.
    if outcome.error:
        return {"status": "error", "reason": outcome.error, "entry_date": entry_date,
                "retryable": bool(outcome.retryable)}

    # §T38 — any giant paste(s) are diverted (offer to attach as a document), INDEPENDENT of whether
    # the rest of the day produced an entry. Surface the count so the home strip can make the offer.
    oversized_n = len(outcome.oversized_messages)

    if outcome.entry is None:
        if oversized_n and outcome.no_entry_reason == "only_oversized":
            # The day was ONLY a giant paste — nothing to journal, just the attach-offer.
            return {"status": "oversized", "reason": "giant_paste", "entry_date": entry_date,
                    "oversized_count": oversized_n, "truncated": truncated}
        # §Q11 — a low-signal / empty day writes NO entry, with the reason surfaced.
        return {"status": "no_entry", "reason": outcome.no_entry_reason, "entry_date": entry_date,
                "oversized_count": oversized_n, "chunks": outcome.chunks_processed, "truncated": truncated}

    written = await book_client.write_diary_entry(
        book_id=book_id, owner_user_id=user_id, entry_date=entry_date, entry_zone=entry_zone,
        body=outcome.entry.body(), title=None, journal_kind="primary", language=language,
    )
    if written is None or written.get("error"):
        return {"status": "error", "reason": "write_failed", "entry_date": entry_date,
                "retryable": bool((written or {}).get("retryable", True))}
    if written.get("kept"):
        # A post-confirm day: the primary is kept; the caller re-runs as a supplement (§Q6).
        return {"status": "kept", "entry_date": entry_date}

    # WS-2.3 — divert the day's facts into the KG pending-facts INBOX (human-gated; never trusted).
    # BEST-EFFORT: the entry is already durably written, so a queue failure must NOT fail the distill
    # or drop the day — the facts are a reviewable enrichment, retried on the next distill of this day.
    facts_queued = 0
    if knowledge_client is not None and outcome.facts:
        try:
            res = await knowledge_client.queue_diary_facts(
                user_id=user_id,
                book_id=book_id,
                entry_date=entry_date,
                facts=[{"kind": f.kind, "text": f.text} for f in outcome.facts],
            )
            facts_queued = int(res.get("queued", 0)) if isinstance(res, dict) else 0
        except Exception:  # noqa: BLE001 — enrichment only; never fail a written day on the inbox.
            logger.warning("distill: failed to queue diary facts to the KG inbox (entry stands)", exc_info=True)

    return {
        "status": "written",
        "chapter_id": written.get("chapter_id"),
        "entry_date": entry_date,
        "facts_found": outcome.facts_found,
        "facts_queued": facts_queued,
        "chunks": outcome.chunks_processed,
        "oversized_count": oversized_n,  # a paste alongside a real day is diverted, not lost
        "truncated": truncated,
    }
