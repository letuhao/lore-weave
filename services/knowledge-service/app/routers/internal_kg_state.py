"""Internal KG-state probe — "does this book have a knowledge graph, how big?"

GET /internal/books/{book_id}/kg-state

Service-to-service read surface for **chat-service**, which calls it ONCE PER
CHAT TURN to decide whether the book has a KG projection worth consulting (and
how big it is) before spending tokens on retrieval. Because it sits on the chat
hot path it must stay a single cheap indexed read:

  * It answers from the **cached counters** on ``knowledge_projects``
    (``stat_entity_count`` / ``stat_fact_count`` / ``stat_event_count``), which
    ``app/jobs/stats_updater.py`` keeps fresh. It NEVER touches Neo4j — counting
    nodes per turn would be exactly the cost this endpoint exists to avoid.
  * One indexed row lookup (``idx_knowledge_projects_book_active`` — see
    ``app/db/migrate.py``), no joins.

**A book with no knowledge project is a 200, not a 404.** "This book has no KG
yet" is the expected cold-start answer for most books, not an error — chat asks
this about every book, and an error status would force the caller to treat a
normal state as a failure. Same convention as ``/internal/knowledge/timeline``
(``found=False``).

Tenancy: matches the sibling ``/internal`` routes (``internal_canon``,
``internal_timeline``) — the caller is a trusted service authenticated by
``X-Internal-Token`` and passes only the ``book_id``; the owning tenant is
resolved server-side from ``knowledge_projects``. No owner/user id is accepted
from the caller, so there is nothing for a caller to spoof.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/books",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)

# Newest non-archived project for the book. A book can accumulate more than one
# knowledge project over its life (a re-extraction creates a fresh one); the
# most recent live one is the projection chat should reason about.
#
# The stat_* columns are a CACHE maintained by the stats_updater job — they are 0 not only
# for an empty projection but also for one the job has never touched. Reporting an
# uncomputed cache as "0 connections" deadlocks the flagship rail: its `connect-people` step
# is done_when "connections > 0", which an always-0 counter can never satisfy. So distinguish
# "computed and empty" (0) from "never computed" (NULL = UNKNOWN, which the consumer falls
# back from) via stat_updated_at — the column that is set exactly when the job runs.
#
# The is_derivative / is_assistant guard mirrors the service's own get_by_book (projects.py)
# — a derived/assistant scratch project is not the book's real KG and must not be reported as
# its connection state.
_KG_STATE_SQL = """
SELECT project_id,
       extraction_status,
       CASE WHEN stat_updated_at IS NULL THEN NULL ELSE stat_entity_count END AS entity_count,
       CASE WHEN stat_updated_at IS NULL THEN NULL ELSE stat_fact_count   END AS fact_count,
       CASE WHEN stat_updated_at IS NULL THEN NULL ELSE stat_event_count  END AS event_count
  FROM knowledge_projects
 WHERE book_id = $1
   AND NOT is_archived
   AND NOT is_derivative
   AND NOT is_assistant
 ORDER BY created_at DESC
 LIMIT 1
"""


class KgStateResponse(BaseModel):
    """Cold start (no project) is a first-class valid result: ``has_projection``
    is False with null ``project_id`` and zeroed counts — returned with 200."""

    book_id: str
    has_projection: bool = False
    project_id: str | None = None
    # None = the stats cache was never computed for this project (UNKNOWN, NOT zero) — the
    # consumer must not read it as "0 connections" and re-drive a projection that exists.
    entity_count: int | None = None
    fact_count: int | None = None
    event_count: int | None = None
    extraction_status: str | None = None


def _count(value: Any) -> int | None:
    """Pass a cached counter through, preserving NULL as UNKNOWN. A project whose stats job
    has not run reports None (not 0), so the caller can tell "computed empty" from "not yet
    computed". An unexpected non-int still fails loudly rather than silently reading 0."""
    return None if value is None else int(value)


@router.get("/{book_id}/kg-state", response_model=KgStateResponse)
async def get_kg_state(book_id: UUID) -> KgStateResponse:
    """Report whether a book has a KG projection and how big it is.

    Reads only the cached ``stat_*`` counters — no Neo4j, no aggregation.
    """
    row = await get_knowledge_pool().fetchrow(_KG_STATE_SQL, book_id)
    if row is None:
        # No live knowledge project for this book ⇒ cold start. Expected, not an
        # error: 200 with has_projection=False.
        return KgStateResponse(book_id=str(book_id))

    return KgStateResponse(
        book_id=str(book_id),
        has_projection=True,
        project_id=str(row["project_id"]),
        entity_count=_count(row["entity_count"]),
        fact_count=_count(row["fact_count"]),
        event_count=_count(row["event_count"]),
        extraction_status=row["extraction_status"],
    )
