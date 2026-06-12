"""Decoupled online-judge state machine (LLM re-arch Phase 3 M1).

Both online judges — extraction-precision (eval-runner) and translation-fidelity
(collector) — used to run INLINE via ``submit_and_wait``, pinning the consumer
coroutine for the whole (multi-batch, for extraction) judge. This module moves
them onto the durable job-row + terminal-event pattern that worker-ai extraction
and translation already use:

  start_*  → plan the judge into N batches, INSERT one ``llm_judges`` row
             (idempotent per source signal), submit the FIRST batch, persist its
             ``provider_job_id`` → return. The consumer coroutine is freed.
  resume() → driven by the llm-job terminal-event consumer: fold the finished
             batch's verdicts into ``resume_state.accum``, advance the cursor, and
             SEQUENTIALLY dispatch the next batch under the row's FOR UPDATE lock
             (single ``provider_job_id`` column — the V3-decouple shape). On the
             last batch, finalize OUTSIDE the lock via the existing
             persist_online_judge / persist_translation_judge (idempotent).

**At-least-once safe.** ``UNIQUE(kind, origin_dedup_key)`` means a redelivered
source event finds the row and skips (no second judge run). A redelivered terminal
event for a superseded batch finds no ``status='running'`` row at that
``provider_job_id`` and is ignored. The stuck-resume sweeper re-drives any row idle
past the timeout (submit→persist gap, lost terminal event, consumer crash). The
whole judge stays best-effort/droppable, exactly as the inline version was.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from loreweave_eval.llm_judge import (
    FIDELITY_SYSTEM,
    FidelityVerdict,
    build_fidelity_user_prompt,
    build_judge_input,
    judge_content_from_result,
    parse_fidelity_content,
    parse_precision_batch,
    plan_precision_tasks,
)
from loreweave_llm.models import SubmitJobRequest

from app.db.online_judge import aggregate_precision_dicts, persist_online_judge
from app.db.online_translation_judge import persist_translation_judge

logger = logging.getLogger(__name__)

_JOB_META = {"extractor": "llm_judge"}


def _rs(row: asyncpg.Record) -> dict:
    rs = row["resume_state"]
    return rs if isinstance(rs, dict) else json.loads(rs)


# ── start (submit first batch, persist the durable row) ───────────────────────


async def start_extraction_judge(
    pool: asyncpg.Pool,
    sdk: Any,
    *,
    run_id: str,
    owner_user_id: Any,
    billing_user_id: str,
    project_id: Any,
    book_id: Any,
    config_hash: str | None,
    judge_model: str,
    judge_model_source: str,
    source_text: str,
    items_by_category: dict[str, list[Any]],
) -> bool:
    """Plan the extraction-precision judge into per-category batches, persist the
    durable row, and submit the first batch. Returns False when nothing is judgeable
    (no items) or the run is already being judged (dedup). ``owner_user_id`` is the
    content owner (persist target); ``billing_user_id`` is the BYOK submit/get_job
    identity (may be an env fallback)."""
    tasks = plan_precision_tasks(source_text=source_text, items_by_category=items_by_category)
    if not tasks:
        return False
    rs = {
        "kind": "extraction",
        "cursor": 0,
        "tasks": [
            {
                "category": t.category,
                "global_start": t.global_start,
                "n_items": t.n_items,
                "system": t.system,
                "user": t.user,
            }
            for t in tasks
        ],
        "accum": {},  # {category: [{idx,verdict,reason}, ...]}
        "persist": {
            "run_id": str(run_id),
            "owner_user_id": str(owner_user_id) if owner_user_id is not None else None,
            "project_id": str(project_id) if project_id is not None else None,
            "book_id": str(book_id) if book_id is not None else None,
            "config_hash": config_hash,
        },
    }
    dedup = f"online-judge:{run_id}:{judge_model}"
    return await _start(
        pool, sdk, kind="extraction", rs=rs, dedup=dedup,
        billing_user_id=billing_user_id,
        judge_model=judge_model, judge_model_source=judge_model_source,
    )


async def start_translation_judge(
    pool: asyncpg.Pool,
    sdk: Any,
    *,
    ct_id: str,
    owner_user_id: Any,
    billing_user_id: str,
    book_id: Any,
    origin_event_id: str,
    judge_model: str,
    judge_model_source: str,
    source_text: str,
    translated_text: str,
    emit_eval_judged: bool,
    eval_payload: dict[str, Any],
) -> bool:
    """Plan the translation-fidelity judge (a single batch), persist the durable
    row, and submit. Returns False when either side is blank or the event is already
    being judged (dedup). ``emit_eval_judged`` mirrors the inline campaign path: on
    finalize a campaign-chosen judge XADDs ``translation.eval_judged`` for the
    campaign projection (the global-config judge stays telemetry-only)."""
    user = build_fidelity_user_prompt(source_text, translated_text)
    if user is None:
        return False
    rs = {
        "kind": "translation",
        "cursor": 0,
        "tasks": [{"n_items": 1, "system": FIDELITY_SYSTEM, "user": user}],
        "accum": {},  # {"fidelity": {score, reason} | None}
        "persist": {
            "ct_id": str(ct_id),
            "owner_user_id": str(owner_user_id) if owner_user_id is not None else None,
            "book_id": str(book_id) if book_id is not None else None,
            "origin_event_id": origin_event_id,
            "emit_eval_judged": bool(emit_eval_judged),
            "eval_payload": eval_payload,
        },
    }
    dedup = f"transl-judge:{origin_event_id}"
    return await _start(
        pool, sdk, kind="translation", rs=rs, dedup=dedup,
        billing_user_id=billing_user_id,
        judge_model=judge_model, judge_model_source=judge_model_source,
    )


async def _start(
    pool: asyncpg.Pool,
    sdk: Any,
    *,
    kind: str,
    rs: dict,
    dedup: str,
    billing_user_id: str,
    judge_model: str,
    judge_model_source: str,
) -> bool:
    """INSERT the durable row (idempotent on (kind, dedup)) + submit the first
    batch, all in ONE transaction so the terminal event can't match the row before
    its ``provider_job_id`` is committed (no submit→persist gap on the start path)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row_id = await conn.fetchval(
                """
                INSERT INTO llm_judges
                  (kind, billing_user_id, judge_model, judge_model_source,
                   resume_state, origin_dedup_key)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT (kind, origin_dedup_key) DO NOTHING
                RETURNING id
                """,
                kind, billing_user_id, judge_model, judge_model_source,
                json.dumps(rs), dedup,
            )
            if row_id is None:
                return False  # already being judged / judged — at-least-once dedup
            await _dispatch_task(
                conn, sdk, row_id, rs,
                billing_user_id=billing_user_id,
                judge_model=judge_model, judge_model_source=judge_model_source,
            )
    return True


# ── dispatch one batch under the row's lock ───────────────────────────────────


async def _dispatch_task(
    conn: asyncpg.Connection,
    sdk: Any,
    row_id: Any,
    rs: dict,
    *,
    billing_user_id: str,
    judge_model: str,
    judge_model_source: str,
) -> None:
    """Submit the batch at ``rs['cursor']`` and persist its ``provider_job_id`` +
    the (possibly advanced) ``resume_state`` on the row. Called UNDER the row's
    FOR UPDATE lock (or in the fresh-row start txn) so ``provider_job_id`` advances
    atomically — a redelivered terminal event for the prior batch can't race the
    next one in."""
    task = rs["tasks"][rs["cursor"]]
    submit = await sdk.submit_job(
        SubmitJobRequest(
            operation="chat",
            model_source=judge_model_source,  # type: ignore[arg-type]
            model_ref=judge_model,
            input=build_judge_input(
                system=task["system"], user=task["user"], n_items=task["n_items"],
            ),
            job_meta=_JOB_META,
        ),
        user_id=billing_user_id,
    )
    await conn.execute(
        "UPDATE llm_judges SET provider_job_id = $1, resume_state = $2::jsonb, "
        "updated_at = now() WHERE id = $3",
        submit.job_id, json.dumps(rs), row_id,
    )


def _fold(rs: dict, job: Any) -> None:
    """Fold the just-finished batch's content into ``rs['accum']`` and advance the
    cursor. A non-completed job (failed/cancelled, result=None) folds as empty
    content → unjudged/None (best-effort: a single judge hiccup never aborts)."""
    task = rs["tasks"][rs["cursor"]]
    content = judge_content_from_result(job.result, n_items=task["n_items"])
    if rs["kind"] == "extraction":
        verdicts = parse_precision_batch(
            content, global_start=task["global_start"], n_items=task["n_items"],
        )
        rs["accum"].setdefault(task["category"], []).extend(
            {"idx": v.idx, "verdict": v.verdict, "reason": v.reason} for v in verdicts
        )
    else:  # translation
        fid = parse_fidelity_content(content)
        rs["accum"]["fidelity"] = (
            {"score": fid.score, "reason": fid.reason} if fid is not None else None
        )
    rs["cursor"] += 1


# ── resume (terminal-event / sweeper driven) ──────────────────────────────────


async def load_for_job(pool: asyncpg.Pool, provider_job_id: str) -> tuple[Any, str] | None:
    """(row_id, billing_user_id) for the RUNNING judge awaiting ``provider_job_id``,
    or None (not a judge job, or already finalized / superseded). Cheap existence
    check the consumer makes before get_job; ``resume`` re-reads under the lock."""
    try:
        job_uuid = UUID(provider_job_id)
    except (ValueError, TypeError):
        return None
    row = await pool.fetchrow(
        "SELECT id, billing_user_id FROM llm_judges "
        "WHERE provider_job_id = $1 AND status = 'running'",
        job_uuid,
    )
    return (row["id"], row["billing_user_id"]) if row else None


async def resume(pool: asyncpg.Pool, sdk: Any, job: Any) -> None:
    """Fold a terminal judge job + either dispatch the next batch or finalize.

    Serializes the read-modify-write under the row's FOR UPDATE lock + a
    provider_job_id match (idempotent against at-least-once redelivery): a duplicate
    terminal for a superseded batch finds no matching running row; a duplicate for
    the LAST batch hits the ``cursor >= len(tasks)`` guard (no double-fold) and
    re-runs the idempotent finalize."""
    do_finalize = False
    row_id = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, kind, provider_job_id, billing_user_id, judge_model, "
                "judge_model_source, resume_state FROM llm_judges "
                "WHERE provider_job_id = $1 AND status = 'running' FOR UPDATE",
                job.job_id,
            )
            if row is None:
                return  # superseded / already finalized / not a judge job
            row_id = row["id"]
            rs = _rs(row)
            if rs["cursor"] < len(rs["tasks"]):
                _fold(rs, job)
            if rs["cursor"] >= len(rs["tasks"]):
                # Persist the folded accum + cursor before releasing the lock so a
                # crash before finalize is re-drivable (sweeper sees cursor==len).
                await conn.execute(
                    "UPDATE llm_judges SET resume_state = $1::jsonb, updated_at = now() "
                    "WHERE id = $2",
                    json.dumps(rs), row_id,
                )
                do_finalize = True
            else:
                await _dispatch_task(
                    conn, sdk, row_id, rs,
                    billing_user_id=row["billing_user_id"],
                    judge_model=row["judge_model"],
                    judge_model_source=row["judge_model_source"],
                )
                return
    if do_finalize:
        await _finalize(pool, row_id)


async def _finalize(pool: asyncpg.Pool, row_id: Any) -> None:
    """Persist the folded result via the existing idempotent persist functions, then
    mark the row completed. Runs OUTSIDE the row lock (persist_* acquire their own
    connection); idempotent (re-read guards on ``status='running'``, persist_* dedup
    on their own keys) so the sweeper / a redelivery can safely re-run it.

    Ordering matters for the (non-idempotent) ``translation.eval_judged`` emit
    (/review-impl MED#1): persist FIRST (idempotent — the judge result must be durable
    before the row reads done), then CAS-claim completion
    (``UPDATE … WHERE status='running' RETURNING id``), then emit ONLY if the claim
    won. So a concurrent finalize / crash re-drive yields at-most-once emit
    (lost-on-crash is acceptable per ``_emit_eval_judged``), never a double-emit."""
    row = await pool.fetchrow(
        "SELECT id, kind, status, judge_model, resume_state FROM llm_judges WHERE id = $1",
        row_id,
    )
    if row is None or row["status"] != "running":
        return  # fast path: already finalized
    rs = _rs(row)
    judge_model = row["judge_model"]
    ctx = rs["persist"]
    result: Any = None
    emit_args: tuple | None = None

    if rs["kind"] == "extraction":
        result = aggregate_precision_dicts(rs["accum"])
        owner = ctx.get("owner_user_id")
        if owner:
            await persist_online_judge(
                pool,
                run_id=ctx["run_id"],
                user_id=UUID(owner),
                judge_model=judge_model,
                judge_result=result,
                project_id=UUID(ctx["project_id"]) if ctx.get("project_id") else None,
                book_id=UUID(ctx["book_id"]) if ctx.get("book_id") else None,
                config_hash=ctx.get("config_hash"),
            )
    else:  # translation
        fid = rs["accum"].get("fidelity")
        result = fid
        owner = ctx.get("owner_user_id")
        if fid is not None and owner:
            verdict = FidelityVerdict(score=fid["score"], reason=fid.get("reason", ""))
            await persist_translation_judge(
                pool,
                ct_id=ctx["ct_id"],
                user_id=UUID(owner),
                book_id=UUID(ctx["book_id"]) if ctx.get("book_id") else None,
                verdict=verdict,
                judge_model=judge_model,
                origin_event_id=ctx["origin_event_id"],
            )
            if ctx.get("emit_eval_judged"):
                emit_args = (ctx.get("eval_payload") or {}, verdict)

    # CAS-claim: only the driver that flips running→completed proceeds to emit.
    won = await pool.fetchval(
        "UPDATE llm_judges SET status = 'completed', provider_job_id = NULL, "
        "result = $1::jsonb, updated_at = now() WHERE id = $2 AND status = 'running' "
        "RETURNING id",
        json.dumps(result), row_id,
    )
    if won is None:
        return  # another driver finalized concurrently — don't double-emit
    if emit_args is not None:
        await _emit_eval_judged(*emit_args)


async def _emit_eval_judged(eval_payload: dict[str, Any], verdict: FidelityVerdict) -> None:
    """Best-effort XADD ``translation.eval_judged`` so the campaign projection records
    the fidelity score (mirrors handlers._emit_eval_judged). learning-service has no
    transactional outbox (D-S5BEVAL-LEARNING-OUTBOX) — a lost emit just leaves
    eval_fidelity_score null, acceptable for best-effort telemetry. Never raises."""
    import redis.asyncio as aioredis

    from app.config import settings

    body = {
        "user_id": eval_payload.get("user_id"),
        "book_id": eval_payload.get("book_id"),
        "chapter_id": eval_payload.get("chapter_id"),
        "target_language": eval_payload.get("target_language"),
        "score": float(verdict.score),
    }
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await r.xadd(
            "loreweave:events:translation_eval",
            {"event_type": "translation.eval_judged", "payload": json.dumps(body)},
        )
    except Exception:  # noqa: BLE001 — best-effort telemetry
        logger.warning("decoupled judge: translation.eval_judged emit failed", exc_info=True)
    finally:
        await r.aclose()


# ── stuck-resume sweeper ──────────────────────────────────────────────────────


async def sweep_once(pool: asyncpg.Pool, sdk: Any, *, timeout_s: int, batch: int) -> int:
    """Re-drive judge rows stuck ``running`` past the idle timeout (submit→persist
    gap, a lost terminal event, or a consumer crash). Replays the SAME idempotent
    resume/finalize the event path uses. Returns the number re-driven."""
    rows = await pool.fetch(
        """SELECT id, provider_job_id, billing_user_id, resume_state
           FROM llm_judges
           WHERE status = 'running'
             AND updated_at < now() - make_interval(secs => $1::int)
           ORDER BY updated_at ASC
           LIMIT $2::int""",
        timeout_s, batch,
    )
    redriven = 0
    for row in rows:
        rs = _rs(row)
        # Folded-but-not-finalized (crash between commit + persist) → re-finalize.
        if row["provider_job_id"] is None or rs["cursor"] >= len(rs["tasks"]):
            try:
                await _finalize(pool, row["id"])
                redriven += 1
            except Exception:  # noqa: BLE001 — one bad row mustn't stop the sweep
                logger.exception("judge-sweep: finalize failed id=%s", row["id"])
            continue
        try:
            job = await sdk.get_job(
                str(row["provider_job_id"]), user_id=row["billing_user_id"],
            )
        except Exception:  # noqa: BLE001 — transient get_job fault: next row/tick
            continue
        if not job.is_terminal():
            continue  # slow ≠ stuck
        try:
            await resume(pool, sdk, job)
            redriven += 1
            logger.warning(
                "judge-sweep: re-drove stranded judge id=%s via job=%s",
                row["id"], row["provider_job_id"],
            )
        except Exception:  # noqa: BLE001
            logger.exception("judge-sweep: re-drive failed id=%s", row["id"])
    return redriven
