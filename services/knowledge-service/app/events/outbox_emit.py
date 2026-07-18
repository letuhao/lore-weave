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

import asyncpg

from app.db.pool import get_knowledge_pool
from app.metrics import correction_emit_failure_total

logger = logging.getLogger(__name__)

# FD-19/053 — transient (pool/conn/PG) errors are best-effort-OK (ops will heal;
# the §10.1 replay tool is the durability backstop). A PERMANENT error (malformed
# payload, a non-UUID-coercible aggregate_id, serialization/schema drift) will
# NEVER self-heal and never reached outbox_events, so it has zero replay
# durability — surface it loudly (ERROR + metric) instead of a silent warning.
_TRANSIENT_EMIT_ERRORS = (asyncpg.PostgresError, ConnectionError, OSError, TimeoutError)


def _record_emit_failure(event_type: str, aggregate_id: str, exc: Exception) -> None:
    """Split a swallowed emit failure into transient (warn) vs permanent (error +
    metric) so a code-level bug can't hide behind the best-effort warning."""
    if isinstance(exc, _TRANSIENT_EMIT_ERRORS):
        correction_emit_failure_total.labels(kind="transient").inc()
        logger.warning(
            "outbox: TRANSIENT emit failure %s for %s (non-fatal — correction log "
            "under-counts; graph write already committed; replay backstop applies)",
            event_type, aggregate_id, exc_info=True,
        )
    else:
        correction_emit_failure_total.labels(kind="permanent").inc()
        logger.error(
            "outbox: PERMANENT emit failure %s for %s — correction PERMANENTLY "
            "LOST (never reached outbox_events, no replay backstop). This is a bug "
            "to fix (e.g. a non-UUID aggregate_id / malformed payload).",
            event_type, aggregate_id, exc_info=True,
        )

# event_type → target_type, kept beside the producer so callers can't drift.
ENTITY_CORRECTED = "knowledge.entity_corrected"
RELATION_CORRECTED = "knowledge.relation_corrected"  # sub-session C
EVENT_CORRECTED = "knowledge.event_corrected"        # sub-session C
FACT_CORRECTED = "knowledge.fact_corrected"          # S-05 (human fact invalidate)
CONFIG_ADJUSTED = "knowledge.config_adjusted"        # Phase B2-B
ENTITY_FORGOTTEN = "knowledge.entity_forgotten"      # WS-2.6c (D17 forget-a-person)


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
    except Exception as exc:
        _record_emit_failure(event_type, aggregate_id, exc)


async def emit_config_adjustment(
    *,
    aggregate_id: str,
    payload: dict[str, Any],
) -> None:
    """Phase B2-B — best-effort insert of a config-adjustment event.

    Same best-effort discipline as `emit_correction`: a per-novel tuning edit
    has already committed to `knowledge_projects.extraction_config`; this
    analytics event is async/lossy-OK (DESIGN Q3) and must NEVER fail the edit.
    `aggregate_id` is the project_id."""
    try:
        pool = get_knowledge_pool()
        await pool.execute(
            """
            INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
            VALUES ('knowledge', $1, $2, $3::jsonb)
            """,
            uuid.UUID(str(aggregate_id)),
            CONFIG_ADJUSTED,
            json.dumps(payload, default=str),
        )
    except Exception as exc:
        _record_emit_failure(CONFIG_ADJUSTED, aggregate_id, exc)


def config_adjustment_payload(
    *,
    user_id: str,
    project_id: str,
    actor_id: str,
    target: str,
    before_structural: Any = None,
    after_structural: Any = None,
    before_content_hash: str | None = None,
    after_content_hash: str | None = None,
) -> dict[str, Any]:
    """Build a knowledge.config_adjusted payload (one per changed target).

    Structural targets (e.g. 'precision_filter') carry before/after_structural.
    Raw-prompt targets (e.g. 'prompts.entity', b2) carry before/after_content_hash
    ONLY — the prompt TEXT is content-hashed at the producer and NEVER sent to
    learning-service (DESIGN Q5 redact-by-default)."""
    return {
        "user_id": user_id,
        "project_id": project_id,
        "actor_type": "user",
        "actor_id": actor_id,
        "target": target,
        "op": "set",
        "before_structural": before_structural,
        "after_structural": after_structural,
        "before_content_hash": before_content_hash,
        "after_content_hash": after_content_hash,
        "emitted_at": now_iso(),
    }


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


def relation_correction_payload(
    *,
    user_id: str,
    project_id: str | None,
    book_id: str | None,
    target_id: str,
    op: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    source_chapter: str | None,
    actor_id: str,
) -> dict[str, Any]:
    """knowledge.relation_corrected payload core."""
    return {
        "user_id": user_id,
        "project_id": project_id,
        "book_id": book_id,
        "target_type": "relation",
        "target_id": target_id,
        "op": op,
        "before": before,
        "after": after,
        "source_chapter": source_chapter,
        "actor_type": "user",
        "actor_id": actor_id,
        "emitted_at": now_iso(),
    }


def event_correction_payload(
    *,
    user_id: str,
    project_id: str | None,
    book_id: str | None,
    target_id: str,
    op: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    source_chapter: str | None,
    actor_id: str,
) -> dict[str, Any]:
    """knowledge.event_corrected payload core."""
    return {
        "user_id": user_id,
        "project_id": project_id,
        "book_id": book_id,
        "target_type": "event",
        "target_id": target_id,
        "op": op,
        "before": before,
        "after": after,
        "source_chapter": source_chapter,
        "actor_type": "user",
        "actor_id": actor_id,
        "emitted_at": now_iso(),
    }


def event_snapshot_dict(
    *,
    title: str | None,
    summary: str | None,
    time_cue: str | None,
    event_date_iso: str | None,
    participants: list[str] | None,
) -> dict[str, Any]:
    """The diffable event snapshot learning-service splits: structural =
    event_date_iso; content-hashed = title/summary/time_cue/participants."""
    return {
        "title": title,
        "summary": summary,
        "time_cue": time_cue,
        "event_date_iso": event_date_iso,
        "participants": list(participants) if participants else [],
    }


def relation_snapshot(rel: Any) -> dict[str, Any] | None:
    """The diffable relation snapshot learning-service splits — ALL fields are
    structural (endpoint ids + predicate + confidence + valid_until; no content
    hash). `rel` is a `Relation` model or None."""
    if rel is None:
        return None
    valid_until = getattr(rel, "valid_until", None)
    return {
        "subject_id": getattr(rel, "subject_id", None),
        "object_id": getattr(rel, "object_id", None),
        "predicate": getattr(rel, "predicate", None),
        "confidence": getattr(rel, "confidence", None),
        "valid_until": valid_until.isoformat() if valid_until is not None else None,
    }


def fact_correction_payload(
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
    """knowledge.fact_corrected payload core (S-05). Mirrors the relation/entity
    correction shape so the `corrections` columns + learning-service's handler
    contract stay uniform across target types. learning-service registers this
    event (main.py) and mines it (`target_type IN (…, 'fact')`, mining.py); the KS
    invalidate route only emits it for EXTRACTION-derived facts (a purely
    human-authored fact retraction is gated out, so it can't false-degrade a run)."""
    return {
        "user_id": user_id,
        "project_id": project_id,
        "book_id": book_id,
        "target_type": "fact",
        "target_id": target_id,
        "op": op,
        "before": before,
        "after": after,
        "actor_type": "user",
        "actor_id": actor_id,
        "emitted_at": now_iso(),
    }


def fact_snapshot(fact: Any) -> dict[str, Any] | None:
    """The diffable fact snapshot. Structural = type + confidence + valid_until;
    content = the fact text + the structured (subject/predicate/object) claim.
    `fact` is a `Fact` model or None (an invalidate's `after` is always None)."""
    if fact is None:
        return None
    valid_until = getattr(fact, "valid_until", None)
    return {
        "type": getattr(fact, "type", None),
        "content": getattr(fact, "content", None),
        "predicate": getattr(fact, "predicate", None),
        "object": getattr(fact, "object", None),
        "confidence": getattr(fact, "confidence", None),
        "valid_until": valid_until.isoformat() if valid_until is not None else None,
    }
