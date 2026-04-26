# ADR — knowledge-service migration to unified LLM contract (Phase 4a)

> **Status:** Accepted (2026-04-26, session 53 cycle 1 / DESIGN-first).
> **Decision:** **Path C** (job-pattern + chunking) sliced into 4 sub-cycles **4a-α / 4a-β / 4a-γ / 4a-δ**, each L-sized and independently green.
> **Closes-on-BUILD:** Phase 4a row in [`LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md`](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md#phase-4--service-migrations-to-job-pattern).
> **First BUILD cycle:** 4a-α (post-this DESIGN cycle). Implementation sketch §5.1 is shovel-ready.
> **Related plan:** [LLM Pipeline Unified Refactor Plan §4 Phase 4a](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md#phase-4--service-migrations-to-job-pattern).

---

## 1. Context — what Phase 4a represents

The unified-contract refactor (sessions 52, cycles 2–20) shipped Phase 1 (streaming) + Phase 2 (async-job pipeline + RabbitMQ + SSE bridge) + Phase 3 (chunking + per-op JSON aggregators) but **left every existing LLM caller on the legacy contracts**. Phase 4 is the consumer-side migration that retires `/internal/proxy/v1/chat/completions`, `/internal/invoke`, and `/v1/model-registry/invoke`. Phase 4a is the **knowledge-service slice** — by far the largest of the three (knowledge / worker-ai / translation), and the one that triggered the whole refactor when [qwen/qwen3.6-35b-a3b on a 13K-token chapter](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md#23-timeout-chain--math-doesnt-work) hit the 60s `provider_client_timeout_s` ceiling repeatedly.

This ADR pins:
- **Path** (A / B / C from the session-52 handoff §"What's NEXT")
- **Sub-cycle slicing** so no single PR is XL
- **Resolution of D1–D7** open questions raised in CLARIFY
- **Closing checklist** for when Phase 4a is "done"

---

## 2. Existing surface (audited 2026-04-26)

### 2.1 Source surface

| File | LOC | Role |
|------|-----|------|
| [`app/clients/provider_client.py`](../../services/knowledge-service/app/clients/provider_client.py) | 608 | Wrapper around `/internal/proxy/v1/chat/completions`. Exception hierarchy (Provider* family), token-bucket rate limiter, 4 MiB body cap classification, Retry-After parser. |
| [`app/extraction/llm_json_parser.py`](../../services/knowledge-service/app/extraction/llm_json_parser.py) | 563 | K17.3 — wraps `chat_completion` with: 1 HTTP-retry on retry-eligible Provider* errors + 1 fix-up turn on JSON parse / Pydantic validate failure. Total ≤3 LLM calls per `extract_json` invocation. Strips markdown code fences. |
| [`app/extraction/llm_entity_extractor.py`](../../services/knowledge-service/app/extraction/llm_entity_extractor.py) | 267 | Calls `extract_json(EntityExtractionResponse, ...)`. |
| [`app/extraction/llm_relation_extractor.py`](../../services/knowledge-service/app/extraction/llm_relation_extractor.py) | 337 | Calls `extract_json(RelationExtractionResponse, ...)`. |
| [`app/extraction/llm_event_extractor.py`](../../services/knowledge-service/app/extraction/llm_event_extractor.py) | 329 | Calls `extract_json(EventExtractionResponse, ...)`. |
| [`app/extraction/llm_fact_extractor.py`](../../services/knowledge-service/app/extraction/llm_fact_extractor.py) | 273 | Calls `extract_json(FactExtractionResponse, ...)`. **No `fact_extraction` op exists in [openapi.yaml](../../contracts/api/llm-gateway/v1/openapi.yaml) JobOperation enum yet.** |
| [`app/extraction/pass2_orchestrator.py`](../../services/knowledge-service/app/extraction/pass2_orchestrator.py) | 363 | `extract_pass2_chapter` / `extract_pass2_chat_turn`: extract_entities → gate-on-empty → `asyncio.gather(R, E, F)` → write_pass2_extraction. |
| [`app/jobs/regenerate_summaries.py`](../../services/knowledge-service/app/jobs/regenerate_summaries.py) | 732 | L0/L1/L2 summary regen scheduler (K20.3). Calls `chat_completion` at line 495. |
| [`app/routers/public/summaries.py`](../../services/knowledge-service/app/routers/public/summaries.py) | 645 | On-demand entity-bio + project summarize (FE-triggered). |
| [`app/routers/internal_summarize.py`](../../services/knowledge-service/app/routers/internal_summarize.py) | — | Internal summarize wrapper. |
| [`app/context/selectors/passages.py:592`](../../services/knowledge-service/app/context/selectors/passages.py#L592) | — | Single LLM-driven passage-selector call (small surface). |

### 2.2 Test surface (the migration cost)

| Test file | Mock-name occurrences |
|-----------|----------------------|
| `tests/unit/test_provider_client.py` | 45 |
| `tests/unit/test_llm_json_parser.py` | 41 |
| `tests/unit/test_llm_{entity,event,fact,relation}_extractor.py` | ~89 (4 files × ~22) |
| `tests/unit/test_regenerate_summaries.py` + `test_summary_regen_scheduler.py` | 171 |
| `tests/unit/test_summarize_api.py` + `test_public_summarize.py` | 61 |
| **Total** | **≈ 407** |

**~407 mock sites across ~3741 LOC of test code.** This is the real cost ceiling for any path that changes `ProviderClient.chat_completion`'s signature or replaces it entirely. The session-52 handoff's "~30 test mocks" figure was a one-extractor estimate, not the full mock surface.

### 2.3 Gateway capability (sessions 52 cycles 4–20, already shipped)

- [`POST /v1/llm/jobs`](../../contracts/api/llm-gateway/v1/openapi.yaml#L147) (and `/internal/llm/jobs`) — submit returns 202 with `job_id`; goroutine drives MarkRunning → adapter.Stream → Finalize.
- [`GET /v1/llm/jobs/{id}`](../../contracts/api/llm-gateway/v1/openapi.yaml#L224) — polling.
- `JobOperation` enum already includes `entity_extraction` / `relation_extraction` / `event_extraction` / `chat` / `embedding` / `translation` / `stt` / `tts` / `image_gen` / `completion`. **No `fact_extraction`.**
- [`jsonListAggregator`](../../services/provider-registry-service/internal/jobs/aggregator.go) (cycle 20 / Phase 3b-followup): per-op merge keys — entity (`name+kind`), relation (`subject+predicate+object+polarity`), event (`name+time_cue`). Soft-fail per chunk; populates `result.chunk_errors[]`.
- Worker chunked dispatch (cycle 17 / Phase 3c) — sequential per-chunk `adapter.Stream` with `StartChunk/EndChunk` aggregator hooks.
- RabbitMQ terminal events on `loreweave.events` topic exchange with routing key `user.<id>.llm.<op>.<status>` (cycle 11 / Phase 2c).
- [`sdks/python/loreweave_llm/`](../../sdks/python/loreweave_llm/) (cycle 5 / Phase 1b) — `Client.stream()` ready; **`Client.submit_job()` is a stub** that raises `NotImplementedError`.

### 2.4 Gateway gaps that 4a-α MUST close before consumer migration (added post /review-impl HIGH#1, HIGH#2)

The capabilities above describe **infrastructure that exists**. Cross-checked with the actual gateway code, three gaps prevent ADR §5.1's sketch from running E2E today:

1. **Worker dispatch hard-rejects non-chat operations** — [`worker.go:140`](../../services/provider-registry-service/internal/jobs/worker.go#L140-L146) gates `if operation != "chat" && operation != "completion" → LLM_OPERATION_NOT_SUPPORTED`. The aggregator factory wires `entity_extraction` (line 72) but the worker never reaches `NewAggregator(operation)` because of this gate. **Submitting `entity_extraction` today produces a `failed` job within milliseconds.**
2. **No HTTP-retry at gateway on transient upstream errors** — `adapter.Stream` returns error → [`worker.go:190-198`](../../services/provider-registry-service/internal/jobs/worker.go#L190-L198) calls `finalizeAndNotify(status="failed")` with zero retries. Today knowledge-service's `extract_json` absorbs ≤1 retry on `ProviderRateLimited` / `ProviderUpstreamError` / `ProviderTimeout` (honoring `Retry-After`). Migration without a retry-replacement = quality regression on local LLM (LM Studio) where transient 502s are routine.
3. **`fact_extraction` not in `JobOperation` enum** — already noted in §2.3 bullet 3; restated for cross-reference with HIGH#1 fix.

These gaps are **closed in 4a-α step 0** (gateway-side, see §5.1) before any knowledge-service consumer code touches the new path.

---

## 3. Decision

### 3.1 Path

**Path C — job-pattern + chunking.** Knowledge-service extractors switch from `provider_client.chat_completion` to `loreweave_llm.Client.submit_job(operation=entity_extraction, chunking={...})` and await terminal state via SDK. This is the only path that **technically fixes the original user complaint** (qwen3.6-35b-a3b on 13K-token chapters), because the gateway-side chunker + per-op JSON aggregator (already shipped Phase 3) handles >8K-token inputs without timeout pressure, and the RabbitMQ terminal-event publisher decouples response delivery from HTTP keep-alive.

Path A (surface-preserving rewrite) is rejected because it preserves the synchronous blocking semantics that caused the original timeout, just under a different transport. Path B (abandon `provider_client.py` for direct SDK chat-completion calls) is rejected because it's the same XL test-mock churn as Path C without solving chunking.

### 3.2 Sub-cycle slicing

XL-in-one-PR is rejected. Phase 4a ships as 4 sub-cycles, each ≤L:

| Sub-cycle | Scope | Size estimate |
|-----------|-------|---------------|
| **4a-α** (this cycle's BUILD target) | **Step 0 gateway prereqs** (worker op-whitelist + gateway-side single-retry — added per /review-impl HIGH#1+#2). **Step 1+** SDK `submit_job` + `wait_terminal` + `cancel_job` wired with caller-side retry budget; `entity_extraction` operation E2E proof-of-concept (1 extractor); `provider_client.py` retained as legacy path for the other 3 extractors + summaries; cancel-race regression test | XL DESIGN (this cycle) + **XL BUILD** (next cycle — upgraded from L due to gateway prereqs) |
| **4a-β** | Migrate `relation`, `event`, `fact` extractors. Adds `fact_extraction` to openapi `JobOperation` enum + jsonListAggregator + worker dispatch. | L |
| **4a-γ** | Migrate `regenerate_summaries.py` (K20.3 L0/L1/L2 scheduler) + on-demand summarize routers. Uses `chat` operation (no chunking; summaries fit single call). | L |
| **4a-δ** | Drop `provider_client.py` + `llm_json_parser.py` + 4 extractor's `client: ProviderClient` parameter. Delete `tests/unit/test_provider_client.py` + `test_llm_json_parser.py`. Adjust extractor tests to SDK fixture pattern. | M |

**Slice rationale:** mock churn is ~407 sites — slicing keeps each PR's diff <30% of that. Each sub-cycle ships green (existing 1466 knowledge-service tests pass throughout). Pattern can be reverted at sub-cycle granularity if 4a-α reveals a wrong abstraction.

### 3.3 D1–D7 resolutions (CLARIFY-approved defaults)

| ID | Question | Decision | Why |
|----|----------|----------|-----|
| **D1** | Knowledge-service receives completion how? | **Polling via SDK `Client.wait_terminal()` with exponential backoff** (250ms → 5s cap). | RabbitMQ subscriber inside knowledge-service is XL infrastructure for sub-cycle α (durable queue + binding + consumer + reconnect). Polling reuses existing GET endpoint. RabbitMQ remains live for FE notification path (Phase 2c–2f) — knowledge-service doesn't need its own subscriber until a future Phase 6 hardening cycle proves polling overhead matters. |
| **D2** | `extract_pass2_chapter` saga shape? | **B1 — Sync-saga preserved.** Each extractor function `await Client.submit_job + wait_terminal`. The orchestrator (`pass2_orchestrator._run_pipeline`) keeps its current structure: extract_entities → gate → `asyncio.gather(R, E, F)` → write. | B2 (state machine + RabbitMQ resume) requires saga state column + consumer + crash-recovery — XL infra for marginal win at hobby scale. B3 (composite gateway operation) violates P3 (gateway becomes domain-aware). |
| **D3** | K17.3 retry semantics (3 distinct retry types) goes where? | **Split the question** (per /review-impl HIGH#2). **(D3a) Parse fix-up retry**: drop entirely. **(D3b) Validate fix-up retry**: drop entirely. **(D3c) HTTP-retry on `ProviderRateLimited` / `ProviderUpstreamError` / `ProviderTimeout`**: **preserved** by SDK `wait_terminal` watching for `status=failed AND error.code IN {LLM_RATE_LIMITED, LLM_UPSTREAM_ERROR}` → caller resubmits 1× (honors `error.retry_after_s` when present) before raising `ExtractionError`. Subsequent caller-side retry kept to a budget of 1 to match K17.3's existing contract. | (D3a/D3b) Fix-up turns were costly extra LLM calls; Phase 1c chat-service migration proved tolerant Pydantic schemas at caller side outperform fix-up turns on quality eval. Soft-fail at gateway aggregator surfaces malformed chunks via `result.chunk_errors[]` for post-mortem instead of silently retrying. (D3c) Gateway-side retry is Phase 6b plan territory; until that ships, dropping HTTP-retry would regress quality on local-LLM (LM Studio) where transient 502s are routine — `feedback_local_llm_first_cloud_is_fallback` makes local LLM the calibration baseline so this regression is non-negotiable. SDK caller-side single-retry is the bridge until 6b. |
| **D4** | `fact_extraction` operation? | **(a) — Add new op.** Append `fact_extraction` to `JobOperation` enum in openapi. Add `factKey = subject + predicate + claim` to gateway's `jsonListAggregator` switch in [`aggregator.go`](../../services/provider-registry-service/internal/jobs/aggregator.go). Worker dispatch already handles unknown ops via the chat-aggregator fallback — no worker change needed beyond op-table registration. | Folding facts into events (option b) breaks the "1 op = 1 schema" invariant the gateway relies on for aggregation. Dropping facts (c) is a product decision out of scope for this ADR. |
| **D5** | Prompt ownership? | **(a) — Knowledge-service sends full system + user prompt in `input.messages[]`.** Gateway stays prompt-agnostic. Each extractor's prompt files in [`app/extraction/prompts/`](../../services/knowledge-service/app/extraction/prompts/) keep their current location. | Gateway-side prompt templates would couple the gateway to every consumer's prompt-tuning cycle — a tight feedback loop that today is contained inside knowledge-service. P3 (unified contract) doesn't require shared prompts; it requires shared transport. |
| **D6** | `extraction_jobs` table fate? | **(c) — Stays unchanged in 4a; cross-link via `llm_jobs.job_meta.extraction_job_id` (reverse-lookup pattern).** Single-column FK on `extraction_jobs` rejected per /review-impl HIGH#3 because each chapter extraction submits 4 LLM jobs (entity/relation/event/fact); 1 column ≠ 4 jobs. Each `submit_job` call sets `job_meta = {extraction_job_id, chapter_id, role: "entity"\|"relation"\|"event"\|"fact"}`; reporting queries `llm_jobs WHERE job_meta->>'extraction_job_id' = $1`. | `extraction_jobs` is a business-job table (chapter scope, project scope, user-facing status) distinct from the LLM-job substrate. Plan §3.3 endorses two-tier model. Reverse-lookup via `job_meta` matches openapi line 631 example (`{ extraction_job_id, chapter_id }`). Avoids N×M-column proliferation if a future extractor adds a 5th LLM call (e.g. claim verification). Array column / join table options rejected as premature — reverse-lookup is sufficient for hobby-scale reporting volume. |
| **D7** | worker-ai (Phase 4b territory) — touched? | **(a) — Untouched.** worker-ai keeps calling knowledge-service's `/internal/extraction/extract-item`. Only the *internals* of that endpoint change. | Phase 4b exists precisely so worker-ai's RabbitMQ migration ships independently. Coupling 4a + 4b doubles blast radius without adding value — the polling decision (D1) means the new code path stays HTTP-shaped at the worker-ai boundary. |

---

## 4. Alternatives considered

### 4.1 Path A — Surface-preserving rewrite

`ProviderClient.chat_completion` keeps its signature but internally swaps `httpx.post` for `Client.submit_job + wait_terminal`. ~30 test mocks adjust; rest of knowledge-service untouched.

**Rejected** because:
- Fails the original-complaint test: still synchronous blocking with caller-side timeout, just under a different transport.
- Hides the contract change from extractors that should be aware of it (chunking config, schema tolerance, error envelope shape).
- Creates "two right ways" — surface-preserving wrapper PLUS the SDK direct path that other services (chat-service Phase 1c-ii, future translation Phase 4c) already use. Drift again.

### 4.2 Path B — Abandon `provider_client.py`, extractors call SDK chat directly

Extractors call `Client.stream()` (or a new buffered helper), parse JSON content themselves, drop `extract_json` + `provider_client.py` wholesale. ~407 mocks rewrite, ~1171 LOC delete, but no chunking.

**Rejected** because:
- Same test-mock churn as Path C without solving the chunking half (still hits 8K-token model-context limits on big chapters).
- Forces every extractor to hand-roll JSON parsing (vs. one shared `wait_terminal` helper that returns the typed `Job.result` envelope).
- Loses the per-op aggregator semantic — partial-failure per chunk would tank the whole extraction instead of surfacing in `chunk_errors[]`.

### 4.3 Path C with single XL cycle (no slicing)

Same Path C decision but ship as one XL cycle.

**Rejected** because:
- 4 extractors + 2 summary callers + 407 mocks in one PR is unbounded review surface.
- A subtle SDK contract bug discovered mid-cycle would block the entire migration; with slicing, 4a-α catches it in a 1-extractor blast radius.
- Closing checklist below explicitly grants partial credit per sub-cycle, which a single-XL cycle would deny.

---

## 5. Implementation sketch

### 5.1 Sub-cycle 4a-α (next BUILD cycle) — Gateway prereq + SDK `submit_job` + entity_extraction proof-of-concept

**Step 0 — Gateway prerequisites (per /review-impl HIGH#1 + HIGH#2; ship FIRST inside 4a-α before any knowledge-service code touches the new path):**

1. **Whitelist non-chat operations** in [`worker.go:140`](../../services/provider-registry-service/internal/jobs/worker.go#L140-L146): replace the hard-reject with a per-op switch that allows `chat`, `completion`, `entity_extraction`, `relation_extraction`, `event_extraction`. (`fact_extraction` joins in 4a-β.) Other operations (embedding/translation/stt/tts/image_gen) keep the LLM_OPERATION_NOT_SUPPORTED gate. Aggregator factory at [`aggregator.go:72`](../../services/provider-registry-service/internal/jobs/aggregator.go#L72) is already wired — only the worker gate moves.
2. **Gateway-side single-retry on transient upstream errors** (per D3c): when `adapter.Stream` returns `provider.ErrUpstreamRateLimited`, `provider.ErrUpstreamTransient`, or `provider.ErrUpstreamTimeout` (NEW typed errors at adapter layer; today everything funnels into a generic error), worker retries the same chunk once, honoring `Retry-After` parsed from the upstream response. Caller-side retry in SDK (D3c clause) is the bridge IF gateway-side retry isn't ready by 4a-α; gateway-side is preferred because it preserves chunk-level granularity (only the failing chunk retries, not the whole multi-chunk job).
3. **Tests at gateway side**: `worker_test.go` gains a per-op routing test (entity_extraction → jsonListAggregator path proven in unit) + a transient-retry test (httptest server returns 502 once then 200 → expect 1 retry + completed). +5 tests minimum.

**Step 1 — SDK changes** ([`sdks/python/loreweave_llm/`](../../sdks/python/loreweave_llm/)):

```python
# client.py
async def submit_job(
    self,
    *,
    operation: JobOperation,
    model_source: ModelSource,
    model_ref: str,                            # str (per /review-impl MED#5) — SDK validates UUID-shape
    input: dict[str, Any],
    chunking: ChunkingConfig | None = None,
    callback: CallbackConfig | None = None,
    trace_id: str | None = None,
    job_meta: dict[str, Any] | None = None,
) -> SubmitJobResponse:
    """POST /v1/llm/jobs (jwt) or /internal/llm/jobs (internal). Returns 202 envelope.

    Raises LLMInvalidRequestError if model_ref isn't a UUID-shaped string;
    no UUID() coercion at extractor sites — extractor signatures stay `model_ref: str`.
    """

async def get_job(self, job_id: str) -> Job:
    """GET /v1/llm/jobs/{id}. Returns full Job state.

    Polling-side HTTP timeout: httpx.Timeout(connect=5, read=10, write=5, pool=5).
    Per-poll caps are independent of the wall-clock-less wait_terminal loop —
    a slow poll fails fast and the next iteration retries from the backoff schedule.
    """

async def wait_terminal(
    self,
    job_id: str,
    *,
    poll_interval_s: float = 0.25,
    max_poll_interval_s: float = 5.0,
    poll_backoff: float = 1.5,
    transient_retry_budget: int = 1,           # per /review-impl HIGH#2 D3c
) -> Job:
    """Poll get_job until status ∈ {completed, failed, cancelled}.

    Exponential backoff: 250ms → 375ms → ... → 5s cap. NO wall-clock
    timeout — polling continues until terminal or HTTP error. Caller
    handles cancellation by calling Client.cancel_job(job_id).

    Transient-retry semantic (D3c bridge until Phase 6b): if a terminal
    job has status=failed AND error.code IN {LLM_RATE_LIMITED,
    LLM_UPSTREAM_ERROR}, AND transient_retry_budget>0, raises
    LLMTransientRetryNeededError carrying the original input (caller
    decides to resubmit). The SDK does NOT auto-resubmit because
    inputs aren't retained client-side — the extractor function owns
    resubmission with the same args. Honors error.retry_after_s when present.

    Per-poll HTTP failures (network blip while polling) consume the
    transient_retry_budget too — at zero, raise LLMHttpError.
    """

async def cancel_job(self, job_id: str) -> None:
    """DELETE /v1/llm/jobs/{id}. 204 → None; 409 (already terminal) → None."""
```

**Step 2 — Entity extractor migration** ([`app/extraction/llm_entity_extractor.py`](../../services/knowledge-service/app/extraction/llm_entity_extractor.py)):

```python
async def extract_entities(
    *,
    text: str,
    known_entities: list[str],
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,                                 # stays str (MED#5)
    llm_client: LLMClient | None = None,            # NEW: loreweave_llm.Client
    client: ProviderClient | None = None,           # KEEP: legacy fallback
) -> list[EntityCandidate]:
    if llm_client is None:
        # Legacy path — preserved through 4a-α, removed in 4a-δ
        return await _extract_via_provider_client(...)

    # New path. Caller-side retry budget = 1 (D3c bridge).
    for attempt in range(2):
        submit = await llm_client.submit_job(
            operation="entity_extraction",
            model_source=model_source,
            model_ref=model_ref,                     # SDK validates UUID-shape
            input={
                "messages": _build_extraction_messages(text, known_entities),
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            },
            chunking=ChunkingConfig(strategy="paragraphs", size=8),
            trace_id=trace_id_var.get(None),
            job_meta={"extraction_job_id": ..., "chapter_id": ..., "role": "entity"},  # D6 reverse-lookup
        )
        try:
            job = await llm_client.wait_terminal(submit.job_id)
            break
        except LLMTransientRetryNeededError:
            if attempt == 1:
                raise
            continue                                 # one retry on transient, then bubble
    if job.status != "completed":
        raise ExtractionError(stage="provider", last_error=Exception(job.error.message))
    return _parse_entities_with_tolerance(job.result.get("entities", []))
```

**Step 3 — Tolerant parser** (uses the [feedback_llm_schema_tolerate_filter_dont_reject](../../C:\Users\NeneScarlet\.claude\projects\d--Works-source-lore-weave\memory\feedback_llm_schema_tolerate_filter_dont_reject.md) pattern):

```python
def _parse_entities_with_tolerance(raw: list[dict]) -> list[EntityCandidate]:
    """Soft-validate per item; drop items missing required fields, log count.

    Per /review-impl LOW#11 explicit field semantics:
      Required (drop item if absent or not a string):
        - name
        - kind
      Optional (defaulted on absence):
        - aliases     → []
        - confidence  → 0.5
      Required-by-anchoring (drop item if absent — anchor loader needs it
      to attach to a glossary anchor row):
        - evidence_passage_id

    Replaces K17.3's all-or-nothing fix-up retry. Per cycle-20
    jsonListAggregator contract: gateway already merged across chunks;
    this function just narrows each merged item to the local Pydantic
    shape, skipping malformed items rather than failing the whole batch.
    Drops a `dropped_count` Prometheus counter via metrics.knowledge_extraction_dropped_total.
    """
```

**Helper location** (per /review-impl LOW#10): `_build_extraction_messages` is **inlined per extractor** in 4a-α (matches today's per-extractor message-build helpers). 4a-β consolidates into shared `app/extraction/messages.py` if the pattern stabilizes across all 4 extractors — defer the consolidation decision to 4a-β CLARIFY.

**Step 4 — Knowledge-service `deps.py`** — register new SDK client lifespan singleton next to existing `provider_client`:

```python
async def get_llm_client() -> LLMClient:
    """Per-worker singleton, mirrors get_provider_client lifecycle."""
```

**Pass 2 orchestrator** ([`pass2_orchestrator.py`](../../services/knowledge-service/app/extraction/pass2_orchestrator.py)) — add `llm_client: LLMClient | None = None` param, thread to `extract_entities` only in 4a-α (other 3 extractors keep `provider_client` until 4a-β).

**Tests:** ~22 mocks in `test_llm_entity_extractor.py` adjust to AsyncMock-on-LLMClient instead of AsyncMock-on-ProviderClient. New test file `tests/unit/test_llm_client.py` (~15 tests) covers SDK polling + backoff + cancel + terminal-states.

**Live smoke:** `submit_job(operation=entity_extraction, chunking={strategy:'paragraphs',size:8})` against qwen3.6-35b-a3b on the Speckled Band test fixture (13K tokens / ~70 paragraphs → ~9 chunks). Verify `result.entities` returns N entities and `result.chunk_errors[]` is empty.

### 5.2 Sub-cycle 4a-β — relation/event/fact extractors

**Gateway changes**:
- Append `fact_extraction` to `JobOperation` enum in [openapi.yaml](../../contracts/api/llm-gateway/v1/openapi.yaml).
- Append `factKey(subject + predicate + claim)` to [`internal/jobs/aggregator.go`](../../services/provider-registry-service/internal/jobs/aggregator.go) op-table switch.
- Worker dispatch already handles via Phase 3b-followup factory — no worker change needed beyond enum recognition.
- 5 new tests in [`aggregator_test.go`](../../services/provider-registry-service/internal/jobs/aggregator_test.go): factKey dedup, polarity-distinct, malformed-chunk soft-fail, missing-list-field, alias-union semantic.

**Knowledge-service changes**:
- 3 extractors get the same `llm_client | None` param + new SDK call path.
- ~66 test mocks adjust (3 files × ~22 each).
- `pass2_orchestrator` now threads `llm_client` to all 4 extractors; legacy `client: ProviderClient` removed from extractor signatures.

**Live smoke:** full `extract_pass2_chapter` against Speckled Band — entities → R/E/F gather → write_pass2 — confirm Neo4j receives merged entities/relations/events/facts.

### 5.3 Sub-cycle 4a-γ — summaries migration

**Knowledge-service changes**:
- [`regenerate_summaries.py:495`](../../services/knowledge-service/app/jobs/regenerate_summaries.py#L495) `chat_completion` call → `submit_job(operation="chat", chunking=None)` + `wait_terminal`.
- [`routers/public/summaries.py:567,628`](../../services/knowledge-service/app/routers/public/summaries.py#L567) on-demand summarize → same.
- [`internal_summarize.py:120,133`](../../services/knowledge-service/app/routers/internal_summarize.py#L120) → same.
- ~232 test mocks adjust (regenerate + scheduler + summarize_api + public_summarize).
- **No chunking for summaries** — they fit in one LLM call; pass `chunking=None`.

**Live smoke:** trigger global L0 regen scheduler iteration; verify `summary_regen_cost_usd_total` counter increments and DB row updates with new summary text.

### 5.4 Sub-cycle 4a-δ — cleanup

- Delete [`app/clients/provider_client.py`](../../services/knowledge-service/app/clients/provider_client.py).
- Delete [`app/extraction/llm_json_parser.py`](../../services/knowledge-service/app/extraction/llm_json_parser.py).
- Delete `tests/unit/test_provider_client.py` + `test_llm_json_parser.py` (~86 tests gone, NOT replacements — the SDK has its own test suite in `sdks/python/tests/`).
- Remove `client: ProviderClient | None = None` param from all 4 extractor signatures + `pass2_orchestrator` + `regenerate_summaries` + summarize routers.
- **Metrics sunset (per /review-impl MED#8)**: `provider_chat_completion_total{outcome}` + `provider_chat_completion_duration_seconds{outcome}` → REPLACED, not deleted. Add equivalent caller-side counters to [`app/metrics.py`](../../services/knowledge-service/app/metrics.py): `knowledge_llm_job_total{operation, outcome}` + `knowledge_llm_job_duration_seconds{operation, outcome}` recorded around `wait_terminal` calls. Outcome enum extended: `ok`, `failed_provider`, `failed_decode`, `failed_transient_after_retry`, `cancelled`. Plus a parallel sunset note in the dashboard JSON: knowledge-service Grafana panels referencing `provider_chat_completion_*` need updating in the same PR — list the panel IDs in commit body. Gateway-side `llm_jobs_terminal_total{operation, status}` (already shipped Phase 2c) provides the system-wide view; per-service caller counter gives extraction-team-local view.
- Update [`KNOWLEDGE_SERVICE_ARCHITECTURE.md`](./KNOWLEDGE_SERVICE_ARCHITECTURE.md) §LLM-pipeline reference.

**Verify:** knowledge-service `pytest` regression-budget = `count_at_4a-δ_entry - 86` (per /review-impl LOW#12 — the 1466 figure was the session-51 close baseline; by 4a-δ entry the count grows from 4a-α/β/γ test additions, so the literal 1380 number is misleading). Concretely: capture pytest count at the start of the 4a-δ CLARIFY phase, subtract 86 (deletions), assert post-δ count ≥ that. Live smoke: full extraction E2E + summary regen scheduler tick.

### 5.5 Recording-order semantic + cancel-race correctness (cross-cycle)

Knowledge-service's [`extraction_jobs`](../../services/knowledge-service/app/db/repositories/extraction_jobs.py) row continues to be the business-job source of truth. **No new column added** (per D6 reverse-lookup decision); cross-link is `llm_jobs.job_meta = {extraction_job_id, chapter_id, role}` populated at every `submit_job` call. On `wait_terminal` completion, `extraction_jobs.status` flips to terminal in the SAME transaction as the Pass 2 Neo4j write.

**Cancel-race correctness (corrected per /review-impl MED#4):** the cycle-10 invariant at [`provider-registry/internal/jobs/repo.go Finalize WHERE status='running'`](../../services/provider-registry-service/internal/jobs/repo.go) guarantees gateway auto-completion cannot overwrite a cancelled `llm_jobs` row. **Cancellation itself CAN happen** mid-extraction — user/UI calls `DELETE /v1/llm/jobs/{id}` from FE through gateway while knowledge-service worker is in `wait_terminal`. Worker's next poll sees `status=cancelled` and `wait_terminal` returns the cancelled `Job`. Knowledge-service orchestrator MUST handle three terminal outcomes distinctly:
- `status=completed` → parse result + write Pass 2
- `status=failed` → raise `ExtractionError` (with possible D3c transient retry per §5.1 Step 2 logic)
- `status=cancelled` → flip `extraction_jobs.status = "cancelled"`, do NOT write Pass 2, do NOT raise (operator-initiated, not a fault)

Tests in 4a-α MUST cover the cancelled-mid-flight path explicitly — feature test that submits a job, cancels via `DELETE`, awaits worker recovery; assert `extraction_jobs.status = cancelled` + no Neo4j write occurred.

---

## 6. Open questions deferred to BUILD-cycle CLARIFY

These do not block the ADR but each BUILD cycle's CLARIFY phase MUST resolve:

1. **(4a-α)** What is the per-chunk paragraph size for `entity_extraction`? Plan §4 uses `size=8` paragraphs as gateway default. For Speckled Band's ~70 paragraphs that's ~9 chunks — is this optimal for known-entities deduplication, or should the chunker prefer larger chunks (~15 paragraphs) so the LLM has more context for cross-paragraph entity references?
2. **(4a-α)** Does `wait_terminal` need a per-poll timeout (network-level) distinct from the no-wall-clock-cap on the overall wait? §5.1 Step 1 specifies `httpx.Timeout(connect=5, read=10, write=5, pool=5)` for polling GETs (which are <1s normally); confirm under live smoke that this doesn't false-trigger when gateway is under load.
3. **(4a-α)** **Cross-chunk known_entities priming** (per /review-impl MED#6) — gateway dispatches per-chunk LLM calls against the SAME prompt; entities discovered in chunk-1 are NOT propagated to chunk-2's prompt. Today's synchronous orchestrator builds `all_known = list(set(known_entities + entity_names))` after step 1 and feeds it to R/E/F. Path C breaks this propagation. Mitigation candidates: (a) larger chunk size so single-chunk path dominates (~15 paragraphs covers most chapters in single chunk), (b) defer to future Phase 6 where gateway carries chunk-N entities into chunk-N+1 prompt (cracks D5 "prompt-agnostic gateway"), (c) accept reduced cross-chunk entity dedup quality — `entityKey(name+kind)` still merges whatever the LLM does canonicalize. **Recommend (a) at 4a-α + measure quality eval delta.**
4. **(4a-α)** **Polling DB load profile** (per /review-impl MED#7) — at hobby scale (N=2 chapter-parallel, ~4.5min job, 5s poll cap) ≈ 432 GETs sustained. Each GET hits Postgres `llm_jobs` row. Acceptable today but worth measuring during live smoke. Mitigations if pain shows: gateway adds `Last-Modified`/`ETag` for 304 cheap-poll, or knowledge-service moves to RabbitMQ subscriber (Phase 6 territory). Add a Prometheus counter `knowledge_llm_poll_total{outcome}` in 4a-α to make this measurable.
5. **(4a-α / 4a-β)** **Gateway concurrency limit** (per /review-impl MED#9) — D2 sync-saga keeps `asyncio.gather(R, E, F)` so each chapter bursts 3 concurrent `submit_job` calls; N parallel chapters × 3-4 ops = 9-12 concurrent goroutines hitting upstream LM Studio (which serves sequentially anyway). Today gateway has no per-user in-flight cap. Risk: queue-depth spike at LM Studio. Phase 6a "rate-limit at submission" exists for this; either (a) ship a stop-gap per-user in-flight cap inside 4a-α gateway prereqs, or (b) document the burst pattern and rely on Phase 6a. **Recommend (b) + add metric `knowledge_llm_inflight_jobs{user_id}` for visibility.**
6. **(4a-β)** Does `fact_extraction` need a separate prompt template, or can it reuse `event_extraction`'s system prompt with a different user prompt? (Current `llm_fact_extractor.py` has its own prompt; mirror in 4a-β unless prompts converge.)
7. **(4a-γ)** Does on-demand summarize from FE benefit from `/v1/llm/stream` (P1 — user is watching) instead of `/v1/llm/jobs` (P2 — fire-and-forget)? Plan §3.2 says streaming is the right contract for "user is watching". If so, 4a-γ splits into γ1 (regen scheduler → jobs) + γ2 (FE summarize → stream).
8. **(4a-δ pre-delete)** Are there any external callers of knowledge-service that depend on the `Provider*` exception class hierarchy? `git grep -rn "ProviderError\|ProviderRateLimited\|ProviderUpstreamError\|ProviderTimeout\|ProviderModelNotFound\|ProviderAuthError\|ProviderInvalidRequest\|ProviderDecodeError"` outside `services/knowledge-service/` MUST return zero before deletion. Currently grep is local to knowledge-service — verify in 4a-δ CLARIFY.

---

## 7. Closing checklist (gates Phase 4a fully cleared)

A sub-cycle's plan-row [x] only counts when ALL of the following are true. Phase 4a as a whole is "cleared" when 4a-δ ships green AND `git grep -i 'provider_client'` in `services/knowledge-service/` returns zero matches.

### Per sub-cycle:

- [ ] **4a-α**: (Step 0 gateway prereqs per /review-impl HIGH#1+#2) `worker.go:140` whitelists `entity_extraction` + `relation_extraction` + `event_extraction` operations; gateway-side single-retry on `provider.ErrUpstreamRateLimited`/`ErrUpstreamTransient`/`ErrUpstreamTimeout` typed errors with `Retry-After` honored; +5 `worker_test.go` tests (per-op routing + transient retry). (Step 1+) SDK `submit_job` + `wait_terminal` + `cancel_job` shipped with ≥15 unit tests including transient-retry budget logic; entity extractor migrated; `pass2_orchestrator` threads `llm_client` to entity step; other 3 extractors still on `provider_client`. Live smoke: Speckled Band 13K-token chapter through `extract_entities` returns N entities via gateway job. **Cancel-race regression test** (per /review-impl MED#4) — submit job, DELETE mid-flight, assert `extraction_jobs.status="cancelled"` + no Neo4j write. SESSION_PATCH header + handoff updated.
- [ ] **4a-β**: openapi `JobOperation` enum gains `fact_extraction`; `aggregator.go` adds `factKey`; 5 new aggregator tests. Relation/event/fact extractors migrated. Live smoke: full `extract_pass2_chapter` E2E through gateway with all 4 ops.
- [ ] **4a-γ**: `regenerate_summaries.py` + `internal_summarize.py` + `routers/public/summaries.py` migrated. Live smoke: scheduler tick produces summary row + cost counter increment.
- [ ] **4a-δ**: `provider_client.py` + `llm_json_parser.py` + corresponding tests deleted. Knowledge-service `pytest` green. Architecture doc updated. `git grep` regression locks added (lint cycle): forbid `import.*provider_client` outside historical references.
- [ ] **/review-impl** invoked AFTER each sub-cycle's BUILD/VERIFY; 0 unresolved HIGH/MED.
- [ ] Plan row in [`LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md#phase-4--service-migrations-to-job-pattern) updated with [x] per sub-cycle.

### Cross-cycle invariants:

- [ ] Knowledge-service `pytest` count never regresses (additions + deletions tracked sub-cycle-by-sub-cycle in SESSION_PATCH).
- [ ] No `import litellm` / `import openai` / `import anthropic` ever appears in knowledge-service (Phase 1e lint rule already enforces this).
- [ ] Each sub-cycle's commit message names the sub-cycle ID (4a-α / 4a-β / 4a-γ / 4a-δ) and the closing-checklist item it ticks.

---

## 8. References

- [LLM Pipeline Unified Refactor Plan](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md) — §4 Phase 4a row, §3 target architecture, §6.2 Q1–Q8 user-approved decisions
- [openapi.yaml — llm-gateway v1](../../contracts/api/llm-gateway/v1/openapi.yaml) — JobOperation enum, SubmitJobRequest schema, Job result schemas
- [`aggregator.go` — jsonListAggregator](../../services/provider-registry-service/internal/jobs/aggregator.go) — per-op merge keys (cycle 20 / Phase 3b-followup)
- [`sdks/python/loreweave_llm/`](../../sdks/python/loreweave_llm/) — Phase 1b SDK foundation
- [SESSION_PATCH session 52](../sessions/SESSION_PATCH.md) cycles 2–20 — refactor narrative
- [SESSION_HANDOFF session 52](../sessions/SESSION_HANDOFF.md) §"What's NEXT" — Path A/B/C tradeoffs
- Memory: [feedback_llm_schema_tolerate_filter_dont_reject](../../C:\Users\NeneScarlet\.claude\projects\d--Works-source-lore-weave\memory\feedback_llm_schema_tolerate_filter_dont_reject.md) — caller-side tolerance > fix-up retry, evidence basis for D3
- Memory: [feedback_local_llm_first_cloud_is_fallback](../../C:\Users\NeneScarlet\.claude\projects\d--Works-source-lore-weave\memory\feedback_local_llm_first_cloud_is_fallback.md) — quality cycles target LM Studio gemma-4-26b-a4b baseline / qwen3.6-35b-a3b stretch
- ADR pattern reference: [`KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md`](./KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md) — C16 DESIGN-first cycle template
