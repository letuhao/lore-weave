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


class AudioChunkEvent(_BaseEvent):
    """Phase 5a TTS streaming event. Wire alias is `audio-chunk` (with
    hyphen) per the openapi schema; the Python alias matches.

    Caller decodes `data` from base64 to get raw audio bytes in the
    format negotiated via TtsInput.format. `final=True` marks the
    closing chunk and is followed by a `DoneEvent`.
    """

    event_type: Literal["audio-chunk"] = Field("audio-chunk", alias="event")
    sequence_id: int
    data: str  # base64 — caller decodes
    final: bool


class ToolCallEvent(_BaseEvent):
    """One incremental fragment of a tool call the model is emitting,
    re-framed by the gateway from OpenAI `delta.tool_calls[]` / Anthropic
    `input_json_delta`. Reassemble by `index` — the first fragment for an
    index carries `id` + `name`; later fragments carry only
    `arguments_delta`. There is no per-index terminal marker — completion
    is the `DoneEvent`. The gateway omits `index` when 0 and
    `arguments_delta` when empty (shared-struct omitempty); both default here.
    """

    event_type: Literal["tool_call"] = Field("tool_call", alias="event")
    index: int = 0
    id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


# Discriminated union of all canonical events.
StreamEvent = Annotated[
    Union[
        TokenEvent,
        ReasoningEvent,
        UsageEvent,
        DoneEvent,
        ErrorEvent,
        AudioChunkEvent,
        ToolCallEvent,
    ],
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
    # OpenAI-shaped tool-choice control — "auto"/"none"/"required" or
    # {"type":"function","function":{"name":...}}. The gateway rejects this
    # for a provider without tool support (LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER).
    tool_choice: dict[str, Any] | str | None = None
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
    "video_gen",  # Phase 5d
    "audio_gen",  # Phase 5e-β.2
    "entity_extraction",
    "relation_extraction",
    "event_extraction",
    "fact_extraction",  # Phase 4a-β
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


# ── Audio operation models (Phase 5a) ─────────────────────────────────

AudioFormat = Literal["mp3", "wav", "opus", "pcm"]


class TtsInput(BaseModel):
    """Mirrors openapi `TtsInput`. Used as `input` for `operation=tts`
    on POST /v1/llm/stream (NOT POST /v1/llm/jobs — tts is streaming-only).

    Phase 5a defaults match the openapi schema:
    - voice: alloy
    - speed: 1.0
    - format: mp3
    - text max length: 4000 chars (OpenAI TTS limit)
    """

    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(..., min_length=1, max_length=4000)
    voice: str = "alloy"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    format: AudioFormat = "mp3"


class TtsStreamRequest(BaseModel):
    """Mirrors openapi `TtsStreamRequest`. Submitted to POST /v1/llm/stream
    with `operation=tts`.

    Reuses model_source / model_ref / trace_id from the chat StreamRequest
    pattern; the only new top-level field is `input` (TtsInput shape).
    """

    model_config = ConfigDict(populate_by_name=True)

    operation: Literal["tts"] = "tts"
    model_source: ModelSource
    model_ref: UUID
    input: TtsInput
    trace_id: str | None = None

    def to_request_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class SttInput(BaseModel):
    """Mirrors openapi `SttInput`. Used as `input` field in
    SubmitJobRequest for `operation=stt`.

    `audio_url` MUST be HTTPS reachable from the gateway VPC. For
    chat-service voice flow (Phase 5b), this is a pre-signed MinIO URL
    with ≤60s TTL.
    """

    model_config = ConfigDict(populate_by_name=True)

    audio_url: str
    language: str = "auto"


class SttResult(BaseModel):
    """Mirrors openapi `SttResult`. Decoded from Job.result when
    `operation=stt` and `status=completed`.

    `language` and `duration_ms` are populated when upstream returns
    them (OpenAI Whisper `verbose_json` does); otherwise None.
    """

    model_config = ConfigDict(populate_by_name=True)

    text: str
    language: str | None = None
    duration_ms: int | None = None


# ── Phase 5c-α — image-gen models ─────────────────────────────────────


class ImageGenDataItem(BaseModel):
    """Mirrors openapi `ImageGenDataItem`. Single generated image in the
    response array.

    Exactly one of `url` or `b64_json` is populated based on the
    request's `response_format`. `revised_prompt` is upstream-populated
    when the model rewrote the prompt (DALL-E-3 + gpt-image-1 do this;
    local models typically don't).
    """

    model_config = ConfigDict(populate_by_name=True)

    url: str | None = None
    b64_json: str | None = None
    revised_prompt: str | None = None


class ImageGenResult(BaseModel):
    """Mirrors openapi `ImageGenResult`. Decoded from Job.result when
    `operation=image_gen` and `status=completed`.

    `data` contains 1..4 entries (gateway caps via MaxImagesPerJob).
    Caller is responsible for downloading the URL (if `url` mode) and
    storing in its own MinIO bucket — gateway does NOT download. URL
    lifetime is upstream-dependent (OpenAI: ~1 hour; local services:
    caller-configured). Caller MUST fetch immediately after polling
    completed; persistent storage of the upstream URL is unsafe.
    """

    model_config = ConfigDict(populate_by_name=True)

    created: int
    data: list[ImageGenDataItem] = Field(min_length=1, max_length=4)


# ── Phase 5d — video-gen models ─────────────────────────────────────


class VideoGenDataItem(BaseModel):
    """Mirrors openapi `VideoGenDataItem`. Single generated video.

    Phase 5d is url-only (b64_json rejected at handler per /review-impl
    MED#3 — realistic videos exceed the 8MB response cap). Field shape
    matches local-image-generator-service's response.

    `revised_prompt` is upstream-populated when the model rewrote the
    prompt (rare for video — most local backends don't have safety-system
    rewriting).
    """

    model_config = ConfigDict(populate_by_name=True)

    url: str | None = None
    revised_prompt: str | None = None


class VideoGenResult(BaseModel):
    """Mirrors openapi `VideoGenResult`. Decoded from Job.result when
    `operation=video_gen` and `status=completed`.

    `data` contains exactly 1 entry (gateway locks n=1 for Phase 5d).
    Caller is responsible for downloading the URL and storing in its
    own MinIO bucket — gateway does NOT download. URL lifetime is
    upstream-dependent. Caller MUST fetch immediately after polling
    completed.
    """

    model_config = ConfigDict(populate_by_name=True)

    created: int
    # max_length=1 mirrors Phase 5d n=1 lock. If Phase 5d-β (or later)
    # supports n>1, raise this in lockstep with: gateway handler
    # validateVideoGenInput, adapter pre-check in openai_video.go, and
    # the worker_video runVideoGenJob normalization. Otherwise the
    # pydantic deserialization rejects valid multi-video responses.
    data: list[VideoGenDataItem] = Field(min_length=1, max_length=1)


# ── Phase 5e-β.2 — audio_gen models ──────────────────────────────────


class AudioGenDataItem(BaseModel):
    """Mirrors openapi `AudioGenDataItem`. Single generated audio in the
    batch response.

    Exactly one of `url` or `b64_json` is populated based on the request's
    `response_format`. `duration_ms` is upstream-dependent (typically 0
    for OpenAI TTS). `content_type` is always populated.
    """

    model_config = ConfigDict(populate_by_name=True)

    url: str | None = None
    b64_json: str | None = None
    duration_ms: int | None = None
    content_type: str


class AudioGenResult(BaseModel):
    """Mirrors openapi `AudioGenResult`. Decoded from Job.result when
    `operation=audio_gen` and `status=completed`.

    `data` contains exactly len(texts) entries (gateway caps at
    MaxAudioGenInputs=10). Order is preserved: data[i] corresponds to
    input.texts[i] 1:1. Caller decodes b64_json bytes (default) OR
    fetches the URL (gateway-staged in MinIO with 1d server-side TTL).
    """

    model_config = ConfigDict(populate_by_name=True)

    created: int
    data: list[AudioGenDataItem] = Field(min_length=1, max_length=10)
