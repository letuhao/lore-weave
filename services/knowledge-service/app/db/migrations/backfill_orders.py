"""CM4 — per-project backfill for the dual-order axes.

Stamps the reading-order and chronology fields that B1 left perpetually
NULL (so the timeline's `before_chronological` / reading-order filters
were no-ops):

  - `:Event.event_order`        ← chapter `sort_order` × 1e6 + within-chapter
                                  index (events ordered by id within a chapter)
  - `:Event.chronological_order`← `rerank_chronological_order` (date-rank)
  - `:Passage.chapter_index`    ← chapter `sort_order` (metadata SET, NO re-embed)

Per-project (book_id scoped) — the chapter `sort_order` is resolved from
book-service. Idempotent: SET overwrites, so a re-run stamps the same
values. Triggered by the internal route
`POST /internal/projects/{project_id}/backfill-orders`.

Mirrors `backfill_event_date.py` (function + result holder); the trigger
here is an HTTP endpoint (per the CM4 PO decision) rather than a CLI, so
it can run per-project on demand.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from uuid import UUID

from app.clients.book_client import BookClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.events import (
    EVENT_ORDER_CHAPTER_STRIDE,
    rerank_chronological_order,
)

logger = logging.getLogger(__name__)

__all__ = ["run_orders_backfill", "OrdersBackfillResult"]

# List ALL chapter events — builds the chapter set (also drives passage
# backfill) + the deterministic within-chapter ordering.
_LIST_PROJECT_EVENTS_CYPHER = """
MATCH (e:Event {user_id: $user_id, project_id: $project_id})
WHERE e.chapter_id IS NOT NULL AND e.archived_at IS NULL
RETURN e.id AS id, e.chapter_id AS chapter_id
"""

# ⚠️ ONE-TIME legacy migration semantic (mirrors C18 backfill_event_date):
# event_order is set UNCONDITIONALLY over the full id-sorted order. This is
# collision-free and re-runnable to the SAME result. (A `WHERE event_order IS
# NULL` gap-fill was REJECTED in /review-impl: with the idx computed over all
# events, a re-run after new events were inserted would assign a NULL event the
# same base+idx an already-stamped sibling holds — a duplicate-order bug.)
# Run on LEGACY projects whose events predate CM4; do NOT re-run on a live
# CM4 project (it would overwrite the write-path's extraction-order index —
# functionally equivalent at chapter granularity, but unnecessary churn).
_SET_EVENT_ORDER_CYPHER = """
MATCH (e:Event {id: $id, user_id: $user_id})
SET e.event_order = $event_order, e.updated_at = datetime()
"""

# Stamp every chapter passage's chapter_index from the chapter's sort_order.
# Metadata only — vectors untouched (no re-embed).
_SET_PASSAGE_CHAPTER_INDEX_CYPHER = """
MATCH (p:Passage {user_id: $user_id, project_id: $project_id,
                  source_type: 'chapter', source_id: $chapter_id})
WHERE p.chapter_index IS NULL
SET p.chapter_index = $chapter_index
RETURN count(p) AS updated
"""


class OrdersBackfillResult:
    """Plain stats holder — direct attribute access from the route + tests."""

    def __init__(self) -> None:
        self.events_ordered = 0
        self.events_skipped_no_sort = 0  # chapter sort_order unresolved
        self.passages_indexed = 0
        self.chrono_ranked = 0

    def __repr__(self) -> str:  # pragma: no cover (debug aid only)
        return (
            f"OrdersBackfillResult(events_ordered={self.events_ordered}, "
            f"events_skipped_no_sort={self.events_skipped_no_sort}, "
            f"passages_indexed={self.passages_indexed}, "
            f"chrono_ranked={self.chrono_ranked})"
        )


async def run_orders_backfill(
    session: CypherSession,
    book_client: BookClient,
    *,
    user_id: str,
    project_id: str,
) -> OrdersBackfillResult:
    """Backfill event_order + passage chapter_index + chronological_order
    for one project's events/passages. Idempotent.

    `session` and `book_client` are injected so unit tests can pass fakes.
    """
    result = OrdersBackfillResult()

    # 1. Collect events that need ordering, grouped by chapter.
    cypher_result = await session.run(
        _LIST_PROJECT_EVENTS_CYPHER, user_id=user_id, project_id=project_id,
    )
    by_chapter: dict[str, list[str]] = defaultdict(list)
    async for record in cypher_result:
        by_chapter[record["chapter_id"]].append(record["id"])

    # 2. Resolve chapter sort_orders from book-service (one batch call).
    chapter_uuids: list[UUID] = []
    for cid in by_chapter:
        try:
            chapter_uuids.append(UUID(cid))
        except (ValueError, TypeError):
            continue  # non-UUID chapter id — skip (can't resolve sort_order)
    sort_orders = (
        await book_client.get_chapter_sort_orders(chapter_uuids)
        if chapter_uuids
        else {}
    )

    # 3. Stamp event_order = sort_order × stride + within-chapter index
    #    (events ordered by id for a deterministic, stable index).
    for chapter_id, event_ids in by_chapter.items():
        try:
            sort_order = sort_orders.get(UUID(chapter_id))
        except (ValueError, TypeError):
            sort_order = None
        if sort_order is None:
            # Chapter deleted / sort_order unresolved — leave event_order as-is
            # (NULL events null-sink in the timeline). Don't fabricate an order.
            result.events_skipped_no_sort += len(event_ids)
            continue
        base = sort_order * EVENT_ORDER_CHAPTER_STRIDE
        # idx over the full id-sorted order → unique within the chapter,
        # deterministic across re-runs (one-time migration; see the SET above).
        for idx, event_id_ in enumerate(sorted(event_ids)):
            await session.run(
                _SET_EVENT_ORDER_CYPHER,
                id=event_id_, user_id=user_id, event_order=base + idx,
            )
            result.events_ordered += 1

        # 4. Stamp this chapter's passage chapter_index (metadata, no re-embed).
        pres = await session.run(
            _SET_PASSAGE_CHAPTER_INDEX_CYPHER,
            user_id=user_id, project_id=project_id,
            chapter_id=chapter_id, chapter_index=sort_order,
        )
        prec = await pres.single()
        if prec is not None:
            result.passages_indexed += int(prec["updated"])

    # 5. Recompute chronological_order across the whole project.
    result.chrono_ranked = await rerank_chronological_order(
        session, user_id=user_id, project_id=project_id,
    )

    logger.info(
        "CM4 orders backfill: project=%s events_ordered=%d skipped=%d "
        "passages_indexed=%d chrono_ranked=%d",
        project_id, result.events_ordered, result.events_skipped_no_sort,
        result.passages_indexed, result.chrono_ranked,
    )
    return result
