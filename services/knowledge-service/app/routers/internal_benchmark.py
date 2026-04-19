"""T2-close-1b — `/internal/projects/{id}/benchmark-status`.

Read-only endpoint that returns the latest benchmark run (or the
no-run-yet signal) for a project. Called by:
  - The K12.4 FE picker to render the benchmark badge.
  - (Future) the chat-service gateway if it ever needs to
    short-circuit Mode 3 when a benchmark regresses mid-session.

Gated by `require_internal_token` — same token surface as every
other `/internal/*` endpoint. `user_id` comes in as a query param
(trusted because the caller is another LoreWeave service that
already validated the user's JWT).

Response shape returns 200 even when no benchmark has happened —
`has_run=False` is a valid state the FE wants to render
("Run benchmark to enable extraction"), NOT an error.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.db.repositories.benchmark_runs import BenchmarkRunsRepo
from app.deps import get_benchmark_runs_repo
from app.middleware.internal_auth import require_internal_token

__all__ = ["router", "BenchmarkStatusResponse"]


router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class BenchmarkStatusResponse(BaseModel):
    """Latest benchmark run summary for the K12.4 picker.

    `has_run=False` is a real state — projects that haven't been
    benchmarked yet. Callers render a "Run benchmark" CTA for that
    state, NOT a 404 error. Everything else is None when has_run is
    False.
    """

    has_run: bool
    passed: bool | None = None
    run_id: str | None = None
    embedding_model: str | None = None
    recall_at_3: float | None = None
    mrr: float | None = None
    created_at: datetime | None = None


@router.get(
    "/{project_id}/benchmark-status",
    response_model=BenchmarkStatusResponse,
)
async def get_benchmark_status(
    project_id: UUID,
    user_id: UUID = Query(..., description="project owner"),
    embedding_model: str | None = Query(
        None, description="filter to a specific model; omit for latest-any",
    ),
    repo: BenchmarkRunsRepo = Depends(get_benchmark_runs_repo),
) -> BenchmarkStatusResponse:
    row = await repo.get_latest(user_id, project_id, embedding_model)
    if row is None:
        return BenchmarkStatusResponse(has_run=False)
    return BenchmarkStatusResponse(
        has_run=True,
        passed=row.passed,
        run_id=row.run_id,
        embedding_model=row.embedding_model,
        recall_at_3=row.recall_at_3,
        mrr=row.mrr,
        created_at=row.created_at,
    )
