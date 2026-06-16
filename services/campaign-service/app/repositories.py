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
from loreweave_jobs import emit_job_event, emit_job_event_safe

from .saga.gating import ChapterState

#: Unified Job Control Plane P1 — the service id stamped on every emitted JobEvent.
_JOB_SERVICE = "campaign"

# campaign-native status → canonical JobStatus. Only `created` is non-canonical
# (maps to `pending`); every other native value is already a canonical JobStatus
# (running/paused/cancelling/completed/failed/cancelled). The native string is
# preserved verbatim in the event's `detail_status` whenever it differs.
_CANONICAL_STATUS = {
    "created": "pending",
    "running": "running",
    "paused": "paused",
    "cancelling": "cancelling",
    "cancelled": "cancelled",
    "completed": "completed",
    "failed": "failed",
}


def _canonical_status(native: str) -> str:
    """Map a campaign-native status to the closest canonical JobStatus."""
    return _CANONICAL_STATUS.get(native, native)

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
    est_usd_low: Optional[Decimal] = None,
    est_usd_high: Optional[Decimal] = None,
    knowledge_model_name: Optional[str] = None,
    translation_model_name: Optional[str] = None,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f"""
        INSERT INTO campaigns (
          owner_user_id, book_id, name, gating_mode, target_language,
          knowledge_project_id, knowledge_model_source, knowledge_model_ref,
          translation_model_source, translation_model_ref,
          verifier_model_source, verifier_model_ref,
          eval_judge_model_source, eval_judge_model_ref,
          chapter_from, chapter_to, total_chapters, budget_usd,
          est_usd_low, est_usd_high
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
        RETURNING {_CAMPAIGN_COLS}
        """,
        owner_user_id, book_id, name, gating_mode, target_language,
        knowledge_project_id, knowledge_model_source, knowledge_model_ref,
        translation_model_source, translation_model_ref,
        verifier_model_source, verifier_model_ref,
        eval_judge_model_source, eval_judge_model_ref,
        chapter_from, chapter_to, total_chapters, budget_usd,
        est_usd_low, est_usd_high,
    )
    # Unified Job Control Plane P1 — emit the initial lifecycle event on the SAME
    # conn as the INSERT (the router wraps both in one tx, so the event commits
    # atomically with the new campaign row — H1). A campaign starts `created`,
    # whose canonical JobStatus is `pending`; the native string rides detail_status.
    native = row["status"]
    canonical = _canonical_status(native)
    # P4 — whitelisted params + cost (spent_usd, 0 at create; accumulates via the S4
    # SpendConsumer). D-JOBS-P4-CAMPAIGN-MODEL-NAMES: per-stage model NAMES are now resolved
    # by the ROUTER OUT-OF-TX (resolving here would be HTTP inside the router's tx — H1) and
    # passed in; emitted ONLY on create, where the projection's COALESCE keeps them across
    # the later status events. The refs still ride params too. (top-level `model` carries the
    # translation-stage name as the campaign's primary model for the GUI's model column.)
    _spent = row["spent_usd"]
    await emit_job_event(
        conn, service=_JOB_SERVICE, job_id=str(row["campaign_id"]),
        owner_user_id=str(row["owner_user_id"]), kind="campaign", status=canonical,
        detail_status=native if native != canonical else None,
        title=row["name"],
        cost_usd=float(_spent) if _spent is not None else None,
        model=translation_model_name or knowledge_model_name,
        params={
            "gating_mode": row["gating_mode"],
            "target_language": row["target_language"],
            "total_chapters": row["total_chapters"],
            "knowledge_model_ref": (
                str(row["knowledge_model_ref"]) if row["knowledge_model_ref"] else None
            ),
            "translation_model_ref": (
                str(row["translation_model_ref"]) if row["translation_model_ref"] else None
            ),
            "knowledge_model": knowledge_model_name,
            "translation_model": translation_model_name,
        },
    )
    return row


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
    # #2 polish — include a lightweight progress count (translation done+skipped) per
    # row via a correlated subquery, for the list's progress bar (one query total).
    return await pool.fetch(
        f"""
        SELECT {_CAMPAIGN_COLS},
          (SELECT COUNT(*) FROM campaign_chapters cc
           WHERE cc.campaign_id = campaigns.campaign_id
             AND cc.translation_status IN ('done', 'skipped')) AS progress_done
        FROM campaigns
        WHERE owner_user_id = $1 ORDER BY created_at DESC
        """,
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


_ATTENTION_FILTER = (
    "AND NOT (knowledge_status IN ('done','skipped') "
    "AND translation_status IN ('done','skipped') "
    "AND eval_status IN ('done','skipped'))"
)
# D-FACTORY-INFLIGHT-PANEL — rows with a stage currently dispatched to a provider
# (the "Now processing" panel). Only knowledge/translation are driver-dispatched
# (eval is observed, never sits in 'dispatched'); mirrors count_inflight's predicate.
_INFLIGHT_FILTER = "AND 'dispatched' IN (knowledge_status, translation_status)"

# status → WHERE fragment. A whitelist (never raw-interpolated): the router clamps
# the request value to these keys; an unknown value falls back to "attention".
_CHAPTER_FILTERS = {
    "attention": _ATTENTION_FILTER,
    "inflight": _INFLIGHT_FILTER,
    "all": "",
}


async def get_campaign_chapters_page(
    pool: asyncpg.Pool, campaign_id: UUID, *,
    status: str = "attention", limit: int = 200, offset: int = 0,
) -> tuple[list[asyncpg.Record], int]:
    """D-S6-CHAPTER-PAGING — one page of the per-chapter projection + the total
    (server-side, so a 4000-chapter campaign doesn't ship every row to the monitor).
    `status='attention'` filters to rows that aren't fully settled (failed or
    in-progress) — the table's default; `'inflight'` = rows with a stage currently
    dispatched (the processing panel); `'all'` returns everything. The filter is a
    fixed literal chosen by a whitelisted `status` (never raw-interpolated)."""
    where = _CHAPTER_FILTERS.get(status, _ATTENTION_FILTER)
    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM campaign_chapters WHERE campaign_id = $1 {where}",
        campaign_id,
    )
    rows = await pool.fetch(
        f"""
        SELECT chapter_id, chapter_sort, ingest_status, knowledge_status,
               translation_status, eval_status, knowledge_attempts,
               translation_attempts, last_error, eval_fidelity_score
        FROM campaign_chapters
        WHERE campaign_id = $1 {where}
        ORDER BY chapter_sort ASC
        LIMIT $2 OFFSET $3
        """,
        campaign_id, limit, offset,
    )
    return rows, int(total or 0)


async def get_campaign_activity(
    pool: asyncpg.Pool, campaign_id: UUID, *, limit: int = 50, before_id: Optional[int] = None,
) -> list[asyncpg.Record]:
    """D-FACTORY-INFLIGHT-LOG — one recent-first page of the activity log (written by
    the campaign_chapters trigger). Keyset pagination: `before_id` returns rows older
    than that id (id DESC), so newer rows arriving at the head never shift a page."""
    if before_id is not None:
        return await pool.fetch(
            """
            SELECT id, chapter_id, chapter_sort, stage, status, detail, created_at
            FROM campaign_activity
            WHERE campaign_id = $1 AND id < $2
            ORDER BY id DESC LIMIT $3
            """,
            campaign_id, before_id, limit,
        )
    return await pool.fetch(
        """
        SELECT id, chapter_id, chapter_sort, stage, status, detail, created_at
        FROM campaign_activity
        WHERE campaign_id = $1
        ORDER BY id DESC LIMIT $2
        """,
        campaign_id, limit,
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


async def get_report_row(
    pool: asyncpg.Pool, campaign_id: UUID, owner_user_id: UUID,
) -> Optional[asyncpg.Record]:
    """G1 — owner-scoped summary row for the completion report (status, timing,
    spend, budget, persisted estimate band). Dedicated SELECT so it stays isolated
    from the Campaign-building endpoints."""
    return await pool.fetchrow(
        """
        SELECT status, total_chapters, spent_usd, budget_usd,
               est_usd_low, est_usd_high, started_at, finished_at,
               EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))::bigint
                 AS duration_seconds
        FROM campaigns
        WHERE campaign_id = $1 AND owner_user_id = $2
        """,
        campaign_id, owner_user_id,
    )


async def get_failed_error_strings(
    pool: asyncpg.Pool, campaign_id: UUID,
) -> list[asyncpg.Record]:
    """G1 — (last_error, count) for chapters with a FAILED knowledge/translation
    stage, for the report's error grouping. The router buckets each `last_error` via
    `normalize_error_cause` and sums counts per cause (bucketing is a pure, unit-
    tested fn). Scoped to knowledge/translation (NOT eval) to match
    `reset_failed_stages` — eval is observed (rides translation.quality), not
    dispatched, so an eval failure is neither actionable nor re-runnable; counting it
    here would report an "error" that "Re-run all failed" can't clear (review-impl)."""
    return await pool.fetch(
        """
        SELECT last_error, COUNT(*) AS n
        FROM campaign_chapters
        WHERE campaign_id = $1
          AND 'failed' IN (knowledge_status, translation_status)
        GROUP BY last_error
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
    """Transition a campaign's status (the PRIMARY lifecycle chokepoint — driven by
    the /start, /pause, /cancel, /rerun-failed routes and the saga driver's
    complete/cancel paths). Unified Job Control Plane P1: emits the lifecycle
    JobEvent in the SAME tx as the UPDATE (H1 — the status change and its event
    commit atomically), only when a row actually matched. `status` is the
    campaign-native value; it maps to the closest canonical JobStatus for the
    event (native string preserved in detail_status when it differs)."""
    async with pool.acquire() as conn:
        async with conn.transaction():  # UPDATE + emit_job_event atomic (H1)
            row = await conn.fetchrow(
                """
                UPDATE campaigns
                SET status = $2,
                    error_message = COALESCE($3, error_message),
                    started_at = CASE WHEN $4 AND started_at IS NULL THEN now() ELSE started_at END,
                    finished_at = CASE WHEN $5 THEN now() ELSE finished_at END,
                    updated_at = now()
                WHERE campaign_id = $1
                RETURNING campaign_id, owner_user_id, status, error_message, spent_usd
                """,
                campaign_id, status, error_message, set_started, set_finished,
            )
            if row is None:
                return  # campaign vanished (cross-tenant / deleted) — nothing to emit
            native = row["status"]
            canonical = _canonical_status(native)
            # P4 — carry the CHANGING accumulated spend (params set once at create).
            _spent = row["spent_usd"]
            await emit_job_event(
                conn, service=_JOB_SERVICE, job_id=str(row["campaign_id"]),
                owner_user_id=str(row["owner_user_id"]), kind="campaign",
                status=canonical,
                detail_status=native if native != canonical else None,
                cost_usd=float(_spent) if _spent is not None else None,
                error=(
                    {"code": "error", "message": str(row["error_message"])}
                    if native == "failed" and row["error_message"]
                    else None
                ),
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
            updated = await conn.fetchrow(
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
                RETURNING owner_user_id, spent_usd, status
                """,
                campaign_id, cost_usd,
            )
    # D-JOBS-CAMPAIGN-SPEND-EMIT — surface the LIVE accumulated cost (and any auto-pause
    # folded into the UPDATE above) to the Jobs GUI. POST-COMMIT + best-effort: telemetry
    # must NEVER roll back the money accumulation, so a failed emit can't under-count spend;
    # the projection's COALESCE + the next status event are the durability backstop.
    if updated is not None:
        native = updated["status"]
        canonical = _canonical_status(native)
        _spent = updated["spent_usd"]
        await emit_job_event_safe(
            pool, service=_JOB_SERVICE, job_id=str(campaign_id),
            owner_user_id=str(updated["owner_user_id"]), kind="campaign", status=canonical,
            detail_status=native if native != canonical else None,
            cost_usd=float(_spent) if _spent is not None else None,
        )
    return True


# D-FACTORY-SWITCH-MODEL-RESUME — columns a PATCH may update. A whitelist so a
# rogue key can never reach the SET clause (the field name is interpolated only
# after this membership check; values stay parameterized). Embedding/rerank are
# NOT here (knowledge-project SSOT; embedding change is destructive to the graph).
_UPDATABLE_COLS = (
    "budget_usd",
    "translation_model_source", "translation_model_ref",
    "knowledge_model_source", "knowledge_model_ref",
    "verifier_model_source", "verifier_model_ref",
    "eval_judge_model_source", "eval_judge_model_ref",
)


async def update_campaign_fields(
    pool: asyncpg.Pool, campaign_id: UUID, owner_user_id: UUID, fields: dict,
) -> Optional[asyncpg.Record]:
    """Owner-scoped partial update (PATCH) of whitelisted campaign columns (budget +
    the four switchable LLM models). Only keys in `_UPDATABLE_COLS` are applied — the
    column name is interpolated solely from that whitelist, values stay parameterized.
    Returns the updated row, or None when no valid field is given / the campaign isn't
    found or owned (→ 404). Status is unchanged (resume via /start)."""
    cols = [c for c in _UPDATABLE_COLS if c in fields]
    if not cols:
        return None
    set_frag = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(cols))
    values = [fields[c] for c in cols]
    return await pool.fetchrow(
        f"""
        UPDATE campaigns
        SET {set_frag}, updated_at = now()
        WHERE campaign_id = $1 AND owner_user_id = $2
        RETURNING {_CAMPAIGN_COLS}
        """,
        campaign_id, owner_user_id, *values,
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


# ── D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: stuck-`dispatched` self-heal ──────────

async def find_stuck_dispatched(
    pool: asyncpg.Pool, campaign_id: UUID, timeout_s: int,
) -> list[asyncpg.Record]:
    """Rows where a stage has sat in `dispatched` longer than `timeout_s` — the
    completion event was never absorbed (lost best-effort emit, or a relay/consumer
    drop). `updated_at` is a sound stuck-timer: translation only dispatches after
    THIS chapter's knowledge is terminal-success (gating), so the two stages never
    co-occupy `dispatched` on one row, and nothing bumps `updated_at` while the
    single in-flight stage waits. Returns the per-stage status + translation_job_id
    so the reconcile can query the right downstream truth (knowledge truth is
    project-scoped — the project_id comes from the campaign, not the row)."""
    return await pool.fetch(
        """
        SELECT chapter_id, knowledge_status, translation_status, translation_job_id
        FROM campaign_chapters
        WHERE campaign_id = $1
          AND updated_at < now() - make_interval(secs => $2::int)
          AND 'dispatched' IN (knowledge_status, translation_status)
        """,
        campaign_id, timeout_s,
    )


async def reset_stuck_stage(
    pool: asyncpg.Pool, campaign_id: UUID, chapter_id: str, stage: str, reason: str,
) -> int:
    """Reset a stuck stage `dispatched`→'failed' so gating re-dispatches it within
    the attempt cap. Guarded on the CURRENT status still being `dispatched` — a
    real completion event that raced in already flipped it to `done`, and this
    no-ops (returns 0). The downstream skip-gate prevents re-spend on re-dispatch
    of already-completed work."""
    col = _stage_col(stage)
    result = await pool.execute(
        f"""
        UPDATE campaign_chapters
        SET {col} = 'failed', last_error = $3, updated_at = now()
        WHERE campaign_id = $1 AND chapter_id = $2 AND {col} = 'dispatched'
        """,
        campaign_id, UUID(chapter_id), reason[:2000],
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def reset_failed_stages(
    pool: asyncpg.Pool, campaign_id: UUID, chapter_ids: Optional[list[UUID]] = None,
) -> int:
    """G2 (user re-run-failed): reset FAILED knowledge/translation stages to
    'pending' + zero their attempts + clear last_error, so gating re-dispatches
    them (the downstream skip-gate prevents re-spend on already-done work). Scoped
    to `chapter_ids` (None = ALL failed chapters in the campaign). `eval` is OBSERVED
    (rides translation.quality), so it is not reset here. Returns rows changed."""
    result = await pool.execute(
        """
        UPDATE campaign_chapters
        SET knowledge_status   = CASE WHEN knowledge_status='failed'   THEN 'pending' ELSE knowledge_status END,
            knowledge_attempts = CASE WHEN knowledge_status='failed'   THEN 0 ELSE knowledge_attempts END,
            translation_status = CASE WHEN translation_status='failed' THEN 'pending' ELSE translation_status END,
            translation_attempts = CASE WHEN translation_status='failed' THEN 0 ELSE translation_attempts END,
            last_error = NULL,
            updated_at = now()
        WHERE campaign_id = $1
          AND 'failed' IN (knowledge_status, translation_status)
          AND ($2::uuid[] IS NULL OR chapter_id = ANY($2::uuid[]))
        """,
        campaign_id, chapter_ids,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0
