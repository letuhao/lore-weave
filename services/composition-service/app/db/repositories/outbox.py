"""outbox_events repository — transactional-outbox emit (§1, §4.5).

UNLIKE knowledge-service's best-effort post-commit emit, composition's outbox
is **txn-local**: `emit` REQUIRES a connection and inserts inside the caller's
open transaction, so the domain write (e.g. composition_work create, a
scene-committed marker) and its event commit or roll back atomically. worker-
infra's generic relay ships the row to `loreweave:events:composition`.

The caller is responsible for opening the transaction:

    async with pool.acquire() as conn:
        async with conn.transaction():
            work = await works_repo.create(..., conn=conn)
            await outbox.emit(conn, aggregate_id=work.project_id,
                              event_type="composition.work_created", payload={...})
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

# Known composition event types (kept beside the producer so callers can't
# drift). The relay does not filter on type — these are documentation + a
# const surface for routers/engine.
WORK_CREATED = "composition.work_created"
SCENE_COMMITTED = "composition.scene_committed"
GENERATION_CORRECTED = "composition.generation_corrected"


async def emit(
    conn: asyncpg.Connection,
    *,
    aggregate_id: UUID,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> UUID:
    """Insert an outbox row inside the caller's transaction. Returns the row id.

    Intentionally NOT best-effort and NOT self-acquiring: emitting on a passed-in
    `conn` is what makes the event atomic with the domain write. If the
    surrounding transaction rolls back, this row vanishes with it (no orphan
    event); if it raises, the caller's write is aborted too (no lost event).
    """
    return await conn.fetchval(
        """
        INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('composition', $1, $2, $3::jsonb)
        RETURNING id
        """,
        aggregate_id, event_type, json.dumps(payload or {}, default=str),
    )
