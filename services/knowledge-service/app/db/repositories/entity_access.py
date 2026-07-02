"""Entity access-log repository (Track 4 P0 — salience substrate).

SECURITY RULE (house style): every method takes `user_id` first and every
statement filters/keys by `(user_id, project_id)`. Salience is per-tenant —
there is no cross-user or global row.

The recorder is written **fire-and-forget** by the context router AFTER the
block is rendered (off the request latency path), so `record_accesses` must
never raise into its caller — it swallows + logs. Reads (`load_salience`) are
used by the P1 salience blend and the P1 decay job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

__all__ = ["EntityAccessRepo", "EntitySalience"]


@dataclass(frozen=True)
class EntitySalience:
    entity_id: str
    retrieval_count: int
    decayed_score: float
    last_retrieved_at: datetime


class EntityAccessRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_accesses(
        self, user_id: UUID, project_id: UUID, entity_ids: list[str]
    ) -> int:
        """Increment the surface count (and refresh recency) for each entity the
        context build just showed this user. Idempotent per call: +1 per entity.

        Fire-and-forget contract: NEVER raises — a telemetry write must not be
        able to break a context build. Returns the number of entity ids applied
        (0 on empty input or on a swallowed error)."""
        # De-dup within the call so an entity shown twice in one block counts once.
        ids = sorted({e for e in entity_ids if e})
        if not ids:
            return 0
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO entity_access_log
                      (user_id, project_id, entity_id, retrieval_count, last_retrieved_at)
                    SELECT $1, $2, eid, 1, now()
                    FROM unnest($3::text[]) AS eid
                    ON CONFLICT (user_id, project_id, entity_id) DO UPDATE
                      SET retrieval_count = entity_access_log.retrieval_count + 1,
                          last_retrieved_at = now()
                    """,
                    user_id, project_id, ids,
                )
            return len(ids)
        except Exception:
            logger.warning(
                "entity access-log record failed (non-fatal) user=%s project=%s n=%d",
                user_id, project_id, len(ids), exc_info=True,
            )
            return 0

    async def load_salience(
        self, user_id: UUID, project_id: UUID
    ) -> dict[str, EntitySalience]:
        """All salience rows for a (user, project), keyed by entity_id. Used by the
        P1 blend to look up an entity's learned salience. Returns {} on empty/error."""
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT entity_id, retrieval_count, decayed_score, last_retrieved_at
                    FROM entity_access_log
                    WHERE user_id = $1 AND project_id = $2
                    """,
                    user_id, project_id,
                )
            return {
                r["entity_id"]: EntitySalience(
                    entity_id=r["entity_id"],
                    retrieval_count=r["retrieval_count"],
                    decayed_score=r["decayed_score"],
                    last_retrieved_at=r["last_retrieved_at"],
                )
                for r in rows
            }
        except Exception:
            logger.warning(
                "entity salience load failed user=%s project=%s",
                user_id, project_id, exc_info=True,
            )
            return {}
