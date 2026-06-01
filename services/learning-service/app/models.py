"""Pydantic models for the learning-service read APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


# ── Q2 — gold-label projection (corrections as preference triples) ───


class GoldLabelRow(BaseModel):
    """One correction projected as a gold-label triple: the user's ``preferred``
    output over the extractor's ``non_preferred`` original (structural + hash
    only — redact-by-default)."""

    target_type: str
    target_id: str
    op: str
    diff_class: str | None = None
    non_preferred: dict[str, Any] | None = None  # extractor's original output
    preferred: dict[str, Any] | None = None       # the user's correction (gold)
    before_content_hash: str | None = None
    after_content_hash: str | None = None
    change_magnitude: int
    source_chapter: str | None = None
    source_extraction_run_id: str | None = None
    origin_service: str
    created_at: datetime


class GoldLabelsResponse(BaseModel):
    items: list[GoldLabelRow]
    total: int


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


# ── Q1 — quality-plane eval-run read models ──────────────────────────


class EvalRunRow(BaseModel):
    """One scored eval run (the metric-of-record + panel composition)."""

    eval_run_id: str
    user_id: str
    project_id: str | None = None
    book_id: str | None = None
    source_extraction_run_id: str | None = None
    config_hash: str | None = None
    dataset_version: str | None = None
    source: str
    judges: list[dict[str, Any]] = Field(default_factory=list)
    disjoint_median_f1: float | None = None
    full_panel_median_f1: float | None = None
    fleiss_kappa: float | None = None
    bootstrap_ci: dict[str, Any] | None = None
    bias_metrics: dict[str, Any] | None = None
    n_chapters: int | None = None
    n_disjoint_judges: int | None = None
    created_at: datetime


class EvalRunList(BaseModel):
    items: list[EvalRunRow]


class EvalResultRow(BaseModel):
    category: str
    judge_label: str | None = None
    judge_uuid: str | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    chapter_ref: str | None = None


class EvalRunDetail(EvalRunRow):
    results: list[EvalResultRow] = Field(default_factory=list)
