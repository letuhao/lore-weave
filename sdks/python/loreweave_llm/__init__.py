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
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMStreamNotSupported,
    LLMUpstreamError,
)
from loreweave_llm.models import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    StreamRequest,
    TokenEvent,
    UsageEvent,
)

__all__ = [
    "Client",
    # Models
    "StreamRequest",
    "StreamEvent",
    "TokenEvent",
    "UsageEvent",
    "DoneEvent",
    "ErrorEvent",
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
]

__version__ = "0.1.0"
