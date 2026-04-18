"""K16.12 — Cost tracking API.

Endpoints for viewing extraction spending and setting budget caps.
All figures are derived from extraction_jobs.cost_spent_usd and
knowledge_projects budget columns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.pool import get_knowledge_pool
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_projects_repo
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["costs"],
    dependencies=[Depends(get_current_user)],
)


# ── Response models ──────────────────────────────────────────────────


class UserCostSummary(BaseModel):
    all_time_usd: Decimal
    current_month_usd: Decimal


class ProjectCostSummary(BaseModel):
    project_id: UUID
    all_time_usd: Decimal
    current_month_usd: Decimal
    monthly_budget_usd: Decimal | None
    jobs: list[dict]


class SetBudgetRequest(BaseModel):
    monthly_budget_usd: Decimal | None = Field(default=None, ge=0)


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/costs", response_model=UserCostSummary)
async def get_user_costs(
    user_id: UUID = Depends(get_current_user),
) -> UserCostSummary:
    """Total AI spending across all projects."""
    pool = get_knowledge_pool()
    row = await pool.fetchrow(
        """
        SELECT
          COALESCE(SUM(actual_cost_usd), 0) AS all_time,
          COALESCE(SUM(
            CASE WHEN current_month_key = to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM')
                 THEN current_month_spent_usd ELSE 0 END
          ), 0) AS current_month
        FROM knowledge_projects
        WHERE user_id = $1
        """,
        user_id,
    )
    return UserCostSummary(
        all_time_usd=row["all_time"],
        current_month_usd=row["current_month"],
    )


@router.get(
    "/projects/{project_id}/costs",
    response_model=ProjectCostSummary,
)
async def get_project_costs(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> ProjectCostSummary:
    """Per-project cost breakdown by job."""
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="project not found")

    pool = get_knowledge_pool()

    # Read budget/month columns directly — these aren't on the Project
    # Pydantic model (kept out of _SELECT_COLS to avoid bloating the
    # generic repo reads). Same pattern as budget.py.
    budget_row = await pool.fetchrow(
        """
        SELECT monthly_budget_usd, current_month_spent_usd, current_month_key
        FROM knowledge_projects
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id,
    )
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    current_month = Decimal("0")
    monthly_budget = None
    if budget_row:
        monthly_budget = budget_row["monthly_budget_usd"]
        if budget_row["current_month_key"] == month_key:
            current_month = budget_row["current_month_spent_usd"] or Decimal("0")

    rows = await pool.fetch(
        """
        SELECT job_id, scope, status, cost_spent_usd, created_at
        FROM extraction_jobs
        WHERE user_id = $1 AND project_id = $2
        ORDER BY created_at DESC
        LIMIT 50
        """,
        user_id, project_id,
    )
    jobs = [
        {
            "job_id": str(r["job_id"]),
            "scope": r["scope"],
            "status": r["status"],
            "cost_usd": str(r["cost_spent_usd"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

    return ProjectCostSummary(
        project_id=project_id,
        all_time_usd=project.actual_cost_usd,
        current_month_usd=current_month,
        monthly_budget_usd=monthly_budget,
        jobs=jobs,
    )


@router.put("/projects/{project_id}/budget")
async def set_project_budget(
    project_id: UUID,
    body: SetBudgetRequest,
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> dict:
    """Set monthly budget cap for a project. NULL = unlimited."""
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="project not found")

    pool = get_knowledge_pool()
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET monthly_budget_usd = $3, updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, body.monthly_budget_usd,
    )

    return {
        "project_id": str(project_id),
        "monthly_budget_usd": str(body.monthly_budget_usd) if body.monthly_budget_usd is not None else None,
    }
