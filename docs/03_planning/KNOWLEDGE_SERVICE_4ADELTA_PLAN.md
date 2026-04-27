---
name: KNOWLEDGE_SERVICE_4ADELTA_PLAN
description: Phase 4a-δ XL+ migration plan — full retirement of provider_client.py + llm_json_parser.py, K18.3 L3 passage rerank migrated to SDK
type: plan
---

# Phase 4a-δ — knowledge-service legacy LLM cleanup (XL+)

> **Status:** PLAN (2026-04-27, session 53 cycle 6)
> **Authorized by:** User chose Option A (full XL+) over 3-cycle split
> **Closes:** Phase 4a row in [`LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md`](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md#phase-4--service-migrations-to-job-pattern). After 4a-δ the legacy `/internal/proxy/v1/chat/completions` path has zero callers in knowledge-service.
> **Related ADR:** [`KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`](./KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md) §5.4 (now superseded for scope by this plan; ADR §5.4 was underspecified — missed [`context/selectors/passages.py:592`](../../services/knowledge-service/app/context/selectors/passages.py#L592)).
> **Size:** XL+ — 38 files (17 prod modify, 2 prod delete, 13 test rewrite, 3 test delete, 3 docs).

---

## 1. Scope mismatch from ADR §5.4

ADR §5.4's cleanup checklist enumerated extractor + summary call sites only. Audit (2026-04-27) found one additional production caller and a deeper test surface:

- **Missed prod caller:** [`app/context/selectors/passages.py:592`](../../services/knowledge-service/app/context/selectors/passages.py#L592) — K18.3 L3 listwise rerank. Threaded through [`context/builder.py`](../../services/knowledge-service/app/context/builder.py#L54), [`context/modes/full.py`](../../services/knowledge-service/app/context/modes/full.py#L115) (2 sites), [`routers/context.py`](../../services/knowledge-service/app/routers/context.py#L96).
- **Test surface bigger than ADR estimate:** 16 test files import `provider_client`/`ProviderClient`/`ProviderError`/`extract_json` (ADR §2.2 sized at ~407 mock sites; verified).
- **Exception home:** Surviving callers catch `ProviderError`, `ProviderRateLimited`, `ProviderCancelled`, `ProviderUpstreamError` by class. After deleting `provider_client.py` these classes need a new module.

---

## 2. Decisions baked into this plan

### D1 — Exception+model home: consolidate into `app/clients/llm_client.py`

**Decision:** Move surviving Provider* exception classes + `ChatCompletionResponse` + `ChatCompletionUsage` into [`llm_client.py`](../../services/knowledge-service/app/clients/llm_client.py) (the SDK wrapper module that already raises them). NO new "errors" module.

- **Why one module:** The wrapper raises them and synthesizes the response shape from `Job.result`. Co-locating raiser + raised type keeps a single import surface for callers.
- **Why not `provider_errors.py`:** Adds one module without adding coverage; SDK wrapper IS the provider boundary now.
- **Surviving classes:** `ProviderError`, `ProviderRateLimited`, `ProviderCancelled`, `ProviderUpstreamError`, `ChatCompletionUsage`, `ChatCompletionResponse`. Drop the 5 unused subclasses (`ProviderInvalidRequest`, `ProviderModelNotFound`, `ProviderAuthError`, `ProviderTimeout`, `ProviderDecodeError`) — confirmed via `grep "except Provider\|isinstance.*Provider"` (only the 4 surviving names are matched by class anywhere in `app/` after deletes).

### D2 — passages.py:592 rerank → `submit_and_wait(operation="chat", chunking=None)`

**Decision:** L3 rerank uses the SAME SDK call shape as `regenerate_summaries.py` chat — no chunking (single short prompt), `transient_retry_budget=1`, builds an inline `ChatCompletionResponse` from `job.result`.

- **Why operation="chat":** Rerank prompt returns a JSON list of indices but is a chat-mode call (no per-op aggregator); the fact that the caller asks for `response_format={"type":"json_object"}` is a provider hint, not a gateway operation type.
- **Why no chunking:** Rerank input is `query + N short passage previews` — fits in one prompt by construction (`max_tokens=_rerank_max_tokens(n)` capped at <2K).
- **Caller-side timeout preserved:** The existing `asyncio.wait_for(timeout=1.0s)` wraps the SDK call exactly as it wrapped `chat_completion`. K18.3's tight rerank timeout invariant is preserved.

### D3 — Drop `provider_client` thread from context modules

[`context/builder.py`](../../services/knowledge-service/app/context/builder.py), [`context/modes/full.py`](../../services/knowledge-service/app/context/modes/full.py), [`routers/context.py`](../../services/knowledge-service/app/routers/context.py) thread `provider_client: ProviderClient | None` through to `passages.rerank_passages`. After D2, threading switches to `llm_client: LLMClient | None`. Param is renamed (not aliased) — no backward-compat shim.

### D4 — Test-rewrite scope: rewrite-or-delete (no preservation of legacy mocks)

| Test file | Action | Why |
|-----------|--------|-----|
| `test_provider_client.py` | DELETE | Tests deleted module |
| `test_llm_json_parser.py` | DELETE | Tests deleted module |
| `test_rate_limiter.py` | DELETE | Tests `_TokenBucket` from deleted module |
| `test_llm_{entity,event,fact,relation}_extractor.py` | REWRITE to FakeLLMClient | Legacy mocks invalid after `client: ProviderClient` param drop |
| `test_pass2_orchestrator.py` | REWRITE | Same |
| `test_passages_selector.py` | REWRITE | New: `llm_client` param + `_RERANK_TIMEOUT_S` mock target moves |
| `test_mode_full.py` | REWRITE param threading | `provider_client` arg → `llm_client` |
| `test_internal_extraction.py` | REWRITE DI | `Depends(get_provider_client)` removed |
| `test_lifespan_startup_cleanup.py` | UPDATE | `close_provider_client` no longer called |
| `test_summary_drift.py` | REWRITE | Uses `provider_client` to seed summaries |
| `test_regenerate_summaries.py` | KEEP SDK-path tests, DROP legacy-fallback tests | Cycle 5 added SDK tests; legacy-only tests die with the legacy branch |
| `test_summary_regen_scheduler.py` | REWRITE | `provider_client` arg threaded through 4 functions |
| `test_summarize_api.py` + `test_public_summarize.py` | REWRITE DI | Same |

**No FakeProviderClient kept** — once production has zero `provider_client` references, keeping a fake muddies the test surface. `FakeLLMClient` (already used in cycle 5 SDK-path tests) is the canonical pattern.

### D5 — Telemetry: drop `provider_chat_completion_*` metrics

`provider_client.py` registers Prometheus counters/histograms (`provider_chat_completion_total`, `_duration_seconds`, `_rate_limited_total`, etc.). These are emitted by the deleted module; equivalent gateway-side metrics already exist in `provider-registry-service`. No knowledge-service-side replacement — the gateway is the single emit point now.

### D6 — Order of operations: extract-then-migrate-then-delete

Order matters because the codebase must compile after each step:

1. **Extract** (additive): `Provider*Error` + `ChatCompletionResponse` to `llm_client.py` as re-exports + new defs. `provider_client.py` re-imports its own classes from `llm_client.py` to keep API stable mid-flight.
2. **Migrate `passages.py`** to SDK (still exports legacy ProviderClient param wrapper for test-day green).
3. **Drop `provider_client` param** from each migrated caller — one file at a time, run unit tests after each.
4. **Delete** `provider_client.py` + `llm_json_parser.py` + 3 test files.
5. **Rewrite tests** to FakeLLMClient.
6. **Verify** full suite + grep for stale imports.

This order keeps each commit individually green if we ever choose to split (we won't — Option A is one commit — but the discipline catches refactor errors fast).

---

## 3. Step-by-step file map

| Step | Files | Action |
|------|-------|--------|
| 1 | `app/clients/llm_client.py` | Add `ProviderError`/`ProviderRateLimited`/`ProviderCancelled`/`ProviderUpstreamError` + `ChatCompletionUsage`/`ChatCompletionResponse` |
| 1 | `app/clients/provider_client.py` | Re-import classes from `llm_client.py` (transient — deleted in step 4) |
| 1 | `app/jobs/regenerate_summaries.py` | Switch import to `app.clients.llm_client` |
| 2 | `app/context/selectors/passages.py` | `provider_client.chat_completion` → `llm_client.submit_and_wait` |
| 2 | `app/context/selectors/passages.py` | param rename `provider_client` → `llm_client` |
| 2 | `tests/unit/test_passages_selector.py` | Rewrite to FakeLLMClient |
| 3 | `app/context/builder.py` | param rename + import switch |
| 3 | `app/context/modes/full.py` | param rename (2 sites) + import switch |
| 3 | `app/routers/context.py` | DI rename `Depends(get_provider_client)` → `Depends(get_llm_client)` |
| 3 | `tests/unit/test_mode_full.py` | Mirror prod renames |
| 4 | `app/extraction/llm_entity_extractor.py` | Drop `client: ProviderClient \| None` param + else branch |
| 4 | `app/extraction/llm_relation_extractor.py` | Same |
| 4 | `app/extraction/llm_event_extractor.py` | Same |
| 4 | `app/extraction/llm_fact_extractor.py` | Same |
| 4 | `app/extraction/pass2_orchestrator.py` | Drop `client` param (3 sites) |
| 4 | `app/jobs/regenerate_summaries.py` | Drop legacy `_call_provider` + `provider_client` from ctx |
| 4 | `app/jobs/summary_regen_scheduler.py` | Drop `provider_client` arg (4 functions) |
| 4 | `app/routers/internal_summarize.py` | Drop `provider_client` DI |
| 4 | `app/routers/internal_extraction.py` | Drop `provider_client` DI |
| 4 | `app/routers/public/summaries.py` | Drop `provider_client` DI (2 sites) |
| 4 | `app/main.py` | Drop `close_provider_client` lifespan + import |
| 4 | `app/deps.py` | DELETE `get_provider_client` |
| 5 | `app/clients/provider_client.py` | DELETE |
| 5 | `app/extraction/llm_json_parser.py` | DELETE |
| 5 | `tests/unit/test_provider_client.py` | DELETE |
| 5 | `tests/unit/test_llm_json_parser.py` | DELETE |
| 5 | `tests/unit/test_rate_limiter.py` | DELETE |
| 6 | `tests/unit/test_llm_entity_extractor.py` | REWRITE (~22 mocks → FakeLLMClient) |
| 6 | `tests/unit/test_llm_relation_extractor.py` | REWRITE (~22 mocks) |
| 6 | `tests/unit/test_llm_event_extractor.py` | REWRITE (~22 mocks) |
| 6 | `tests/unit/test_llm_fact_extractor.py` | REWRITE (~22 mocks) |
| 6 | `tests/unit/test_pass2_orchestrator.py` | REWRITE |
| 6 | `tests/unit/test_internal_extraction.py` | REWRITE DI |
| 6 | `tests/unit/test_lifespan_startup_cleanup.py` | DROP `close_provider_client` assertion |
| 6 | `tests/integration/db/test_summary_drift.py` | REWRITE |
| 7 | `tests/unit/test_regenerate_summaries.py` | DROP legacy-fallback tests; SDK-path tests stay |
| 7 | `tests/unit/test_summary_regen_scheduler.py` | REWRITE |
| 7 | `tests/unit/test_summarize_api.py` | REWRITE DI |
| 7 | `tests/unit/test_public_summarize.py` | REWRITE DI |
| 8 | `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` | Update §LLM-pipeline reference (provider_client → llm_client) |
| 8 | `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md` | Mark §5.4 supersession by this plan |
| 8 | `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` | Mark Phase 4a row complete |
| 9 | `docs/sessions/SESSION_PATCH.md` + `SESSION_HANDOFF.md` | Cycle 6 entry |

---

## 4. Verification gates (Phase 6 evidence)

| Gate | Command | Pass criterion |
|------|---------|----------------|
| Knowledge-service unit suite | `cd services/knowledge-service && pytest tests/unit -q` | All green; test count delta declared |
| Knowledge-service integration | `cd services/knowledge-service && pytest tests/integration -q` | Existing tests green |
| Stale-import grep | `grep -rn "provider_client\|ProviderClient\|extract_json\|llm_json_parser" services/knowledge-service/app services/knowledge-service/tests` | Zero hits except the 4 surviving Provider*Error names imported from `llm_client.py` |
| File-deletion proof | `ls services/knowledge-service/app/clients/provider_client.py services/knowledge-service/app/extraction/llm_json_parser.py 2>&1` | "No such file" for both |

---

## 5. Risks + mitigations

| Risk | Mitigation |
|------|-----------|
| Test count drops sharply from deleting 3 files | Counted upfront in §3; document delta in SESSION_PATCH |
| `passages.py` rerank latency regression (SDK adds job-poll overhead vs direct chat) | SDK `submit_and_wait` polls every 100ms; rerank timeout is 1s, so up to ~10 polls. Acceptable — fallback-on-timeout already exists |
| Mid-refactor crash if step ordering wrong | D6 order keeps each step compiling; commit-by-step optional but bundled into one commit per Option A scope |
| /review-impl finds missed call site | Step 6 grep gate catches stale imports; final grep is the regression lock |

---

## 6. Acceptance for Phase 4a closure

Phase 4a (4 sub-cycles) is "done" when:
- [x] α (cycle 2): gateway gaps closed (worker whitelist, retry budget, fact_extraction enum)
- [x] β (cycle 3+4): entity/relation/event/fact extractors on SDK; summaries on SDK
- [x] γ (cycle 5): regenerate_summaries on SDK with `_invoke_llm_for_summary` helper
- [ ] δ (this cycle): legacy modules deleted; tests rewritten; zero `provider_client` references in knowledge-service

After δ: K17.2b's 60s timeout ceiling is **architecturally unreachable** by knowledge-service callers. The gateway chunker + RabbitMQ terminal-event publisher handle 13K-token chapters end-to-end without HTTP keep-alive pressure.
