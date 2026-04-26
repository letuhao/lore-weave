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

## Coexistence with `model-registry` contract

`contracts/api/model-registry/` covers credential / inventory / model-config
endpoints (`POST /v1/model-registry/providers`, `GET /v1/model-registry/user-models`,
etc.). It still owns those concerns.

The legacy `POST /v1/model-registry/invoke` endpoint is the **buffered
sync invoke** that this contract replaces. Per the refactor plan §4d,
`/v1/model-registry/invoke` and `/internal/invoke` will be removed in
Phase 4d after grep+log confirms zero callers. Until then, both contracts
coexist.
