import json
import logging
from uuid import UUID

import httpx

from ..auth import mint_user_jwt
from ..config import settings
from .session_translator import translate_chapter

log = logging.getLogger(__name__)

# Default context window used when provider-registry cannot supply one
_FALLBACK_CONTEXT_WINDOW = 8192


async def handle_chapter_message(msg: dict, pool, publish_event, retry_count: int = 0) -> None:
    """
    Heavy worker: processes exactly one chapter via session-based chunked translation.
    - Splits chapter into chunks (≤ 1/4 of model context window)
    - Maintains rolling conversation history across chunks for style consistency
    - Compacts history with the configured compact model when it grows too large
    - Updates DB atomically after all chunks complete
    - Checks if job is complete after each chapter
    """
    job_id     = UUID(msg["job_id"])
    chapter_id = UUID(msg["chapter_id"])
    user_id    = msg["user_id"]

    try:
        await _process_chapter(msg, job_id, chapter_id, user_id, pool, publish_event)
    except _TransientError as exc:
        log.warning("chapter %s: transient error — %s", chapter_id, exc)
        await _fail_chapter_idempotent(pool, job_id, chapter_id, f"transient: {exc}")
        await _emit_chapter_done(publish_event, user_id, msg, "failed", f"transient: {exc}")
        await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        raise
    except Exception as exc:
        log.exception("chapter %s: unhandled error — %s", chapter_id, exc)
        await _fail_chapter_idempotent(pool, job_id, chapter_id, f"permanent: {exc}")
        await _emit_chapter_done(publish_event, user_id, msg, "failed", f"permanent: {exc}")
        await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        raise


async def _process_chapter(msg, job_id, chapter_id, user_id, pool, publish_event) -> None:
    log.info("chapter %s [job %s]: starting", chapter_id, job_id)

    # Check for cancellation before doing any work
    async with pool.acquire() as db:
        job_status = await db.fetchval(
            "SELECT status FROM translation_jobs WHERE job_id=$1", job_id
        )
    log.info("chapter %s: job_status=%s", chapter_id, job_status)
    if job_status == "cancelled":
        log.info("chapter %s: job cancelled — skipping", chapter_id)
        await _fail_chapter_idempotent(pool, job_id, chapter_id, "job_cancelled")
        await _emit_chapter_done(publish_event, user_id, msg, "failed", "job_cancelled")
        await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        return

    # Mark chapter running and get its id for chunk rows
    async with pool.acquire() as db:
        ct_row = await db.fetchrow(
            """UPDATE chapter_translations
               SET status='running', started_at=now()
               WHERE job_id=$1 AND chapter_id=$2
               RETURNING id""",
            job_id, chapter_id,
        )
    chapter_translation_id = ct_row["id"] if ct_row else None
    log.info("chapter %s: marked running, chapter_translation_id=%s", chapter_id, chapter_translation_id)

    # Fetch chapter body from book-service
    log.info("chapter %s: fetching body from book-service (book %s)", chapter_id, msg["book_id"])
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=5.0)) as client:
            r = await client.get(
                f"{settings.book_service_internal_url}"
                f"/internal/books/{msg['book_id']}/chapters/{chapter_id}"
            )
    except httpx.RequestError as exc:
        log.error("chapter %s: book-service request failed: %s", chapter_id, exc)
        raise _TransientError(f"book-service unreachable: {exc}") from exc

    log.info("chapter %s: book-service responded status=%d", chapter_id, r.status_code)
    if r.status_code == 404:
        raise _PermanentError("chapter_not_found")
    if r.status_code >= 500:
        raise _TransientError(f"book-service {r.status_code}")
    r.raise_for_status()

    chapter      = r.json()
    source_lang  = chapter.get("original_language") or "unknown"
    chapter_text = chapter.get("text_content") or ""
    chapter_body = chapter.get("body")  # Tiptap JSONB (dict with "content" key) or None
    log.info(
        "chapter %s: fetched %d chars, source_lang=%s, has_json_body=%s",
        chapter_id, len(chapter_text), source_lang, bool(chapter_body and isinstance(chapter_body, dict)),
    )

    # Fetch model context window from provider-registry (best-effort)
    context_window = await _get_model_context_window(msg)
    log.info("chapter %s: context_window=%d", chapter_id, context_window)

    # Detect JSON body → use block pipeline, otherwise fall back to text pipeline
    use_block_pipeline = (
        isinstance(chapter_body, dict)
        and isinstance(chapter_body.get("content"), list)
        and len(chapter_body["content"]) > 0
    )

    if use_block_pipeline:
        from .session_translator import translate_chapter_blocks
        blocks = chapter_body["content"]
        log.info(
            "chapter %s: using BLOCK pipeline (%d blocks, model=%s/%s)",
            chapter_id, len(blocks), msg.get("model_source"), msg.get("model_ref"),
        )
        translated_blocks, input_tokens, output_tokens = await translate_chapter_blocks(
            blocks=blocks,
            source_lang=source_lang,
            msg=msg,
            pool=pool,
            chapter_translation_id=chapter_translation_id,
            context_window=context_window,
        )
        # Store as JSONB
        translated_body_json = json.dumps(translated_blocks)
        translated_body_text = None  # not used for block translations
        translated_body_format = "json"
        log.info(
            "chapter %s: block pipeline done — %d blocks, in=%s out=%s",
            chapter_id, len(translated_blocks), input_tokens, output_tokens,
        )
    else:
        log.info(
            "chapter %s: using TEXT pipeline (model=%s/%s)",
            chapter_id, msg.get("model_source"), msg.get("model_ref"),
        )
        translated_body_text, input_tokens, output_tokens = await translate_chapter(
            chapter_text=chapter_text,
            source_lang=source_lang,
            msg=msg,
            pool=pool,
            chapter_translation_id=chapter_translation_id,
            context_window=context_window,
        )
        translated_body_json = None
        translated_body_format = "text"
        log.info(
            "chapter %s: text pipeline done — %d output chars, in=%s out=%s",
            chapter_id, len(translated_body_text or ""), input_tokens, output_tokens,
        )

    # Persist final result — all writes in one transaction for outbox atomicity
    log.info("chapter %s: persisting completed result to DB", chapter_id)
    async with pool.acquire() as db:
        async with db.transaction():
            await db.execute(
                """UPDATE chapter_translations SET
                     status='completed',
                     translated_body=$1,
                     translated_body_json=$2::jsonb,
                     translated_body_format=$3,
                     source_language=$4,
                     input_tokens=$5,
                     output_tokens=$6,
                     finished_at=now()
                   WHERE job_id=$7 AND chapter_id=$8""",
                translated_body_text, translated_body_json, translated_body_format,
                source_lang,
                input_tokens or None, output_tokens or None,
                job_id, chapter_id,
            )
            log.info("chapter %s: chapter_translations updated, incrementing job counter", chapter_id)
            await db.execute(
                "UPDATE translation_jobs SET completed_chapters=completed_chapters+1 WHERE job_id=$1",
                job_id,
            )
            # Auto-set active: insert only if no active version exists yet for (chapter_id, target_language)
            await db.execute(
                """
                INSERT INTO active_chapter_translation_versions
                  (chapter_id, target_language, chapter_translation_id, set_by_user_id)
                SELECT $1, ct.target_language, $2, ct.owner_user_id
                FROM chapter_translations ct
                WHERE ct.id = $2
                ON CONFLICT (chapter_id, target_language) DO NOTHING
                """,
                chapter_id, chapter_translation_id,
            )
            # Emit outbox event for statistics-service
            await _insert_outbox_event(db, "chapter.translated", chapter_id, {
                "user_id": str(msg["user_id"]),
                "book_id": str(msg["book_id"]),
                "chapter_id": str(chapter_id),
                "target_language": msg["target_language"],
                "status": "completed",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            })
    log.info("chapter %s: DB persist complete", chapter_id)

    await _emit_chapter_done(publish_event, user_id, msg, "completed", None)
    log.info("chapter %s: chapter_done event emitted", chapter_id)
    await _check_job_completion(pool, job_id, user_id, msg, publish_event)


async def _get_model_context_window(msg: dict) -> int:
    """
    Query provider-registry-service for the model's context window.
    Returns _FALLBACK_CONTEXT_WINDOW if the endpoint is unavailable or the
    model doesn't publish a context length (common for local Ollama/LM Studio models).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.provider_registry_service_url}"
                f"/v1/model-registry/models/{msg['model_ref']}/context-window",
                params={"model_source": msg["model_source"]},
            )
            if r.status_code == 200:
                cw = int(r.json().get("context_window") or _FALLBACK_CONTEXT_WINDOW)
                log.debug("context_window for model %s: %d", msg["model_ref"], cw)
                return cw
            log.debug(
                "context_window endpoint returned %d for model %s — using fallback",
                r.status_code, msg["model_ref"],
            )
    except Exception as exc:
        log.debug("context_window fetch failed (%s) — using fallback %d", exc, _FALLBACK_CONTEXT_WINDOW)
    return _FALLBACK_CONTEXT_WINDOW


async def _check_job_completion(pool, job_id, user_id, msg, publish_event) -> None:
    """
    After each chapter terminal state, atomically check + finalize the job.
    Uses a single UPDATE ... WHERE ... RETURNING to avoid TOCTOU race.
    Only the worker that wins the UPDATE emits the final event.
    """
    async with pool.acquire() as db:
        row = await db.fetchrow(
            """UPDATE translation_jobs SET
                 status = CASE
                   WHEN failed_chapters = 0                  THEN 'completed'
                   WHEN completed_chapters > 0               THEN 'partial'
                   ELSE 'failed'
                 END,
                 finished_at = now()
               WHERE job_id = $1
                 AND status = 'running'
                 AND (completed_chapters + failed_chapters) = total_chapters
               RETURNING status, completed_chapters, failed_chapters""",
            job_id,
        )

    if row is None:
        return  # Job not done yet, or another worker already finalized it

    await publish_event(user_id, {
        "event":    "job.status_changed",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {
            "status":             row["status"],
            "completed_chapters": row["completed_chapters"],
            "failed_chapters":    row["failed_chapters"],
        },
    })

    # Fire-and-forget notification
    await _send_translation_notification(
        user_id, msg.get("job_id", ""), msg.get("book_title", ""),
        row["status"], row["completed_chapters"], row["failed_chapters"],
    )


async def _fail_chapter_idempotent(pool, job_id, chapter_id, reason: str) -> None:
    """
    Mark chapter as failed and increment failed_chapters.
    Guarded by AND status != 'failed' so double-calls don't double-count.
    """
    async with pool.acquire() as db:
        updated = await db.fetchval(
            """UPDATE chapter_translations
               SET status='failed', error_message=$1, finished_at=now()
               WHERE job_id=$2 AND chapter_id=$3 AND status != 'failed'
               RETURNING chapter_id""",
            reason, job_id, chapter_id,
        )
        if updated is not None:
            await db.execute(
                "UPDATE translation_jobs SET failed_chapters=failed_chapters+1 WHERE job_id=$1",
                job_id,
            )


async def _emit_chapter_done(publish_event, user_id, msg, status, error_message) -> None:
    await publish_event(user_id, {
        "event":    "job.chapter_done",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {
            "chapter_id":     msg["chapter_id"],
            "chapter_index":  msg["chapter_index"],
            "total_chapters": msg["total_chapters"],
            "status":         status,
            "error_message":  error_message,
        },
    })


async def _insert_outbox_event(db, event_type: str, aggregate_id, payload: dict) -> None:
    """Insert a transactional outbox event for worker-infra relay to Redis Streams."""
    await db.execute(
        """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
           VALUES ($1, 'chapter', $2, $3::jsonb)""",
        event_type, aggregate_id, json.dumps(payload),
    )


async def _send_translation_notification(
    user_id, job_id: str, book_title: str, status: str,
    completed_chapters: int, failed_chapters: int,
) -> None:
    """Fire-and-forget notification to notification-service."""
    try:
        if status == "completed":
            title = f"Translation complete — {completed_chapters} chapters of \"{book_title}\""
            category = "translation"
        elif status == "partial":
            title = f"Translation partial — {completed_chapters} done, {failed_chapters} failed"
            category = "translation"
        else:
            title = f"Translation failed — \"{book_title}\""
            category = "translation"

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.notification_service_internal_url}/internal/notifications",
                json={
                    "user_id": str(user_id),
                    "category": category,
                    "title": title,
                    "metadata": {
                        "job_id": str(job_id),
                        "status": status,
                        "type": f"translation_{status}",
                    },
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
    except Exception as exc:
        log.warning("Failed to send translation notification: %s", exc)


class _TransientError(Exception):
    """Network blip, service unavailable — safe to retry."""


class _PermanentError(Exception):
    """Bad data, 404, 402, unrecoverable — retry won't help."""
