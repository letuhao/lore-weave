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
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import asyncpg

from app.clients import (
    BookClient,
    ChapterInfo,
    GlossaryClient,
    GlossaryEntity,
    KnowledgeClient,
)

__all__ = ["process_job", "poll_and_run"]

logger = logging.getLogger(__name__)

# Default token cost estimate per item for try_spend. The real cost
# is reconciled after the LLM call via the extraction result, but
# try_spend needs an upfront estimate to enforce the budget cap.
_DEFAULT_COST_PER_ITEM = Decimal("0.004")  # ~2000 tokens × $2/M

# C12c-a: glossary_sync items have no LLM call (pure Neo4j MERGE via
# the K15.11 helper). Cost is 0 but we still run them through
# _try_spend so the pause/cancel-detection flow stays uniform.
_GLOSSARY_SYNC_COST_PER_ITEM = Decimal("0.0")

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


async def _append_log(
    pool: asyncpg.Pool,
    user_id: UUID,
    job_id: UUID,
    level: str,
    message: str,
    context: dict | None = None,
) -> None:
    """K19b.8 — mirror a key lifecycle event to job_logs so the FE's
    JobLogsPanel can render it. Inlined SQL matches the worker's
    existing `_try_spend` / `_record_spending` pattern (worker owns
    the DB write path to the shared knowledge DB; avoids an HTTP
    round-trip per event).

    Vocabulary: level MUST be one of info/warning/error (enforced by
    the table CHECK constraint). Caller passes an optional JSON
    context (e.g. chapter_id, error text) that's serialised inline.
    Fire-and-forget from the caller's point of view — we don't return
    the log_id; callers don't chain on it.
    """
    await pool.execute(
        """
        INSERT INTO job_logs (job_id, user_id, level, message, context)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        """,
        job_id,
        user_id,
        level,
        message,
        json.dumps(context or {}),
    )


async def _record_spending(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID, cost: Decimal,
) -> None:
    """D-K16.11-01 — update the per-project monthly + all-time spend
    counters after a successful extraction item.

    Mirrors ``app.jobs.budget.record_spending`` in knowledge-service;
    kept inline here for the same reason ``_try_spend`` is — the worker
    owns the write path to the same DB and avoids an HTTP round-trip
    per item. Handles month rollover atomically via CASE-on-key: if the
    project's ``current_month_key`` doesn't match the current month,
    the counter resets to this cost before adding.

    Not guarded by an atomic budget check — that's ``_try_spend``'s job
    on ``extraction_jobs.max_spend_usd``. This function is strictly
    accounting + rollover.
    """
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET current_month_spent_usd = CASE
              WHEN current_month_key = $3 THEN current_month_spent_usd + $4
              ELSE $4
            END,
            current_month_key = $3,
            actual_cost_usd = actual_cost_usd + $4,
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, month_key, cost,
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


async def _set_items_total(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, total: int,
) -> None:
    """Set items_total on a job (for progress percentage in UI)."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET items_total = $3, updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        """,
        user_id, job_id, total,
    )


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


async def _enumerate_glossary_entities(
    glossary_client: GlossaryClient,
    book_id: UUID | None,
    cursor: dict | None,
) -> tuple[list[GlossaryEntity], bool]:
    """C12c-a — page through a book's glossary entities.

    Aggregates all pages into a single list (books are user-curated,
    hundreds at most — not millions). On resume, skips entities with
    ``entity_id <= cursor.last_glossary_entity_id`` since the
    glossary-service endpoint orders by UUID ASC (total ordering).

    Returns ``(entities, complete)`` where ``complete`` is ``False``
    when glossary-service returned ``None`` mid-enumeration OR the
    HARD_CAP truncation kicked in. The caller uses ``complete`` to
    decide whether to set items_total — an incomplete enumeration
    would underestimate and freeze the progress bar at the wrong
    total (/review-impl LOW#5).

    Graceful-degrade: on ANY glossary-service failure the partial
    list so far is returned; the next job run re-enumerates from
    scratch (resume_after skips what we already synced).

    Hard cap: 5000 entities per job. Books with more are rare and
    the cap prevents a runaway enumeration from blocking the worker
    if the BE endpoint's `next_cursor` logic regresses.
    """
    if book_id is None:
        return [], True
    resume_after: str | None = None
    if cursor and cursor.get("last_glossary_entity_id"):
        resume_after = str(cursor["last_glossary_entity_id"])

    out: list[GlossaryEntity] = []
    page_cursor: str | None = None
    pages_fetched = 0
    HARD_CAP = 5000
    while True:
        page = await glossary_client.list_book_entities(
            book_id, cursor=page_cursor, limit=100,
        )
        if page is None:
            # Graceful-degrade: stop enumerating. Any entities already
            # collected in this pass are kept (the caller will still
            # process them; a future resume retries the failed page).
            logger.warning(
                "Job glossary enumeration partial for book %s "
                "(glossary-service returned None); %d entities collected "
                "so far will process but items_total will not be set",
                book_id, len(out),
            )
            return out, False
        pages_fetched += 1
        for ent in page.items:
            # Resume filter: skip entities we've already synced in a
            # prior worker run. UUID ordering is total, so string
            # compare against the cursor id works.
            if resume_after and ent.entity_id <= resume_after:
                continue
            out.append(ent)
            if len(out) >= HARD_CAP:
                logger.warning(
                    "Job glossary enumeration hit HARD_CAP=%d for book %s "
                    "— truncating this run's sync",
                    HARD_CAP, book_id,
                )
                return out, False
        if not page.next_cursor:
            return out, True
        page_cursor = page.next_cursor
        # Defensive: protect against a pathological loop if BE returns
        # the same cursor repeatedly.
        if pages_fetched > 200:
            logger.warning(
                "Job glossary enumeration hit 200-page ceiling for book %s",
                book_id,
            )
            return out, False


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
    glossary_client: GlossaryClient,
    job: JobRow,
) -> None:
    """Process all items for a single extraction job.

    Handles:
      - Item enumeration by scope (chapters, chat, glossary_sync, all)
      - Per-item: try_spend → extract → advance_cursor
      - Pause/cancel detection between items
      - Job completion / failure

    C12c-a: scope='glossary_sync' iterates a book's glossary entities
    via glossary-service pagination, calling knowledge-service's
    glossary-sync-entity endpoint per entity. scope='all' runs this
    tail after chapters+chat.
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

        # Pre-enumerate items. Done once — the results are reused for
        # both K16.7 items_total counting and the main processing loop,
        # avoiding a second HTTP call to book-service.
        pre_chapters: list[ChapterInfo] | None = None
        pre_pending: list[dict] | None = None
        pre_glossary: list[GlossaryEntity] | None = None
        glossary_enumeration_complete: bool = True

        if job.scope in ("chapters", "all"):
            pre_chapters = await _enumerate_chapters(
                book_client, book_id, job.current_cursor,
            )
        if job.scope in ("chat", "all"):
            pre_pending = await _enumerate_pending_chat_turns(
                pool, job.user_id, job.project_id,
            )
        # C12c-a: pre-enumerate glossary entities for glossary_sync OR
        # all-scope (if the project has a book). Empty / None book_id
        # → skip silently, matching the book-service enumerator.
        if job.scope in ("glossary_sync", "all") and book_id is not None:
            pre_glossary, glossary_enumeration_complete = (
                await _enumerate_glossary_entities(
                    glossary_client, book_id, job.current_cursor,
                )
            )

        # K16.7: if items_total wasn't set by the caller (backfill case),
        # count items now so the UI can show progress percentage.
        # C12c-a /review-impl LOW#5: skip items_total when the glossary
        # enumeration came back partial (glossary-service flake
        # mid-pagination, or HARD_CAP hit) — using the partial count
        # would freeze the progress bar at a wrong total.
        if job.items_total is None and glossary_enumeration_complete:
            total = (
                len(pre_chapters or [])
                + len(pre_pending or [])
                + len(pre_glossary or [])
            )
            await _set_items_total(pool, job.user_id, job.job_id, total)
            logger.info("Job %s: items_total set to %d (chapters=%d, chat=%d)",
                        job.job_id, total,
                        len(pre_chapters or []), len(pre_pending or []))

        # Process items based on scope
        if pre_chapters:
            for ch in pre_chapters:
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
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        "Job auto-paused: max_spend_usd reached",
                        context={"event": "auto_paused", "scope": "chapters"},
                    )
                    await _update_project_status(pool, job.user_id, job.project_id, "paused")
                    return

                # Get chapter text
                text = await book_client.get_chapter_text(book_id, ch.chapter_id)
                if text is None:
                    logger.warning("Skipping chapter %s — text unavailable", ch.chapter_id)
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        f"Skipped chapter {ch.chapter_id}: text unavailable",
                        context={
                            "event": "chapter_skipped",
                            "chapter_id": str(ch.chapter_id),
                            "reason": "text_unavailable",
                        },
                    )
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
                        await _append_log(
                            pool, job.user_id, job.job_id, "error",
                            f"Job failed on chapter {ch.chapter_id}: {result.error}",
                            context={
                                "event": "failed",
                                "chapter_id": str(ch.chapter_id),
                                "error": result.error,
                            },
                        )
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
                        await _append_log(
                            pool, job.user_id, job.job_id, "error",
                            f"Chapter {ch.chapter_id} skipped after {retries} retries",
                            context={
                                "event": "retry_exhausted",
                                "chapter_id": str(ch.chapter_id),
                                "retries": retries,
                                "error": result.error,
                            },
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
                # D-K16.11-01: bump per-project monthly + all-time spend
                # counters so CostSummary's GET /costs reflects reality.
                await _record_spending(
                    pool, job.user_id, job.project_id, _DEFAULT_COST_PER_ITEM,
                )
                # K19b.8: surface this success to the FE log panel.
                await _append_log(
                    pool, job.user_id, job.job_id, "info",
                    f"Chapter {ch.chapter_id} processed",
                    context={
                        "event": "chapter_processed",
                        "chapter_id": str(ch.chapter_id),
                        "entities_merged": result.entities_merged,
                        "relations_created": result.relations_created,
                    },
                )
                items_processed += 1
                logger.info(
                    "Job %s: chapter %s done (entities=%d, relations=%d)",
                    job.job_id, ch.chapter_id,
                    result.entities_merged, result.relations_created,
                )

        if pre_pending:
            for turn in pre_pending:
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
                # D-K16.11-01: same per-project accounting as the chapters
                # branch, see above.
                await _record_spending(
                    pool, job.user_id, job.project_id, _DEFAULT_COST_PER_ITEM,
                )
                items_processed += 1

        # C12c-a: glossary_sync branch. Fires for scope='glossary_sync'
        # (primary) AND the tail of scope='all'. No LLM call — each
        # entity is MERGEd into Neo4j via knowledge-service's
        # /internal/extraction/glossary-sync-entity handler (which
        # wraps the K15.11 `sync_glossary_entity_to_neo4j` helper).
        # Cost per item = 0 (see _GLOSSARY_SYNC_COST_PER_ITEM) but we
        # still run through _try_spend so pause/cancel detection stays
        # uniform across branches.
        if pre_glossary:
            for ent in pre_glossary:
                status = await _refresh_job_status(pool, job.job_id)
                if status != "running":
                    logger.info(
                        "Job %s no longer running (status=%s), stopping glossary loop",
                        job.job_id, status,
                    )
                    return

                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _GLOSSARY_SYNC_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    return
                if outcome == "auto_paused":
                    # Shouldn't fire for glossary (cost=0 never crosses
                    # max_spend) but log + return defensively so the
                    # branching story stays uniform with chapters/chat.
                    logger.info("Job %s auto-paused during glossary loop", job.job_id)
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        "Job auto-paused: max_spend_usd reached",
                        context={"event": "auto_paused", "scope": "glossary_sync"},
                    )
                    return

                result = await knowledge_client.glossary_sync_entity(
                    user_id=job.user_id,
                    project_id=job.project_id,
                    glossary_entity_id=ent.entity_id,
                    name=ent.name,
                    kind=ent.kind_code,
                    aliases=ent.aliases,
                    short_description=ent.short_description,
                )

                if result.error and not result.retryable:
                    await _fail_job(pool, job.user_id, job.job_id, result.error)
                    await _update_project_status(
                        pool, job.user_id, job.project_id, "failed",
                    )
                    return
                # /review-impl MED#3 — bounded retry mirroring the
                # chapters branch. Track retry count per entity in
                # the cursor; on retry_key >= _MAX_RETRIES_PER_ITEM
                # skip the entity (advance cursor past it) so a
                # flapping glossary-service can't loop indefinitely.
                if result.error and result.retryable:
                    retry_key = f"retry_glossary_{ent.entity_id}"
                    cur = job.current_cursor or {}
                    retries = cur.get(retry_key, 0) + 1
                    if retries >= _MAX_RETRIES_PER_ITEM:
                        logger.warning(
                            "Skipping glossary entity %s after %d retries: %s",
                            ent.entity_id, retries, result.error,
                        )
                        await _append_log(
                            pool, job.user_id, job.job_id, "error",
                            f"Glossary entity {ent.entity_id} skipped after {retries} retries",
                            context={
                                "event": "retry_exhausted",
                                "glossary_entity_id": ent.entity_id,
                                "retries": retries,
                                "error": result.error,
                                "scope": "glossary_sync",
                            },
                        )
                        await _advance_cursor(
                            pool, job.user_id, job.job_id,
                            {
                                "last_glossary_entity_id": ent.entity_id,
                                "scope": "glossary_sync",
                            },
                        )
                        items_processed += 1
                        continue
                    logger.warning(
                        "Retryable error on glossary entity %s (attempt %d/%d): %s",
                        ent.entity_id, retries, _MAX_RETRIES_PER_ITEM, result.error,
                    )
                    # Persist retry count; don't advance past this item;
                    # stop this run so next poll retries.
                    await _advance_cursor(
                        pool, job.user_id, job.job_id,
                        {**cur, retry_key: retries, "scope": "glossary_sync"},
                        items_delta=0,
                    )
                    return

                await _advance_cursor(
                    pool, job.user_id, job.job_id,
                    {
                        "last_glossary_entity_id": ent.entity_id,
                        "scope": "glossary_sync",
                    },
                )
                # Record zero spend — keeps the per-project ledger
                # consistent (every item advances it, glossary items
                # advance it by 0).
                await _record_spending(
                    pool, job.user_id, job.project_id,
                    _GLOSSARY_SYNC_COST_PER_ITEM,
                )
                items_processed += 1

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
    glossary_client: GlossaryClient,
) -> int:
    """One poll cycle: find running jobs and process them.

    Returns the number of jobs processed (for logging/metrics).
    Called repeatedly by the main loop with a sleep interval.
    """
    jobs = await _get_running_jobs(pool)
    if not jobs:
        return 0

    for job in jobs:
        await process_job(
            pool, knowledge_client, book_client, glossary_client, job,
        )

    return len(jobs)
