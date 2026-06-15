"""LLM re-arch Phase 2b WX-T3b — terminal-event consumer for the decoupled
extraction orchestrator.

Consumes ``loreweave:events:llm_job_terminal`` (the durable terminal-event stream the
provider-registry relay XADDs on every job's terminal transition) and drives the
per-chunk extraction state machine (`decoupled_extract`): entity → trio fan-in →
persist. So the runner submits a chapter's entity job + releases (the in-flight guard
returns), and THIS consumer folds each terminal event, submits the next stage, and on
completion persists + advances the cursor + emits the campaign completion event — the
control-flow **inversion** (the consumer drives the chapter, the runner re-polls for
the next one once resume_state is cleared).

Scope (this increment): entity → trio → persist. Projects that configure recovery or
filter fall back to the synchronous `extract_pass2` in the runner branch (the SM + the
WX-T2c seams support those stages; wiring them is a follow-up).

Billing: `set_billing_user_id`/`set_campaign_id` are re-bound from resume_state before
each resumed submit so the trio jobs keep the collaborator's BYOK identity (E0-3).

Idempotent under at-least-once delivery: the lookup keys on
``extraction_jobs.provider_job_ids`` (the in-flight set) — a superseded/foreign job
finds no row (ack+ignore); a duplicate trio event re-folds idempotently
(`fold_trio_op` is a no-op once that op is folded); the final persist clears
resume_state so a redelivery finds no row.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import redis.asyncio as aioredis

from loreweave_jobs import BaseTerminalConsumer

from app import decoupled_extract as dx
from app.llm_client import LLMClient, set_billing_user_id, set_campaign_id
from app.sample_emit import persist_run_sample_best_effort

logger = logging.getLogger(__name__)

TERMINAL_STREAM = "loreweave:events:llm_job_terminal"
GROUP = "worker-ai-extract-resume"
MAX_RETRIES = 3


def _decode(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v) if v is not None else ""


def _field(fields: dict, key: str) -> str:
    v = fields.get(key, fields.get(key.encode("utf-8")))
    return _decode(v)


async def _load_for_job(pool, provider_job_id: str):
    """(extraction_job_id, resume_state) for the chunk whose in-flight set contains
    `provider_job_id` — or None (a non-extraction job, or already finalized)."""
    row = await pool.fetchrow(
        """SELECT job_id, resume_state FROM extraction_jobs
           WHERE resume_state IS NOT NULL
             AND provider_job_ids @> to_jsonb($1::text)""",
        provider_job_id,
    )
    if not row or row["resume_state"] is None:
        return None
    rs = row["resume_state"]
    rs = rs if isinstance(rs, dict) else json.loads(rs)
    return row["job_id"], rs


async def _persist_inflight(ex, ej_id, provider_job_ids: list[str], rs: dict) -> None:
    # ex is a Pool OR an asyncpg Connection (the trio-fold race guard persists the
    # merged state inside the FOR UPDATE tx — D-WX-TRIO-FANIN-RACE).
    await ex.execute(
        """UPDATE extraction_jobs
           SET provider_job_ids=$2::jsonb, resume_state=$3::jsonb, pipeline_stage=$4,
               updated_at=now()
           WHERE job_id=$1""",
        ej_id, json.dumps([str(j) for j in provider_job_ids]),
        json.dumps(rs), rs["stage"],
    )


async def _clear_resume(ex, ej_id) -> None:
    await ex.execute(
        "UPDATE extraction_jobs SET resume_state=NULL, provider_job_ids=NULL, pipeline_stage='done' WHERE job_id=$1",
        ej_id,
    )


async def _persist_chunk(pool, knowledge_client, ej_id, rs: dict) -> None:
    """Terminal stage: persist candidates to knowledge (idempotent MERGE, BEFORE the
    tx) → then advance cursor + emit run/chapter_extracted + record spend + clear
    resume_state ALL IN ONE TRANSACTION.

    D-WX-PERSIST-DOUBLE-SPEND: the spend + the resume-clear are folded into the same
    tx as the cursor-advance, and the tx re-reads the row ``FOR UPDATE`` and skips if
    resume_state is already NULL — so a redelivery (the previous code crashed in the
    multi-write window after `_record_spending` before `_clear_resume`) re-runs the
    idempotent persist_pass2 but does NOT re-spend: either the whole finalize committed
    (row cleared → recheck returns NULL → skip) or none of it did (retry cleanly).
    persist_pass2 stays OUTSIDE the tx (it's a knowledge HTTP call; holding a DB row
    lock across it would pin a pooled connection — and the MERGE is idempotent)."""
    from app.runner import (
        _DEFAULT_COST_PER_ITEM as COST,
        _advance_cursor,
        _record_spending,
    )
    from app.outbox_emit import emit_chapter_extracted, emit_extraction_run

    ctx = rs["persist_ctx"]
    cands = dx.reconstruct_candidates(rs)
    owner_id = UUID(rs["user_id"])
    project_id = UUID(ctx["project_id"]) if ctx.get("project_id") else None

    result = await knowledge_client.persist_pass2(
        user_id=owner_id, project_id=project_id,
        source_type=ctx["source_type"], source_id=ctx["source_id"],
        job_id=UUID(ctx["job_id"]), extraction_model=ctx["extraction_model"],
        entities=cands.entities, relations=cands.relations,
        events=cands.events, facts=cands.facts,
        hierarchy_paths=ctx.get("hierarchy_paths"),
        chapter_index=ctx.get("chapter_index"),
        book_parts=ctx.get("book_parts"),
        is_last_chapter_of_book=ctx.get("is_last_chapter_of_book", False),
        embedding_model_uuid=ctx.get("embedding_model_uuid"),
        embedding_dimension=ctx.get("embedding_dimension"),
        writer_autocreate=ctx.get("writer_autocreate"),
        billing_user_id=ctx.get("billing_user_id"),
        billing_llm_model=ctx.get("billing_llm_model"),
        billing_embedding_model=ctx.get("billing_embedding_model"),
        # C12 — gate the summary enqueue on `summaries ∈ targets` (None ⇒ all).
        targets=ctx.get("targets"),
    )

    # Fill the pre-built run_payload's metrics from the persist result.
    run_payload = dict(rs["run_payload"])
    run_payload["metrics"] = {
        **run_payload.get("metrics", {}),
        "entities_merged": result.entities_merged,
        "relations_created": result.relations_created,
        "events_merged": result.events_merged,
        "facts_merged": result.facts_merged,
    }
    chapter_extracted = rs.get("chapter_extracted")
    # D-WX-RUN-SAMPLE-DECOUPLE — write the online-judge run-sample at parity with
    # the sync chapter loop, keyed by the SAME run_id that lands in the event below
    # (the eval-runner fetches the sample by the event's run_id). Done on `pool` (its
    # own connection) BEFORE the finalize tx — persist_run_sample_best_effort swallows
    # errors, and a swallowed failure INSIDE the tx would poison it (a failed statement
    # aborts the whole Postgres transaction). Best-effort + idempotent (ON CONFLICT
    # run_id); a redelivery re-writes the same row as a no-op. Non-opted → skipped.
    if rs.get("save_raw_extraction"):
        await persist_run_sample_best_effort(
            pool, run_id=run_payload["run_id"], user_id=owner_id,
            project_id=project_id, book_id=run_payload.get("book_id"),
            config_hash=run_payload.get("config_hash"), candidates=cands,
            source_text=rs.get("chunk_text", ""),
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Re-read FOR UPDATE: if a concurrent finalize (a duplicate terminal event
            # racing this one) already cleared resume_state, skip the cursor/spend/clear
            # entirely — the work is done; re-spending here is exactly the bug.
            locked = await conn.fetchrow(
                "SELECT resume_state FROM extraction_jobs WHERE job_id=$1 FOR UPDATE",
                ej_id,
            )
            if locked is None or locked["resume_state"] is None:
                logger.info(
                    "decoupled extraction: chunk %s already finalized concurrently; "
                    "skipping cursor/spend (no double-spend)", ctx["source_id"],
                )
                return
            await _advance_cursor(conn, owner_id, UUID(ctx["job_id"]), rs["cursor_to_set"])
            await emit_extraction_run(conn, run_payload)
            if chapter_extracted is not None:
                await emit_chapter_extracted(conn, **chapter_extracted)
            if project_id is not None:
                await _record_spending(conn, owner_id, project_id, COST)
            await _clear_resume(conn, ej_id)
    logger.info(
        "decoupled extraction: chunk %s persisted via event path (entities=%d relations=%d)",
        ctx["source_id"], result.entities_merged, result.relations_created,
    )


# ── WX Wave 4 — recovery/filter stage dispatch ──────────────────────────────────
# After a fold advances the stage, submit the next optional fan-out (recovery → filter)
# under the caller's row lock — the submits are fire-and-forget POSTs (fast enqueue, NOT
# an LLM wait), exactly like the entity→trio transition, so holding the lock across them
# is cheap and serialises a concurrent driver / replica. Empty recovery/filter stages
# advance through to persist.

_INFLIGHT_KEY = {dx.TRIO: "trio_jobs", dx.RECOVERY: "recovery_jobs", dx.FILTER: "filter_jobs"}


def _concurrency_level(rs: dict) -> int | None:
    """C12 (D-C12-CONCURRENCY-DECOUPLED) — the job's cap on parallel in-flight LLM
    submits for THIS chunk's fan-outs (trio / recovery / filter). Seeded onto rs by
    `_start_decoupled_chunk` from `job.concurrency_level`. None / <1 / a legacy resume
    blob without the key ⇒ unbounded (back-compat — the prior sequential behaviour)."""
    cl = rs.get("concurrency_level")
    if isinstance(cl, int) and cl >= 1:
        return cl
    return None


async def _submit_map(llm_client: LLMClient, rs: dict, submits: dict[str, dict]) -> dict[str, str]:
    """Submit a fan-out of provider jobs ({key: submit_kwargs}) and return
    {key: provider_job_id}. C12 — bound the number of concurrent in-flight submits
    to the job's `concurrency_level` (an asyncio.Semaphore over the gather), mirroring
    the SDK sync-gather cap so the decoupled path honours the same knob. None ⇒ no cap
    (a plain gather — every submit in flight at once, the prior unbounded behaviour)."""
    user_id = rs["user_id"]
    cap = _concurrency_level(rs)
    sem = asyncio.Semaphore(cap) if cap is not None else None

    async def _one(kwargs: dict) -> str:
        if sem is not None:
            async with sem:
                sub = await llm_client.submit_job(user_id=user_id, **kwargs)
        else:
            sub = await llm_client.submit_job(user_id=user_id, **kwargs)
        return str(sub.job_id)

    keys = list(submits.keys())
    job_ids = await asyncio.gather(*(_one(submits[k]) for k in keys))
    return dict(zip(keys, job_ids))


async def _dispatch_next(llm_client: LLMClient, rs: dict) -> tuple[dict, list[str] | None]:
    """Submit the next stage's fan-out. Returns (rs, inflight_ids) for the first stage
    with work, or (rs, None) = ready-to-persist when it reaches PERSIST. Only entered
    after a fold ADVANCED past its stage, so it never sees ENTITY/TRIO here."""
    while True:
        stage = rs["stage"]
        if stage == dx.RECOVERY:
            submits, rs = dx.assemble_recovery(rs)
            if submits:
                jobs = await _submit_map(llm_client, rs, submits)
                return dx.begin_recovery(rs, jobs), list(jobs.values())
            rs = dx.begin_recovery(rs, {})  # no Tier-3 work → advance to filter/persist
        elif stage == dx.FILTER:
            submits, rs = dx.assemble_filter(rs)
            if submits:
                jobs = await _submit_map(llm_client, rs, submits)
                return dx.begin_filter(rs, jobs), list(jobs.values())
            rs = dx.begin_filter(rs, {})  # no items → persist
        else:  # PERSIST / unexpected
            return rs, None


async def _advance_after_fold(conn, llm_client: LLMClient, ej_id, fresh: dict, fold_stage: str) -> dict | None:
    """Under the open row lock: if still mid-fan-in on `fold_stage`, persist the partial
    state and stay; else (the stage completed) finalize the filter stitch / dispatch the
    next stage. Returns the completed rs to persist OUTSIDE the lock, or None when it
    persisted in-flight under the lock."""
    if fresh["stage"] == fold_stage:
        ids = list(fresh[_INFLIGHT_KEY[fold_stage]].values())
        await _persist_inflight(conn, ej_id, ids, fresh)
        return None
    if fold_stage == dx.FILTER:
        return dx.finalize_filter(fresh)  # filter only ever completes → PERSIST
    rs2, inflight = await _dispatch_next(llm_client, fresh)
    if inflight is not None:
        await _persist_inflight(conn, ej_id, inflight, rs2)
        return None
    return rs2


async def _resume(pool, knowledge_client, llm_client: LLMClient, owner_user_id, job_id, ej_id, rs: dict) -> None:
    """Fold the terminal job into the SM, then submit the next stage or persist."""
    set_campaign_id(rs.get("campaign_id"))
    set_billing_user_id(rs.get("billing_user_id"))
    try:
        job = await llm_client.get_job(job_id, user_id=owner_user_id or rs.get("billing_user_id") or rs["user_id"])
        stage = rs["stage"]

        if stage == dx.ENTITY:
            # D-WX-TRIO-FANIN-RACE (entity stage) — serialise the entity fold + trio
            # submit under the row lock, exactly like the TRIO fold, so the sweeper and
            # the consumer (separate gather'd tasks — concurrent even single-replica) or
            # multiple replicas can't both fold this entity terminal and double-submit the
            # trio. submit_job is a fire-and-forget POST (fast enqueue, NOT an LLM wait),
            # so holding the lock across the 3 submits is cheap. The claim re-verifies
            # provider_job_ids still contains THIS entity job — a concurrent fold has
            # already advanced it to the trio ids, so that contender skips.
            empty_rs = None
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT resume_state FROM extraction_jobs
                           WHERE job_id=$1 AND resume_state IS NOT NULL
                             AND provider_job_ids @> to_jsonb($2::text) FOR UPDATE""",
                        ej_id, job_id,
                    )
                    if row is None:
                        return  # a concurrent driver already folded this entity terminal
                    fresh = row["resume_state"]
                    fresh = fresh if isinstance(fresh, dict) else json.loads(fresh)
                    if fresh.get("stage") != dx.ENTITY:
                        return  # already advanced past entity
                    fresh = dx.fold_entity_job(fresh, job)
                    if fresh["stage"] == dx.TRIO:
                        submits = dx.assemble_trio_submits(fresh)
                        # C12 (D-C12-CONCURRENCY-DECOUPLED) — bound concurrent in-flight
                        # trio submits to the job's concurrency_level (via _submit_map's
                        # Semaphore), exactly like the recovery/filter fan-outs. None ⇒
                        # unbounded (back-compat). The ops set is UNCHANGED — only HOW
                        # MANY submit at once is capped; begin_trio records the same ids.
                        trio_jobs = await _submit_map(llm_client, fresh, submits)
                        fresh = dx.begin_trio(fresh, trio_jobs)
                        await _persist_inflight(conn, ej_id, list(trio_jobs.values()), fresh)
                    elif fresh["stage"] in (dx.RECOVERY, dx.FILTER):
                        # C12 — an entities-only build (no trio target) with
                        # recovery/precision-filter enabled advances ENTITY →
                        # RECOVERY/FILTER directly (skipping the trio). Dispatch
                        # that fan-out UNDER the lock just like the trio path;
                        # only the persist (PERSIST stage / no fan-out work)
                        # finalizes outside. Without this the chunk would
                        # persist empty, dropping recovery/filter entirely.
                        rs2, inflight = await _dispatch_next(llm_client, fresh)
                        if inflight is not None:
                            await _persist_inflight(conn, ej_id, inflight, rs2)
                        else:
                            empty_rs = rs2  # fan-out had no work → persist now
                    else:  # no entities → finalize empty OUTSIDE the lock (persist_chunk re-locks)
                        empty_rs = fresh
            if empty_rs is not None:
                await _persist_chunk(pool, knowledge_client, ej_id, empty_rs)

        elif stage == dx.TRIO:
            # D-WX-TRIO-FANIN-RACE — the fold is a read-modify-write on resume_state.
            # With >1 worker-ai replica, the relation/event/fact terminal events arrive
            # concurrently; each replica would read the same rs, fold only its own op,
            # and the last write would clobber the others → a lost op → the fan-in
            # never completes (chunk stuck in TRIO). SELECT ... FOR UPDATE serialises
            # the read-modify-write on the row so every op is folded. The fold +
            # in-flight persist run UNDER the lock; the terminal persist (a knowledge
            # HTTP call) runs OUTSIDE it (persist_chunk re-locks + is idempotent).
            completed_rs = None
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT resume_state FROM extraction_jobs
                           WHERE job_id=$1 AND resume_state IS NOT NULL FOR UPDATE""",
                        ej_id,
                    )
                    if row is None:
                        return  # finalized/cleared by a concurrent winner
                    fresh = row["resume_state"]
                    fresh = fresh if isinstance(fresh, dict) else json.loads(fresh)
                    if fresh.get("stage") != dx.TRIO:
                        return  # a concurrent fold already advanced past trio
                    op = dx.op_for_job(fresh, job_id)
                    if op is None:  # duplicate of an already-superseded op
                        return
                    fresh = dx.fold_trio_job(fresh, op, job)
                    # All 3 folded → dispatch recovery/filter (or persist); else persist
                    # the partial fan-in and stay in trio. _advance_after_fold submits the
                    # next fan-out UNDER this lock (fast fire-and-forget POSTs).
                    completed_rs = await _advance_after_fold(conn, llm_client, ej_id, fresh, dx.TRIO)
            if completed_rs is not None:
                await _persist_chunk(pool, knowledge_client, ej_id, completed_rs)

        elif stage == dx.RECOVERY:
            # Recovery is a fan-out of Tier-3 classifier batches. Same FOR UPDATE
            # read-modify-write serialisation as trio: fold this batch's verdicts, then
            # either persist the partial fan-in or (all folded) dispatch filter/persist.
            completed_rs = None
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT resume_state FROM extraction_jobs
                           WHERE job_id=$1 AND resume_state IS NOT NULL FOR UPDATE""",
                        ej_id,
                    )
                    if row is None:
                        return
                    fresh = row["resume_state"]
                    fresh = fresh if isinstance(fresh, dict) else json.loads(fresh)
                    if fresh.get("stage") != dx.RECOVERY:
                        return
                    batch_key = dx.recovery_task_for_job(fresh, job_id)
                    if batch_key is None:  # dup/superseded batch
                        return
                    fresh = dx.fold_recovery_terminal(fresh, batch_key, job)
                    completed_rs = await _advance_after_fold(conn, llm_client, ej_id, fresh, dx.RECOVERY)
            if completed_rs is not None:
                await _persist_chunk(pool, knowledge_client, ej_id, completed_rs)

        elif stage == dx.FILTER:
            # Filter is a fan-out of (category, batch) tasks. Fold this task's verdicts;
            # when the whole fan-in completes, _advance_after_fold runs finalize_filter
            # (compute kept + stitch) and returns the finalize-ready rs.
            completed_rs = None
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT resume_state FROM extraction_jobs
                           WHERE job_id=$1 AND resume_state IS NOT NULL FOR UPDATE""",
                        ej_id,
                    )
                    if row is None:
                        return
                    fresh = row["resume_state"]
                    fresh = fresh if isinstance(fresh, dict) else json.loads(fresh)
                    if fresh.get("stage") != dx.FILTER:
                        return
                    task_key = dx.filter_task_for_job(fresh, job_id)
                    if task_key is None:
                        return
                    fresh = dx.fold_filter_terminal(fresh, task_key, job)
                    completed_rs = await _advance_after_fold(conn, llm_client, ej_id, fresh, dx.FILTER)
            if completed_rs is not None:
                await _persist_chunk(pool, knowledge_client, ej_id, completed_rs)

        else:  # PERSIST / unexpected — finalize defensively
            await _persist_chunk(pool, knowledge_client, ej_id, rs)
    finally:
        set_campaign_id(None)
        set_billing_user_id(None)


async def _handle(pool, knowledge_client, llm_client, fields: dict) -> None:
    job_id = _field(fields, "job_id")
    owner = _field(fields, "owner_user_id") or None
    if not job_id:
        return
    loaded = await _load_for_job(pool, job_id)
    if loaded is None:
        return  # not a decoupled extraction job (or already finalized/superseded)
    ej_id, rs = loaded
    await _resume(pool, knowledge_client, llm_client, owner, job_id, ej_id, rs)


async def _process_msg(client, pool, knowledge_client, llm_client, msg_id: str, fields: dict) -> None:
    """Process one terminal event with BOUNDED retry (review-impl finding 1). On a
    transient failure (DB blip, knowledge 503, slow get_job) we DO NOT ack — the
    message stays in the PEL and is re-processed by the startup drain on the next run,
    so the chapter is NOT permanently dropped; the Wave-1b stuck-resume sweeper is the
    additional runtime backstop (a row idle past the timeout is re-driven even without
    a redelivery). A genuine poison is acked after MAX_RETRIES deliveries so it can't
    redeliver-storm. Mirrors the glossary / translation terminal consumers."""
    try:
        await _handle(pool, knowledge_client, llm_client, fields)
        await client.xack(TERMINAL_STREAM, GROUP, msg_id)
    except Exception as exc:  # noqa: BLE001
        retry_key = f"worker-ai:extract-resume:retry:{msg_id}"
        count = int(await client.incr(retry_key))
        await client.expire(retry_key, 3600)
        if count >= MAX_RETRIES:
            # /review-impl finding 1 — the finalize tx is strict (no best-effort
            # cursor-advance fallback), so a POISON finalize leaves resume_state SET
            # while we ack here: a Redis stream gives no redelivery after ack. The
            # Wave-1b stuck-resume sweeper IS the runtime backstop (it re-drives a row
            # idle past the timeout even with no redelivery), so name the stranded chunk
            # loudly for observability; the sweeper recovers it on its next tick.
            job_id = _field(fields, "job_id")
            logger.error(
                "decoupled-extract resume POISON after %d× msg=%s job=%s — acking; the "
                "chunk's resume_state is STRANDED for now (no terminal-event redelivery "
                "after ack). Recovery: the Wave-1b stuck-resume sweeper re-drives it on "
                "its next tick. Last error: %s",
                count, msg_id, job_id, exc,
            )
            await client.xack(TERMINAL_STREAM, GROUP, msg_id)
            await client.delete(retry_key)
        else:
            logger.warning(
                "decoupled-extract resume failed (%d/%d) msg=%s — leaving unacked "
                "(recovered by the startup drain): %s",
                count, MAX_RETRIES, msg_id, exc,
            )


async def _drain_pending(client, pool, knowledge_client, llm_client, consumer_name: str) -> None:
    """Re-process this consumer's unacked PEL (id '0') — recovers transient-failed
    events left unacked by a prior run."""
    try:
        results = await client.xreadgroup(
            GROUP, consumer_name, {TERMINAL_STREAM: "0"}, count=100,
        )
        for _stream, messages in results or []:
            for msg_id, fields in messages:
                await _process_msg(client, pool, knowledge_client, llm_client, msg_id, fields)
    except Exception:
        logger.exception("error draining pending decoupled-extract events")


# ── WX Wave 1b — stuck-resume sweeper (D-WX-SUBMIT-PERSIST-GAP) ───────────────────
# The runtime backstop the strict-tx finalize (Wave 1a) made load-bearing: a Redis
# stream gives no redelivery after ack, so a consumer crash/poison, a lost terminal
# event, or a submit→persist gap can strand an extraction_jobs row with resume_state
# set. This re-drives any such row idle longer than the timeout by re-checking each
# in-flight provider_job_id's terminal status and replaying the consumer's idempotent
# `_resume` (the FOR UPDATE / finalize-recheck make a concurrent consumer + sweeper
# safe). A still-in-flight job is left alone (slow, not stuck).


async def _sweep_once(pool, knowledge_client, llm_client: LLMClient, *,
                      timeout_s: int, batch: int) -> int:
    """One sweep tick. Returns the number of rows re-driven (for tests/telemetry)."""
    # D-WX-TRIO-FANIN-RACE (sweep side) — FOR UPDATE SKIP LOCKED so concurrent
    # worker-ai replicas claim DISJOINT stranded rows: a row already locked by another
    # replica's in-flight sweep is skipped (not blocked on), preventing two replicas
    # from both re-driving the same chunk and double-submitting its ENTITY-stage fan-out.
    # The lock is held only for the duration of this SELECT's own (implicit) statement
    # context here; _resume re-locks the row under its own FOR UPDATE when it folds, so
    # the claim is a best-effort partition, not a long-held lock. The trio fold's own
    # FOR UPDATE (no SKIP — it must block to serialise the read-modify-write) is unchanged.
    rows = await pool.fetch(
        """SELECT job_id, provider_job_ids, resume_state
           FROM extraction_jobs
           WHERE resume_state IS NOT NULL
             AND status IN ('running', 'paused')
             AND updated_at < now() - make_interval(secs => $1::int)
           ORDER BY updated_at ASC
           LIMIT $2::int
           FOR UPDATE SKIP LOCKED""",
        timeout_s, batch,
    )
    redriven = 0
    for row in rows:
        rs = row["resume_state"]
        rs = rs if isinstance(rs, dict) else json.loads(rs)
        job_ids = row["provider_job_ids"] or []
        if not isinstance(job_ids, list):
            job_ids = json.loads(job_ids)
        owner = rs.get("billing_user_id") or rs.get("user_id")
        for jid in job_ids:
            try:
                job = await llm_client.get_job(jid, user_id=owner)
            except Exception:  # noqa: BLE001 — a transient get_job fault: try the next id/tick
                continue
            # Only replay a TERMINAL job — _resume folds the job result unconditionally
            # (it's normally driven by a terminal event), so re-driving a still-running
            # job would fold an incomplete result. Slow ≠ stuck. Use the SDK's own
            # predicate (the single source of truth for terminal states — no parallel
            # status set to drift out of sync).
            if not job.is_terminal():
                continue
            try:
                await _resume(pool, knowledge_client, llm_client, None, jid, row["job_id"], rs)
                redriven += 1
                logger.warning(
                    "resume-sweep: re-drove stranded chunk ej=%s via job=%s (stage=%s)",
                    row["job_id"], jid, rs.get("stage"),
                )
            except Exception:  # noqa: BLE001
                logger.exception("resume-sweep: re-drive failed ej=%s job=%s", row["job_id"], jid)
            break  # _resume advanced/persisted the row; re-evaluate on the next tick
    return redriven


async def run_resume_sweeper(pool, knowledge_client, llm_client: LLMClient, *,
                             interval_s: int, timeout_s: int, batch: int) -> None:
    """Long-running periodic sweeper (gather'd in app.main alongside the consumer,
    gated on the decouple flag). interval_s <= 0 ⇒ disabled (returns immediately)."""
    import asyncio
    if interval_s <= 0:
        logger.info("resume sweeper disabled (interval<=0)")
        return
    logger.info(
        "decoupled-extract resume sweeper started (interval=%ds timeout=%ds batch=%d)",
        interval_s, timeout_s, batch,
    )
    while True:
        try:
            n = await _sweep_once(pool, knowledge_client, llm_client,
                                  timeout_s=timeout_s, batch=batch)
            if n:
                logger.info("resume-sweep: re-drove %d stranded chunk(s)", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — one bad tick must not kill the loop
            logger.exception("resume sweeper tick failed")
        await asyncio.sleep(interval_s)


async def consume_llm_terminal_stream(
    pool, knowledge_client, llm_client: LLMClient, *,
    redis_url: str, consumer_name: str, block_ms: int = 5000,
) -> None:
    """Long-running consumer task (run via asyncio.gather in app.main, gated on the
    decouple flag). Cancel-safe: shutdown raises CancelledError from xreadgroup."""
    import asyncio
    # socket_timeout=None is REQUIRED — a per-read socket timeout shorter than
    # block_ms pre-empts the server-side BLOCK and raises redis.TimeoutError, which
    # would crash the consumer task (and the worker via the gather). Mirrors the
    # glossary / translation terminal consumers.
    client = aioredis.from_url(redis_url, decode_responses=True, socket_timeout=None)
    try:
        try:
            # id="$" — forward-looking; a decoupled job in flight at first deploy
            # doesn't exist (flag was off). After creation the group tracks delivery.
            await client.xgroup_create(TERMINAL_STREAM, GROUP, id="$", mkstream=True)
            logger.info("created consumer group %s on %s", GROUP, TERMINAL_STREAM)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        # Recover any unacked events from a prior run BEFORE reading new ones
        # (review-impl finding 1 — the recovery path for transient-failed resumes).
        await _drain_pending(client, pool, knowledge_client, llm_client, consumer_name)
        logger.info("decoupled-extract terminal consumer started (name=%s)", consumer_name)
        while True:
            try:
                results = await client.xreadgroup(
                    GROUP, consumer_name, {TERMINAL_STREAM: ">"}, count=10, block=block_ms,
                )
                for _stream, messages in results or []:
                    for msg_id, fields in messages:
                        await _process_msg(client, pool, knowledge_client, llm_client, msg_id, fields)
            except aioredis.TimeoutError:
                continue  # idle long-poll — no new events this block window
            except aioredis.ConnectionError:
                logger.warning("terminal consumer: redis connection lost; retry in 5s")
                await asyncio.sleep(5)
    finally:
        await client.aclose()


# ── Unified Job Control Plane P1 — money-path migration onto the shared base ──────
# The SAME transport recipe as the other 11 consumers, but flag-gated: this class is the
# NEW path; the functional `consume_llm_terminal_stream` + `run_resume_sweeper` above stay
# as the proven fallback until a live extraction E2E flips the flag (a regression here
# double-spends or strands chapters — extra scrutiny). The business state machine (`_handle`
# → `_resume` → entity/trio/recovery/filter/persist) and the stuck-resume sweep (`_sweep_once`)
# are reused VERBATIM; only the Redis transport (group/PEL-drain/idle/retry-poison) is the
# shared scaffold. consumer_name / group / retry-key prefix preserved (PEL continuity).
class ExtractTerminalConsumer(BaseTerminalConsumer):
    """Decoupled-extraction terminal-event consumer on the shared transport scaffold.
    ``handle`` folds one terminal event through the chunk state machine; ``sweep_once``
    re-drives stranded resume_state rows."""

    stream = TERMINAL_STREAM
    group = GROUP
    consumer_name_prefix = "worker-ai-extract"
    retry_prefix = "worker-ai:extract-resume:retry"

    def __init__(
        self, redis_url, pool, knowledge_client, llm_client,
        *, consumer_name: str | None = None, block_ms: int = 5000,
    ) -> None:
        self.block_ms = block_ms
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._knowledge_client = knowledge_client
        self._llm_client = llm_client

    async def handle(self, fields: dict) -> None:
        # _handle returns on no-job-id / no-matching-row (→ base acks) and raises on a
        # transient fault (→ base bounded-retry-then-poison, identical to the old
        # _process_msg). The strict-tx finalize + FOR-UPDATE races inside _resume are
        # unchanged, so at-least-once redelivery + the sweeper stay double-spend-safe.
        await _handle(self._pool, self._knowledge_client, self._llm_client, fields)

    async def sweep_once(self, *, timeout_s: int, batch: int) -> int:
        return await _sweep_once(
            self._pool, self._knowledge_client, self._llm_client,
            timeout_s=timeout_s, batch=batch,
        )
