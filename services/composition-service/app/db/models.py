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
# T3.4 — the addressable grounding item types (those with stable source ids)
# + the per-scene steering action. T3.6 added 'reference' (id = reference_source.id).
GroundingItemType = Literal["present", "canon", "lore", "reference"]
PinAction = Literal["pin", "exclude"]
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
    # C23 (dị bản M0): a DERIVATIVE Work points at the SOURCE Work it diverges from
    # (in-DB self-ref on the surrogate id) at a chapter-level `branch_point` (G3).
    # Both are NULL for a non-derivative (greenfield) Work. A derivative keeps
    # project_id NOT NULL (G2 — its own delta partition; DB CHECK enforces it).
    source_work_id: UUID | None = None
    branch_point: int | None = None
    active_template_id: UUID | None = None
    status: WorkStatus = "active"
    settings: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


DivergenceTaxonomy = Literal["pov_shift", "character_transform", "au"]


class DivergenceSpec(BaseModel):
    """C23 (dị bản M0): the delta declaration for a derivative Work. The taxonomy
    (POV shift · character transform · AU — UX §7.1) reduces to `taxonomy` +
    optional `pov_anchor` + added `canon_rule[]` (M0 override scope = entity fields
    + added canon rules). `project_id` = the derivative's own project."""

    id: UUID | None = None
    user_id: UUID
    project_id: UUID
    work_id: UUID
    taxonomy: DivergenceTaxonomy = "au"
    pov_anchor: UUID | None = None
    canon_rule: list[_Long] = Field(default_factory=list)
    created_at: datetime | None = None


class EntityOverride(BaseModel):
    """C23 (dị bản M0): a per-derivative entity-FIELD override (relationship/event
    overrides DEFERRED). `target_entity_id` = the overridden entity (cross-DB id);
    `overridden_fields` = the field→value JSON delta. PERSISTED here; the packer
    applies it at retrieval in C25 (this cycle persists only)."""

    id: UUID | None = None
    user_id: UUID
    project_id: UUID
    work_id: UUID
    target_entity_id: UUID
    overridden_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


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


class SceneGroundingPin(BaseModel):
    """T3.4 — a per-scene author steering row over one addressable grounding item.
    `item_id` is a STABLE canonical id (glossary anchor / canon_rule uuid / lore
    source_id), never a localized label, so the pin survives a reader-language
    switch or a derivative override."""
    id: UUID
    user_id: UUID
    project_id: UUID
    outline_node_id: UUID
    item_type: GroundingItemType
    item_id: Annotated[str, StringConstraints(max_length=200)]
    action: PinAction
    created_at: datetime | None = None


class ReferenceSource(BaseModel):
    """T3.6 — one author-curated reference passage (an external influence) for a
    Work. composition-owned: `content` is embedded via provider-registry and the
    vector is stored in `embedding` (a plain float list — brute-force cosine top-K
    at search time). All of a Work's references share ONE embedding model. The
    `embedding` is omitted from the list/search projection (the vector stays on the
    server); a row with a null embedding is never a search hit."""
    id: UUID
    user_id: UUID
    project_id: UUID
    title: _Title = ""
    author: _Title = ""
    source_url: _Title = ""
    content: _Long
    embedding_model: _Title = ""
    embedding_dim: int | None = None
    created_at: datetime | None = None


StyleScope = Literal["work", "chapter", "scene"]


class StyleProfile(BaseModel):
    """T3.5 — per-scope prose-style steering. `scope_id` is the project_id (work),
    chapter_id (chapter) or outline node_id (scene). Density/Pace are 0-100; the
    packer resolves the most-specific row for a scene and maps them to prose-style
    directives in the draft prompts."""
    user_id: UUID
    project_id: UUID
    scope_type: StyleScope
    scope_id: UUID
    density: Annotated[int, Field(ge=0, le=100)]
    pace: Annotated[int, Field(ge=0, le=100)]
    updated_at: datetime | None = None


class VoiceProfile(BaseModel):
    """T3.5 — per-character voice tags. Keyed by `entity_id`; `entity_name` is
    denormalized for prompt rendering. Injected only when the entity is present in
    the scene."""
    user_id: UUID
    project_id: UUID
    entity_id: UUID
    entity_name: str
    tags: list[str] = []
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


# ════════════════════════════════════════════════════════════════════════════
# NARRATIVE MOTIF LIBRARY (F0 — spec §R1.4 + 00-RECONCILE §1). 2-tier tenancy
# (system = owner NULL | user = owner set). Row models are the read shape (the
# `embedding` vector is NEVER projected — it stays server-side, reference_source
# precedent); the *Args models are the write shape and forbid extra keys (audit
# S2 — the LLM/router cannot smuggle owner_user_id or an embedding-model choice).
# ════════════════════════════════════════════════════════════════════════════

# ── enums (type aliases)
MotifKind = Literal["sequence", "situation", "hook", "emotion_arc", "trope", "pattern", "scheme"]
MotifSource = Literal["authored", "mined", "adopted", "imported"]
MotifVisibility = Literal["private", "unlisted", "public"]
MotifStatus = Literal["draft", "active", "archived"]
MotifLinkKind = Literal["composed_of", "precedes", "variant_of"]
Actant = Literal["subject", "object", "sender", "receiver", "helper", "opponent"]
ArcSource = Literal["authored", "mined", "imported"]
_Code = Annotated[str, StringConstraints(max_length=200)]
_Lang = Annotated[str, StringConstraints(max_length=20)]
_Key = Annotated[str, StringConstraints(max_length=100)]


class _ForbidExtra(BaseModel):
    """Base for write-arg models — extra='forbid' is the S2 guard so a caller (the
    LLM/router/MCP tool) cannot smuggle `owner_user_id` or an embedding-model choice
    onto a write. Mirrors loreweave_mcp.ForbidExtra; a local alias so non-MCP
    callers/routers share it."""

    model_config = {"extra": "forbid"}


# ── sub-shapes (validated JSONB members on write)
class MotifRole(BaseModel):
    key: _Key
    actant: Actant
    label: _Title = ""
    constraints: list[_Short] = Field(default_factory=list)


class MotifBeat(BaseModel):
    key: _Key
    label: _Title = ""
    intent: _Short = ""
    tension_target: int | None = None             # 1..5
    order: int = 0
    reversal: dict[str, Any] | None = None         # §15.2 {thread, from, to}
    alliance_shift: dict[str, Any] | None = None   # §15.2 {a, b, from, to}


class InfoAsymmetry(BaseModel):
    knows: list[str] = Field(default_factory=list)
    deceived: list[str] = Field(default_factory=list)
    gap: _Long = ""


# ── row models (the repo return shape; embedding is NEVER projected)
class Motif(BaseModel):
    id: UUID
    owner_user_id: UUID | None = None              # NULL = system tier
    code: _Code
    language: _Lang = "en"
    visibility: MotifVisibility = "private"
    kind: MotifKind = "sequence"
    category: _Code | None = None
    name: _Title
    summary: _Long = ""
    genre_tags: list[_Key] = Field(default_factory=list)
    roles: list[dict[str, Any]] = Field(default_factory=list)         # validated via MotifRole on write
    beats: list[dict[str, Any]] = Field(default_factory=list)         # validated via MotifBeat on write
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    info_asymmetry: dict[str, Any] | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)         # RECONCILE D1 — template-level scheme props
    tension_target: int | None = None
    emotion_target: Annotated[str, StringConstraints(max_length=100)] | None = None
    examples: list[dict[str, Any]] = Field(default_factory=list)
    abstraction_confidence: Literal["high", "med", "low"] | None = None
    source: MotifSource = "authored"
    imported_derived: bool = False                 # B-3 lineage taint (clone propagates; trigger reads)
    source_ref: _Short | None = None
    source_version: int | None = None
    embedding_model: _Title = ""                   # the vector itself is omitted from the projection
    embedding_dim: int | None = None
    judge_score: Decimal | None = None
    mining_support: int | None = None
    status: MotifStatus = "active"
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MotifLink(BaseModel):
    id: UUID
    from_motif_id: UUID
    to_motif_id: UUID
    kind: MotifLinkKind
    ord: int | None = None
    created_at: datetime | None = None


class MotifApplication(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    book_id: UUID
    motif_id: UUID | None = None                   # SET NULL if the motif is archived
    motif_version: int | None = None
    outline_node_id: UUID | None = None
    role_bindings: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ArcPlacement(BaseModel):                     # one layout[] entry
    motif_code: _Code
    motif_id: UUID | None = None                   # resolved id (R1.4)
    thread: _Key
    span_start: int
    span_end: int
    ord: int = 0
    role_hints: dict[str, Any] = Field(default_factory=dict)
    triggers: list[str] = Field(default_factory=list)   # §15.3 other-placement ids


class ArcTemplate(BaseModel):
    id: UUID
    owner_user_id: UUID | None = None
    code: _Code
    language: _Lang = "en"
    visibility: MotifVisibility = "private"
    name: _Title
    summary: _Long = ""
    genre_tags: list[_Key] = Field(default_factory=list)
    chapter_span: int | None = None
    threads: list[dict[str, Any]] = Field(default_factory=list)
    layout: list[dict[str, Any]] = Field(default_factory=list)
    pacing: list[dict[str, Any]] = Field(default_factory=list)
    arc_roster: list[dict[str, Any]] = Field(default_factory=list)
    source: ArcSource = "authored"
    source_ref: _Short | None = None
    source_version: int | None = None
    embedding_model: _Title = ""
    embedding_dim: int | None = None
    status: MotifStatus = "active"
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImportSource(BaseModel):
    id: UUID
    owner_user_id: UUID
    project_id: UUID | None = None
    title: _Title = ""
    content: _Long
    created_at: datetime | None = None


# ── retrieval result (the FROZEN contract W3 produces / W2 + the MCP suggest consume)
class MotifCandidate(BaseModel):
    motif: Motif
    score: float
    match_reason: dict[str, Any] = Field(default_factory=dict)   # {tension, genre, precond, cosine}


# ── WRITE-ARG models (ForbidExtra — owner is NEVER an arg; the repo stamps it; there
# is NO embedding-model arg — the model is platform config, never a write choice, B-1)
class MotifCreateArgs(_ForbidExtra):
    code: _Code
    name: _Title
    language: _Lang = "en"
    kind: MotifKind = "sequence"
    category: _Code | None = None
    summary: _Long = ""
    genre_tags: list[_Key] = Field(default_factory=list)
    roles: list[MotifRole] = Field(default_factory=list)
    beats: list[MotifBeat] = Field(default_factory=list)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    info_asymmetry: InfoAsymmetry | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)   # RECONCILE D1
    tension_target: Annotated[int, Field(ge=1, le=5)] | None = None
    emotion_target: Annotated[str, StringConstraints(max_length=100)] | None = None
    examples: list[dict[str, Any]] = Field(default_factory=list)
    visibility: MotifVisibility = "private"            # public/unlisted allowed at create; system is migrate-only


class MotifPatchArgs(_ForbidExtra):
    # every field optional (PATCH semantics); owner/code/language/source are NOT
    # patchable here (identity/lineage are immutable post-create — clone to re-key).
    name: _Title | None = None
    kind: MotifKind | None = None
    category: _Code | None = None
    summary: _Long | None = None
    genre_tags: list[_Key] | None = None
    roles: list[MotifRole] | None = None
    beats: list[MotifBeat] | None = None
    preconditions: list[dict[str, Any]] | None = None
    effects: list[dict[str, Any]] | None = None
    info_asymmetry: InfoAsymmetry | None = None
    annotations: dict[str, Any] | None = None          # RECONCILE D1
    tension_target: Annotated[int, Field(ge=1, le=5)] | None = None
    emotion_target: Annotated[str, StringConstraints(max_length=100)] | None = None
    examples: list[dict[str, Any]] | None = None
    visibility: MotifVisibility | None = None
    status: MotifStatus | None = None


# ── ARC-TEMPLATE write-arg models (W10) — mirror the motif Create/Patch shape.
# owner is NEVER an arg (the repo stamps it = caller); embedding-model is platform
# config, never a write choice (B-1). The JSONB members (threads/layout/pacing/
# arc_roster) are validated by their sub-shapes on write.
class ArcThread(BaseModel):
    key: _Key
    label: _Title = ""


class ArcRosterEntry(BaseModel):                   # one arc_roster[] entry (§12.2)
    key: _Key                                      # the arc-level role slot (e.g. 'protagonist')
    actant: Actant | None = None
    label: _Title = ""
    constraints: list[_Short] = Field(default_factory=list)


class ArcTemplateCreateArgs(_ForbidExtra):
    code: _Code
    name: _Title
    language: _Lang = "en"
    summary: _Long = ""
    genre_tags: list[_Key] = Field(default_factory=list)
    chapter_span: Annotated[int, Field(ge=1)] | None = None
    threads: list[ArcThread] = Field(default_factory=list)
    layout: list[ArcPlacement] = Field(default_factory=list)
    pacing: list[dict[str, Any]] = Field(default_factory=list)
    arc_roster: list[ArcRosterEntry] = Field(default_factory=list)
    visibility: MotifVisibility = "private"         # public/unlisted allowed at create; system is migrate-only


class ArcTemplatePatchArgs(_ForbidExtra):
    # every field optional (PATCH semantics); owner/code/language/source are NOT
    # patchable (identity/lineage are immutable post-create — clone to re-key).
    name: _Title | None = None
    summary: _Long | None = None
    genre_tags: list[_Key] | None = None
    chapter_span: Annotated[int, Field(ge=1)] | None = None
    threads: list[ArcThread] | None = None
    layout: list[ArcPlacement] | None = None
    pacing: list[dict[str, Any]] | None = None
    arc_roster: list[ArcRosterEntry] | None = None
    visibility: MotifVisibility | None = None
    status: MotifStatus | None = None


# ── ARC APPLY (W10) — the PURE/deterministic placement-rescale contract (§12.5).
# apply = decompose at arc scale: reconcile chapter_span→target, bind arc_roster
# ONCE, place motifs across the target chapters, interleave per thread, and surface
# a drop/merge report (§12.6 — NEVER silent). NO LLM/DB here; the deep planner
# materialization (outline_node rows) is the W10 live-smoke follow-up.
class ArcApplyArgs(_ForbidExtra):
    target_chapters: Annotated[int, Field(ge=1, le=2000)]
    # role binding: arc_roster role-key → the new book's concrete cast id/name
    # (bound ONCE for the whole arc, propagated to every placement). ForbidExtra
    # keeps the LLM/caller from smuggling ownership ids onto the apply.
    roster_bindings: dict[str, Any] = Field(default_factory=dict)


class ResolvedPlacement(BaseModel):                # one rescaled placement in the plan
    motif_code: _Code
    motif_id: UUID | None = None
    thread: _Key
    ord: int = 0
    src_span_start: int                            # the template's original span (audit)
    src_span_end: int
    span_start: int                                # rescaled into [1..target_chapters]
    span_end: int
    role_hints: dict[str, Any] = Field(default_factory=dict)
    role_bindings: dict[str, Any] = Field(default_factory=dict)   # arc_roster propagated
    triggers: list[str] = Field(default_factory=list)
    merged_codes: list[str] = Field(default_factory=list)         # other placements folded in (§12.6)


class DropMergeEntry(BaseModel):                   # one §12.6 reconciliation event — never silent
    kind: Literal["dropped", "merged"]
    motif_code: _Code
    thread: _Key
    src_span_start: int
    src_span_end: int
    into_motif_code: _Code | None = None           # the survivor a merge folded into
    reason: _Short = ""


class ArcApplyPlan(BaseModel):                      # the apply-preview result (router returns this)
    arc_template_id: UUID
    source_chapter_span: int                        # the span the rescale ran from
    target_chapters: int
    threads: list[dict[str, Any]] = Field(default_factory=list)
    placements: list[ResolvedPlacement] = Field(default_factory=list)
    roster_bindings: dict[str, Any] = Field(default_factory=dict)   # bound ONCE (§12.5)
    unbound_roster_keys: list[str] = Field(default_factory=list)    # roster slots with no binding supplied
    drop_merge_report: list[DropMergeEntry] = Field(default_factory=list)
    # per-chapter interleave: chapter_no (1-based) → [placement ords active there]
    chapter_interleave: dict[str, list[int]] = Field(default_factory=dict)
