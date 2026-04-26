"""Typed event + request models for the loreweave_llm SDK.

Mirrors `StreamEventEnvelope`, `StreamRequest`, and the per-event schemas
in contracts/api/llm-gateway/v1/openapi.yaml. Pydantic v2 discriminated
union — `event_type` is the discriminator field; consumers can pattern-
match by class.
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
