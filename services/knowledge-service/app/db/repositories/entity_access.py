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
    # P3b — accumulated thumbs (±1) attributed to this entity (0 until the
    # feedback handler runs; older rows read back 0 via COALESCE).
    feedback_score: float = 0.0


class EntityAccessRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_accesses(
        self, user_id: UUID, project_id: UUID, entity_ids: list[str],
        session_id: UUID | None = None,
    ) -> int:
        """Increment the surface count (and refresh recency) for each entity the
        context build just showed this user. Idempotent per call: +1 per entity.
        P3b: stamps `last_session_id` (when the build carried one) so a later
        thumbs on that session's turn can attribute the feedback to these rows.

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
                      (user_id, project_id, entity_id, retrieval_count,
                       last_retrieved_at, last_session_id)
                    SELECT $1, $2, eid, 1, now(), $4
                    FROM unnest($3::text[]) AS eid
                    ON CONFLICT (user_id, project_id, entity_id) DO UPDATE
                      SET retrieval_count = entity_access_log.retrieval_count + 1,
                          last_retrieved_at = now(),
                          last_session_id = COALESCE($4, entity_access_log.last_session_id)
                    """,
                    user_id, project_id, ids, session_id,
                )
            return len(ids)
        except Exception:
            logger.warning(
                "entity access-log record failed (non-fatal) user=%s project=%s n=%d",
                user_id, project_id, len(ids), exc_info=True,
            )
            return 0

    async def apply_feedback(
        self, user_id: UUID, project_id: UUID, session_id: UUID,
        rating: int, turn_at: datetime, window_minutes: int = 10,
    ) -> int:
        """P3b — attribute a thumbs (±1) to the entities this session surfaced
        around the rated turn: rows stamped with `last_session_id = session` whose
        recency falls within [turn_at - window, turn_at + window]. Bounded ±1 per
        event; the blend clamps the aggregate. NEVER raises (event handler path
        must ack; a lost boost is advisory). Returns rows boosted (0 on error)."""
        try:
            async with self._pool.acquire() as conn:
                status = await conn.execute(
                    """
                    UPDATE entity_access_log
                    SET feedback_score = feedback_score + $4
                    WHERE user_id = $1 AND project_id = $2
                      AND last_session_id = $3
                      AND last_retrieved_at BETWEEN
                            $5::timestamptz - make_interval(mins => $6)
                        AND $5::timestamptz + make_interval(mins => $6)
                    """,
                    user_id, project_id, session_id, float(rating),
                    turn_at, window_minutes,
                )
            try:
                return int(status.rsplit(" ", 1)[-1])
            except (ValueError, AttributeError):
                return 0
        except Exception:
            logger.warning(
                "entity feedback apply failed (non-fatal) user=%s project=%s session=%s",
                user_id, project_id, session_id, exc_info=True,
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
                    SELECT entity_id, retrieval_count, decayed_score, last_retrieved_at,
                           COALESCE(feedback_score, 0) AS feedback_score
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
                    feedback_score=r["feedback_score"],
                )
                for r in rows
            }
        except Exception:
            logger.warning(
                "entity salience load failed user=%s project=%s",
                user_id, project_id, exc_info=True,
            )
            return {}
