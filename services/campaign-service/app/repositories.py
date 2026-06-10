"""Data access for campaigns + the campaign_chapters projection.

Inline asyncpg (no ORM), mirroring translation-service. Two consumers:
  * the projection **consumer** sets a stage's status from an inbound event,
    correlating event→campaign by (book_id, owner_user_id, chapter_id);
  * the saga **driver** loads active campaigns + chapter states and records
    dispatch/failure outcomes.

Stage→column is a fixed whitelist (`_STAGE_COL`) — the stage string only ever
comes from internal code (gating/consumer), never from request bodies, and is
validated against the whitelist before any SQL interpolation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

import asyncpg

from .saga.gating import ChapterState

# Whitelist: stage → projection column. Interpolated into SQL ONLY after this
# membership check, so a rogue stage string can never reach the query.
_STAGE_COL = {
    "knowledge": "knowledge_status",
    "translation": "translation_status",
    "eval": "eval_status",
}
_ATTEMPTS_COL = {
    "knowledge": "knowledge_attempts",
    "translation": "translation_attempts",
}

_CAMPAIGN_COLS = """
  campaign_id, owner_user_id, book_id, name, status, gating_mode, stages,
  target_language, knowledge_project_id,
  knowledge_model_source, knowledge_model_ref,
  translation_model_source, translation_model_ref,
  verifier_model_source, verifier_model_ref,
  eval_judge_model_source, eval_judge_model_ref,
  chapter_from, chapter_to, budget_usd, spent_usd, total_chapters, error_message,
  created_at, updated_at, started_at, finished_at
"""


def _stage_col(stage: str) -> str:
    col = _STAGE_COL.get(stage)
    if col is None:
        raise ValueError(f"unknown stage: {stage!r}")
    return col


# ── Campaign CRUD ─────────────────────────────────────────────────────────


async def create_campaign(
    conn: asyncpg.Connection,
    *,
    owner_user_id: UUID,
    book_id: UUID,
    name: str,
    gating_mode: str,
    target_language: Optional[str],
    knowledge_project_id: Optional[UUID],
    knowledge_model_source: Optional[str],
    knowledge_model_ref: Optional[UUID],
    translation_model_source: Optional[str],
    translation_model_ref: Optional[UUID],
    chapter_from: Optional[int],
    chapter_to: Optional[int],
    total_chapters: int,
    budget_usd: Optional[Decimal] = None,
    verifier_model_source: Optional[str] = None,
    verifier_model_ref: Optional[UUID] = None,
    eval_judge_model_source: Optional[str] = None,
    eval_judge_model_ref: Optional[UUID] = None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        f"""
        INSERT INTO campaigns (
          owner_user_id, book_id, name, gating_mode, target_language,
          knowledge_project_id, knowledge_model_source, knowledge_model_ref,
          translation_model_source, translation_model_ref,
          verifier_model_source, verifier_model_ref,
          eval_judge_model_source, eval_judge_model_ref,
          chapter_from, chapter_to, total_chapters, budget_usd
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
        RETURNING {_CAMPAIGN_COLS}
        """,
        owner_user_id, book_id, name, gating_mode, target_language,
        knowledge_project_id, knowledge_model_source, knowledge_model_ref,
        translation_model_source, translation_model_ref,
        verifier_model_source, verifier_model_ref,
        eval_judge_model_source, eval_judge_model_ref,
        chapter_from, chapter_to, total_chapters, budget_usd,
    )


async def seed_campaign_chapters(
    conn: asyncpg.Connection,
    campaign_id: UUID,
    chapters: list[tuple[UUID, int]],
) -> None:
    """Bulk-insert the per-chapter projection rows (chapter_id, sort_order).

    All stages start `pending`; ingest defaults `done` (decision I — ingest is
    a precondition verified at create, not a campaign stage). ON CONFLICT keeps
    seeding idempotent if create is retried."""
    if not chapters:
        return
    await conn.executemany(
        """
        INSERT INTO campaign_chapters (campaign_id, chapter_id, chapter_sort)
        VALUES ($1, $2, $3)
        ON CONFLICT (campaign_id, chapter_id) DO NOTHING
        """,
        [(campaign_id, cid, sort) for cid, sort in chapters],
    )


async def get_campaign(
    pool: asyncpg.Pool, campaign_id: UUID, owner_user_id: UUID,
) -> Optional[asyncpg.Record]:
    return await pool.fetchrow(
        f"SELECT {_CAMPAIGN_COLS} FROM campaigns "
        f"WHERE campaign_id = $1 AND owner_user_id = $2",
        campaign_id, owner_user_id,
    )


async def list_campaigns(
    pool: asyncpg.Pool, owner_user_id: UUID,
) -> list[asyncpg.Record]:
    return await pool.fetch(
        f"SELECT {_CAMPAIGN_COLS} FROM campaigns "
        f"WHERE owner_user_id = $1 ORDER BY created_at DESC",
        owner_user_id,
    )


async def get_campaign_chapters(
    pool: asyncpg.Pool, campaign_id: UUID,
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT chapter_id, chapter_sort, ingest_status, knowledge_status,
               translation_status, eval_status, knowledge_attempts,
               translation_attempts, last_error, eval_fidelity_score
        FROM campaign_chapters
        WHERE campaign_id = $1
        ORDER BY chapter_sort ASC
        """,
        campaign_id,
    )


async def get_campaign_progress(
    pool: asyncpg.Pool, campaign_id: UUID,
) -> asyncpg.Record:
    """S6 — per-stage progress counts for the live monitor. ONE aggregate over
    campaign_chapters (O(1) payload regardless of chapter count, unlike fetching
    the full chapters[]). Counts done/failed/skipped per stage; the route derives
    in_progress = total - done - failed - skipped."""
    return await pool.fetchrow(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE knowledge_status   = 'done')    AS kn_done,
          COUNT(*) FILTER (WHERE knowledge_status   = 'failed')  AS kn_failed,
          COUNT(*) FILTER (WHERE knowledge_status   = 'skipped') AS kn_skipped,
          COUNT(*) FILTER (WHERE translation_status = 'done')    AS tr_done,
          COUNT(*) FILTER (WHERE translation_status = 'failed')  AS tr_failed,
          COUNT(*) FILTER (WHERE translation_status = 'skipped') AS tr_skipped,
          COUNT(*) FILTER (WHERE eval_status        = 'done')    AS ev_done,
          COUNT(*) FILTER (WHERE eval_status        = 'failed')  AS ev_failed,
          COUNT(*) FILTER (WHERE eval_status        = 'skipped') AS ev_skipped
        FROM campaign_chapters
        WHERE campaign_id = $1
        """,
        campaign_id,
    )


async def set_campaign_status(
    pool: asyncpg.Pool,
    campaign_id: UUID,
    status: str,
    *,
    error_message: Optional[str] = None,
    set_started: bool = False,
    set_finished: bool = False,
) -> None:
    await pool.execute(
        """
        UPDATE campaigns
        SET status = $2,
            error_message = COALESCE($3, error_message),
            started_at = CASE WHEN $4 AND started_at IS NULL THEN now() ELSE started_at END,
            finished_at = CASE WHEN $5 THEN now() ELSE finished_at END,
            updated_at = now()
        WHERE campaign_id = $1
        """,
        campaign_id, status, error_message, set_started, set_finished,
    )


# ── S4d budget cap: spend accumulation + budget update ─────────────────────


async def accumulate_and_maybe_pause(
    pool: asyncpg.Pool,
    *,
    request_id: UUID,
    campaign_id: UUID,
    cost_usd: Decimal,
) -> bool:
    """Add one usage event's cost to the campaign's spent_usd and auto-pause it if
    that reaches budget_usd — all in ONE tx. Idempotent: the campaign_usage_seen PK
    dedups a redelivered event (returns False, no double-count). The pause is folded
    into the accumulate UPDATE and only fires `running`→`paused` (so it composes with
    breaker-pause / manual pause and never resurrects a terminal campaign).

    Returns True when this event was freshly counted, False on a duplicate.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            fresh = await conn.fetchval(
                """
                INSERT INTO campaign_usage_seen (request_id, campaign_id, cost_usd)
                VALUES ($1, $2, $3)
                ON CONFLICT (request_id) DO NOTHING
                RETURNING request_id
                """,
                request_id, campaign_id, cost_usd,
            )
            if fresh is None:
                return False  # already counted — no-op
            await conn.execute(
                """
                UPDATE campaigns
                SET spent_usd = spent_usd + $2,
                    status = CASE
                        WHEN budget_usd IS NOT NULL AND spent_usd + $2 >= budget_usd
                             AND status = 'running' THEN 'paused'
                        ELSE status END,
                    error_message = CASE
                        WHEN budget_usd IS NOT NULL AND spent_usd + $2 >= budget_usd
                             AND status = 'running' THEN 'budget cap reached'
                        ELSE error_message END,
                    updated_at = now()
                WHERE campaign_id = $1
                """,
                campaign_id, cost_usd,
            )
            return True


async def update_budget(
    pool: asyncpg.Pool, campaign_id: UUID, owner_user_id: UUID, budget_usd: Decimal,
) -> Optional[asyncpg.Record]:
    """Owner-scoped budget update (PATCH). Returns the updated row, or None when the
    campaign isn't found / not owned (→ 404). Does NOT change status — a paused
    campaign stays paused; resume via /start once budget_usd is above spent_usd."""
    return await pool.fetchrow(
        f"""
        UPDATE campaigns
        SET budget_usd = $3, updated_at = now()
        WHERE campaign_id = $1 AND owner_user_id = $2
        RETURNING {_CAMPAIGN_COLS}
        """,
        campaign_id, owner_user_id, budget_usd,
    )


# ── Projection consumer write path ────────────────────────────────────────


async def mark_stage_done_by_chapter(
    pool: asyncpg.Pool,
    *,
    owner_user_id: UUID,
    book_id: UUID,
    chapter_id: UUID,
    stage: str,
    target_language: Optional[str] = None,
) -> int:
    """Set `stage` → 'done' for `chapter_id` across every ACTIVE campaign on this
    (book, user). Returns the number of rows updated.

    Convergent + idempotent: re-delivery of the same event is a no-op write.
    A chapter may belong to multiple concurrent campaigns on the same book —
    all matching rows advance.

    `target_language` is the LANGUAGE GUARD for language-specific stages
    (translation/eval): a `chapter.translated(vi)` event must only advance
    campaigns whose `target_language` is `vi` (or NULL = delegated to the user's
    saved settings). Without it, an out-of-band or different-language translation
    would silently mark a campaign's chapter done in the WRONG language. Pass
    None for the language-agnostic knowledge stage (no filter)."""
    col = _stage_col(stage)
    result = await pool.execute(
        f"""
        UPDATE campaign_chapters cc
        SET {col} = 'done', last_error = NULL, updated_at = now()
        FROM campaigns c
        WHERE c.campaign_id = cc.campaign_id
          AND c.book_id = $1
          AND c.owner_user_id = $2
          -- 'paused' included (S3c): a paused campaign stops NEW dispatch but
          -- must still absorb completions of already-in-flight jobs, else those
          -- chapters stay 'dispatched' and get stuck on resume.
          AND c.status IN ('running', 'cancelling', 'paused')
          AND cc.chapter_id = $3
          AND ($4::text IS NULL OR c.target_language IS NULL OR c.target_language = $4)
          AND cc.{col} <> 'done'
        """,
        book_id, owner_user_id, chapter_id, target_language,
    )
    # asyncpg returns e.g. "UPDATE 3"
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def set_eval_fidelity_by_chapter(
    pool: asyncpg.Pool,
    *,
    owner_user_id: UUID,
    book_id: UUID,
    chapter_id: UUID,
    score: float,
    target_language: Optional[str] = None,
) -> int:
    """S5b-eval: record the translation-fidelity judge's [0,1] score for a chapter
    across every active campaign on this (book, user). Additive telemetry — does
    NOT touch eval_status (the eval stage still advances via translation.quality;
    the LLM judge is best-effort and must not gate completion). Same (book, owner,
    language) correlation + active-status filter as the stage-done path; idempotent
    (a re-delivered eval_judged event just rewrites the same score)."""
    result = await pool.execute(
        """
        UPDATE campaign_chapters cc
        SET eval_fidelity_score = $4, updated_at = now()
        FROM campaigns c
        WHERE c.campaign_id = cc.campaign_id
          AND c.book_id = $1
          AND c.owner_user_id = $2
          AND c.status IN ('running', 'cancelling', 'paused')
          AND cc.chapter_id = $3
          AND ($5::text IS NULL OR c.target_language IS NULL OR c.target_language = $5)
        """,
        book_id, owner_user_id, chapter_id, score, target_language,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def pause_campaigns_for_dispatched_chapter(
    pool: asyncpg.Pool,
    *,
    owner_user_id: UUID,
    book_id: UUID,
    chapter_id: UUID,
    stage: str,
    reason: str,
) -> int:
    """S3c-2b breaker→pause: auto-pause RUNNING campaigns whose in-flight
    `(chapter, stage)` just hit a provider circuit-open. Precise correlation —
    only campaigns that actually dispatched THIS chapter for THIS stage pause
    (not unrelated campaigns on the same book). Returns rows paused. Idempotent
    (WHERE status='running')."""
    col = _stage_col(stage)
    result = await pool.execute(
        f"""
        UPDATE campaigns c
        SET status = 'paused', error_message = $4, updated_at = now()
        WHERE c.owner_user_id = $1
          AND c.book_id = $2
          AND c.status = 'running'
          AND EXISTS (
            SELECT 1 FROM campaign_chapters cc
            WHERE cc.campaign_id = c.campaign_id
              AND cc.chapter_id = $3
              AND cc.{col} = 'dispatched'
          )
        """,
        owner_user_id, book_id, chapter_id, reason,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


# ── Saga driver read/write path ───────────────────────────────────────────


async def list_active_campaigns(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Non-terminal campaigns the reconcile loop must drive (no claim — used by
    tests / single-replica callers)."""
    return await pool.fetch(
        f"SELECT {_CAMPAIGN_COLS} FROM campaigns "
        f"WHERE status IN ('running', 'cancelling') ORDER BY created_at ASC"
    )


async def claim_active_campaigns(
    pool: asyncpg.Pool, *, driver_id: str, lease_seconds: int, limit: int,
) -> list[asyncpg.Record]:
    """HA claim (S3c, D-CAMPAIGN-DRIVER-SINGLETON): atomically LEASE up to `limit`
    active campaigns to THIS driver and return them. Claimable = lease expired,
    NULL, OR already owned by this driver (`driver_leased_by = driver_id`) — so
    the owner RENEWS its own leases every tick while a peer skips a live lease.
    `FOR UPDATE SKIP LOCKED` gives disjoint claims across concurrent replicas;
    the lease (not a held lock) lets the driver process outside the transaction.
    A crashed driver's lease expires → another replica re-claims.

    The lease MUST exceed one process_campaign tick so a campaign this driver is
    mid-processing isn't re-claimed by a peer."""
    return await pool.fetch(
        f"""
        UPDATE campaigns
        SET driver_leased_until = now() + make_interval(secs => $1::int),
            driver_leased_by = $3,
            updated_at = now()
        WHERE campaign_id IN (
            SELECT campaign_id FROM campaigns
            WHERE status IN ('running', 'cancelling')
              AND (driver_leased_until IS NULL
                   OR driver_leased_until < now()
                   OR driver_leased_by = $3)
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT $2::int
        )
        RETURNING {_CAMPAIGN_COLS}
        """,
        lease_seconds, limit, driver_id,
    )


async def load_chapter_states(
    pool: asyncpg.Pool, campaign_id: UUID,
) -> list[ChapterState]:
    rows = await pool.fetch(
        """
        SELECT chapter_id, knowledge_status, translation_status,
               knowledge_attempts, translation_attempts
        FROM campaign_chapters
        WHERE campaign_id = $1
        ORDER BY chapter_sort ASC
        """,
        campaign_id,
    )
    return [
        ChapterState(
            chapter_id=str(r["chapter_id"]),
            knowledge_status=r["knowledge_status"],
            translation_status=r["translation_status"],
            knowledge_attempts=r["knowledge_attempts"],
            translation_attempts=r["translation_attempts"],
        )
        for r in rows
    ]


async def count_inflight(pool: asyncpg.Pool, campaign_id: UUID) -> int:
    """Rows currently `dispatched` for either dispatchable stage (the driver's
    bounded in-flight window for S1 fairness)."""
    return await pool.fetchval(
        """
        SELECT count(*) FROM campaign_chapters
        WHERE campaign_id = $1
          AND (knowledge_status = 'dispatched' OR translation_status = 'dispatched')
        """,
        campaign_id,
    )


async def mark_stage_dispatched(
    pool: asyncpg.Pool, campaign_id: UUID, chapter_id: str, stage: str,
) -> None:
    """Atomically flip `stage`→'dispatched' and bump its attempt counter, but
    ONLY from a dispatchable status — guards against a concurrent reconcile or a
    racing completion event double-dispatching the same (chapter, stage)."""
    col = _stage_col(stage)
    acol = _ATTEMPTS_COL[stage]
    await pool.execute(
        f"""
        UPDATE campaign_chapters
        SET {col} = 'dispatched', {acol} = {acol} + 1, last_error = NULL,
            updated_at = now()
        WHERE campaign_id = $1 AND chapter_id = $2
          AND {col} IN ('pending', 'failed')
        """,
        campaign_id, UUID(chapter_id),
    )


_STAGE_JOB_COL = {"knowledge": "knowledge_job_id", "translation": "translation_job_id"}


async def set_dispatched_job_id(
    pool: asyncpg.Pool, campaign_id: UUID, chapter_ids: list[str], stage: str, job_id: str,
) -> None:
    """Record the downstream job that owns these chapters' in-flight `stage`
    (S3c-2), so a campaign cancel can target it. Only stamps rows still
    `dispatched` for this stage (the just-claimed batch)."""
    job_col = _STAGE_JOB_COL.get(stage)
    if job_col is None:
        raise ValueError(f"stage {stage!r} has no job-id column")
    col = _stage_col(stage)
    await pool.execute(
        f"""
        UPDATE campaign_chapters
        SET {job_col} = $3, updated_at = now()
        WHERE campaign_id = $1 AND chapter_id = ANY($2::uuid[])
          AND {col} = 'dispatched'
        """,
        campaign_id, [UUID(c) for c in chapter_ids], UUID(job_id),
    )


async def inflight_translation_job_ids(pool: asyncpg.Pool, campaign_id: UUID) -> list[UUID]:
    """Distinct translation job_ids still in flight (translation_status='dispatched')
    — the set a campaign cancel must propagate to."""
    rows = await pool.fetch(
        """
        SELECT DISTINCT translation_job_id FROM campaign_chapters
        WHERE campaign_id = $1 AND translation_status = 'dispatched'
          AND translation_job_id IS NOT NULL
        """,
        campaign_id,
    )
    return [r["translation_job_id"] for r in rows]


async def has_inflight_knowledge(pool: asyncpg.Pool, campaign_id: UUID) -> bool:
    """Whether any knowledge stage is in flight (so a cancel should hit the
    project's extraction job). Knowledge is one job per project, so we cancel by
    project_id rather than tracking per-chapter knowledge job_ids."""
    return bool(await pool.fetchval(
        """
        SELECT 1 FROM campaign_chapters
        WHERE campaign_id = $1 AND knowledge_status = 'dispatched' LIMIT 1
        """,
        campaign_id,
    ))


async def mark_dispatched_stages_cancelled(pool: asyncpg.Pool, campaign_id: UUID) -> None:
    """Terminalize still-`dispatched` stages on a cancel: the underlying jobs were
    just cancelled and will NOT emit completion events, so without this the rows
    stay `dispatched` forever and the campaign can't finalize. A genuine
    completion that raced in before cancel already flipped the row to `done`
    (consumer includes 'cancelling') — only still-dispatched rows are touched."""
    await pool.execute(
        """
        UPDATE campaign_chapters
        SET knowledge_status = CASE WHEN knowledge_status = 'dispatched' THEN 'failed' ELSE knowledge_status END,
            translation_status = CASE WHEN translation_status = 'dispatched' THEN 'failed' ELSE translation_status END,
            last_error = COALESCE(last_error, 'campaign cancelled'),
            updated_at = now()
        WHERE campaign_id = $1
          AND ('dispatched' IN (knowledge_status, translation_status))
        """,
        campaign_id,
    )


async def mark_stage_failed(
    pool: asyncpg.Pool, campaign_id: UUID, chapter_id: str, stage: str,
    error: str,
) -> None:
    col = _stage_col(stage)
    await pool.execute(
        f"""
        UPDATE campaign_chapters
        SET {col} = 'failed', last_error = $3, updated_at = now()
        WHERE campaign_id = $1 AND chapter_id = $2
        """,
        campaign_id, UUID(chapter_id), error[:2000],
    )
