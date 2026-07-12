from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# KG customizable-ontology epic (L1) — the kg_* graph-schema models live in a
# sibling module. Imported here so the DB-model package is a single surface;
# consumers address them as `app.db.ontology_models.<Name>` (NOT re-exported
# flat, to avoid clobbering the chat-memory `FactType` Literal defined below).
from app.db import ontology_models  # noqa: F401

ProjectType = Literal["book", "translation", "code", "general"]
ExtractionStatus = Literal["disabled", "building", "paused", "ready", "failed"]
ScopeType = Literal["global", "project", "session", "entity"]
# K21-C (design D5): mirrors the Neo4j FactType closed enum in
# app/db/neo4j_repos/facts.py. Kept as a local Literal (same pattern
# as ProjectType / ScopeType) so app.db.models stays free of any
# neo4j_repos import.
FactType = Literal["decision", "preference", "milestone", "negation", "statement"]

# Names are stripped of surrounding whitespace and must contain at least
# one non-whitespace character. Max 200 chars, chat-service convention.
ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

# K7 (D-K1-01/02 cleanup): length caps mirrored in Pydantic for early
# 422s and in the DB CHECK constraints (migrate.py) for defense-in-depth.
ProjectDescription = Annotated[str, StringConstraints(max_length=2000)]
ProjectInstructions = Annotated[str, StringConstraints(max_length=20000)]
SummaryContent = Annotated[str, StringConstraints(max_length=50000)]


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    user_id: UUID
    name: str
    description: str
    project_type: ProjectType
    book_id: UUID | None = None
    instructions: str
    extraction_enabled: bool
    extraction_status: ExtractionStatus
    # D-EMB-MODEL-REF-01: the provider-registry `user_model` UUID of the
    # project's embedding model (the `model_ref` for `/internal/embed`).
    # TEXT-typed for back-compat; holds a UUID string. NULL = not yet
    # configured. (Pre-fix this held a logical name like "bge-m3", which
    # provider-registry 400'd — see KNOWLEDGE_SERVICE_EMBEDDING_MODEL_REF_ADR.)
    embedding_model: str | None = None
    # D-EMB-MODEL-REF-01: caller-supplied vector dimension; the
    # passage_ingester + L3 selector + benchmark read it at call time.
    embedding_dimension: int | None = None
    # D-RERANK-NOT-BYOK: per-project BYOK rerank model (provider-registry
    # user_model UUID) + source. None ⇒ raw-search skips the rerank step
    # (rerank is optional, never platform-fixed). FE picker = S0b.
    rerank_model: str | None = None
    rerank_model_source: str = "user_model"
    extraction_config: dict
    last_extracted_at: datetime | None = None
    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal
    is_archived: bool
    # K21.12-BE (design D9): per-project tool-calling toggle. Default
    # True so a project row that predates the column reads back enabled
    # (mirrors the DB `DEFAULT true`).
    tool_calling_enabled: bool = True
    # K21-C (design D4): per-project memory_remember confirmation gate.
    # Default False — opt-in; a project row that predates the column
    # reads back off (mirrors the DB `DEFAULT false`) so memory_remember
    # keeps writing directly until the user turns confirmation on.
    memory_remember_confirm: bool = False
    # WS-4C Half A: per-project canon auto-capture. When True (and the deploy
    # ceiling allows), chat-service captures the newly-named entities of every
    # Nth turn into this book's glossary review inbox as ai-suggested drafts.
    # Default **False** — mirrors the DB `DEFAULT false`. Capture is AMBIENT
    # spend on the user's own model, so it is OPT-IN: the toggle is the consent,
    # and it must start un-granted. (Deliberately the opposite of
    # tool_calling_enabled, which is a behaviour the user turns OFF.)
    canon_capture_enabled: bool = False
    # P2 (D6 opt-in raw retention): when True, leaf_processor persists
    # the full LLM raw response to extraction_leaves_raw alongside the
    # postprocessed candidates. Default False — power users opt-in for
    # re-judge / debug / A-B prompt comparison. FE wire-up tracked as
    # D-P2-FE-SAVE-RAW.
    save_raw_extraction: bool = False
    # E2 — user-set genre tag for per-genre config-quality mining.
    genre: str | None = None
    # C23-fix (dị bản G2): True ⇒ this project is a DERIVATIVE's own fresh
    # partition. Excluded from the source book's per-(user,book) get-or-create
    # dedup + get_by_book so a derivative never inherits / is never handed back
    # for the source book. Default False so a row that predates the column
    # reads back as a normal (non-derivative) project (mirrors DB DEFAULT false).
    is_derivative: bool = False
    # G4 (world-level project): when set, this project IS a world's dedicated
    # knowledge partition (bound to the world's hidden bible book). FK-by-
    # convention to book-service worlds.id (cross-DB, no SQL FK). NULL for every
    # normal per-book / general project. Hidden from the HOME projects browser;
    # surfaced only through the world workspace + the world rollup subgraph.
    world_id: UUID | None = None
    version: int  # D-K8-03: bumped on every non-empty PATCH.
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    name: ProjectName
    description: ProjectDescription = ""
    project_type: ProjectType
    book_id: UUID | None = None
    instructions: ProjectInstructions = ""
    genre: str | None = None
    # G4 (world-level project): set by the world-create / lazy-provision path so
    # the project is stamped as the world's dedicated partition (bound to the
    # world's bible book). Idempotent: create_or_get stamps it onto the existing
    # bible-book project if newly supplied. NULL for normal projects.
    world_id: UUID | None = None
    # C23-fix (dị bản G2): set True by the composition derive path so the
    # derivative's project ALWAYS inserts as a fresh distinct project
    # (skips the per-(user,book) get-or-create dedup) AND is stamped
    # is_derivative=true (so the source book's future create_or_get /
    # get_by_book never returns it). Default False ⇒ the normal book-binding
    # path is unchanged (still idempotent per (user, book)).
    force_new: bool = False


class ProjectUpdate(BaseModel):
    """Partial update. Field semantics:

    - `name`, `description`, `instructions`: omit to leave unchanged. Setting
      explicitly to None is rejected (these columns are NOT NULL). Passing
      a value replaces the current value.
    - `book_id`: omit to leave unchanged. Setting to None explicitly CLEARS
      the book link. Setting to a UUID sets a new link.
    - `is_archived`: restore-only. Set to `false` to un-archive. Setting
      to `true` is rejected at the router with 422 — archive uses the
      dedicated `POST /archive` endpoint which has the 404-oracle
      hardening (does not leak whether a project exists). K-CLEAN-3.
    - `embedding_model` (D-EMB-MODEL-REF-01): omit to leave unchanged.
      Set to a provider-registry `user_model` UUID (the embedding
      model's `model_ref`) to switch the project's vector space; set to
      None to clear. Send `embedding_dimension` alongside it — the two
      define the vector space together and the dimension is no longer
      derivable from the (now opaque UUID) model ref. Clearing the model
      (None) clears the dimension.
    - `embedding_dimension` (D-EMB-MODEL-REF-01): omit to leave
      unchanged. The vector dimension of the chosen embedding model;
      caller-supplied (the FE picker / config flow knows it, e.g. from a
      probe call). Must pair with `embedding_model`.
    - `tool_calling_enabled` (K21.12-BE, design D9): omit to leave
      unchanged. Set to `true`/`false` to toggle whether the
      chat-service tool-calling loop offers memory tools for this
      project. NOT NULL in the DB, so setting it explicitly to None
      is treated as "skip" by the repo (same as name/description).
      The settings toggle UI that drives this is Cycle C — accepting
      the field now lets that be a FE-only change.
    - `memory_remember_confirm` (K21-C, design D4): omit to leave
      unchanged. Set to `true`/`false` to toggle whether the
      executor queues `memory_remember` facts for user confirmation
      instead of writing them directly. NOT NULL in the DB, so
      setting it explicitly to None is treated as "skip" by the repo
      (same as tool_calling_enabled).
    - `canon_capture_enabled` (WS-4C Half A): omit to leave unchanged.
      Set to `true`/`false` to toggle whether chat-service auto-captures
      the entities a conversation establishes into the book's glossary
      review inbox. NOT NULL in the DB, so an explicit None is "skip"
      (same as tool_calling_enabled).
    """

    name: ProjectName | None = None
    description: ProjectDescription | None = None
    instructions: ProjectInstructions | None = None
    book_id: UUID | None = None
    is_archived: bool | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    # D-RERANK-NOT-BYOK (S0b): omit to leave unchanged. Set to a provider-registry
    # user_model UUID to enable BYOK rerank for raw-search; set to None to clear
    # (rerank then skipped). rerank_model_source is NOT NULL in the DB so an
    # explicit None is "skip" (same as tool_calling_enabled).
    rerank_model: str | None = None
    rerank_model_source: str | None = None
    tool_calling_enabled: bool | None = None
    memory_remember_confirm: bool | None = None
    canon_capture_enabled: bool | None = None
    save_raw_extraction: bool | None = None
    # E2: None = "skip" (unchanged); explicitly set to None via PATCH uses
    # _NULLABLE_UPDATE_COLUMNS so it clears (sets to SQL NULL).
    genre: str | None = None
    # G4: attach/detach a project to a world. Omit = unchanged; explicit None
    # CLEARS the world link (uses _NULLABLE_UPDATE_COLUMNS). Set to a UUID to
    # bind. Normal flows never touch this — world provisioning does.
    world_id: UUID | None = None


# ── B2-B-b1 — per-project extraction-config tuning (structural subset) ──
# These drive worker-ai's resolve_effective_config (project override > global
# default). `extra="forbid"` rejects out-of-subset keys with 422 (DESIGN Q4).
# Raw prompt editing (`prompts`) is the SEPARATE security-sensitive b2 pass —
# deliberately NOT here. PUT semantics: the body REPLACES extraction_config;
# omit a sub-object to drop that override (fall back to the global default).

ModelSourceLit = Literal["user_model", "platform_model"]
FilterCategoryLit = Literal["entity", "relation", "event"]
PartialPolicyLit = Literal["keep", "drop"]


class LlmModelOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_ref: str | None = None
    model_source: ModelSourceLit | None = None


class PrecisionFilterOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    categories: list[FilterCategoryLit] | None = None
    partial_policy: PartialPolicyLit | None = None
    model_ref: str | None = None
    model_source: ModelSourceLit | None = None


class EntityRecoveryOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    model_ref: str | None = None
    model_source: ModelSourceLit | None = None
    # KN model-roles — Tier-3 classifier batch size (names classified per LLM
    # call). Bounded 1-20; None = the env/default (5). Read by the extract-item
    # resolver (_resolve_entity_recovery_config).
    max_items_per_batch: Annotated[int, Field(ge=1, le=20)] | None = None


class WriterAutocreateOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None


# B2-B-b2 — raw per-op system-prompt override (SECURITY-sensitive). Only the
# `system` instructions are overridable (the user message is always the raw
# chapter text). Capped at 16 kB/field (DESIGN §2.5 — the SDK context_budget
# absorbs oversize as more chunks; the cap only stops the absurd whole-novel
# paste). The SDK appends a fixed output-contract reminder so a custom prompt
# can't break the JSON-only discipline. Raw text lives ONLY in the owner's
# project row — it is content-hashed, never copied raw, into learning-service.
# /review-impl MED-1 — only the ops extract_pass2 actually applies overrides
# for. `summarize_level` runs in a separate P3 path that doesn't thread
# prompt_overrides yet, so offering it here would accept an inert override.
PromptOpLit = Literal["entity", "relation", "event", "fact"]
_PROMPT_MAX_LEN = 16384  # ~16 kB


class PromptOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: Annotated[str, StringConstraints(max_length=_PROMPT_MAX_LEN)] | None = None


class ProjectExtractionConfigUpdate(BaseModel):
    """The full per-project extraction-config. PUT replaces the stored
    `extraction_config` with the non-None fields of this body — the caller
    (FE) must send the COMPLETE config (structural + prompts) each time, or an
    omitted section is dropped (PUT-replace, not merge)."""
    model_config = ConfigDict(extra="forbid")
    llm_model: LlmModelOverride | None = None
    precision_filter: PrecisionFilterOverride | None = None
    entity_recovery: EntityRecoveryOverride | None = None
    writer_autocreate: WriterAutocreateOverride | None = None
    prompts: dict[PromptOpLit, PromptOverride] | None = None
    # D-K18.3-02 / Track 4 P2 — the two L3 rerank knobs read by Mode 3
    # (`full.py`): a generative LLM rerank and the purpose-built cross-encoder
    # (both provider-registry user_model UUIDs, BYOK). Were readable by the
    # builder but had NO public write path (extra="forbid" rejected them) —
    # unreachable-config gap found by the Track 4 eval run.
    rerank_model: str | None = None
    cross_encoder_rerank_model: str | None = None


class Summary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_id: UUID
    user_id: UUID
    scope_type: ScopeType
    scope_id: UUID | None = None
    content: str
    token_count: int | None = None
    version: int
    created_at: datetime
    updated_at: datetime


# D-K8-01: append-only history row captured by the repo on every
# successful summary update. `edit_source` is the rollback audit
# trail — rollback operations write 'rollback' so the UI can
# distinguish them from user-typed history entries.
EditSource = Literal["manual", "rollback", "regen"]


class SummaryVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: UUID
    summary_id: UUID
    user_id: UUID
    version: int
    content: str
    token_count: int | None = None
    created_at: datetime
    edit_source: EditSource


# K21-C (design D5): a transient queue row awaiting user confirmation
# before a `memory_remember` fact lands in the graph. `fact_type`
# mirrors the Neo4j FactType closed enum. `fact_text` is stored already
# injection-neutralized (design D6) so the confirm endpoint writes it
# through to merge_fact as-is. `project_id` is nullable — a no-project
# chat can still queue a fact.
class PendingFact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pending_fact_id: UUID
    user_id: UUID
    project_id: UUID | None = None
    session_id: str | None = None  # WS-2.1: a DIARY fact has no chat session
    fact_type: FactType
    fact_text: str
    created_at: datetime
    # WS-2.2 (structured s/p/o) — optional; a coarse legacy fact carries only fact_text.
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    event_date: date | None = None
    provenance: str | None = None
