# loreweave_llm — Python SDK

Phase 1b of the [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN](../../docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md).
Canonical Python client for the LoreWeave LLM gateway.

## Status

| Capability | Phase | Status |
|---|---|---|
| `Client.stream()` — SSE streaming chat | 1b | ✅ this version |
| `Client.submit_job()` — async LLM job | 2 | stub raising `NotImplementedError` |

## Install (in-monorepo)

Services consume the SDK as a path-installed dependency. In a service's
`requirements.txt`:

```
-e ../../sdks/python
```

Or install ad-hoc for development:

```bash
pip install -e sdks/python
```

## Usage — streaming

```python
from loreweave_llm import Client, StreamRequest, TokenEvent, DoneEvent, UsageEvent

client = Client(
    base_url="http://provider-registry-service:8085",
    auth_mode="internal",
    internal_token="<dev_internal_token>",
    user_id="<owner-user-uuid>",
)

request = StreamRequest(
    model_source="user_model",
    model_ref="<user-model-uuid>",
    messages=[{"role": "user", "content": "Tell me a story"}],
    temperature=0.7,
)

async for event in client.stream(request):
    if isinstance(event, TokenEvent):
        print(event.delta, end="", flush=True)
    elif isinstance(event, UsageEvent):
        print(f"\n[tokens: in={event.input_tokens}, out={event.output_tokens}]")
    elif isinstance(event, DoneEvent):
        print(f"\n[finish: {event.finish_reason}]")
        break

await client.aclose()
```

## Auth modes

- **`auth_mode="jwt"`** — pass `bearer_token`. Calls `/v1/llm/stream`. Used by
  api-gateway-bff or any user-context caller.
- **`auth_mode="internal"`** — pass `internal_token` AND `user_id`. Calls
  `/internal/llm/stream`. Used by service-to-service callers
  (knowledge-service, chat-service, etc.).

## No timeouts

Per refactor plan principle P1, streaming has **no wall-clock timeout**.
The SDK only enforces:
- a 5s connect timeout (fail fast if gateway is unreachable)
- a per-frame idle read timeout (default 120s, configurable via
  `idle_read_timeout_s` constructor kwarg) — the longest gap between SSE
  frames before treating the stream as stalled

## Errors

All errors inherit from `loreweave_llm.LLMError`. Specific subclasses:
`LLMAuthFailed`, `LLMInvalidRequest`, `LLMQuotaExceeded`,
`LLMModelNotFound`, `LLMRateLimited`, `LLMUpstreamError`,
`LLMStreamNotSupported`, `LLMDecodeError`. SSE-frame errors (`event:
error`) are raised as the matching exception with the original code +
message.

## Tests

```bash
cd sdks/python
pip install -e .[test]
pytest
```

Tests use `respx` to mock the gateway HTTP transport — no live network
calls.
