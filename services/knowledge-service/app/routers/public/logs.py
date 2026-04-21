"""K19b.8 — Public extraction-job log viewer endpoint.

GET /v1/knowledge/extraction/jobs/{job_id}/logs?since_log_id=0&limit=50

Paginated via `since_log_id` (the log_id of the last row the client
already has). `next_cursor` in the response is the max log_id when
the page is full, otherwise null — the client stops requesting.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db.repositories.extraction_jobs import ExtractionJobsRepo
from app.db.repositories.job_logs import JobLog, JobLogsRepo, LOGS_MAX_LIMIT
from app.deps import get_extraction_jobs_repo, get_job_logs_repo
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge/extraction",
    tags=["extraction-logs"],
    dependencies=[Depends(get_current_user)],
)


class JobLogsPage(BaseModel):
    logs: list[JobLog]
    # K19b.8: when the page is full (`len(logs) == limit`), next_cursor
    # is the max log_id from the page. FE uses it as `since_log_id`
    # for the follow-up request. `None` signals end-of-stream so the
    # FE can hide the "load more" affordance.
    next_cursor: int | None


@router.get(
    "/jobs/{job_id}/logs",
    response_model=JobLogsPage,
)
async def list_job_logs(
    job_id: UUID,
    since_log_id: int = Query(
        0,
        ge=0,
        description="Return log rows with log_id > this value. 0 = from start.",
    ),
    limit: int = Query(50, ge=1, le=LOGS_MAX_LIMIT),
    user_id: UUID = Depends(get_current_user),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    logs_repo: JobLogsRepo = Depends(get_job_logs_repo),
) -> JobLogsPage:
    """K19b.8 — fetch a page of job lifecycle events.

    404 on missing or cross-user job (JWT-scoped via the router-level
    dep; explicit `jobs_repo.get` also filters on user_id for defence
    in depth). `next_cursor` only set when the page is full — callers
    should stop polling once it's null.
    """
    job = await jobs_repo.get(user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )

    logs = await logs_repo.list(
        user_id, job_id, since_log_id=since_log_id, limit=limit,
    )
    next_cursor: int | None = None
    if len(logs) == limit and logs:
        next_cursor = logs[-1].log_id
    return JobLogsPage(logs=logs, next_cursor=next_cursor)
