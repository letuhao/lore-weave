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


class _ChatReader(Protocol):
    async def get_day_window(
        self, *, user_id: str, book_id: str, local_date: str, limit: int,
    ) -> tuple[list[dict[str, Any]], bool] | None: ...


class _DiaryWriter(Protocol):
    async def write_diary_entry(
        self, *, book_id: str, owner_user_id: str, entry_date: str, entry_zone: str,
        body: str, title: str | None, journal_kind: str, language: str,
    ) -> dict[str, Any] | None: ...


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

    if outcome.oversized_message is not None:
        # §T38 — a giant paste: don't digest, tell the caller to offer attach-as-document.
        return {"status": "oversized", "reason": "giant_paste", "entry_date": entry_date,
                "truncated": truncated}
    if outcome.entry is None:
        # §Q11 — a low-signal / empty day writes NO entry, with the reason surfaced.
        return {"status": "no_entry", "reason": outcome.no_entry_reason, "entry_date": entry_date,
                "chunks": outcome.chunks_processed, "truncated": truncated}

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

    return {
        "status": "written",
        "chapter_id": written.get("chapter_id"),
        "entry_date": entry_date,
        "facts_found": outcome.facts_found,
        "chunks": outcome.chunks_processed,
        "truncated": truncated,
    }
