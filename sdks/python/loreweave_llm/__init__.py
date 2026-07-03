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

from loreweave_llm.attribution import (
    get_public_key_attribution,
    merge_attribution_into_job_meta,
    set_public_key_attribution,
)
from loreweave_llm.client import Client
from loreweave_llm.errors import (
    LLMAudioFetchFailed,
    LLMAudioGenerationFailed,
    LLMAudioTooLarge,
    LLMAudioURLDisallowed,
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMGatewayStorageError,
    LLMHttpError,
    LLMImageContentPolicy,
    LLMImageGenerationFailed,
    LLMInvalidRequest,
    LLMJobNotFound,
    LLMJobTerminal,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMStreamNotSupported,
    LLMTransientRetryNeededError,
    LLMUpstreamError,
    LLMVideoContentPolicy,
    LLMVideoGenerationFailed,
)
from loreweave_llm.models import (
    AudioChunkEvent,
    AudioFormat,
    AudioGenDataItem,
    AudioGenResult,
    DoneEvent,
    ErrorEvent,
    ImageGenDataItem,
    ImageGenResult,
    ReasoningEffort,
    ReasoningEvent,
    SttInput,
    SttResult,
    StreamEvent,
    StreamRequest,
    TokenEvent,
    ToolCallEvent,
    TtsInput,
    TtsStreamRequest,
    UsageEvent,
    VideoGenDataItem,
    VideoGenResult,
)
from .reasoning import (
    ReasoningControl,
    ReasoningDirective,
    UserReasoningPref,
    bucket_effort,
    infer_reasoning_control,
    reasoning_fields,
    resolve_reasoning,
)
from .structured import (
    GenerateResult,
    StructuredGenerateError,
    parse_json_object,
    structured_generate,
)

__all__ = [
    "Client",
    # P4/Wave-C slice D — public MCP-key spend attribution carrier
    "set_public_key_attribution",
    "get_public_key_attribution",
    "merge_attribution_into_job_meta",
    # Models
    "StreamRequest",
    "ReasoningEffort",
    # Reasoning policy (auto-thinking) — reusable across services
    "ReasoningControl",
    "UserReasoningPref",
    "ReasoningDirective",
    "infer_reasoning_control",
    "bucket_effort",
    "resolve_reasoning",
    "reasoning_fields",
    # AI-Task Standard — single-shot structured generate (shared plumbing)
    "structured_generate",
    "parse_json_object",
    "GenerateResult",
    "StructuredGenerateError",
    "StreamEvent",
    "TokenEvent",
    "ReasoningEvent",
    "UsageEvent",
    "DoneEvent",
    "ErrorEvent",
    # Phase 0b tool-use model
    "ToolCallEvent",
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
    # Phase 5d video-gen models
    "VideoGenDataItem",
    "VideoGenResult",
    # Phase 5e-β.2 audio_gen models
    "AudioGenDataItem",
    "AudioGenResult",
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
    # Phase 5d video-gen-specific errors
    "LLMVideoContentPolicy",
    "LLMVideoGenerationFailed",
    # Phase 5e-β.2 audio_gen-specific errors
    "LLMAudioGenerationFailed",
    "LLMGatewayStorageError",
    # Phase 4a-α async-job exceptions + transport (Phase 5e-α surfaces these
    # at the top-level loreweave_llm namespace for caller-side error mapping
    # in services like video-gen-service that map SDK errors to HTTPExceptions)
    "LLMJobNotFound",
    "LLMJobTerminal",
    "LLMHttpError",
    "LLMTransientRetryNeededError",
]

__version__ = "0.1.0"
