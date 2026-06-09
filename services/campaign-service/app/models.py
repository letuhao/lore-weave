"""API request/response schemas for campaign-service (S1)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ── Domain vocabulary (mirrors the DB CHECK-free string columns) ──────────
GATING_MODES = {"phase_barrier", "cold_start"}
CAMPAIGN_STATUSES = {
    "created", "running", "paused", "completed", "failed", "cancelling", "cancelled",
}
# Per-(chapter, stage) projection statuses.
STAGE_STATUSES = {"pending", "dispatched", "done", "failed", "skipped"}


class CreateCampaignPayload(BaseModel):
    book_id: UUID
    name: str = Field(min_length=1, max_length=200)
    gating_mode: str = "phase_barrier"
    target_language: Optional[str] = None
    knowledge_project_id: Optional[UUID] = None
    knowledge_model_source: Optional[str] = None
    knowledge_model_ref: Optional[UUID] = None
    translation_model_source: Optional[str] = None
    translation_model_ref: Optional[UUID] = None
    # Chapter range (sort_order, inclusive). None = whole book.
    chapter_from: Optional[int] = None
    chapter_to: Optional[int] = None

    @field_validator("gating_mode")
    @classmethod
    def _valid_gating(cls, v: str) -> str:
        if v not in GATING_MODES:
            raise ValueError(f"gating_mode must be one of {sorted(GATING_MODES)}")
        return v


class Campaign(BaseModel):
    campaign_id: UUID
    owner_user_id: UUID
    book_id: UUID
    name: str
    status: str
    gating_mode: str
    stages: list[str]
    target_language: Optional[str]
    knowledge_project_id: Optional[UUID]
    knowledge_model_source: Optional[str]
    knowledge_model_ref: Optional[UUID]
    translation_model_source: Optional[str]
    translation_model_ref: Optional[UUID]
    chapter_from: Optional[int]
    chapter_to: Optional[int]
    total_chapters: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class CampaignChapter(BaseModel):
    chapter_id: UUID
    chapter_sort: int
    ingest_status: str
    knowledge_status: str
    translation_status: str
    eval_status: str
    knowledge_attempts: int
    translation_attempts: int
    last_error: Optional[str]


class CampaignDetail(Campaign):
    """Campaign + its per-chapter projection (the Monitor's data source)."""
    chapters: list[CampaignChapter] = []


class ErrorResponse(BaseModel):
    code: str
    message: str
