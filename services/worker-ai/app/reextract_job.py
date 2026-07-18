"""WS-2.6a legs 2+3 (spec — D17 memory amendment) — the CORRECTION re-extract ORCHESTRATOR.

When a user amends a diary day's entry ("Alice froze the budget, not Minh"), book-service writes the
corrected revision (leg 1) and this path reconciles the derived knowledge graph so the correction is
not a lie that a rebuild resurrects:

  - leg 2 — re-run the distiller MAP over the CORRECTED ENTRY text (D-R30: the amended entry is the
    re-distill source; the chat transcript is immutable) → structured facts → queue them into the
    pending-facts INBOX (human-gated, D4). The corrected fact ("Alice…") lands as a fresh proposal;
    the unchanged facts re-appear identically (same entry ⇒ same facts, deduped per-day).
  - leg 3 — soft-invalidate the day's OLD confirmed facts (`valid_until`), so the superseded fact
    ("Minh…") vanishes from recall and a KG rebuild cannot resurrect it.

Order is deliberate: queue (leg 2) BEFORE invalidate (leg 3). If the process dies between them, the
worst intermediate state is "corrected facts already in the inbox + old facts still live" (recall shows
the old value until the retry) — never "old facts invalidated + corrected facts lost" (a day's memory
silently gone). Both legs RAISE on failure and both are idempotent (queue dedups per-day; invalidate
only touches active facts), so leaving the message un-acked converges on a clean reconcile.

Non-agentic LLM pipeline (map only), so a Redis-stream job is the right shape — same as the distiller.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.distiller import WINDOW_TOKENS, LLMCall, extract_facts_from_text

logger = logging.getLogger(__name__)


class _FactQueuer(Protocol):
    async def queue_diary_facts(
        self, *, user_id: str, book_id: str, entry_date: str, facts: list[dict],
    ) -> dict[str, Any]: ...

    async def invalidate_diary_day(
        self, *, user_id: str, book_id: str, entry_date: str,
    ) -> dict[str, Any]: ...


class _BudgetChecker(Protocol):
    async def daily_cap_exhausted(self, *, user_id: str) -> bool: ...


async def reextract_and_reconcile(
    *,
    user_id: str,
    book_id: str,
    entry_date: str,
    body: str,
    llm: LLMCall,
    knowledge_client: _FactQueuer,
    billing_client: "_BudgetChecker | None" = None,
    window: int = WINDOW_TOKENS,
) -> dict[str, Any]:
    """Re-extract a corrected diary entry's facts (leg 2) and reconcile the day's graph (leg 3).

    Returns a status dict the consumer acts on. status ∈ {reconciled, no_facts, paused, error}. Never
    raises: a transport/compute failure is a retryable 'error', not an exception, so one bad correction
    doesn't crash the worker loop.

    WS-2.8 — like the distiller, if the user's DAILY spend cap is exhausted this PAUSES before any LLM
    spend (status='paused', not retryable) rather than burning a returning user's budget. Fails OPEN
    (proceeds) on any billing error — the provider-gateway reserve is the hard backstop."""
    if billing_client is not None:
        try:
            if await billing_client.daily_cap_exhausted(user_id=user_id):
                logger.info("reextract: daily spend cap reached — pausing correction reconcile")
                return {"status": "paused", "reason": "daily_cap_reached", "retryable": False,
                        "entry_date": entry_date}
        except Exception:  # noqa: BLE001 — fail OPEN; provider-gateway reserve backstops.
            logger.warning("reextract: daily-cap pre-check failed; proceeding", exc_info=True)

    outcome = await extract_facts_from_text(body, llm, window=window)
    if outcome.error:
        # A compute/model failure — do NOT reconcile from a partial/empty extraction (that would
        # invalidate the day but re-queue the wrong/no facts). Retry the WHOLE correction.
        return {"status": "error", "reason": outcome.error, "entry_date": entry_date,
                "retryable": bool(outcome.retryable)}

    # leg 2 — queue the corrected facts to the inbox FIRST (before the invalidate). RAISES on failure →
    # the consumer leaves the message un-acked → retry (queue is idempotent per-day dedup_key). Unlike
    # the distiller's best-effort queue (the entry already stands there), here the queue IS the leg —
    # losing it would drop the corrected facts, so a failure must fail the job.
    queued = 0
    if outcome.facts:
        res = await knowledge_client.queue_diary_facts(
            user_id=user_id, book_id=book_id, entry_date=entry_date,
            facts=[
                {
                    "kind": f.kind, "text": f.text, "provenance": f.provenance,
                    **({"subject": f.subject} if f.subject else {}),
                    **({"predicate": f.predicate} if f.predicate else {}),
                    **({"object": f.object} if f.object else {}),
                    **({"event_date": f.event_date} if f.event_date else {}),
                }
                for f in outcome.facts
            ],
        )
        queued = int(res.get("queued", 0)) if isinstance(res, dict) else 0

    # leg 3 — invalidate the day's OLD confirmed facts. RAISES on failure → retry. Runs even when the
    # corrected entry yielded NO facts (a correction that REMOVES the day's only fact still must retire
    # the old one — else the deleted fact survives in recall). Idempotent (only active facts).
    inv = await knowledge_client.invalidate_diary_day(
        user_id=user_id, book_id=book_id, entry_date=entry_date,
    )
    invalidated = int(inv.get("invalidated", 0)) if isinstance(inv, dict) else 0

    status = "reconciled" if (queued or invalidated) else "no_facts"
    logger.info("reextract user=%s book=%s date=%s queued=%s invalidated=%s status=%s",
                user_id, book_id, entry_date, queued, invalidated, status)
    return {
        "status": status, "entry_date": entry_date,
        "facts_found": len(outcome.facts), "facts_queued": queued,
        "facts_invalidated": invalidated, "chunks": outcome.chunks_processed,
    }
