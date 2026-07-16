from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ── Interview-roleplay: working_memory (charter + state) ─────────────────────
# The pinned goal-state block. Mirrors contracts/agent-control/working_memory.schema.json.
# `charter` is written ONLY by the goal authority (template here) and is the frozen
# anchor; `state` is the executive-rewritten progress estimate (safe-when-wrong).
# Spec: docs/specs/2026-06-23-interview-roleplay.md.

class WorkingMemoryCharter(BaseModel):
    """Committed goal/intention. Frozen for interview (template writes once)."""

    goal: str
    phases: list[str] = Field(min_length=1)
    checklist: list[str] = Field(default_factory=list)
    time_budget_min: int | None = None
    language: str
    # ACP A4 (RV-M4/RV-M7) — the fixed question count an interview drives before wrapping.
    # MUST be declared here: the model defaults to extra='ignore', so an undeclared field would
    # be silently DROPPED and the anchor would never see it. Optional/additive (older charters ok).
    question_target: int | None = None


class WorkingMemoryState(BaseModel):
    """Mutable progress estimate. `covered` is monotonic; `remaining` is derived."""

    phase: str = ""
    covered: list[str] = Field(default_factory=list)
    elapsed_min: int | None = None
    drift_note: str | None = None
    redirect_hint: str | None = None


class WorkingMemory(BaseModel):
    version: int = 1
    charter: WorkingMemoryCharter
    state: WorkingMemoryState = Field(default_factory=WorkingMemoryState)

    def remaining(self) -> list[str]:
        """Derived, never stored: charter.checklist − state.covered."""
        done = set(self.state.covered)
        return [c for c in self.charter.checklist if c not in done]


# ── Interview-roleplay: session_templates (the goal authority) ───────────────
# A reusable interviewer persona + the scenario that seeds a session's frozen
# `charter`. Tenancy: System tier (owner_user_id NULL, seeded via migration,
# admin-managed) is read-only to users; Per-user tier is the user's own. The
# user-facing write API only ever touches the caller's own Per-user rows —
# System rows are never writable through it (a regular user MUST NOT mutate a
# shared/System row).

class SessionTemplateScenario(BaseModel):
    """Seeds working_memory.charter at session create (the goal authority)."""

    goal: str
    phases: list[str] = Field(min_length=1)
    checklist: list[str] = Field(default_factory=list)
    time_budget_min: int | None = None
    language: str = "en"


class CreateTemplateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str = Field(min_length=1)
    model_source: str | None = None
    model_ref: UUID | None = None
    scenario: SessionTemplateScenario
    rubric: dict[str, Any] | None = None


class PatchTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    scenario: SessionTemplateScenario | None = None
    rubric: dict[str, Any] | None = None
    is_active: bool | None = None


class SessionTemplate(BaseModel):
    template_id: UUID
    owner_user_id: UUID | None
    tier: str
    code: str
    name: str
    description: str | None
    system_prompt: str
    model_source: str | None
    model_ref: UUID | None
    scenario: SessionTemplateScenario
    rubric: Any | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    items: list[SessionTemplate]


class StartPracticeRequest(BaseModel):
    """Clone a template into a new chat session (seeds the frozen charter)."""

    title: str | None = None
    # Override the template's default model when set; else the template must
    # carry one.
    model_source: str | None = None
    model_ref: UUID | None = None
    project_id: UUID | None = None


# ── Interview-roleplay: evaluation scorecard (M6) ────────────────────────────
# A non-agentic pipeline scores the finished practice transcript against the
# frozen charter.checklist (+ optional template rubric) → a structured
# Scorecard, stored as a ChatOutput (output_type='scorecard'). The model emits
# the JSON; we coerce it defensively so a hallucinating model can never invent a
# checklist item or 500 the endpoint.

class ChecklistVerdict(BaseModel):
    """Per-charter-checklist verdict. `item` is always a verbatim charter item;
    the coercion step guarantees every charter item has exactly one verdict so
    the model can neither drop nor invent items."""

    item: str
    covered: bool = False
    note: str | None = None  # one-line evidence (covered) or what was missing


class Scorecard(BaseModel):
    """Structured interview scorecard (spec §3.5). Every field is optional/
    defaulted: the LLM fills what it can, coercion supplies the rest. `partial`
    is set by the server (EC-13), never trusted from the model."""

    overall_score: int | None = None        # 0-100, model's holistic estimate
    star_coverage: str | None = None        # Situation/Task/Action/Result narrative
    clarity: str | None = None              # how clearly the candidate communicated
    filler: str | None = None               # rambling / filler-word observation
    checklist: list[ChecklistVerdict] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)  # improvement tips
    summary: str | None = None
    # Server-set: the transcript didn't reach `wrap`, was short, or was clipped
    # to the prompt budget — the scorecard scores only what exists (EC-13).
    partial: bool = False
    # WS-5.22 (P5 Gate-4 / SD-7) — quarantine tier: a coaching score is SHOWN but NEVER
    # trended until the numeric eval gate clears in a human-rating milestone. Defaults TRUE
    # (fail-closed): every score a code run produces is quarantine, because `evaluate_gate`
    # can never clear without human labels. The FE excludes quarantine scores from any trend.
    quarantine: bool = True
    # WS-5.21 — N-dimensional score, SERVER-AUTHORITATIVE from the coaching_rubrics dimensions
    # (the model contributes a 1-5 score per FIXED key; it can't drop/invent a dimension).
    # Empty for a legacy interview scorecard (the named STAR fields above stay for that path).
    dimensions: list[dict] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    """The evaluate result: the persisted ChatOutput id + the structured card."""

    output_id: UUID
    session_id: UUID
    scorecard: Scorecard
    model_source: str
    model_ref: str


# ── Message feedback (Q3 — Production Eval + Feedback Flywheel) ───────────────


class MessageFeedbackRequest(BaseModel):
    """Explicit thumbs (+1/-1) or implicit regenerate-as-negative on a chat
    turn. ``regenerated_from_message_id`` is set when the FE regenerate flow
    posts the implicit negative on the original message."""

    rating: int = Field(..., description="+1 thumb up, -1 thumb down")
    reason: str | None = None
    regenerated_from_message_id: UUID | None = None


class MessageFeedbackResponse(BaseModel):
    id: str
    message_id: str
    rating: int
    created_at: datetime


# ── Sessions ──────────────────────────────────────────────────────────────────

class GenerationParams(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    thinking: bool | None = None
    # Granular reasoning-effort default for the session (resolve_reasoning reads it,
    # taking precedence over the legacy boolean `thinking`). "off" disables hidden
    # thinking entirely — the cure for an over-thinking / runaway-reasoning model that
    # burns tokens without finishing. None ⇒ fall back to `thinking` / platform default.
    reasoning_effort: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.top_p is not None and not (0.0 <= self.top_p <= 1.0):
            raise ValueError("top_p must be between 0.0 and 1.0")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ValueError("max_tokens must be non-negative")
        if self.reasoning_effort is not None and self.reasoning_effort not in (
            "off", "auto", "low", "medium", "high",
        ):
            raise ValueError("reasoning_effort must be off|auto|low|medium|high")


class CreateSessionRequest(BaseModel):
    model_source: str         # 'user_model' | 'platform_model'
    model_ref: UUID
    title: str = "New Chat"
    system_prompt: str | None = None
    generation_params: GenerationParams | None = None
    # K5: optional knowledge-service project link. chat-service stores
    # the UUID without validating its existence — knowledge-service is
    # the source of truth and rejects unknown project_ids on context
    # build (returns 404 → graceful degrade to no memory).
    project_id: UUID | None = None
    # Track B B1(2) — multi-KG: an optional SET of knowledge projects to union
    # into one grounding context (world + member books). Takes precedence over
    # `project_id` on context build; the single field stays for tool scope +
    # back-compat. ≤16 (matches knowledge-service's ContextBuildRequest cap).
    project_ids: list[UUID] | None = Field(default=None, max_length=16)
    # A2A phase-2: optional "composer" model. When set, the orchestrator
    # (model_ref) can call compose_prose, which streams THIS model for prose.
    composer_model_source: str | None = None
    composer_model_ref: UUID | None = None
    # D-PLAN-PLANNER-DEFAULT-FE phase 2: optional per-session PLANNER model.
    # When set, chat-service injects it into the agent's glossary_plan call.
    planner_model_source: str | None = None
    planner_model_ref: UUID | None = None
    # D-COMPOSE-SESSION-RESTORE: set by a book-scoped caller (Writing Studio
    # Compose) so the session survives being found again on the next open,
    # independent of whether a knowledge project is linked yet.
    book_id: UUID | None = None
    # T-4 (sealed) — the assistant-session discriminator. The Work Assistant FE
    # (WS-1.10) creates its session with session_kind='assistant'; the day-window
    # read, voice gate, and search scoping key off it. Closed set (enum-validated
    # on write); every other caller omits it → a regular 'chat' session.
    session_kind: Literal["chat", "assistant"] = "chat"


class PatchSessionRequest(BaseModel):
    title: str | None = None
    system_prompt: str | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    status: str | None = None
    generation_params: GenerationParams | None = None
    is_pinned: bool | None = None
    # Story 04: session-scoped tool/skill pins (empty = auto-discovery mode).
    enabled_tools: list[str] | None = Field(default=None, max_length=32)
    enabled_skills: list[str] | None = Field(default=None, max_length=16)
    activated_tools: list[str] | None = None  # write: clear discovered tools via []
    # Tool-catalog-simplification Part D (CAT-4): manually pin a legacy (superseded,
    # find_tools-invisible) tool into this session. Validated server-side against
    # the live legacy catalog — see GET /v1/chat/sessions/tools/legacy.
    pinned_legacy_tools: list[str] | None = Field(default=None, max_length=16)
    # K5: PATCH can set or clear project_id. Use Pydantic's model_dump
    # exclude_unset semantics — explicit `null` clears, omitted leaves alone.
    project_id: UUID | None = None
    # Track B B1(2) — multi-KG: set/replace the grounding project SET. Presence
    # in the body drives the write (an explicit [] clears it back to the legacy
    # single-project path); omitted leaves it alone. ≤16.
    project_ids: list[UUID] | None = Field(default=None, max_length=16)
    # A2A phase-2: set/clear the composer model (same exclude_unset semantics).
    composer_model_source: str | None = None
    composer_model_ref: UUID | None = None
    # D-PLAN-PLANNER-DEFAULT-FE phase 2: set/clear the per-session planner model.
    planner_model_source: str | None = None
    planner_model_ref: UUID | None = None
    # ── Chat & AI settings, SESSION tier (spec 2026-07-05 §3.5) ──────────────
    # These three columns already existed and were READ by the effective-settings
    # resolver (and `grounding_enabled` by the turn itself, messages.py), but had no
    # write path anywhere — so the Session tier of the cascade was permanently NULL.
    # A tier that is read and never written is the mirror of a write-only setting.
    #
    # All three carry 3-state semantics, like `project_id`: omitted ⇒ untouched;
    # explicit `null` ⇒ CLEAR the override (inherit from Book/Account/System);
    # a value ⇒ override for this session. Presence is detected via
    # `model_fields_set`, never `is not None` (which cannot see a clear).
    grounding_enabled: bool | None = None
    voice_overrides: dict[str, Any] | None = None
    context_overrides: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_session_enums(self) -> "PatchSessionRequest":
        """The session row is the SECOND write door onto settings the turn consumes,
        so it validates against the SAME closed sets the account patch uses. Without
        this, a bad `context_overrides.mode` stores fine and every reader silently
        treats it as 'auto' — a value-shaped silent no-op."""
        from app.services import settings_resolution as sr

        sr.validate_setting_enums("context", self.context_overrides)
        if self.generation_params is not None:
            sr.validate_setting_enums(
                "behavior", self.generation_params.model_dump(exclude_unset=True)
            )
        return self


class ChatSession(BaseModel):
    session_id: UUID
    owner_user_id: UUID
    title: str
    model_source: str
    model_ref: UUID
    system_prompt: str | None
    generation_params: dict[str, Any]
    is_pinned: bool
    status: str
    message_count: int
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    project_id: UUID | None = None  # K5
    book_id: UUID | None = None  # D-COMPOSE-SESSION-RESTORE
    session_kind: str = "chat"  # T-4 — 'chat' | 'assistant' (the assistant-session discriminator)
    # Track B B1(2) — multi-KG grounding set. Empty list = the legacy
    # single-project path. Default-empty so an older row / no-project session
    # stays back-compatible.
    project_ids: list[UUID] = Field(default_factory=list)
    composer_model_source: str | None = None  # A2A phase-2
    composer_model_ref: UUID | None = None
    planner_model_source: str | None = None  # D-PLAN-PLANNER-DEFAULT-FE phase 2
    planner_model_ref: UUID | None = None
    # Chat & AI settings, SESSION tier. `None` = no session override (inherit).
    # Surfaced on read so the session settings panel can distinguish "set HERE"
    # from "inherited" without a second request — the tier chip needs the raw
    # session value, not just the resolved cascade.
    grounding_enabled: bool | None = None
    voice_overrides: dict[str, Any] = Field(default_factory=dict)
    context_overrides: dict[str, Any] = Field(default_factory=dict)
    # K-CLEAN-5 (D-K8-04): client-derived initial memory mode for the
    # session header indicator. The router computes this from
    # `project_id` alone (no_project / static) on GET — `degraded` only
    # ever arrives via the per-turn SSE `memory-mode` event, since it's
    # an ephemeral state of the last turn's knowledge-service call. The
    # FE consumes both: the GET response sets the initial badge, the
    # SSE stream updates it on each turn.
    memory_mode: str = "no_project"
    # WS-1.6 (spec 05 §Q7) — the last persisted per-turn capture decision
    # ({"fire": bool, "reason": str}) so the assistant home strip can render capture
    # visibly ON/OFF with a reason on GET. None until the first post-turn write.
    capture_status: dict[str, Any] | None = None
    enabled_tools: list[str] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    activated_tools: list[str] = Field(default_factory=list)
    pinned_legacy_tools: list[str] = Field(default_factory=list)
    # W3 — manual steerable compact: messages with sequence_num < this are
    # represented by the session's stored compact_summary on every later turn.
    # NULL/None = never manually compacted. (The summary text itself is not
    # exposed on the session payload — the FE only needs the marker.)
    compacted_before_seq: int | None = None


# ── Chat Quality Wave W3 — manual steerable compact ─────────────────────────

class CompactSessionRequest(BaseModel):
    """POST /v1/chat/sessions/{id}/compact body. ``instructions`` steer WHAT
    survives the summary ("keep all plot promises and character names");
    ``keep_recent`` = how many most-recent messages stay verbatim.
    ``clear`` = true wipes the stored compact (summary + marker) instead of
    compacting — mutually exclusive with instructions/keep_recent."""
    instructions: str | None = Field(default=None, max_length=500)
    keep_recent: int = Field(default=8, ge=1, le=100)
    clear: bool = False


class CompactSessionResponse(BaseModel):
    summary_tokens: int
    compacted_message_count: int
    # None only on a clear (cleared=True) — a compact always sets it.
    compacted_before_seq: int | None
    tokens_before_estimate: int
    tokens_after_estimate: int
    # True when the request cleared the stored compact instead of compacting.
    cleared: bool = False


class SessionListResponse(BaseModel):
    items: list[ChatSession]
    next_cursor: str | None


class SearchResult(BaseModel):
    session_id: UUID
    session_title: str
    message_id: UUID
    role: str
    snippet: str
    created_at: datetime


class SearchResponse(BaseModel):
    items: list[SearchResult]


# ── Story 04: tool/skill catalog (rack browser) ─────────────────────────────

class ToolCatalogItem(BaseModel):
    name: str
    domain: str
    tier: str
    description: str
    # CAT-4: discoverable (default, browsable/pinnable via enabled_tools) or
    # legacy (superseded — only reachable via pinned_legacy_tools).
    visibility: str = "discoverable"


class ToolCatalogResponse(BaseModel):
    items: list[ToolCatalogItem]


class SkillCatalogItem(BaseModel):
    id: str
    label: str
    surfaces: list[str]


class SkillCatalogResponse(BaseModel):
    items: list[SkillCatalogItem]


# ── Messages ──────────────────────────────────────────────────────────────────

class EditorContext(BaseModel):
    """ARCH-1 C6 — present when the editor `<Chat>` panel sends a message.
    Signals chat-service to advertise the frontend write-back tool, and carries
    which chapter the assistant is editing (for the proposal's chapter guard)."""
    book_id: str
    chapter_id: str
    # RAID C1 (DR-C1) — optional active chapter/scene title, matched by
    # scene_match steering entries (case-insensitive substring). Additive:
    # older FEs simply never send it and scene_match entries stay dormant.
    chapter_title: str | None = None


class BookContext(BaseModel):
    """Glossary-assistant P3 — present when a book-scoped chat (glossary page,
    reader) that is NOT the chapter editor sends a message. Signals chat-service
    to advertise the glossary edit-existing write-back tool
    (`glossary_propose_entity_edit`). Carries only the book; no chapter."""
    book_id: str


class AdminContext(BaseModel):
    """Tiered-MCP-tools T4c — present when the cms-frontend ADMIN chat panel sends
    a message. A presence marker only: it signals chat-service to advertise the
    System-tier admin tools from glossary's `/mcp/admin` (instead of the book/user
    `/mcp` catalog). It carries NO admin credential — the RS256 `admin:write` token
    rides the `X-Admin-Token` HEADER (bearer hygiene, §6.7), never the body. The
    optional `label` is a UI string only and grants no authority (INV-T2: admin
    authority is the verified RS256 token, never anything in this model)."""
    label: str | None = None


class StudioContext(BaseModel):
    """Studio compose context — API-ready; validation deferred to studio phase.

    CTX-1 (the position pointer): project_id/active_chapter_id let the system message
    TELL the model the composition project + active chapter it is standing in, instead
    of forcing tool-forage (a live M-E gate run dead-ended retrying the book_id AS a
    project_id against composition_* tools)."""
    book_id: UUID | None = None
    project_id: UUID | None = None
    active_chapter_id: UUID | None = None
    active_panel_ids: list[str] = Field(default_factory=list)
    context_revision: int | None = None


class ConsumerCapabilities(BaseModel):
    """Studio consumer capabilities stub — reconciler track #09."""
    pass


class SendMessageRequest(BaseModel):
    content: str
    edit_from_sequence: int | None = None
    context: str | None = None  # Optional context block (book/chapter/glossary text) injected as system message
    thinking: bool | None = None  # Override session default: true=think, false=fast, None=use session default
    # AI-task standard — granular per-message effort from the input-bar dropdown,
    # now the UNIFIED 5-level vocabulary (off|low|medium|high|auto) that matches the
    # session-stored default; maps into UserReasoningPref in _thinking_pref (identity
    # + auto→adaptive) and takes precedence over the legacy `thinking` boolean. The
    # legacy 3-level (fast|standard|deep) is still accepted for back-compat during
    # the FE convergence.
    reasoning_effort: Literal[
        "off", "low", "medium", "high", "auto", "fast", "standard", "deep"
    ] | None = None
    editor_context: EditorContext | None = None  # ARCH-1 C6: editor panel → enable frontend write-back tool
    book_context: BookContext | None = None  # Glossary-assistant P3: book-scoped chat → enable glossary edit tool
    admin_context: AdminContext | None = None  # T4c: cms admin chat → advertise System-tier admin tools (token via X-Admin-Token header)
    disable_tools: bool = False  # Editor "Compose" mode: advertise no tools this turn (prose-only; reasoning model drafts, user Applies)
    display_language: str | None = None  # S6: the user's display language → knowledge composes entity aliases in this language (omit = source-language)
    # Story 04: per-turn ephemeral overrides (do not PATCH session).
    enabled_tools: list[str] | None = None
    enabled_skills: list[str] | None = None
    studio_context: StudioContext | None = None
    consumer_capabilities: ConsumerCapabilities | None = None
    # RAID Wave C2 (DR-C2) — HITL permission mode. 'write' (default) = today's
    # behavior + the Tier-A prompt-once approval gate; 'ask' = read-only research
    # surface (server tools filter to tier R; frontend tools stay — they are
    # human-executed by construction). Compose stays the disable_tools seam above.
    # RAID Wave B2 (07S §5b) — 'plan' = the ask surface PLUS the PlanForge
    # `plan_*` server tools (they write plan artifacts, never prose); plan_forge
    # skill auto-injects and a plan-mode system nudge is appended.
    # Default None (not "write") so the turn can tell "omitted" from an explicit
    # "write" and fall back to the user's account default (user_chat_ai_prefs.
    # behavior.permission_mode) when omitted, then to "write". The FE input bar
    # always sends an explicit value, so this only affects callers that omit it.
    permission_mode: Literal["ask", "write", "plan"] | None = None


class ToolResultRequest(BaseModel):
    """ARCH-1 C6 — the resume request: the FE executed a frontend tool (the
    user reviewed + applied/dismissed the proposed edit) and returns the
    outcome so the agent can continue.

    Outcomes:
      propose_edit (prose):  "applied" | "dismissed"
      glossary_propose_entity_edit (P3, H6 truthful resume):
        "applied_saved" | "applied_conflict" | "applied_error" | "dismissed"
    The value is passed through verbatim to the agent as the tool result so it
    reports the REAL outcome (claim success only on applied_saved)."""
    run_id: str
    tool_call_id: str
    # Optional because MCP-fanout ui_* nav tools resolve with a structured
    # `result` instead of the outcome enum (no human gate — see `result`).
    outcome: str | None = None
    applied_text: str | None = None
    # MCP fan-out (C-NAV): structured result for a ui_* nav resolve (e.g.
    # {"navigated": true}); fed back verbatim as the tool result on the 2nd pass.
    result: dict | None = None


class ChatMessage(BaseModel):
    message_id: UUID
    session_id: UUID
    owner_user_id: UUID
    role: str
    content: str
    content_parts: Any | None
    # K21-B/C (D-K21B-05): per-message tool-call history — the
    # chat_messages.tool_calls JSONB column. NULL when the turn made no
    # tool calls.
    tool_calls: Any | None = None
    sequence_num: int
    input_tokens: int | None
    output_tokens: int | None
    model_ref: UUID | None
    is_error: bool
    error_detail: str | None
    parent_message_id: UUID | None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[ChatMessage]


# ── Context history (per-turn token breakdown over the session) ────────────────
# Chat Quality Wave W1 persisted chat_messages.context_breakdown (the full
# contextBudget frame) per assistant turn; this surfaces the ordered SERIES so
# the FE can chart how each category's token cost evolved across the conversation
# (the "History" view of the ContextBreakdownPanel — not just the live "Now").

class ContextHistoryPoint(BaseModel):
    sequence_num: int
    created_at: datetime
    input_tokens: int | None
    output_tokens: int | None
    # The `breakdown` sub-map of the persisted contextBudget frame: fixed 12-key
    # vocabulary (token_budget.BREAKDOWN_CATEGORIES). Every value is an int token
    # count except `memory_knowledge`, which nests {total, sections}. Passed
    # through verbatim so the FE reuses the same category color map + the
    # `categoryTokens` flattening helper as the live panel.
    breakdown: dict[str, Any]


class ContextHistoryResponse(BaseModel):
    items: list[ContextHistoryPoint]


# ── Context trace (the Inspector's per-turn data source, spec §11) ─────────────
# Unlike ContextHistoryPoint (the chart — breakdown sub-map only), the Inspector
# needs the WHOLE persisted contextBudget frame per turn (raw_tokens, reduction_pct,
# target, status_flags, retrieval_mode, intent, entity_presence, the trace spans, the
# allocation breakdown) plus the user message that drove the turn. `frame` is the
# frame verbatim so the FE reads exactly what the compiler emitted (no lossy reshape).

class ContextTracePoint(BaseModel):
    sequence_num: int
    created_at: datetime
    input_tokens: int | None
    output_tokens: int | None
    # The parent user turn's text (what the author typed). None when the assistant
    # turn has no text-column parent (e.g. a parts-only user message).
    user_message: str | None
    # The full persisted contextBudget frame (context_breakdown JSONB) verbatim.
    frame: dict[str, Any]


class ContextTraceResponse(BaseModel):
    items: list[ContextTracePoint]


class LatestContextBudgetResponse(BaseModel):
    # The LAST assistant turn's persisted contextBudget frame (the same shape the
    # SSE `contextBudget` event carries: used_tokens / context_length /
    # effective_limit / pct / breakdown / baseline_tokens / until_compact_pct).
    # `None` when the session has no measured turn yet (a brand-new session). Lets
    # the FE header meter render on session LOAD instead of only after the next
    # live turn finishes — the meter's snapshot was previously live-only.
    budget: dict[str, Any] | None


# ── Outputs ───────────────────────────────────────────────────────────────────

class ChatOutput(BaseModel):
    output_id: UUID
    message_id: UUID
    session_id: UUID
    owner_user_id: UUID
    output_type: str
    title: str | None
    content_text: str | None
    language: str | None
    storage_key: str | None
    mime_type: str | None
    file_name: str | None
    file_size_bytes: int | None
    metadata: Any | None
    created_at: datetime


class PatchOutputRequest(BaseModel):
    title: str | None = None


class OutputListResponse(BaseModel):
    items: list[ChatOutput]


# ── Internal client models ────────────────────────────────────────────────────

class ProviderCredentials(BaseModel):
    provider_kind: str
    provider_model_name: str
    base_url: str
    api_key: str
    context_length: int | None
    # Provider Context Strategy §3 — the provider kind's static caching capabilities
    # (prompt_cache_control / responses_api / auto_prefix_cache), resolved by
    # provider-registry (the single home) and consumed here to label the caching
    # monitoring frame + pick a ContextStrategy. Defaults empty so a legacy/absent
    # field degrades to "no special caching" (StatelessFullContext).
    capabilities: dict[str, bool] = Field(default_factory=dict)
