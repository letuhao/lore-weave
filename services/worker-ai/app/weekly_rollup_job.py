"""WS-3.7 (spec 11 Q2) — the costed WEEKLY ROLLUP.

A scheduled weekly summary DRAFT (never auto-canon): recall the week's CONFIRMED diary facts and
reduce them into one readable weekly review, written as a 'weekly' diary entry (get-or-replace, idempotent) the user reviews.
Reuses the distiller's `reduce_entry` (facts → an entry draft) + `DistillFact` — the weekly rollup is
"reduce over a week's facts" instead of "map a day + reduce". Spend-capped like the distiller (WS-2.8).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.distiller import DistillFact, LLMCall, reduce_entry

logger = logging.getLogger(__name__)


class _FactRecaller(Protocol):
    async def recall_facts_range(
        self, *, user_id: str, book_id: str, date_from: str, date_to: str, limit: int = ...,
    ) -> list[dict]: ...


class _DiaryWriter(Protocol):
    async def write_diary_entry(
        self, *, book_id: str, owner_user_id: str, entry_date: str, entry_zone: str,
        body: str, title: str | None, journal_kind: str, language: str,
    ) -> dict[str, Any] | None: ...


class _BudgetChecker(Protocol):
    async def daily_cap_exhausted(self, *, user_id: str) -> bool: ...


def _fact_dict_to_distill(f: dict) -> DistillFact:
    """Adapt a recalled fact dict (WS-2.4 shape) to the reducer's DistillFact."""
    return DistillFact(
        kind=str(f.get("type") or "event"),
        text=str(f.get("content") or "").strip(),
        provenance="user",
        subject=f.get("subject"), predicate=f.get("predicate"), object=f.get("object"),
        event_date=f.get("event_date_iso") or f.get("event_date"),
    )


async def roll_up_week(
    *,
    user_id: str,
    book_id: str,
    week_start: str,
    week_end: str,
    entry_zone: str,
    language: str,
    llm: LLMCall,
    knowledge_client: _FactRecaller,
    book_client: _DiaryWriter,
    billing_client: "_BudgetChecker | None" = None,
) -> dict[str, Any]:
    """Recall [week_start, week_end]'s facts → reduce → write a weekly-review DRAFT (supplement).
    Returns a status dict {rolled_up|no_facts|paused|error}. Never raises (transport failure → error)."""
    if billing_client is not None:
        try:
            if await billing_client.daily_cap_exhausted(user_id=user_id):
                return {"status": "paused", "reason": "daily_cap_reached", "retryable": False}
        except Exception:  # noqa: BLE001 — fail open (provider-gateway reserve is the backstop).
            logger.warning("weekly-rollup: daily-cap pre-check failed; proceeding", exc_info=True)

    raw = await knowledge_client.recall_facts_range(
        user_id=user_id, book_id=book_id, date_from=week_start, date_to=week_end,
    )
    facts = [df for f in raw if (df := _fact_dict_to_distill(f)).text]
    if not facts:
        return {"status": "no_facts", "week_start": week_start, "week_end": week_end}

    # P5 Gate-3 (cold-review M3) — the weekly review is LLM-generated emotional content, the
    # same surface the reflection floor protects. Screen the week's facts through the shared
    # safety floor BEFORE generating a summary; a trip short-circuits fail-closed (no LLM
    # summary written) rather than auto-generating a review of a distressed week.
    from loreweave_safety import screen
    _verdict = screen("\n".join(f.text for f in facts))
    if _verdict.tripped:
        logger.info("weekly-rollup short-circuit (safety floor) user=%s category=%s",
                    user_id, _verdict.category)
        return {"status": "safety_short_circuit", "category": _verdict.category,
                "week_start": week_start, "week_end": week_end}

    try:
        draft = await reduce_entry(facts, language, llm)
    except Exception as exc:  # noqa: BLE001 — a compute failure is retryable, not a fabricated summary.
        logger.warning("weekly-rollup reduce failed", exc_info=True)
        return {"status": "error", "reason": f"reduce_failed: {exc}", "retryable": True}
    if draft is None or not draft.body().strip():
        return {"status": "no_facts", "reason": "empty_reduce", "week_start": week_start}

    # A weekly review is journal_kind='weekly' dated to the week's end — a get-or-REPLACE kind (review
    # M2): re-running this week's rollup REPLACES the prior review, never duplicates it. Draft-into-inbox
    # (D4 / P3-D6): the user reviews it. (It doesn't touch a day's primary entry.)
    written = await book_client.write_diary_entry(
        book_id=book_id, owner_user_id=user_id, entry_date=week_end, entry_zone=entry_zone,
        body=draft.body(), title=f"Weekly review · {week_start} – {week_end}",
        journal_kind="weekly", language=language,
    )
    if written is None or written.get("error"):
        return {"status": "error", "reason": "write_failed", "retryable": True}
    return {
        "status": "rolled_up", "week_start": week_start, "week_end": week_end,
        "facts_summarized": len(facts), "chapter_id": written.get("chapter_id"),
    }
