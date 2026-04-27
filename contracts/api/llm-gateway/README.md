# LLM Gateway Contract

Unified contract for ALL LLM operations on the LoreWeave platform.
Supersedes per-service ad-hoc patterns (`/internal/proxy/v1/chat/completions`,
`/v1/model-registry/invoke`, `litellm` direct imports). Two flavors:

- **`POST /v1/llm/stream`** — interactive streaming chat (SSE, no timeout)
- **`POST /v1/llm/jobs`** — async LLM job (submit → 202 → callback)

OpenAPI source:

- `v1/openapi.yaml`

Lint command:

```bash
npx @stoplight/spectral-cli lint --ruleset "contracts/.spectral.yaml" "contracts/api/llm-gateway/v1/openapi.yaml"
```

See [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md](../../../docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
for principles, audit findings, and migration phases.

## Status

- **Phase 0a** (this draft) — OpenAPI spec, no implementation yet
- **Phase 1** (next) — gateway implementation of `POST /v1/llm/stream`
- **Phase 2** — gateway implementation of `POST /v1/llm/jobs`
- **Phase 3+** — chunking, aggregation, service migrations
- **Phase 4d** ✅ — legacy buffered-invoke endpoints retired (see below)

## Coexistence with `model-registry` contract

`contracts/api/model-registry/` covers credential / inventory / model-config
endpoints (`POST /v1/model-registry/providers`, `GET /v1/model-registry/user-models`,
etc.). It still owns those concerns.

### Phase 4d retirement

The following legacy endpoints have been removed:

- `POST /v1/model-registry/invoke` — buffered sync invoke (public)
- `POST /internal/invoke` — buffered sync invoke (service-to-service)
- `POST /internal/proxy/v1/chat/completions` — transparent proxy (chat)
- `POST /internal/proxy/v1/completions` — transparent proxy (legacy)
- `POST /internal/proxy/v1/embeddings` — transparent proxy (embeddings)

The proxy paths above now respond with `410 Gone` + error code
`PROXY_PATH_DEPRECATED` as defense-in-depth so any future caller that
slips past code review fails loudly.

Audio paths (`/internal/proxy/v1/audio/transcriptions`,
`/internal/proxy/v1/audio/speech`) still pass through; chat-service
voice depends on them until the audio adapter ships in Phase 5b.

All non-audio LLM operations now go through `POST /v1/llm/jobs` (or
`POST /v1/llm/stream` for SSE) via the `loreweave_llm` SDK.
