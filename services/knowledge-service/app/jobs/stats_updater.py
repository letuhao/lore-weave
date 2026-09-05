"""K16.14 — Project stats cache updater.

Maintains denormalized counts on knowledge_projects:
  stat_entity_count, stat_fact_count, stat_event_count, stat_glossary_count

Two update modes:
  - incremental: called by worker-ai after each extraction batch
  - reconcile: full recount through `GraphStore` (daily cron or manual)

The stats are advisory — the UI uses them for dashboard tiles.
Source of truth is always the knowledge graph (entities/facts/events)
and glossary-service (glossary entities).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from app.ports.graph_store import GraphStore

__all__ = ["reconcile_project_stats", "increment_stats"]

logger = logging.getLogger(__name__)


async def increment_stats(
    pool: asyncpg.Pool,
    user_id: UUID,
    project_id: UUID,
    *,
    entities: int = 0,
    facts: int = 0,
    events: int = 0,
) -> None:
    """Increment stat counters after an extraction batch.

    Called by worker-ai after processing an item. Deltas can be
    negative (e.g., after a graph delete resets counts).
    """
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET stat_entity_count = GREATEST(0, stat_entity_count + $3),
            stat_fact_count = GREATEST(0, stat_fact_count + $4),
            stat_event_count = GREATEST(0, stat_event_count + $5),
            stat_updated_at = now(),
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, entities, facts, events,
    )


async def reconcile_project_stats(
    pool: asyncpg.Pool,
    store: GraphStore,
    user_id: UUID,
    project_id: UUID,
) -> dict[str, int]:
    """Full recount from the graph → update Postgres.

    Returns the reconciled counts. Should be called on a daily
    schedule or after a graph delete/rebuild.

    Takes a `GraphStore` (plan T17 A10), not a Neo4j session. This job asks the graph one
    question — *how much is in this project* — and that question has an answer on any engine,
    which is exactly why spec §1.2 put it on the port while leaving the destructive janitors
    beside it in the engine layer.
    """
    # stat_glossary_count is NOT reconciled here — it comes from
    # glossary-service (different DB), not the graph. Update it via
    # GlossaryClient.count_entities when glossary-service integration
    # is wired (K16.14-v2).
    #
    # ONE call, not three. The loop this replaces issued a count per label because the repo
    # function counted one label at a time; the port answers the whole card, so an engine
    # that can do it in a single pass (Neo4j's call-subquery) is allowed to.
    stats = await store.project_graph_stats(
        user_id=str(user_id), project_id=str(project_id),
    )
    counts = {
        "stat_entity_count": stats["entity_count"],
        "stat_fact_count": stats["fact_count"],
        "stat_event_count": stats["event_count"],
    }

    await pool.execute(
        """
        UPDATE knowledge_projects
        SET stat_entity_count = $3,
            stat_fact_count = $4,
            stat_event_count = $5,
            stat_updated_at = now(),
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id,
        counts["stat_entity_count"],
        counts["stat_fact_count"],
        counts["stat_event_count"],
    )

    logger.info(
        "K16.14: stats reconciled project_id=%s entities=%d facts=%d events=%d",
        project_id,
        counts["stat_entity_count"],
        counts["stat_fact_count"],
        counts["stat_event_count"],
    )
    return counts
