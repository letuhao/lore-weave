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

    before_structural, before_hash, before_desc_hash = split_snapshot(target_type, before_snapshot)
    after_structural, after_hash, after_desc_hash = split_snapshot(target_type, after_snapshot)
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
          before_description_content_hash, after_description_content_hash,
          diff_class, source_extraction_run_id, source_chapter, source_span,
          actor_type, actor_id, origin_service, origin_event_id, origin_event_type, emitted_at
        ) VALUES (
          $1, $2, $3, $4, $5, $6,
          $7::jsonb, $8::jsonb, $9, $10,
          $11, $12,
          $13, $14, $15, $16::jsonb,
          $17, $18, $19, $20, $21, $22
        )
        ON CONFLICT (origin_service, origin_event_id) DO NOTHING
        """,
        user_id, project_id, book_id, target_type, target_id, op,
        _jsonb(before_structural), _jsonb(after_structural), before_hash, after_hash,
        before_desc_hash, after_desc_hash,
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


# payload `op` ("merged"/"unmerged") → corrections `op`. Both map to a verb that
# derive_diff_class treats as merge-class (`_MERGE_OPS = {"merge", "split"}`), so a
# merge AND its compensating un-merge both classify as diff_class="merge" (the
# reversal is still a same/not-same resolution signal). "split" is the codebase's
# idiomatic un-merge verb (diff_class.py's _MERGE_OPS).
_MERGE_OP = {"merged": "merge", "unmerged": "split"}


async def handle_glossary_entity_merged(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`glossary.entity_merged` → an entity resolution correction (D-LEARN-ENTITY-MERGED).

    A user merged two duplicate glossary entities ("these two are the same") — a
    resolution-quality correction on the extractor's entity boundaries. Emitted by
    glossary `merge_handler.go` (op="merged") and its compensating un-merge
    (op="unmerged"). The payload carries only the winner/loser entity ids (+ book),
    NOT the name/kind snapshot the entity_updated path uses, so the correction is
    encoded structurally: target = the surviving winner; before = the absorbed
    loser ref, after = the surviving winner ref (structural id refs — no novel
    content, like relation endpoint ids). op="merge"/"split" ⇒ derive_diff_class →
    "merge".

    Owner: the merging user. Today owner == actor (glossary `verifyBookOwner`), so
    user_id := actor_id, mirroring handle_glossary_entity_updated. Same R3-W1
    discipline as the siblings — an empty outbox_id or a missing owner raises →
    DLQ (a merge with no attributable owner cannot be persisted per-tenant).

    NOTE (producer gap, out of scope here — services/learning-service only): the
    glossary entity_merged payload does NOT currently carry actor_id, so until the
    producer adds it every merge event lands in the DLQ rather than persisting. The
    learning-side handler is ready; the one-field producer addition is the remaining
    slice (see the task report / D-LEARN-ENTITY-MERGED)."""
    payload = event.payload
    actor_id = _uuid_or_none(payload.get("actor_id"))
    op = _MERGE_OP.get(payload.get("op"), "merge")
    winner_id = payload.get("winner_glossary_id") or event.aggregate_id
    loser_id = payload.get("loser_glossary_id")

    await _persist_correction(
        pool,
        user_id=actor_id,  # owner == actor (verifyBookOwner); see handle_glossary_entity_updated
        project_id=None,
        book_id=_uuid_or_none(payload.get("book_id")),
        target_type="entity",
        target_id=str(winner_id),  # the surviving canon (aggregate_id = winner)
        op=op,
        before_snapshot={"entity_id": loser_id} if loser_id else None,  # the absorbed side
        after_snapshot={"entity_id": str(winner_id)},  # the surviving side
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
    logger.debug(
        "entity merge correction persisted: winner=%s loser=%s op=%s origin=glossary:%s",
        winner_id, loser_id, op, event.outbox_id,
    )


async def handle_knowledge_corrected(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`knowledge.{entity,relation,event,fact}_corrected` → a correction.

    KS emits these only from user-facing edit endpoints (BUILD sub-session B; fact
    added S-05), so they are user corrections by construction. The payload carries
    the full correction core including the owner `user_id`. `target_type` is taken
    from the payload (entity|relation|event|fact). KS gates the `fact` event to
    EXTRACTION-derived facts only (a purely human-authored fact retraction is not
    emitted), so mining never sees a user's own-fact edit as an extraction signal."""
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
    "knowledge.fact_corrected": "fact",  # S-05 (extraction-derived fact retractions)
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


# Only genuine-author-choice kinds become gold (design §2 / spec H2). accept-as-is
# is NOT here: composition never emits it (its CorrectionKind Literal excludes it),
# and mining the reranker's own winner would be self-reinforcement.
_COMPOSITION_GOLD_KINDS = {"edit", "pick_different", "regenerate", "reject"}


def _composition_snapshots(
    kind: str, payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Encode the H2-safe preference shape into (before, after) STRUCTURAL dicts.

    Indices / magnitude / booleans only — there is no novel prose on the wire
    (raw is gated behind composition's per-work opt-in, §5). `reject` returns a
    None `after` (the whole generation was dropped → derive_diff_class →
    spurious-drop). `pick_different` is the one direct, non-circular correction on
    the A1 reranker: before=winner(i), after=chosen(j)."""
    winner_index = payload.get("winner_index")
    before: dict[str, Any] = {"role": "winner"}
    if winner_index is not None:
        before["index"] = winner_index

    if kind == "pick_different":
        after: dict[str, Any] | None = {
            "role": "chosen",
            "index": payload.get("chosen_candidate_index"),
            "candidate_count": payload.get("candidate_count"),
        }
    elif kind == "edit":
        after = {
            "changed_blocks": payload.get("changed_blocks"),
            "has_guidance": bool(payload.get("has_guidance")),
            "has_raw_prose": bool(payload.get("has_raw_prose")),
        }
    elif kind == "regenerate":
        after = {
            "regenerated_to_job_id": payload.get("regenerated_to_job_id"),
            "has_guidance": bool(payload.get("has_guidance")),
        }
    else:  # reject — the generation was discarded wholesale
        after = None
    return before, after


async def handle_generation_corrected(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`composition.generation_corrected` → a `generation` correction (V1 slice 2).

    The author's human-gate action on a co-write becomes a `corrections` row
    (target_type=`generation`, op=the kind, origin_service=`composition`). Only
    edit/pick_different/regenerate/reject persist — `accept`/unknown kinds are
    ACKed without a row (H2 self-reinforcement guard). The event is structural-
    only (no prose on the wire); `_persist_correction` requires a non-empty
    `outbox_id` (dedup) + `user_id` (owner) and raises → DLQ otherwise."""
    payload = event.payload
    kind = payload.get("kind")
    if kind not in _COMPOSITION_GOLD_KINDS:
        logger.debug(
            "composition.generation_corrected kind=%r not gold — skipping (id=%s)",
            kind, event.message_id,
        )
        return  # ack, no row — not an error, just not a preference signal

    job_id = payload.get("job_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    before_structural, after_structural = _composition_snapshots(kind, payload)

    await _persist_correction(
        pool,
        user_id=user_id,  # the author == the work owner
        project_id=_uuid_or_none(payload.get("project_id")),
        book_id=_uuid_or_none(payload.get("book_id")),
        target_type="generation",
        target_id=str(job_id),
        op=kind,
        before_snapshot=before_structural,
        after_snapshot=after_structural,
        source_chapter=None,
        source_span=None,
        source_extraction_run_id=None,
        actor_type="user",
        actor_id=user_id,
        origin_service="composition",
        origin_event_id=event.outbox_id,
        origin_event_type=event.event_type,
        emitted_at=None,  # composition event carries no emitted_at; created_at suffices
    )
    logger.debug(
        "composition correction persisted: job=%s kind=%s origin=composition:%s",
        job_id, kind, event.outbox_id,
    )


# ── wiki-llm M8 (D-WIKI-M8-LEARNING-CONSUMER) — the wiki feedback flywheel ─────
# Collect-by-default; the LLM-judge scoring of wiki articles is a separate,
# off-by-default follow-up (D-WIKI-M8-EVAL-PLUS). The gold AI→human PROSE is NOT
# copied here (the corrections table is redact-by-default — structural + hashes);
# it stays in glossary `wiki_revisions`, reachable via the correction's
# target_id=article_id when the few-shot half (D-WIKI-M8-FEWSHOT) needs it.


async def handle_wiki_corrected(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`wiki.corrected` → a `wiki_article` correction (the AI-draft→human-edit gold
    POINTER). Emitted by glossary when a human edits an AI-authored article; the
    owner (`user_id`) is the corrector. Structural-only: before = the AI state at
    correction (author_type + prior generation_status), after = human-owned — a
    non-None `after` so derive_diff_class reads a generic edit, not a spurious-drop.
    Gated by `wiki_learning_enabled` (off → ack, no row); empty outbox_id / missing
    user_id raise → DLQ (R3-W1)."""
    from app.config import settings

    if not settings.wiki_learning_enabled:
        logger.debug("wiki.corrected — wiki learning disabled, skipping (id=%s)", event.message_id)
        return
    payload = event.payload
    # target_id = article_id is the canonical gold-pair pointer (the few-shot half
    # fetches the AI+human revisions from glossary by it); the event's entity_id is
    # intentionally not stored — it's derivable from the article in glossary.
    article_id = payload.get("article_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    await _persist_correction(
        pool,
        user_id=user_id,
        project_id=None,
        book_id=_uuid_or_none(payload.get("book_id")),
        target_type="wiki_article",
        target_id=str(article_id),
        op="human_edit",
        before_snapshot={
            "author_type": "ai",
            "generation_status": payload.get("prior_generation_status"),
        },
        after_snapshot={"author_type": "human"},
        source_chapter=None,
        source_span=None,
        source_extraction_run_id=None,
        actor_type="user",
        actor_id=user_id,
        origin_service="glossary",
        origin_event_id=event.outbox_id,
        origin_event_type=event.event_type,
        emitted_at=_parse_ts(payload.get("emitted_at")),
    )
    logger.debug(
        "wiki correction persisted: article=%s prior=%s origin=glossary:%s",
        article_id, payload.get("prior_generation_status"), event.outbox_id,
    )


async def handle_wiki_suggestion_reviewed(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`wiki.suggestion_reviewed` → a `source='human'` quality_score on the AI article.

    Only AI-generated articles give an AI-quality signal (`was_ai_generated`); a
    review of a human-authored article is skipped (ack, no row). accept=1.0 /
    reject=0.0 under `metric_name='wiki_suggestion_reviewed'` (the action +
    suggestion_id ride in the comment). Gated by `wiki_learning_enabled`; empty
    outbox_id / missing user_id|article_id / bad action raise → DLQ."""
    from app.config import settings

    if not settings.wiki_learning_enabled:
        logger.debug(
            "wiki.suggestion_reviewed — wiki learning disabled, skipping (id=%s)", event.message_id,
        )
        return
    payload = event.payload
    if not payload.get("was_ai_generated"):
        logger.debug(
            "wiki.suggestion_reviewed on a non-AI article — skipping (id=%s)", event.message_id,
        )
        return
    if not event.outbox_id:
        raise ValueError("wiki.suggestion_reviewed has empty outbox_id — refusing to insert")
    article_id = payload.get("article_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    action = payload.get("action")
    if user_id is None or not article_id or action not in ("accept", "reject"):
        raise ValueError(
            "wiki.suggestion_reviewed missing user_id/article_id or bad action "
            f"(user_id={payload.get('user_id')!r} article={article_id!r} action={action!r}) — refusing"
        )
    await persist_consumed_score(
        pool,
        target_kind="wiki_article",
        target_id=str(article_id),
        user_id=user_id,
        book_id=_uuid_or_none(payload.get("book_id")),
        metric_name="wiki_suggestion_reviewed",
        value_num=1.0 if action == "accept" else 0.0,
        source="human",
        origin_service="glossary",
        origin_event_id=event.outbox_id,
        comment=json.dumps({"action": action, "suggestion_id": payload.get("suggestion_id")}),
    )
    logger.debug(
        "wiki suggestion-review persisted: article=%s action=%s origin=glossary:%s",
        article_id, action, event.outbox_id,
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
    await _maybe_judge_translation(event, payload, ct_id, pool)


async def _maybe_judge_translation(
    event: EventData, payload: dict, ct_id, pool: asyncpg.Pool
) -> None:
    """M7d-2 fidelity judge, now per-campaign capable (S5b-eval).

    Runs when EITHER:
      * the event carries an `eval_judge_model_ref` — a campaign explicitly chose a
        judge model; that pick IS the opt-in, so we run regardless of the two
        service-wide flags (the worker also force-feeds the texts for those chapters); OR
      * the legacy global opt-in: `online_translation_judge_enabled` + a configured
        `online_judge_model_ref`.
    Requires source+translated text on the event either way. Best-effort: a judge/LLM
    failure never fails the translation.quality handler. On a campaign judge, also emits
    a best-effort `translation.eval_judged` so the campaign projection can record the score."""
    from app.config import settings

    campaign_judge_ref = payload.get("eval_judge_model_ref")
    if campaign_judge_ref:
        judge_model = str(campaign_judge_ref)
        judge_model_source = payload.get("eval_judge_model_source") or "user_model"
    elif settings.online_translation_judge_enabled and settings.online_judge_model_ref:
        judge_model = settings.online_judge_model_ref
        judge_model_source = settings.online_judge_model_source
    else:
        return  # neither a campaign pick nor the global opt-in → inert

    source_text = payload.get("source_text")
    translated_text = payload.get("translated_text")
    if not source_text or not translated_text:
        return
    try:
        from app.clients.llm_client import build_judge_sdk
        from app.judges.decoupled_judge import start_translation_judge

        # D-EVAL-JUDGE-PER-USER: bill the BYOK judge to the CONTENT OWNER (the
        # event's user_id) rather than the operator's env-configured id, so a
        # multi-tenant batch attributes judge cost to whoever owns the translation.
        # Fall back to the env id only when the event lacks an owner.
        user_id = _uuid_or_none(payload.get("user_id"))
        judge_user_id = str(user_id) if user_id is not None else settings.online_judge_user_id
        if not judge_user_id:
            return  # no owner and no env fallback → cannot resolve a BYOK model
        # M1: submit the fidelity batch + persist a durable `llm_judges` row, then
        # return — the llm-job terminal-event consumer folds the verdict, persists,
        # and (campaign judge only) emits `translation.eval_judged`. Was an inline
        # `submit_and_wait` that pinned the collector consumer for the whole judge.
        sdk = build_judge_sdk(
            base_url=settings.provider_registry_internal_url,
            internal_token=settings.internal_service_token,
        )
        try:
            await start_translation_judge(
                pool,
                sdk,
                ct_id=str(ct_id),
                owner_user_id=user_id,
                billing_user_id=judge_user_id,
                book_id=_uuid_or_none(payload.get("book_id")),
                origin_event_id=event.outbox_id,
                judge_model=judge_model,
                judge_model_source=judge_model_source,
                source_text=source_text,
                translated_text=translated_text,
                # S5b-eval: only a campaign-chosen judge surfaces the verdict to the
                # campaign projection; the global-config judge stays telemetry-only.
                emit_eval_judged=bool(campaign_judge_ref),
                eval_payload={
                    "user_id": payload.get("user_id"),
                    "book_id": payload.get("book_id"),
                    "chapter_id": payload.get("chapter_id"),
                    "target_language": payload.get("target_language"),
                },
            )
        finally:
            await sdk.aclose()
    except Exception:  # noqa: BLE001 — the judge is best-effort telemetry
        logger.warning("M7d: online translation judge failed (non-fatal)", exc_info=True)


async def handle_translation_reviewed(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`translation.reviewed` → a `source='human'` accept signal (track M7b,
    Channel 1a — existing human judgments).

    Setting a chapter-translation version active is a human-only publish decision
    (the worker auto-activates via a different path), so it is a genuine "this
    translation is good enough" signal: `target_kind='translation'`,
    `metric_name='translation_human_accept'`=1.0. The verifier-calibration detail
    — `acknowledged_issues` + `unresolved_high_count` at accept (i.e. the human
    published DESPITE N verifier flags, suggesting false positives) — rides in
    `comment`. Validated against score_config; idempotent on the relay `outbox_id`.
    Empty `outbox_id` / missing `user_id`/`chapter_translation_id` raises → DLQ."""
    payload = event.payload
    if not event.outbox_id:
        raise ValueError("translation.reviewed has empty outbox_id — refusing to insert")
    ct_id = payload.get("chapter_translation_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    if user_id is None or not ct_id:
        raise ValueError(
            "translation.reviewed missing user_id/chapter_translation_id "
            f"(user_id={payload.get('user_id')!r} ct={ct_id!r}) — refusing"
        )
    detail = json.dumps(
        {
            "acknowledged_issues": payload.get("acknowledged_issues"),
            "unresolved_high_count": payload.get("unresolved_high_count"),
            "target_language": payload.get("target_language"),
        },
        ensure_ascii=False,
    )
    await persist_consumed_score(
        pool,
        target_kind="translation",
        target_id=str(ct_id),
        user_id=user_id,
        book_id=_uuid_or_none(payload.get("book_id")),
        metric_name="translation_human_accept",
        value_num=1.0,
        source="human",
        origin_service="translation",
        origin_event_id=event.outbox_id,
        comment=detail,
    )
    logger.debug(
        "translation reviewed persisted: ct=%s ack=%s origin=translation:%s",
        ct_id, payload.get("acknowledged_issues"), event.outbox_id,
    )


async def handle_translation_corrected(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`translation.corrected` → a `corrections` row (track M7c, Channel 1b — the
    human-fix gold). A human edited an LLM translation; the LLM draft (`before`)
    and the human edit (`after`) are captured so future tuning can see exactly
    what the model got wrong and how the human fixed it.

    Unlike the entity/relation/event paths (redact-by-default → hash only), the
    translation path ALSO stores the RAW before/after body in
    `before_content`/`after_content` (PO 2026-06-08: raw-text retention for
    translation tuning). Structural (language/version) + a content hash are also
    written. `actor_type='user'`; idempotent on the relay `outbox_id`; per-owner.
    Empty `outbox_id` / missing `user_id`/`chapter_translation_id` raises → DLQ."""
    payload = event.payload
    if not event.outbox_id:
        raise ValueError("translation.corrected has empty outbox_id — refusing to insert")
    ct_id = payload.get("chapter_translation_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("user_id"))
    if user_id is None or not ct_id:
        raise ValueError(
            "translation.corrected missing user_id/chapter_translation_id "
            f"(user_id={payload.get('user_id')!r} ct={ct_id!r}) — refusing"
        )

    before = payload.get("before") or {}
    after = payload.get("after") or {}
    before_structural, before_hash, _ = split_snapshot("translation", before)
    after_structural, after_hash, _ = split_snapshot("translation", after)
    diff_class = derive_diff_class(
        target_type="translation",
        op="updated",
        before_structural=before_structural,
        after_structural=after_structural,
        before_content_hash=before_hash,
        after_content_hash=after_hash,
    )

    await pool.execute(
        """
        INSERT INTO corrections (
          user_id, book_id, target_type, target_id, op,
          before_structural, after_structural, before_content_hash, after_content_hash,
          before_content, after_content, diff_class,
          source_chapter, actor_type, origin_service, origin_event_id, origin_event_type
        ) VALUES (
          $1, $2, 'translation', $3, 'updated',
          $4::jsonb, $5::jsonb, $6, $7,
          $8::jsonb, $9::jsonb, $10,
          $11, 'user', 'translation', $12, $13
        )
        ON CONFLICT (origin_service, origin_event_id) DO NOTHING
        """,
        user_id, _uuid_or_none(payload.get("book_id")), str(ct_id),
        _jsonb(before_structural), _jsonb(after_structural), before_hash, after_hash,
        _jsonb({"body": before.get("body")}), _jsonb({"body": after.get("body")}), diff_class,
        payload.get("chapter_id"), event.outbox_id, event.event_type,
    )
    logger.debug(
        "translation correction persisted: ct=%s diff=%s origin=translation:%s",
        ct_id, diff_class, event.outbox_id,
    )


async def handle_name_confirmed(event: EventData, *, pool: asyncpg.Pool) -> None:
    """`glossary.name_confirmed` → a `source='human'` signal (track M7c-3 — the
    name-confirm flywheel).

    A user set a glossary name translation to `confidence='verified'` (the M6a
    "confirm a name" action), so it is a human-canonical source→target rendering:
    `target_kind='glossary'`, `metric_name='glossary_name_confirmed'`=1.0. The
    source name / confirmed target / language ride in `comment`. Validated against
    score_config; idempotent on the relay `outbox_id`; per-owner (actor == corpus
    owner). Empty `outbox_id` / missing actor or entity raises → DLQ."""
    payload = event.payload
    if not event.outbox_id:
        raise ValueError("glossary.name_confirmed has empty outbox_id — refusing to insert")
    entity_id = payload.get("glossary_entity_id") or event.aggregate_id
    user_id = _uuid_or_none(payload.get("actor_id"))
    if user_id is None or not entity_id:
        raise ValueError(
            "glossary.name_confirmed missing actor_id/glossary_entity_id "
            f"(actor_id={payload.get('actor_id')!r} entity={entity_id!r}) — refusing"
        )
    detail = json.dumps(
        {
            "source_name": payload.get("source_name"),
            "target_value": payload.get("value"),
            "language": payload.get("language_code"),
        },
        ensure_ascii=False,
    )
    await persist_consumed_score(
        pool,
        target_kind="glossary",
        target_id=str(entity_id),
        user_id=user_id,
        book_id=_uuid_or_none(payload.get("book_id")),
        metric_name="glossary_name_confirmed",
        value_num=1.0,
        source="human",
        origin_service="glossary",
        origin_event_id=event.outbox_id,
        comment=detail,
    )
    logger.debug(
        "name confirmed persisted: entity=%s lang=%s origin=glossary:%s",
        entity_id, payload.get("language_code"), event.outbox_id,
    )
