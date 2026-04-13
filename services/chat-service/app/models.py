from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


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

class SendMessageRequest(BaseModel):
    content: str
    edit_from_sequence: int | None = None
    context: str | None = None  # Optional context block (book/chapter/glossary text) injected as system message
    thinking: bool | None = None  # Override session default: true=think, false=fast, None=use session default


class ChatMessage(BaseModel):
    message_id: UUID
    session_id: UUID
    owner_user_id: UUID
    role: str
    content: str
    content_parts: Any | None
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
