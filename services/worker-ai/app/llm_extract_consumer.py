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

import json
import logging
from uuid import UUID

import redis.asyncio as aioredis

from app import decoupled_extract as dx
from app.llm_client import LLMClient, set_billing_user_id, set_campaign_id

logger = logging.getLogger(__name__)

TERMINAL_STREAM = "loreweave:events:llm_job_terminal"
GROUP = "worker-ai-extract-resume"
_DEFAULT_COST_PER_ITEM = None  # resolved lazily from runner to avoid an import cycle


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
        """SELECT id, resume_state FROM extraction_jobs
           WHERE resume_state IS NOT NULL
             AND provider_job_ids @> to_jsonb($1::text)""",
        provider_job_id,
    )
    if not row or row["resume_state"] is None:
        return None
    rs = row["resume_state"]
    rs = rs if isinstance(rs, dict) else json.loads(rs)
    return row["id"], rs


async def _persist_inflight(pool, ej_id, provider_job_ids: list[str], rs: dict) -> None:
    await pool.execute(
        """UPDATE extraction_jobs
           SET provider_job_ids=$2::jsonb, resume_state=$3::jsonb, pipeline_stage=$4
           WHERE id=$1""",
        ej_id, json.dumps([str(j) for j in provider_job_ids]),
        json.dumps(rs), rs["stage"],
    )


async def _clear_resume(pool, ej_id) -> None:
    await pool.execute(
        "UPDATE extraction_jobs SET resume_state=NULL, provider_job_ids=NULL, pipeline_stage='done' WHERE id=$1",
        ej_id,
    )


async def _persist_chunk(pool, knowledge_client, ej_id, rs: dict) -> None:
    """Terminal stage: persist candidates → advance cursor + emit chapter_extracted
    (atomic) → record spend → clear resume_state. Finalize-FIRST then clear (a crash
    between redelivers; the lookup still finds the row to retry). The campaign
    reconcile backstops a lost completion event."""
    from app.runner import (
        _DEFAULT_COST_PER_ITEM as COST,
        _advance_cursor_and_emit_run,
        _record_spending,
    )

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
    )

    # Fill the pre-built run_payload's metrics from the persist result, then advance
    # the cursor + emit the run + the campaign completion event in ONE tx.
    run_payload = dict(rs["run_payload"])
    run_payload["metrics"] = {
        **run_payload.get("metrics", {}),
        "entities_merged": result.entities_merged,
        "relations_created": result.relations_created,
        "events_merged": result.events_merged,
        "facts_merged": result.facts_merged,
    }
    await _advance_cursor_and_emit_run(
        pool, owner_id, UUID(ctx["job_id"]), rs["cursor_to_set"], run_payload,
        chapter_extracted=rs.get("chapter_extracted"),
    )
    if project_id is not None:
        await _record_spending(pool, owner_id, project_id, COST)
    await _clear_resume(pool, ej_id)
    logger.info(
        "decoupled extraction: chunk %s persisted via event path (entities=%d relations=%d)",
        ctx["source_id"], result.entities_merged, result.relations_created,
    )


async def _resume(pool, knowledge_client, llm_client: LLMClient, owner_user_id, job_id, ej_id, rs: dict) -> None:
    """Fold the terminal job into the SM, then submit the next stage or persist."""
    set_campaign_id(rs.get("campaign_id"))
    set_billing_user_id(rs.get("billing_user_id"))
    try:
        job = await llm_client.get_job(job_id, user_id=owner_user_id or rs.get("billing_user_id") or rs["user_id"])
        stage = rs["stage"]

        if stage == dx.ENTITY:
            rs = dx.fold_entity_job(rs, job)
            if rs["stage"] == dx.TRIO:
                submits = dx.assemble_trio_submits(rs)
                trio_jobs: dict[str, str] = {}
                for op, kwargs in submits.items():
                    sub = await llm_client.submit_job(user_id=rs["user_id"], **kwargs)
                    trio_jobs[op] = str(sub.job_id)
                rs = dx.begin_trio(rs, trio_jobs)
                await _persist_inflight(pool, ej_id, list(trio_jobs.values()), rs)
            else:  # no entities → persist empty
                await _persist_chunk(pool, knowledge_client, ej_id, rs)

        elif stage == dx.TRIO:
            op = dx.op_for_job(rs, job_id)
            if op is None:  # duplicate of an already-superseded op
                return
            rs = dx.fold_trio_job(rs, op, job)
            if rs["stage"] == dx.TRIO:  # still waiting on the other ops
                await _persist_inflight(pool, ej_id, list(rs["trio_jobs"].values()), rs)
            else:  # all 3 folded → persist
                await _persist_chunk(pool, knowledge_client, ej_id, rs)

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


async def consume_llm_terminal_stream(
    pool, knowledge_client, llm_client: LLMClient, *,
    redis_url: str, consumer_name: str, block_ms: int = 5000,
) -> None:
    """Long-running consumer task (run via asyncio.gather in app.main, gated on the
    decouple flag). Cancel-safe: shutdown raises CancelledError from xreadgroup."""
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        try:
            # id="$" — forward-looking; a decoupled job in flight at first deploy
            # doesn't exist (flag was off). After creation the group tracks delivery.
            await client.xgroup_create(TERMINAL_STREAM, GROUP, id="$", mkstream=True)
            logger.info("created consumer group %s on %s", GROUP, TERMINAL_STREAM)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        logger.info("decoupled-extract terminal consumer started (name=%s)", consumer_name)
        while True:
            try:
                results = await client.xreadgroup(
                    GROUP, consumer_name, {TERMINAL_STREAM: ">"}, count=10, block=block_ms,
                )
                for _stream, messages in results or []:
                    for msg_id, fields in messages:
                        try:
                            await _handle(pool, knowledge_client, llm_client, fields)
                            await client.xack(TERMINAL_STREAM, GROUP, msg_id)
                        except Exception:
                            logger.exception(
                                "decoupled-extract resume failed for msg %s — acking "
                                "to avoid a redelivery storm (the chapter stays in-flight; "
                                "the 2h stale sweeper / campaign reconcile is the backstop)",
                                msg_id,
                            )
                            await client.xack(TERMINAL_STREAM, GROUP, msg_id)
            except aioredis.ConnectionError:
                logger.warning("terminal consumer: redis connection lost; retry in 5s")
                import asyncio
                await asyncio.sleep(5)
    finally:
        await client.aclose()
