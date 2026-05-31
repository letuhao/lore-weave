"""Pydantic models for the learning-service read APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Correction(BaseModel):
    """A single persisted correction (redacted projection — no raw content)."""

    id: str
    user_id: str
    project_id: str | None = None
    book_id: str | None = None
    target_type: str
    target_id: str
    op: str
    before_structural: dict[str, Any] | None = None
    after_structural: dict[str, Any] | None = None
    before_content_hash: str | None = None
    after_content_hash: str | None = None
    diff_class: str | None = None
    source_extraction_run_id: str | None = None
    source_chapter: str | None = None
    actor_type: str
    actor_id: str | None = None
    origin_service: str
    origin_event_type: str
    emitted_at: datetime | None = None
    created_at: datetime


class CorrectionPage(BaseModel):
    """Cursor-paginated page of corrections."""

    items: list[Correction]
    next_cursor: str | None = None


class CorrectionStats(BaseModel):
    """Aggregate counts feeding the future eval-gold / few-shot tiers."""

    total: int
    by_diff_class: dict[str, int]
    by_target_type: dict[str, int]


# ── Phase E2 — mining response models ────────────────────────────────


class ConfigQualityRow(BaseModel):
    genre: str | None = None
    config_hash: str
    run_count: int
    succeeded: int
    avg_entities_on_success: float | None = None
    success_rate: float | None = None


class ConfigQualityResponse(BaseModel):
    items: list[ConfigQualityRow]
    exploration: list[ConfigQualityRow]


class ModelMatrixRow(BaseModel):
    model_ref: str | None = None
    scope: str | None = None
    has_filter: bool
    run_count: int
    succeeded: int
    weighted_outcome: float | None = None


class ModelMatrixResponse(BaseModel):
    items: list[ModelMatrixRow]


class DriftRow(BaseModel):
    target: str
    base_default_version: str | None = None
    affected_projects: int
    distinct_after_values: int
    drift_pattern: str
    runs_with_outcome: int


class DefaultDriftResponse(BaseModel):
    items: list[DriftRow]


class OutcomeRecomputeRow(BaseModel):
    run_id: Any
    project_id: Any
    pipeline_outcome: str | None = None
    created_at: Any
    post_run_corrections: int
    recomputed_outcome: str | None = None


class OutcomeRecomputeResponse(BaseModel):
    items: list[OutcomeRecomputeRow]
    total: int
