"""Resume worker — Redis Streams consumer that re-drives paused jobs (F-C14-1/051).

Loop (mirrors worker-ai's summary_consumer):
  1. XREADGROUP from the resume-trigger stream (consumer group, MKSTREAM).
  2. For each {job_id, project_id, user_id}: load the persisted request, rebuild
     the runner seeded with the prior spend, and run_job SKIPPING already-done
     gaps (skip_gap_refs) — so a resume re-spends neither budget nor tokens on
     done gaps and converges.
  3. XACK on a terminal outcome / unrecoverable message (drop poison); leave
     un-ACKed on a transient infra error so the PEL redelivers.

Idempotent end-to-end (UNIQUE(job_id,gap_ref) + skip-done + seeded spend), so
at-least-once redelivery is safe.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis

from app.api.jobs import GapTarget, _gap_from_target, load_spent_so_far
from app.db.book_profile import get_book_profile
from app.jobs.assembly import build_live_runner
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM
from app.jobs.job_request import existing_gap_refs, load_job_request
from app.strategies.base import StrategyContext
from app.strategies.registry import InactiveStrategyError, UnknownStrategyError

__all__ = ["consume_resume_stream", "redrive_one", "RESUME_GROUP"]

logger = logging.getLogger("lore_enrichment.resume_worker")

RESUME_GROUP = "lore-enrichment-resume"


async def _ensure_group(client: aioredis.Redis, stream: str, group: str) -> None:
    """Idempotently create the consumer group (MKSTREAM bootstraps the stream)."""
    try:
        await client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        logger.info("created consumer group %s on %s", group, stream)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def redrive_one(
    *, pool: asyncpg.Pool, job_id: str, project_id: str, user_id: str
) -> str:
    """Re-drive ONE paused job, skipping done gaps. Returns a short status string
    (for the log). Idempotent — safe to call again on redelivery."""
    request = await load_job_request(pool=pool, job_id=UUID(job_id))
    if request is None:
        # No persisted request (a job created before this table) — can't re-drive.
        logger.warning("resume %s: no persisted request — cannot re-drive (drop)", job_id)
        return "no_request"

    # de-bias C1 (#3): resolve the book profile ONCE so the gap builder localizes
    # the dimension table the SAME way detect/generation/the ctx below do.
    profile = await get_book_profile(
        pool, UUID(request["book_id"]) if request.get("book_id") else None
    )
    gaps = []
    for t in request.get("targets") or []:
        try:
            gap = _gap_from_target(GapTarget(**t), profile)
        except Exception:  # noqa: BLE001 — a malformed target is skipped, not fatal
            continue
        if gap is not None:
            gaps.append(gap)
    if not gaps:
        logger.warning("resume %s: no gaps to re-drive (drop)", job_id)
        return "no_gaps"

    spent = await load_spent_so_far(pool=pool, job_id=UUID(job_id))
    done = await existing_gap_refs(pool=pool, job_id=UUID(job_id))

    try:
        bundle = await build_live_runner(
            pool=pool,
            job_id=job_id,
            user_id=user_id,
            project_id=project_id,
            embedding_model_ref=str(request["embedding_model_ref"]),
            cost_cap=request.get("max_spend_usd"),
            eval_reserve_fraction=float(request.get("eval_reserve_fraction") or 0.15),
            top_k=int(request.get("top_k") or 5),
            technique=str(request.get("technique") or "retrieval"),
            spent_so_far=spent,
            # C3/F-C12-1: book_id (saved on the request) lets the re-driven runner
            # read authored glossary canon for the contradiction check. Absent →
            # the lookup degrades honestly (no false-green).
            book_id=str(request["book_id"]) if request.get("book_id") else None,
        )
    except (InactiveStrategyError, UnknownStrategyError) as exc:
        # Gate-locked / unknown technique → cannot re-drive; drop (not retryable).
        logger.error("resume %s: runner build refused (%s) — drop", job_id, exc)
        return "refused"

    try:
        ctx = StrategyContext(
            user_id=user_id,
            project_id=project_id,
            model_ref=str(request["generation_model_ref"]),
            # de-bias C1: the per-book profile (resolved once above) makes a resumed
            # run book-aware too (NEUTRAL when absent).
            profile=profile,
            # Compose mode D (slice 1): the author's draft + expand mode ride on the
            # persisted request; thread them into the ctx so the DraftExpandStrategy
            # (selected when technique='compose_draft') can seed its generation.
            # None for every other technique (the strategies ignore them).
            seed_text=request.get("seed_text"),
            expand_mode=request.get("expand_mode"),
        )
        outcome = await bundle.runner.run_job(
            job_id=job_id,
            gaps=gaps,
            context=ctx,
            entity_kind=request.get("entity_kind") or "location",
            skip_gap_refs=frozenset(done),
        )
    finally:
        await bundle.aclose()

    logger.info(
        "resume %s → %s (skipped_done=%d, new_proposals=%d, spent=%.4f)",
        job_id, outcome.final_state, len(outcome.resumed_skipped),
        len(outcome.proposals), outcome.spent,
    )
    return outcome.final_state


async def consume_resume_stream(
    *,
    pool: asyncpg.Pool,
    redis_url: str,
    consumer_name: str = "resume-1",
    block_ms: int = 5000,
) -> None:
    """Long-running consumer. Cancel-safe: shutdown raises CancelledError from
    xreadgroup; the finally-block closes the Redis client."""
    client = aioredis.from_url(redis_url, decode_responses=True)
    stream = LORE_ENRICHMENT_RESUME_STREAM
    try:
        await _ensure_group(client, stream, RESUME_GROUP)
        logger.info(
            "resume consumer started group=%s name=%s stream=%s",
            RESUME_GROUP, consumer_name, stream,
        )
        while True:
            try:
                resp = await client.xreadgroup(
                    groupname=RESUME_GROUP,
                    consumername=consumer_name,
                    streams={stream: ">"},
                    count=1,
                    block=block_ms,
                )
            except asyncio.CancelledError:
                raise
            except aioredis.RedisError as exc:
                # A blocking-read timeout / transient Redis error: back off and
                # retry (NOT a crash — the worker must survive an idle block).
                logger.debug("resume consumer XREADGROUP retry: %s", exc)
                await asyncio.sleep(1.0)
                continue
            if not resp:
                continue
            for _stream, messages in resp:
                for message_id, fields in messages:
                    ack = True
                    try:
                        await redrive_one(
                            pool=pool,
                            job_id=fields.get("job_id", ""),
                            project_id=fields.get("project_id", ""),
                            user_id=fields.get("user_id", ""),
                        )
                    except Exception:  # noqa: BLE001 — transient infra → redeliver
                        logger.warning(
                            "resume msg %s failed; leaving un-ACKed for redelivery",
                            message_id, exc_info=True,
                        )
                        ack = False
                    if ack:
                        await client.xack(stream, RESUME_GROUP, message_id)
    finally:
        await client.aclose()
