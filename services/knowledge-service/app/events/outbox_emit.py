"""Phase B — knowledge-service correction outbox emit.

User edits to the graph emit a `knowledge.*_corrected` event into the Postgres
`outbox_events` table; worker-infra's relay ships it to
`loreweave:events:knowledge` for learning-service to persist as a correction.

CROSS-STORE caveat (design §6.6): the graph write is in Neo4j (the source of
truth), this outbox is in Postgres — so emission CANNOT be atomic with the
graph edit. `emit_correction` runs AFTER a successful Neo4j write and is
**best-effort**: it never raises (a transient PG failure under-counts the
correction log but must never turn a successful user edit into a 500, nor
corrupt the graph). The §10.1 replay tool is the durability backstop.

Idempotency note: the outbox row PK becomes the stream `outbox_id`, which
learning-service uses as the dedup key — so a relay re-emission is deduped
downstream, and a rare double-emit here would simply produce two rows the
consumer collapses to one.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.pool import get_knowledge_pool

logger = logging.getLogger(__name__)

# event_type → target_type, kept beside the producer so callers can't drift.
ENTITY_CORRECTED = "knowledge.entity_corrected"
RELATION_CORRECTED = "knowledge.relation_corrected"  # sub-session C
EVENT_CORRECTED = "knowledge.event_corrected"        # sub-session C


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_correction(
    *,
    event_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> None:
    """Best-effort insert of a correction event into the Postgres outbox.

    Acquires the knowledge pool internally and wraps EVERYTHING in try/except:
    a missing/unhealthy pool (or any insert error) is logged and swallowed —
    emission must NEVER fail a user edit that already committed to Neo4j, nor
    corrupt the graph (§6.6). The §10.1 replay tool is the durability backstop.

    `aggregate_id` is the graph node's canonical id (a 32-hex string, which
    Postgres accepts as a UUID) — NOT the dedup key (that is the outbox row PK,
    surfaced as `outbox_id`). The correction's real `target_id` is in `payload`."""
    try:
        pool = get_knowledge_pool()
        await pool.execute(
            """
            INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
            VALUES ('knowledge', $1, $2, $3::jsonb)
            """,
            uuid.UUID(str(aggregate_id)),
            event_type,
            json.dumps(payload, default=str),
        )
    except Exception:
        logger.warning(
            "outbox: failed to emit %s for %s (non-fatal — correction log "
            "under-counts; graph write already committed)",
            event_type, aggregate_id, exc_info=True,
        )


def entity_correction_payload(
    *,
    user_id: str,
    project_id: str | None,
    book_id: str | None,
    target_id: str,
    op: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor_id: str,
) -> dict[str, Any]:
    """Build the knowledge.entity_corrected payload core (mirrors the
    `corrections` columns + learning-service's handler contract)."""
    return {
        "user_id": user_id,
        "project_id": project_id,
        "book_id": book_id,
        "target_type": "entity",
        "target_id": target_id,
        "op": op,
        "before": before,
        "after": after,
        "actor_type": "user",
        "actor_id": actor_id,
        "emitted_at": now_iso(),
    }


def entity_snapshot(name: str | None, kind: str | None, aliases: list[str] | None) -> dict[str, Any]:
    """The diffable entity snapshot learning-service splits (kind=structural,
    name/aliases=content-hashed). KS entities have no short_description."""
    return {
        "name": name,
        "kind": kind,
        "aliases": list(aliases) if aliases else [],
    }
