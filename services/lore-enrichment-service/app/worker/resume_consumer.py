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

import logging
from uuid import UUID

import asyncpg

from loreweave_jobs import BaseTerminalConsumer

from app.api.jobs import GapTarget, _gap_from_target, load_spent_so_far
from app.compose.compose_task import run_compose_task
from app.db.book_profile import get_book_profile
from app.jobs.assembly import build_live_runner
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM
from app.jobs.job_request import existing_gap_refs, load_job_request
from app.strategies.base import StrategyContext
from app.strategies.registry import InactiveStrategyError, UnknownStrategyError

__all__ = [
    "LoreEnrichmentResumeConsumer", "redrive_one", "dispatch_resume_message", "RESUME_GROUP",
]

logger = logging.getLogger("lore_enrichment.resume_worker")

RESUME_GROUP = "lore-enrichment-resume"


# A fixed bigint advisory-lock key derived from a job_id UUID's first 64 bits. Used to
# CLAIM a job for one runner (HIGH-2): the create / resume / retry / stranded-sweeper
# triggers all land on the SAME resume stream and all call redrive_one, so without a claim
# two could drive the SAME job concurrently and double-SPEND real LLM tokens (redrive_one
# dedups proposals only at PERSIST, AFTER the LLM call). The claim is a Postgres SESSION
# advisory lock held for the whole run on a dedicated connection. It is STATUS-AGNOSTIC by
# design — a status CAS (pending->running) would reject a legitimate resume, because the
# resume endpoint pre-flips paused->running BEFORE it XADDs the trigger.
_JOB_LOCK_KEY_SQL = "SELECT ('x' || substr(replace($1, '-', ''), 1, 16))::bit(64)::bigint"


async def redrive_one(
    *, pool: asyncpg.Pool, job_id: str, project_id: str, user_id: str
) -> str:
    """Re-drive ONE job (fresh run, resume, or retry — all are a re-drive skipping done
    gaps), under a per-job advisory-lock CLAIM so concurrent triggers for the same job can
    never run two LLM-spending runners (HIGH-2). A runner that can't claim no-ops. Returns
    a short status string (for the log). Idempotent — safe to call again on redelivery."""
    # Derive the bigint lock key once (UUID's first 64 bits → negligible collision vs
    # bare hashtext, which matters because a false collision would skip a real job).
    async with pool.acquire() as lock_conn:
        try:
            lock_key = await lock_conn.fetchval(_JOB_LOCK_KEY_SQL, job_id)
        except Exception:  # noqa: BLE001 — a malformed job_id can't be a real job; drop
            logger.warning("redrive %s: bad job_id for lock key — drop", job_id)
            return "bad_job_id"
        claimed = await lock_conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_key)
        if not claimed:
            # Another runner holds this job's lock (a concurrent create/resume/retry/sweeper
            # trigger) — no-op so we don't double-spend. The holder drives it to terminal;
            # this message is ack'd by the caller (the work is in flight elsewhere).
            logger.info("redrive %s: job already claimed by another runner — skip", job_id)
            return "already_claimed"
        try:
            return await _redrive_locked(
                pool=pool, job_id=job_id, project_id=project_id, user_id=user_id
            )
        finally:
            # Release the claim (best-effort; a session lock is also freed if the conn drops).
            try:
                await lock_conn.fetchval("SELECT pg_advisory_unlock($1)", lock_key)
            except Exception:  # noqa: BLE001 — conn-close frees the session lock anyway
                logger.warning("redrive %s: advisory unlock failed (conn-close frees it)", job_id)


async def _redrive_locked(
    *, pool: asyncpg.Pool, job_id: str, project_id: str, user_id: str
) -> str:
    """The actual re-drive, run while holding the per-job advisory claim (see redrive_one).
    Idempotent — safe to call again on redelivery."""
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
            # Optional (D-COMPOSE-S1-EMBED-REF): a compose_draft job has no embed ref;
            # build_live_runner ignores it (the embed seam resolves from the ctx).
            embedding_model_ref=request.get("embedding_model_ref"),
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


async def dispatch_resume_message(*, pool: asyncpg.Pool, fields: dict) -> None:
    """Route ONE resume-stream message by its shape (Phase 3 M2).

    The SAME stream carries two trigger kinds: a `task_id` field is a one-shot
    compose task (profile-suggest / intent-resolve → :func:`run_compose_task`); the
    legacy `job_id` shape is a cost-cap-paused gap-fill re-drive (:func:`redrive_one`).
    Both are idempotent for at-least-once redelivery. A business failure is handled
    INSIDE the callee (marks the task failed / drops a poison) and returns normally
    → the caller ACKs; only an infra error propagates → the caller leaves it
    un-ACKed for redelivery."""
    task_id = fields.get("task_id", "")
    if task_id:
        await run_compose_task(pool, task_id=task_id)
        return
    await redrive_one(
        pool=pool,
        job_id=fields.get("job_id", ""),
        project_id=fields.get("project_id", ""),
        user_id=fields.get("user_id", ""),
    )


class LoreEnrichmentResumeConsumer(BaseTerminalConsumer):
    """Resume worker on the shared transport scaffold. Single resume-trigger stream at
    ``start_id="0"``. Business fold = ``dispatch_resume_message`` (idempotent; a business
    failure is handled INSIDE the callee → ``handle`` returns → ack; only an infra error
    raises → the base leaves it un-acked for redelivery). No sweeper here — the compose-task
    sweeper runs separately in the worker entrypoint."""

    stream = LORE_ENRICHMENT_RESUME_STREAM
    group = RESUME_GROUP
    start_id = "0"
    count = 1  # heavy resume jobs — one-at-a-time for fair multi-replica distribution
    consumer_name_prefix = "resume"
    retry_prefix = "lore-enrichment:resume:retry"

    def __init__(self, redis_url: str, pool: asyncpg.Pool, *, consumer_name: str | None = None) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool

    async def handle(self, fields: dict) -> None:
        await dispatch_resume_message(pool=self._pool, fields=fields)
