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


class CreateSessionRequest(BaseModel):
    model_source: str         # 'user_model' | 'platform_model'
    model_ref: UUID
    title: str = "New Chat"
    system_prompt: str | None = None
    generation_params: GenerationParams | None = None


class PatchSessionRequest(BaseModel):
    title: str | None = None
    system_prompt: str | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    status: str | None = None
    generation_params: GenerationParams | None = None
    is_pinned: bool | None = None


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
