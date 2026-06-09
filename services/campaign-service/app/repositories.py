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
  chapter_from, chapter_to, total_chapters, error_message,
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
) -> asyncpg.Record:
    return await conn.fetchrow(
        f"""
        INSERT INTO campaigns (
          owner_user_id, book_id, name, gating_mode, target_language,
          knowledge_project_id, knowledge_model_source, knowledge_model_ref,
          translation_model_source, translation_model_ref,
          chapter_from, chapter_to, total_chapters
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
        RETURNING {_CAMPAIGN_COLS}
        """,
        owner_user_id, book_id, name, gating_mode, target_language,
        knowledge_project_id, knowledge_model_source, knowledge_model_ref,
        translation_model_source, translation_model_ref,
        chapter_from, chapter_to, total_chapters,
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
               translation_attempts, last_error
        FROM campaign_chapters
        WHERE campaign_id = $1
        ORDER BY chapter_sort ASC
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
