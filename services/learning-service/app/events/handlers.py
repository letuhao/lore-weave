"""Correction event handlers (design §2, §3).

Each handler maps an inbound correction event to a `corrections` row. The
glossary path filters to `actor_type=="user"` (pipeline writes are the original
output, not corrections, and are NOT persisted). The knowledge path persists
every `knowledge.*_corrected` event (those are user edits by construction — KS
only emits them on user-facing edit endpoints; wired in BUILD sub-session B).

Idempotency: INSERT ... ON CONFLICT (origin_service, origin_event_id) DO NOTHING
keyed on the relay's `outbox_id` (EventData.outbox_id). An EMPTY outbox_id is a
hard error (R3-W1) — raised so the message goes to the DLQ rather than being
inserted with "" (an empty key would collapse every correction to one row).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from app.db.eval_repo import persist_consumed_score
from app.events.diff_class import derive_diff_class
from app.events.dispatcher import EventData
from app.events.snapshot import split_snapshot

logger = logging.getLogger(__name__)

# glossary `op` ("created"/"updated") → corrections `op`
_GLOSSARY_OP = {"created": "create", "updated": "update"}


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _jsonb(value: Any) -> str | None:
    return None if value is None else json.dumps(value, default=str)


async def _persist_correction(
    pool: asyncpg.Pool,
    *,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    book_id: uuid.UUID | None,
    target_type: str,
    target_id: str,
    op: str,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
    source_chapter: str | None,
    source_span: dict[str, Any] | None,
    source_extraction_run_id: uuid.UUID | None,
    actor_type: str,
    actor_id: uuid.UUID | None,
    origin_service: str,
    origin_event_id: str,
    origin_event_type: str,
    emitted_at: datetime | None,
) -> None:
    # R3-W1: never persist with an empty dedup key — fail loud → DLQ.
    if not origin_event_id:
        raise ValueError(
            f"correction from {origin_service} ({origin_event_type}) has empty "
            "outbox_id — refusing to insert (would collapse the corrections log)"
        )
    if user_id is None:
        raise ValueError(
            f"correction from {origin_service} ({origin_event_type}) has no "
            "user_id/owner — refusing to insert"
        )

    before_structural, before_hash = split_snapshot(target_type, before_snapshot)
    after_structural, after_hash = split_snapshot(target_type, after_snapshot)
    diff_class = derive_diff_class(
        target_type=target_type,
        op=op,
        before_structural=before_structural,
        after_structural=after_structural,
        before_content_hash=before_hash,
        after_content_hash=after_hash,
    )

    await pool.execute(
        """
        INSERT INTO corrections (
          user_id, project_id, book_id, target_type, target_id, op,
          before_structural, after_structural, before_content_hash, after_content_hash,
          diff_class, source_extraction_run_id, source_chapter, source_span,
          actor_type, actor_id, origin_service, origin_event_id, origin_event_type, emitted_at
        ) VALUES (
          $1, $2, $3, $4, $5, $6,
          $7::jsonb, $8::jsonb, $9, $10,
          $11, $12, $13, $14::jsonb,
          $15, $16, $17, $18, $19, $20
        )
        ON CONFLICT (origin_service, origin_event_id) DO NOTHING
        """,
        user_id, project_id, book_id, target_type, target_id, op,
        _jsonb(before_structural), _jsonb(after_structural), before_hash, after_hash,
        diff_class, source_extraction_run_id, source_chapter, _jsonb(source_span),
        actor_type, actor_id, origin_service, origin_event_id, origin_event_type, emitted_at,
    )
    logger.debug(
        "correction persisted: %s/%s op=%s diff=%s origin=%s:%s",
        target_type, target_id, op, diff_class, origin_service, origin_event_id,
    )


async def handle_glossary_entity_updated(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`glossary.entity_updated` → an entity correction, IFF actor_type=="user".

    Pipeline (bulk-extract) and any unenriched legacy events carry actor_type
    != "user" and are skipped (ACKed, not persisted). Today the editing user is
    the corpus owner (glossary `verifyBookOwner`), so user_id := actor_id.
    """
    payload = event.payload
    actor_type = payload.get("actor_type")
    if actor_type != "user":
        logger.debug(
            "glossary.entity_updated actor_type=%r (not user) — skipping (id=%s)",
            actor_type, event.message_id,
        )
        return

    actor_id = _uuid_or_none(payload.get("actor_id"))
    op = _GLOSSARY_OP.get(payload.get("op"), "update")
    target_id = payload.get("glossary_entity_id") or event.aggregate_id

    await _persist_correction(
        pool,
        user_id=actor_id,  # today owner == actor (verifyBookOwner); see design §3
        project_id=None,
        book_id=_uuid_or_none(payload.get("book_id")),
        target_type="entity",
        target_id=target_id,
        op=op,
        before_snapshot=payload.get("before"),
        after_snapshot=payload.get("after"),
        source_chapter=None,
        source_span=None,
        source_extraction_run_id=None,
        actor_type="user",
        actor_id=actor_id,
        origin_service="glossary",
        origin_event_id=event.outbox_id,
        origin_event_type=event.event_type,
        emitted_at=_parse_ts(payload.get("emitted_at")),
    )


async def handle_knowledge_corrected(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`knowledge.{entity,relation,event}_corrected` → a correction.

    KS emits these only from user-facing edit endpoints (BUILD sub-session B),
    so they are user corrections by construction. The payload carries the full
    correction core including the owner `user_id`. `target_type` is taken from
    the payload (entity|relation|event)."""
    payload = event.payload
    target_type = payload.get("target_type") or _TARGET_FROM_EVENT.get(event.event_type, "entity")

    await _persist_correction(
        pool,
        user_id=_uuid_or_none(payload.get("user_id")),
        project_id=_uuid_or_none(payload.get("project_id")),
        book_id=_uuid_or_none(payload.get("book_id")),
        target_type=target_type,
        target_id=payload.get("target_id") or event.aggregate_id,
        op=payload.get("op") or "update",
        before_snapshot=payload.get("before"),
        after_snapshot=payload.get("after"),
        source_chapter=payload.get("source_chapter"),
        source_span=payload.get("source_span"),
        source_extraction_run_id=_uuid_or_none(payload.get("source_extraction_run_id")),
        actor_type=payload.get("actor_type") or "user",
        actor_id=_uuid_or_none(payload.get("actor_id")),
        origin_service="knowledge",
        origin_event_id=event.outbox_id,
        origin_event_type=event.event_type,
        emitted_at=_parse_ts(payload.get("emitted_at")),
    )


_TARGET_FROM_EVENT = {
    "knowledge.entity_corrected": "entity",
    "knowledge.relation_corrected": "relation",
    "knowledge.event_corrected": "event",
}


async def handle_run_completed(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`knowledge.extraction_run_completed` → an `extraction_runs` row + a
    content-addressed `config_registry` upsert (Phase B2-A).

    worker-ai emits one event per chapter at completion. The registry upsert is
    idempotent on `config_hash` (N runs of one config → 1 registry row); the run
    insert is idempotent on the relay dedup key (`outbox_id`). Both run in ONE
    transaction so a run never references a missing registry row.

    Same loud-fail discipline as corrections: an empty `outbox_id` (dedup key)
    or missing `user_id`/`config_hash`/`run_id` raises → the message goes to the
    DLQ rather than being silently dropped or collapsed."""
    payload = event.payload
    origin_event_id = event.outbox_id
    if not origin_event_id:
        raise ValueError(
            "extraction_run_completed has empty outbox_id — refusing to insert "
            "(would collapse the run log)"
        )
    run_id = _uuid_or_none(payload.get("run_id"))
    user_id = _uuid_or_none(payload.get("user_id"))
    config_hash = payload.get("config_hash")
    if run_id is None or user_id is None or not config_hash:
        raise ValueError(
            "extraction_run_completed missing run_id/user_id/config_hash "
            f"(run_id={payload.get('run_id')!r} user_id={payload.get('user_id')!r} "
            f"config_hash={config_hash!r}) — refusing to insert"
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO config_registry
                  (config_hash, resolved_config, base_default_version, prompt_versions)
                VALUES ($1, $2::jsonb, $3, $4::jsonb)
                ON CONFLICT (config_hash) DO NOTHING
                """,
                config_hash,
                _jsonb(payload.get("resolved_config") or {}),
                payload.get("base_default_version") or "",
                _jsonb(payload.get("prompt_versions") or {}),
            )
            await conn.execute(
                """
                INSERT INTO extraction_runs (
                  run_id, user_id, project_id, book_id, job_id, scope, chapter_ref,
                  config_hash, model_ref, metrics, outcome, outcome_source,
                  genre, origin_service, origin_event_id, emitted_at
                ) VALUES (
                  $1, $2, $3, $4, $5, $6, $7,
                  $8, $9, $10::jsonb, $11, $12,
                  $13, $14, $15, $16
                )
                ON CONFLICT (origin_service, origin_event_id) DO NOTHING
                """,
                run_id, user_id,
                _uuid_or_none(payload.get("project_id")),
                _uuid_or_none(payload.get("book_id")),
                _uuid_or_none(payload.get("job_id")),
                payload.get("scope"),
                payload.get("chapter_ref"),
                config_hash,
                payload.get("model_ref"),
                _jsonb(payload.get("metrics") or {}),
                payload.get("outcome"),
                payload.get("outcome_source") or "pipeline",
                payload.get("genre"),
                "knowledge",
                origin_event_id,
                _parse_ts(payload.get("emitted_at")),
            )
    logger.debug(
        "extraction_run persisted: run=%s config=%s outcome=%s origin=knowledge:%s",
        run_id, config_hash, payload.get("outcome"), origin_event_id,
    )


async def handle_config_adjusted(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`knowledge.config_adjusted` → a `config_adjustment_events` row (B2-B).

    Append-only per-novel tuning log; best-effort upstream (analytics, lossy-OK).
    b1 carries structural targets only (before/after_structural); raw-prompt
    targets (before/after_content_hash) land in b2 — `*_content` stays NULL
    until a tenant opts into raw retention (DESIGN Q5). Same loud-fail
    discipline: empty outbox_id or missing user_id → DLQ."""
    payload = event.payload
    origin_event_id = event.outbox_id
    if not origin_event_id:
        raise ValueError(
            "config_adjusted has empty outbox_id — refusing to insert "
            "(would collapse the adjustment log)"
        )
    user_id = _uuid_or_none(payload.get("user_id"))
    target = payload.get("target")
    if user_id is None or not target:
        raise ValueError(
            "config_adjusted missing user_id/target "
            f"(user_id={payload.get('user_id')!r} target={target!r}) — refusing to insert"
        )

    await pool.execute(
        """
        INSERT INTO config_adjustment_events (
          user_id, project_id, actor_type, actor_id, base_default_version,
          target, op, before_structural, after_structural,
          before_content_hash, after_content_hash,
          origin_service, origin_event_id, emitted_at
        ) VALUES (
          $1, $2, $3, $4, $5,
          $6, $7, $8::jsonb, $9::jsonb,
          $10, $11,
          $12, $13, $14
        )
        ON CONFLICT (origin_service, origin_event_id) DO NOTHING
        """,
        user_id,
        _uuid_or_none(payload.get("project_id")),
        payload.get("actor_type") or "user",
        _uuid_or_none(payload.get("actor_id")),
        payload.get("base_default_version"),
        target,
        payload.get("op") or "set",
        _jsonb(payload.get("before_structural")),
        _jsonb(payload.get("after_structural")),
        payload.get("before_content_hash"),
        payload.get("after_content_hash"),
        "knowledge",
        origin_event_id,
        _parse_ts(payload.get("emitted_at")),
    )
    logger.debug(
        "config_adjustment persisted: target=%s origin=knowledge:%s",
        target, origin_event_id,
    )


async def handle_chat_feedback(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`chat.message_feedback` → a `quality_scores` row (track Q3).

    The user's explicit thumbs (+1/-1) or implicit regenerate-as-negative on a
    chat turn becomes a `source='human'` quality_score keyed to the message
    (`target_kind='chat_message'`, `metric_name='chat_user_rating'`). Validated
    against score_config; idempotent on the relay `outbox_id`. An empty
    `outbox_id` or missing `user_id` raises → DLQ (R3-W1)."""
    payload = event.payload
    if not event.outbox_id:
        raise ValueError(
            "chat.message_feedback has empty outbox_id — refusing to insert"
        )
    message_id = payload.get("message_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    if user_id is None or not message_id:
        raise ValueError(
            "chat.message_feedback missing user_id/message_id "
            f"(user_id={payload.get('user_id')!r} message_id={message_id!r}) — refusing"
        )
    try:
        rating = float(payload.get("rating"))
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"chat.message_feedback rating not numeric: {payload.get('rating')!r}"
        ) from e

    await persist_consumed_score(
        pool,
        target_kind="chat_message",
        target_id=str(message_id),
        user_id=user_id,
        metric_name="chat_user_rating",
        value_num=rating,
        source="human",
        origin_service="chat",
        origin_event_id=event.outbox_id,
        comment=payload.get("reason"),
    )
    logger.debug(
        "chat feedback persisted: message=%s rating=%s origin=chat:%s",
        message_id, rating, event.outbox_id,
    )


async def handle_translation_quality(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`translation.quality` → a `source='auto'` quality_score (track M7a, Channel 2
    — the LLM-action log).

    The V3 verifier's per-chapter rollup (overall `quality_score` in [0,1]) becomes
    a tunable auto signal keyed to the chapter translation
    (`target_kind='translation'`, `metric_name='translation_quality_score'`). The
    richer breakdown (unresolved-high count, qa rounds, per-issue-type counts,
    language, pipeline) is stashed in `comment` — the consumed dedup is one row per
    event (`origin_service`+`outbox_id`), so the score is the single persisted
    metric and the rest is context for later analysis/tuning.

    Validated against score_config; idempotent on the relay `outbox_id`. An empty
    `outbox_id`, missing `user_id`/`chapter_translation_id`, or non-numeric score
    raises → DLQ."""
    payload = event.payload
    if not event.outbox_id:
        raise ValueError("translation.quality has empty outbox_id — refusing to insert")
    ct_id = payload.get("chapter_translation_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    if user_id is None or not ct_id:
        raise ValueError(
            "translation.quality missing user_id/chapter_translation_id "
            f"(user_id={payload.get('user_id')!r} ct={ct_id!r}) — refusing"
        )
    try:
        score = float(payload.get("quality_score"))
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"translation.quality quality_score not numeric: {payload.get('quality_score')!r}"
        ) from e

    detail = json.dumps(
        {
            "unresolved_high_count": payload.get("unresolved_high_count"),
            "qa_rounds_used": payload.get("qa_rounds_used"),
            "issue_counts": payload.get("issue_counts") or {},
            "target_language": payload.get("target_language"),
            "pipeline_version": payload.get("pipeline_version"),
        },
        ensure_ascii=False,
    )
    await persist_consumed_score(
        pool,
        target_kind="translation",
        target_id=str(ct_id),
        user_id=user_id,
        book_id=_uuid_or_none(payload.get("book_id")),
        metric_name="translation_quality_score",
        value_num=score,
        source="auto",
        origin_service="translation",
        origin_event_id=event.outbox_id,
        comment=detail,
    )
    logger.debug(
        "translation quality persisted: ct=%s score=%s origin=translation:%s",
        ct_id, score, event.outbox_id,
    )
