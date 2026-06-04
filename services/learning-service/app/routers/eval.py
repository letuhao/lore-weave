"""Eval-run read API — `/v1/learning/eval-runs` (track phase Q1).

STRICT per-owner isolation: every query filters on `user_id = JWT.sub`. The
quality plane is the eval half of the learning-service; this surfaces the
persisted metric-of-record (disjoint median F1 + CI + per-judge breakdown) for
the caller's corpus.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.eval_repo import get_eval_run, list_eval_runs
from app.deps import get_current_user, get_db
from app.models import (
    EvalResultRow,
    EvalRunDetail,
    EvalRunList,
    EvalRunRow,
)

router = APIRouter(prefix="/v1/learning", tags=["learning-eval"])

_UUID_FIELDS = (
    "eval_run_id",
    "user_id",
    "project_id",
    "book_id",
    "source_extraction_run_id",
)


def _stringify(d: dict) -> dict:
    """asyncpg returns UUID columns as uuid.UUID; the response models use str."""
    for k in _UUID_FIELDS:
        if d.get(k) is not None:
            d[k] = str(d[k])
    return d


@router.get("/eval-runs", response_model=EvalRunList)
async def list_eval_runs_endpoint(
    project_id: UUID | None = Query(default=None),
    config_hash: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> EvalRunList:
    """List the caller's eval runs, newest first."""
    rows = await list_eval_runs(
        pool,
        user_id=UUID(user_id),
        project_id=project_id,
        config_hash=config_hash,
        source=source,
        limit=limit,
        offset=offset,
    )
    return EvalRunList(items=[EvalRunRow(**_stringify(r)) for r in rows])


@router.get("/eval-runs/{eval_run_id}", response_model=EvalRunDetail)
async def get_eval_run_endpoint(
    eval_run_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> EvalRunDetail:
    """Fetch one eval run (owner-scoped) with its per-judge results."""
    run = await get_eval_run(pool, user_id=UUID(user_id), eval_run_id=eval_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    results = run.pop("results", [])
    return EvalRunDetail(
        **_stringify(run),
        results=[EvalResultRow(**r) for r in results],
    )
