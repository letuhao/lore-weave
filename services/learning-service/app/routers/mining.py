"""Phase E2 — config data-mining read API.

Four endpoints under /v1/learning/mining/:
  GET /config-quality     — genre × config success rate + explore fraction
  GET /model-matrix       — model_ref × task weighted outcome
  GET /default-drift      — convergent vs divergent param changes
  GET /outcome-recompute  — correction-join recipe (empty at cold-start)

Strict per-owner isolation: every endpoint filters on user_id from JWT.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.db.mining import (
    get_config_quality,
    get_default_drift,
    get_model_matrix,
    get_outcome_recompute,
)
from app.deps import get_current_user, get_db
from app.models import (
    ConfigQualityResponse,
    DefaultDriftResponse,
    ModelMatrixResponse,
    OutcomeRecomputeResponse,
)

router = APIRouter(prefix="/v1/learning/mining", tags=["learning-mining"])


@router.get("/config-quality", response_model=ConfigQualityResponse)
async def config_quality(
    genre: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    exploration_fraction: float = Query(default=0.1, ge=0.0, le=0.5),
    segment_power_users: bool = Query(default=False),
    power_user_threshold: int = Query(default=10, ge=1, le=1000),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ConfigQualityResponse:
    result = await get_config_quality(
        pool,
        user_id=UUID(user_id),
        genre=genre,
        limit=limit,
        exploration_fraction=exploration_fraction,
        segment_power_users=segment_power_users,
        power_user_threshold=power_user_threshold,
    )
    return ConfigQualityResponse(**result)


@router.get("/model-matrix", response_model=ModelMatrixResponse)
async def model_matrix(
    scope: str | None = Query(default=None),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ModelMatrixResponse:
    items = await get_model_matrix(pool, user_id=UUID(user_id), scope=scope)
    return ModelMatrixResponse(items=items)


@router.get("/default-drift", response_model=DefaultDriftResponse)
async def default_drift(
    target: str | None = Query(default=None),
    base_default_version: str | None = Query(default=None),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> DefaultDriftResponse:
    items = await get_default_drift(
        pool,
        user_id=UUID(user_id),
        target=target,
        base_default_version=base_default_version,
    )
    return DefaultDriftResponse(items=items)


@router.get("/outcome-recompute", response_model=OutcomeRecomputeResponse)
async def outcome_recompute(
    project_id: UUID | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> OutcomeRecomputeResponse:
    result = await get_outcome_recompute(
        pool,
        user_id=UUID(user_id),
        project_id=project_id,
        window_days=window_days,
        limit=limit,
        offset=offset,
    )
    return OutcomeRecomputeResponse(**result)
