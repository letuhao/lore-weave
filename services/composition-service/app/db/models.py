"""Pydantic row models for the composition schema (§1.2).

One model per table — the shape the repos (M2) return and validate. Text fields
carry StringConstraints length caps so a repo write can't store unbounded input
(the cap is the input guard; reads tolerate existing rows). Cross-DB id fields
are plain UUIDs (no FK — §1.4, validated in app code).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

# Reusable capped-text aliases.
_Title = Annotated[str, StringConstraints(max_length=500)]
_Short = Annotated[str, StringConstraints(max_length=2000)]
_Long = Annotated[str, StringConstraints(max_length=20000)]

WorkStatus = Literal["active", "archived"]
NodeKind = Literal["arc", "chapter", "scene", "beat"]
NodeStatus = Literal["empty", "outline", "drafting", "done"]
LinkKind = Literal["setup_payoff", "custom"]
RuleScope = Literal["world", "entity", "reveal_gate"]
JobMode = Literal["cowrite", "auto"]
JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
# Only genuine-author-choice actions are corrections (§2). accept-as-is is NOT
# here — mining the reranker's own winner = self-reinforcement (review H2).
CorrectionKind = Literal["edit", "pick_different", "regenerate", "reject"]


class CompositionWork(BaseModel):
    # C16 (WG-3): `id` is the surrogate PK; `project_id` is the (now nullable)
    # knowledge-project id — null = a lazy greenfield Work whose knowledge project
    # could not be created yet (knowledge-service down/5xx) and is awaiting backfill
    # (`pending_project_backfill`). A DERIVATIVE Work keeps project_id NOT NULL
    # (C23 guard — null is greenfield-only). `id` defaults to project_id for backed
    # rows so existing project_id-keyed callers keep working unchanged.
    project_id: UUID | None = None
    user_id: UUID
    book_id: UUID
    id: UUID | None = None
    pending_project_backfill: bool = False
    active_template_id: UUID | None = None
    status: WorkStatus = "active"
    settings: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StructureTemplate(BaseModel):
    id: UUID
    owner_user_id: UUID | None = None  # NULL = global/built-in
    name: _Title
    kind: str = "generic"
    beats: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None


class NarrativeThread(BaseModel):
    """The promise/foreshadow/MICE constraint ledger row (cycle 14, §5.2/§10.2).
    ADVISORY — a flag + re-injection signal, not a hard commit gate."""

    id: UUID
    user_id: UUID
    project_id: UUID
    kind: Literal["promise", "foreshadow", "question", "mice_thread"]
    status: Literal["open", "progressing", "paid", "dropped"] = "open"
    opened_at_node: UUID | None = None
    payoff_node: UUID | None = None
    trigger: str = ""
    nesting_depth: int = 0
    priority: int = 50
    summary: str = ""
    version: int = 1
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OutlineNode(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    kind: NodeKind
    rank: Annotated[str, StringConstraints(max_length=200)]
    title: _Title = ""
    pov_entity_id: UUID | None = None
    present_entity_ids: list[UUID] = Field(default_factory=list)
    goal: _Short = ""
    beat_role: Annotated[str, StringConstraints(max_length=100)] | None = None
    status: NodeStatus = "empty"
    chapter_id: UUID | None = None
    tension: int | None = None  # 0..100
    story_order: int | None = None
    synopsis: _Long = ""
    version: int = 1
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SceneLink(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    kind: LinkKind = "setup_payoff"
    label: _Title = ""
    created_at: datetime | None = None


class CanonRule(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    text: _Long
    scope: RuleScope = "world"
    entity_id: UUID | None = None
    from_order: int | None = None
    until_order: int | None = None
    kind: Annotated[str, StringConstraints(max_length=100)] | None = None
    active: bool = True
    version: int = 1
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GenerationJob(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    outline_node_id: UUID | None = None
    operation: Annotated[str, StringConstraints(max_length=100)]
    mode: JobMode = "cowrite"
    status: JobStatus = "pending"
    llm_job_id: UUID | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    critic: dict[str, Any] | None = None
    target_chapter_id: UUID | None = None
    base_revision_id: UUID | None = None  # OI-2 accept-staleness guard
    target_revision_id: UUID | None = None
    cost_usd: Decimal = Decimal("0")
    idempotency_key: Annotated[str, StringConstraints(max_length=200)] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GenerationCorrection(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    job_id: UUID
    kind: CorrectionKind
    chosen_candidate_index: int | None = None  # required for pick_different
    guidance: _Long | None = None
    changed_blocks: int | None = None  # edit-magnitude (# differing blocks)
    # OPT-IN only (§5 `capture_correction_prose`): verbatim prose, NULL by default.
    raw_before: str | None = None
    raw_after: str | None = None
    regenerated_to_job_id: UUID | None = None  # §8.3 chain (new ≻ old)
    created_at: datetime | None = None


class ModeCorrectionStats(BaseModel):
    """Correction-rate signal for one generation mode (auto | cowrite), §6.

    `accept_rate` is the H2-safe positive signal — accept-as-is leaves no
    correction row, so it is derived (generations − corrected_jobs) / generations,
    NOT mined as a preference. `avg_edit_magnitude` reads `changed_blocks` (the
    real edit size), not a generic key-diff (D-LEARN-GEN-CHANGE-MAGNITUDE). Rates
    are None when there are no generations (cold-start)."""
    mode: str
    generations: int
    corrected_jobs: int
    accept_rate: float | None = None
    edit_rate: float | None = None
    pick_different_rate: float | None = None
    regenerate_rate: float | None = None
    reject_rate: float | None = None
    avg_edit_magnitude: float | None = None


class CorrectionStats(BaseModel):
    """Per-Work correction-rate dashboard (the V1 eval-gate, §6). Always carries
    BOTH modes (zero-filled) so the FE can show the auto-vs-cowrite A/B — within
    one Work the author is fixed, so the comparison cancels author style."""
    project_id: UUID
    by_mode: list[ModeCorrectionStats]


class OutboxEvent(BaseModel):
    id: UUID
    aggregate_type: str = "composition"
    aggregate_id: UUID
    event_type: Annotated[str, StringConstraints(max_length=100)]
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    published_at: datetime | None = None
    retry_count: int = 0
    last_error: str | None = None
