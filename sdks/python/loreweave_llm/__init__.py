"""loreweave_llm — Python SDK for the LoreWeave LLM gateway.

Phase 1b deliverable. See contracts/api/llm-gateway/v1/openapi.yaml for
the canonical contract.

Streaming usage:

    from loreweave_llm import Client, StreamRequest, TokenEvent, DoneEvent

    client = Client(
        base_url="http://provider-registry-service:8085",
        auth_mode="internal",
        internal_token="<token>",
        user_id="<uuid>",
    )
    request = StreamRequest(
        model_source="user_model",
        model_ref="<uuid>",
        messages=[{"role": "user", "content": "hi"}],
    )
    async for ev in client.stream(request):
        if isinstance(ev, TokenEvent):
            print(ev.delta, end="", flush=True)
        elif isinstance(ev, DoneEvent):
            break
    await client.aclose()
"""

from loreweave_llm.client import Client
from loreweave_llm.errors import (
    LLMAudioFetchFailed,
    LLMAudioTooLarge,
    LLMAudioURLDisallowed,
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMImageContentPolicy,
    LLMImageGenerationFailed,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMStreamNotSupported,
    LLMUpstreamError,
)
from loreweave_llm.models import (
    AudioChunkEvent,
    AudioFormat,
    DoneEvent,
    ErrorEvent,
    ImageGenDataItem,
    ImageGenResult,
    ReasoningEvent,
    SttInput,
    SttResult,
    StreamEvent,
    StreamRequest,
    TokenEvent,
    TtsInput,
    TtsStreamRequest,
    UsageEvent,
)

__all__ = [
    "Client",
    # Models
    "StreamRequest",
    "StreamEvent",
    "TokenEvent",
    "ReasoningEvent",
    "UsageEvent",
    "DoneEvent",
    "ErrorEvent",
    # Phase 5a audio models
    "AudioChunkEvent",
    "AudioFormat",
    "TtsInput",
    "TtsStreamRequest",
    "SttInput",
    "SttResult",
    # Phase 5c-α image-gen models
    "ImageGenDataItem",
    "ImageGenResult",
    # Errors
    "LLMError",
    "LLMAuthFailed",
    "LLMInvalidRequest",
    "LLMQuotaExceeded",
    "LLMModelNotFound",
    "LLMRateLimited",
    "LLMUpstreamError",
    "LLMStreamNotSupported",
    "LLMDecodeError",
    # Phase 5b audio-specific errors
    "LLMAudioTooLarge",
    "LLMAudioFetchFailed",
    "LLMAudioURLDisallowed",
    # Phase 5c-α image-gen-specific errors
    "LLMImageContentPolicy",
    "LLMImageGenerationFailed",
]

__version__ = "0.1.0"
