"""Pydantic row models for the composition schema (§1.2).

One model per table — the shape the repos (M2) return and validate. Text fields
carry StringConstraints length caps so a repo write can't store unbounded input
(the cap is the input guard; reads tolerate existing rows). Cross-DB id fields
are plain UUIDs (no FK — §1.4, validated in app code).

BOOK-PACKAGE RE-KEY (spec 25 M3 / BPS-1; PM-5/PM-14 anti-revert): on the package
tables the actor column is `created_by` — a plain STAMP (who did it: spend/audit
attribution under BYOK), STORED but NEVER a scope key and NEVER filtered on.
`project_id` is the Work PARTITION key and `book_id` is the TENANCY scope key;
access is decided BEFORE the repo at the E0 book-grant gate. Do NOT re-introduce a
per-user `user_id` field here or an actor predicate in a query — that reverts the
re-key. Each model's fields mirror exactly what its repo's `_SELECT_COLS` project:
a model carries `book_id` only where the repo actually selects it (OutlineNode,
GenerationJob, MotifApplication, CompositionWork, Motif) — the other package
tables store book_id but their repos don't project it, so the model omits it. The
deps/ registry (StructureTemplate, Motif, ArcTemplate) and outside-the-package
tables (ImportSource, daily-progress) keep `owner_user_id` BY DESIGN (PM-16).
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
    project_id: UUID  # Work partition key (PM-3)
    book_id: UUID     # tenancy scope key (25 M1/M2); the E0 book gate resolves on this
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
    # 23 BA2/BA12 — the arc a CHAPTER node is assigned to (structure_node.id). NULL on
    # scenes (the outline_structure_kind CHECK forbids a scene from carrying one). The
    # packer reads it to inject the resolved arc frame into the draft prompt (BA12).
    structure_node_id: UUID | None = None
    # 22 SC4 — authored scene intent (the eight fields). Written via the MCP create/update
    # args (B3) + _UPDATABLE_COLUMNS (B2); read back here so create/get/list ECHO the intent
    # and the scene-inspector (22-C) can render it (else the fields are write-only). conflict/
    # outcome/stakes are NOT NULL DEFAULT ''; the rest are nullable. exit_state is the SC12
    # {v:1,…} envelope (stored JSONB; surfaced as a dict).
    location_entity_id: UUID | None = None
    story_time: str | None = None
    conflict: str = ""
    outcome: str = ""
    value_shift: int | None = None      # -100..100
    stakes: str = ""
    target_words: int | None = None     # > 0
    exit_state: dict[str, Any] | None = None
    # ── SC11 amendment — the WRITTEN VERDICT (Phase 1). NOT authored: MAINTAINED. ──
    # "Is there prose behind this spec node?" reconciled from book-service's
    # `scenes.source_scene_id` (the sole authored anchor — DA-3 still holds, this is its
    # regenerable inverse). Distinct from `status`, which is the AUTHOR'S INTENT: PH16 locks a
    # two-chip desired-vs-actual header, and fusing them would mean marking a scene 'done' makes
    # an UNWRITTEN scene render as written.
    # `written_chapter_id` is WHICH CHAPTER'S PROSE backs it — NOT the node's own `chapter_id`.
    # They come apart (a copied anchor; a planned node has chapter_id NULL), and a reconcile keyed
    # on the wrong one either flaps forever or can never clear.
    written_scene_id: UUID | None = None
    written_chapter_id: UUID | None = None
    written_at: datetime | None = None
    # 26 IX-11 — provenance: 'authored' (human) · 'decompiled' (import) · 'planforge'.
    # The inspector/Hub render a "mined" badge; the decompiler never overwrites 'authored'.
    source: str = "authored"
    version: int = 1
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Non-archived direct-child count — populated ONLY by list_children (the lazy-tree
    # navigator uses it for the sidebar badge: a chapter's scene count, an arc's chapter
    # count). None (not 0) on every other query, so a consumer can tell "not computed" from
    # "genuinely childless" (the field is absent from _SELECT_COLS → default None).
    child_count: int | None = None


StructureNodeKind = Literal["saga", "arc"]


class StructureNode(BaseModel):
    """23 A3 — the durable spec layer (`structure_node`): the saga→arc→sub-arc
    tree. Per-book (BA8: `book_id` is the SCOPE key, set directly — NO
    composition_work join, NO project_id, NO user_id). `depth` (0..2) is
    trigger-maintained; `parent_id` nesting is guarded by
    `structure_node_depth_guard` (depth<=2 · no cycle · same book). `tracks`/
    `roster` resolve root→leaf shadowed by `key`; `roster_bindings` by `role_key`
    (StructureRepo.resolve_*). Provenance (`arc_template_id`/`template_version`)
    is nullable — an arc authored from conversation has none (BA13).

    `created_by` (23-A3) is the arc's author — a stored actor stamp, never a scope
    key/filter (PM-5/DA-11), nullable (a pre-A3 arc has no recorded author). Fields
    mirror the shipped columns exactly.
    """

    id: UUID
    book_id: UUID
    created_by: UUID | None = None  # 23-A3 actor stamp — stored, never a scope key (PM-5/DA-11)
    parent_id: UUID | None = None
    kind: StructureNodeKind
    depth: int = 0
    rank: Annotated[str, StringConstraints(max_length=200)]
    title: _Title = ""
    summary: _Long = ""
    goal: _Short = ""
    status: NodeStatus = "outline"
    tracks: list[dict[str, Any]] = Field(default_factory=list)          # [{key,label}]
    roster: list[dict[str, Any]] = Field(default_factory=list)          # [{key,actant,label,constraints[]}]
    roster_bindings: dict[str, Any] = Field(default_factory=dict)       # {role_key: glossary_entity_id}
    arc_template_id: UUID | None = None
    template_version: int | None = None
    version: int = 1
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


# 22 SC12/BPS-12 — provenance of an exit_state write: 'generator' (the drafting
# seam emitted it) vs 'author' (a human corrected it — a regeneration must never
# silently discard an author's correction).
ExitStateSource = Literal["generator", "author"]


class SceneExitState(BaseModel):
    """22 SC12 — the versioned `{v:1,…}` envelope stored in `outline_node.exit_state`.

    Typed JSONB validated on write — never a free-form blob (an unvalidated JSONB
    column becomes a schema nobody owns; the versioned envelope makes the next
    migration possible). Mirrors the cross-chapter ChapterExitState delta
    (engine/plan.py) pushed down to scene granularity: three typed buckets
    (Character / World / Plot) as compact strings + the NEW-developments list.
    extra='forbid' keeps a caller (LLM/router) from smuggling unversioned keys.
    """

    model_config = {"extra": "forbid"}

    v: Literal[1] = 1
    source: ExitStateSource = "generator"
    characters: _Short = ""  # per-entity emotion/goal/relationship/power at scene end
    world: _Short = ""       # location + time at scene end
    plot: _Short = ""        # open threads / secrets / what's now revealed
    advances: list[_Short] = Field(default_factory=list)  # NEW developments (anti-repeat signal)


class SceneLink(BaseModel):
    id: UUID
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
    project_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    kind: LinkKind = "setup_payoff"
    label: _Title = ""
    created_at: datetime | None = None


class CanonRule(BaseModel):
    id: UUID
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
    project_id: UUID
    entity_id: UUID
    entity_name: str
    tags: list[str] = []
    updated_at: datetime | None = None


class GenerationJob(BaseModel):
    id: UUID
    created_by: UUID  # 25 M3 actor stamp — BYOK spend attribution (25 T5); never a filter
    # BE-7c: NULL only for an OWNER-scoped, Work-LESS job (a corpus/book motif-mine or an
    # arc-import — there is no composition_work to derive a book from). For those rows
    # `created_by` IS the scope key, and the read MUST gate on it (GET /motif-jobs/{id}).
    # Both-or-neither is enforced by the DB (CHECK generation_job_scope_shape).
    project_id: UUID | None = None  # Work partition key (PM-3)
    book_id: UUID | None = None     # tenancy scope key (25 M1/M2); the E0 book gate resolves on this
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
    created_by: UUID  # 25 M3 actor stamp (the corrector) — stored, never a filter (PM-5)
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
    book_id: UUID | None = None                    # per-book label (D-MOTIF-ADOPT-PER-BOOK); NULL = global/system. Owner's full dump only — NOT in the public/non-owner projections.
    book_shared: bool = False                      # D-MOTIF-ADOPT-BOOK-COLLAB-TIER (model B): true = the book's SHARED tier (book-grant gated). Owner full dump only — never on the public catalog allow-list.
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
    created_by: UUID  # 25 M3 actor stamp — stored, never a scope key / filter (PM-5)
    project_id: UUID
    book_id: UUID
    motif_id: UUID | None = None                   # SET NULL if the motif is archived
    motif_version: int | None = None
    outline_node_id: UUID | None = None
    structure_node_id: UUID | None = None          # BA5: the realized layout's arc (23-A1
    #     added the column; arc_apply writes it first-class so arc conformance can read
    #     `WHERE structure_node_id = $arc` instead of the legacy annotations bridge)
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
    imported_derived: bool = False                 # B-3 lineage taint (clone propagates; trigger reads)
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


# 27 V2-A1: `planned` = the passes are staged but not yet compiled into a package.
# These MIRROR `plan_run_status_chk` / `plan_artifact_kind_chk` in migrate.py. A value the
# DB accepts but this Literal rejects is a silent 422 on a legal row; a value this accepts
# but the DB rejects is a 500 on write. Change one, change both — there is no gate that
# would catch the drift for you.
PlanRunStatus = Literal[
    "pending", "proposed", "checkpoint", "validated", "compiled", "failed", "planned",
]
PlanRunMode = Literal["rules", "llm"]

# The seven compiler passes (PF-1). The `pass_state` ledger is keyed by these, and the order here IS
# the dependency order — `pass_cursor` walks it.
#
# This IS the closed set, and it is enforced on every surface that takes a pass id — the HTTP route
# (`pass_id: PlanPassId` in the path ⇒ 422 on anything else) and the MCP tools (the `Literal`
# annotation is the schema, so the enum reaches the agent). The Literal is the single source: there
# is no second list to drift from it.
#
# These names are the SPEC's (27 §170), not a paraphrase: `motifs` not `motif`, `beats` not `beat`,
# `character_arcs` not `char_arc`, `self_heal` not `heal`. A closed-set arg whose values drift from
# the spec is the Frontend-Tool-Contract bug class — an agent passes the documented value and the
# server 422s, or worse, silently no-ops. (`link` is NOT a pass: it is a step, and its artifact is
# `link_report`.)
PlanPassId = Literal[
    "motifs", "cast", "world", "beats", "character_arcs", "scenes", "self_heal",
]
PASS_ORDER: tuple[str, ...] = (
    "motifs", "cast", "world", "beats", "character_arcs", "scenes", "self_heal",
)

PlanArtifactKind = Literal[
    # v1 — still writable (a CHECK re-add that drops a historical value makes existing rows
    # unwritable; the same rule applies to the model that mirrors it).
    "document", "analyze", "spec", "graph", "package", "llm_io", "validation_report",
    # v2 — one artifact kind per pass, plus the two reports (27 V2-A1).
    "motif_plan", "cast_plan", "world_plan", "beat_plan", "char_arc_plan", "scene_plan",
    "heal_report", "link_report",
    # close-21-28 P-O1a — the rules-mode pre-flight collision report.
    "preflight",
]

PassStatus = Literal["pending", "running", "completed", "failed"]
PassDecision = Literal["pending", "accepted", "rejected", "auto"]


class PassEntry(BaseModel):
    """One `pass_state` entry (27 V2-A1). Keyed by `pass_id` on `PlanRun.pass_state`.

    NOTE what is NOT here: `fresh`/`stale`, `pass_cursor`, `blocked_at`. Those are DERIVED at
    serialization from `input_fingerprint` vs the run's current inputs, and storing them would
    make them a second source of truth that goes stale the instant an input changes — which is
    the entire reason PF-3 keys freshness on a fingerprint rather than a flag.
    """

    status: PassStatus = "pending"
    decision: PassDecision = "pending"
    artifact_id: UUID | None = None
    job_id: UUID | None = None
    input_fingerprint: str | None = None
    # The params this pass RAN with. STORED, because freshness recomputes the fingerprint and must
    # use the same params — a derivation that took them from the caller would recompute with `None`
    # (derive_view has no params to pass) and every param-carrying pass would read as permanently
    # stale, blocking everything downstream.
    params: dict[str, Any] = Field(default_factory=dict)
    # passes 2/3 only (PF-7) — the glossary seed proposal this pass is waiting on.
    bootstrap_proposal_id: UUID | None = None
    decided_by: Literal["user", "auto"] | None = None
    decided_at: datetime | None = None


class PlanRun(BaseModel):
    id: UUID
    created_by: UUID  # 25 M3 actor stamp (was owner_user_id) — stored, never a filter (PM-5)
    book_id: UUID
    work_id: UUID | None = None
    status: PlanRunStatus = "pending"
    mode: PlanRunMode
    model_ref: UUID | None = None
    source_checksum: str = ""
    source_markdown: str = ""
    active_job_id: UUID | None = None
    error_detail: str | None = None
    checkpoint_state: dict[str, Any] = Field(default_factory=dict)
    # 27 V2-A1 — the pass ledger (one key per pass_id) + the genre input (PF-15).
    pass_state: dict[str, PassEntry] = Field(default_factory=dict)
    genre_tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlanArtifact(BaseModel):
    id: UUID
    run_id: UUID
    created_by: UUID  # 25 M3 actor stamp (was owner_user_id) — stored, never a filter (PM-5)
    kind: PlanArtifactKind
    content: dict[str, Any]
    created_at: datetime | None = None


# ── PlanForge auto-bootstrap gate (docs/specs/2026-07-06-planforge-auto-bootstrap.md §3.1)
PlanBootstrapProposalStatus = Literal[
    "pending", "approved", "rejected", "applying", "applied", "failed",
]


class PlanBootstrapProposal(BaseModel):
    id: UUID
    run_id: UUID
    book_id: UUID
    created_by: UUID  # 25 M3 actor stamp (was owner_user_id) — stored, never a filter (PM-5)
    status: PlanBootstrapProposalStatus = "pending"
    diff: dict[str, Any]
    applied_results: dict[str, Any] = Field(default_factory=dict)
    error_detail: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── authoring run (RAID Wave D2, DR-D — the §10 autonomy-dial level-3/4 run)
AuthoringRunStatus = Literal[
    "draft", "gated", "running", "paused", "failed", "report_ready", "closed",
]


class AuthoringRun(BaseModel):
    run_id: UUID
    created_by: UUID  # 25 M3 actor stamp (was owner_user_id) — spend/bearer identity; never a filter
    book_id: UUID
    plan_run_id: UUID
    level: int
    scope: list[str] = Field(default_factory=list)          # ordered chapter-id strings
    budget_usd: Decimal = Decimal("0")
    spent_usd: Decimal = Decimal("0")
    tool_allowlist: list[str] = Field(default_factory=list)  # C2 snapshot (caller-provided)
    params: dict[str, Any] = Field(default_factory=dict)     # drafting-seam inputs (model ref)
    breaker_state: dict[str, Any] = Field(default_factory=dict)
    status: AuthoringRunStatus = "draft"
    current_unit: int = 0
    error_message: str | None = None
    # D4 durable driver: which driver process owns the run + its per-unit
    # heartbeat (stale heartbeat on a 'running' run = no live driver → the
    # periodic sweep re-claims and resumes from current_unit). `background` is
    # the FE-facing fg/bg flag (v1: display/filter only — sweep durability
    # applies to BOTH fg and bg runs).
    driver_id: str | None = None
    driver_heartbeat_at: datetime | None = None
    background: bool = False
    # D-AGENT-MODE §20 D4: server-side auto-pause-after-each-unit policy (default
    # ON — matches the DB column default). The driver's per-unit boundary check
    # honors this flag regardless of entry point (Studio UI or headless MCP).
    pause_after_each_unit: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── authoring run unit (RAID Wave D3 — the per-unit ledger row the driver writes;
# review FSM pending→drafted→(accepted|rejected), pending→failed)
AuthoringRunUnitStatus = Literal[
    "pending", "drafted", "failed", "accepted", "rejected",
]


class AuthoringRunUnit(BaseModel):
    run_id: UUID
    unit_index: int
    chapter_id: UUID
    status: AuthoringRunUnitStatus = "pending"
    pre_revision_id: UUID | None = None   # pre-run restore point (NULL = no revisions yet)
    post_revision_id: UUID | None = None  # the run's draft revision (best-effort)
    cost_usd: Decimal = Decimal("0")      # this unit's share of the run's spent_usd
    error_message: str | None = None
    # D5: the continuity-critic verdict — {severity: ok|warn|severe, summary,
    # cost_usd[, detail]}. None = not critiqued (critic disabled / unit never
    # drafted / run paused-or-stolen at the boundary before the critique).
    critic_verdict: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── retrieval result (the FROZEN contract W3 produces / W2 + the MCP suggest consume)
class MotifCandidate(BaseModel):
    motif: Motif
    score: float
    match_reason: dict[str, Any] = Field(default_factory=dict)   # {tension, genre, precond, cosine}


# ── arc retrieval result (D-ARC-RETRIEVE — composition_arc_suggest consumes this)
class ArcCandidate(BaseModel):
    arc_template: ArcTemplate
    score: float
    match_reason: dict[str, Any] = Field(default_factory=dict)   # {genre, cosine[, degraded]}


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
