"""Typed event + request models for the loreweave_llm SDK.

Mirrors `StreamEventEnvelope`, `StreamRequest`, `SubmitJobRequest`, `Job`,
and the per-event schemas in contracts/api/llm-gateway/v1/openapi.yaml.
Pydantic v2 discriminated union — `event_type` is the discriminator
field; consumers can pattern-match by class.

Phase 4a-α Step 1 — adds async-job models (JobOperation, JobStatus,
ChunkingConfig, CallbackConfig, SubmitJobRequest, SubmitJobResponse,
JobProgress, Job) so knowledge-service migration can construct typed
submit_job() calls without hand-marshalling JSON.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Stream events ─────────────────────────────────────────────────────


class _BaseEvent(BaseModel):
    """Common base — present so consumers can `isinstance(x, _BaseEvent)`."""

    model_config = ConfigDict(populate_by_name=True)


class TokenEvent(_BaseEvent):
    event_type: Literal["token"] = Field("token", alias="event")
    delta: str
    index: int = 0


class ReasoningEvent(_BaseEvent):
    """Thinking-model intermediate output (Qwen3.x, DeepSeek-R1, OpenAI
    o-series, etc.). Indexes are independent of TokenEvent indexes."""

    event_type: Literal["reasoning"] = Field("reasoning", alias="event")
    delta: str
    index: int = 0


class UsageEvent(_BaseEvent):
    event_type: Literal["usage"] = Field("usage", alias="event")
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int | None = None


class DoneEvent(_BaseEvent):
    event_type: Literal["done"] = Field("done", alias="event")
    finish_reason: str | None = None


class ErrorEvent(_BaseEvent):
    event_type: Literal["error"] = Field("error", alias="event")
    code: str
    message: str


# Discriminated union of all canonical events.
StreamEvent = Annotated[
    Union[TokenEvent, ReasoningEvent, UsageEvent, DoneEvent, ErrorEvent],
    Field(discriminator="event_type"),
]


# ── Stream request ────────────────────────────────────────────────────

ModelSource = Literal["user_model", "platform_model"]
StreamFormat = Literal["openai", "anthropic", "vercel-ai-ui-v1"]


class StreamRequest(BaseModel):
    """Mirrors `StreamRequest` schema in the openapi contract."""

    model_config = ConfigDict(populate_by_name=True)

    model_source: ModelSource
    model_ref: UUID
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    stream_format: StreamFormat = "openai"
    trace_id: str | None = None

    def to_request_body(self) -> dict[str, Any]:
        """Serialize to the wire JSON body. Drops `max_tokens` when it's
        None OR 0 — caller policy: omit means 'let the model decide'.
        Sending `max_tokens=0` to most providers means 'cap output at 0
        tokens' which is never what the caller wants; treating 0 as
        omit prevents that footgun. UUID stringified via mode='json'."""
        data = self.model_dump(mode="json", exclude_none=True)
        if data.get("max_tokens") == 0:
            data.pop("max_tokens", None)
        return data


# ── Async jobs (P2) — Phase 4a-α Step 1 ───────────────────────────────

JobOperation = Literal[
    "chat",
    "completion",
    "embedding",
    "stt",
    "tts",
    "image_gen",
    "entity_extraction",
    "relation_extraction",
    "event_extraction",
    "translation",
]

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

ChunkStrategy = Literal["tokens", "paragraphs", "sentences", "none"]

CallbackKind = Literal["rabbitmq", "webhook"]


class ChunkingConfig(BaseModel):
    """Mirrors `ChunkingConfig` in openapi. `size` defaults are gateway-
    side per-strategy (2000 tokens / 8 paragraphs / 30 sentences); pass
    explicit values when overriding."""

    model_config = ConfigDict(populate_by_name=True)

    strategy: ChunkStrategy = "none"
    size: int | None = None
    overlap: int | None = None


class CallbackConfig(BaseModel):
    """RabbitMQ topic OR webhook URL for completion notification.
    routing_key required for rabbitmq; url required for webhook."""

    model_config = ConfigDict(populate_by_name=True)

    kind: CallbackKind
    routing_key: str | None = None
    url: str | None = None


class SubmitJobRequest(BaseModel):
    """Mirrors openapi `SubmitJobRequest`.

    `model_ref` is `str` (NOT UUID) per ADR §5.1 MED#5 — extractor
    signatures stay `str`; the SDK validates UUID-shape at the wire
    boundary so a malformed ref fails with LLMInvalidRequest before
    hitting the gateway.
    """

    model_config = ConfigDict(populate_by_name=True)

    operation: JobOperation
    model_source: ModelSource
    model_ref: str
    input: dict[str, Any]
    chunking: ChunkingConfig | None = None
    callback: CallbackConfig | None = None
    trace_id: str | None = None
    job_meta: dict[str, Any] | None = None

    def to_request_body(self) -> dict[str, Any]:
        """Serialize for POST /v1/llm/jobs. exclude_none keeps the wire
        payload tight + matches gateway's nullable-field handling."""
        return self.model_dump(mode="json", exclude_none=True)


class SubmitJobResponse(BaseModel):
    """202 Accepted envelope from POST /v1/llm/jobs."""

    model_config = ConfigDict(populate_by_name=True)

    job_id: UUID
    status: JobStatus
    submitted_at: str  # RFC3339 nano — kept as str for caller-side parsing


class JobProgress(BaseModel):
    """Mirrors openapi `JobProgress`. All fields nullable — chunks_total
    is None for unchunked jobs, populated mid-flight for chunked."""

    model_config = ConfigDict(populate_by_name=True)

    chunks_total: int | None = None
    chunks_done: int | None = None
    tokens_used: int | None = None
    last_progress_at: str | None = None


class JobError(BaseModel):
    """Mirrors openapi `ErrorBody`. Populated on Job.status=failed."""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    retry_after_s: float | None = None


class Job(BaseModel):
    """Mirrors openapi `Job`. Populated by GET /v1/llm/jobs/{id}.

    `result` is operation-specific dict — see openapi schema for shape
    per operation. Caller's tolerant parser narrows to typed records.
    """

    model_config = ConfigDict(populate_by_name=True)

    job_id: UUID
    operation: JobOperation
    status: JobStatus
    progress: JobProgress | None = None
    result: dict[str, Any] | None = None
    error: JobError | None = None
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    trace_id: str | None = None
    job_meta: dict[str, Any] | None = None

    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")
