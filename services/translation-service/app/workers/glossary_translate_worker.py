"""Glossary batch attribute translation worker."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from uuid import UUID

from loreweave_llm.errors import (
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMStreamNotSupported,
    LLMTransientRetryNeededError,
)

from loreweave_jobs import emit_job_event_safe

from ..llm_client import LLMClient
from .glossary_client import fetch_translation_candidates, post_apply_translations
from .glossary_translate_prompt import (
    attr_response_format,
    build_system_prompt,
    build_user_prompt,
    entity_output_budget,
    parse_translation_response,
)
from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields

log = logging.getLogger(__name__)

# D-LLM-FAILURE-RATE #1 — structured-output enforcement for the translation
# pipelines. Default ON; set TRANSLATION_STRUCTURED_OUTPUT=0 to disable fleet-wide
# (the per-call LLMInvalidRequest fallback already degrades a single unsupported
# model safely).
_STRUCTURED_OUTPUT_ENABLED = os.getenv(
    "TRANSLATION_STRUCTURED_OUTPUT", "1"
).strip().lower() not in ("0", "false", "no", "off")

_PAGE_SIZE = 25

# bug #8 — upper bound for the per-entity output budget (entity_output_budget floors at
# the old 4096 default; this is the ceiling). Tunable per the deployed model's real max
# output. A genuinely larger entity needs attribute chunking (#26), not a bigger cap.
_GLOSSARY_TRANSLATE_MAX_OUTPUT_TOKENS = int(
    os.getenv("GLOSSARY_TRANSLATE_MAX_OUTPUT_TOKENS", "32768") or "32768"
)

# bug #4: hard ceiling on how many entities translate concurrently, regardless of the
# caller's requested concurrency (protects the provider/GPU + glossary-service). 1 ⇒
# sequential (prior behavior). Mirrors extraction's _EXTRACTION_MAX_CONCURRENCY.
_GLOSSARY_TRANSLATE_MAX_CONCURRENCY = 16

# Unified Job Control Plane (producer-emit backfill, D-JOBS-GLOSSARY-TRANSLATE-UNWIRED).
# Glossary batch translation is hosted in translation-service; it surfaces in the unified
# Jobs screen as service="translation", kind="glossary_translation" (DISTINCT from the
# "translation" chapter pipeline + "glossary_extraction"). The create endpoint emits
# 'pending' in-tx; this worker emits running/terminal/cancelled best-effort post-commit
# (emit_job_event_safe — a failed emit must not crash the run; the reconcile UNION in
# internal_dispatch.py is the H1 backstop).
_JOB_SERVICE = "translation"
_JOB_KIND = "glossary_translation"


async def handle_glossary_translate_job(
    msg: dict, pool, publish_event, llm_client: LLMClient,
) -> None:
    job_id = UUID(msg["job_id"])
    user_id = msg["user_id"]
    try:
        await _run_job(msg, job_id, user_id, pool, publish_event, llm_client)
    except Exception as exc:
        log.exception("glossary_translate: job %s failed: %s", job_id, exc)
        async with pool.acquire() as db:
            await db.execute(
                """UPDATE glossary_translation_jobs
                   SET status='failed', error_message=$2, finished_at=now()
                   WHERE job_id=$1""",
                job_id, str(exc)[:500],
            )
        await emit_job_event_safe(
            pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
            kind=_JOB_KIND, status="failed",
            error={"code": "glossary_translation_failed", "message": str(exc)[:500]},
        )
        await publish_event(user_id, {
            "event": "job.status_changed",
            "job_id": str(job_id),
            "job_type": "translate_glossary",
            "payload": {"status": "failed", "error": str(exc)[:200]},
        })


async def _run_job(
    msg: dict, job_id: UUID, user_id: str, pool, publish_event, llm_client: LLMClient,
) -> None:
    book_id = msg["book_id"]
    target_language = msg["target_language"]
    source_language = msg.get("source_language", "zh")
    model_source = msg.get("model_source", "platform_model")
    model_ref = msg.get("model_ref")
    overwrite_mode = msg.get("overwrite_mode", "missing_only")
    metadata = msg.get("metadata") or {}
    entity_ids_filter = metadata.get("entity_ids")
    # AI-task standard — graded reasoning effort (clamped none|low|medium|high at the
    # router). Fall back to the deprecated thinking_enabled bool (True→medium) for any
    # in-flight message minted before the field existed.
    reasoning_effort = (
        msg.get("reasoning_effort")
        or metadata.get("reasoning_effort")
        or ("medium" if bool(msg.get("thinking_enabled", metadata.get("thinking_enabled", False))) else "none")
    )
    # bug #4: per-entity LLM-call fan-out cap. Absent/None on a pre-field message ⇒ 1
    # (sequential, prior behavior). Clamped to the hard ceiling.
    concurrency = max(1, min(_GLOSSARY_TRANSLATE_MAX_CONCURRENCY, int(msg.get("concurrency") or 1)))

    # Cancel-safe claim (same fix as extraction_worker): only start a job that is NOT
    # already cancelled/terminal. An unconditional "SET status='running'" here would
    # CLOBBER a 'cancelling' status on the next redelivery, so the per-page cancel check
    # below never sees it and the job keeps running despite being cancelled. If the guard
    # matches nothing, settle + return so message.process() ACKs and drops the message.
    # RETURNING owner_user_id folds in the owner lookup (NOT NULL → None ⇔ guard failed).
    async with pool.acquire() as db:
        owner_user_id = await db.fetchval(
            "UPDATE glossary_translation_jobs SET status='running', started_at=now() "
            "WHERE job_id=$1 AND status NOT IN "
            "('cancelled','cancelling','completed','completed_with_errors','failed') "
            "RETURNING owner_user_id",
            job_id,
        )
        settled = None
        if owner_user_id is None:
            settled = await db.fetchval(
                "UPDATE glossary_translation_jobs SET status='cancelled', finished_at=now() "
                "WHERE job_id=$1 AND status='cancelling' RETURNING job_id",
                job_id,
            )
    if owner_user_id is None:
        log.info("glossary_translate: job %s not runnable (cancelled/terminal) — acking, no work", job_id)
        # Emit 'cancelled' ONLY if we actually flipped a cancelling row — an already-terminal
        # job matched nothing and must not be re-marked cancelled (mirrors extraction_worker).
        if settled is not None:
            await emit_job_event_safe(
                pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
                kind=_JOB_KIND, status="cancelled",
            )
        await publish_event(user_id, {
            "event": "job.status_changed",
            "job_id": str(job_id),
            "job_type": "translate_glossary",
            "payload": {"status": "cancelled"},
        })
        return

    # claimed → running: emit the running transition (best-effort, post-claim).
    await emit_job_event_safe(
        pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
        kind=_JOB_KIND, status="running",
    )
    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "translate_glossary",
        "payload": {"status": "running"},
    })

    offset = 0
    processed_entity_ids: set[str] = set()
    completed = 0
    failed = 0
    attrs_translated = 0
    attrs_skipped = 0
    total_in = 0
    total_out = 0
    total_entities = 0
    # bug #37 — realized LLM calls: one per entity that actually issues a call (an entity with
    # no attributes returns early without a call). Pairs with the create event's
    # estimated_llm_calls (= entity_count) for the Jobs-GUI "done / total".
    llm_calls_made = 0

    # bug #4: translate up to `concurrency` entities in parallel. Each entity is independent
    # (its own LLM call + its own glossary rows), so a Semaphore-bounded gather over a page
    # safely fans out the per-entity LLM calls. Shared counters are mutated between awaits only
    # (asyncio is single-threaded → atomic), mirroring the extraction worker. concurrency == 1
    # keeps the EXACT prior sequential behavior. A single entity's unexpected error fails only
    # that entity (logged) — it must not abort the whole batch.
    sem = asyncio.Semaphore(concurrency)

    async def _process_entity(ent: dict) -> None:
        nonlocal completed, failed, attrs_translated, attrs_skipped, total_in, total_out, llm_calls_made
        try:
            async with sem:
                entity_id = ent["entity_id"]
                attrs = ent.get("attributes") or []
                if not attrs:
                    completed += 1
                    return

                expected_codes = {a["code"] for a in attrs}
                code_to_avid = {a["code"]: a["attr_value_id"] for a in attrs}

                system_prompt = build_system_prompt(source_language, target_language)
                user_prompt = build_user_prompt(
                    ent.get("display_name", ""), ent.get("kind_code", ""), attrs,
                )

                call_input: dict = {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                    # bug #8 — budget scales with THIS entity's attribute values (floored at
                    # the old 4096) instead of a flat cap that truncated large entities.
                    "max_tokens": entity_output_budget(
                        attrs, ceiling=_GLOSSARY_TRANSLATE_MAX_OUTPUT_TOKENS
                    ),
                    # reasoning_effort="none" ⇒ explicit disable (thinking:false), matching
                    # the old thinking_llm_fields(False); low/medium/high ⇒ graded.
                    **reasoning_fields(
                        ReasoningDirective(effort=reasoning_effort, passthrough=False, source="user")
                    ),
                }
                # D-LLM-FAILURE-RATE #1 — force a valid JSON object of the expected
                # attribute codes (kills the "Expecting ',' delimiter" parse failures
                # that fail an entity). A model/server that rejects the shape raises
                # LLMInvalidRequest and is retried ONCE without it.
                if _STRUCTURED_OUTPUT_ENABLED:
                    call_input["response_format"] = attr_response_format(expected_codes)

                async def _submit(_inp: dict):
                    return await llm_client.submit_and_wait(
                        user_id=str(owner_user_id),
                        operation="chat",
                        model_source=model_source,
                        model_ref=str(model_ref),
                        input=_inp,
                        chunking=None,
                        job_meta={
                            "usage_purpose": "glossary_translation",
                            "operation": "glossary_translate",
                            "glossary_translate_job_id": str(job_id),
                            "entity_id": entity_id,
                        },
                        transient_retry_budget=1,
                    )

                llm_calls_made += 1  # bug #37 — this entity issues an LLM call (retry = same logical call)
                try:
                    try:
                        sdk_job = await _submit(call_input)
                    except LLMInvalidRequest:
                        if "response_format" not in call_input:
                            raise
                        log.warning(
                            "glossary_translate: response_format rejected for entity %s — retrying without structured output",
                            entity_id,
                        )
                        call_input.pop("response_format", None)
                        sdk_job = await _submit(call_input)
                except (LLMQuotaExceeded, LLMModelNotFound, LLMAuthFailed,
                        LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
                    log.error("glossary_translate: permanent error entity %s: %s", entity_id, exc)
                    failed += 1
                    return
                except (LLMTransientRetryNeededError, LLMError) as exc:
                    log.error("glossary_translate: transient error entity %s: %s", entity_id, exc)
                    failed += 1
                    return

                if sdk_job.status != "completed":
                    failed += 1
                    return

                result_payload = sdk_job.result or {}
                messages_out = result_payload.get("messages") or []
                raw = ""
                if isinstance(messages_out, list) and messages_out:
                    first = messages_out[0]
                    if isinstance(first, dict):
                        raw = first.get("content", "") or ""
                usage = result_payload.get("usage") or {}
                total_in += int(usage.get("input_tokens") or 0)
                total_out += int(usage.get("output_tokens") or 0)
                try:
                    translated = parse_translation_response(raw, expected_codes)
                except (json.JSONDecodeError, ValueError) as exc:
                    log.warning("glossary_translate: parse failed entity %s: %s", entity_id, exc)
                    failed += 1
                    return

                apply_items = [
                    {
                        "entity_id": entity_id,
                        "attr_value_id": code_to_avid[code],
                        "value": val,
                    }
                    for code, val in translated.items()
                    if code in code_to_avid
                ]
                result = await post_apply_translations(book_id, target_language, apply_items)
                if result is None:
                    failed += 1
                    return

                attrs_translated += result.get("translated", 0)
                attrs_skipped += result.get("skipped_verified", 0) + result.get("skipped_empty", 0)
                completed += 1

                # Live progress on the broker channel (no DB connection — safe to do per
                # entity under concurrency). The durable DB write is batched per page below
                # (a per-entity DB write would hold up to `concurrency` of the shared
                # max_size=10 pool's connections at once — review MED).
                await publish_event(user_id, {
                    "event": "job.status_changed",
                    "job_id": str(job_id),
                    "job_type": "translate_glossary",
                    "payload": {
                        "status": "running",
                        "completed_entities": completed,
                        "total_entities": total_entities,
                    },
                })
        except Exception as exc:  # noqa: BLE001 — one entity's unexpected failure ≠ whole batch
            log.error("glossary_translate: unexpected error entity %s: %s", ent.get("entity_id"), exc)
            failed += 1

    while True:
        async with pool.acquire() as db:
            row = await db.fetchrow(
                "SELECT status FROM glossary_translation_jobs WHERE job_id=$1", job_id,
            )
        if row and row["status"] == "cancelling":
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE glossary_translation_jobs SET status='cancelled', finished_at=now() WHERE job_id=$1",
                    job_id,
                )
            await emit_job_event_safe(
                pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
                kind=_JOB_KIND, status="cancelled",
            )
            await publish_event(user_id, {
                "event": "job.status_changed",
                "job_id": str(job_id),
                "job_type": "translate_glossary",
                "payload": {"status": "cancelled"},
            })
            return

        fetch_offset = 0 if overwrite_mode == "missing_only" else offset
        page = await fetch_translation_candidates(
            book_id, target_language,
            overwrite_mode=overwrite_mode,
            limit=_PAGE_SIZE,
            offset=fetch_offset,
            entity_ids=entity_ids_filter,
        )
        if page is None:
            raise RuntimeError("glossary-service translation-candidates unavailable")
        if fetch_offset == 0 and (overwrite_mode == "missing_only" or offset == 0):
            total_entities = page.get("total", 0)
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE glossary_translation_jobs SET total_entities=$2 WHERE job_id=$1",
                    job_id, total_entities,
                )

        items = page.get("items") or []
        if not items:
            break

        if overwrite_mode == "missing_only":
            items = [e for e in items if e["entity_id"] not in processed_entity_ids]
            if not items:
                break

        # Mark the whole page processed up-front (resume/missing_only dedup), then fan the
        # entities out concurrently (bounded by the Semaphore inside _process_entity).
        for ent in items:
            processed_entity_ids.add(ent["entity_id"])
        await asyncio.gather(*[_process_entity(ent) for ent in items])

        # Persist the page's accumulated progress in ONE write — a per-entity DB write would
        # hold up to `concurrency` of the shared max_size=10 pool's connections at once and
        # could starve the rest of the service (review MED). Counters were updated live in
        # each coroutine; this snapshots them. The finalize write below is authoritative.
        async with pool.acquire() as db:
            await db.execute(
                """UPDATE glossary_translation_jobs
                   SET completed_entities=$2, failed_entities=$3,
                       attrs_translated=$4, attrs_skipped=$5,
                       total_input_tokens=$6, total_output_tokens=$7
                   WHERE job_id=$1""",
                job_id, completed, failed, attrs_translated, attrs_skipped,
                total_in, total_out,
            )

        # bug #37 / unified live progress — advance the Jobs GUI per page (this worker
        # otherwise emits only the initial 'running' + the terminal, so its detail page sat
        # frozen). progress = entities done; params.llm_calls_done = realized calls (paired
        # with the create event's estimated_llm_calls). Best-effort (emit_job_event_safe).
        await emit_job_event_safe(
            pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
            kind=_JOB_KIND, status="running",
            progress={"done": completed + failed, "total": total_entities},
            detail_status=f"{completed + failed}/{total_entities} entities",
            params={"llm_calls_done": llm_calls_made},
            tokens_in=total_in or None, tokens_out=total_out or None,
        )

        if overwrite_mode == "missing_only":
            # Candidate set shrinks as translations are written — always page from 0.
            continue
        offset += len(items)
        if offset >= page.get("total", 0):
            break

    final_status = "completed" if failed == 0 else "completed_with_errors"
    async with pool.acquire() as db:
        await db.execute(
            """UPDATE glossary_translation_jobs
               SET status=$2, finished_at=now(),
                   completed_entities=$3, failed_entities=$4,
                   attrs_translated=$5, attrs_skipped=$6,
                   total_input_tokens=$7, total_output_tokens=$8
               WHERE job_id=$1""",
            job_id, final_status, completed, failed,
            attrs_translated, attrs_skipped, total_in, total_out,
        )

    # Terminal emit — both natives map to the canonical 'completed' (completed_with_errors
    # is still a finished run); carry the summed tokens. The projection rejects a 2nd terminal.
    await emit_job_event_safe(
        pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
        kind=_JOB_KIND, status="completed",
        params={"llm_calls_done": llm_calls_made},  # bug #37 — final realized call count
        tokens_in=total_in or None, tokens_out=total_out or None,
    )
    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "translate_glossary",
        "payload": {"status": final_status},
    })
