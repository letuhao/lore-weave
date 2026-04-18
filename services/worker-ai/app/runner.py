"""K16.6b — Extraction job runner.

Core loop:
  1. Poll for running jobs (status='running')
  2. For each job, enumerate items by scope
  3. For each item: try_spend → extract → advance_cursor
  4. Detect pause/cancel between items
  5. On all items done → complete the job

DB queries are inline (not via shared repo classes) because worker-ai
is a separate service. The queries mirror ExtractionJobsRepo and
ExtractionPendingRepo from knowledge-service but only include the
subset the worker needs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.clients import BookClient, ChapterInfo, KnowledgeClient

__all__ = ["process_job", "poll_and_run"]

logger = logging.getLogger(__name__)

# Default token cost estimate per item for try_spend. The real cost
# is reconciled after the LLM call via the extraction result, but
# try_spend needs an upfront estimate to enforce the budget cap.
_DEFAULT_COST_PER_ITEM = Decimal("0.004")  # ~2000 tokens × $2/M

# Max retries per item before skipping. Prevents infinite retry loops
# when a specific item consistently triggers a retryable LLM error.
_MAX_RETRIES_PER_ITEM = 3


# ── Data types ───────────────────────────────────────────────────────


@dataclass
class JobRow:
    job_id: UUID
    user_id: UUID
    project_id: UUID
    scope: str
    scope_range: dict | None
    status: str
    llm_model: str
    embedding_model: str
    max_spend_usd: Decimal | None
    items_total: int | None
    items_processed: int
    current_cursor: dict | None
    cost_spent_usd: Decimal


# ── DB helpers ───────────────────────────────────────────────────────


async def _get_running_jobs(pool: asyncpg.Pool) -> list[JobRow]:
    """Fetch all jobs in 'running' status."""
    rows = await pool.fetch(
        """
        SELECT job_id, user_id, project_id, scope, scope_range,
               status, llm_model, embedding_model, max_spend_usd,
               items_total, items_processed, current_cursor, cost_spent_usd
        FROM extraction_jobs
        WHERE status = 'running'
        ORDER BY created_at ASC
        """
    )
    result = []
    for r in rows:
        sr = r["scope_range"]
        if isinstance(sr, str):
            sr = json.loads(sr)
        cc = r["current_cursor"]
        if isinstance(cc, str):
            cc = json.loads(cc)
        result.append(JobRow(
            job_id=r["job_id"],
            user_id=r["user_id"],
            project_id=r["project_id"],
            scope=r["scope"],
            scope_range=sr,
            status=r["status"],
            llm_model=r["llm_model"],
            embedding_model=r["embedding_model"],
            max_spend_usd=r["max_spend_usd"],
            items_total=r["items_total"],
            items_processed=r["items_processed"],
            current_cursor=cc,
            cost_spent_usd=r["cost_spent_usd"],
        ))
    return result


async def _refresh_job_status(pool: asyncpg.Pool, job_id: UUID) -> str | None:
    """Re-read job status from DB. Returns None if job not found."""
    row = await pool.fetchval(
        "SELECT status FROM extraction_jobs WHERE job_id = $1",
        job_id,
    )
    return row


async def _try_spend(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, cost: Decimal,
) -> str:
    """Atomic cost reservation. Returns 'reserved', 'auto_paused', or 'not_running'.

    Mirror of ExtractionJobsRepo.try_spend — see that class for the
    full safety rationale.
    """
    row = await pool.fetchrow(
        """
        UPDATE extraction_jobs
        SET
          cost_spent_usd = cost_spent_usd + $3,
          status = CASE
            WHEN max_spend_usd IS NOT NULL
                 AND cost_spent_usd + $3 >= max_spend_usd
              THEN 'paused'
            ELSE status
          END,
          paused_at = CASE
            WHEN max_spend_usd IS NOT NULL
                 AND cost_spent_usd + $3 >= max_spend_usd
              THEN now()
            ELSE paused_at
          END,
          updated_at = now()
        WHERE user_id = $1 AND job_id = $2 AND status = 'running'
        RETURNING cost_spent_usd, status
        """,
        user_id, job_id, cost,
    )
    if row is None:
        return "not_running"
    return "auto_paused" if row["status"] == "paused" else "reserved"


async def _advance_cursor(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID,
    cursor: dict, items_delta: int = 1,
) -> None:
    """Persist progress so a restart can resume from here."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET current_cursor = $3::jsonb,
            items_processed = items_processed + $4,
            updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status IN ('running', 'paused')
        """,
        user_id, job_id, json.dumps(cursor), items_delta,
    )


async def _complete_job(pool: asyncpg.Pool, user_id: UUID, job_id: UUID) -> None:
    """Transition job to 'complete'."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET status = 'complete', completed_at = now(), updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        """,
        user_id, job_id,
    )


async def _fail_job(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, error: str,
) -> None:
    """Transition job to 'failed' with an error message."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET status = 'failed', completed_at = now(), updated_at = now(),
            error_message = $3
        WHERE user_id = $1 AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        """,
        user_id, job_id, error[:2000],
    )


async def _get_project_book_id(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
) -> UUID | None:
    """Look up the book_id for a project. Returns None if the project
    has no linked book or doesn't exist."""
    row = await pool.fetchval(
        "SELECT book_id FROM knowledge_projects WHERE user_id = $1 AND project_id = $2",
        user_id, project_id,
    )
    return row


async def _update_project_status(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
    extraction_status: str,
) -> None:
    """Update project extraction_status (advisory — job is source of truth)."""
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET extraction_status = $3, updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, extraction_status,
    )


# ── Item enumeration ─────────────────────────────────────────────────


async def _enumerate_chapters(
    book_client: BookClient, book_id: UUID | None, cursor: dict | None,
) -> list[ChapterInfo]:
    """Get chapters to process, respecting cursor for resume."""
    if book_id is None:
        return []
    chapters = await book_client.list_chapters(book_id)
    if chapters is None:
        return []

    # Resume: skip chapters already processed (cursor has last_chapter_id)
    if cursor and cursor.get("last_chapter_id"):
        last_id = cursor["last_chapter_id"]
        found = False
        filtered = []
        for ch in chapters:
            if found:
                filtered.append(ch)
            if ch.chapter_id == last_id:
                found = True
        if not found:
            # Cursor chapter no longer in list (deleted between runs).
            # Process all chapters from scratch rather than silently
            # completing with zero work.
            logger.warning(
                "Cursor chapter %s not found in chapter list — "
                "restarting from beginning",
                last_id,
            )
            return chapters
        return filtered

    return chapters


async def _enumerate_pending_chat_turns(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
) -> list[dict]:
    """Fetch unprocessed chat turn events from extraction_pending."""
    rows = await pool.fetch(
        """
        SELECT ep.pending_id, ep.event_id, ep.event_type,
               ep.aggregate_type, ep.aggregate_id
        FROM extraction_pending ep
        JOIN knowledge_projects p
          ON p.project_id = ep.project_id AND p.user_id = $1
        WHERE ep.project_id = $2 AND ep.processed_at IS NULL
        ORDER BY ep.created_at ASC
        LIMIT 1000
        """,
        user_id, project_id,
    )
    return [dict(r) for r in rows]


async def _mark_pending_processed(
    pool: asyncpg.Pool, user_id: UUID, pending_id: UUID,
) -> None:
    """Mark a pending event as processed."""
    await pool.execute(
        """
        UPDATE extraction_pending ep
        SET processed_at = now()
        FROM knowledge_projects p
        WHERE ep.pending_id = $2
          AND ep.processed_at IS NULL
          AND p.project_id = ep.project_id
          AND p.user_id = $1
        """,
        user_id, pending_id,
    )


# ── Core job processing ─────────────────────────────────────────────


async def process_job(
    pool: asyncpg.Pool,
    knowledge_client: KnowledgeClient,
    book_client: BookClient,
    job: JobRow,
) -> None:
    """Process all items for a single extraction job.

    Handles:
      - Item enumeration by scope (chapters, chat, all)
      - Per-item: try_spend → extract → advance_cursor
      - Pause/cancel detection between items
      - Job completion / failure
    """
    logger.info(
        "Processing job %s (scope=%s, project=%s, processed=%d/%s)",
        job.job_id, job.scope, job.project_id,
        job.items_processed, job.items_total or "?",
    )

    items_processed = 0
    try:
        # Resolve book_id from project (project_id ≠ book_id)
        book_id = await _get_project_book_id(pool, job.user_id, job.project_id)

        # Enumerate items based on scope
        if job.scope in ("chapters", "all"):
            chapters = await _enumerate_chapters(
                book_client, book_id, job.current_cursor,
            )
            for ch in chapters:
                # Check job status (pause/cancel detection)
                status = await _refresh_job_status(pool, job.job_id)
                if status != "running":
                    logger.info("Job %s no longer running (status=%s), stopping", job.job_id, status)
                    return

                # Atomic cost reservation
                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _DEFAULT_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    logger.info("Job %s try_spend returned not_running, stopping", job.job_id)
                    return
                if outcome == "auto_paused":
                    logger.info("Job %s auto-paused by budget cap", job.job_id)
                    await _update_project_status(pool, job.user_id, job.project_id, "paused")
                    return

                # Get chapter text
                text = await book_client.get_chapter_text(book_id, ch.chapter_id)
                if text is None:
                    logger.warning("Skipping chapter %s — text unavailable", ch.chapter_id)
                    await _advance_cursor(
                        pool, job.user_id, job.job_id,
                        {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                    )
                    continue

                # Extract
                result = await knowledge_client.extract_item(
                    user_id=job.user_id,
                    project_id=job.project_id,
                    item_type="chapter",
                    source_type="chapter",
                    source_id=ch.chapter_id,
                    job_id=job.job_id,
                    model_source="user_model",
                    model_ref=job.llm_model,
                    chapter_text=text,
                )

                if result.error:
                    if not result.retryable:
                        await _fail_job(pool, job.user_id, job.job_id, result.error)
                        await _update_project_status(pool, job.user_id, job.project_id, "failed")
                        return
                    # Track retry count in cursor to prevent infinite loops
                    retry_key = f"retry_{ch.chapter_id}"
                    cur = job.current_cursor or {}
                    retries = cur.get(retry_key, 0) + 1
                    if retries >= _MAX_RETRIES_PER_ITEM:
                        logger.warning(
                            "Skipping chapter %s after %d retries: %s",
                            ch.chapter_id, retries, result.error,
                        )
                        await _advance_cursor(
                            pool, job.user_id, job.job_id,
                            {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                        )
                        items_processed += 1
                        continue
                    logger.warning(
                        "Retryable error on chapter %s (attempt %d/%d): %s",
                        ch.chapter_id, retries, _MAX_RETRIES_PER_ITEM, result.error,
                    )
                    # Persist retry count in cursor, don't advance past this item
                    await _advance_cursor(
                        pool, job.user_id, job.job_id,
                        {**cur, retry_key: retries, "scope": "chapters"},
                        items_delta=0,
                    )
                    return  # stop this run, retry on next poll

                # Advance cursor
                await _advance_cursor(
                    pool, job.user_id, job.job_id,
                    {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                )
                items_processed += 1
                logger.info(
                    "Job %s: chapter %s done (entities=%d, relations=%d)",
                    job.job_id, ch.chapter_id,
                    result.entities_merged, result.relations_created,
                )

        if job.scope in ("chat", "all"):
            pending = await _enumerate_pending_chat_turns(
                pool, job.user_id, job.project_id,
            )
            for turn in pending:
                status = await _refresh_job_status(pool, job.job_id)
                if status != "running":
                    logger.info("Job %s no longer running (status=%s), stopping", job.job_id, status)
                    return

                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _DEFAULT_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    return
                if outcome == "auto_paused":
                    await _update_project_status(pool, job.user_id, job.project_id, "paused")
                    return

                # Chat turns don't have text in extraction_pending — the
                # worker would need to fetch from chat-service. For v1,
                # we call extract-item with source_id and let knowledge-
                # service's orchestrator handle it. This is a placeholder
                # that will be fleshed out when chat-service exposes a
                # message-text endpoint.
                result = await knowledge_client.extract_item(
                    user_id=job.user_id,
                    project_id=job.project_id,
                    item_type="chat_turn",
                    source_type="chat_turn",
                    source_id=str(turn["aggregate_id"]),
                    job_id=job.job_id,
                    model_source="user_model",
                    model_ref=job.llm_model,
                    user_message="",  # placeholder — needs chat-service integration
                )

                if result.error and not result.retryable:
                    await _fail_job(pool, job.user_id, job.job_id, result.error)
                    await _update_project_status(pool, job.user_id, job.project_id, "failed")
                    return

                await _mark_pending_processed(pool, job.user_id, turn["pending_id"])
                await _advance_cursor(
                    pool, job.user_id, job.job_id,
                    {"last_pending_id": str(turn["pending_id"]), "scope": "chat"},
                )
                items_processed += 1

        # TODO: glossary_sync scope — needs glossary-service entity
        # enumeration + knowledge-service sync endpoint. For now, jobs
        # with scope="glossary_sync" skip silently. scope="all" covers
        # chapters + chat but not glossary until this is implemented.

        # All items processed — complete the job
        await _complete_job(pool, job.user_id, job.job_id)
        await _update_project_status(pool, job.user_id, job.project_id, "ready")
        logger.info(
            "Job %s completed: %d items processed this run",
            job.job_id, items_processed,
        )

    except Exception as exc:
        logger.exception("Job %s failed with unhandled error: %s", job.job_id, exc)
        await _fail_job(pool, job.user_id, job.job_id, str(exc)[:2000])
        await _update_project_status(pool, job.user_id, job.project_id, "failed")


# ── Poll loop ────────────────────────────────────────────────────────


async def poll_and_run(
    pool: asyncpg.Pool,
    knowledge_client: KnowledgeClient,
    book_client: BookClient,
) -> int:
    """One poll cycle: find running jobs and process them.

    Returns the number of jobs processed (for logging/metrics).
    Called repeatedly by the main loop with a sleep interval.
    """
    jobs = await _get_running_jobs(pool)
    if not jobs:
        return 0

    for job in jobs:
        await process_job(pool, knowledge_client, book_client, job)

    return len(jobs)
