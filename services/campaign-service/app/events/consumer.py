"""Projection consumer — builds the campaign_chapters projection from the
existing event spine (gap G7).

Consumes per-chapter completion events and advances the matching projection rows
across every active campaign on that (book, user):

  | stream                        | event_type                  | stage advanced |
  |-------------------------------|-----------------------------|----------------|
  | loreweave:events:knowledge    | knowledge.chapter_extracted | knowledge      |
  | loreweave:events:chapter      | chapter.translated          | translation    |
  | loreweave:events:translation  | translation.quality         | eval           |

Consumer group `campaign-collector` — DISTINCT from learning-service's
`learning-collector` and knowledge-service's `knowledge-extractor`. Redis
delivers a copy of every message to each group, so adding this consumer does not
perturb the existing ones.

`handle_event` is convergent + idempotent (sets a status to 'done'), so
at-least-once delivery is safe; no DLQ is needed in S1 (a dropped completion
event self-heals — the driver re-dispatches a still-`dispatched` row only after
the S3 stuck-timeout reconcile; until then the chapter shows in-flight).
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg

from loreweave_jobs import BaseProjectionConsumer

from .. import repositories as repo

logger = logging.getLogger(__name__)

__all__ = ["EVENT_STAGE", "STREAMS", "GROUP_NAME", "handle_event", "ProjectionConsumer"]

# event_type → projection stage to advance.
EVENT_STAGE = {
    "knowledge.chapter_extracted": "knowledge",
    "chapter.translated": "translation",
    # S2: translation idempotency emits this when a chapter is already current
    # (skipped, no re-spend). Same done-signal for the projection so a resumed
    # campaign converges; statistics-service ignores it (stats-neutral).
    "chapter.translation_skipped": "translation",
    "translation.quality": "eval",
}

# S3c-2b breaker→pause: a per-chapter FAILURE event carrying error_code. When a
# provider's S3a circuit is open, the worker emits one with LLM_CIRCUIT_OPEN →
# the campaign auto-pauses (provider-health signal only; does NOT touch stage
# status, so it can't race the worker's internal retry).
FAILURE_EVENT_STAGE = {
    "chapter.translation_failed": "translation",
    "knowledge.chapter_failed": "knowledge",
}
CIRCUIT_OPEN_CODE = "LLM_CIRCUIT_OPEN"

STREAMS = [
    "loreweave:events:knowledge",
    "loreweave:events:chapter",
    "loreweave:events:translation",
    # S5b-eval: learning-service emits translation.eval_judged here (a DEDICATED
    # stream so learning doesn't consume its own emit off :translation).
    "loreweave:events:translation_eval",
]
GROUP_NAME = "campaign-collector"
BLOCK_MS = 5000


async def handle_event(pool: asyncpg.Pool, event_type: str, payload: dict) -> bool:
    """Advance the projection for one inbound event. Returns True if it mapped to
    a stage and was applied, False if ignored (unknown type / missing ids)."""
    # S3c-2b: a circuit-open FAILURE event auto-pauses the affected campaign(s).
    # Provider-health signal only — never touches stage status (no retry race).
    failure_stage = FAILURE_EVENT_STAGE.get(event_type)
    if failure_stage is not None:
        return await _handle_circuit_failure(pool, failure_stage, payload)

    # S5b-eval: a translation-fidelity verdict records a per-chapter score (additive
    # telemetry — does NOT advance the eval stage, which rides translation.quality).
    if event_type == "translation.eval_judged":
        return await _handle_eval_judged(pool, payload)

    stage = EVENT_STAGE.get(event_type)
    if stage is None:
        return False
    try:
        user_id = payload["user_id"]
        book_id = payload["book_id"]
        chapter_id = payload["chapter_id"]
    except (KeyError, TypeError):
        logger.warning("event %s missing user_id/book_id/chapter_id", event_type)
        return False
    if not user_id or not book_id or not chapter_id:
        return False
    # Language guard for the language-specific stages: translation/eval events
    # carry `target_language`; knowledge.chapter_extracted has no such key, so
    # `.get` yields None = no filter (knowledge is language-agnostic).
    target_language = payload.get("target_language")
    try:
        await repo.mark_stage_done_by_chapter(
            pool,
            owner_user_id=UUID(str(user_id)),
            book_id=UUID(str(book_id)),
            chapter_id=UUID(str(chapter_id)),
            stage=stage,
            target_language=target_language,
        )
    except (ValueError, TypeError):
        logger.warning("event %s has malformed UUID(s)", event_type)
        return False
    return True


async def _handle_circuit_failure(pool: asyncpg.Pool, stage: str, payload: dict) -> bool:
    """S3c-2b: pause campaigns whose in-flight (chapter, stage) hit a provider
    circuit-open. Acts ONLY on LLM_CIRCUIT_OPEN (other error codes are ignored —
    a normal failure is the worker's own retry concern, not a campaign pause)."""
    if payload.get("error_code") != CIRCUIT_OPEN_CODE:
        return False
    try:
        user_id = payload["user_id"]
        book_id = payload["book_id"]
        chapter_id = payload["chapter_id"]
    except (KeyError, TypeError):
        return False
    if not user_id or not book_id or not chapter_id:
        return False
    try:
        paused = await repo.pause_campaigns_for_dispatched_chapter(
            pool,
            owner_user_id=UUID(str(user_id)),
            book_id=UUID(str(book_id)),
            chapter_id=UUID(str(chapter_id)),
            stage=stage,
            reason="auto-paused: provider circuit open",
        )
    except (ValueError, TypeError):
        return False
    if paused:
        logger.warning(
            "circuit-open auto-paused %d campaign(s) on book=%s stage=%s", paused, book_id, stage,
        )
    return True


async def _handle_eval_judged(pool: asyncpg.Pool, payload: dict) -> bool:
    """S5b-eval: store the translation-fidelity judge's [0,1] score on the chapter's
    projection row(s). Best-effort telemetry — a malformed/missing score is ignored
    (never DLQ'd; the judge itself is best-effort) and it never touches eval_status."""
    try:
        user_id = payload["user_id"]
        book_id = payload["book_id"]
        chapter_id = payload["chapter_id"]
        score = float(payload["score"])
    except (KeyError, TypeError, ValueError):
        logger.warning("translation.eval_judged missing/invalid fields — ignoring")
        return False
    if not user_id or not book_id or not chapter_id:
        return False
    try:
        await repo.set_eval_fidelity_by_chapter(
            pool,
            owner_user_id=UUID(str(user_id)),
            book_id=UUID(str(book_id)),
            chapter_id=UUID(str(chapter_id)),
            score=score,
            target_language=payload.get("target_language"),
        )
    except (ValueError, TypeError):
        logger.warning("translation.eval_judged has malformed UUID(s)")
        return False
    return True


class ProjectionConsumer(BaseProjectionConsumer):
    """Campaign projection collector on the shared scaffold. run() as a lifespan
    background task. Idempotent + convergent handlers → `ack_on_error` (a failed advance
    self-heals via the S3 stuck-timeout reconcile; no poison-message loop), so there is no
    DLQ and the PEL never lingers (reclaim disabled)."""

    streams = STREAMS
    group = GROUP_NAME
    ack_on_error = True
    reclaim_every_n_loops = 0   # always-ack → nothing stays pending
    count = 20
    block_ms = BLOCK_MS
    consumer_name_prefix = "campaign"

    def __init__(self, redis_url: str, pool: asyncpg.Pool, *, consumer_name: str | None = None) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        event_type = fields.get("event_type", "")
        raw_payload = fields.get("payload", "{}")
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            payload = {}
            logger.warning("invalid JSON payload: stream=%s id=%s", stream, msg_id)
        await handle_event(self._pool, event_type, payload)
