"""Internal eval-gate status route (RAID C15).

Read-only ``/internal/eval/{project_id}/gate-status`` — returns the LATEST
enrichment_eval_runs row for a (project, suite_version) and the derived
P2/P3-gate signal. This is the surface C16 (fabrication) / C17 (re-cook) read to
decide whether their higher-cost tier may activate: ``p2_p3_unlocked`` is True
ONLY when the latest run for the suite passed the gate.

``has_run=False`` is a valid state (no eval yet) → the gate stays BLOCKED
(p2_p3_unlocked=False) — fail-CLOSED, never a false-green when no eval exists.

Gated by the internal service token (server-to-server), mirroring
knowledge-service ``internal_benchmark`` (the persist pattern this eval mirrors).
``user_id`` is a trusted query param (the caller is another LoreWeave service).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.config import settings
from app.db.repositories.eval_runs import EvalRunsRepo
from app.deps import get_db

__all__ = ["router", "GateStatusResponse"]


async def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Server-to-server guard. Rejects a missing/wrong token (401)."""
    if not x_internal_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal token",
        )


router = APIRouter(
    prefix="/internal/eval",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


async def get_eval_runs_repo(pool=Depends(get_db)) -> EvalRunsRepo:
    return EvalRunsRepo(pool)


class GateStatusResponse(BaseModel):
    """Latest eval-run summary + the derived P2/P3 gate signal.

    ``p2_p3_unlocked`` is the load-bearing field: True ONLY when an eval has run
    for this suite AND it passed the gate. C16/C17 must NOT activate when this is
    False. ``has_run=False`` → unlocked=False (fail-closed)."""

    has_run: bool
    p2_p3_unlocked: bool
    suite_version: str
    passed: bool | None = None
    composite: float | None = None
    fleiss_kappa: float | None = None
    judge_ensemble_acceptable: bool | None = None
    run_id: str | None = None
    created_at: datetime | None = None


@router.get("/{project_id}/gate-status", response_model=GateStatusResponse)
async def gate_status(
    project_id: UUID,
    user_id: UUID = Query(..., description="project owner"),
    suite_version: str = Query("enrichment-v1"),
    repo: EvalRunsRepo = Depends(get_eval_runs_repo),
) -> GateStatusResponse:
    row = await repo.get_latest(
        user_id=user_id, project_id=project_id, suite_version=suite_version
    )
    if row is None:
        # No eval yet → gate stays BLOCKED (fail-closed).
        return GateStatusResponse(
            has_run=False, p2_p3_unlocked=False, suite_version=suite_version
        )
    return GateStatusResponse(
        has_run=True,
        p2_p3_unlocked=bool(row.passed),
        suite_version=row.suite_version,
        passed=row.passed,
        composite=row.composite,
        fleiss_kappa=row.fleiss_kappa,
        judge_ensemble_acceptable=row.judge_ensemble_acceptable,
        run_id=row.run_id,
        created_at=row.created_at,
    )
