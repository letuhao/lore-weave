"""Glossary batch attribute translation worker."""
from __future__ import annotations

import json
import logging
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

from ..llm_client import LLMClient
from .glossary_client import fetch_translation_candidates, post_apply_translations
from .glossary_translate_prompt import (
    build_system_prompt,
    build_user_prompt,
    parse_translation_response,
)
from .llm_thinking import thinking_llm_fields

log = logging.getLogger(__name__)

_PAGE_SIZE = 25


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
    thinking_enabled = bool(msg.get("thinking_enabled", metadata.get("thinking_enabled", False)))

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
        if owner_user_id is None:
            await db.execute(
                "UPDATE glossary_translation_jobs SET status='cancelled', finished_at=now() "
                "WHERE job_id=$1 AND status='cancelling'",
                job_id,
            )
    if owner_user_id is None:
        log.info("glossary_translate: job %s not runnable (cancelled/terminal) — acking, no work", job_id)
        await publish_event(user_id, {
            "event": "job.status_changed",
            "job_id": str(job_id),
            "job_type": "translate_glossary",
            "payload": {"status": "cancelled"},
        })
        return

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

        for ent in items:
            entity_id = ent["entity_id"]
            processed_entity_ids.add(entity_id)
            attrs = ent.get("attributes") or []
            if not attrs:
                completed += 1
                continue

            expected_codes = {a["code"] for a in attrs}
            code_to_avid = {a["code"]: a["attr_value_id"] for a in attrs}

            system_prompt = build_system_prompt(source_language, target_language)
            user_prompt = build_user_prompt(
                ent.get("display_name", ""), ent.get("kind_code", ""), attrs,
            )

            try:
                sdk_job = await llm_client.submit_and_wait(
                    user_id=str(owner_user_id),
                    operation="chat",
                    model_source=model_source,
                    model_ref=str(model_ref),
                    input={
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 4096,
                        **thinking_llm_fields(enabled=thinking_enabled),
                    },
                    chunking=None,
                    job_meta={
                        "operation": "glossary_translate",
                        "glossary_translate_job_id": str(job_id),
                        "entity_id": entity_id,
                    },
                    transient_retry_budget=1,
                )
            except (LLMQuotaExceeded, LLMModelNotFound, LLMAuthFailed,
                    LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
                log.error("glossary_translate: permanent error entity %s: %s", entity_id, exc)
                failed += 1
                continue
            except (LLMTransientRetryNeededError, LLMError) as exc:
                log.error("glossary_translate: transient error entity %s: %s", entity_id, exc)
                failed += 1
                continue

            if sdk_job.status != "completed":
                failed += 1
                continue

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
                continue

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
                continue

            attrs_translated += result.get("translated", 0)
            attrs_skipped += result.get("skipped_verified", 0) + result.get("skipped_empty", 0)
            completed += 1

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

    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "translate_glossary",
        "payload": {"status": final_status},
    })
