"""API request/response schemas for campaign-service (S1)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Domain vocabulary (mirrors the DB CHECK-free string columns) ──────────
GATING_MODES = {"phase_barrier", "cold_start"}
CAMPAIGN_STATUSES = {
    "created", "running", "paused", "completed", "failed", "cancelling", "cancelled",
}
# Per-(chapter, stage) projection statuses.
STAGE_STATUSES = {"pending", "dispatched", "done", "failed", "skipped"}

# budget_usd ceiling — campaigns.budget_usd is NUMERIC(16,8) (8 integer digits),
# so the value must stay below 10^8 to avoid an overflow on INSERT/UPDATE.
_BUDGET_USD_MAX = Decimal("100000000")


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
    # S5b — per-campaign VERIFIER model (V3). None = fall back to the translator.
    verifier_model_source: Optional[str] = None
    verifier_model_ref: Optional[UUID] = None
    # S5b-eval — per-campaign translation EVAL-JUDGE model. None = no per-campaign
    # judge (learning falls back to its service-wide config).
    eval_judge_model_source: Optional[str] = None
    eval_judge_model_ref: Optional[UUID] = None
    # S5b — knowledge-project model overrides applied to the project at create
    # (the project is SSOT; these are NOT persisted on the campaign). embedding
    # override on a project that already has a graph needs confirm_embedding_change
    # (destructive: deletes the stale vectors). reranker has no vector-space hazard.
    # NOTE: embedding_model_source is accepted for FE Model-Matrix symmetry but
    # IGNORED — knowledge embedding is always BYOK user_model (knowledge_projects
    # has no embedding-source column); only embedding_model_ref is applied.
    embedding_model_source: Optional[str] = None
    embedding_model_ref: Optional[UUID] = None
    rerank_model_source: Optional[str] = None
    rerank_model_ref: Optional[UUID] = None
    confirm_embedding_change: bool = False
    # Chapter range (sort_order, inclusive). None = whole book.
    chapter_from: Optional[int] = None
    chapter_to: Optional[int] = None
    # S4d: per-campaign cumulative budget cap (USD). None = uncapped. The campaign
    # auto-pauses once its summed spend reaches this (reactive).
    budget_usd: Optional[Decimal] = None

    @field_validator("gating_mode")
    @classmethod
    def _valid_gating(cls, v: str) -> str:
        if v not in GATING_MODES:
            raise ValueError(f"gating_mode must be one of {sorted(GATING_MODES)}")
        return v

    @field_validator("budget_usd")
    @classmethod
    def _valid_budget(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return v
        if v <= 0:
            raise ValueError("budget_usd must be > 0 (omit for uncapped)")
        if v >= _BUDGET_USD_MAX:
            raise ValueError("budget_usd exceeds the maximum (numeric(16,8))")
        return v


class UpdateBudgetPayload(BaseModel):
    """S4d — PATCH /campaigns/{id}: raise/lower the budget cap. Lowering below the
    current spend is allowed (bounds new work) but does NOT auto-resume a paused
    campaign — resume via /start once the budget is above spent_usd."""
    budget_usd: Decimal

    @field_validator("budget_usd")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("budget_usd must be > 0")
        if v >= _BUDGET_USD_MAX:
            raise ValueError("budget_usd exceeds the maximum (numeric(16,8))")
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
    verifier_model_source: Optional[str]
    verifier_model_ref: Optional[UUID]
    eval_judge_model_source: Optional[str]
    eval_judge_model_ref: Optional[UUID]
    chapter_from: Optional[int]
    chapter_to: Optional[int]
    budget_usd: Optional[Decimal]
    spent_usd: Decimal
    total_chapters: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class EstimateModelRef(BaseModel):
    """A per-role model pick for the cost estimate. Both None = role unset
    (that stage is skipped / not estimated)."""
    # `model_*` collides with Pydantic v2's protected namespace; allow it (these
    # field names mirror the provider-registry + FE picker contract).
    model_config = ConfigDict(protected_namespaces=())

    model_source: Optional[str] = None
    model_ref: Optional[UUID] = None


class EstimateRequest(BaseModel):
    """S5a — POST /v1/campaigns/estimate. Describes the PROPOSED campaign so the
    wizard can show a cost+time review before create/launch. Owner-scoped: the
    book is ownership-verified exactly like create. `models` maps each pipeline
    role (extractor/embedding/reranker/translator/verifier/eval_judge) to a pick."""
    book_id: UUID
    chapter_from: Optional[int] = None
    chapter_to: Optional[int] = None
    target_language: Optional[str] = None
    models: dict[str, EstimateModelRef] = Field(default_factory=dict)


class StageEstimate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    stage: str
    role: str
    model_source: Optional[str]
    model_ref: Optional[str]
    status: str          # ok | unpriced | not_found | bad_request | not_estimated
    estimated_usd: Decimal


class EstimateResponse(BaseModel):
    chapter_count: int
    currency: str
    estimated_usd_low: Decimal
    estimated_usd_high: Decimal
    estimated_minutes_low: int
    estimated_minutes_high: int
    per_stage: list[StageEstimate]
    notes: list[str]
    disclaimer: str


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
    # S5b-eval: the translation-fidelity judge's [0,1] verdict (None until judged;
    # best-effort telemetry, does not gate the eval stage).
    eval_fidelity_score: Optional[Decimal] = None


class CampaignDetail(Campaign):
    """Campaign + its per-chapter projection (the Monitor's data source)."""
    chapters: list[CampaignChapter] = []


class StageCounts(BaseModel):
    """S6 — per-stage chapter tally for the monitor's progress bars."""
    total: int
    done: int
    failed: int
    skipped: int
    in_progress: int  # total - done - failed - skipped


class CampaignProgress(BaseModel):
    """S6 — lightweight live-progress payload (O(1) vs the full chapters[]). Polled
    frequently while a campaign is active."""
    campaign_id: UUID
    status: str
    spent_usd: Decimal
    budget_usd: Optional[Decimal]
    total_chapters: int
    stages: dict[str, StageCounts]  # knowledge / translation / eval


class ErrorResponse(BaseModel):
    code: str
    message: str
