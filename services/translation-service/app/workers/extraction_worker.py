"""
GEP-BE-09: Extraction worker.

Processes one chapter at a time — fetches chapter text from book-service,
builds prompts from extraction profile, calls LLM, parses output,
posts entities to glossary-service.

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §6.6, §7
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import httpx

from ..config import settings
from .content_extractor import extract_content
from .extraction_preprocessor import prepare_chapter_text
from .extraction_prompt import (
    build_extraction_prompt,
    build_known_entities_context,
    build_system_prompt,
    build_user_prompt,
    parse_and_validate,
    plan_kind_batches,
)
from .glossary_client import (
    fetch_known_entities,
    post_extracted_entities,
)

log = logging.getLogger(__name__)


async def handle_extraction_job(msg: dict, pool, publish, publish_event) -> None:
    """Coordinator: receives extraction job, marks running, processes chapters sequentially.

    Unlike translation jobs which fan out chapters in parallel,
    extraction processes chapters sequentially to accumulate known entities.
    """
    job_id = UUID(msg["job_id"])
    user_id = msg["user_id"]
    try:
        await _run_extraction_job(msg, job_id, user_id, pool, publish, publish_event)
    except Exception as exc:
        log.exception("extraction_worker: job %s failed unexpectedly: %s", job_id, exc)
        async with pool.acquire() as db:
            await db.execute(
                "UPDATE extraction_jobs SET status='failed', error_message=$2, finished_at=now() WHERE job_id=$1",
                job_id, str(exc)[:500],
            )
        await publish_event(user_id, {
            "event": "job.status_changed",
            "job_id": str(job_id),
            "job_type": "extract_glossary",
            "payload": {"status": "failed", "error": str(exc)[:200]},
        })


async def _run_extraction_job(msg: dict, job_id: UUID, user_id: str, pool, publish, publish_event) -> None:
    """Inner extraction job runner — separated for top-level error handling."""
    book_id = msg["book_id"]
    chapter_ids = msg["chapter_ids"]
    extraction_profile = msg.get("extraction_profile", {})
    kinds_metadata = msg.get("kinds_metadata", [])
    context_filters = msg.get("context_filters", {})
    source_language = msg.get("source_language", "zh")
    model_source = msg.get("model_source", "platform_model")
    model_ref = msg.get("model_ref")
    max_entities_per_kind = msg.get("max_entities_per_kind", 30)

    log.info("extraction_worker: job %s — %d chapters", job_id, len(chapter_ids))

    async with pool.acquire() as db:
        await db.execute(
            "UPDATE extraction_jobs SET status='running', started_at=now() WHERE job_id=$1",
            job_id,
        )

    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "extract_glossary",
        "payload": {"status": "running", "completed_chapters": 0},
    })

    # Fetch initial known entities (smart-filtered)
    known_entities = await fetch_known_entities(
        book_id,
        alive=context_filters.get("alive", True),
        min_frequency=context_filters.get("min_frequency", 2),
        recency_window=context_filters.get("recency_window", 100),
        limit=context_filters.get("limit", 50),
    )

    total_created = 0
    total_updated = 0
    total_skipped = 0
    total_input_tokens = 0
    total_output_tokens = 0
    completed = 0
    failed = 0

    for idx, chapter_id_str in enumerate(chapter_ids):
        chapter_id = UUID(chapter_id_str) if isinstance(chapter_id_str, str) else chapter_id_str

        # Cooperative cancellation check
        async with pool.acquire() as db:
            job_status = await db.fetchval(
                "SELECT status FROM extraction_jobs WHERE job_id=$1", job_id
            )
        if job_status in ("cancelled", "cancelling"):
            log.info("extraction_worker: job %s cancelled — stopping at chapter %d/%d", job_id, idx, len(chapter_ids))
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE extraction_jobs SET status='cancelled', finished_at=now() WHERE job_id=$1",
                    job_id,
                )
            await publish_event(user_id, {
                "event": "job.status_changed",
                "job_id": str(job_id),
                "job_type": "extract_glossary",
                "payload": {"status": "cancelled"},
            })
            return

        # Mark chapter as running
        async with pool.acquire() as db:
            await db.execute(
                "UPDATE extraction_chapter_results SET status='running', started_at=now() WHERE job_id=$1 AND chapter_id=$2",
                job_id, chapter_id,
            )

        try:
            result = await _process_extraction_chapter(
                job_id=job_id,
                book_id=book_id,
                chapter_id=chapter_id,
                chapter_index=idx,
                extraction_profile=extraction_profile,
                kinds_metadata=kinds_metadata,
                known_entities=known_entities,
                source_language=source_language,
                model_source=model_source,
                model_ref=model_ref,
                max_entities_per_kind=max_entities_per_kind,
                pool=pool,
            )
            # Update known entities with newly created entities (capped at 200 to prevent
            # unbounded prompt growth — design §7 says ~50 entities ≈ 250 tokens)
            _KNOWN_ENTITIES_CAP = 200
            for ent in result.get("entities", []):
                if ent.get("status") == "created" and len(known_entities) < _KNOWN_ENTITIES_CAP:
                    known_entities.append({
                        "name": ent["name"],
                        "kind_code": ent["kind_code"],
                        "aliases": [],
                        "frequency": 1,
                    })

            ch_created = result.get("created", 0)
            ch_updated = result.get("updated", 0)
            ch_skipped = result.get("skipped", 0)
            ch_input_tokens = result.get("input_tokens", 0)
            ch_output_tokens = result.get("output_tokens", 0)

            total_created += ch_created
            total_updated += ch_updated
            total_skipped += ch_skipped
            total_input_tokens += ch_input_tokens
            total_output_tokens += ch_output_tokens
            completed += 1

            async with pool.acquire() as db:
                await db.execute(
                    """UPDATE extraction_chapter_results
                       SET status='completed', entities_found=$3,
                           input_tokens=$4, output_tokens=$5, completed_at=now()
                       WHERE job_id=$1 AND chapter_id=$2""",
                    job_id, chapter_id, ch_created + ch_updated,
                    ch_input_tokens, ch_output_tokens,
                )

        except Exception as exc:
            log.exception("extraction_worker: chapter %s failed: %s", chapter_id, exc)
            failed += 1
            async with pool.acquire() as db:
                await db.execute(
                    """UPDATE extraction_chapter_results
                       SET status='failed', error_message=$3, completed_at=now()
                       WHERE job_id=$1 AND chapter_id=$2""",
                    job_id, chapter_id, str(exc)[:500],
                )

        # Update job progress
        async with pool.acquire() as db:
            await db.execute(
                """UPDATE extraction_jobs
                   SET completed_chapters=$2, failed_chapters=$3,
                       entities_created=$4, entities_updated=$5, entities_skipped=$6,
                       total_input_tokens=$7, total_output_tokens=$8
                   WHERE job_id=$1""",
                job_id, completed, failed,
                total_created, total_updated, total_skipped,
                total_input_tokens, total_output_tokens,
            )

        await publish_event(user_id, {
            "event": "job.progress",
            "job_id": str(job_id),
            "job_type": "extract_glossary",
            "payload": {
                "completed_chapters": completed,
                "failed_chapters": failed,
                "total_chapters": len(chapter_ids),
                "entities_created": total_created,
                "entities_updated": total_updated,
                "entities_skipped": total_skipped,
            },
        })

    # Job complete
    final_status = "completed" if failed == 0 else ("failed" if completed == 0 else "completed_with_errors")
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE extraction_jobs SET status=$2, finished_at=now() WHERE job_id=$1",
            job_id, final_status,
        )

    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "extract_glossary",
        "payload": {
            "status": final_status,
            "entities_created": total_created,
            "entities_updated": total_updated,
            "entities_skipped": total_skipped,
        },
    })

    log.info(
        "extraction_worker: job %s complete — created=%d updated=%d skipped=%d failed_chapters=%d",
        job_id, total_created, total_updated, total_skipped, failed,
    )


async def _process_extraction_chapter(
    job_id: UUID,
    book_id: str,
    chapter_id: UUID,
    chapter_index: int,
    extraction_profile: dict,
    kinds_metadata: list,
    known_entities: list,
    source_language: str,
    model_source: str,
    model_ref: str | None,
    max_entities_per_kind: int,
    pool,
) -> dict:
    """Extract entities from a single chapter via LLM."""
    import time as _time
    _ch_start = _time.monotonic()

    # 1. Fetch chapter from book-service
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=5)) as client:
        r = await client.get(
            f"{settings.book_service_internal_url}"
            f"/internal/books/{book_id}/chapters/{chapter_id}",
            headers={"X-Internal-Token": settings.internal_service_token},
        )
    if r.status_code != 200:
        raise RuntimeError(f"book-service returned {r.status_code} for chapter {chapter_id}")

    chapter = r.json()
    chapter_text = prepare_chapter_text(chapter)
    if not chapter_text.strip():
        log.warning("extraction: chapter %s has no text content — skipping", chapter_id)
        return {"created": 0, "updated": 0, "skipped": 0, "entities": [], "input_tokens": 0, "output_tokens": 0}

    # 2. Plan batches
    batches = plan_kind_batches(extraction_profile, kinds_metadata)
    log.info("extraction: chapter %s (index %d) — %d batch(es), text_len=%d",
             chapter_id, chapter_index, len(batches), len(chapter_text))

    # 3. Build known entities context
    known_ctx = build_known_entities_context(known_entities) if known_entities else ""

    # Resolve owner user_id once for internal invoke auth
    async with pool.acquire() as db:
        owner_user_id = await db.fetchval(
            "SELECT owner_user_id FROM extraction_jobs WHERE job_id=$1", job_id
        )

    all_entities: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for batch_idx, batch in enumerate(batches):
        # 4. Build prompt
        schema = build_extraction_prompt(batch, extraction_profile, kinds_metadata)
        system_prompt = build_system_prompt(
            dynamic_schema=schema,
            source_language=source_language,
            known_entities_context=known_ctx,
            max_entities_per_kind=max_entities_per_kind,
        )
        user_prompt = build_user_prompt(chapter_text)

        # 5. LLM call via provider-registry
        invoke_payload = {
            "model_source": model_source,
            "model_ref": model_ref,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 12000,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=300, write=10, pool=5)) as client:
            resp = await client.post(
                f"{settings.provider_registry_service_url}/internal/invoke",
                params={"user_id": str(owner_user_id)},
                json=invoke_payload,
                headers={"X-Internal-Token": settings.internal_service_token},
            )

        if resp.status_code != 200:
            log.error(
                "extraction: LLM invoke failed status=%d for chapter %s batch %d/%d — skipping batch (kinds: %s)",
                resp.status_code, chapter_id, batch_idx + 1, len(batches), batch,
            )
            continue

        resp_data = resp.json()
        raw_output = resp_data.get("output", {})
        response_text = extract_content(raw_output)
        input_tokens = resp_data.get("usage", {}).get("input_tokens", 0)
        output_tokens = resp_data.get("usage", {}).get("output_tokens", 0)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        # Log LLM response stats for monitoring model quality / token budget tuning
        choices = raw_output.get("choices", []) if isinstance(raw_output, dict) else []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message", {})
            content_len = len(msg.get("content", "") or "")
            reasoning_len = len(msg.get("reasoning_content", "") or "")
            source = "content" if content_len > 0 else "reasoning"
            log.info("extraction: chapter %s batch %d/%d — in=%d out=%d response=%d chars (source=%s, reasoning=%d chars)",
                     chapter_id, batch_idx + 1, len(batches), input_tokens, output_tokens,
                     len(response_text), source, reasoning_len)

        # 6. Parse + validate
        entities = parse_and_validate(response_text, batch, extraction_profile)

        # Add chapter_links to each entity (use .get() to avoid mutating parsed dict)
        chapter_title = chapter.get("title", "")
        for ent in entities:
            relevance = ent.get("relevance", "appears")
            ent["chapter_links"] = [{
                "chapter_id": str(chapter_id),
                "chapter_title": chapter_title,
                "chapter_index": chapter_index,
                "relevance": relevance,
            }]

        all_entities.extend(entities)

    _ch_elapsed = _time.monotonic() - _ch_start

    if not all_entities:
        log.info("extraction: chapter %s done in %.1fs — 0 entities (empty LLM output)", chapter_id, _ch_elapsed)
        return {"created": 0, "updated": 0, "skipped": 0, "entities": [], "input_tokens": total_input_tokens, "output_tokens": total_output_tokens}

    # 7. Post to glossary-service
    upsert_result = await post_extracted_entities(
        book_id=book_id,
        source_language=source_language,
        attribute_actions=extraction_profile,
        entities=all_entities,
    )

    if upsert_result is None:
        raise RuntimeError("glossary-service upsert failed")

    log.info("extraction: chapter %s done in %.1fs — created=%d updated=%d skipped=%d (in=%d out=%d)",
             chapter_id, _ch_elapsed,
             upsert_result.get("created", 0), upsert_result.get("updated", 0), upsert_result.get("skipped", 0),
             total_input_tokens, total_output_tokens)

    upsert_result["input_tokens"] = total_input_tokens
    upsert_result["output_tokens"] = total_output_tokens
    return upsert_result
