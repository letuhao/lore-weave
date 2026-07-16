"""Writing-progress router (composition-service, LOOM T4.2).

GET  /works/{project_id}/progress?today=YYYY-MM-DD — today's authored words, the
     book total, the editable daily goal (read from work.settings), the current
     consecutive-day streak, and a 30-day day-words sparkline (the FE slices 7/30).
POST /works/{project_id}/progress/report {chapter_id, words, date} — the editor
     reports the active chapter's current total word count on save (a SNAPSHOT,
     keyed to the user's LOCAL date). Idempotent per (chapter, local date).

Access (spec 25 PM-8/PM-9/PM-16): the Work is resolved by `project_id` (un-user-
scoped) and every route gates the caller's E0 VIEW grant on the row's `book_id`
BEFORE it trusts the project_id — de-usering `works.get` without this gate would
be zero access control (any authenticated user could read/write any book's stats
by guessing the project id). The daily-progress/baseline tables themselves stay
OUTSIDE the package and PER-USER (PM-16): the stat is the caller's OWN authoring,
so `progress.*` keeps `user_id` — a legitimate viewer only ever sees/writes their
own words. The client supplies its local date so streaks honor the writer's
midnight, not UTC.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.repositories.daily_progress import DailyProgressRepo
from app.db.repositories.works import WorksRepo
from app.deps import get_daily_progress_repo, get_grant_client_dep, get_works_repo
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")

_SPARKLINE_DAYS = 30


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP. none→404 (no oracle), under→403.
    composition_work is PER-BOOK (spec 25 PM-9); this gate is the ONLY access
    decision that lets the route trust the project_id (the per-user progress stat
    it then reads/writes is the caller's own — PM-16)."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


def _parse_local_date(raw: str) -> date:
    """Parse a client-supplied local date (YYYY-MM-DD). 422 on a bad format so a
    malformed date can't silently shift the streak/window."""
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")


def _coerce_goal(settings: dict[str, Any]) -> int | None:
    """work.settings is a free-form JSONB blob; `daily_goal` is optional and only
    meaningful as a positive int. Anything else (absent / 0 / non-int) → no goal."""
    g = settings.get("daily_goal")
    if isinstance(g, bool):  # bool is an int subclass — exclude it explicitly
        return None
    if isinstance(g, int) and g > 0:
        return g
    return None


def _current_streak(day_words: dict[date, int], today: date) -> int:
    """Consecutive local-date days with any authored words (>0), counting back from
    today — or from yesterday if nothing is written yet today (the streak is still
    alive until the day ends). 0 once a gap is hit."""
    if day_words.get(today, 0) > 0:
        cur = today
    elif day_words.get(today - timedelta(days=1), 0) > 0:
        cur = today - timedelta(days=1)
    else:
        return 0
    streak = 0
    while day_words.get(cur, 0) > 0:
        streak += 1
        cur -= timedelta(days=1)
    return streak


def _sparkline(day_words: dict[date, int], today: date) -> list[dict[str, Any]]:
    """A dense `_SPARKLINE_DAYS`-long [today-(N-1) .. today] series (zero-filled for
    days with no writing) so the FE can render a continuous sparkline + slice 7/30."""
    return [
        {"date": (d := today - timedelta(days=i)).isoformat(), "words": day_words.get(d, 0)}
        for i in range(_SPARKLINE_DAYS - 1, -1, -1)
    ]


@router.get("/works/{project_id}/progress")
async def get_progress(
    project_id: UUID,
    today: str = Query(..., description="client local date, YYYY-MM-DD"),
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    progress: DailyProgressRepo = Depends(get_daily_progress_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # VIEW gate on the book before trusting project_id (PM-8); the per-user stat
    # below is still keyed to the caller (PM-16).
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    anchor = _parse_local_date(today)
    agg = await progress.read_aggregate(user_id, project_id, anchor)
    by_date = dict(agg.day_words)
    # BE-P2 — the goal is PER-USER (composition_progress_goal). Read-through fallback to the
    # legacy shared work.settings.daily_goal so no existing user loses a goal on cutover; the
    # WRITER only ever writes the new per-user table (the legacy window is closed in the writer).
    # SET-1: expose the source tier so the panel can show WHERE the effective value came from.
    user_goal = await progress.get_goal(user_id, project_id)
    legacy_goal = _coerce_goal(work.settings or {})
    if user_goal is not None:
        daily_goal, goal_source = user_goal, "user"
    elif legacy_goal is not None:
        daily_goal, goal_source = legacy_goal, "work_legacy"
    else:
        daily_goal, goal_source = None, "none"
    return {
        "today": anchor.isoformat(),
        "today_words": by_date.get(anchor, 0),
        "book_total": agg.book_total,
        "daily_goal": daily_goal,
        "daily_goal_source": goal_source,
        "current_streak": _current_streak(by_date, anchor),
        "sparkline": _sparkline(by_date, anchor),
    }


class ProgressGoalBody(BaseModel):
    # 0 clears the goal (per-user row deleted); a positive int sets it. Same sane upper cap.
    daily_goal: int = Field(ge=0, le=5_000_000)


@router.put("/works/{project_id}/progress/goal")
async def set_progress_goal(
    project_id: UUID,
    body: ProgressGoalBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    progress: DailyProgressRepo = Depends(get_daily_progress_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """BE-P2 — set the caller's OWN daily word goal for this Work (0 clears it). Per-user:
    one collaborator's goal never moves another's. VIEW-gated like the other progress routes
    (the goal is the caller's own stat, not a package mutation), then written to the per-user
    composition_progress_goal table — NOT work.settings (the tenancy defect this replaces)."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    await progress.set_goal(user_id, project_id, body.daily_goal)
    return {"ok": True, "daily_goal": body.daily_goal or None}


class ProgressReportBody(BaseModel):
    chapter_id: UUID
    # bounded: a chapter word count is realistically < a few million; the upper cap
    # turns an absurd/garbage value into a 422 instead of a 500 on the INT column.
    words: int = Field(ge=0, le=5_000_000)
    # the client's LOCAL date for this snapshot (YYYY-MM-DD)
    date: str


@router.post("/works/{project_id}/progress/report")
async def report_progress(
    project_id: UUID,
    body: ProgressReportBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    progress: DailyProgressRepo = Depends(get_daily_progress_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Record the active chapter's current total word count for the caller's local
    date. Idempotent per (chapter, date) — a re-save the same day overwrites the
    snapshot. Advisory: the FE fires this best-effort after a successful save."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # VIEW gate on the book before trusting project_id (PM-8); the snapshot is
    # written to the caller's OWN per-user progress row (PM-16).
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    snapshot_date = _parse_local_date(body.date)
    await progress.report(user_id, project_id, body.chapter_id, body.words, snapshot_date)
    return {"ok": True, "date": snapshot_date.isoformat(), "words": body.words}


class ProgressBaselineBody(BaseModel):
    chapter_id: UUID
    # the chapter's PRE-EXISTING word count at open (same cap rationale as report)
    words: int = Field(ge=0, le=5_000_000)


@router.post("/works/{project_id}/progress/baseline")
async def baseline_progress(
    project_id: UUID,
    body: ProgressBaselineBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    progress: DailyProgressRepo = Depends(get_daily_progress_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Capture a chapter's pre-existing word count the first time it is opened after
    tracking starts (insert-once; re-opens never overwrite). The FE fires this on
    chapter load so the chapter's first daily snapshot counts only NEW words. Advisory
    / best-effort — like the report, a failure never blocks editing."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # VIEW gate on the book before trusting project_id (PM-8); the baseline is the
    # caller's OWN per-user row (PM-16).
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    await progress.ensure_baseline(user_id, project_id, body.chapter_id, body.words)
    return {"ok": True}
