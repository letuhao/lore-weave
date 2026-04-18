"""K16.14 — Project stats cache updater.

Maintains denormalized counts on knowledge_projects:
  stat_entity_count, stat_fact_count, stat_event_count, stat_glossary_count

Two update modes:
  - incremental: called by worker-ai after each extraction batch
  - reconcile: full recount from Neo4j (daily cron or manual)

The stats are advisory — the UI uses them for dashboard tiles.
Source of truth is always Neo4j (entities/facts/events) and
glossary-service (glossary entities).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

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
    neo4j_session,
    user_id: UUID,
    project_id: UUID,
) -> dict[str, int]:
    """Full recount from Neo4j → update Postgres.

    Returns the reconciled counts. Should be called on a daily
    schedule or after a graph delete/rebuild.
    """
    counts = {}
    for label, col in [
        ("Entity", "stat_entity_count"),
        ("Fact", "stat_fact_count"),
        ("Event", "stat_event_count"),
    ]:
        result = await neo4j_session.run(
            f"MATCH (n:{label}) "
            "WHERE n.user_id = $user_id AND n.project_id = $project_id "
            "RETURN count(n) AS c",
            user_id=str(user_id),
            project_id=str(project_id),
        )
        record = await result.single()
        counts[col] = record["c"] if record else 0

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
