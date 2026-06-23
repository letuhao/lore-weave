from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Interview-roleplay: working_memory (charter + state) ─────────────────────
# The pinned goal-state block. Mirrors contracts/interview/working_memory.schema.json.
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

    def model_post_init(self, __context: Any) -> None:
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.top_p is not None and not (0.0 <= self.top_p <= 1.0):
            raise ValueError("top_p must be between 0.0 and 1.0")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ValueError("max_tokens must be non-negative")


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
    # A2A phase-2: optional "composer" model. When set, the orchestrator
    # (model_ref) can call compose_prose, which streams THIS model for prose.
    composer_model_source: str | None = None
    composer_model_ref: UUID | None = None


class PatchSessionRequest(BaseModel):
    title: str | None = None
    system_prompt: str | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    status: str | None = None
    generation_params: GenerationParams | None = None
    is_pinned: bool | None = None
    # K5: PATCH can set or clear project_id. Use Pydantic's model_dump
    # exclude_unset semantics — explicit `null` clears, omitted leaves alone.
    project_id: UUID | None = None
    # A2A phase-2: set/clear the composer model (same exclude_unset semantics).
    composer_model_source: str | None = None
    composer_model_ref: UUID | None = None


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
    composer_model_source: str | None = None  # A2A phase-2
    composer_model_ref: UUID | None = None
    # K-CLEAN-5 (D-K8-04): client-derived initial memory mode for the
    # session header indicator. The router computes this from
    # `project_id` alone (no_project / static) on GET — `degraded` only
    # ever arrives via the per-turn SSE `memory-mode` event, since it's
    # an ephemeral state of the last turn's knowledge-service call. The
    # FE consumes both: the GET response sets the initial badge, the
    # SSE stream updates it on each turn.
    memory_mode: str = "no_project"


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


# ── Messages ──────────────────────────────────────────────────────────────────

class EditorContext(BaseModel):
    """ARCH-1 C6 — present when the editor `<Chat>` panel sends a message.
    Signals chat-service to advertise the frontend write-back tool, and carries
    which chapter the assistant is editing (for the proposal's chapter guard)."""
    book_id: str
    chapter_id: str


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


class SendMessageRequest(BaseModel):
    content: str
    edit_from_sequence: int | None = None
    context: str | None = None  # Optional context block (book/chapter/glossary text) injected as system message
    thinking: bool | None = None  # Override session default: true=think, false=fast, None=use session default
    editor_context: EditorContext | None = None  # ARCH-1 C6: editor panel → enable frontend write-back tool
    book_context: BookContext | None = None  # Glossary-assistant P3: book-scoped chat → enable glossary edit tool
    admin_context: AdminContext | None = None  # T4c: cms admin chat → advertise System-tier admin tools (token via X-Admin-Token header)
    disable_tools: bool = False  # Editor "Compose" mode: advertise no tools this turn (prose-only; reasoning model drafts, user Applies)
    display_language: str | None = None  # S6: the user's display language → knowledge composes entity aliases in this language (omit = source-language)


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
