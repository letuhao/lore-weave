"""Stuck-`dispatched` self-heal — D-CAMPAIGN-BESTEFFORT-EMIT-REDIS.

The saga advances per-chapter stages on inbound completion events
(`knowledge.chapter_extracted`, `chapter.translated`). Those events are
best-effort across a service boundary (worker-ai outbox → relay → redis →
consumer): a lost emit, a relay/redis hiccup, or a consumer drop leaves a stage
stuck in `dispatched` — and gating never re-dispatches `dispatched`, so without
this it stalls **forever** (the live-smoke "did not recover in 10 min").

Reconcile-by-TRUTH (decision, CLARIFY): once a stage has sat `dispatched` past
the timeout, ask the downstream service whether the work actually finished.
  * finished  → mark the chapter `done` WITHOUT re-dispatching (zero re-spend);
  * failed/gone → reset to `failed` so gating re-dispatches within the attempt
    cap (the downstream skip-gate prevents re-spend on already-done work);
  * still in-flight → leave it (a slow job is not stuck).

Knowledge runs one extraction job per project over a scope (no per-chapter job),
so its truth is project-scoped and queried once per campaign. Translation tracks
a per-chapter job, so its truth is queried per stuck (job, chapter).

Conservative on uncertainty: any downstream error LEAVES the row untouched (it
retries next reconcile) — never reset on a transient failure (no re-dispatch loop).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import asyncpg

from .. import repositories as repo
from ..clients.dispatch_clients import DispatchError

if TYPE_CHECKING:  # avoid a circular import with driver.py at runtime
    from .driver import DispatchClients

logger = logging.getLogger(__name__)


async def reconcile_stuck(
    pool: asyncpg.Pool,
    clients: "DispatchClients",
    campaign: asyncpg.Record,
    *,
    timeout_s: int,
) -> None:
    """Self-heal stuck-`dispatched` stages for one campaign against downstream
    truth. Cheap when healthy: a single indexed query, and the cross-service
    truth calls only fire when there IS a stuck row past the timeout."""
    campaign_id: UUID = campaign["campaign_id"]
    stuck = await repo.find_stuck_dispatched(pool, campaign_id, timeout_s)
    if not stuck:
        return  # healthy — no cross-service calls

    knowledge_stuck = [r for r in stuck if r["knowledge_status"] == "dispatched"]
    translation_stuck = [r for r in stuck if r["translation_status"] == "dispatched"]

    if knowledge_stuck:
        await _reconcile_knowledge(pool, clients, campaign, knowledge_stuck)
    if translation_stuck:
        await _reconcile_translation(pool, clients, campaign, translation_stuck)


async def _reconcile_knowledge(
    pool: asyncpg.Pool,
    clients: "DispatchClients",
    campaign: asyncpg.Record,
    stuck: list[asyncpg.Record],
) -> None:
    campaign_id: UUID = campaign["campaign_id"]
    # E0-4b: the knowledge project + graph belong to the BOOK OWNER. Probe extraction
    # truth under that identity, and mark-done under it too — the knowledge-stage
    # consumer correlation now matches `book_owner_user_id` (= the event's user_id).
    book_owner: UUID = campaign["book_owner_user_id"] or campaign["owner_user_id"]
    book_id: UUID = campaign["book_id"]
    project_id = campaign["knowledge_project_id"]

    if project_id is None:
        # A knowledge stage can't legitimately be dispatched without a project
        # (the driver marks it failed first) — reset defensively.
        for row in stuck:
            await repo.reset_stuck_stage(
                pool, campaign_id, str(row["chapter_id"]), "knowledge",
                "stuck-reconcile: no knowledge_project_id",
            )
        return

    try:
        status = await clients.knowledge.extraction_status(
            user_id=str(book_owner), project_id=str(project_id),
        )
    except DispatchError as exc:
        logger.warning(
            "campaign %s knowledge reconcile: truth query failed (%s) — leaving "
            "%d stuck row(s) for next pass", campaign_id, exc, len(stuck),
        )
        return

    if status.get("active"):
        return  # extraction still in flight — these chapters are legitimately slow

    # NOTE (latent drift — D-CAMPAIGN-RECONCILE-KNOWLEDGE-RANGE): treating a
    # 'complete' project extraction as "every stuck chapter was extracted" is
    # correct only because the worker-ai runner currently processes the WHOLE
    # project scope (it does not yet honour chapter_range — D-K16.2-02b/S2). If S2
    # makes extraction range-aware, a completed PARTIAL job could mark out-of-range
    # chapters done falsely; this must then become a per-chapter truth (e.g. a
    # processed-cursor / extracted-set check) rather than the project outcome.
    outcome = status.get("last_outcome")
    for row in stuck:
        chapter_id = str(row["chapter_id"])
        if outcome == "complete":
            await repo.mark_stage_done_by_chapter(
                pool, owner_user_id=book_owner, book_id=book_id,
                chapter_id=UUID(chapter_id), stage="knowledge", target_language=None,
            )
            logger.info(
                "campaign %s knowledge reconcile: chapter %s → done (extraction "
                "complete, event lost)", campaign_id, chapter_id,
            )
        else:
            await repo.reset_stuck_stage(
                pool, campaign_id, chapter_id, "knowledge",
                f"stuck-reconcile: extraction {outcome or 'no-job'}",
            )


async def _reconcile_translation(
    pool: asyncpg.Pool,
    clients: "DispatchClients",
    campaign: asyncpg.Record,
    stuck: list[asyncpg.Record],
) -> None:
    """Resolve stuck translation rows, grouped by their dispatching job. A campaign
    dispatches a chapter batch as ONE job, so the common case is a single group:
    one job-aliveness call decides "all in-flight → leave" vs "terminal → resolve
    per chapter". This bounds the per-chapter truth fan-out — a slow-but-alive job
    past the timeout costs ONE call per tick, not one per stuck chapter."""
    campaign_id: UUID = campaign["campaign_id"]
    owner_user_id: UUID = campaign["owner_user_id"]

    # Group by job_id. Rows with no job_id (crash between claim and the job-id
    # stamp) have no truth to query → reset directly.
    by_job: dict[str, list[asyncpg.Record]] = {}
    for row in stuck:
        job_id = row["translation_job_id"]
        if job_id is None:
            await repo.reset_stuck_stage(
                pool, campaign_id, str(row["chapter_id"]), "translation",
                "stuck-reconcile: no translation_job_id",
            )
            continue
        by_job.setdefault(str(job_id), []).append(row)

    for job_id, rows in by_job.items():
        try:
            job_state = await clients.translation.job_status(
                user_id=str(owner_user_id), job_id=job_id,
            )
        except DispatchError as exc:
            logger.warning(
                "campaign %s translation reconcile: job_status(%s) failed (%s) — "
                "leaving %d chapter(s) for next pass",
                campaign_id, job_id, exc, len(rows),
            )
            continue
        if job_state == "active":
            continue  # batch still in flight — every chapter is legitimately slow
        if job_state == "gone":
            for row in rows:
                await repo.reset_stuck_stage(
                    pool, campaign_id, str(row["chapter_id"]), "translation",
                    "stuck-reconcile: translation job gone",
                )
            continue
        # terminal → resolve each chapter against its fresh-translation truth.
        for row in rows:
            await _resolve_terminal_translation_chapter(
                pool, clients, campaign, job_id, row,
            )


async def _resolve_terminal_translation_chapter(
    pool: asyncpg.Pool,
    clients: "DispatchClients",
    campaign: asyncpg.Record,
    job_id: str,
    row: asyncpg.Record,
) -> None:
    campaign_id: UUID = campaign["campaign_id"]
    owner_user_id: UUID = campaign["owner_user_id"]
    book_id: UUID = campaign["book_id"]
    target_language = campaign["target_language"]
    chapter_id = str(row["chapter_id"])

    try:
        status = await clients.translation.chapter_status(
            user_id=str(owner_user_id), job_id=job_id, chapter_id=chapter_id,
        )
    except DispatchError as exc:
        logger.warning(
            "campaign %s translation reconcile: chapter_status(%s) failed (%s) — "
            "leaving chapter for next pass", campaign_id, chapter_id, exc,
        )
        return

    if status == "done":
        await repo.mark_stage_done_by_chapter(
            pool, owner_user_id=owner_user_id, book_id=book_id,
            chapter_id=UUID(chapter_id), stage="translation",
            target_language=target_language,
        )
        logger.info(
            "campaign %s translation reconcile: chapter %s → done (translated, "
            "event lost)", campaign_id, chapter_id,
        )
    else:  # "failed" | "gone" | "running" — a terminal job won't progress, re-dispatch
        await repo.reset_stuck_stage(
            pool, campaign_id, chapter_id, "translation",
            f"stuck-reconcile: translation {status}",
        )
