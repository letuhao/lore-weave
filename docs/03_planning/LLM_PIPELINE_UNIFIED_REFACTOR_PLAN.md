# LLM Pipeline Unified Contract — Audit + Refactor Plan

> **Status**: DRAFT — pending user review
> **Created**: 2026-04-26 (cycle C-LLM-PIPELINE-PLAN, session 52)
> **Driver**: User flagged that the platform's LLM usage is fragmented — every service implements its own contract, timeouts are arbitrary wall-clock guards on open-ended LLM workloads, and one service (chat) bypasses the gateway entirely. Need a single, strict contract before scale.

---

## 1. Principles (user-stated, non-negotiable)

| # | Principle | Implication |
|---|-----------|-------------|
| **P1** | **Streaming chat (interactive)** must support streaming end-to-end. **No timeout.** Tokens reach user immediately. | Gateway must SSE-pass-through; no buffer-and-respond; no wall-clock cap on the response. |
| **P2** | **Background LLM jobs** must be **fully async with notification**. No fragmentation between sync and async patterns. | Single submission contract → job_id → progress events → terminal-state notification (NEVER block caller via timeout). |
| **P3** | **Unified contract / SDK**. All LLM operations across services use the same contract — no per-team improvisation. | One spec (OpenAPI), one client SDK per language (Python, Go, TypeScript), generated from spec. Direct LLM SDK calls (litellm, openai-python, etc.) are forbidden in service code. |
| **P4** | **All LLM calls must go through `provider-registry`**. | Gateway invariant from CLAUDE.md restored and enforced; no direct upstream calls in any service. |

**Why these principles exist**: every LLM workload is open-ended (can't bound by wall clock). Either the user is watching it stream live (P1) or it's a job that runs in the background (P2). The contract layer (P3) prevents the drift that audit revealed below. The gateway invariant (P4) keeps credentials, rate-limit, model-resolution, and observability in one place.

---

## 2. Audit findings — current state (drift map)

### 2.1 LLM call site inventory

| Service | Pattern | Call path | Through gateway? | Violation? |
|---------|---------|-----------|-------------------|------------|
| **chat-service** (streaming chat) | Direct `litellm.acompletion` | `chat-service/app/services/stream_service.py:17,81,285` | **NO** — only resolves credentials via gateway, then bypasses | **P4 violation**. Bypass exists because gateway forces `stream: false` (see §2.4) |
| **chat-service** (voice STT/TTS) | Transparent proxy | `chat-service/app/services/voice_stream_service.py:95,127` → `/internal/proxy/v1/audio/{transcriptions,speech}` | YES | OK |
| **knowledge-service** (Pass 2 extraction) | ✅ unified gateway (Phase 4a-δ shipped) | `knowledge-service/app/clients/llm_client.py` → `/v1/llm/jobs` (job pattern + chunking + per-op JSON aggregator) | NO | Migrated to SDK |
| **translation-service** (translate) | Typed invoke (public) | `translation-service/app/routers/translate.py:93,163` → `/v1/model-registry/invoke` | YES | OK |
| **translation-service** (workers) | Typed invoke (internal) | `translation-service/app/workers/extraction_worker.py:327` + `session_translator.py:463,539,867` → `/internal/invoke` | YES | OK |
| **worker-ai** (job runner) | No direct LLM call | Calls knowledge-service `/internal/extraction/extract-item` | N/A | N/A — but inherits knowledge-service's drift |
| **glossary-service**, **book-service**, **auth-service**, **catalog-service**, **sharing-service**, **usage-billing-service**, **api-gateway-bff** | No LLM calls | — | — | — |

**Three different contracts for the same operation**:
1. **Transparent proxy** (`/internal/proxy/v1/*`) — passes bytes, requires caller to know upstream JSON shape, used by knowledge + chat-voice
2. **Typed invoke** (`/internal/invoke` and `/v1/model-registry/invoke`) — JSON envelope, normalized output, used by translation
3. **Direct SDK** (litellm) — bypasses everything, used by chat-streaming

### 2.2 Streaming infrastructure — partial, fragmented

| Where | Mechanism | Notes |
|-------|-----------|-------|
| `chat-service/app/routers/messages.py:222,236` | FastAPI `StreamingResponse` with `media_type="text/event-stream"` | SSE to FE works; uses Vercel AI SDK envelope (`x-vercel-ai-ui-message-stream: v1`) |
| `chat-service/app/routers/voice.py:72,85,117,127` | Same pattern | SSE for transcribe + speak |
| `provider-registry/internal/provider/adapters.go:464` | **Forces `stream: false`** | Gateway adapter strips `stream: true` from caller's body |
| Anywhere else in monorepo | None | knowledge, translation, glossary have NO streaming endpoint |

**Drift**: chat-service has SSE end-to-end but built it **around** the gateway, not through it. To stream, it had to go direct → P4 violation.

### 2.3 Timeout chain — math doesn't work

```
FE → api-gateway-bff
       └→ worker-ai (extract_item_timeout = 120s)
              └→ knowledge-service /internal/extraction/extract-item
                     └→ provider_client (provider_client_timeout_s = 60s default)
                            ├─ entity extraction (1 LLM call, ≤60s)
                            ├─ relation extraction (1 LLM call, ≤60s)
                            └─ event extraction (1 LLM call, ≤60s)
                            (concurrent via asyncio.gather, max=60s if happy path)
       OR
       └→ translation-service /v1/jobs (invoke_timeout = 300s, chunk_size_tokens = 2000)
              └→ provider-registry /v1/model-registry/invoke (httpx default ~5s? — UNKNOWN)
       OR
       └→ chat-service /v1/chat/* (StreamingResponse — no timeout)
              └→ litellm DIRECT to upstream (litellm has its own timeout default)
```

**Specific failures the audit found**:
- `chat-service KnowledgeClient` has 0.5s timeout but knowledge context-build needs ~2.7s → silent degraded context every call
- `knowledge-service` 60s × 3 calls > worker-ai's 120s budget → already-broken on big chapters
- `translation-service` has 300s and chunking — works for now, but value isn't shared
- Eval test bumped to 1500s — masked the real architectural gap, didn't fix it

### 2.4 Provider-registry capability matrix

| Capability | Status |
|------------|--------|
| Public invoke (`/v1/model-registry/invoke`) | Buffered request-response only |
| Internal invoke (`/internal/invoke`) | Buffered request-response only |
| Transparent proxy (`/internal/proxy/*`) | Bytes pass-through, but adapters force `stream: false` |
| Embeddings (`/internal/embed`) | Buffered |
| Async job submission | **MISSING** |
| Streaming (SSE pass-through) | **MISSING** |
| Job status + callback | **MISSING** |
| Batch | **MISSING** |
| Rate-limit / quota headers | **MISSING** |
| Adapter coverage | OpenAI ✓ · Anthropic ✓ · Ollama ✓ · LM Studio ✓ — chat + embed only; no STT/TTS adapters (audio is currently transparent-proxied raw) |

### 2.5 Background-job infrastructure

| Component | Where | Status |
|-----------|-------|--------|
| RabbitMQ broker | translation-service uses DIRECT exchange `loreweave.jobs`; worker-infra uses TOPIC exchange `loreweave.events` | Two exchanges for two pattern flavors — drift |
| Job state table | `translation_jobs` (PG) — `pending|running|completed|failed|cancelled` | Translation only; knowledge has its own `extraction_jobs` shape |
| Outbox pattern | `worker-infra` relays PG outbox tables → RabbitMQ | Used by translation; not used by extraction |
| Notification service | `notification-service` — REST-only, polling | No SSE/WebSocket push to FE |
| Job status SDK | None — each service defines its own enum + payload | — |

### 2.6 Per-principle violation summary

| Principle | Violations |
|-----------|------------|
| **P1 (streaming chat)** | Gateway hardcodes `stream: false` (adapters.go:464) → chat must bypass to stream |
| **P2 (async jobs)** | Knowledge has no chunking + sync HTTP call; translation has chunking but its own job shape; extraction caller (worker-ai) blocks on HTTP |
| **P3 (unified contract)** | 3 distinct LLM contracts; 2 distinct job-shape patterns; no shared SDK |
| **P4 (gateway-only)** | chat-service's litellm direct call |

---

## 3. Target architecture

### 3.1 Two-flavor LLM contract

```
                    ┌───────────────────────────────┐
                    │   provider-registry (gateway) │
                    │                                │
  ┌─── CHAT ────────┤  POST /v1/llm/stream  (SSE)   │
  │   (P1)          │  POST /v1/llm/jobs    (P2)    │
  │                 │  GET  /v1/llm/jobs/:id        │
  │                 │                                │
  │                 │  Adapters: OpenAI · Anthropic │
  │                 │  · LM Studio · Ollama · ...   │
  └─────────────────┴───────────────────────────────┘
        ▲                       ▲
        │                       │
   chat-service        knowledge / translation /
   (live SSE)          glossary-extraction / wiki-gen / ...
                       (job submit + notification)
```

**Two endpoints, one gateway, one auth model.** Every other service in the monorepo uses one of these — no third path.

### 3.2 Endpoint A: streaming chat (P1)

```
POST /v1/llm/stream
Headers: Authorization: Bearer <jwt>  OR  X-Internal-Token (svc→svc)
Body: {
  "model_source": "user_model" | "platform_model",
  "model_ref": "<uuid>",
  "messages": [...],            // OpenAI-shaped
  "tools": [...],               // optional
  "temperature": 0.0,
  "stream_format": "openai"|"anthropic"|"vercel-ai-ui-v1"  // SSE envelope shape
}
Response: 200, Content-Type: text/event-stream
  event: token   data: {"delta": "..."}
  event: usage   data: {"input_tokens": N, "output_tokens": M}
  event: done    data: {}
  event: error   data: {"code": "...", "message": "..."}
```

**Properties**:
- Gateway streams upstream provider's chunks straight through (one re-frame to canonical SSE envelope)
- **No wall-clock timeout** (only abort-on-disconnect from caller)
- Adapter responsibility: handle each provider's streaming format (OpenAI delta, Anthropic event_type, etc.) → emit canonical envelope
- Caller cancellation: HTTP disconnect propagates `context.cancel()` to upstream provider call
- chat-service migrates: drop litellm, call `/v1/llm/stream` and re-emit Vercel AI envelope to FE (or pass-through if `stream_format=vercel-ai-ui-v1` chosen at this layer)

### 3.3 Endpoint B: async LLM job (P2)

```
POST /v1/llm/jobs
Body: {
  "operation": "chat" | "completion" | "embedding" | "stt" | "tts" | "image_gen",
  "model_source", "model_ref",
  "input": { ... operation-specific },
  "chunking": {                       // OPTIONAL — gateway-side chunking
    "strategy": "tokens" | "paragraphs" | "none",
    "size": 2000,
    "overlap": 200
  },
  "callback": {                       // OPTIONAL — push notification when done
    "kind": "rabbitmq" | "webhook",
    "routing_key": "user.{user_id}.llm.done"   // for rabbitmq
    "url": "https://..."                       // for webhook
  },
  "trace_id": "...",
  "job_meta": { ... arbitrary, returned in status }
}
Response: 202 Accepted
{
  "job_id": "<uuid>",
  "status": "pending",
  "submitted_at": "..."
}
```

```
GET /v1/llm/jobs/{id}
Response: 200
{
  "job_id", "operation", "status": "pending|running|completed|failed|cancelled",
  "progress": { "chunks_total": 12, "chunks_done": 5, "tokens_used": 3400 },
  "result": { ... } | null,           // populated when status=completed
  "error":  { "code", "message" } | null,
  "started_at", "completed_at",
  "trace_id"
}

DELETE /v1/llm/jobs/{id}              // cancellation
```

**Properties**:
- **No timeout** at any layer of the call. Job runs until provider returns or upstream errors.
- Gateway-side chunking handles large input. Each chunk = independent provider call → `asyncio.gather` (or worker pool) → aggregate. Aggregator is operation-specific (entity dedup, translation concat, etc.).
- Notification is the **completion contract**. Caller never blocks on HTTP for the result. Two delivery modes:
  - **RabbitMQ topic** `user.{user_id}.llm.{op}.done` — preferred for in-cluster consumers (worker-ai, knowledge-service if it submits sub-jobs)
  - **Webhook URL** — for FE direct subscription via api-gateway-bff bridge
- FE listens via SSE (`/v1/notifications/stream`) — bridge from RabbitMQ to user-scoped SSE channel through api-gateway-bff
- **Job state owned by provider-registry** in a new `llm_jobs` table — single source of truth. Per-service job tables (extraction_jobs, translation_jobs) become **business-job tables** that REFERENCE `llm_jobs.job_id` for the LLM piece.

### 3.4 Provider-registry as the chunking + retry boundary

Today every service tries to handle these concerns differently. Move them into the gateway:

| Concern | Today | Target |
|---------|-------|--------|
| Chunking | translation has it; knowledge doesn't | Gateway-side, configurable per-job-submission |
| Retries on 429/5xx | Each service rolls its own | Gateway built-in with exponential backoff + Retry-After honor |
| Token counting / budget enforcement | usage-billing tracks; not enforced at gateway | Gateway enforces user quota before each provider call |
| Per-provider quirks (response_format, /v1/v1/) | Half in adapter, half in proxy | Gateway-only; service code is provider-agnostic |
| Streaming format normalization | None | Gateway emits canonical SSE envelope |
| Aggregation across chunks | Each service does its own | Gateway provides per-operation aggregator (chat=concat, entity=dedup-by-canonical-id, ...) |

### 3.5 SDK layer (P3)

One SDK per language, generated from the gateway's OpenAPI spec.

```
contracts/api/llm-gateway.yml          # canonical OpenAPI 3.1
sdks/
  python/loreweave_llm/                # for chat-service, knowledge-service, translation-service workers
    Client.stream(request) -> AsyncIterator[StreamEvent]
    Client.submit_job(request) -> JobHandle
    JobHandle.wait() -> JobResult       # subscribes to RabbitMQ user.{id}.llm.done
    JobHandle.poll() -> JobStatus       # for webhook callers
  go/loreweave-llm-go/                  # for any future Go service that needs LLM
  ts/loreweave-llm-ts/                  # for api-gateway-bff if it ever needs to call directly (and FE if we choose)
```

**Rule (enforced by lint + code review)**: any service may import `loreweave_llm` (or local-language equivalent). Direct imports of `litellm`, `openai`, `anthropic`, `httpx.post(... provider URL ...)`, etc., are forbidden — caught by:
- Pre-commit grep for forbidden imports
- CI lint rule

### 3.6 Notification → FE bridge

```
provider-registry → RabbitMQ topic "user.{user_id}.llm.{op}.{event}"
                              ↓
                  notification-service (consumer)
                              ↓
              user_notifications table (PG outbox)
                              ↓
                    api-gateway-bff
                              ↓
                  GET /v1/notifications/stream     (SSE to FE)
```

- FE opens 1 SSE connection on login (`/v1/notifications/stream`)
- All async-job completion events flow through this single channel
- FE uses event metadata to route to the right reducer (job_id matches a UI job widget)
- This also unifies **non-LLM** notifications (translation done, glossary export ready, ...) so we don't grow another bespoke pipe per feature

---

## 4. Migration plan

> Do NOT refactor everything in one PR. The plan below is sequential, each phase ships green, and each phase delivers measurable value.

### Phase 0 — Foundation (BLOCKING for all later phases)

| Cycle | Deliverable | Files | Effort |
|-------|-------------|-------|--------|
| **0a** | OpenAPI spec for `/v1/llm/stream` + `/v1/llm/jobs` (DRAFT) | `contracts/api/llm-gateway.yml` | M |
| **0b** | Architecture ADR (this doc → polished) + KSA amendment | `docs/03_planning/...` | S |
| **0c** | Migration deferral list (each existing call site → which phase migrates it) | this plan §5 | S |

### Phase 1 — Streaming (P1) end-to-end

| Cycle | Deliverable | Effort |
|-------|-------------|--------|
| **1a** | Gateway: implement `POST /v1/llm/stream` (OpenAI/Anthropic/LM Studio/Ollama adapters re-emit canonical SSE envelope; fix the hardcoded `stream: false` in adapters.go:464) | L |
| **1b** | Python SDK `Client.stream()` (consumer) | M |
| **1c** | Migrate chat-service: drop `litellm`, route through SDK; drop `from litellm import acompletion` | M |
| **1d** | Validate: existing chat E2E (`smoke-login` + interactive chat) green; latency parity with current litellm path | S |
| **1e** | Lint rule: forbid direct litellm import in monorepo | XS |

**Success gate**: chat-service has zero `import litellm` and `/v1/llm/stream` is the only streaming chat surface.

### Phase 2 — Async job (P2) infrastructure

| Cycle | Deliverable | Effort |
|-------|-------------|--------|
| **2a** | Gateway: `llm_jobs` table + DDL migration | S |
| **2b** | Gateway: `POST /v1/llm/jobs` + `GET /v1/llm/jobs/{id}` + `DELETE /v1/llm/jobs/{id}` (chat operation only, no chunking yet) | L |
| **2c** | Gateway: RabbitMQ producer for `user.{id}.llm.{op}.done` events | M |
| **2d** | Notification-service: consume LLM events → unified user_notifications table | M |
| **2e** | api-gateway-bff: `GET /v1/notifications/stream` SSE bridge | M |
| **2f** | FE: subscribe SSE on login; route LLM-job events to job widgets | L |

**Success gate**: a worker can submit a chat job to gateway, receive completion via RabbitMQ + FE shows toast via SSE — without any per-service wiring.

### Phase 3 — Chunking + aggregation in gateway

| Cycle | Deliverable | Effort |
|-------|-------------|--------|
| **3a** | Gateway: chunking strategies (`tokens` via tiktoken, `paragraphs`) | M |
| **3b** | Gateway: per-operation aggregators (chat=concat, embedding=stack, entity-extraction=dedup-by-canonical-id, relation=union-by-tuple) | L |
| **3c** | Gateway: per-chunk parallel via worker pool with backpressure | L |

**Success gate**: a 53KB chapter (Speckled Band) submitted as one job to gateway returns aggregated entities without timeout, regardless of model size (gemma-26b OR qwen3.6-35b).

### Phase 4 — Service migrations to job pattern

| Cycle | Deliverable | Effort |
|-------|-------------|--------|
| **4a** | knowledge-service migration — see [LLM_MIGRATION_ADR](./KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md). Sliced into 4 sub-cycles below. | XL (4 sub-cycles) |
| **4a-α** | Gateway prereqs (worker op-whitelist + transient-retry, per ADR §5.1 Step 0); SDK `submit_job` + `wait_terminal` + `cancel_job` with caller-side retry budget; entity_extraction E2E proof-of-concept; cancel-race regression test; `provider_client.py` retained. **✅ shipped at HEAD `6697d8d6`.** | XL |
| **4a-α-followup** | Restructure entity prompt as system+user (system = instructions + KNOWN_ENTITIES preserved across chunks; user = chapter text only, chunked); re-enable ChunkingConfig(strategy=paragraphs, size=15). **✅ shipped — Speckled Band 30 paragraphs → 2 chunks → 34 entities live smoke.** | M |
| **4a-β** | Migrate relation/event/fact extractors. Adds `fact_extraction` to openapi `JobOperation` enum + jsonListAggregator + worker dispatch. **✅ shipped — all 4 ops live: 5 entities + 5 relations + 2 events + 2 facts.** | L (shipped XL) |
| **4a-γ** | Migrate regenerate_summaries.py + on-demand summarize routers + scheduler. Uses `chat` operation (no chunking). NEW ProviderCancelled exception subclass; ProviderRateLimited preserves retry_after_s on transient-retry exhaustion. **✅ shipped — 1640/1640 tests + back-compat preserved.** | L |
| **4a-δ** | Drop `provider_client.py` + `llm_json_parser.py` + `client: ProviderClient` extractor params + K18.3 L3 passage rerank migrated to SDK. Mass-rewrite 14 test files to FakeLLMClient. Drop legacy `provider_chat_completion_*` + `llm_json_extraction_*` metrics (gateway-side equivalents cover). **✅ shipped — 1598 unit tests passed; zero `provider_client` references in knowledge-service.** | XL+ (Option A — full retirement in one cycle) |
| **4b** | Migrate worker-ai off the sync `extract-item` HTTP call. Sliced into 3 sub-cycles per Option C3 (shared library) — see plan docs below. | L (3 sub-cycles) |
| **4b-α** | Extract `loreweave_extraction` shared library at `sdks/python/loreweave_extraction/` (4 extractors + prompts + canonical IDs + Pass2 orchestrator + ExtractionError). Knowledge-service refactored to delegate; worker-ai untouched. **✅ shipped — SDK 160 + ks-svc 1530 = 1690 tests passed; +42 net coverage.** | XL |
| **4b-β** | knowledge-service adds `POST /internal/extraction/persist-pass2` accepting `Pass2Candidates` payload (uses existing `pass2_writer.write_pass2_extraction`). extract-item kept for back-compat. **✅ shipped — 8 new tests; library candidate models validated at wire boundary.** | M |
| **4b-γ** | worker-ai migration: drops `KnowledgeClient.extract_item`; uses `loreweave_extraction.extract_pass2(llm_client, ...)` then POSTs to `/persist-pass2`. **✅ shipped — 120s HTTP timeout removed; worker-ai runs Pass 2 LLM in-process via SDK; all 23 worker-ai tests + 160 SDK + 1541 ks-svc tests green.** Note: extract-item endpoint kept for back-compat through Phase 4d (deletion + zero-callers grep deferred). | L |
| **4c** | translation-service migration. Sliced into 3 sub-cycles per the 4a/4b precedent. | XL (3 sub-cycles) |
| **4c-α** | SDK install + dead-code cleanup. NEW `app/llm_client.py` wrapper (mirrors knowledge-service + worker-ai); `provider_registry_internal_url` config; Dockerfile + Dockerfile.worker SDK install (context bumped to repo root). DELETE dead `app/services/translation_runner.py` (M04 async rewrite superseded; tests already skipped). 5 smoke tests for SDK wrapper construction + lifecycle. **✅ shipped — translation-service: 285 passed (was 273); SDK 160 + worker-ai 30 + ks-svc 1491 = 1966 combined.** | M-L |
| **4c-β** | Migrate `app/workers/session_translator.py` (985 LOC): 3 buffered `client.stream()` call sites (translate chunks + compact memo + block translator v2) → `submit_and_wait(operation="translation")` SDK pattern (the calls were buffered HTTP not actual SSE despite `client.stream`). chapter_worker + worker.py thread `llm_client` through. **✅ shipped — translation-svc 286 passed (matches baseline; 5 pre-existing AsyncMock failures unchanged); SDK 160 + worker-ai 30 + ks-svc 1491 unchanged.** Drops `mint_user_jwt` from translation flows. | L |
| **4c-γ** | Migrate `app/workers/extraction_worker.py` + `app/routers/translate.py` to SDK. Drop ALL deprecated `/v1/model-registry/invoke` + `/internal/invoke` calls. **✅ shipped — translation-svc 293 passed; zero deprecated callers grep confirmed; Phase 4d unblocked.** Schema migration (translation_jobs.llm_job_id FK) DEFERRED — reverse-lookup via `llm_jobs.job_meta = {chapter_translation_id, chunk_idx}` already provides traceability (Phase 4a ADR §3.3 D6 pattern); FK adds value only for billing reconciliation. `provider_registry_service_url` config field RETAINED — `chapter_worker._get_model_context_window` still uses it for non-LLM model-metadata fetch. | L |
| **4d** | Drop deprecated `/v1/model-registry/invoke` + `/internal/invoke` + `/internal/proxy/v1/{chat/completions,completions,embeddings}` (zero callers confirmed by Phase 4c-γ grep). Keep `/internal/proxy/v1/audio/*` until audio adapter ships in Phase 5b. **✅ shipped — server.go: -291 LOC handlers, +helper `isDeprecatedProxyPath` + 410-Gone defense-in-depth guard in `doProxy`; openapi.yaml: removed `/v1/model-registry/invoke` path + InvokeModel{Request,Response} schemas; tests: removed `TestInvokeModelValidationAndUnauthorized`, swapped `chat/completions` → `v1/audio/speech` in proxy mechanic tests, added `TestDoProxyDeprecatedPathsReturn410` (3 sub-cases) + `TestDoProxyAudioPathsNotDeprecated` (2 sub-cases) regression-locks. provider-registry-svc go test green.** | M |

**Success gate**: zero service has its own HTTP client to provider-registry's old endpoints; all go through the SDK; old endpoints removed.

### Phase 5 — Audio + image + future ops

| Cycle | Deliverable | Effort |
|-------|-------------|--------|
| **5a** | Gateway adapters: `stt`, `tts`, `image_gen` operations on `/v1/llm/jobs` (or `/v1/llm/stream` for live STT) | L |
| **5b** | Migrate chat-service voice STT/TTS off `/internal/proxy/v1/audio/*` onto the new contract | M |

### Phase 6 — Hardening

| Cycle | Deliverable | Effort |
|-------|-------------|--------|
| **6a** | Gateway: rate-limit + quota enforcement at job submission (uses usage-billing-service; emits 429 with Retry-After) | M |
| **6b** | Gateway: job-level retry policy (per-chunk independent retries with exponential backoff) | M |
| **6c** | Job-level tracing (OpenTelemetry trace_id end-to-end through gateway → adapter → upstream → notification → FE) | M |

---

## 5. Per-existing-call-site migration table

Reference for Phase 4 — every current LLM call site in the monorepo and which cycle migrates it.

| Service | Call site | Today | Target | Cycle |
|---------|-----------|-------|--------|-------|
| chat-service | `services/stream_service.py:285` (`_stream_litellm`) | direct litellm | `Client.stream()` | 1c |
| chat-service | `services/voice_stream_service.py:95,127` | `/internal/proxy/v1/audio/*` | `Client.submit_job(operation="stt"/"tts")` | 5b |
| knowledge-service | `clients/provider_client.py:351` (3 extractor call sites) | `/internal/proxy/v1/chat/completions` | `Client.submit_job(operation="entity"/"relation"/"event")` with chunking | 4a |
| knowledge-service | `clients/embedding_client.py` | `/internal/embed` | `Client.submit_job(operation="embedding")` | 4a |
| translation-service | `routers/translate.py:93,163` | `/v1/model-registry/invoke` | `Client.submit_job(operation="translation")` | 4c |
| translation-service | `services/translation_runner.py:75` | `/v1/model-registry/invoke` | same | 4c |
| translation-service | `workers/extraction_worker.py:327` | `/internal/invoke` | `Client.submit_job(operation="entity")` | 4c |
| translation-service | `workers/session_translator.py:463,539,867` | `/v1/model-registry/invoke` | `Client.submit_job(operation="translation")` | 4c |

---

## 6. Risks + open questions

### 6.1 Risks

| Risk | Mitigation |
|------|------------|
| Phase 1 (streaming) regressions break chat — current chat E2E passes (Phase 3a-3c demos) | Gate Phase 1c on FE chat E2E + manual smoke; no merge until parity demonstrated |
| Phase 4 migration is 3 services × XL each — high coordination | Each service migrates independently; SDK is the contract; old endpoints kept until grep confirms zero callers |
| Gateway becomes a bottleneck (single point of failure for ALL LLM) | Gateway scales horizontally; adapter calls already stateless; chunk-pool worker model designed for parallelism |
| Notification SSE bridge adds latency — not great for "interactive" jobs | P1 streaming endpoint exists exactly for interactive case; jobs are by definition non-interactive |
| Provider-registry was Go; adapters in Go; chunking + parallel needs more Python-ish data work | Keep gateway in Go; aggregators in Go (pure data shapes); only the SDK consumer side is per-language |
| RabbitMQ topic explosion (`user.{id}.llm.{op}.done`) | Use hierarchical topic (`llm.{op}.done`) for service consumers; only fan out per-user when reaching SSE bridge |

### 6.2 Open questions for user (BEFORE Phase 0 ADR signs off)

| Q | Options |
|---|---------|
| **Q1** Job submission auth — JWT (user-issued) or X-Internal-Token (service-issued)? | (a) JWT only — every job is user-attributed. (b) Both — services can submit on user's behalf with svc-token + user_id param. **Recommend (b)** to match existing `/internal/invoke` pattern. |
| **Q2** Does FE submit jobs **directly** to gateway (via `/v1/llm/jobs` exposed through api-gateway-bff) or always via a domain service (knowledge / translation)? | (a) Direct — FE submits "extract entities for chapter X" directly. (b) Domain service mediates, owns business-job table. **Recommend (b)** so business validation (project ownership, scope rules) stays in domain. |
| **Q3** SDK regeneration cadence | Manual on contract change vs CI-generate on every spec edit. **Recommend** CI-generate, commit lockfile. |
| **Q4** Where does chunking live for translation specifically (currently translation-service handles it)? | (a) Gateway-only — drop translation's chunking; keep as fallback if needed. (b) Both layers can chunk; only gateway's used by default. **Recommend (a)** — single source of chunking truth. |
| **Q5** How to handle FE that doesn't have an SSE connection (background tab, network blip)? | RabbitMQ messages persist in `user_notifications` outbox; FE on reconnect fetches the missed notifications via REST + reconciles. Standard pattern. |
| **Q6** Hard deprecation of `/internal/invoke` and `/v1/model-registry/invoke` — what's the timeline? | Keep through Phase 4; remove in Phase 4d after grep+prod-log confirms zero callers for ≥1 release. |
| **Q7** Streaming format: do we re-frame to one canonical SSE envelope at the gateway, or pass-through whatever upstream emits? | (a) Canonical — service code stays provider-agnostic. (b) Pass-through — perf, but every consumer must learn 4 formats. **Recommend (a)** — matches P3. |
| **Q8** Job result retention — how long does a completed job's result stay queryable? | (a) 7d default, configurable. (b) Forever (storage tradeoff). **Recommend (a)**. |

### 6.3 Out of scope (for THIS plan, may be later phases)

- Multi-tenant isolation at gateway (single-tenant assumption holds for now)
- Cost-based routing (cheapest model for "good enough" job) — Track 3
- Streaming for non-chat operations (e.g., entity extraction streamed by chunk) — possible Phase 7+
- Cloud LLM pre-warming / connection pooling
- Provider failover (if upstream X dies, fall through to upstream Y)

---

## 7. What gets done THIS cycle (cycle C-LLM-PIPELINE-PLAN)

Just this document + ADR signoff. **Zero code.** Once user signs off on §6.2 questions, Phase 0a starts as a separate cycle.

## 8. Next decision needed from user

Please review §1 (principles), §3 (target architecture), and §6.2 (open questions Q1–Q8). Once those are settled this plan promotes to ADR and Phase 0 cycles open.
