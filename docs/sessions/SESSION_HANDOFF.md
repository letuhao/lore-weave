# Session Handoff — Session 53 (4 cycles shipped · Phase 4a-α/β COMPLETE — all 4 Pass 2 extractors migrated · 4a-γ next)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-27 (session 53, cycles 1-4 shipped)
> **HEAD:** `<pending>` (Phase 4a-β; Phase 4a-α-followup @ `309913bb`; Phase 4a-α BUILD @ `6697d8d6`; ADR @ `b2f577e`; Session 52 closed at `c0420d2`)
> **Branch:** `main` (ahead of origin — user pushes manually)

## Session 53 cycle 4 — Phase 4a-β · relation/event/fact extractors migrated · /review-impl caught 7 issues (all 6 actionable fixed inline)

**What shipped:** All 3 remaining Pass 2 extractors (relation/event/fact) now route through unified LLM gateway with the same SDK + chunking + system+user prompt + tolerant-parser pattern as entity extractor. Gateway gains `fact_extraction` operation + `factKey` aggregator + 2 mid-cycle bug fixes (validJobOperations + DB CHECK constraint). **Phase 4a-α tier COMPLETE**: all 4 Pass 2 extractors uniformly migrated.

**24 files** across gateway/contracts/ks-svc/SDK/tests. Reference impl: this cycle's 3 extractor migrations follow entity extractor's 4a-α + followup pattern verbatim. Live smoke verified: `entities=5, relations=5, events=2, facts=2` — all 4 ops complete end-to-end against qwen3.6-35b-a3b.

### `/review-impl` round 4 — caught 7 issues, all 6 actionable fixed inline

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | factKey docstring claimed "polarity contradictions surface as separate rows" but actually merges → corrected docstring + test name + cross-ref to D-PHASE6-FACT-POLARITY-IN-KEY |
| 2 | 🟡 MED | mergeKnownKeys silently overwrote non-null with null when winner had null value (data loss for fact subject + entity evidence_passage_id) → fix prefers loser-non-null + 2 regression-lock tests |
| 3 | 🟡 MED | 5-place sync invariant (worker / API / DB CHECK / openapi / SDK Literal) only locked worker↔API → widened test to grep openapi.yaml + migrate.go + jobs_handler.go in one Go test |
| 4 | 🟢 LOW | Multi-chunk only verified at unit-test level for entity → 3 NEW per-extractor multi-paragraph chunking-invariant tests |
| 5 | 🟢 LOW | Null-enum cases not tested → `kind=None` / `type=None` added to drops_malformed tests |
| 6 | 🟢 LOW | Duplicate `import pytest` in appended sections → cleaned |
| 7 | 🔵 COSMETIC | Test naming clarity | Skip |

### Mid-cycle bugs caught + fixed during BUILD
- jobs_handler.go `validJobOperations` rejected fact_extraction → fixed + locked
- DB CHECK constraint on `llm_jobs.operation` rejected fact_extraction insert → additive ALTER migration

### Verify evidence
```
gateway:  go test ./internal/... → ALL GREEN
sdk:      pytest tests/ → 37 passed in 0.32s
ks-svc:   pytest tests/unit/ → 1633 passed in 10.99s (was 1611 cycle-3 baseline; +22)
live smoke: 4/4 ops completed (no chunk_errors)
```

### What's NEXT for the next agent

**4a-γ (L)** — migrate `regenerate_summaries.py` + `routers/public/summaries.py` + `routers/internal_summarize.py` to use SDK with `chat` operation (no chunking — summaries fit single call). Reference impl: 4a-β pattern × 3 sites.

ADR §6 Q7 to resolve in 4a-γ CLARIFY: does on-demand FE summarize benefit from `/v1/llm/stream` (P1) instead of `/v1/llm/jobs` (P2)? If yes, split 4a-γ into γ1 (regen scheduler → jobs) + γ2 (FE summarize → stream).

**Deferred items added in cycles 2-4:**
- D-PHASE6-XCHUNK-PRIMING — cross-chunk known_entities priming (cycle 3 MED#1)
- D-PHASE6-FACT-POLARITY-IN-KEY — adding polarity to factKey (cycle 4 MED#1)
- D-PHASE6-AGGREGATOR-NULL-MERGE — mostly mitigated by MED#2 fix; track residual for parallel-chunk aggregator design

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state
2. `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`
3. This handoff file
4. **Reference for 4a-γ**: Phase 4a-β at HEAD `<this-commit>` — extractor pattern; summaries are simpler (no `entities` param, no chunking)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For 4a-γ: `python scripts/workflow-gate.py size L 6 4 1` then `phase clarify`
3. Live smoke target: `019dc738-a6b7-7bff-b953-b47868ae7db0` (qwen3.6-35b-a3b for `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

---

## Session 53 cycle 3 — Phase 4a-α-followup · chunked entity extraction LIVE

## Session 53 cycle 3 — Phase 4a-α-followup · chunked entity extraction LIVE

**What shipped:** 5 files restructure entity prompt as system+user + re-enable `ChunkingConfig(strategy='paragraphs', size=15)`. Closes /review-impl cycle 2 HIGH#1 (chunking-shreds-combined-prompt) end-to-end. Live smoke on Speckled Band first 30 paragraphs (10854 chars) → gateway dispatches **2 sequential chunks** → **34 deduped entities** → no `chunk_errors[]`. **The original-complaint cycle (qwen3.6-35b-a3b on 13K-token chapters) is now FULLY supported.**

**Files (5)**:
- NEW `entity_extraction_system.md` — system-only template (instructions + KNOWN_ENTITIES + rules + examples) with chunking-self-contained directive; NO `{text}` placeholder
- MOD `llm_prompts/__init__.py` — PromptName Literal +'entity_system' + _load_raw mapping
- MOD `llm_entity_extractor.py` — SDK path now sends `[{role:system,content:system_prompt},{role:user,content:text}]` with chunking re-enabled; legacy K17.2 combined-template path preserved
- MOD `test_llm_entity_extractor.py` — assert chunking + 2-message structure + 2 new regression-lock tests
- MOD `test_llm_prompts.py` — TEXT_BEARING_PROMPT_NAMES skips entity_system + 2 entity_system-dedicated tests + 1 silent-drop regression-lock

### `/review-impl` round 3 — caught 1 MED + 3 LOW + 1 COSMETIC; all 4 actionable findings fixed inline

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| 1 | 🟡 MED | Cross-chunk discovered-entity priming gap — system message KNOWN_ENTITIES preserved across chunks but entities discovered in chunk N NOT propagated to chunk N+1 prompt; "Helen Stoner" in chunk 0 + "Miss Stoner" in chunk 1 → 2 distinct entities | NEW regression-lock test pins current behavior with explicit Phase 6 fix path; deferred D-PHASE6-XCHUNK-PRIMING |
| 2 | 🟢 LOW | Unit tests don't exercise multi-chunk dispatch | NEW test `test_extract_entities_via_llm_client_chunking_invariant_for_multi_paragraph_input` asserts extractor SENDS ChunkingConfig on 30-paragraph input |
| 3 | 🟢 LOW | System prompt's "Chunking note" misleading on single-call path | Wording softened: "may be a chunk OR the entire chapter" + explicit "do NOT caveat" |
| 4 | 🟢 LOW | `load_prompt("entity_system", text=...)` silently drops `text` kwarg | NEW regression test documents the silent-drop gotcha + cross-references intended use site |
| 5 | 🔵 COSMETIC | Example A KNOWN_ENTITIES literal | Skip |

### Verify evidence
```
ks-svc unit tests: 1611/1611 PASS in 10.63s (was 1608; +3 new)
LIVE SMOKE: Speckled Band 30 paragraphs (10854 chars)
  → 2 chunks dispatched sequentially (chunks_done 0→1/2→2/2)
  → 34 deduped entities returned
  → no chunk_errors[]
  → high-confidence proper nouns merged correctly across chunks
```

### What's NEXT for the next agent

**4a-β (L)** — migrate relation/event/fact extractors to the SDK pattern. Same surface as 4a-α (extractor signature + tolerant parser + orchestrator threading) × 3 extractors. Gateway changes:
- Add `fact_extraction` to `JobOperation` enum in [openapi.yaml](contracts/api/llm-gateway/v1/openapi.yaml)
- Add `factKey(subject + predicate + claim)` to gateway's `jsonListAggregator` switch + 5 new aggregator tests
- Worker whitelist already covers entity/relation/event_extraction; +`fact_extraction` to `streamableOperations` map

Knowledge-service changes:
- Restructure relation/event/fact prompts as system+user (mirror entity_extraction_system.md pattern) — system has rules + KNOWN_ENTITIES, user has chapter text only
- 3 extractors get `llm_client | None = None` param + new SDK path branch + tolerant parser
- `pass2_orchestrator` threads `llm_client` to all 4 extractors (legacy `client: ProviderClient` removed from extractor signatures only after 4a-δ)
- ~66 test mocks adjust (3 files × ~22 each)

**Reference impl:** Phase 4a-α at HEAD `6697d8d6` (entity migration) + this cycle's followup pattern. Each extractor follows the same shape.

**5 ADR §6 deferred questions still relevant:**
- Q3 cross-chunk known_entities priming (now D-PHASE6-XCHUNK-PRIMING; document only, fix in Phase 6)
- Q4 polling DB load profile (knowledge_llm_poll_total metric exists; needs measurement)
- Q5 gateway concurrency limit (knowledge_llm_inflight_jobs gauge exists; cap deferred to Phase 6a)
- Q6 fact_extraction prompt template (own vs share with event) — RESOLVE in 4a-β CLARIFY
- Q7 on-demand summarize: P1 stream vs P2 jobs (4a-γ)

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle metadata at top
2. `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a sub-cycle rows
4. This handoff file
5. **For 4a-β reference**: `services/knowledge-service/app/extraction/llm_prompts/entity_extraction_system.md` (the system+user split pattern to mirror)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` to confirm prior cycle closed
2. For 4a-β: `python scripts/workflow-gate.py size L 8 5 1` then `phase clarify`
3. Infra: `docker ps --filter name=infra-` — provider-registry + knowledge-service + LM Studio reachable
4. Live smoke target: `019dc738-a6b7-7bff-b953-b47868ae7db0` (qwen3.6-35b-a3b user_model registered for `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

---

## Session 53 cycle 2 — Phase 4a-α BUILD live · /review-impl caught 9 issues all fixed inline

**What shipped:** Knowledge-service entity extraction now routes through the unified LLM gateway end-to-end. Live smoke against qwen/qwen3.6-35b-a3b returned `{Sherlock Holmes/Person, 221B Baker Street/Location, Dr. Watson/Person, Professor Moriarty/Person}` — **the original-complaint cycle that triggered the entire refactor is PROVEN end-to-end through the unified contract.**

**22 files** (gateway 6 + SDK 5 + ks-svc 9 + infra 1 + contracts 1) implementing ADR §5.1 Steps 0-5:
- **Step 0a — gateway worker op-whitelist** (`worker.go:140`): chat/completion/entity_extraction/relation_extraction/event_extraction now route past the gate; isStreamableOperation map + 3 routing tests
- **Step 0b — typed transient errors + gateway-side retry** (`provider/errors.go` NEW): ErrUpstreamRateLimited+Transient+Timeout+Permanent + IsTransientUpstreamError + RetryAfter + ClassifyUpstreamHTTP factory; openCompletionStream + anthropic_streamer classify HTTP status into typed shape; worker.streamWithRetry/streamWithBudget honor Retry-After + 1 retry per /review-impl MED#5 SHARED across chunks (not per-chunk)
- **Step 1 — SDK jobs API** (`sdks/python/loreweave_llm/`): submit_job/get_job/wait_terminal/cancel_job + multi-tenant per-call user_id on jobs AND stream methods; LLMTransientRetryNeededError raised when budget>0; httpx polling 250ms→5s
- **Step 2 — entity extractor migration**: `_extract_via_llm_client` routes via SDK when llm_client param supplied; `chunking=None` per /review-impl HIGH#1 — chunked extraction deferred to 4a-α-followup because current K17.1 prompt as single user message would shred under gateway's `\n\n` chunker; cancelled job RAISES ExtractionError(stage=cancelled) per /review-impl MED#3; tolerant parser drops items missing required fields with metric-bumped reasons
- **Step 3 — knowledge-service wrapper** (`app/clients/llm_client.py` NEW): LLMClient.submit_and_wait owns caller-side retry budget — fixed per /review-impl HIGH#2 to forward budget=1 to SDK so LLMTransientRetryNeededError actually fires + asyncio.sleep on retry_after_s + bumps outcome=transient_retry AND outcome=failed on exhaustion per LOW#7
- **Step 4 — orchestrator** threads llm_client to entity step ONLY; other 3 extractors stay on legacy provider_client until 4a-β
- **Step 5 — cancel-race regression test**: covered at SDK level (test_cancel_race_polling_observes_external_cancel) + extractor level (test_extract_entities_via_llm_client_cancelled_raises_with_stage)

### `/review-impl` round 2 — caught 9 issues, all fixed inline

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| 1 | 🔴 HIGH | Chunking shreds entity prompt (single user message contains instructions+rules+examples+text inline; gateway splits on `\n\n` → chunks 2..N have NO instructions → quality collapse on 13K-token chapters). My live smoke didn't trigger because input was 1 paragraph. | `chunking=None` + deferred 4a-α-followup that restructures prompt as system+user before re-enabling |
| 2 | 🔴 HIGH | Wrapper transient retry was DEAD CODE — passed budget=0 to SDK so LLMTransientRetryNeededError never fired; K17.3 quality contract (the entire reason ADR §3.3 D3c exists) NOT preserved | Forward budget=1 to SDK + new `test_llm_client_wrapper.py` (6 tests pin REAL retry-loop semantics; previous tests bypassed wrapper by mocking LLMClient directly) |
| 3 | 🟡 MED | Cancelled job conflated with "0 entities found" — orchestrator wrote empty Pass 2 + flipped extraction_jobs to completed, lying to user about cancel | Raise ExtractionError(stage='cancelled') instead of returning [] |
| 4 | 🟡 MED | Client.stream() didn't accept per-call user_id (multi-tenant pattern incomplete) | Mirror jobs methods; +2 SDK tests |
| 5 | 🟡 MED | Worker per-chunk retry budget (9 chunks × 2 attempts = 18 upstream calls under sustained transient errors) | Refactor to streamWithBudget shared-pointer; +2 budget regression tests |
| 6 | 🟢 LOW | openCompletionStream → typed error mapping not unit-tested directly (a regression to fmt.Errorf would silently disable streamWithRetry) | NEW open_completion_stream_test.go — 7 httptest tests pin status→type mapping |
| 7 | 🟢 LOW | knowledge_llm_job_total{outcome="failed"} didn't include exhausted-transient | Bump `outcome="failed"` ALSO on exhaustion |
| 8 | 🟢 LOW | openapi entity_extraction.input description claimed `{text, known_entities, language}` but real wire shape is chat-message | Updated description to clarify all extraction ops use chat-message wire; operation enum picks aggregator only |
| 9 | 🔵 COSMETIC | Unreachable `assert last_job is not None` | Auto-fixed by HIGH#2 refactor |

### Test deltas
- **Gateway:** +15 (8 worker_test.go: 3 whitelist + 5 retry + 2 shared-budget; 7 open_completion_stream_test.go httptest typed-error mapping)
- **SDK:** +21 (19 test_client_jobs.py: submit/get/wait/cancel/budget/cancel-race/multi-tenant; 2 test_client_stream.py: stream user_id)
- **knowledge-service:** +12 (6 test_llm_entity_extractor.py SDK-path; 6 test_llm_client_wrapper.py wrapper REAL retry semantics)

### Verify evidence
```
gateway:  go test ./internal/... → ALL GREEN
sdk:      pytest tests/ → 37 passed in 0.34s
ks-svc:   pytest tests/unit/ → 1606 passed in 10.53s
                              (19 pre-existing host-env failures unrelated; confirmed via git stash on b2f577e)
live smoke (post-fixes): qwen3.6-35b-a3b entity_extraction → 1 entity, status=completed
```

### What's NEXT for the next agent

**Two equally-valid next cycles** — pick based on quality-eval priority vs migration-velocity:

**Option A — 4a-α-followup (S/M)**: re-enable chunking by restructuring entity prompt as system+user. Touches `app/extraction/llm_prompts/entity_extraction.md` (split into a system block and a `{text}`-only user block) + `app/extraction/llm_entity_extractor.py` (build messages as `[{role:system, content:instructions}, {role:user, content:text}]` + set chunking=ChunkingConfig(strategy='paragraphs', size=15)). Re-run quality eval on Speckled Band (13K tokens) to validate chunked extraction matches single-call quality. **This is the cycle that finally fixes the original 13K-chapter complaint at production quality.**

**Option B — 4a-β (L)**: migrate relation/event/fact extractors to SDK pattern. Same surface as 4a-α (extractor signature + tolerant parser + orchestrator threading) × 3 extractors. Adds `fact_extraction` to openapi `JobOperation` enum + `factKey(subject+predicate+claim)` to gateway's jsonListAggregator + +5 aggregator tests. Includes the `_build_extraction_messages` consolidation decision (per ADR §5.1 LOW#10) when 3 extractors all need the same helper.

**Recommend Option A first** — closes the original-complaint loop end-to-end before scaling to 3 more extractors. 4a-β can ship after.

**5 ADR §6 deferred questions still open for 4a-β/γ/δ:**
- Q3 cross-chunk known_entities priming (still relevant once chunking re-enabled)
- Q4 polling DB load profile (knowledge_llm_poll_total metric exists; needs measurement)
- Q5 gateway concurrency limit (knowledge_llm_inflight_jobs gauge exists; cap deferred to Phase 6a)
- Q6 fact_extraction prompt template (own vs share with event)
- Q7 on-demand summarize: P1 stream vs P2 jobs (4a-γ)

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle metadata at top
2. `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md` — 8 sections + 25 subsections + 9-item closing checklist
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a sub-cycle rows
4. This handoff file (you're reading)
5. **For 4a-α-followup**: `services/knowledge-service/app/extraction/llm_prompts/entity_extraction.md` (~135 lines; needs system+user split)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` to confirm prior cycle closed
2. For 4a-α-followup: size S/M (`size S 3 2 0` then `phase clarify`); for 4a-β: size L (`size L 8 5 1`)
3. Infra: `docker ps --filter name=infra-` — provider-registry + knowledge-service + LM Studio reachable
4. Live smoke target: `019dc738-a6b7-7bff-b953-b47868ae7db0` (qwen3.6-35b-a3b user_model registered for `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

---

## Session 53 cycle 1 — Phase 4a ADR DESIGN-first · /review-impl validated 3 HIGH gaps before commit

**Story:** Session opened on the natural Phase-4a-next path identified at session 52 close. Per CLAUDE.md "DESIGN-first cycle (like C16/C17/C18)", shipped a 394-LOC ADR pinning Path C (job-pattern + chunking) over Path A (surface-preserving) and Path B (SDK-direct). 4-cycle slicing 4a-α XL / 4a-β L / 4a-γ L / 4a-δ M bounds the ~407 mock-site test churn at <30% per PR. D1-D7 all resolved with rationale + 8 deferred Qs to BUILD-cycle CLARIFY.

**`/review-impl` paid for itself this cycle.** Initial ADR draft passed self-review and POST-REVIEW summary. User invoked `/review-impl` which re-read actual gateway code (`worker.go:140`, `repo.go Finalize`, `aggregator.go:72`) and caught **3 HIGH** that would have blocked 4a-α BUILD live smoke OR caused silent quality regression on local LLM:
- **HIGH#1**: `worker.go:140` hard-rejects non-chat operations TODAY — ADR §5.1 sketch was unrunnable; aggregator factory wires entity_extraction at line 72 but worker fails the job before reaching `NewAggregator(operation)`. Fix: §2.4 Gateway Gaps section + §5.1 Step 0 ships op-whitelist as 4a-α prereq.
- **HIGH#2**: D3 silently dropped HTTP-retry on transient upstream errors — gateway has zero retries, K17.3 absorbs 1 retry today. Without replacement, every transient LM Studio 502 = chapter-level failure. Fix: D3 split into D3a/b/c — preserve transient-retry via gateway-side single-retry on typed errors + SDK caller-side retry budget=1 bridge until Phase 6b ships proper retry.
- **HIGH#3**: D6 single `llm_job_id UUID NULL` column doesn't fit reality — each chapter extraction submits 4 LLM jobs (entity/relation/event/fact). Fix: revised to reverse-lookup via `llm_jobs.job_meta = {extraction_job_id, role}`; NO new column added.

Plus 6 MED + 3 LOW + 2 COSMETIC. All 12 actionable findings amended in ADR with explicit `/review-impl` cross-references (17 callouts total). 4a-α BUILD reclassified L→XL after gateway prereqs Step 0 added.

### Cycle 1 — C-LLM-PHASE-4A-ADR Phase 4a knowledge-service migration ADR [DOC XL DESIGN-first]

NEW `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md` (394 LOC, 8 numbered sections + 25 subsections, 9-item closing checklist, 8 deferred Qs). MOD `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 (Phase 4a single XL row replaced with 4 sub-cycle rows + ADR cross-link). Decisions baked in: Path C, 4-cycle slice, polling via SDK wait_terminal exp backoff 250ms→5s, sync-saga preserved B1, D3 split with caller-side single-retry bridge, fact_extraction added in 4a-β with factKey=subject+predicate+claim, prompts stay in knowledge-service, reverse-lookup via job_meta, worker-ai untouched. 4a-α Step 0 closes 2 gateway gaps before any consumer code touches new path.

### What's NEXT for the next agent

**4a-α BUILD cycle (XL)** is the immediate next BUILD. Per ADR §5.1 + closing-checklist:

1. **Step 0 gateway prereqs** (ship FIRST):
   - `services/provider-registry-service/internal/jobs/worker.go:140` — replace hard-reject with per-op switch allowing chat / completion / entity_extraction / relation_extraction / event_extraction
   - Adapter typed transient errors (`provider.ErrUpstreamRateLimited`, `ErrUpstreamTransient`, `ErrUpstreamTimeout`) for gateway-side single-retry honoring `Retry-After`
   - +5 worker_test.go tests (per-op routing + transient retry)

2. **Step 1 SDK changes** (`sdks/python/loreweave_llm/`):
   - `submit_job(operation, model_source, model_ref: str, input, chunking, callback, trace_id, job_meta)` — model_ref STAYS str, SDK validates UUID-shape
   - `get_job(job_id) → Job` with `httpx.Timeout(connect=5, read=10, write=5, pool=5)` per-poll
   - `wait_terminal(job_id, *, transient_retry_budget=1)` — exp backoff + raises `LLMTransientRetryNeededError` on `error.code IN {LLM_RATE_LIMITED, LLM_UPSTREAM_ERROR}` for caller-side retry
   - `cancel_job(job_id)`
   - ≥15 unit tests including transient-retry budget logic

3. **Step 2 Entity extractor migration** (`services/knowledge-service/app/extraction/llm_entity_extractor.py`):
   - New `llm_client: LLMClient | None = None` param — legacy `client: ProviderClient | None = None` retained for fallback
   - `for attempt in range(2):` retry loop catching `LLMTransientRetryNeededError`
   - `job_meta={"extraction_job_id": ..., "chapter_id": ..., "role": "entity"}` for D6 reverse-lookup
   - Tolerant parser fields per ADR §5.1 Step 3: required {name, kind, evidence_passage_id} optional {aliases→[], confidence→0.5}

4. **Step 3 pass2_orchestrator** threads `llm_client` to entity step ONLY in 4a-α; other 3 extractors stay on legacy.

5. **Step 4 deps.py** registers new SDK client lifespan singleton.

6. **Cancel-race regression test** mandatory (per ADR §5.5 + /review-impl MED#4): submit job + DELETE mid-flight + assert `extraction_jobs.status="cancelled"` + no Neo4j write.

7. **Live smoke**: Speckled Band 13K-token chapter through `extract_entities` returns N entities via gateway job. Verify against qwen3.6-35b-a3b (the original-complaint model).

**8 deferred Qs from ADR §6 — 4a-α CLARIFY MUST resolve Q1-Q5:**
1. Per-chunk paragraph size for entity_extraction (size=8 vs ~15)
2. wait_terminal per-poll httpx.Timeout shape under live load
3. Cross-chunk known_entities priming (recommend size=15 + measure)
4. Polling DB load profile (add metric `knowledge_llm_poll_total`)
5. Gateway concurrency limit (add metric `knowledge_llm_inflight_jobs{user_id}`)

**4a-β / 4a-γ / 4a-δ** scoped in ADR §5.2-5.4. Each independently green.

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle metadata at top
2. **`docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`** — 8 sections + 25 subsections + 9-item closing checklist + 8 deferred Qs
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a sub-cycle rows
4. This handoff file (you're reading)
5. `contracts/api/llm-gateway/v1/openapi.yaml` — JobOperation enum, SubmitJobRequest schema (gateway gap §2.4 noted: enum lists ops the worker doesn't dispatch yet)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` to confirm prior cycle closed
2. Start 4a-α with `python scripts/workflow-gate.py size XL N M K` then `phase clarify` (XL — gateway prereq + SDK + 1 extractor + tests + migration helpers ≥10 files; logic ≥6; 1 side-effect = new SDK API surface)
3. Infra check: `docker ps --filter name=infra-` — provider-registry + postgres + LM Studio reachable
4. For live smoke: `LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1` + qwen3.6-35b-a3b registered as user_model

---

## Session 52 — closed at HEAD `c0420d2` (20 cycles shipped · Phase 1+2+3 TIERS COMPLETE + Phase 1c-anthropic ✅ + Phase 3b-followup ✅)

> **Date:** 2026-04-26 (session 52, closed at 20th cycle / Phase 3b-followup per-op JSON aggregators)
> **HEAD:** `c0420d2` (Phase 3b-followup per-op aggregators; 1c-anthropic @ `2c7c9a2`; max_tokens-policy @ `1ae3158`; 3c worker chunked @ `842e1bf`; 3b multi-chunk agg @ `388d2ac`; 3a chunker @ `5c72133`; 2f FE EventSource @ `141fb01`; 2e SSE bridge @ `2b411a2`; 2d notif consumer @ `83a255a`; 2c RabbitMQ pub @ `9afb5bf`; 2b job lifecycle @ `64ff7d6`; 2a llm_jobs DDL @ `f28f4a3`; 1e lint rule @ `936724b`; 1c-ii chat-svc drops litellm @ `200a794`; 1c-i ReasoningEvent @ `d43d508`; 1b Python SDK @ `58b2024`; 1a Gateway streaming @ `aaff5e1`; 0a OpenAPI spec @ `4d1a1e0`; refactor plan @ `870b683`; pre-plan proxy fix @ `e63f90f`; session 52 prior demo-track HEAD `568cbfd`)

## Session 52 — 20 cycles shipped · **Pivot from extraction quality polish to LLM pipeline architecture refactor** · **Phase 1+2+3 TIERS COMPLETE**

**Pivot story:** session opened intending to "continue C19/C20 extraction quality cycles" against gemma-4-26b-a4b baseline. User asked to register + use `qwen/qwen3.6-35b-a3b` (their strongest local model). Eval timed out at 1500s × 2 retries — I incorrectly concluded "model not viable on this hardware". User pushed back firmly: timeouts on LLM pipelines are the wrong abstraction, system needs unified async + chunking + notification contract. Audit revealed 3 distinct LLM contracts in production (chat-service direct litellm bypass, knowledge-service transparent-proxy, translation-service typed invoke) plus 60s default timeout in knowledge-service mathematically incompatible with thinking-model workloads. Spent the rest of the session shipping the unified-contract refactor end-to-end.

**Highlights:**
- **🎯 Phase 1 tier COMPLETE** (1a Gateway streaming + 1b Python SDK + 1c-i ReasoningEvent + 1c-ii chat-service drops litellm + 1e lint rule). chat-service no longer imports `litellm` or `openai` — gateway invariant from CLAUDE.md restored for streaming code path.
- **🎯 Phase 2 tier COMPLETE** (2a llm_jobs DDL + 2b lifecycle handlers/worker + 2c RabbitMQ publisher + 2d notification-service consumer + 2e SSE bridge + 2f FE EventSource). Full async-job pipeline live end-to-end: provider-registry submit → goroutine streams → DB terminal → RabbitMQ user.<id>.llm.<op>.<status> → notification-service persist + api-gateway-bff SSE → FE bell badge bumps real-time.
- **🎯 Phase 3 tier COMPLETE** (3a chunker primitives + 3b multi-chunk aggregator + 3c worker chunked dispatch). Original user complaint (qwen3.6-35b-a3b on 13K-token chapters) technically unblocked — sequential per-chunk dispatch + JSON-merging aggregators ready for Phase 4a knowledge-service migration.
- **🚀 Deferred regression closed: Phase 1c-anthropic** — Anthropic SSE streamer with thinking_delta → ReasoningEvent for Claude 3.7+ extended thinking. Closes D-PHASE-1C-ANTHROPIC.
- **🚀 max_tokens=0 means omit** — caller policy enforcement at SDK + gateway-handler + adapter (3-layer defense-in-depth) so deep-reasoning tasks let the model decide token budget. Anthropic exception preserved (API requires max_tokens).
- **🚀 Phase 3b-followup per-op JSON aggregators** — final unblocker for Phase 4a. jsonListAggregator merges entity/relation/event JSON outputs across chunks with soft-fail on malformed chunks; without this Phase 4a was blocked because chatAggregator concatenates with `\n\n` producing invalid JSON.
- **18 commits new code + 1 commit refactor plan + 1 commit pre-plan proxy fix = 20 commits total**.
- **~6000+ LOC** new code across provider-registry-service (Go), api-gateway-bff (TS/NestJS), notification-service (Go), chat-service (Python), frontend (React/TS), sdks/python (NEW), contracts/api/llm-gateway (NEW).
- **NEW package `sdks/python/loreweave_llm/`** — first shared SDK in monorepo. Other services consume via `pip install -e ../../sdks/python` from their requirements.txt + Dockerfile multi-stage COPY pattern (chat-service Phase 1c-ii is the reference impl).
- **NEW contract `contracts/api/llm-gateway/v1/openapi.yaml`** — 17 schemas, 6 paths covering POST /v1/llm/stream + POST /v1/llm/jobs + GET/DELETE /v1/llm/jobs/{id} × public/internal pair. spectral lint clean.
- **NEW planning doc `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md`** — 8 sections covering principles, audit findings, target architecture, 7-phase migration plan, 8 user-decision questions Q1-Q8 (all approved with recommended defaults).

### Cycle 20 — C-LLM-AGG-PEROP Phase 3b-followup [BE M] — per-operation JSON aggregators

Final unblocker for Phase 4a. NEW `jsonListAggregator` in `internal/jobs/aggregator.go` parses per-chunk `{<list_field>:[...]}` JSON and merges items by caller-supplied keyFn. Three operation routes: `entity_extraction` (key = name+kind, aliases array gets union semantic on tie), `relation_extraction` (key = subject+predicate+object+polarity), `event_extraction` (key = name+time_cue). Higher confidence wins on tie; soft-fail per chunk so 1/N malformed output doesn't fail the whole job (errors captured in `result.chunk_errors[]`). Insertion-order preserved for deterministic results. **2 bugs discovered + fixed mid-cycle**: (a) `mergeKnownKeys` argument-order swap was making low-confidence existing rows win over higher-confidence new rows; (b) `chunkBuffer` not reset in EndChunk caused Finalize defensive-flush to re-parse already-handled chunks producing duplicate `chunk_errors`. **+8 tests**: Entity merge with alias union, Relation tuple-dedup, Polarity-distinct, Event by name+cue, malformed-chunk soft-fail, missing-list-field error, unchunked single-parse backward-compat. **Files: 2** (aggregator.go + test). **Verify**: jobs pkg 31 tests PASS (+8); api/chunker/provider all green.

### Cycle 19 — C-LLM-ANTHROPIC-STREAM Phase 1c-anthropic [BE M] — Anthropic SSE streamer

Closes deferred regression D-PHASE-1C-ANTHROPIC. Anthropic chat models now stream end-to-end through gateway's `/v1/llm/stream` instead of returning LLM_STREAM_NOT_SUPPORTED. NEW `internal/provider/anthropic_streamer.go` — streamAnthropicSSE parser dispatches per Anthropic event type: message_start captures input_tokens, content_block_delta with text_delta → TokenEvent + thinking_delta → ReasoningEvent (Claude 3.7+ extended thinking), message_delta emits UsageEvent + captures stop_reason, message_stop terminates emitting DoneEvent with mapped finish_reason, ping events filtered, error events surface as canonical StreamErrorEvent + stop. mapAnthropicStopReason translates end_turn|stop_sequence→stop, max_tokens→length, tool_use→tool_calls. openAnthropicStream POSTs `/v1/messages` with `x-api-key` + `anthropic-version: 2023-06-01` headers, forces stream:true. anthropicAdapter.Stream replaces the ErrStreamNotSupported stub; max_tokens 8192 default preserved (API requires). **Files: 3** (anthropic_streamer.go + adapters.go + anthropic_streamer_test.go). **Verify**: provider pkg PASS — 7 new Anthropic tests + existing AnthropicInvoke + adapters/streamer tests all green; live smoke deferred (needs Anthropic API key not configured in dev).

### Cycle 18 — C-LLM-MAXTOKEN-POLICY [BE+SDK M] — max_tokens=0 means omit

User-driven policy clarification: caller-omitted OR caller-zero `max_tokens` means "let the model decide" — must NOT appear in upstream payload. Critical for thinking models where reasoning + answer combined exceeds any reasonable arbitrary cap. **3-layer defense-in-depth**: (1) SDK `to_request_body` drops max_tokens when 0; (2) gateway `stream_handler.go` gate `if *MaxTokens > 0`; (3) adapters' Stream + Invoke methods drop unless > 0. Anthropic Invoke documented exception keeps 8192 default (API requires). **Files: 5** (SDK models.py + tests + stream_handler.go + adapters.go + new max_tokens_policy_test.go with 6 httptest-based tests verifying exact wire bytes).

### Cycle 17 — C-LLM-WORKER-CHUNK Phase 3c [BE L] — worker chunked dispatch

Phase 3 tier complete. Worker now reads chunking config from llm_jobs row, splits last user message via Phase 3a chunker, dispatches per-chunk adapter.Stream calls bracketed by aggregator StartChunk/EndChunk (Phase 3b), reports per-chunk progress. **Sequential dispatch** for MVP — chatAggregator state isn't goroutine-safe across chunks; parallel is Phase 3c-followup or Phase 6. **Files: 5** (chunked_input.go + tests + worker.go + jobs_handler.go + repo.go). **Verify**: live smoke 4-paragraph chunked job with size=2 → 2 chunks dispatched sequentially → progress 0/None → 1/2 → 2/2 → completed; content concatenated with `\n\n` separator; reasoning keeps last chunk per Phase 3b design.

### Cycle 16 — C-LLM-AGG-MULTICHUNK Phase 3b [BE M] — multi-chunk aggregator

chatAggregator gains StartChunk/EndChunk hooks. Per-chunk content+reasoning buffers reset on StartChunk, flushed on EndChunk with chunkSeparator='\\n\\n' between non-empty chunks (counter avoids leading sep + skips empty chunks). Reasoning-keep-last-chunk semantic. Usage SUMMED across chunks. Backward-compat: no Start/End calls = single-chunk Phase 2b behavior identical. **Files: 2**. **Verify**: 14 tests (+5 new) PASS.

### Cycle 15 — C-LLM-CHUNKER Phase 3a [BE M] — chunker primitives

Foundation for >8K-token inputs. NEW `internal/chunker/chunker.go` — Strategy enum (tokens/paragraphs/sentences/none), tiktoken-go cl100k_base for token counting, regex `(?:\\r?\\n\\s*\\r?\\n)+` for paragraphs, `[.!?。！？]+\\s*` for ASCII+CJK sentences. **CJK regex bug discovered + fixed mid-cycle** (original `\\s+|$` requirement failed for CJK which has no inter-sentence whitespace). **Files: 2 + tiktoken-go dep**. **Verify**: 15 chunker tests PASS.

### Cycle 14 — C-LLM-FE-STREAM Phase 2f [FE M] — EventSource subscriber

Phase 2 tier complete. `useNotificationStream` self-contained hook with EventSource + exponential-backoff reconnect (1s→30s cap) + ref-stable onEvent + accessToken-null teardown. NotificationBell drops 30s poll for live SSE; initial unread fetch becomes one-shot. **Files: 4**. **Verify**: vitest 8/8 PASS; tsc clean.

### Cycle 13 — C-LLM-SSE-BRIDGE Phase 2e [BE M] — api-gateway-bff SSE bridge

NEW NotificationsController @Sse('stream') at `/v1/notifications/stream` with JWT-via-query auth. Reuses existing AmqpService that consumes loreweave.events; routes by `event.user_id ?? event.owner_user_id` (back-compat with translation-service AND Phase 2c TerminalEvent). gateway-setup.ts excludes /stream path from upstream proxy filter. **Files: 7**. **Verify**: jest 5/5 PASS; live E2E full chain captured `id:1\\ndata:{full TerminalEvent JSON}` on FE-side curl.

### Cycle 12 — C-LLM-NOTIF-CONSUMER Phase 2d [BE L] — notification-service consumer

Closes the half between provider-registry's RabbitMQ publisher (Phase 2c) and FE EventSource subscription (Phase 2f). Notifications row created automatically for every LLM job terminal transition. NEW `internal/consumer/consumer.go` — durable queue `notification-service.llm-jobs` bound `user.*.llm.#`; `transformTerminalEvent` pure helper builds notifications row args; nack-no-requeue on malformed (poison-message guard) + requeue on transient DB error (at-least-once). **Files: 6**. **Verify**: 6 transform tests PASS; live E2E completed + cancelled flows produce notifications rows with category=llm_job.

### Cycle 11 — C-LLM-JOBS-NOTIFY Phase 2c [BE L] — RabbitMQ terminal-event publisher

Terminal-state events publish to `loreweave.events` topic exchange with exactly-once semantic via rowsAffected gate. NEW `internal/jobs/notifier.go` — Notifier interface + rabbitMQNotifier (amqp091-go) + NoopNotifier fallback. TerminalEvent envelope with RoutingKey = `user.<id>.llm.<op>.<status>`. Worker.finalizeAndNotify helper publishes IFF Repo.Finalize rowsAffected > 0 — race protection prevents duplicate event when cancel beats stream completion. **Files: 11**. **Verify**: live cancel-race regression — 25s wait after cancel confirms queue stays empty (no late completed event after cancel won).

### Cycle 10 — C-LLM-JOBS-LIFECYCLE Phase 2b [BE L] — async job handlers + worker

Submit → 202 with job_id → goroutine drives MarkRunning → adapter.Stream → Finalize → caller polls GET. NEW `internal/jobs/{repo,aggregator,worker}.go`; NEW `internal/api/jobs_handler.go` with 6 handlers (POST/GET/DELETE × JWT/internal pair). Phase 2b cuts: only chat/completion ops; non-chat → LLM_OPERATION_NOT_SUPPORTED. **Bug fixed in cycle**: Repo.Finalize originally had no status guard — goroutine could overwrite cancelled→completed when user cancels mid-stream. Fixed: `WHERE status='running'`. **Files: 7**. **Verify**: 13 new tests; live smoke happy path + cancel race regression.

### Cycle 9 — C-LLM-JOBS-DDL Phase 2a [BE M] — llm_jobs table foundation

NEW `llm_jobs` table appended to provider-registry schemaSQL. 23 columns mirroring openapi Job + SubmitJobRequest verbatim. operation enum (10 values), status enum default 'pending', `expires_at default now()+'7 days'` per Q8. **CHECK `llm_jobs_terminal_consistency` locks the invariant** `status terminal ↔ completed_at NOT NULL` at DB layer. 4 indexes including partial on expires_at WHERE terminal for future Phase 6 sweeper. **Files: 1**. **Verify**: live INSERT verifies CHECK rejects status='completed', completed_at=NULL.

### Cycle 8 — C-LLM-LINT-RULE Phase 1e [INFRA XS] — forbid direct provider-SDK imports

Enforcement gate locking in P3+P4. `scripts/lint-no-direct-llm-imports.sh` greps `services/`+`frontend/` for `(import|from) (litellm|openai|anthropic)` outside allowlist (`services/provider-registry-service/`, `sdks/python/`). Phase 1 COMPLETE. **Verify**: regression-tested by injecting `from litellm import acompletion` in chat-service path → exit 1 with offender output; cleanup → exit 0.

### Cycle 7 — C-LLM-CHAT-MIGRATE Phase 1c-ii [BE L] — chat-service drops litellm

Largest architectural deliverable of Phase 1. chat-service no longer bypasses gateway via direct provider SDK. CLAUDE.md gateway invariant restored for streaming chat. NEW `_stream_via_gateway` helper using SDK; title-gen migrates to SDK accumulation. Drop `_stream_openai_compatible`/`_stream_litellm`/`_resolve_model`. Dockerfile build context shifted to repo root for SDK COPY. requirements.txt drops `litellm>=1.40`. **Bug fixed in cycle**: passing `temperature=gen_params.get('temperature')` overrode pydantic StreamRequest default 0.0 with None → validation error. Fix: kwargs sparsity. **Files: 6 + 4 test files migrated**. **Verify**: chat-service pytest 177/177 PASS; live E2E `POST /v1/chat/sessions/{id}/messages` → 194 reasoning-delta + 6 text-delta = `'\\n\\n{"ok":true}'` zero litellm in path.

### Cycle 6 — C-LLM-REASONING-EVENT Phase 1c-i [BE+SDK M] — ReasoningEvent canonical

Closes silent Phase 1a regression. Discovered via direct LM Studio probe: thinking models stream `delta.reasoning_content` per-token but the parser was DROPPING those chunks (only emitting `delta.content`). NEW `StreamChunkReasoning` kind in canonical envelope. SDK adds ReasoningEvent pydantic class to discriminated union. **Files: 5**. **Verify**: live smoke against qwen3.6 — 146 reasoning chunks + 2 token chunks streamed separately end-to-end.

### Cycle 5 — C-LLM-SDK-PY Phase 1b [SDK L] — Python SDK loreweave_llm

First shared SDK in the monorepo. NEW `sdks/python/loreweave_llm/` package. Client.stream(StreamRequest) → AsyncIterator[StreamEvent]. 2 auth modes (jwt → /v1/llm/stream, internal → /internal/llm/stream + user_id query). httpx.Timeout(None, connect=5, read=120) — no wall-clock cap on whole stream. SSE parser handles event/data/comment lines. Error consistency: HTTP-level + SSE-frame `event: error` both surface as same typed exception via from_code factory. submit_job() stub raises NotImplementedError (Phase 2). **Files: 8**. **Verify**: pytest 14/14 PASS in 0.27s; live smoke against gateway+LM Studio qwen3.6 reconstructed `'\\n\\n{"ok":true}'`.

### Cycle 4 — C-LLM-STREAM-IMPL Phase 1a [BE L] — gateway streaming

First runtime piece of unified contract. NEW `POST /v1/llm/stream` (JWT) + `POST /internal/llm/stream` (X-Internal-Token + user_id query). SSE end-to-end with **no wall-clock timeout**. Closes the gap that forced chat-service to bypass via litellm. NEW `streamer.go` with canonical types + `streamOpenAICompat` parser shared by openai/lm_studio/ollama-compat. Anthropic stub returns ErrStreamNotSupported. NEW `stream_handler.go` with emit closure that JSON-marshals chunk + writes `event: <kind>\\ndata: <json>\\n\\n` + flushes. **Files: 5**. **Verify**: 9 streamer unit tests + live smoke through `/internal/llm/stream` against qwen3.6-35b-a3b emitted 6 token events + 1 done event.

### Cycle 3 — C-LLM-CONTRACT-OAS Phase 0a [DOC M] — OpenAPI spec

NEW `contracts/api/llm-gateway/v1/openapi.yaml` (~740 lines). 17 schemas covering streaming + async jobs + canonical SSE event envelope. Plan Q1-Q8 approved decisions baked in. spectral lint clean (initial run caught 4 nullable+$ref siblings + 1 unused ProviderKind, all fixed in-cycle). **Files: 2**.

### Cycle 2 — C-LLM-PIPELINE-PLAN [DOC XL] — refactor plan + audit

User-driven full-system architecture plan. Audit revealed 3 distinct LLM contracts in production, gateway-hardcoded `stream:false` forcing chat bypass, timeout-chain math fail. NEW `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 8 sections covering principles (P1 streaming no-timeout, P2 async-jobs unified, P3 shared SDK, P4 gateway-only invariant), audit findings, target architecture (2 flavors at gateway), 7-phase migration plan, 8 open questions. **Files: 2**. User approved plan + Q1-Q8 defaults via "approve" reply.

### Cycle 1 — LM-STUDIO-PROXY-FIX [BE M] — transparent proxy strips trailing /v1

Pre-plan cycle. Closes the half that earlier LM-STUDIO-URL-FIX (commit 74da52c) missed: doProxy code path in api/server.go was still building `/v1/v1/chat/completions` for users who store endpoint as `http://host:1234/v1`. Discovered when running quality eval against qwen3.6-35b-a3b. Export NormalizeLmStudioBase + extract buildProxyTargetURL helper + 5 unit tests. **Files: 5**. **Verify**: live POST /internal/proxy/v1/chat/completions returns proper {choices, usage, stats} struct after rebuild.

### What's NEXT for the next agent

**Phase 4a is the natural next cycle but it is XL+ regardless of slice.** Knowledge-service has ~600 LOC `provider_client.py` business logic + ~1500 LOC test surface (test_provider_client.py 909 LOC + test_llm_json_parser.py 627 LOC). The migration target options:

1. **Surface-preserving rewrite (XL)**: chat_completion internals swap from JSON→SSE; ~30 test mocks need adjustment.
2. **Abandon provider_client.py (XL)**: 4 extractors use SDK directly; delete wrapper + tests; rewrite extractor mock pattern.
3. **Job-pattern + chunking (XL+)**: extractors become `submit_job + wait`; RabbitMQ subscriber inside knowledge-service or polling. **This is the cycle that actually fixes the original user complaint** (qwen3.6-35b-a3b on 13K-token chapters).

Phase 4a should open with a **DESIGN-first cycle** (like C16/C17/C18 of session 51) to choose the path + ADR before BUILD. Phase 3b-followup per-op aggregators + Phase 3c worker chunked dispatch are ready to consume.

**Other deferred items** (lower priority):
- Phase 3c-followup: parallel chunk dispatch (needs goroutine-safe aggregator) — Phase 6 hardening territory.
- Phase 4b/4c/4d: worker-ai/translation-service migrations + drop legacy invoke endpoints.
- Phase 5: Audio/STT/TTS migration to unified contract.
- Phase 6: rate-limit + retry + tracing + cancel-context propagation + crash-recovery.
- Phase 1c-anthropic-followup: Anthropic tool-use input_json_delta mapping (when tool-calling support lands).

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle-by-cycle metadata in header
2. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 8 sections + 7-phase plan + Q1-Q8 (user-approved)
3. This handoff file (you're reading) — cycle summaries with HEAD refs
4. `contracts/api/llm-gateway/v1/openapi.yaml` — canonical wire contract for the unified pipeline

**Session 52 closed at HEAD `c0420d2`. Session 53 opens fresh on Phase 4a DESIGN-first.**

---

## Session 51 — 14 cycles shipped (all Track 2/3 Gap Closure: C7..C16) · **P2 DONE (7/7)** · **P3 DONE (12/12)** · **P4 C14 DONE** · **P5 🏗 1/3 DESIGN-signed-off** · session closed

**Highlights:**
- **P2 tier closed at C9** (entity optimistic concurrency + unlock). All 7 P2 cycles shipped across sessions 50+51 (C3..C9).
- **🎉 P3 tier DONE 12/12** — opened at C10, fully closed at C12c-b. All Track 2/3 Gap Closure Priority 3 work shipped across 8 cycles (C10 + C11 + C12a + C12b-a + C12b-b + C13 + C12c-a + C12c-b).
- **🚀 P4 C14 fully shipped** in two cycles (C14a schedulers + C14b cursor state). User override of the P4 trigger criterion at C14b CLARIFY — plan-completion mindset. First session 51 cycle where "honest audit caught the plan understating scope" was applied BEFORE committing to size — saved a potential XL overrun.
- **🏗 P5 opened with C16** — first DESIGN-first cycle in plan history shipped clean. ADR for budget-attribution global-scope regen. Decision: Option B (`knowledge_summary_spending` table). Implementation sketch shovel-ready for next BUILD cycle. C15 honestly deferred per "fire when profiling shows pain" P4 trigger — opposite stance from C14b's user-override.
- **C12 split saga** — C12a (paired FS) + C12b-a/b-b (BE/FE split) + C12c-a/c-b (BE/FE split). Plan's single "C12 L" row bloomed into 5 honest-sized cycles. Memory `feedback_scope_audit_before_batching` applied each time.
- **C12c-a size reclassified** from plan-said-"S FE-only blocked" to workflow-gate-required FS L after audit caught: (a) no glossary-service list endpoint, (b) no worker branch handling scope='glossary_sync' (explicit TODO at runner.py:621 silently no-op'd), (c) scope='all' ALSO excluded glossary — user-approved flip makes the name honest.
- Back-end test coverage: **1466/1466 knowledge-service** (+61 over session 50's 1405) + **23/23 worker-ai** (+6 from C13's 17) + **12/12 glossary-service Go** at session 51 end.
- Front-end test coverage: **474/474** at session 51 end (unchanged since C12b-b — C13 stories are tsc-only, C12c-a is pure BE).

### Cycle 46 — Track 2/3 Gap Closure C16 🏗 [XL DESIGN-first] — budget-attribution ADR

**First P5 🏗 DESIGN-first cycle.** Shipped 280-line ADR
([`KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md))
choosing **Option B** (`knowledge_summary_spending` table) over Option A (phantom-project pollution) and Option C (unified ledger XL refactor). Closes D-K20α-01's BUILD-blocker; the deferral itself stays partial until a BUILD cycle ships the implementation per §5/§7 checklist.

**Audit + decision rationale:** global L0 regen (`scope_type='global'`) bypasses the K16.11/K16.12 budget gate today because `record_spending` requires a `project_id`. Plan offered A vs B; audit + greenfield context (no production data) eliminated Option A's migration concerns and established C as overkill for the immediate problem.

**Implementation sketch covers:** DDL with composite PK + CHECK constraint + idx; `SummarySpendingRepo` (record + current_month_total); `check_user_monthly_budget` extension; `regenerate_global_summary` wire-in next to existing Prometheus increment; recording-order semantic (record AFTER provider success BEFORE guardrails); 15 enumerated test cases; DDL regression locks.

**4 open questions** explicitly deferred to BUILD-cycle CLARIFY: (1) project regen audit (does it ALSO bypass the gate?); (2) sanity caps; (3) FE wire shape; (4) auto-pause semantics.

**Closing checklist (§7)** gates D-K20α-01 fully-cleared: BUILD cycle ships migration + repo + budget extension + scheduler wire + DDL regression tests + 8 unit + 3 budget integration + 3 scheduler integration tests + plan row [x] AND `/review-impl` 0 unresolved HIGH/MED.

**Stage 2 self-fix:** added §5.4 recording-order paragraph clarifying record-after-provider-success rationale + recovery path via Prometheus/ledger divergence alert.

**Files: 3** (1 NEW ADR + SESSION_PATCH + plan row update). **Verify:** No code → no tsc/pytest. ADR doc-complete: 7 numbered sections, 5 subsections in §5, 4 explicit open questions, 9-item closing checklist.

---

### Cycle 45 — Track 2/3 Gap Closure C14b [BE L] — resumable scheduler cursor state

Closes **C14 fully** (C14a schedulers + C14b cursor). Second P4 cycle. User override of P4 trigger criterion at CLARIFY — plan-completion mindset.

**Three blocks:**
- **migrate.py** — NEW `sweeper_state` table (sweeper_name PK + last_user_id UUID + last_scope JSONB + updated_at). Per-sweeper resumable cursor, `last_scope` as escape hatch for future per-user-sub-scope sweepers. No FK on last_user_id (cross-DB forbidden).
- **NEW `SweeperStateRepo`** (4 methods: read_cursor / read_cursor_full / upsert_cursor with partial-UPDATE semantic / clear_cursor). Module docstring explains crash semantics.
- **Reconciler integration**: `SWEEPER_NAME` grep anchor; `_LIST_USERS_SQL` seek predicate `$1::uuid IS NULL OR user_id > $1::uuid` with ORDER BY user_id for deterministic resume; sweep_reconcile_once gains optional sweeper_state_repo (back-compat: None = C14a behavior); flow is read_cursor → fetch users with seek → per-user reconcile + upsert_cursor (BEFORE counter increment per /review-impl LOW#2) + counters → natural-completion clear; per-user raise leaves cursor at last successful user. Quarantine scheduler: docstring-only note (self-advancing filter, no natural per-user key).

**/review-impl caught 1 MED + 3 LOW + 1 COSMETIC; fixed MED + 1 LOW in-cycle, 1 LOW retracted (false finding), 2 accepted:**
- **MED#1** DDL regression test (3 new tests: table_present + schema_shape + no-cross-db-FK)
- **LOW#2** swapped upsert+counter order — cleaner semantics, both are safe (reconcile idempotent)
- **LOW#3 RETRACTED** — `idx_knowledge_projects_user_all ON knowledge_projects(user_id)` already exists from K16.12; my audit missed it

**Size reclassified** M→L at CLARIFY (7 files trips 6+ threshold). Honest-sizing memory applied — sixth reclassification this session.

**Closes D-K11.9-01 cursor-state + P-K15.10-01 cursor-state.** **C14 fully shipped.** Only C15 remains in P4 (trigger-gated).

**Files: 10** (6 code/test + 2 NEW — sweeper_state.py + test_sweeper_state_repo.py; 2 docs SESSION_PATCH/plan). **Verify:** pytest **1501/1501** (+17 from C14a baseline 1484: 10 repo + 4 scheduler integration + 3 DDL regression).

---

### Cycle 44 — Track 2/3 Gap Closure C14a [BE L] — reconciler + quarantine scheduler loops

**First P4 cycle.** Audit before CLARIFY caught that the plan's C14 row understated scope: K11.9 `reconcile_evidence_count` and K15.10 `run_quarantine_cleanup` are CALLABLE FUNCTIONS with no cron wiring — operators had to trigger manually. Split at user request into **C14a** (create missing schedulers, this cycle) + **C14b** (cursor hardening, deferred per P4 trigger criterion).

Two new scheduler modules mirroring K20.3 `summary_regen_scheduler` + K19b.8 `job_logs_retention` shape:

- **reconcile_evidence_count_scheduler.py** (NEW 210 LOC) — `sweep_reconcile_once` + `run_reconcile_loop`; advisory lock `20_310_004`; 24h cadence + 25min startup stagger; per-user iteration over DISTINCT user_id (NO is_archived filter post-LOW#4 fix — reconciler is cheap, archived projects still drift-prone). Per-user error isolation; Pydantic direct attribute access so schema drift crashes loudly.

- **quarantine_cleanup_scheduler.py** (NEW 200 LOC) — `sweep_quarantine_once` + `run_quarantine_loop`; advisory lock `20_310_005`; 12h cadence + 30min startup stagger; global sweep with /review-impl MED#1 inner-loop drain (10× throughput: 10k facts/sweep vs 1k original via `max_drain_iterations=10` safety cap + natural `count < limit` terminator).

- **metrics.py** (+2 Counter vecs with 3-outcome pre-seed + clarified Help strings per /review-impl MED#3 — `errored` is sweeps-with-≥1-error, not per-user-error count).

- **main.py** — 2 lifespan tasks + teardown cancellation mirroring K20.3/K19b.8. Advisory lock keys 001-005 now fully reserved.

**/review-impl caught 3 MED + 1 LOW + 2 COSMETIC; fixed 3 MED + 1 LOW in-cycle:**
- **MED#1** quarantine drain 10× (inner loop + safety cap + 3 regression tests)
- **MED#2** pool advisory-lock persistence on hard crash (pre-existing K20.3; documented in module docstring)
- **MED#3** metric `errored` semantics clarified in Help strings + derived-query examples
- **LOW#4** archived-only users now covered + source-scan regression lock

**Closes D-K11.9-01 partial + P-K15.10-01 partial (BE half).**

**Files: 10** (6 code/test + 2 docs SESSION_PATCH + plan + 2 scheduler NEW). **Verify:** pytest 1484/1484 (+18 from C12c-b baseline 1466: 9 reconciler + 9 quarantine).

---

### Cycle 43 — Track 2/3 Gap Closure C12c-b [FE L] — glossary_sync scope radio + retry fallback

Closes **D-K19a.5-06** completely (FE half paired with C12c-a BE). **P3 tier DONE 12/12.**

Pure FE additive on BuildGraphDialog: `ALL_SCOPES += 'glossary_sync'` (between chat and all); `availableScopes` memo extends book_id gate to cover both `chapters` AND `glossary_sync`; `openScope` falls back to `defaultScope` when `initialValues.scope` is a book-required scope but `project.book_id` is null — prevents orphaned state-but-not-rendered after book-unlink between job creation and retry (fixes pre-existing chapters bug for free). 4 locale JSON files + `BUILD_DIALOG_KEYS` drift-lock extended. 5 new tests (2 scope-radio + 3 /review-impl regression).

**/review-impl caught 3 LOW + 2 COSMETIC; all 3 LOWs fixed in-cycle:**
- **LOW#1** retry-fallback for book-unlinked projects (fixes chapters too) + 2 regression tests
- **LOW#2** retry pre-fill test for scope='glossary_sync'
- **LOW#3** Vietnamese `noBookHint` refined to "book-based scopes" grouping with examples

**Size reclassified** S→L at CLARIFY per workflow-gate (7 files trips 6+ threshold). Honest-sizing memory applied again — fifth reclassification in session 51.

**Files: 9** (7 code/test + 2 docs SESSION_PATCH + plan update). **Verify:** tsc clean; vitest 479/479 (+5 from C13 baseline 474). No BE touched — C12c-a's 422 guard is authoritative.

---

### Cycle 42 — Track 2/3 Gap Closure C12c-a [FS L] — glossary_sync BE unblock

3-service FS reclassified from plan-said "S FE-only blocked". Audit caught that **no glossary-service list endpoint existed**, **worker-ai had a TODO at runner.py:621 silently no-op'ing glossary_sync jobs**, and **scope='all' ALSO excluded glossary**. User approved flipping `all` to include glossary (making the name honest).

**Block A — glossary-service Go**: NEW `GET /internal/books/{book_id}/entities?cursor&limit` paginated endpoint with peek-ahead cursor logic, `alive=true AND deleted_at IS NULL` filter, short_description joined via LEFT JOIN on attribute_definitions. 5 tests (4 unit no-DB + 1 DB-gated cursor walk).

**Block B — worker-ai**: NEW `GlossaryClient` + `GlossaryEntity/Page` dataclasses with graceful-degrade → None. NEW `KnowledgeClient.glossary_sync_entity` + `GlossarySyncResult`. NEW `_enumerate_glossary_entities` returning `(list, complete: bool)` tuple + HARD_CAP=5000 + 200-page safety + UUID-ASC resume-skip. NEW `_GLOSSARY_SYNC_COST_PER_ITEM = 0.0` (through `_try_spend` for pause/cancel uniformity). NEW branch in `_process_job` for scope ∈ {glossary_sync, all} + book_id set. Bounded retry via `retry_glossary_<id>` cursor key mirroring chapters. `process_job`/`poll_and_run` sigs gain `glossary_client`.

**Block C — knowledge-service**: NEW `POST /internal/extraction/glossary-sync-entity` thin handler wrapping K15.11 helper (previously dead code). K15.11 helper ON MATCH SET now updates `project_id` (latest-sync wins, fixes first-call-wins drift for users with 2 projects sharing a book). `start_extraction_job` 422 guard for `glossary_sync + null book_id`.

**/review-impl caught 3 MED + 3 LOW + 1 COSMETIC; all 6 actionable findings fixed in-cycle:**
- **MED#1** start endpoint glossary_sync+null-book guard (422 with `error_code: 'glossary_sync_requires_book'`)
- **MED#2** K15.11 ON MATCH project_id drift (pre-existing; C12c-a activates helper)
- **MED#3** glossary branch bounded retry
- **LOW#4** opaque 502 boundary message
- **LOW#5** items_total drift on partial enumeration (enumerator returns `complete: bool`)
- **LOW#6** 5xx mid-enumeration test coverage
- **COSMETIC#7** 200-page ceiling kept as defense-in-depth

**Bonus:** during test Edit caught + restored a stray assertion in `test_start_job_active_job_exists_returns_409` (original test had 2 asserts; my first Edit only matched the first line, orphaning the second into a new test).

**Closes** D-K19a.5-06 BE half. **P3 tier 11/12 done** after C12c-a. Only **C12c-b** (FE scope radio, S) remains in P3.

**Files: 17** (14 code/test + 2 docs SESSION_PATCH/plan + 1 handoff). **Verify:** go test ok; worker-ai 23/23; knowledge-service 1466/1466.

---

### Cycle 41 — Track 2/3 Gap Closure C13 [FE L] — Storybook dialog stories via MSW

Pure FE infra. `msw@^2` + `msw-storybook-addon@^2` devDeps wired into `.storybook/preview.tsx` via `initialize({onUnhandledRequest:'warn'}) + loaders:[mswLoader]`. Service worker committed at `frontend/public/mockServiceWorker.js` (9KB, `msw init` output). 3 new infra modules under `.storybook/`: `fixtures/knowledge.ts` (14 typed factories), `msw-handlers.ts` (7 endpoint factories + `HandlerOptions`), `story-helpers.ts` (`findConfirmButton` / `findRunBenchmarkButton` / `waitForSelects` option-value-aware). 3 new story files × 19 stories (BuildGraph 11 + ChangeModel 5 + ErrorViewer 3). `@sb/*` Vite alias + tsconfig path collapses 4-level relative imports. MockAuthProvider.user reshaped from pre-existing `{id}` to production `{user_id, display_name: string|null, email}`.

**/review-impl caught 0 HIGH + 1 MED + 4 LOW + 2 COSMETIC; all 7 fixed in-cycle:**
- **MED#1** VERIFY was static-bundle-only — live-smoked via Chrome DevTools MCP (`npm run storybook`), confirmed MSW intercepts fire for all POSTed endpoints (estimate, start, benchmark-run, update-model) + play() interactions drive React state through the DOM. **DISCOVERED DURING SMOKE**: Radix Dialog portals to `document.body` so `canvasElement.querySelector*` misses dialog subtree entirely → extracted `story-helpers.ts` that queries `document`. Second-order: native `<select>` renders with placeholder-only while models useQuery pends → `waitForSelects` must gate on target-option-value or `selectOptions` throws "value not found in options".
- **LOW#2** `userModelsHandler` blind to `?capability=` query → split fixtures + query-param branch.
- **LOW#3** MockAuthProvider user shape mismatch (pre-existing K19a.8 latent) → renamed to match production `UserProfile`.
- **LOW#4** `benchmarkRunHandler` dead-on-arrival → NEW 11th BuildGraph story `BenchmarkRunFromCTA` consumes it via `findRunBenchmarkButton`.
- **LOW#5** `ambientHandlers` estimate-opt structural discriminator → explicit `{mode:'happy'|'loading'|'error'}` tagged union.
- **COSMETIC#6** `'../../../../.storybook/...'` imports → `@sb/*` Vite alias + tsconfig paths.
- **COSMETIC#7** `errorOr` blind cast to `JsonBodyType` → `isJsonSafe` recursive runtime narrow with fallback envelope.

**Closes** D-K19a.8-01. **P3 tier 9/9 DONE** after C13. **Files: 13** (6 MOD + 7 NEW). **Verify:** tsc clean + vitest 474/474 + `storybook build --test` success + live smoke Chrome DevTools MCP 4 story variants end-to-end.

### Cycle 40 — Track 2/3 Gap Closure C12b-b [FE L] — Run-benchmark CTA + error-code toast map

Pure FE. NEW `useRunBenchmark` mutation hook + inline `RunBenchmarkButton` rendered inside `EmbeddingModelPicker` — blast-radius = BuildGraphDialog + ChangeModelDialog + ProjectFormModal all inherit the CTA automatically. `runs=3` hardcoded (matches CLI + L-CH-09 methodology; BE validates 1..5). Gated on `projectId && value && !data.passed` so button shows for no-run AND failed, hides once passed. `runBenchmarkErrorMessage(t, code, detailMessage)` helper maps 6 codes (5 BE error codes + `'unknown'`) to localised toast copy. Success toast interpolates `{{model}}` from `resp.embedding_model` so model-swap mid-mutation can't render stale scope. 9-key i18n × 4 locales + placeholder drift lock.

**/review-impl** caught 0 HIGH + 1 MED + 3 LOW + 1 COSMETIC; fixed MED + 3 LOWs in-cycle, 2 accepted-with-doc:
- **MED#1**: toast didn't disclose which model the result belongs to — fixed by interpolating `{{model}}` from the response body (not the dropdown value, which may have changed).
- **LOW#2**: no placeholder-presence drift lock on new keys → 2 `it.each(LOCALES)` assertions mirroring C7's `jobs.detail.eta` pattern.
- **LOW#3**: `runs=null` explicit path untested → hook test pinning null pass-through so a future null→undefined coerce can't mask a BE 422 regression.
- **LOW#4 accept**: unmount-during-mutation drops toast (BE still completes + invalidates queryClient cache) — documented in hook docblock, matches `useRegenerateBio`.
- **LOW#5 accept**: button inside outer `<label>` is a structural smell (label-click forwarding no-ops on direct `<button>` target) — documented, matches BenchmarkBadge placement.
- **COSMETIC#6 accept**: rapid double-click race — `disabled={isPending}` updates synchronously within React's event tick; BE sentinel catches the edge.

**Closes** D-K19a.5-07 (FE half). **Files: 9**. **Verify:** FE knowledge+lib **474/474** GREEN (+9 from C12b-a baseline 465). `tsc --noEmit` clean.

### Cycle 39 — Track 2/3 Gap Closure C12b-a [BE L] — on-demand POST benchmark endpoint

NEW `app/benchmark/` module (230 LOC runner) + `POST /v1/knowledge/projects/{id}/benchmark-run`. Reuses K17.9 harness (AsyncBenchmarkRunner + fixture_loader + persist) so request-path is a thin sibling of the CLI's `_run_cli`. Typed exception hierarchy → 6 distinct error codes mapped to {404, 4×409, 1×502, 422}. Validation ladder: 404 cross-user/missing → 409 `no_embedding_model` → 409 `unknown_embedding_model` (dim-mismatched like `nomic-embed-text`) → 409 `not_benchmark_project` (empty-project guard via `KNOWN_SOURCE_TYPES` filter) → 409 `benchmark_already_running` (sentinel check-and-add) → 502 `embedding_provider_flake` (partial fixture load refuses to persist false-negative). Sync 120s default — background-task pattern rejected at CLARIFY (orphaned-failure UX worse than long request).

**/review-impl** caught 0 HIGH + 2 MED + 3 LOW + 1 COSMETIC; fixed all 5 non-cosmetic:
- **MED#1 source-scan drift lock**: `KNOWN_SOURCE_TYPES` correct today but silent risk if future PR adds a new producer. Fixed: regression test greps `passage_ingester.py` at test time for `source_type="..."` literals, asserts each is in the set.
- **MED#2**: initial `asyncio.Lock` + pre-check was atomic-only-in-single-threaded-asyncio + fragile to refactor (any future await-insert between check and acquire silently breaks serialization). Swapped to pure-sync `set[tuple[str,str]]` sentinel — check-and-add atomic-by-construction.
- **LOW#3**: no test pinned "benchmark_entity NOT in KNOWN_SOURCE_TYPES" invariant → added.
- **LOW#4**: partial fixture load silently persisted false-negative `passed=False` row (indistinguishable from real regression in FE badge) → NEW `FixtureLoadIncompleteError` → 502, refuses to persist. 2 tests: critical-contract + router.
- **LOW#5**: `_has_real_passages` Cypher literal had no direct assertion (all unit tests mocked it) → string-literal check for 3 safety clauses (`user_id`, `project_id`, `IN $real_types`).

**Closes** C12b (BE half). **Defers** C12b-b (FE) + C12c (glossary_sync, blocked). **Files: 5**. **Verify:** 28/28 new tests (15 runner + 13 router); 1405/1405 BE adjacent.

### Cycle 38 — Track 2/3 Gap Closure C12a [FS XL] — chapter-range picker + runner-side scope_range gate

Cross-service FS: NEW book-service `POST /internal/chapters/sort-orders` (mirrors `postInternalChapterTitles` shape verbatim — 200-cap, scan_error_count best-effort, rows.Err() fatal) + knowledge-service `BookClient.get_chapter_sort_orders` + NEW `ExtractionJobsRepo.list_active_for_project(user_id, project_id)` + event-handler runner gate in `handle_chapter_saved` + FE chapter-range inputs (From/To) in BuildGraphDialog gated on `scope='chapters'`.

**Disjoint union semantic** on the runner gate: ≥1 unbounded chapter-scope job → full ingest wins; otherwise `[10,20] ∪ [40,50]` excludes 30, includes 45. Graceful degrade on sort_order fetch failure → over-ingest (safer than silent skip). FE `chapterRange` useMemo declared BEFORE `estimateQuery` (TDZ fix during BUILD).

**/review-impl** caught 0 HIGH + 1 MED + 4 LOW + 0 COSMETIC; fixed MED + 1 LOW:
- **MED#1**: BE `_extract_chapter_range` accepted reversed `[50, 10]` — validator rejected wrong-length/non-int/negative but not `from > to`. Persisted, then runner gate `lo ≤ sort_order ≤ hi` vacuously false → silent skip with no error signal. Fixed: 3-line check raising 422; existing `test_estimate_scope_range_malformed_rejected` gains reversed-range case.
- **LOW#2**: `list_active_for_project` had no unit/integration test → 2 new integration tests (status filter + cross-user isolation) gated on `TEST_DATABASE_URL`.

**Closes** D-K19a.5-04 + D-K16.2-02b. **Defers** D-K19a.5-07 → C12b + D-K19a.5-06 → C12c (blocked). **Files: 16** (Go 2 + Python 5 + FE 4 + i18n 4 + docs 2). **Verify:** Go `TestPostInternalChapterSortOrders_*` 3/3; Python `test_event_handlers.py` 16/16 (+6 C12a); 247/247 BE adjacent. FE 444/444.

### Cycle 37 — Track 2/3 Gap Closure C11 [FS XL] — cursor pagination for extraction jobs history

Cross-service FS: NEW cursor codec + SQL row-value/NULLS-LAST predicate + response envelope + FE infinite query + Load more button. `_encode_cursor(c, r, j)` / `_decode_cursor(raw)` base64-urlsafe JSON, defensive against binascii/Unicode/JSON/field-shape errors. `list_all_for_user` signature returns `(list[ExtractionJob], str | None)` tuple + `cursor: str | None = None` kwarg. History path: 4-branch NULLS-LAST OR covering (cursor non-null + row non-null lower completed_at), (equal completed_at + lower tiebreak), (cursor non-null + row null — null always after), (both null + lower tiebreak). NEW `ExtractionJobsPage { items, next_cursor }` envelope; 422 on malformed cursor.

FE: `useInfiniteQuery` with `initialPageParam: ''` + `getNextPageParam: (last) => last.next_cursor ?? undefined`. `refetchInterval` conditional (function-form) gated on `pages.length ≤ 1` — single-page users keep 10s freshness, power users who Load more get a frozen view (explicit opt-in → explicit refresh). `ExtractionJobsTab` drops obsolete `COMPLETE_VISIBLE_LIMIT=10` slice.

**/review-impl** caught 0 HIGH (blocked early) + 1 HIGH + 1 MED + 3 LOW + 1 COSMETIC; fixed HIGH + MED + 1 LOW:
- **HIGH#1**: 9 integration-test call sites in `test_extraction_jobs_repo.py` treated return as list but the new tuple return `(rows, next_cursor)` silently broke them — would fail the moment the suite ran against live Postgres. Fixed: unpacked all 9 sites.
- **MED#2**: history polling was initially removed to avoid N-page refetch storm but created a UX regression → restored as function-form conditional gated on page count.
- **LOW#3**: no integration test exercised the novel 4-branch NULLS-LAST OR predicate → 2 new tests (walk-7-through-pages-of-3 + tied-completed_at-tiebreak).

**Closes** D-K19b.1-01 + D-K19b.2-01. **Files: 17**. **Verify:** BE unit 19/19 + cursor codec 7/7 = 26/26; FE 440/440.

### Cycle 36 — Track 2/3 Gap Closure C10 [FS XL] — timeline entity_id + chronological range filters

**First P3 cycle.** Cross-service FS: 3 new Cypher WHERE predicates (`participant_candidates`, `after_chronological`, `before_chronological`) + router entity_id resolution + FE TimelineFilters component (entity search dropdown + chronological range inputs).

Router resolution: `get_entity(user_id=str(jwt_user_id), canonical_id=entity_id)` with JWT-threaded user_id for cross-user safety. Missing entity → `participant_candidates=[]` (NOT `None`) so Cypher's `ANY(c IN [] WHERE ...)` = false → zero rows; collapses 404 path to empty timeline per KSA §6.4 anti-existence-leak. Reversed chronological range → 422.

FE TimelineFilters reuses `useEntities` (min-2-char + 250ms debounce matching EntityMergeDialog). **/review-impl MED#1**: chronological inputs fired BE call per keystroke → fixed by internal `afterInput`/`beforeInput` state + 400ms debounced commit effect + parent-reset sync effects. 2 regression tests (4-keystroke-coalesce + parent-reset-no-re-fire).

**Closes** D-K19e-α-01 + D-K19e-α-03. **Files: 16**. **Verify:** BE `test_timeline_api.py` 18/18 (+6 C10); 213/213 BE adjacent. FE 432/432.

### Cycle 35 — Track 2/3 Gap Closure C9 [FS XL] — entity optimistic concurrency + unlock endpoint — **P2 DONE 7/7**

Cross-service FS: `Entity.version: int = 1` field + coalesce backfill + atomic FOREACH Cypher + `POST /entities/{id}/unlock` + FE ifMatch threading + `useUnlockEntity` hook + Unlock CTA in detail panel. Atomic single-round-trip: `WITH e, coalesce(e.version, 1) AS current_version` + `FOREACH (_ IN CASE WHEN current_version = $expected_version THEN [1] ELSE [] END | SET ...)` + `RETURN e, current_version = $expected_version AS applied`. Version bumps at 4 user-facing sites (update / unlock / merge ON CREATE + ON MATCH / merge-update-target). System-internal writes (anchor recompute / archive / promote / unlink_glossary) deliberately NOT bumped to avoid spurious 412s.

**/review-impl** caught 1 HIGH + 0 MED + 4 LOW + 1 COSMETIC:
- **HIGH**: pre-C9 entities PERMANENTLY UNEDITABLE — `_node_to_entity` coalesced missing version to 1 but all 4 Cypher `coalesce(e.version, 0)` defaulted to 0, so FE's `If-Match: W/"1"` always 412'd against `current_version=0`. Unit tests mocked `run_write` and never hit this path. **Fixed** by aligning all 4 Cypher coalesce defaults to 1. **LOW#2**: added source-scan regression lock `test_cypher_version_coalesce_default_matches_read_path` that reads the 4 Cypher string literals at import time and asserts absence of `coalesce(.version, 0)`.

PATCH contract: 428 Precondition Required on missing If-Match, 412 Precondition Failed with `current.model_dump(mode="json")` body + fresh ETag header on mismatch. Unlock is idempotent (no If-Match) — `user_edited=true` entities become permanently alias-append-gated until user explicitly unlocks.

**Closes** D-K19d-γa-01 + D-K19d-γa-02. **P2 tier 7/7 — DONE.** **Files: 16**. **Verify:** BE entity 34/34 (+14 C9 + 2 regression locks); 163/163 BE adjacent. FE 422/422.

### Cycle 34 — Track 2/3 Gap Closure C8 [FS XL] — drawer-search source_type filter + in-card highlight + BE facet counts

Cross-service FS: NEW `count_passages_by_source_type` + Literal enum router param + response facet counts (user addendum) + NEW FE `highlightTokens` util + NEW `DrawerSearchFilters` component. Native `<input type="radio">` inside `<fieldset role="radiogroup">` for free WAI-ARIA keyboard semantics.

**/review-impl** caught 0 HIGH + 3 MED + 4 LOW + 2 COSMETIC; fixed 7 in-cycle:
- **MED#1**: cross-locale `sourceType.*` key presence test added.
- **MED#2**: `DRAWER_SOURCE_TYPES` tuple in api.ts as single source of truth — `EMPTY_COUNTS` + `OPTIONS` derive from it via `Object.fromEntries` / `.map`. BE adding a 4th type = ONE edit in api.ts, not 3.
- **MED#3**: filter reset on project change in `RawDrawersTab` — holding "Chapter" across projects hid hits in chat-only projects.

**Closes** D-K19e-γa-01 + D-K19e-γb-01. **Files: 16**. **Verify:** BE `test_drawers_api.py` 20/20 + new `test_passages_count.py` 4/4 = 24/24. FE 414/414.

### Cycle 33 — Track 2/3 Gap Closure C7 [FE XL] — humanised ETA formatter + stale-offset self-heal

**Reclassified from S to XL at CLARIFY** due to honest file count (10 files including locales). Pure FE: NEW `formatMinutes(minutes) → "<1min" | "{n}min" | "{h}h" | "{h}h {mm}min"` util + `useTimeline` optional `onStaleOffset` callback + consumer wiring.

Util pre-rounds to integer before branching so `59.6 → "1h"` (not naive `"0h 60min"`). Defensive NaN/Infinity/≤0 → `"<1min"` (dead code today, cheap future-safety). Hook fires callback when `total>0 && offset>0 && events.length===0 && !isLoading && !isFetching && !error` — all 6 guards. `events.length` dep (not identity) avoids re-fire on fresh-array fallback. After fire, parent sets offset=0 → guard `offset>0` fails → no loop.

**/review-impl** MED: collision with 5 existing local `formatDuration` helpers (ms/seconds semantics) → renamed `formatMinutes` for unambiguous unit. L4: inline `onStaleOffset` arrow churns effect deps → wrapped in `useCallback([])` in TimelineTab.

**Closes** D-K19b.3-02 + D-K19e-β-02. **Files: 12**. **Verify:** FE knowledge+lib 390/390 (+27 from 363 C6 baseline).

---

**What's next — Session 52 default path:**

🎉 **P1+P2+P3 all DONE + P4 C14 fully shipped + P5 C16 ADR signed off**. Remaining actionable: **C16-BUILD** (the implementation cycle for the ADR just shipped) OR **C17 + C18 DESIGN-first** ADRs. Next actionable default is **C16-BUILD** while ADR context is fresh.

Next cycle — **C16-BUILD (L)**: implement Option B per [the ADR](../03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md). Files: migrate.py DDL append + NEW `SummarySpendingRepo` + budget.py extension + regenerate_summaries.py wire-in + 8 repo unit + 3 budget integration + 3 scheduler integration tests + DDL regression tests. CLARIFY MUST resolve §6's 4 open questions (especially #1: re-audit project regen budget path). Expect L-size; closing checklist in ADR §7 gates D-K20α-01 fully-cleared.

**Alternative next-cycle candidates:**
- **C17 🏗 (P5, XL DESIGN-first)** — Entity-merge canonical-alias mapping. KSA §3.4.E amendment + backfill story.
- **C18 🏗 (P5, XL DESIGN-first)** — Event wall-clock date. KSA §3.4 amendment + LLM prompt change + migration.
- **C15 (P4, S TRIGGER-GATED)** — Neo4j fulltext index. Fire ONLY when any user crosses ~10k entities.
- **User-gated ⏸** — C19 multilingual fixtures + C20 Gate-13 walkthrough.

**Session-51 stats**: 14 cycles shipped (C7→C16). Plan progress: 35 items / 23 cycles total; 33 items / 19 cycles done + 1 DESIGN-signed-off (C16 🏗). **P1+P2+P3 tiers fully closed; P4 C14 DONE; P5 opened with C16 ADR.** First session in LoreWeave history to close three plan tiers + fully ship a fourth's primary cycle + open the fifth via DESIGN-first in one continuous session.

**Session 51 aftermath — things to keep in mind:**

- **C9 HIGH (pre-C9 entities uneditable)** is a class lesson: when adding optimistic-concurrency to an existing model, audit EVERY coalesce/default-value site in read + write paths together. A read that defaults to 1 paired with a write that defaults to 0 creates a silent "permanently-stale" bug invisible to unit tests that mock `run_write`. Consider saving a feedback memory for coalesce-default symmetry if another cycle trips over this.
- **C11 HIGH (9 test sites tuple-breaks)** is a class lesson: when changing a repo method's return signature from `list[X]` to `(list[X], cursor)`, grep EVERY caller AND every test call site before VERIFY. The integration tests didn't run in CI (live-Postgres-gated) so the breakage would have surfaced only after the next stash baseline.
- **Source-scan regression locks** (C12b-a + C9 + C8) are now an established pattern for invariants that cross module boundaries and have no natural unit-test anchor: grep the source at test time + assert a predicate over the literal string. Cheap, zero Neo4j needed. Reuse whenever a new invariant spans 2+ files.
- **Pure-sync set-sentinel > asyncio.Lock** for check-and-add atomicity (C12b-a MED#2). Lock's pre-check-then-acquire is atomic only because no await sits between the two lines today — fragile to refactor. `set.add` returning True-if-new is atomic-by-construction and immune to future await-insertion.
- **Etag must fold every field in the response body** (C6 lesson reinforced via C9 ETag-in-412-mismatch behaviour). Adding a new field to a Pydantic response model without folding it into `_etag` lets stale data serve via 304. `hashlib.md5(..., usedforsecurity=False)` for the stable hash (NOT Python `hash()` which is PYTHONHASHSEED-randomized).
- **CLARIFY honesty > plan commitment**. C7 plan-said-S shipped as XL; C12 plan-bundled-L shipped as 3 cycles (C12a + C12b-a + C12b-b + C12c-blocked). Honest sizing at CLARIFY is worth more than hitting an initial classification — the workflow-gate tolerates reclassification.

**Starting-session boilerplate:**
1. Read [SESSION_PATCH.md](SESSION_PATCH.md) session-51 entries (cycles 33–46) + the plan file's §3 cycle table + the [C16 ADR](../03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md) §5–§7
2. `./scripts/workflow-gate.sh status` to confirm previous cycle closed
3. Start C16-BUILD with `./scripts/workflow-gate.sh size L 8 4 1` then `phase clarify` (L — DDL append + NEW repo + budget extension + scheduler wire + ~3 NEW + 2 MOD test files; 1 side-effect = new DB table). CLARIFY MUST resolve ADR §6's 4 open questions, especially #1 (re-audit project regen budget path).
4. Infra: `docker ps --filter name=infra-` — C16-BUILD wants live Postgres for integration tests; bring up infra-postgres at minimum
5. For future BE integration tests: `TEST_KNOWLEDGE_DB_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge` (port 5555 on host; DB name `loreweave_knowledge` NOT `knowledge`)
6. For Neo4j integration tests: `TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_PASSWORD=loreweave_dev_neo4j`
7. Test account: `claude-test@loreweave.dev / Claude@Test2026` (Playwright smoke tests)

---

## Session 50 — 32 cycles shipped (24 Track 3 + 2 Track 2 close-out + 6 Gap Closure) · P1 done · P2 4/7 done · **session closed**

### Cycle 32 — Track 2/3 Gap Closure C6 [FS XL] — chapter-title resolution for Job + Timeline rows

Sixth Gap Closure cycle. Cross-service BE+FE via denormalization: book-service batched chapter-title endpoint + knowledge-service shared enricher + 4 enrichment sites + 2 FE consumer surfaces.

**Three blocks.**

1. **book-service** — new `POST /internal/chapters/titles` handler (inline in server.go per convention). SQL: `SELECT id, sort_order, title FROM chapters WHERE id = ANY($1::uuid[]) AND lifecycle_state='active'`. Format: `"Chapter N — Title"` (fallback `"Chapter N"` for whitespace-only titles). 200-id cap; missing/inactive chapters silently dropped. Path refined from plan's `/internal/books/chapters/titles` → `/internal/chapters/titles` since chapter_ids are cross-book.

2. **knowledge-service** — `BookClient.get_chapter_titles` + NEW `app/clients/chapter_title_enricher.py` with 2 in-place mutation helpers (events + jobs-cursor). `Event.chapter_title` + `ExtractionJob.current_chapter_title` additive optional fields. 4 enrichment sites: `/v1/knowledge/timeline`, `/jobs` list, `/jobs/{id}` single, `/{project_id}/extraction/jobs` per-project list. All 4 share the module-level BookClient singleton via `Depends(get_book_client)`.

3. **FE** — TimelineEventRow prefers `event.chapter_title ?? chapterShort(event.chapter_id)`; JobDetailPanel new "Current chapter" section gated on title presence. 2 new i18n keys × 4 locales.

**`/review-impl` caught 2 MED + 4 LOW; all 6 addressed in-cycle:**

- **M1** (critical): `_etag(job)` was `updated_at`-only → chapter title rename on book-side wouldn't bump etag, FE served 304 with stale title for up to staleTime. Fix folds `current_chapter_title` into etag via stable md5 (NOT Python's `hash()` which is PYTHONHASHSEED-randomized per-process). Regression test locks "same updated_at + different title → different etag".
- **M2**: happy-path SQL untested at Go level (s := &Server{}, pool=nil tests). Docstring documents the gap + recommends manual-curl smoke for future cycles. L5 partial-mitigation: `rows.Err()` turns silent empty-map SQL failures into 500s.
- **L3**: router tests silently skipped the enricher network path (cursor=None / invalid-UUID fixtures). Added 3 router-level enricher tests + `_setup_overrides` / `_make_client` now auto-override `get_book_client` so unit tests never touch real network.
- **L4**: UUID fallback wrapped in `<code>` → SRs announce character-by-character. Fix: `aria-label={t('timeline.row.chapterUnresolved', {id})}` + new i18n key × 4 locales.
- **L5**: handler silently skipped scan errors → schema drift would return empty map with no signal. Fix: `rows.Err()` check + scan_error_count in partial responses.
- **L6**: FE required type `chapter_title: string | null` doesn't match runtime `undefined` during rollout window. Kept required (matches codebase pattern) + added JSDoc noting the nuance + recommending `??` consumption pattern.

**Closes**: D-K19b.3-01 (JobDetailPanel current chapter) + D-K19e-β-01 (TimelineEventRow chapter title).

**Verify**:
- book-service Go tests 3/3 (non-DB only — M2 gap documented)
- knowledge-service BE unit **1379/1379** (+27 from 1352 C5 baseline: 6 book_client + 17 enricher + 3 router + 1 etag-bump)
- FE knowledge vitest **363/363** (+4 tests from C6 initial; L4/L6 additions didn't add new tests)
- `tsc --noEmit` clean
- No BE integration tests run; respx-mocked unit + the explicit Go-gap note are the safety nets

**Plan progress**: 11 items / 6 cycles · **P1 done · P2 4/7 done** (C3 ✅ + C4 ✅ + C5 ✅ + C6 ✅). Remaining P2: C7 (ETA formatter) · C8 (drawer-search UX) · C9 (entity concurrency+unlock).

---

### Cycle 31 — Track 2/3 Gap Closure C5 [FE M] — mobile polish: EntitiesTable + EntityDetailPanel + PrivacyTab

Fifth Gap Closure cycle. Pure FE responsive + a11y polish across 3 desktop-shared components.

**Three substantive deltas.**

1. **EntitiesTable dual render-tree**. Desktop 6-col grid table (~620px summed fixed cols) was overflowing 375px phones horizontally. Split into `hidden md:block` desktop tree (existing grid, preserved) + `md:hidden` mobile tree (card-per-row: Name + Kind primary line, flex-wrap secondary line with mentions/confidence/date/project). Shared `rowKeyHandler` helper dedup'd from the inline `onKeyDown`. Selected-state visual (`bg-primary/5 ring-1 ring-primary/30`) applied to BOTH trees via `cn()`. New testids `entities-table-desktop` / `entities-table-mobile` / `entities-row-mobile`; existing `entities-row` preserved on desktop (backward-compat with `EntitiesTab.test.tsx`'s 3 usages).

2. **EntityDetailPanel full-width on mobile**. One-word change `max-w-md` → `md:max-w-md`. Mobile: fills viewport. Desktop: 448px capped.

3. **PrivacyTab 4 buttons get `TOUCH_TARGET_MOBILE_ONLY_CLASS`**. Export / Delete / Dialog Cancel / Dialog Confirm wrapped in `cn(base, TOUCH_TARGET_MOBILE_ONLY_CLASS)`.

**`/review-impl` caught 1 HIGH + 3 LOW + 1 COSMETIC; all 5 addressed in-cycle:**

- **HIGH**: EntityDetailPanel's full-width mobile panel BLOCKS the overlay-dismiss path (overlay is covered by the panel), making the X close button the SOLE dismiss on touch. But X was `p-1 + h-4 w-4` ≈ 24×24px — well under the 44×44 iOS/Material minimum → fat-finger UX failure directly introduced by C5's width change. **Fix**: new `TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS = 'min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0'` export in `lib/touchTarget.ts` for icon-only buttons (needs BOTH axes because content doesn't fill width via padding); X button wrapped with `inline-flex items-center justify-center` to re-center the icon inside the expanded 44px box. Regression test locks all 4 class tokens + the flex-centering triple.
- **LOW2**: Mobile cards dropped `role="row"` — no columnheader context on mobile made SR announcement confused. Native `<button>` + `aria-label={e.name}` conveys the "activatable item" semantics cleanly. Desktop keeps `role="row"` for consistency with its columnheader row.
- **LOW3**: Added disabled-state PrivacyTab test — mocks `useAuth` with `accessToken: null`, asserts Export + Delete are `.toBeDisabled()` AND still carry `min-h-[44px]` + `md:min-h-0`. Guards against a regression like `className={cn(base, !disabled && TOUCH_TARGET_...)}` which default-enabled tests wouldn't catch.
- **LOW4**: Added inline comment on `entities-row` testid pointing at the `entities-row-mobile` sibling for future tests wanting cross-tree row counts via `findAllByTestId(/^entities-row/)`.
- **COSMETIC5**: Dialog cancel+confirm test rewrote `getAllByRole(...)[last]` DOM-order heuristic to `within(screen.getByRole('dialog'))` scoped query — no reliance on portal ordering.

**Closes**: D-K19d-β-01 (EntitiesTable mobile responsive + EntityDetailPanel full-width) + D-K19f-ε-01 (PrivacyTab sub-44px buttons).

**Verify**:
- 9/9 `mobilePolish.test.tsx` (7 initial + 2 post-/review-impl)
- 359/359 full FE knowledge vitest (+9 from 350 C4 baseline, zero regressions)
- `tsc --noEmit` clean
- No BE changes

**Plan progress**: 9 items / 5 cycles · **P1 done · P2 3/7 done** (C3 ✅ + C4 ✅ + C5 ✅). Remaining P2: C6 (chapter-title resolution) · C7 (ETA formatter) · C8 (drawer-search UX) · C9 (entity concurrency+unlock).

---

### Cycle 30 — Track 2/3 Gap Closure C4 [FE M] — useProjectState action-callback hook tests

Fourth Gap Closure cycle. Pure FE coverage debt closure: 1 new test file locks the runtime action-callback contract that K19a.7's compile-time `ACTION_KEYS` map couldn't reach.

**What the tests lock.** The hook exposes 14 callbacks: 8 BE-firing (`onPause` / `onResume` / `onCancel` / `onDeleteGraph` / `onRetry` / `onExtractNew` / `onRebuild` / `onConfirmModelChange`) + 6 no-op placeholders (K19a.5/K19a.6 dialog-owned). Before C4, a regression swapping `pauseExtraction` for `cancelExtraction` in `onPause` would have shipped undetected. After C4:

- Every BE-firing action asserts the correct `knowledgeApi` method + `(project_id, token)` arg shape
- `runAction` error path is locked: `toast.error` is called with `{label, error}` opts AND `invalidateQueries` does NOT fire (critical — else FE re-polls on bad state)
- `replayPayload`'s 4-branch `||` guard is fully covered: jobId / llm_model / embedding_model / scope null each trigger `noPriorJob` toast + no API call
- `onRebuild`/`onConfirmModelChange` guard's 2×2 matrix (action × missing-field) is fully covered
- `onExtractNew` forces `scope='chapters'` even when prior job was `chat`
- `accessToken=null` short-circuits all 8 actions
- 6 no-op placeholders are callable without throwing + leak to no API

**Plan divergence at CLARIFY.** Plan listed "11 actions" including `archive` / `restore` / `disable`. Audit showed archive/restore live at ProjectsTab/ProjectRow level (not the hook) and `disable` is one of the 6 no-op placeholders. Actual surface: 8 real + 6 placeholders = 14 callbacks.

**`/review-impl` caught 4 LOW + 2 COSMETIC; all 6 addressed in-cycle:**
- **L1** `beforeEach` per-mock reset → `Object.values(apiMocks)` loop (future API additions auto-reset)
- **L2** rebuild-guard 2×2 matrix was 2 of 4 cells → 4 tests fill the matrix
- **L3** `replayPayload`'s 4-branch null guard was 1 of 4 → 3 new tests for llm_model / embedding_model / scope null
- **L4** toast-opt-drop uncatchable with global raw-key i18n mock → **local** `react-i18next` mock encodes opts as `"<key>|<json>"`; error-path now asserts both outer template key AND `{label, error}` opts passed through
- **C5** batch no-token test doesn't isolate which action leaks → docstring explains density/isolation tradeoff
- **C6** error-path length-equality delta → explicit `calls.slice(before)` negative-slice

5 existing toast assertions tightened from `expect.stringContaining('<key>')` to `toHaveBeenCalledWith('<exact-key>')` since non-opt'd calls return bare key strings.

**Build-time fix:** unused `GraphStatsResponse` type import caught by tsc during VERIFY.

**Closes:** D-K19a.5-05 (action-callback runtime contract) + D-K19a.7-01 (partial super of D-K19a.5-05).

**Verify:**
- 20/20 `useProjectState.actions.test.tsx` (15 initial + 5 post-/review-impl)
- 350/350 full FE knowledge vitest (+20 from 330 C3 baseline, zero regressions)
- `tsc --noEmit` clean
- No BE changes

**Plan progress:** 9/33 item-closures · 4/20 cycles · **P1 done · P2 2/7 done** (C3 ✅ + C4 ✅). Remaining P2 cycles: C5 (mobile EntitiesTable + PrivacyTab tap audit) · C6 (chapter-title resolution) · C7 (ETA formatter) · C8 (drawer-search UX) · C9 (entity concurrency+unlock).

---

### Cycle 29 — Track 2/3 Gap Closure C3 [FS XL] — job_logs retention + pass2 stage producer + FE tail-follow

Third Gap Closure cycle, opens P2 tier. Three distinct deltas kept in one cycle at user request (explicit XL over C3a/C3b split).

**Block A — BE retention (D-K19b.8-01)**. NEW `app/jobs/job_logs_retention.py` close-mirror of K20.3 scheduler shape. Key differences: lock key `20_310_003` (unique across K13.1 + K20.3 keys), daily 24h cadence with 20-min startup delay (offsets K20.3's 10/15-min), `make_interval(days => $1)` parameterized DELETE, asyncpg `"DELETE N"` command-tag parse via defensive `_parse_delete_count`, release in try/finally. `main.py` wires create_task + cancel+await+suppress teardown. `migrate.py` adds `idx_job_logs_created_at` BTREE for the DELETE range predicate.

**Block B — Pass 2 stage producer (D-K19b.8-02)**. `pass2_orchestrator._run_pipeline` + 2 entry points accept optional `job_logs_repo: JobLogsRepo | None = None` kwarg (default None preserves ~20 existing test callers). 4 `info`-level events via `_emit_log` best-effort helper: `pass2_entities` (count + duration_ms), `pass2_entities_gate` (zero-entity early-exit marker), `pass2_gather` (R/E/F counts + gather-duration_ms), `pass2_write` (5 counters + write duration_ms added post /review-impl L2). Repo failures swallowed with WARNING log — extraction never dies for audit-write hiccups. `internal_extraction.py` constructs `JobLogsRepo(get_knowledge_pool())` inline, try/except for unit-test back-compat where pool isn't initialised.

**Block C — FE tail-follow (D-K19b.8-03)**. `useJobLogs.ts` swapped `useQuery` → `useInfiniteQuery` with cursor pagination + optional `jobStatus` opt gating 5s `refetchInterval` on `running/paused/pending`. `JobLogsPanel.tsx` gains `jobStatus` prop + listRef/nearBottomRef auto-scroll (100px threshold) + `max-h-80 overflow-y-auto` scroll container + Load-newer button disabled-during-fetching. `JobDetailPanel` passes `jobStatus={job.status}`.

**`/review-impl` caught 1 MED + 7 LOW + 1 COSMETIC; 6/7 fixed in-cycle + 2 accepted as Track 3 concerns**:
- **MED M1** `<details>` re-open left user at scrollTop=0 even when they'd been at bottom before collapse → `onToggle` handler with rAF-wrapped `scrollTo({top: scrollHeight})` + 2 regression tests (toggle-open fires / toggle-closed doesn't)
- **LOW L2** `pass2_write` event missing `duration_ms` (gather + entities had it) → wrapped `write_pass2_extraction` call in `time.perf_counter()` + context updated
- **LOW L3** `test_sweep_zero_row_delete_is_not_error` didn't assert unlock fires on zero-row path → assertion added
- **LOW L4** gather + write payload shapes untested at field-name level → 2 new parallel tests lock all counter/duration field names
- **LOW L6** browser resize left `nearBottomRef` stale → `ResizeObserver` on listRef (SSR-guarded) recomputes on container resize
- **COSMETIC C9** "Load more" ambiguous (cursor is ASC = newer) → i18n rename `loadMore`/`loadingMore` → `loadNewer`/`loadingNewer` across 4 locales
- **LOW L7** (accepted) cross-tenant retention not per-tenant configurable → module docstring documents Track 3 uplift
- **LOW L8** (accepted) log list not virtualized → component docstring documents `react-window` as Track 3 polish

**Build-time fixes**:
- `sinceLogId` camelCase vs `since_log_id` snake_case — tsc caught during build; hook + test assertions updated
- `internal_extraction.py` unit tests don't init the pool — wrapped `JobLogsRepo(get_knowledge_pool())` in try/except matching `_emit_log` repo=None contract
- `fireEvent.toggle` doesn't exist in react-testing-library — used `fireEvent(el, new Event('toggle', {bubbles: false}))`

**Closes**: D-K19b.8-01 + D-K19b.8-02 + D-K19b.8-03.

**Verify**:
- BE unit **1354/1354** (+24 from 1330 C2 end: 16 retention + 8 pass2 producer)
- BE integration retention 3/3 live + job_logs-adjacent 5/5 (8/8 against infra-postgres-1)
- FE knowledge vitest **330/330** (+10 from 320: 5 useJobLogs infinite-query + 5 JobLogsPanel toggle+Load-newer+auto-scroll)
- Worker-ai 17/17 (no regressions)
- `tsc --noEmit` clean

**Plan progress**: 7/33 item-closures · 3/20 cycles · **P1 done · P2 opened with C3** (14 items / 7 cycles remain in P2).

---

### Cycle 28 — Track 2/3 Gap Closure C2 [BE L] — scheduler trigger label + regen cooldown

Second cycle of the [Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md). Closes both remaining P1-tier observability items — **D-K20.3-α-02** (scheduler metrics) + **D-K20α-02** (regen cooldown). Reclassified S → L early in CLARIFY after audit (plan's "2 files" was optimistic; actual touch is 7 files + 3 test-file extensions).

**Two substantive code changes:**

1. **`summary_regen_total` gains `trigger` label** (`manual` | `scheduled`). Cardinality 12 → 24 pre-seeded series. `RegenTrigger = Literal["manual","scheduled"]` added to `regenerate_summaries.py`; threaded as `trigger` kwarg through `_regenerate_core`, `regenerate_global_summary`, `regenerate_project_summary` (default `"manual"` — back-compat). Scheduler passes `trigger="scheduled"`; public endpoints pass `trigger="manual"`. `/internal/summarize`'s `SummarizeRequest` gains a `trigger: RegenTrigger = "manual"` field (post /review-impl LOW#5). Duration/cost/tokens counters stay 2-label (MVP scope, documented).

2. **Redis SETNX cooldown** on both public regen endpoints. Key `knowledge:regen:cooldown:{user}:{scope_type}:{scope_id or '-'}`, 60s TTL. Per-target (scope_id in key), not per-user. Module-level lazy `aioredis` singleton with `asyncio.Lock` double-checked init + `close_cooldown_client` wired into lifespan teardown (both failure-cleanup tuple AND normal post-yield block). On 429: `Retry-After` header from `client.ttl(key)` with TTL-exception fallback to full budget + defensive floor-to-1 for the `-2`-race (key expires between SETNX=False and TTL read). Graceful degrade when `settings.redis_url` empty OR Redis raises.

**`/review-impl` caught 1 MED + 5 LOW + 1 COSMETIC; all 7 fixed in the same commit:**
- **MED#1** cooldown armed on 500-class server-side failures — live-verified via docker curl (Neo4j-not-configured 500 still armed key for 60s, punishing users for our own bugs). Fixed with `_release_regen_cooldown` helper called from `except ProviderError` AND `except Exception` in both endpoints. Business outcomes (user_edit_lock / concurrent_edit / no_op_* / regenerated) KEEP the cooldown armed — `test_regenerate_cooldown_stays_armed_on_business_outcomes` locks that primary anti-spam contract.
- **LOW#2** FakeRedis.ttl always returned the stored EX value so the defensive floor-to-1 branch never fired in tests → FakeRedis gains `expired_keys` mode returning `-2`; `test_regenerate_cooldown_retry_after_floor_when_ttl_expired_mid_race` asserts `Retry-After == 1`.
- **LOW#3** `client.ttl()` exception path had no test coverage (BoomRedis short-circuits at SET) → `_HalfBoomRedis` (SET/DELETE succeed, TTL raises) + `test_regenerate_cooldown_ttl_exception_falls_back_to_full_budget`.
- **LOW#4** `test_regenerate_project_cooldown_per_project_scope` missing `mock_regen.await_count == 2` → assertion added.
- **LOW#5** `/internal/summarize` didn't accept `trigger` → added as `SummarizeRequest.trigger` + 3 tests (default-to-manual, explicit-scheduled-forwards, Literal-validator-rejects-typo).
- **COSMETIC#7** `_check_regen_cooldown` + `_cooldown_key` used `scope_type: str` → tightened to `Literal["global", "project"]`.
- Accepted **LOW#6**: duration/cost/tokens still 2-label — documented in `_regenerate_core` docstring.

**Live manual-curl verify** (docker rebuild `infra-knowledge-service:latest` + hot-swap; Postgres/Redis/glossary healthy; Neo4j intentionally down = Track 1 mode):
- Call 1 to `/me/summary/regenerate` → 500 (Neo4j not configured); Redis key ABSENT (MED#1 release path fired)
- Call 2 → 500 not 429 (no stuck cooldown)
- Manually `redis-cli SET project:11111… EX 60` → endpoint → **429** with `Retry-After: 60` (cooldown still works for armed state)
- Endpoint to `project:22222…` → **422** guardrail (cross-user) NOT 429 (per-scope isolation holds)
- Post-422: both project keys armed independently (TTL 45s + 46s)
- `/metrics` scrape shows 24 pre-seeded series + `{scope_type="project",status="no_op_guardrail",trigger="manual"} 1.0` incremented by the 422 call

**Closes**: D-K20.3-α-02 (scheduler metrics) + D-K20α-02 (regen cooldown).

**Verify**: knowledge-service unit 1330/1330 (was 1322 at C1 end; **+8** = 5 cooldown regressions + 3 trigger-forwarding; existing-test updates: 3 metric assertions + 2 scheduler `await_args.kwargs["trigger"]` asserts + 1 `await_count == 2` assertion).

**Plan progress**: 4/33 item-closures · 2/20 cycles · **P1 tier 2/2 done** (C1 ✅ + C2 ✅); P2 tier opens with C3 next.

---

### Cycle 27 — Track 2/3 Gap Closure C1 [FS M] — merge_entities atomicity + ON MATCH union

**First cycle of the new [Track 2/3 Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md)** — a 20-cycle debt-drain (~32 open deferrals from Track 2 + K19/K20) the user asked for before opening further Track 3 feature work. C1 is P1 tier — the only backlog item with actual data-loss risk.

**Two changes to [`app/db/neo4j_repos/entities.py`](../../services/knowledge-service/app/db/neo4j_repos/entities.py):**

1. **Atomicity.** `merge_entities` steps 4–7 (rewire RELATES_TO / rewire EVIDENCED_BY / update target w/ glossary pre-clear / DETACH DELETE source) wrapped in `async with await session.begin_transaction() as tx:`. A Neo4j crash between glossary pre-clear and DETACH DELETE can no longer leave source orphaned with `glossary_entity_id=NULL`. Docstring added the contract: "session must be a fresh AsyncSession with no open transaction" — Neo4j async sessions don't nest tx.

2. **ON MATCH union.** `_MERGE_REWIRE_RELATES_TO_CYPHER` gained 4 CASE branches beyond the pre-existing `confidence`-MAX + `source_event_ids`-UNION: `pending_validation` via `coalesce(..., false) AND ...` (matches `relations.py`'s 8-site NULL=validated convention), `valid_from` earliest-non-null, `valid_until` NULL-wins (NULL = still-active sentinel per relations.py:13), `source_chapter` concat-when-distinct. Pass-2-validated source edge merging into quarantined target duplicate now correctly promotes to validated.

**+3 integration tests (live Neo4j):**
- `test_merge_entities_promotes_validated_edge_over_quarantined` — all 4 union branches incl. `valid_until` NULL-wins via raw-Cypher seed (`create_relation` doesn't accept the kwarg)
- `test_merge_entities_on_match_preserves_quarantine_and_validated` — both mirror AND cases a hardcoded `= false` regression would pass without
- `test_merge_entities_is_atomic_on_mid_flight_failure` — `monkeypatch`es `_MERGE_DELETE_SOURCE_CYPHER` → bad Cypher and asserts **3 rollback axes** (glossary + no rewired RELATES_TO + target aliases unchanged). Multi-axis defense against a regression moving ANY single step out of tx, not just the step the failure-injection point targets.

`/review-impl` caught **2 MED + 3 LOW + 1 COSMETIC; all 6 folded into same commit**:
- **M1** coalesce-to-true diverged from codebase NULL=false convention → switched both sides to `coalesce(..., false)`
- **M2** atomicity test proved only glossary-axis rollback → extended to 3 axes
- **L3** `valid_until` CASE never exercised → raw-Cypher seed on target
- **L4** AND-combine only tested promotion direction → new mirror test
- **L5** Python `bool(x or False)` NULL coercion — subsumed by M1 aligned defaults
- **L6** nested-tx contract undocumented → docstring updated
- Accepted #7: `source_chapter` concat bloat on repeated merges — hobby scale, in-code comment

**Closes**: D-K19d-γb-01 (ON MATCH union) + D-K19d-γb-02 (merge atomicity).

**Verify**: 26/26 `test_entities_browse_repo.py` (+3 new) + 105/105 adjacent integration + 86/86 entity unit.

**Plan progress**: 2/33 item-closures · 1/20 cycles · P1 tier: 1/2 done (C1 ✅, C2 next).

---

### Cycle 26 — K20.3 Cycle β [BE L] — Scheduled global L0 regen loop

Closes K20.3 by shipping the global-scope sweep that Cycle α deferred. Close-mirror of α with 3 substantive differences:

1. **UNION eligibility**: users with either an existing global summary OR any non-archived project — catches "keep my bio fresh" AND "will create on first successful regen once I have enough content". Locked by integration test against live Postgres.
2. **User-wide model resolution**: `SELECT llm_model FROM extraction_jobs WHERE user_id=$1 AND status='complete' ORDER BY completed_at DESC LIMIT 1` — picks the most-recent model used anywhere. Users who've never extracted get `no_model` skip.
3. **Distinct advisory lock** `_GLOBAL_REGEN_LOCK_KEY = 20_310_002` so project + global loops can run concurrently on different scopes.

Cadence: **weekly** (7d = 604800s) with 15-min startup delay (offset from project loop's 10-min).

`/review-impl` caught **2 LOW + 1 COSMETIC; all 3 addressed in-cycle**:
- **L1** UNION eligibility SQL untested at integration layer → NEW `test_summary_regen_scheduler_sql.py` with 2 tests hitting live Postgres: 5-user scenario matrix (summary-only / project-only / summary+archived / archived-only / dual-source) locks UNION dedup AND `is_archived=false` filter. Separate ordering test locks crash-resume determinism.
- **L2** no audit log showing which model was resolved per sweep → INFO log `K20.3: regen project|global user=... model=...` on both sweeps. Operators can now grep logs to trace "why did this user's regen fail?" back to the BYOK model choice (especially useful after provider model deprecations).
- **C3** FakeConn arg-count routing was fragile → SQL-text matching (`"project_id = $2" in sql`) ties the fake to the exact production code paths.

**Build-time catch**: initial integration test skipped with Postgres auth failure — container uses `loreweave:loreweave_dev@loreweave_knowledge` not `postgres:*@knowledge`. Corrected `TEST_KNOWLEDGE_DB_URL`.

**Cleared**: D-K20.3-α-01 (scheduled global L0 regen loop).

**Still deferred**: D-K20.3-α-02 (Prometheus metrics beyond logged outcome counters).

**Test deltas at K20.3 β end:**
- BE unit: **32/32 scheduler tests pass** (was 18; +14 global-sweep coverage)
- BE integration: **2/2 new SQL tests** against live `infra-postgres-1`
- BE regen-adjacent: **76/76** (no regressions)

---

### Cycle 25 — K20.3 Cycle α [BE L] — Scheduled project summary regen

Ships the scheduled auto-regen that K20α/β/γ intentionally deferred. Mirrors the K13.1 `anchor_refresh_loop` template: `sweep_projects_once` is the pure sweep function (pg_try_advisory_lock + iterate non-archived extraction-enabled projects + per-project call to `regenerate_project_summary`), `run_project_regen_loop` wraps it in an asyncio loop with 10-min startup delay + 24h interval.

**Model resolution**: scheduled regen has no caller to supply `model_ref`, so it subqueries `extraction_jobs` for the most-recent completed job per project and reuses its `llm_model`. Projects that never ran extraction are counted as `no_model` and skipped.

**Status mapping**: 6 `RegenerationStatus` Literal values collapse into 4 counter buckets on `SweepResult`:
- `regenerated` → `regenerated`
- `no_op_similarity`, `no_op_empty_source`, `no_op_guardrail` → `no_op`
- `user_edit_lock`, `regen_concurrent_edit` → `skipped`
- Unknown future status → `errored` + WARNING log (defensive branch)

**Advisory lock** via `try/finally: pg_advisory_unlock` guarantees release even on mid-sweep exception. Lock released before connection returns to pool — no orphaned state on recycled connections.

**Lifespan wire** in `main.py` matches K13.1: conditional on `settings.neo4j_uri` (Track 1 mode skips), teardown via `cancel+await+suppress CancelledError`.

`/review-impl` caught **1 LOW + 2 COSMETIC; all 3 addressed in-cycle**:
- **L1** inline `SummariesRepo(get_knowledge_pool())` vs async `get_summaries_repo()` factory → documented decision (matches K13.1 precedent; factory would make scheduler the odd one out in lifespan wire)
- **C2** `model_construct` test fixture bypass → 11-line docstring explaining forward-compat tradeoff
- **C3** sweep-complete INFO log untested → new test asserts exactly-one completion log + all 6 counter names present in message

**Build-time catches:**
- Pydantic Literal rejection on unknown status → `model_construct` bypass for the defensive-branch test
- Mock signature `**_kwargs` couldn't absorb positional args from real `sweep_projects_once(pool, session_factory, provider_client, summaries_repo)` → `*_args, **_kwargs`
- `startup_delay_s=0` guard skipped the first `asyncio.sleep` call, throwing off count expectations → tests use `startup_delay_s=1`

**Deferred to Cycle β**:
- D-K20.3-α-01 global L0 regen loop (needs cross-project model resolution)
- D-K20.3-α-02 scheduler run metrics (Prometheus counters beyond logged outcome)

**Test deltas at K20.3 α end:**
- BE unit: **18/18 scheduler tests pass** (new file)
- BE regen-adjacent: **62/62** (61 previous + 1 completion-log test)
- No regressions across all regen paths

---

### Cycle 24 — K19f Cycle ε [FE S] — Tap-target audit (K19f.5)

Closes the K19f cluster. Applied `TOUCH_TARGET_CLASS = 'min-h-[44px]'` to the 2 remaining mobile-shell links (MobileKnowledgePage privacy footer link + MobilePrivacyShell back link). Test assertions strengthened to import the constant and assert `className.toContain(TOUCH_TARGET_CLASS)` so a future refactor of the constant value (e.g. to Tailwind's `min-h-11` shorthand) stays lockable.

**Full tap-target inventory at K19f end**: GlobalMobile save (β) · ProjectsMobile toggle + Build (γ) · JobsMobile toggle + Pause/Resume/Cancel (δ) · MobileKnowledgePage privacy link (ε) · MobilePrivacyShell back link (ε). All interactive elements in mobile-rendered mobile-variant code ≥44px. Card spacing via `space-y-2` (8px), section spacing via `mb-8` (32px).

`/review-impl` caught **1 LOW + 2 COSMETIC; 1 COSMETIC fixed + 1 LOW deferred + 1 COSMETIC accepted**:
- **L1 → D-K19f-ε-01** PrivacyTab mobile audit gap. Renders on mobile via MobilePrivacyShell but its 4 buttons (Export, Delete, dialog Cancel, dialog Confirm) are ~26-30px tall. Deferred because PrivacyTab is desktop-shared — applying TOUCH_TARGET_CLASS unconditionally widens desktop buttons too. Future cycle picks between conditional (useIsMobile guard) or blanket (accept desktop cosmetic change).
- **C2** raw-string assertion in tests → import constant instead.
- **C3** no click-navigation test on Links → accepted as existing convention.

**K19f cluster 100% plan-complete** (α shell + β GlobalMobile + γ ProjectsMobile + δ JobsMobile + ε tap audit).

**Session 50 stats (final, session-closed state)**:
- **32 cycles shipped** (24 Track 3 + 2 Track 2 close-out + 6 Gap Closure: C1..C6)
- All Track 3 K19-series clusters (K19a through K19f) 100% plan-complete
- Track 2/3 Gap Closure Plan: P1 done · **P2 4/7 done** · 14 cycles remaining
- Front-end test coverage: **363 pass** at session 50 end (vs ~88 at session 47 end · +43 this session over C1–C6)
- Back-end test coverage: **1379 pass** at session 50 end (vs 1154 at session 47 end · +97 this session over C1–C6)

**What's next — Session 51 default path:** ✅ **Superseded.** Session 51 shipped C7 (as XL, not S — see aftermath note above for honest-sizing lesson) through C12b-b. See **Session 51** block at the top of this file for current status and the "What's next — Session 52 default path" pointing at **C13**.

**C6 aftermath — things to keep in mind for later cycles:**
- **BE denormalization > FE hook** when the data is cheap to look up at list-materialization time and both consumer surfaces share the root cause. Singleton `get_book_client` Depends + shared enricher helper (mutating in-place on Pydantic models) + 4 router wire sites was cleaner than a FE `useChapterTitles` hook would have been
- **Etag must include every field that feeds the response body** — the L6-pattern to watch for: if `_etag(x)` computes over `updated_at` only, any new `x.<field>` that flows into response JSON via enricher won't bump the etag, FE serves stale via 304. `hashlib.md5(...usedforsecurity=False)` for the stable hash (NOT Python's `hash()`, which is PYTHONHASHSEED-randomized per-process → different etag per worker)
- **Graceful-degrade chain has 4 layers, each needs its own test** — BE drops inactive/missing chapters → BookClient returns `{}` on HTTP failure → enricher short-circuits on empty dict → FE falls back via `chapter_title ?? chapterShort(chapter_id)`. Layer 1 Go test, layer 2 respx test, layer 3 enricher unit test, layer 4 vitest. Skipping any layer leaves a silent-degradation hole
- **Cross-service internal handlers with `requireInternalToken`** trust any service holding the shared token to query any IDs. knowledge-service only queries chapter_ids it already holds (from its own tenant-scoped Neo4j), so the leak surface is zero today. If a future service shares the token, this becomes a tenant-isolation concern — worth flagging in the internal-route review checklist
- **`rows.Err()` after pgx `for rows.Next()` loop** — without it, scan errors from schema drift (wrong column type, column dropped) silently return empty maps. With it, they surface as 500s. Cheap defense, high dividend

**C5 aftermath — things to keep in mind for later cycles:**
- **`TOUCH_TARGET_MOBILE_ONLY_CLASS` (`min-h-[44px] md:min-h-0`)** for padding-driven buttons on desktop-shared components; **`TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS` (`min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0`)** for icon-only buttons (X close, settings, kebab). Always pair the SQUARE variant with `inline-flex items-center justify-center` so the icon re-centers inside the expanded 44px box — otherwise sticks to top-left
- **Pure Tailwind `md:` class swaps** preferred over `useIsMobile()` for simple responsive CSS changes — no re-render, SSR-safe, class names are testable
- **Dual render-tree pattern** (`hidden md:block` desktop + `md:hidden` mobile) for components where the mobile layout is structurally different from desktop — cleaner than one tree with many `hidden md:inline` spans. `display: none` removes the other tree from the a11y tree in real browsers; jsdom sees both but className assertions catch class-drop regressions
- **Mobile cards that replicate desktop table structure** should drop `role="row"` for native `<button>` + `aria-label` — there's no columnheader context on mobile and SRs get confused. Desktop keeps `role="row"` for its columnheader context
- **Full-width mobile panels BREAK overlay-click-dismiss** — the panel covers the overlay entirely. Icon-only close buttons then become the sole dismiss and NEED the square tap-target treatment. Always audit mobile dismiss paths when moving from `max-w-*` to full-width

**C4 aftermath — things to keep in mind for later cycles:**
- **`vi.hoisted()` is the canonical hoist-beater** for mock vars in vitest — memory `feedback_vitest_hoisted_mock_vars.md` confirmed. First-attempt BUILD always hits the ReferenceError; always reach for `vi.hoisted()` from the start
- **Global `react-i18next` mock returns raw keys** — this MUTES toast-opt-drop regressions. For tests that need to verify `{label, error}` opts are passed through, write a **local** `react-i18next` mock override that encodes opts as `"<key>|<json>"`. Pattern now established in `useProjectState.actions.test.tsx`
- **Plan "N action" counts are often vibes** — C4's plan said "11 actions" but audit showed 8 BE-firing + 6 placeholders (archive/restore/disable not in the hook). Always audit the actual callback surface before committing to a test count
- **`Object.values(apiMocks)` loop** for `beforeEach` mock reset — future API additions auto-reset. Generalize this pattern for all future hook-test files with multiple API mocks

**C3 aftermath — things to keep in mind for later cycles:**
- `_emit_log` pattern (optional repo + best-effort try/except + UUID parse) is now established for BE→job_logs producers — any new extraction-pipeline stage that wants to surface progress to the FE JobLogsPanel should reuse the same contract
- Advisory lock key series `20_310_00{1,2,3}` is contiguous — next retention/scheduler loop should use `20_310_004`+ to stay in the K20.x/K19b.8 numbering family
- `useInfiniteQuery` refetchInterval refetches ALL loaded pages with their original pageParams — tail-follow is automatic because the last page's response grows as the server appends; NEW pages only appear when the last page fills (50 rows) and `hasNextPage` flips back to true
- `<details>` + `onToggle` + rAF scrollTo is the vetted pattern for "show latest on open" UX in collapsed panels — reusable in future collapsed-viewer components
- FakeConn + FakePool convention lives in `test_job_logs_retention.py` and `test_summary_regen_scheduler.py` — if a 4th scheduler lands, consider hoisting to a shared `tests/unit/_fake_pool.py` fixture module
- Two /review-impl cycles in a row caught `<details>`-style defensive branches that unit tests don't exercise (C2's MED-1 cooldown-on-5xx; C3's MED-1 toggle-open scroll). Pattern: **when a component has state that persists across visibility changes (collapsed/closed panels, route changes, tab switches), the first-open/first-visible path is a coverage hole** — any future component with similar lifecycle should get an explicit toggle/open regression test

Remaining cycles after C2 (grouped by tier):
- **P2 (C3–C9)** — 14 items / 7 cycles: job_logs observability trio · useProjectState hook tests · mobile polish · chapter-title resolution · ETA formatter · drawer-search UX · entity concurrency+unlock
- **P3 (C10–C13)** — 7 items / 4 cycles: timeline gaps · cursor pagination · scope+benchmark dialog · Storybook dialogs via MSW
- **P4 (C14–C15)** — 3 items / 2 cycles: resumable scheduler cursor state · Neo4j fulltext index (fire only at >10k entities)
- **P5 🏗 (C16–C18)** — 3 items / 3 cycles, all DESIGN-first: budget attribution · entity-merge canonical-alias mapping · event wall-clock date
- **User-gated ⏸ (C19–C20)** — multilingual fixtures (user provides text) + Gate-13 human walkthrough

**NOT the default path but possible if user redirects:**
- Continue Track 3 feature cycles (K19g-h, K21 tool calling, K22 privacy page)
- Gate-13 T2-close-2 walkthrough (user-attested BYOK run)
- Data re-engineering ([101_DATA_RE_ENGINEERING_PLAN](../03_planning/101_DATA_RE_ENGINEERING_PLAN.md))

**Starting-session boilerplate:**
1. Read [SESSION_PATCH.md](SESSION_PATCH.md) cycle-32 entry + the plan file's §3 cycle table
2. `./scripts/workflow-gate.sh status` to confirm previous cycle closed
3. Start C7 with `./scripts/workflow-gate.sh size S 3 2 0` then `phase clarify` (S — pure-FE ETA formatter utility + ~2 consumer surfaces + tests; no BE change, no cross-service contract. Side effects = 0)
4. Infra: `docker ps --filter name=infra-` — C7 is FE-only unit tests + no integration path; services can stay up or down
5. For Postgres integration tests (if needed in a subsequent cycle): `TEST_KNOWLEDGE_DB_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge` (port 5555 on host; container maps to 5432; DB name `loreweave_knowledge` NOT `knowledge`)
6. For Neo4j integration tests: `TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_PASSWORD=loreweave_dev_neo4j`
7. For manual-curl verify, JWT gen one-liner: `python -c "import jwt,uuid,datetime; print(jwt.encode({'sub':str(uuid.uuid4()),'exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=10)},'loreweave_local_dev_jwt_secret_change_me_32chars',algorithm='HS256'))"` → `curl -H "Authorization: Bearer $TOKEN" http://localhost:8216/...` (if Neo4j is down, extraction-path tests will 500/503 — known Track 1 limitation)

---

### Cycle 23 — K19f Cycle δ [FE L] — JobsMobile (K19f.3)

Ships the third simplified mobile variant. Merged active+history sorted list (`STATUS_SORT_ORDER: running → paused → pending → failed → cancelled → complete`, within-status newer-first) with **Map-based dedup by job_id** (active wins on conflict — handles the 2s/10s poll transition race). Per card: project_name + colored status badge + progress bar (running/paused only) + Intl-formatted started_at. Tap → inline expand with items counters, timestamps, error message (failed only), action buttons per status. Actions: `pauseExtraction / resumeExtraction / cancelExtraction` with `stopPropagation` + `invalidateQueries(['knowledge-jobs'])` on success. **Dropped** per plan: CostSummary, per-status sections, JobDetailPanel, JobLogsPanel, retry-with-new-settings.

`/review-impl` caught **3 MED + 6 LOW + 1 COSMETIC; 3 MED + 5 LOW fixed in-cycle**:
- **M1** duplicate `key` React warning when same job_id appears in both active (2s poll, stale) + history (10s poll, fresh) during running→complete transition → Map dedup with active-wins-on-conflict + regression test.
- **M2** Resume + Cancel API paths completely untested — only Pause was exercised, so runAction's if/else-if/else branch swap would pass → 2 new tests clicking each + asserting correct mock called.
- **M3** `queryClient.invalidateQueries` contract untested (same gap class as ProjectsMobile refetch) → `vi.spyOn(QueryClient.prototype, 'invalidateQueries')` + assertions on all 3 actions + NOT-called on failure.
- **L4** stopPropagation batch coverage on Resume + Cancel · **L5** action-failure toast · **L6** project_name null fallback · **L7** same-status sort tiebreaker · **L9** historyError branch — all added.
- Accepted: **L8** progress-bar edge cases (BE data-error territory) · **C10** memoization `?? []` dep instability (minor perf).

**5th cycle in a row** `/review-impl` paid meaningful dividends. **M1 is notable** — it's a real production bug (React key collision + potential render drop), not just a coverage gap. The pattern of active+history merging should carry a dedup step any time the caller flattens them.

**What Cycle ε / final cycle inherits:**
- All 3 mobile variants (Global / Projects / Jobs) live
- `lib/touchTarget.ts` with `TOUCH_TARGET_CLASS` applied across mobile variants
- `components/mobile/` convention stable
- Stub pattern proven: data-testid buttons inside stubs expose swallowed callbacks
- `vi.spyOn(QueryClient.prototype, 'invalidateQueries')` pattern for verifying react-query contract

**Remaining K19f work:**
- **K19f.5** full tap-target audit across existing desktop components — sweep `grep -r 'py-1\|py-1.5\|h-6\|h-7'` for sub-44px interactive elements. Deferrals D-K19d-β-01 (EntitiesTable mobile grid) + D-K19e-β-02 (Timeline responsive) remain open but are hidden behind the desktop-only banner on mobile, so fixing them is not a K19f gate.

**Test deltas at δ end:**
- FE knowledge+pages vitest: **320 pass** (was 303 at K19f γ end; **+17** = 10 initial + 7 /review-impl regression)
- `tsc --noEmit` clean

---

### Cycle 22 — K19f Cycle γ [FE L] — ProjectsMobile (K19f.2)

Ships the second simplified mobile variant. Stacked card list reusing `useProjects(false)`: name + project_type badge + extraction_status badge (5-value raw status, NOT the 13-state machine) + description preview. Tap card toggles inline expand showing full description + Intl-formatted last_extracted_at + embedding_model + Build button (reuses existing BuildGraphDialog with `stopPropagation` keeping the card expanded). Dropped per plan: Create/Edit/Archive/Delete dialogs + all 13-state-machine action buttons.

`/review-impl` caught **1 MED + 4 LOW; all 5 fixed in-cycle**:
- **M1** `onStarted` → `refetch()` contract completely untested — initial BuildGraphDialog stub didn't expose the callback. Fixed by expanding stub with `simulate-build-started` button + regression test asserting `refetch` called.
- **L2** raw ISO `last_extracted_at` (same pattern K19e γ-b fixed for drawer created_at) → `Intl.DateTimeFormat` helper.
- **L3** empty-description fallback branch untested → test with `description: ''` asserts `noDescription` renders.
- **L4** truncate long-path untested → 200-char description test asserts `…` present + full 200-A's not present.
- **L5** `onOpenChange(false)` dialog-close path untested → stub exposes `simulate-close` button + regression test asserts dialog unmounts.

**Retro — 4th cycle in a row where /review-impl caught a stub-test coverage pattern.** The pattern is now clearly documented: test stubs for complex children should expose the callback props the parent contracts with, not just the render shape. A "happy div" stub that swallows callbacks hides the contract.

**What Cycle δ (JobsMobile) inherits:**
- `components/mobile/` convention established
- `lib/touchTarget.ts` with `TOUCH_TARGET_CLASS` constant applied to all interactive elements
- Stub pattern: expose callback props via `data-testid` buttons inside the stub so tests can drive them
- Keep desktop dialogs as-is (cramped but functional) unless mobile UX becomes painful
- i18n pattern: `mobile.<variantName>.*` sub-block + MOBILE_KEYS iterator extension per cycle

**Test deltas at γ end:**
- FE knowledge+pages vitest: **303 pass** (was 291 at K19f β end; **+12** = 8 core + 4 /review-impl regression)
- `tsc --noEmit` clean

---

### Cycle 21 — K19f Cycle β [FE L] — GlobalMobile (K19f.4) + tap-target utility

Ships the first simplified mobile variant. 150-line `GlobalMobile` keeps textarea + save + char count + unsaved badge; drops per plan: Reset, Regenerate, Versions, PreferencesSection, token estimate, version counter. **Keeps If-Match conflict handling** — dropping would let a mobile save silently stomp a desktop edit. NEW `lib/touchTarget.ts` exports `TOUCH_TARGET_CLASS = 'min-h-[44px]'` constant as K19f.5 audit groundwork; save button is first consumer. NEW `components/mobile/` directory (future home for ProjectsMobile + JobsMobile). MobileKnowledgePage swaps `<GlobalBioTab />` → `<GlobalMobile />`. 8 i18n keys × 4 locales.

`/review-impl` caught **1 HIGH + 2 LOW + 1 COSMETIC; all 4 fixed in-cycle**:
- **H1** 412 "regression test" used a plain-object mock error that failed `isVersionConflict`'s `err instanceof Error` type guard → took generic-error else branch, passed for wrong reason. Fixed via `makeConflictError` helper building a proper `Error` with `.status=412` and `.body={content,version}`, plus 2-click pattern asserting `expectedVersion` advances 3→4 on retry (STRONG signal the baseline absorbed).
- **L2** no assertion that `TOUCH_TARGET_CLASS` is applied to save → regression could ship 32px button; fixed with `expect(save.className).toContain('min-h-[44px]')`.
- **L3** whitespace-only save branch untested → added test verifying `"   "` → `{content: ''}` payload.
- **C4** `UseSummariesReturn = ReturnType<typeof useSummariesMock>` resolved to `undefined` → replaced with explicit `HookReturn` interface.

**Retro — third cycle in a row where /review-impl caught a test that passed for the wrong reason.** Pattern is now clear: any regression test that claims to lock a defensive branch must PROVE the branch ran (via observable downstream state change), not just that "the error path didn't crash."

**What Cycle γ (next) inherits:**
- `lib/touchTarget.ts` available — apply `TOUCH_TARGET_CLASS` to every interactive element in ProjectsMobile
- `components/mobile/` directory convention established
- i18n pattern: `mobile.<variantName>.*` sub-blocks + MOBILE_KEYS iterator extensions per-cycle
- MobileKnowledgePage swap pattern: replace desktop tab import with mobile variant, update test stub

**Test deltas at β end:**
- FE knowledge+pages vitest: **291 pass** (was 286 at K19f α end; **+5** = 4 GlobalMobile tests + 1 whitespace test; HIGH fix strengthened existing test without adding one)
- `tsc --noEmit` clean

---

### Cycle 20 — K19f Cycle α [FE L] — Mobile shell (K19f.1 MVP)

Opens the K19f Mobile UI cluster. NEW `useIsMobile` hook via `window.matchMedia('(max-width: 767px)')` with synchronous first-render read (no FOUC) + live `change` listener + SSR-safe guards + listener cleanup. NEW `MobileKnowledgePage` single-column shell: 3 stacked sections (Global bio / Projects / Extraction jobs) **reusing existing desktop tab components inline** + "use desktop for Entities/Timeline/Raw" banner + Privacy footer link. NEW `MobilePrivacyShell` renders just PrivacyTab body + back link — avoids the 7-tab desktop nav overflowing on <768px. KnowledgePage guard: `if (isMobile) { if (privacy) <MobilePrivacyShell /> else <MobileKnowledgePage /> }`.

`/review-impl` (user-invoked) caught **2 MED + 1 COSMETIC; both MEDs fixed in-cycle**:
- **M1** mobile + /knowledge/privacy fell through to desktop render shipping the 7-item tab nav → added `MobilePrivacyShell` component + dedicated mobile-privacy branch + `mobile.backToKnowledge` i18n × 4 + regression test asserting `queryByRole('tablist') === null`
- **M2** KnowledgePage had zero test coverage for the new mobile guard → created `pages/__tests__/KnowledgePage.test.tsx` with 4 branch tests (desktop / mobile-non-privacy / mobile-privacy / desktop-privacy) mocking `useIsMobile`
- **C3** mid-effect `setIsMobile(mql.matches)` is defensive-only no-op in production → accepted as documented

Scope-trim deferrals (from CLARIFY):
- **K19f.2/.3/.4** separate `ProjectsMobile/JobsMobile/GlobalMobile` simplified variants — MVP reuses existing tabs inline; build variants when the cramp becomes a real UX problem
- **K19f.5** tap-target audit (44px minimum) — do during Cycle β when mobile variants land
- **D-K19d-β-01 + D-K19e-β-02** mobile-responsive EntitiesTable + Timeline grids — those tabs are **hidden** on mobile via the desktop-only banner, so fixing their grids waits for mobile variants for those tabs

**What Cycle β (next) inherits:**
- `useIsMobile` hook + `MobileKnowledgePage` / `MobilePrivacyShell` components exist and are stable
- Embedded desktop tabs render inside sections — if ProjectRow / JobRow feel cramped at 375px, swap those for simpler mobile card variants
- Dialog `max-w-md` (448px) overflows on 375px phones — Radix pads the viewport but content may be squished; candidate for dialog-level responsive tweaks
- No automated tap-target coverage — K19f.5 audit is manual or via Playwright

**Test deltas at K19f α end:**
- FE knowledge vitest: **286 pass** (was 271 at K19e γ-b end; **+15** = 3 hook + 4 mobile-page [incl MobilePrivacyShell M1 regression] + 4 KnowledgePage + 4 iterator assertions)
- `tsc --noEmit` clean

---

### Cycle 19 — K19e Cycle γ-b [FE XL] — RawDrawersTab consuming γ-a endpoint

Ships the user-facing Raw drawers tab on top of γ-a's BE. NEW `useDrawerSearch` hook (userId-scoped queryKey per K19d β M1, disabled-gate via `project_id + query.length >= 3`, retry:false). NEW `DrawerResultCard` presentational with colored source-type badge (chapter/chat/glossary) + amber hub badge + Intl-clamped match-% + full a11y. NEW `DrawerDetailPanel` Radix slide-from-right mirroring K19d β EntityDetailPanel pattern with full text + metadata grid + `Intl.DateTimeFormat` on `created_at`. NEW `RawDrawersTab` container with **8 render branches** (no-project / no-query / short-query / loading / retryable-error+Retry / non-retryable-error+fix-config / not-indexed / empty / results) + 300ms debounce + retry-invalidates-prefix + `disabled={isFetching}` anti-double-fire.

**KnowledgePage swaps** `<PlaceholderTab name="raw" />` for `<RawDrawersTab />` **and removes PlaceholderTab + PlaceholderName entirely** — **every knowledge tab is now live**. The whole `placeholder.*` i18n block is deleted from all 4 locales, with a regression test asserting `bundle.placeholder === undefined`.

`/review-impl` (user-invoked) caught **3 LOW + 2 COSMETIC; ALL 5 fixed in-cycle**:
- **L1** no test proved 300ms debounce actually debounced rapid keystrokes (a regression to 0ms would have passed all 6 initial tests) → new test fires 5 rapid onChange events, asserts calls=1 with final query="bridge"
- **L2** `is_hub` field came over the wire but was never rendered → amber "Summary" badge on card + hub metadata row on detail panel + 4 new i18n keys × 4 locales
- **L3** raw ISO string in `created_at` → `formatCreatedAt` using `Intl.DateTimeFormat`
- **C4** redundant `&& queryActive` guard on `isLoading` (react-query's `enabled:false` already keeps it false) → removed
- **C5** error-banner could render empty string on oddly-shaped payloads → `?? t('drawers.unknownError')` fallback + new i18n key × 4 locales

Build-time catches: `jsx-a11y/button-name` lint on `<Dialog.Close asChild><button><X/></button></Dialog.Close>` (Radix merges props but lint doesn't see it) → moved `aria-label` + added `title` directly on the inner `<button>`; **fake-timers** for debounce test broke react-query's internal `setTimeout` causing cross-test cascade timeouts → switched to real timers + `waitFor`; initial project-dropdown tests fired `fireEvent.change` before `useProjects` options rendered (silent no-op) → added `selectProject` helper awaiting `findByRole('option')` first.

**What K19e Cycle γ-c / δ would inherit (if ever built):**
- Source-type filter UI on search — blocked on D-K19e-γa-01 BE fix
- Term highlighting in preview — D-K19e-γb-01
- Delete drawer (K19e.6), facts list + edit (K19e.7/.8) — separate BE work

**Test deltas at γ-b end:**
- FE knowledge vitest: **271 pass** (was 253 at K19e β end; **+18** = 3 hook + 7 tab incl debounce + 8 iterator assertions)
- `tsc --noEmit` clean

**K19e cluster 100% plan-complete** (K19e.1/.2/.3/.4/.5 shipped; K19e.6/.7/.8 deferred; K19e.9 i18n covered per-cycle; K19e.10 empty/loading states shipped).

---

### Cycle 18 — K19e Cycle γ-a [BE L] — Drawer search endpoint (K19e.5)

Opens the Raw-drawers sub-cluster. Ships the public `GET /v1/knowledge/drawers/search?project_id=&query=&limit=` endpoint — semantic search over `:Passage` nodes reusing proven K18.3 machinery 1-to-1 (no new Cypher). Server-side flow:

1. `ProjectsRepo.get(user_id, project_id)` → 404 on cross-user/missing
2. If project has no `embedding_model` → 200 `{hits:[], embedding_model:null}`
3. If `embedding_dimension` not in `SUPPORTED_PASSAGE_DIMS` → 200 empty
4. `embedding_client.embed(model_source="user_model", model_ref=project.embedding_model)` → 502 `{error_code:"provider_error", retryable:bool}` on `EmbeddingError`
5. Empty provider response (outer OR inner empty) → 200 empty
6. `find_passages_by_vector(include_vectors=False)` → `DrawerSearchHit[]`
7. 502 `{error_code:"embedding_dim_mismatch"}` if live-vs-stored dim disagree

CLARIFY-time scope trim:
- **D-K19e-γa-01** source_type filter (chapter/chat/glossary) — plan K19e.4 mentioned for FE tab layout; needs K18.3 `find_passages_by_vector` extended with new WHERE branch.
- **D-K19e-γa-02** drawer-search embed cost not tracked toward K16.11 monthly budget — hobby-scale $0.00002/search, real at scale.

`/review-impl` (user-invoked) caught **4 LOW + 1 COSMETIC; 3 fixed in-cycle + 1 deferred + 1 accepted**:
- **L1** mutable default arg in test helper (`_project_stub()` called at module load shared instance) → sentinel-guarded conditional assignment
- **L3** `retryable` flag on `EmbeddingError` was discarded → propagated onto 502 detail + paired regression tests for both True/False paths
- **L4** empty inner vector (`embeddings=[[]]`) fell through to `find_passages_by_vector` ValueError surfacing misleading `dim_mismatch` 502 → extended empty-short-circuit guard to `not result.embeddings or not result.embeddings[0]` + regression test
- **C5** no explicit test for `include_vectors=False` forwarding → added kwargs assertion
- **L2** deferred as D-K19e-γa-02

Build-time catches (all collection-error on first pytest run): `EmbedResult → EmbeddingResult` (wrong class name), `ProjectType.original → "book"` Literal (not enum), `ExtractionStatus.idle → "disabled"` Literal.

**What K19e Cycle γ-b (next) inherits:**
- `GET /v1/knowledge/drawers/search?project_id=&query=&limit=` → `{hits: DrawerSearchHit[], embedding_model: string | null}` (`hits` carries `id / project_id / source_type / source_id / chunk_index / text / is_hub / chapter_index / created_at / raw_score`)
- FE can render "not indexed yet" banner when `embedding_model === null`
- 502 `retryable: true` means show retry button; `false` means show "fix config" messaging
- `source_type` filter is UI-only today (client-side filter the returned `hits[].source_type`) OR pair with D-K19e-γa-01 BE fix
- Cycle γ-b scope: `useDrawerSearch` hook + `RawDrawersTab` container + `DrawerResultCard` (text preview + full-text slide-over click) + i18n + KnowledgePage swap for PlaceholderName='raw'

**Test deltas at γ-a end:**
- BE unit knowledge-service: **1282 pass** (was 1268 at K19e-α end; **+14** drawers)
- 63/63 router-adjacent unit pass (no regressions)

---

### Cycle 17 — K19e Cycle β [FE XL] — TimelineTab consuming α endpoint

FE consumer on top of Cycle α's BE. Ships the user-facing Timeline tab. New hook `useTimeline` (userId-scoped queryKey per K19d β M1, 30s staleTime, `enabled: !!accessToken`). New presentational `TimelineEventRow` with inline expand — event_order / title / chapter-short / up-to-3 participants chips + `+N more` overflow / confidence clamped to [0,100]. New container `TimelineTab` with project filter + prev/next pagination + loading/error/empty states + past-end escape hatch ("Back to first page" button when `total>0 && events=[] && offset>0`). KnowledgePage swaps PlaceholderTab for TimelineTab and narrows PlaceholderName to `'raw'` only. 20 i18n keys × 4 locales + `placeholder.bodies.timeline` removed from all 4 locales + TIMELINE_KEYS iterator locks both additions AND removal.

`/review-impl` caught **1 MED + 3 LOW + 2 COSMETIC, all fixed in-cycle:**
- **MED** pagination prev/next were untested — added 3 tests: Next advances offset, Prev re-disables at offset=0, Prev/Next both disabled when total fits one page.
- **L2** no `enabled: !!accessToken` regression test — added `renderHook` with `accessToken: null` asserting mock never called.
- **L3** `formatConfidence` didn't clamp to [0,100] — `Math.max(0, Math.min(100, pct))` defense vs data drift.
- **L6** stale-offset race when total shrinks below offset — added escape-hatch button + new `timeline.pagination.backToFirst` i18n key × 4 locales.
- **COSMETIC #4** duplicate `data-testid="timeline-event"` on outer `<li>` — removed.
- **COSMETIC #5** `_eventStub` underscore prefix misleading — renamed `EVENT_STUB`.

Build-time catches: `aria-expanded={boolean}` lint → switched to explicit `'true'|'false'` string; pagination tests initially used `mockClear()` + call-count assertions that raced with react-query's in-flight resolution → rewrote to assert DOM state transitions (Prev button disabled/enabled) which tests the actual user-visible contract.

**What Cycle γ (the next K19e piece) now inherits:**
- Range inputs for `after_order` / `before_order` can drop straight into TimelineTab — the hook already accepts them.
- Entity-scope drill-down requires BE work first (D-K19e-α-01 deferral).
- Chapter title resolution still shows raw UUID short form (D-K19e-β-01).
- Raw drawers tab is the next FE-only big piece (K19e.4+).

**Test deltas at K19e Cycle β end:**
- FE knowledge vitest: **253 pass** (was 232 at K19d γ-b end; **+21** = 4 hook + 9 tab + 8 iterator/placeholder-removal)
- `tsc --noEmit` clean

---

### Cycle 16 — K19e Cycle α [BE L] — Timeline list endpoint (K19e.2)

Opens the K19e Timeline + Raw-drawers cluster. BE foundation only; β ships the FE TimelineTab consuming this endpoint. CLARIFY-time scope trim:

- Shipped: `GET /v1/knowledge/timeline?project_id=&after_order=&before_order=&limit=&offset=` → `{events, total}`. JWT user-scoped, archived excluded, 2-query count+page split (O(limit) memory), stable pagination via `title ASC, id ASC` tiebreaker, 422 on reversed range.
- **D-K19e-α-01** `entity_id` filter deferred — `:Event.participants` stores display names; needs entity lookup. Natural fit for Cycle β/γ when FE drill-down lands.
- **D-K19e-α-02** ISO wall-clock `from`/`to` deferred — :Event has no date field; narrative `event_order` is the MVP axis.
- **D-K19e-α-03** `chronological_order` range deferred — let Cycle β FE decide if two-axis toggle is worth the UX.

`/review-impl` (user-invoked before COMMIT) caught **3 LOW** findings, all fixed in-cycle:
- **L1** integration test `_limit_clamped_to_max` seeded only 5 events so a removed clamp would still pass — replaced with 2 unit tests patching `run_read` to assert the exact `$limit` kwarg forwarded to Cypher (both clamp-fires and pass-through branches).
- **L2** no `event_user_project (user_id, project_id)` composite index on :Event even though `entity_user_project` exists — added to `neo4j_schema.cypher`, cleared **P-K19e-α-01**.
- **L3** unused `logger = logging.getLogger(__name__)` in `timeline.py` (read-only endpoint) — removed.

**What Cycle β (FE) now inherits:**
- `knowledgeApi.listTimeline({ projectId, afterOrder, beforeOrder, limit, offset })` wrapper to write.
- `{events: Event[], total: number}` response shape.
- `Event` type mirrors the BE Pydantic — re-use the K19d `Entity` pattern (fields: id, title, chapter_id, event_order, participants, summary, confidence, evidence_count, mention_count).
- 422 on reversed range → surface as toast + clear range input.
- No entity drill-down on BE yet — FE table can list entity names but can't filter by them.
- Schema index exists; project-scoped browse is cheap.

**Test deltas at K19e Cycle α end:**
- BE unit knowledge-service: **1268 pass** (was 1258 at K19d γ-b end; +10 net = 11 timeline - 1 weak integration test deleted)
- BE integration timeline: **11/11 live** against `infra-neo4j-1`
- 23/23 K11.7 events adjacent no regressions
- 49/49 router-adjacent no regressions from `main.py` change

---

## Session 50 — 15 cycles shipped (13 Track 3 + 2 Track 2 close-out) · K19b + K19c + K20 + K19d all 100% plan-complete

```
Track 3 K19b progress (session 50)

Cycle 1  K19b.1 + K19b.4    User-scoped jobs endpoint + hook + JobProgressBar    1c208ce + c79ea90
                            BE: list_all_for_user repo + GET /v1/knowledge/extraction/jobs
                            FE: listAllJobs, useExtractionJobs hook (2s/10s dual-poll),
                                JobProgressBar (6 statuses, indeterminate, Intl USD format)

Cycle 2  K19b.2 + K19b.7-    ExtractionJobsTab + project_name + jobs.* i18n      4fb8b62
         partial             BE: ExtractionJob +project_name + LEFT JOIN
                             FE: ExtractionJobsTab (4 sections, native <details>,
                                 per-group error banners, JobRow with fallback),
                                 jobs.* keys × 4 locales, KnowledgePage wired

Cycle 3  K19b.3 + K19b.5 +   JobDetailPanel (slide-over) + Retry + ETA           5e00f7b
         ETA                 FE-only. NEW useJobProgressRate (EMA hook, α=0.3,
                             60s stale-reset, module-scoped Map<jobId> shared
                             across hook instances). NEW JobDetailPanel (Radix
                             slide-from-right, metadata grid, Pause/Resume/Cancel
                             actions, error block, conditional Retry CTA). MOD
                             BuildGraphDialog +initialValues prop for retry
                             pre-fill. MOD ExtractionJobsTab wires row click
                             (role=button + Enter/Space), panel + retry state
                             (R1 single retryIntent, R2 close panel on retry,
                             R3 retry only for status=failed). +17 i18n keys
                             × 4 locales. Clears D-K19b.4-01 (ETA).

Cycle 4  K16.12 completion   Track 2 close-out. User-wide budget API.            b313c1b

Cycle 5  K19b.6 + D-K19a.5-03 CostSummary card + monthly-remaining hint           32a9a18

Cycle 6  D-K16.11-01         Wire budget helpers into production                 c9f7064
         [BE M]               extraction.py step 2.6 calls can_start_job +
                              check_user_monthly_budget with estimated_cost =
                              max_spend_usd ?? 0; 409 structured detail
                              (monthly_budget_exceeded / user_budget_exceeded).
                              worker-ai runner.py +_record_spending inline
                              helper (CASE-on-current_month_key rollover) +
                              called after every successful chapters / chat
                              extraction. Production current_month_spent_usd
                              now populates as jobs run → CostSummary card
                              finally shows real prod spending.

Cycle 7  K19b.8               Extraction-job log viewer MVP                       526533d

Cycle 8  K19c Cycle α          BE preload: user-scope entities endpoint           a619b5f

Cycle 15 K19d Cycle γ-b        Merge endpoint + FE edit/merge dialogs             c9aaf95
         [FS XL]                BE: merge_entities helper + MergeEntitiesError
                                with 4 codes (same_entity/entity_not_found/
                                entity_archived/glossary_conflict) + 6 Cypher
                                blocks (load/validate, collect both-direction
                                edges, UNWIND batch MERGE with Python-driven
                                relation_id recomputation, EVIDENCED_BY
                                rewire on job_id, target metadata update with
                                glossary pre-clear to dodge UNIQUE constraint,
                                DETACH DELETE source, Python post-dedupe).
                                NEW POST /v1/knowledge/entities/{id}/
                                merge-into/{other_id} with 400/404/409 error
                                envelope. FE: NEW useUpdateEntity + useMerge
                                Entity hooks with closed-union error codes +
                                source detail cache eviction on merge. NEW
                                EntityEditDialog (name/kind/aliases textarea
                                with trim+dedupe + no-op skip). NEW
                                EntityMergeDialog with search-to-select
                                target picker (reuses useEntities, filters
                                out source, FE min-2-char). EntityDetailPanel
                                gets Edit/Merge icon buttons + mounted child
                                dialogs. 37 i18n keys × 4 locales + ENTITIES
                                _KEYS iterator +148 cross-locale assertions.
                                /review-impl caught H1 (source self-relation
                                silently dropped — rewired then cascade-
                                deleted) fixed in-cycle with regression test.
                                M1/M2/M3 deferred (D-K19d-γb-01 ON MATCH
                                union gap, D-K19d-γb-02 non-atomic multi-
                                write, D-K19d-γb-03 post-merge canonical_id
                                mismatch — fundamental architectural).
                                Build-time fix: UNIQUE(glossary_entity_id)
                                violation when both source and target
                                transiently held same anchor → clear source
                                first in same SET statement. BE unit 1258
                                (+5 merge routes). Integration 23/23 live
                                (+9 merge scenarios). FE knowledge 232 (+14
                                = 5 hook + 5 edit + 4 merge dialog). tsc
                                clean; no unhandled rejections after wrapping
                                mutation calls in try/catch. K19d cluster
                                100% plan-complete. K19d.8 graph viz stays
                                optional per plan.

Cycle 14 K19d Cycle γ-a        PATCH entity + user_edited lock [BE half of γ]    5d42afd + db405f6
         [BE L]                 Entity.user_edited: bool = False + _MERGE_ENTITY_
                                CYPHER ON CREATE user_edited=false + ON MATCH
                                aliases CASE coalesce(user_edited,false)=true
                                gate (coalesce handles pre-γ-a nodes as
                                un-edited so existing extraction preserved).
                                NEW update_entity_fields helper + _UPDATE_ENTITY
                                _FIELDS_CYPHER per-field CASE (null=leave,
                                else overwrite) + canonical_name recomputed on
                                name change. NEW PATCH /v1/knowledge/entities/
                                {id} endpoint with EntityUpdate Pydantic:
                                at-least-one model_validator + per-alias
                                non-empty + ≤200 char + max 50. 404 on
                                cross-user/missing. Merge (K19d.6) split to
                                γ-b because RELATES_TO edges carry deterministic
                                IDs derived from subject_id → per-edge MERGE-
                                new+DELETE-old surgery is complex enough for
                                its own cycle. /review-impl L1 fixed (inline
                                // Cypher comments were first-in-codebase →
                                moved to Python #); M1 (no If-Match optimistic
                                concurrency, D-K19d-γa-01) + M2 (no unlock
                                mechanism for user_edited, D-K19d-γa-02)
                                deferred. Build-time catch: "The Phoenix" test
                                variant didn't hit ON MATCH branch because
                                "the" isn't in HONORIFICS strip list → switched
                                to "Master Phoenix" (master is stripped →
                                same canonical_id). BE unit 1253 (+4).
                                Integration entities browse 14/14 live (+4
                                γ-a scenarios incl user_edited-lock regression
                                + pre-γ-a regression). K19d γ-b (merge + FE
                                edit/merge dialogs + CTAs + i18n, ~12 files XL)
                                is the only K19d work remaining.

Cycle 13 K19d Cycle β          Entities tab FE (table + detail panel)            aeb008b + c920d95
         [FE XL]                NEW useEntities + useEntityDetail hooks (userId-
                                scoped queryKeys per review-impl M1, 30s/10s
                                staleTime). NEW EntitiesTable presentational
                                (a11y: role=row + tabIndex + onKeyDown for
                                Enter/Space). NEW EntityDetailPanel Radix Dialog
                                slide-from-right (metadata grid + aliases chips
                                + relations partitioned outgoing/incoming with
                                per-row ↗/↙ arrows + truncation banner +
                                pending-validation badge). NEW EntitiesTab
                                container with debounced search (300ms + FE
                                min-2-chars matching BE 422) + prev/next
                                pagination capped at maxOffset + offset-reset
                                on filter change. KnowledgePage replaces
                                PlaceholderTab with EntitiesTab. 38 i18n keys
                                × 4 locales (placeholder.bodies.entities
                                removed everywhere — same pattern as K19b.2
                                jobs removal). ENTITIES_KEYS iterator +152
                                cross-locale assertions. /review-impl caught
                                M1 (cross-tenant cache flash — 30s window
                                where logout→login swap shows prior user's
                                cached entities before refetch); fixed with
                                userId-prefixed queryKey + regression test.
                                M2 (mobile grid breaks <800px) deferred as
                                D-K19d-β-01 (K19f scope). Build-time fixes:
                                useDebounced with useMemo (leak) → useEffect;
                                useProjects.items not .projects. FE knowledge
                                218 (+15). tsc clean. K19d γ (edit/merge)
                                remains the only K19d work left.

Cycle 12 K19d Cycle α          Entities browse + detail BE [α of β/γ split]      96f9b6b + e0fbd21
         [BE L]                 NEW entities_router at /v1/knowledge prefix +
                                2 JWT-scoped endpoints: GET /entities (filters:
                                project_id/kind/search min-2ch/limit/offset) +
                                GET /entities/{id}. New neo4j repo funcs:
                                list_entities_filtered (2-query count+page split
                                per review-impl M1 for O(limit) memory) +
                                get_entity_with_relations (OPTIONAL MATCH +
                                collect-inside-subquery for 0-relations case).
                                EntityDetail Pydantic reuses existing Relation
                                subject/object projection. Anti-leak: cross-user
                                detail 404 per KSA §6.4. /review-impl caught
                                M1 (pagination materialized full tenant row-set
                                in memory to count) + L1 (entity_id Path had
                                no length cap); both fixed in-cycle with
                                regression tests. Build-time bug: plain CALL
                                subquery with MATCH drops outer row when inner
                                has 0 rows — fixed with OPTIONAL MATCH + collect
                                inside. BE unit 1249 (+10). Integration entities
                                browse 10/10 live. β (FE EntitiesTab + detail
                                panel) + γ (edit/merge) pending. P-K19d-01
                                logged (Neo4j fulltext index when entity count
                                crosses ~10k per user).

Cycle 11 K20 Cycle β+γ         FE consumer + metrics + dup check [K20 complete]   9289ded + 166c9e1
         [FS XL]                BE: metrics.py +4 series (regen_total{scope_type,
                                status}×12 pre-seeded labels + duration histogram
                                + cost_usd + tokens). regenerate_summaries.py
                                split into outer metrics wrapper + inner logic
                                (every status branch bumps counter once); +step
                                6b past-version dup check via list_versions(
                                limit=20) + same 0.95 jaccard threshold;
                                +_compute_llm_cost_usd helper + happy-path
                                cost/token recording. +8 unit tests. FE: NEW
                                useRegenerateBio hook with parseRegenerateError
                                closed-union errorCode from body.detail
                                .error_code + invalidates [SUMMARIES_KEY +
                                VERSIONS_KEY]; NEW RegenerateBioDialog reusing
                                BuildGraphDialog's ['ai-models', 'chat']
                                queryKey for cache share + inline banner for
                                user_edit_lock + distinct toasts for
                                concurrent/guardrail/provider/unknown + info
                                toast for similarity/empty-source. api.ts
                                +RegenerateRequest/Response + regenerateGlobalBio
                                wrapper. GlobalBioTab +Regenerate button
                                disabled={dirty} per review-impl H1 (without
                                guard the existing dirty-protection useEffect
                                would silently preserve local buffer over a
                                successful server regen). 21 new i18n keys ×
                                4 locales + GLOBAL_KEYS extension (+84 cross-
                                locale assertions). /review-impl caught H1
                                (dirty-textarea race), M1 (queryKey
                                fragmentation with BuildGraphDialog), L1
                                (dialog test coverage gap on 3 error paths);
                                all fixed in-cycle. BE unit 1239 (+8). FE
                                knowledge 203 (+13 = 5 hook + 8 dialog).
                                Drift integration 6/6 still live. K20 cluster
                                effectively complete — only K20.3 scheduler
                                + D-K20α-01 budget-integration half +
                                D-K20α-02 per-scope cooldown remain deferred.

Cycle 10 K20 Cycle α           BE regen helpers + public edge [unblocks K19c.2]   71530a1 + 5faaf08
         [BE L]                 NEW app/jobs/regenerate_summaries.py with 6-status
                                RegenerationResult (regenerated / no_op_similarity
                                / no_op_empty_source / no_op_guardrail /
                                user_edit_lock / regen_concurrent_edit) per KSA
                                §7.6. Drift rules: reads raw :Passage text not
                                current summary; 30-day manual-edit lock;
                                diversity check via word-set jaccard > 0.95; K20.6
                                MVP guardrails (empty / token_overflow / K15.6
                                injection) rejecting LLM output. NEW internal
                                endpoint `POST /internal/summarize` +
                                public edges `POST /v1/knowledge/me/summary/
                                regenerate` + `POST /v1/knowledge/projects/{id}/
                                summary/regenerate` (both JWT-scoped; 200/409/
                                422/502 HTTP mapping). /review-impl caught:
                                **H1** every regen wrote history as edit_source=
                                'manual' which would trip the 30-day edit lock
                                on the NEXT regen (fixed: EditSource Literal +
                                migration CHECK + SummariesRepo.upsert kwarg all
                                gain 'regen'; regen helper passes it); **M1** no
                                upfront ownership check on project scope (fixed:
                                `_owns_project` SELECT before LLM call).
                                Deferred: K20.3 scheduler, K20.5 rollback
                                endpoint, K20.7 metrics, D-K20α-01 cost
                                tracking, D-K20α-02 per-scope cooldown.
                                BE unit 1231 (was 1195; +36). Drift integration
                                6/6 live against infra-postgres-1 + infra-neo4j-1.

Cycle 9  K19c Cycle β          FE K19c-partial: reset + diff + preferences        8baa670 + 79503f2
         [FE XL]               Installed diff@^9 + @types/diff@^7. api.ts +Entity
                               type + list/archive wrappers. NEW useUserEntities
                               hook. NEW PreferencesSection (list + confirm +
                               archive + prefix-match invalidation with
                               docstring per review-impl L7). GlobalBioTab:
                               +token estimate (chars/4) + Reset button + confirm
                               dialog + <PreferencesSection/> wire below editor.
                               VersionsPanel preview modal: "Show diff vs current"
                               toggle rendering diffLines() chunks with
                               added/removed/context colour classes; useEffect
                               resets toggle per preview. +global.* i18n (26 new
                               keys × 4 locales). GLOBAL_KEYS iterator added
                               (104 cross-locale assertions). Mid-verify fix:
                               static vi.mock factory for useAuth tripped
                               vitest-2 unhandled-rejection detection on one hook
                               error test; switched to dynamic vi.fn() pattern
                               (matches useUserCosts working pattern). Review-impl
                               L7 fixed in-cycle (queryKey prefix-match docstring).
         [BE L]                 list_user_entities(scope='global') Neo4j helper +
                                GET /v1/knowledge/me/entities?scope=global +
                                DELETE /v1/knowledge/me/entities/{id} (reuses
                                archive_entity, idempotent per RFC 9110). Unblocks
                                K19c.4 FE in Cycle β. Prior audit found:
                                K19c.2 still BLOCKED on K20.x; K19c.1/.3 have
                                partial Track 1 coverage (GlobalBioTab +
                                VersionsPanel); this cycle strictly scopes to the
                                missing BE surface. /review-impl L6 caught
                                DELETE docstring lie about non-idempotent 404
                                (fixed + integration test locks contract).
         [FS XL]               BE: NEW job_logs table (BIGSERIAL + CHECK level +
                               FK CASCADE) + JobLogsRepo (append + cursor list)
                               + GET /v1/knowledge/extraction/jobs/{id}/logs
                               with since_log_id/limit pagination + 404 on
                               cross-user. Worker: _append_log inline helper +
                               5 lifecycle call sites (chapter_processed,
                               chapter_skipped, retry_exhausted, auto_paused,
                               failed). FE: listJobLogs API + useJobLogs hook
                               (staleTime 10s single-page) + NEW JobLogsPanel
                               collapsible inside JobDetailPanel. jobs.detail.
                               logs.* × 4 locales. 3 follow-up deferrals:
                               D-K19b.8-01 retention cron, D-K19b.8-02
                               orchestrator-side logs, D-K19b.8-03 tail-follow.
         [FE XL]              FE-only. NEW useUserCosts hook (staleTime 60s,
                              user_id-scoped queryKey). NEW CostSummary.tsx
                              with inline EditBudgetDialog (decimal regex
                              matches BE NUMERIC(10,4), progress bar colors
                              at 80%/100% thresholds). NEW shared
                              lib/formatUSD.ts after /review-impl caught
                              inconsistent formatting between CostSummary +
                              BuildGraphDialog. Wired into ExtractionJobsTab
                              top. BuildGraphDialog renders monthly-remaining
                              hint near max_spend via useUserCosts (clears
                              D-K19a.5-03). +17 costSummary.* keys + 1
                              maxSpend.monthlyRemaining × 4 locales.
         [BE L]              NEW user_knowledge_budgets table + UserBudgetsRepo
                             (get+upsert). Extended UserCostSummary response
                             with monthly_budget_usd + monthly_remaining_usd
                             (clamped >=0). NEW PUT /v1/knowledge/me/budget
                             endpoint (ge=0, null clears). NEW
                             check_user_monthly_budget helper in budget.py
                             (aggregates across user's projects, stale-month
                             filter). NEW idx_knowledge_projects_user_all
                             covering index for archived-inclusive scans.
                             Unblocks D-K19a.5-03 (monthly budget remaining
                             context in BuildGraphDialog). K19b.6 now has
                             everything it needs on the BE side.

Remaining K19 residuals: K19b.7-rest (other tabs' strings); K19c
                        partial (Cycle α shipped BE; Cycle β ships FE
                        deltas); K19d Entities tab (can reuse entities
                        endpoint pattern from Cycle α); K19e Raw tab.
                        K19b 100% PLAN-COMPLETE.
                        K19c.2 Regenerate still BLOCKED on K20.x.
```

**Test deltas at session 50 end (after 9 cycles):**
- Frontend knowledge: **190 pass** (was 112 at session 49 end; +78 over 6 FE cycles)
- Backend unit knowledge-service: **1195 pass** (was 1154 at session 49 end; +41 — no BE in Cycle 9)
- Backend unit worker-ai: **17 pass** (was 13 at K19b.6 end; +4 across Cycles 6+7)
- Backend integration: 30 extraction_jobs_repo + 5 user_knowledge_budgets + 5 job_logs + **6 list_user_entities** (new this cycle, against live Neo4j)
- Cycle 1 /review-impl: 5 LOW all fixed + 1 MED via review-code
- Cycle 2 review-code: 1 LOW fixed; /review-impl: 4 LOW all fixed
- Cycle 3 review-code: 2 LOW fixed; /review-impl skipped per human approval
- Cycle 4 review-code: 3 LOW accepted; /review-impl: 3 LOW all fixed
- Cycle 5 review-code: 1 LOW fixed; /review-impl: 1 LOW fixed
- Cycle 6 review-code: 10 LOW all accepted; /review-impl skipped per human approval
- Cycle 7 review-code: 1 LOW fixed; /review-impl skipped per human approval
- Cycle 8 review-code: 4 LOW accepted; /review-impl: 1 MED-doc fixed (DELETE idempotent-docstring lie + integration lock-in)
- Cycle 9 review-code: 6 LOW accepted; /review-impl: 1 LOW fixed (prefix-match queryKey invalidation docstring)

**What shipped in Cycle 3 (10 files, FE-only):**
- NEW `useJobProgressRate.ts` hook (EMA rate tracker, 6 tests)
- NEW `JobDetailPanel.tsx` (Radix slide-over with metadata grid + Pause/Resume/Cancel + conditional Retry, 6 tests)
- MOD `BuildGraphDialog.tsx` (+`initialValues` prop for retry pre-fill, +1 test)
- MOD `ExtractionJobsTab.tsx` (selectedJobId + retryIntent state, JobRow role=button + Enter/Space, retry getProject useQuery with error toast, +3 tests)
- MOD 4 locales (+17 `jobs.detail.*` + `jobs.retry.button` keys each)
- MOD `projectState.test.ts` (JOBS_KEYS +17 paths → 31 × 4 = 124 cross-locale assertions)

### What K19b.8 (next cycle candidate) can assume

**K19b.8 Log viewer** — standalone cycle, not blocked. Scope:
- BE schema: `job_logs(log_id BIGSERIAL PK, job_id UUID FK, user_id UUID, level TEXT, message TEXT, context JSONB, created_at TIMESTAMPTZ)` + index `(user_id, job_id, log_id DESC)` + retention cron (N days).
- Extraction-worker instrumentation at every chunker/extractor/error-path in `services/worker-ai/app/runner.py` keyed by `(user_id, job_id)`. Likely easiest via a custom Python logging handler that writes to the table.
- Public endpoint: `GET /v1/knowledge/extraction/jobs/{id}/logs?since_log_id=&limit=50` with cursor pagination.
- FE: `JobLogsPanel` inside `JobDetailPanel` (or new tab). Tail-follow with auto-scroll toggle. Virtual list for 1000+ lines.
- Size estimate XL; doable as a single cycle or split into BE + FE halves.

### What K19c Cycle β now ships (and what's still blocked)

K19c cluster is plan-complete except K19c.2 (regenerate). GlobalBioTab now
exposes token estimate + Reset button (server-side clear with confirm +
If-Match conflict handling). VersionsPanel preview modal has a diff-vs-current
toggle. New PreferencesSection component below the editor lists global
entities with delete-via-archive flow. See [SESSION_PATCH.md §Current Active
Work](SESSION_PATCH.md#current-active-work) for the detailed file list.

**K19c.2 still blocked on K20.x** — regenerate dialog can't land until K20
ships the `POST /internal/summarize` endpoint plus a public edge for it.

### Historical note — What K19c Cycle β initially assumed (now shipped)

Cycle α shipped the BE. Cycle β consumes:
- **GET** `/v1/knowledge/me/entities?scope=global&limit=50` → `{entities: Entity[]}` (Pydantic from `app/db/neo4j_repos/entities.py::Entity` — fields include `id`, `user_id`, `project_id: null`, `name`, `canonical_name`, `kind`, `aliases`, `confidence`, `updated_at`).
- **DELETE** `/v1/knowledge/me/entities/{entity_id}` → `204` on archive; `404` on cross-user / missing entity. **Idempotent** per RFC 9110 — second DELETE also returns 204.
- Query params validated: `scope: Literal['global']` (422 on invalid), `limit: int` ge=1 le=`ENTITIES_MAX_LIMIT=200`.

Cycle β scope (previously estimated XL, now trimmed by α):
- FE `api.ts`: `Entity` type + `listMyEntities` + `archiveMyEntity` wrappers
- NEW `hooks/useUserEntities.ts` with react-query staleTime pattern
- `GlobalBioTab.tsx`: +Reset button (confirm → clear to empty) + token estimate under char count (simple `content.length / 4` heuristic)
- `VersionsPanel.tsx`: diff viewer in preview modal (install `diff` npm ~4KB or inline line-diff)
- NEW `components/PreferencesSection.tsx`: renders global entities with delete confirm; wires into GlobalBioTab
- Tests + i18n × 4 locales

Cycle β is still ~L-XL; splitting it further if needed.

### K19b 100% plan-complete status

All 8 K19b tasks shipped this session:
- **K19b.1** ✅ (Cycle 1) — user-scoped jobs endpoint + hook
- **K19b.2** ✅ (Cycle 2) — ExtractionJobsTab layout
- **K19b.3** ✅ (Cycle 3) — JobDetailPanel slide-over
- **K19b.4** ✅ (Cycle 1) — JobProgressBar
- **K19b.5** ✅ (Cycle 3) — Retry with different settings
- **K19b.6** ✅ (Cycle 5) — CostSummary card
- **K19b.7-partial** ✅ (all cycles) — jobs.* i18n keys × 4 locales
- **K19b.8** ✅ (Cycle 7) — extraction-job log viewer MVP

**Integration state of the Jobs tab:**
- CostSummary reads real production `current_month_spent_usd` (wired in Cycle 6 via worker `_record_spending`).
- Budget-cap pre-check blocks jobs that would exceed per-project or user-wide monthly caps (Cycle 6).
- JobDetailPanel surfaces 5 lifecycle events via JobLogsPanel (chapter_processed, chapter_skipped, retry_exhausted, auto_paused, failed) alongside progress bar, metadata grid, error block, actions, and conditional retry CTA.
- ETA rendered via client-side EMA (Cycle 3).

**Follow-up polish deferrals** (none block shipping the Jobs tab):
- D-K19b.1-01 cursor pagination when user has >200 historical jobs
- D-K19b.2-01 "Show more" on Complete section
- D-K19b.3-01 human-readable "current item" from cursor
- D-K19b.3-02 humanised ETA formatter for >60min jobs
- D-K19b.8-01 retention cron for job_logs
- D-K19b.8-02 orchestrator-side pipeline logs (chunker/extractor stages)
- D-K19b.8-03 tail-follow auto-polling + load-more in JobLogsPanel

### What K19b.3 (detail panel) already ships — for future cycles consuming it

- `ExtractionJobsTab` rows are presentational, no click handler yet. Add `onClick` to `JobRow`, wire `role="button"` + `tabIndex={0}` + `onKeyDown` for Enter/Space.
- Single-job BE endpoint exists: `GET /v1/knowledge/extraction/jobs/{job_id}` (K16.5, session 47). Supports If-None-Match for 304. Returns `ExtractionJobWire` shape (including `project_name` — **wait**, no: K19b.2's `project_name` only populates via `list_all_for_user`'s LEFT JOIN. The single-job route still returns NULL for it). K19b.3 either (a) passes project_name through from the parent row (simplest, already fetched), (b) enhances the single-job endpoint to JOIN too, or (c) fetches the Project separately. Option (a) is zero-BE.
- `useExtractionJobs` exposes active + history lists. K19b.3's slide-over can look up the clicked job from that list without a second fetch (until poll staleness matters; within 2–10s the list data is fresh enough).
- Slide-over pattern: reuse shadcn `Sheet` component if present; else adapt the `Dialog` pattern from K19a.5 BuildGraphDialog. Keep state in `ExtractionJobsTab` (selectedJobId + onClose), not global.
- Retry CTA (K19b.5) goes INSIDE the slide-over on failed/cancelled jobs: button "Retry with different settings" opens BuildGraphDialog with the failed job's scope/model pre-filled. K19a.5's dialog accepts `initialValues` — verify shape matches.

### What the hook `useExtractionJobs` provides (unchanged from Cycle 1)

- Returns `{ active, history, isLoading, error, activeError, historyError }`.
- Polling: 2s active / 10s history (not-in-background via React Query default). Tab owns no timer logic.
- queryKey scoped `['knowledge-jobs', userId, 'active'|'history']` so logout→login on a shared QueryClient doesn't leak cross-user cache.
- Brief ≤10s transition gap when a job flips `running → complete` between the 2s active poll and the 10s history poll — job temporarily absent from both lists. Acceptable; `ExtractionJobsTab` doesn't mask today but K19b.3 could invalidate `['knowledge-jobs', userId, 'history']` from actions that transition jobs to terminal states.

### K19b.2 i18n boundary

- `knowledge.json` under `jobs.*` holds all K19b.2 strings (`loading`, `error.{active,history}`, `sections.*.{title,empty}`, `row.{started,completed,unknownProject}`).
- JOBS_KEYS iterator in `projectState.test.ts` neutralises the global `react-i18next` mock bypass: 14 paths × 4 bundles = 56 runtime assertions that each locale has the key populated. Any new jobs.* key needs to be appended to `JOBS_KEYS` at test-authoring time.
- `placeholder.bodies.jobs` removed from all 4 locales (the jobs tab is live; placeholder no longer reached). If someone re-introduces a placeholder state for jobs, add the key back.

### Schema-recovery lesson (session 50 Cycle 2)

The `test_k19b_2_list_all_project_name_null_when_join_misses` test initially used `ALTER TABLE DROP CONSTRAINT ... / ADD CONSTRAINT ...` to orphan a row. A mid-test failure left the DB with the FK removed AND orphan extraction_jobs rows, which meant the pool fixture's `TRUNCATE knowledge_projects CASCADE` couldn't cascade-clean extraction_jobs (no FK to cascade through), and the next run tried to re-ADD the FK against orphan data and failed. Manual recovery: `TRUNCATE extraction_jobs CASCADE` + `ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES knowledge_projects(project_id) ON DELETE CASCADE`. Rewritten test uses `SET LOCAL session_replication_role = 'replica'` in a transaction — skips FK triggers for writes inside that transaction only, never touches schema, auto-reverts on commit/rollback, zero leak on failure. **Takeaway for future cycles:** avoid DDL (ALTER) in tests when DML-level bypass is available. `session_replication_role`, `DEFERRABLE INITIALLY DEFERRED` constraints, and `DISABLE TRIGGER` (within a transaction) are all safer.

### FS-cycle audit lesson (K19b.1)

The CLARIFY-phase BE audit (per `feedback_fe_draft_html_be_check.md`) caught the user-scoped-list gap before any FE was drafted. Options presented were:
- (a) Reclassify to FS, add new endpoint — chosen
- (b) Expose `list_active` at HTTP layer only, defer history
- (c) Pure-FE N-fanout across `listProjects` + per-project `listExtractionJobs`

Option (a) won because K19b.2's layout sections (Running/Paused/Complete/Failed) map 1:1 to the `status_group` binary, so pushing the filter down to SQL is both cheaper (O(1) query per group) and less code-complex than any FE merging. The option-(c) N-fanout would have worked for a demo but broken at ~10 projects per account. This is exactly the class of call the `feedback_fe_draft_html_be_check.md` rule exists to force before CLARIFY is closed.

### Still deferred after K16.12 completion

- **D-K19b.1-01** → Track 3 polish: cursor pagination for history once users cross ~150 historical jobs.
- **D-K19b.2-01** → Track 3 polish: "Show more" CTA on Complete section (BE ships 50, FE slices 10).
- ~~D-K19b.2-02~~ — **Cleared in K19b.3**.
- ~~D-K19b.4-01~~ — **Cleared in K19b.3**.
- **D-K19b.3-01** → Track 3 polish: human-readable "current item" from cursor. Needs BE cursor enrichment OR FE chapter-title lookup.
- **D-K19b.3-02** → Track 3 polish: humanised ETA formatter for >60min jobs.
- ~~K19b.8~~ — **Cleared in Cycle 7** (MVP shipped). D-K19b.8-01/02/03 tracked below for polish.
- **D-K19b.8-01** → Track 3 polish: retention cron for job_logs (no auto-cleanup today).
- **D-K19b.8-02** → Track 3 polish: orchestrator-side pipeline logs in knowledge-service extract_item handler.
- **D-K19b.8-03** → Track 3 polish: tail-follow auto-polling + load-more in JobLogsPanel.
- **D-K19c.4-01** (new, Cycle 8) → K17/K18 entity-management surface: rename-aware `user_archive_entity` variant that preserves `glossary_entity_id` on archive. Current `archive_entity` clears the FK per its K11.5a scope; fine for user-MVP but imperfect for the "hide now, restore later" flow.
- ~~D-K19a.5-03~~ — **Cleared in K19b.6** (BuildGraphDialog monthly-remaining hint shipped).
- ~~D-K16.11-01~~ — **Cleared in Cycle 6.** Budget helpers wired into production; CostSummary will now populate real figures as jobs run.
- **D-K19a.5-04 + D-K16.2-02b** → Track 3 (paired): chapter_range picker + runner-side enforcement.
- **D-K19a.5-06** → Track 3 polish: `glossary_sync` scope option in BuildGraphDialog.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog.
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests for `useProjectState`.
- **D-K19a.8-01** → Track 3 polish: MSW-backed dialog stories.

---

## Session 49 — 4 Track 3 cycles shipped (K19a.5 + K19a.6 + K19a.7 + K19a.8)

```
Track 3 K19a progress (session 49)

Cycle 6  K19a.5  BuildGraphDialog + ErrorViewerDialog          3148751
         + session_handoff HEAD backfill                        1156193
Cycle 7  K19a.6  ChangeModelDialog + destructive confirms +     2226283
                 BE POST /extraction/disable (FS)
         + HEAD backfill                                        7cf394f
Cycle 8  K19a.7  i18n polish (runAction + PrivacyTab + 4        2cbcc7c
                 locales + ACTION_KEYS typo defence)
         + HEAD backfill                                        c6ee80a
Cycle 9  K19a.8  Storybook 10 install + 13 ProjectStateCard     TBD
                 stories (Vite alias @/auth → MockAuth)

Track 3 K19a cluster: 100% complete (8 non-optional + 1 optional)
```

**Test deltas at session 49 end:**
- Frontend knowledge (+ shared ConfirmDialog): **112 pass** (was 75 at session 48 end; +37 content across K19a.5/6/7)
- Storybook: 14 stories build clean; `npm run build-storybook` 10.7s
- BE: +5 new tests (POST /extraction/disable — happy + 404 + 409 active + 409 paused + idempotent no-op)
- /review-impl across all 4 cycles caught **6 MED + 13 LOW + 5 COSMETIC**; every code finding fixed in-cycle except 2 accepted silently (K19a.7 F4 vitest stub churn + K19a.8 F3 Playwright binaries one-time cost); 10 D-K19a.*-* deferrals logged, 2 cleared in K19a.6 (D-K19a.5-01 change-model, D-K19a.5-02 disable-without-delete)

**What shipped:**
- `BuildGraphDialog.tsx` — scope selector (chapters/chat/all, `chapters` hidden when `!book_id`), chat-model dropdown, embedding picker (reuses K12.4), max_spend decimal-validated input, debounced auto-fetch estimate preview, benchmark pre-flight gate, BE-detail error extractor (`readBackendError` exported for unit test).
- `ErrorViewerDialog.tsx` — shared viewer for `failed` + `building_paused_error`. Job metadata grid + pre-wrapped error text + Copy button.
- Wired via `ProjectRow` dialog-state lifting + `useProjectState` stubs becoming silent no-ops. Merge deps narrowed to `errorPayloadKey` so actions don't re-create on poll tick.

### What K19b can now assume

- All 14 `ProjectStateCardActions` callbacks are wired: 9 fire BE APIs (pause/resume/cancel/retry/extractNew/delete/rebuild/confirmModelChange/ignoreStale), 5 open parent-lifted dialogs/confirms (buildGraph/start/viewError/changeModel/disable).
- `ProjectRow` is the canonical merge point for dialog-dependent actions — lift dialog/confirm state, spread `baseActions`, override the relevant callbacks. For destructive actions, route through `runDestructive(PROJECT_ACTION_KEYS.xxx, op, close)` so ConfirmDialog's `loading` prop shows in-dialog spinner + toast carries the right translated label.
- `readBackendError` lives at `frontend/src/features/knowledge/lib/readBackendError.ts` (K19a.6 F7). Any new dialog surfacing 4xx errors should import from there — `apiJson` only reads top-level `.message` but FastAPI wraps as `{detail: ...}`.
- `ChangeEmbeddingModelResponse` is a discriminated union (warning / noop / result); future callers must narrow before treating as success — K19a.6 F2 fixed the silent-success-on-no-op bug.
- `ConfirmDialog` now disables Cancel + X buttons while `loading=true`. Pattern is consistent across all destructive flows.
- `useProjectState` exports `PROJECT_ACTION_KEYS` (K19a.7 F1) — a compile-time map of action → i18n key. Consumers wanting to surface BE errors as localised toasts should import this rather than repeating string literals; typos become build errors.
- Zero hardcoded toast/label/body strings remain in `frontend/src/features/knowledge/` — `grep -r "toast\.(error\|info\|success\|warning)\(['\"]"` confirms. New dialogs should use `useTranslation('knowledge')` from the start.
- Storybook (K19a.8) is installed with 14 stories covering all 13 `ProjectMemoryState` kinds. `npm run storybook` dev-serves at port 6006; `npm run build-storybook` produces a static catalog. `.storybook/main.ts` aliases `@/auth` → `MockAuthProvider` so any future story can render real components that call `useAuth` without wiring it explicitly.
- BE endpoints now cover all Track 3 K19a surfaces:
  - `DELETE /extraction/graph` — destructive delete
  - `PUT /embedding-model?confirm=true` — destructive change-model (deletes graph + disables)
  - `POST /extraction/disable` — **non-destructive** disable (preserves graph)
  - `POST /extraction/rebuild` — destructive rebuild (delete + start fresh job)

### Still deferred after K19a.7

- **D-K19a.5-03** → K19b.6: Monthly budget remaining context in BuildGraphDialog max-spend field (needs BE `/v1/me/usage/monthly-remaining` endpoint).
- **D-K19a.5-04** → paired with D-K16.2-02b: FE chapter_range picker (BE preview honours, runner doesn't — ship both together).
- **D-K19a.5-05** → superseded by D-K19a.7-01: half closed (F1 typo prevention via `ACTION_KEYS` const); other half now tracked as D-K19a.7-01.
- **D-K19a.5-06** → K19a.7 (NOT done in this cycle): `glossary_sync` scope option in BuildGraphDialog (BE accepts, FE doesn't expose). The "K19a.7" polish cycle focused on string i18n, not scope-list expansion. Re-target to Track 3 polish or K19b as convenient.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog when `has_run=false` (needs POST endpoint for eval harness).
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests (inherits action-fire-path coverage from D-K19a.5-05).
- **D-K19a.8-01** → Track 3 polish: dialog stories for BuildGraphDialog / ChangeModelDialog / ErrorViewerDialog. Needs MSW handlers for `knowledgeApi` interception. Mock auth already wired via K19a.8 Vite alias.

### FS-cycle payload-audit lesson — response-side variant

K19a.5 F1 surfaced the BE `{detail: {message}}` body-extraction gap. K19a.6 F2 added another class: **response shape ambiguity under idempotent/no-op paths**. The BE `PUT /embedding-model?confirm=true` returns three different shapes — warning (confirm=false), no-op (same-model, either direction), result (confirm=true, different model). FE must narrow the discriminated union before treating as success; otherwise a cross-device race turns a silent no-op into a false "success" UX. For future FS cycles with idempotent BE endpoints: **list every BE response branch at CLARIFY time**, not just the happy path.

### i18n silent-fallback lesson (K19a.7)

i18next silently falls back to the raw key path when a key is missing, so a callsite typo like `t('projects.state.actions.pauze')` doesn't crash — it renders `"projects.state.actions.pauze: rate limit"` in the user-visible toast. Runtime JSON-resource iterators catch missing resources but NOT typos at the callsite. Defence: a compile-time constant map (`ACTION_KEYS` in `useProjectState.ts`) turns every callsite into a TypeScript literal lookup so typos become build errors. For any future i18n-heavy module, introduce the const map up front rather than threading string literals.

### Storybook-init quirks (K19a.8)

`npx storybook@latest init --type react` is aggressive: it modifies `vite.config.ts` to inject `@storybook/addon-vitest` plumbing AND downloads ~200 MB of Playwright browser binaries for that addon — even on a no-install run. For a minimal Storybook-only setup:
1. Use `--skip-install` to avoid committing to deps before review.
2. Edit `package.json` to REMOVE `@storybook/addon-vitest`, `@chromatic-com/storybook`, `addon-onboarding`, `@vitest/browser`, `playwright` before `npm install`.
3. `git checkout HEAD -- vite.config.ts` to undo the vitest-addon workspace plumbing (it adds a `test: {workspace: [...]}` block that references the removed addon).
4. Ctrl-C the prompt that asks to install Playwright browser binaries — it comes AFTER addon config, not at the start.
5. Delete the `src/stories/` example directory (Button/Header/Page scaffold) and `vitest.shims.d.ts` shim file.
6. `fn()` for action spies lives in `storybook/test`, not `@storybook/test` (Storybook 10 moved it).

---

## Session 48 — 5 Track 3 cycles shipped (archived for reference)

> Previous session handoff content preserved below.

---

### Previous Session 48 Header

**Date:** 2026-04-19 (session 48 END)
**HEAD:** `5a726be` (K19a.4)
**Branch:** `main` (ahead of origin by sessions 38–48 commits — user pushes manually)

## Session 48 — 5 Track 3 cycles shipped

```
Track 3 K19a progress (session 48)

Cycle 1  K19a.1-rename           /memory → /knowledge end-to-end     d14d71b
Cycle 2  K19a.1-placeholders     4 Coming-soon tabs                   bab8829
Cycle 3  K19a.2 + K19a.7-skel    13-state TS types + i18n labels     70a3136
Cycle 4  K19a.3                  dispatcher + 13 state subcards      af4cefa
Cycle 5  K19a.4                  hook + BE graph-stats + ProjectRow  5a726be
```

**Final test counts at session 48 end:**
- Frontend (knowledge): **75 pass** (26 projectState + 23 useProjectState + 26 ProjectStateCard)
- Backend (new this session): **6 pass** (test_graph_stats.py)
- Track 2 regression tests: still green per last session 47 runs
- /review-impl caught **1 HIGH + ~15 MED/LOW findings** across the 5 cycles; every code finding fixed in-cycle, 3 LOW documented as known issues (see F4/F7/F8 below)

**User feedback adopted this session:**
- Cycle 3 onwards: batch small related tasks into one workflow cycle (rule saved to memory `feedback_batch_small_tasks.md`)
- FE draft HTML → BE audit at DESIGN phase, reclassify to FS if BE is missing (rule saved to memory `feedback_fe_draft_html_be_check.md`) — K19a.4 validated this: the graph-stats endpoint gap was caught pre-CLARIFY, user picked `(c) add BE now` rather than defer

**Cycle 1 (K19a.1-rename, d14d71b):** pure `/memory` → `/knowledge` rename + nav retranslation (24 files).

**Cycle 2 (K19a.1-placeholders, bab8829):** 4 placeholder tabs added. Navigation shell complete (7 tabs: Projects / Jobs / Global / Entities / Timeline / Raw / Privacy). Each new tab renders "Coming soon" + localized function description.

**Cycle 3 (K19a.2 + K19a.7-skeleton, 70a3136):** **First batched cycle** per user feedback. Foundation types for the 13-state memory-mode UI: `ProjectMemoryState` discriminated union + supporting types (BE-aligned per review-impl F1) + `VALID_TRANSITIONS` map + `canTransition` helper + all state/action i18n keys × 4 locales. 22/22 tests passing including runtime i18n cross-locale checks that neutralize the vitest i18n mock bypass (identified as L2 in cycle 1 review-impl).

**Cycle 4 (K19a.3 full, af4cefa):** `ProjectStateCard` dispatcher + all 13 subcomponents + shared primitives + 26-test component test file. Pure presentational (callback-prop pattern, TS exhaustive switch). `ProjectStateCardActions` union of 14 callbacks. /review-impl caught 7 more findings (3 MED dispatcher/prop drops + 1 MED i18n-coverage regression + 3 LOW polish), all fixed in-cycle. i18n runtime coverage now tracks 48 key paths × 4 locales (192 assertions).

**Cycle 5 (K19a.4 hook + BE graph-stats endpoint, 5a726be):** First FS cycle of Track 3. New `GET /v1/knowledge/projects/{id}/graph-stats` endpoint (Cypher UNION-ALL aggregation, 6 BE unit tests). New `useProjectState(project)` hook: derives `ProjectMemoryState` from `(Project, jobs, stats)`, polls `/extraction/jobs` at 2s while active, wires 11 of 14 callbacks to real endpoints (pause/resume/cancel/retry/extractNew/delete/rebuild/confirmModelChange + 3 that stay toast-stubs pointing to K19a.5 + 4 that stay toast-stubs pointing to K19a.6). `ProjectCard.tsx` deleted, replaced by `ProjectRow.tsx`. /review-impl caught 9 findings (1 **HIGH** — missing `embedding_model` on `/start` + `/rebuild` payloads would 422 at runtime; 2 MED — no error handling, no scopeOfJob tests; 5 LOW + 1 cosmetic). All code findings fixed in-cycle; 3 LOW documented as known issues.

**User feedback captured mid-session:** future small tasks should be batched into single cycles (saved to memory `feedback_batch_small_tasks.md`). Cycle 3 is the first application. Worked well — review-impl caught 9 findings in the batched scope that all got fixed in one pass.

### What K19a.5 can now assume

- `useProjectState(project)` hook returns `{ state, actions, isLoading, error }` — the dialog can import it to trigger estimate → confirm → start. When the Build button eventually opens the dialog, the dialog's Start button REPLACES `actions.onStart` (currently a toast-stub).
- `knowledgeApi.estimateExtraction(projectId, {scope, llm_model, embedding_model}, token)` returns a `CostEstimate`. `knowledgeApi.startExtraction(projectId, {scope, llm_model, embedding_model}, token)` returns an `ExtractionJobWire`. Both are ready to call.
- `EmbeddingModelPicker` (from K12.4) handles embedding-model selection UI; the dialog can reuse it.
- Call `queryClient.invalidateQueries({queryKey: ['knowledge-project-jobs', projectId]})` after starting a job to flip the ProjectStateCard from DisabledCard → BuildingRunningCard on the next poll.

### Known issues deferred from K19a.4 review-impl

- **F4 (polling scale):** 2 queries × N projects. Bounded today by the 100-item pagination cap in ProjectsTab. If pagination is ever removed, consider a `/v1/knowledge/projects/active-jobs` aggregator.
- **F7 (multi-device race):** polling stops for paused/complete/failed states. External state changes on another client aren't auto-refreshed. Future: always-on 30 s low-cadence poll OR SSE.
- **F8 (action-API test gap):** the 11 real-action callbacks have no hook-level tests. `renderHook` + mocked `knowledgeApi` would cover them. Medium lift, future hardening.

### What K19a.5 will replace

- `actions.onStart` stub — becomes the dialog's Start button calling `knowledgeApi.startExtraction`.
- `actions.onBuildGraph` stub — becomes the dialog-opener trigger on DisabledCard.
- `actions.onViewError` stub — becomes the error-viewer modal trigger on Failed/BuildingPausedError cards.

### Retro note — lesson for future FS cycles

Review-impl HIGH F1 (missing `embedding_model` on /start + /rebuild payloads) was a real 422-at-runtime trap that NO test layer could have caught: vitest doesn't hit BE, pytest doesn't hit FE, and Playwright smoke was blocked by BE not running. For FS cycles, review-impl MUST explicitly audit FE payload shape against the BE Pydantic schema — it's the only layer that catches this class of bug.

### FS cycle checklist going forward

1. **At CLARIFY:** enumerate every FE action → BE endpoint pair in a table.
2. **At DESIGN:** read the BE Pydantic request model for each endpoint; confirm every required field has a source in the FE state/props.
3. **At /review-impl:** re-read the Pydantic models; trace every payload construction call site; flag any optional-on-FE / required-on-BE mismatches as HIGH.

## Session 48 — K19a.1-rename (first Track 3 cycle) ✅

Pure `/memory` → `/knowledge` rename + nav retranslation.

**What shipped:**
- URL path + page file + component + i18n namespace all renamed to `knowledge`; hard-cut on `/memory` (old URLs 404)
- 5 product-name-referring locale strings retranslated to Knowledge / ナレッジ / Tri thức / 知識; functional/state-machine references (`staticMemory` badge, `indicator.popover.projectHeading`, `picker.*`, body text) deliberately kept as "Memory" — they describe the AI's memory function, not the product name
- `nav.memory` common-namespace key renamed + retranslated
- `tMemory` local alias renamed to `tKnowledge` in SessionSettingsPanel
- Playwright runtime evidence captured

**What still says "Memory" intentionally:**
- `projects.card.staticMemory` badge — technical state label from the 13-state memory-mode machine; backend `session.memory_mode` contract uses `"static"` / `"degraded"` / `"no_project"`
- `indicator.popover.projectHeading` / `globalHeading` / `body text` / `picker.*` — describe the AI's memory function
- Component names `MemoryIndicator`, `MemoryPage`-turned-history are a concept, not the URL — `MemoryIndicator` component kept; file renamed to `KnowledgePage.tsx`

**Test-coverage gap (important for the NEXT i18n-touching cycle):** the vitest setup at [frontend/vitest.setup.ts:24-41](../../frontend/vitest.setup.ts) globally mocks `react-i18next` such that `useTranslation(anyNamespace)` returns keys verbatim. Unit tests provide **zero** evidence of namespace correctness. Future i18n renames must rely on exhaustive grep (including `<Trans ns=>`, `useTranslation([])` array form, `t('ns:key')` prefix form, `i18n.t`, `getFixedT`) + `tsc --noEmit` + `vite build` + Playwright. Do not over-trust vitest green.

**Review-impl caught & fixed:** M1 (misleading `tMemory` alias post-namespace-rename), M2 (option c was half-shipped — retranslated 5 product labels per locale but kept functional descriptions), L1 (no runtime evidence — added Playwright smoke), L3 (2 stale "Memory page" comments).

---

## (Archived for reference) Session 47 END handoff

> Previous session handoff content preserved below for context.

---

## 1. TL;DR — what shipped this session

**20 commits. Track 2 code-complete.** Session 47 executed the full Track 2 close-out extended plan the user negotiated mid-session. All T2-close-* and T2-polish-* cycles shipped; the only remaining Track 2 item is the Gate 13 human-interactive checkpoint loop (T2-close-2), which can't be automated and is waiting on the user.

```
Track 2 close-out (26 cycles total, sessions 46 + 47)

Session 46  (12 commits, shipped first)
  Cycles 1–6 of the original Track 2 close-out roadmap

Session 47  (20 commits, extended-plan close-out)
  Cycle 7a   P-K18.3-02 MMR embedding cosine              ✅  7c666c9
  Cycle 7b   K18.9 Anthropic prompt cache_control         ✅  8f282c3
  Cycle 8a   D-K18.3-02 generative rerank                 ✅  e5aeb96
  Cycle 8b   D-T2-04 cross-process cache invalidation     ✅  239b021
  Cycle 8c   D-T2-05 glossary breaker half-open probe     ✅  2732462
  Cycle 9    K17.9.1 benchmark-runs migration             ✅  e0a94a7
  test-hygiene one-active-job-per-project fixes            ✅  609de2b
  Gate-13-report doc                                       ✅  95d336e
  T2-close-1a   K17.9 golden-set harness core wiring      ✅  525eaa5
  T2-close-1b-BE   benchmark gate + status endpoint       ✅  849be7f
  T2-close-1b-FE   picker badge + public endpoint         ✅  a484e25
  scope-out docs T2-close-1b-CI + T2-polish-4              ✅  34a4d8f
  T2-close-5   D-K16.2-01 per-model USD pricing           ✅  ed9f13d
  T2-close-6   D-K16.2-02 scope_range.chapter_range       ✅  01b8eda
  T2-close-7   P-K2a-02 + P-K3-02 glossary trigger perf   ✅  02067e2
  T2-close-3   scripted C05/C06/C08 chaos harness         ✅  fae8ce1
  T2-polish-1  test-isolation audit + 2 Go test fixes     ✅  8e3410d
  T2-polish-2a /metrics for glossary-service              ✅  0464919
  T2-polish-2b /metrics for book-service                  ✅  98623aa
  T2-polish-3  D-K18.9-01 cache_control on system_prompt  ✅  ff9ef11
  T2-close-4   Track 2 acceptance pack (doc)              ✅  e694e44
```

**Test execution at session END:**
- knowledge-service unit: **1154 pass** (up from 1049 at session 46 end)
- chat-service unit: **177 pass** (up from 169)
- glossary-service api: **100% green in 3.0 s** (was 2 persistent failures — both stale test bugs fixed in polish-1)
- book-service api: **green + new `parseSortRange` / `buildSortRangeFilter` tests**
- provider-registry-service: green

**Scoped out by user decision (not deferred):**
- T2-close-1b-CI — GitHub Actions benchmark job (no CI/CD at this stage)
- T2-polish-4 — CI integration-test wiring (same reason)

---

## 2. Where to pick up — Track 2 sealing + Track 3 onramp

### Option A — Close Gate 13 (recommended first)

The only code-path-adjacent Track 2 task remaining is **T2-close-2**: the 12-step Gate 13 human-interactive checkpoint walkthrough in [GATE_13_READINESS.md §5](GATE_13_READINESS.md). Requires:

1. BYOK credentials for one LLM provider (Anthropic / OpenAI / LM Studio) + one embedding model (bge-m3 on LM Studio or text-embedding-3-small on OpenAI).
2. A test project with 2–3 real chapters loaded via book-service API.
3. Driving the UI: enable extraction → wait for job → open chat → ask broad / specific / relational queries → inspect chat-service logs for `<memory mode="full">` → send 25+ messages to prove only last 20 in history → ask a contradiction-of-negation question → disable/re-enable extraction → check cost against provider invoice.
4. Optionally run the chaos scripts live for extra confidence: `./scripts/chaos/c0{5,6,8}_*.sh`.

Outcome: append a §10 Gate 13 attestation to [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md) with captured evidence (log excerpts, screenshots, invoice line).

This is the **only** remaining step before Track 2 is formally closed. Code-wise nothing else blocks Track 3.

### Option B — Start Track 3 planning

If the Gate 13 loop is being deferred, Track 3 can start anytime because all Track 2 surfaces are shipped. The Deferred Items table in SESSION_PATCH has a "Track 3 preload" list with specific target phases — open that table and pick the cluster that fits the next session's scope.

Track 3 preload clusters (each has a target phase listed in Deferred Items):
- **D-K16.2-02b** — runner-side `chapter_range` enforcement (dormant today; frontend doesn't send `scope_range` yet).
- **D-K11.9-01 + P-K15.10-01 (partial)** — cursor-state for resumable reconciler + quarantine sweep. Paired with a job-state table. Target: K19/K20 scheduler cleanup.
- **D-K8-02 (remaining)** — project card stat tiles (entity / fact / event / glossary counts). Needs FE wiring on top of already-shipped BE surfaces.
- **D-K17.10-02** — xianxia + Vietnamese K17.10 fixtures.
- **P-K3-01 / P-K3-02 (full path)** — per-row short_description backfill → set-based SQL. Blocked on `shortdesc.Generate` ported to SQL; same port unblocks full P-K3-02.

### Resume recipe (either option)

1. **Read [SESSION_PATCH.md](SESSION_PATCH.md) + [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md)** — the acceptance pack is the single-page view; SESSION_PATCH has everything else.
2. **Check Deferred Items "Naturally-next-phase" table** — any row whose Target equals the phase you're entering is in scope.
3. **Use the workflow gate:** `python scripts/workflow-gate.py reset` then `size <XS|S|M|L|XL> <files> <logic> <effects>` before each cycle; phase-by-phase through RETRO.

---

## 3. What changed in the Deferred Items table this session

### Cleared this session (moved to Recently cleared)

| ID | Cycle | Summary |
|---|---|---|
| **D-K16.2-01** | T2-close-5 | Per-model USD pricing table (`app/pricing.py`) for cost preview — replaces legacy ~$2/M fallback. |
| **D-K16.2-02** | T2-close-6 | `scope_range.chapter_range` threaded through estimate endpoint → `BookClient.count_chapters(from_sort=, to_sort=)` → book-service `parseSortRange` + `buildSortRangeFilter`. |
| **D-K18.3-02** | 8a | Generative listwise rerank on top of MMR, opt-in via `extraction_config["rerank_model"]`, inner timeout 1s, fail-safe fallback. |
| **D-T2-04** | 8b | Cross-process L0/L1 cache invalidation via Redis pub/sub. |
| **D-T2-05** | 8c | Glossary circuit-breaker half-open single-probe guarantee. |
| **D-K18.9-01** | T2-polish-3 | `cache_control` on session `system_prompt` — second Anthropic cache breakpoint used. |
| **K17.9 (harness core + BE gate + FE badge + migration)** | T2-close-1a/1b-BE/1b-FE + Cycle 9 | Golden-set benchmark end-to-end live. `project_embedding_benchmark_runs` table + gate in `/extraction/start` + picker badge + `GET /v1/knowledge/projects/{id}/benchmark-status`. |
| **P-K18.3-02** | 7a | MMR embedding cosine + `top_n` early-exit (21× perf win on dim=3072 pool=40). |
| **K18.9** | 7b | Anthropic prompt caching: structured system content with `cache_control: ephemeral` on stable memory prefix. |
| **P-K2a-02 + P-K3-02 (partial)** | T2-close-7 | Glossary trigger watch-list rewrite; pin toggle 1→0 recalcs, description PATCH 3→1 (no-op) / 2 (real). |
| **Chaos C05/C06/C08 (scripted)** | T2-close-3 | `scripts/chaos/{c05,c06,c08}_*.sh` authored + smoke-tested. |
| **T2-polish-1 test-isolation audit** | T2-polish-1 | Python suite audited clean; 2 pre-existing broken Go tests fixed. |
| **T2-polish-2a /metrics glossary** | T2-polish-2a | 4 counter vecs + 8 call sites pre-seeded; review-impl caught + killed 16 dead labels. |
| **T2-polish-2b /metrics book-service** | T2-polish-2b | 3 counter vecs, cross-service label divergence documented. |
| **T2-close-4 acceptance pack** | T2-close-4 | `TRACK_2_ACCEPTANCE_PACK.md` consolidates Track 2 evidence. |

### Still deferred (explicit Track-3-preload, no re-deferrals this session)

| ID | Target |
|---|---|
| D-K8-02 (remaining stat tiles) | Track 2 Gate 12 or Track 3 |
| D-K11.9-01 (partial, cursor state) | K19/K20 scheduler cleanup |
| P-K15.10-01 (partial, cursor state) | Paired with D-K11.9-01 |
| D-K17.10-02 | K17.10-v2 after threshold stabilisation |
| D-K16.2-02b (runner-side chapter_range) | Track 3 (when FE range-picker ships or batch-iterative runner lands) |
| D-K18.3-02b (if any — none currently) | — |
| P-K3-01 (backfill Go→SQL port) | Track 3 |
| P-K3-02 full path (same port) | Track 3 |

No new deferrals added this session besides **D-K16.2-02b** (review-impl catch during T2-close-6 — runner is event-driven and doesn't honour `chapter_range`; preview filters but runner doesn't, dormant until FE sends `scope_range`).

---

## 4. Important context the next agent must know

### Workflow enforcement unchanged (v2.2 · 12-phase)

```
CLARIFY → DESIGN → REVIEW-DESIGN → PLAN → BUILD → VERIFY → REVIEW-CODE → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

State machine: `.workflow-state.json` + `scripts/workflow-gate.py` from repo root. Pre-commit hook blocks commits without VERIFY + POST-REVIEW + SESSION completed.

**POST-REVIEW is a human checkpoint, NOT self-adversarial re-read.** Deep review is on-demand via `/review-impl`. Every cycle this session had a `/review-impl` pass and several caught HIGH issues the initial self-review missed (examples: T2-close-3 found 3 HIGH blockers in chaos scripts; T2-close-6 found 6 findings including a shared-validator bypass; T2-close-7 found a soft-delete regression from the initial trigger-rewrite).

### Key semantic changes this session

1. **`entity_snapshot.updated_at` semantics changed (T2-close-7).** Pin toggle no longer bumps `updated_at`, and the self-trigger dropped `updated_at` from its watch list. `snapshot.updated_at` now tracks last-**semantic**-change, not last-**touch**. Callers wanting last-touch should read `glossary_entities.updated_at` directly.
2. **`scope_range.chapter_range` is preview-only (T2-close-6).** The estimate endpoint filters; the event-driven extraction runner does not yet honour the range. Dormant today because no frontend sends `scope_range`. Tracked as D-K16.2-02b.
3. **Anthropic 2 of 4 cache breakpoints used (7b + polish-3).** parts[0] = stable memory (cached), parts[1] = volatile memory (uncached, changes per-message), parts[2] = session system_prompt (cached).

### Observability surfaces — all 3 Go services on knowledge-service hot paths

| Service | Endpoint | Counters |
|---|---|---|
| provider-registry | `/metrics` (session 46) | 4 (proxy / invoke / embed / verify) |
| glossary-service | `/metrics` (T2-polish-2a) | 4 (select_for_context / bulk_extract / known_entities / entity_count) |
| book-service | `/metrics` (T2-polish-2b) | 3 (projection / chapters_list / chapter_fetch) |

Outcome label sets differ intentionally between glossary (`invalid_body`) and book (`not_found`). Cross-ref comments in both metrics.go files explain why. Do NOT "normalize" them.

### Chaos scripts — live-run when needed

`scripts/chaos/` contains `lib.sh` + `c05_redis_restart.sh` + `c06_neo4j_drift.sh` + `c08_bulk_cascade.sh` + `README.md`. Each exits `0` on PASS, dies with `FAIL <reason>` on failure, and uses `trap cleanup EXIT` so a failed run still sweeps test data. Test UUIDs prefixed `00000000-0000-0000-c0XX-...` for manual sweep. Prereqs: the `infra-*` compose stack running.

### Benchmark harness is live and gate-active

`python -m eval.run_benchmark --project-id=<uuid> --embedding-model=<model>` runs the K17.9 golden-set harness. A passing row in `project_embedding_benchmark_runs` is now required to start an extraction job — the `POST /extraction/start` endpoint returns 409 with structured `{error_code: benchmark_missing | benchmark_failed, ...}` otherwise. The K12.4 embedding-model picker shows a 3-state badge (green passed / red failed / grey no-run) that drives the CTA.

### Caches + breakers shipped this session (all per-worker-process unless noted)

- `_anchor_cache` TTLCache(256, 60s) — `internal_extraction.py` (session 46).
- `_query_embedding_cache` TTLCache(512, 30s) — `selectors/passages.py` (session 46).
- L0/L1 TTLCache + **cross-process pub/sub invalidation** via `CacheInvalidator` on Redis channel `loreweave:cache-invalidate` (Cycle 8b this session). Settings-gated on `redis_url`.
- Glossary breaker with half-open single-probe guarantee (Cycle 8c this session).

### Pre-existing failing tests (not this session's fault)

- `book-service/internal/config TestLoadValidation` — missing `INTERNAL_SERVICE_TOKEN` env in test setup; the validation requirement was added later. Confirmed via `git stash`.
- `translation-service/tests/test_glossary_client.py` + `test_pipeline_v2.py` — module-import pydantic Settings validation errors (pre-existing before session 46).

### New deps this session

- `github.com/prometheus/client_golang v1.23.2` on **both** glossary-service and book-service (from T2-polish-2a/2b). Session 46 already added it to provider-registry. `go.mod` + `go.sum` committed.

### Infra & test invocation (unchanged)

- Compose: `cd infra && docker compose up -d`; Neo4j profile: `docker compose --profile neo4j up -d neo4j`.
- Neo4j port: **7688**, Postgres port: **5555**, Neo4j creds `neo4j / loreweave_dev_neo4j` (note the `_neo4j` suffix — chaos scripts default to this).
- pytest from `services/knowledge-service/` (unit: `-q tests/unit/`; integration needs `TEST_KNOWLEDGE_DB_URL` + `TEST_NEO4J_URI`).
- Go tests from `services/<svc>/` (`go test ./...`); glossary-service integration needs `GLOSSARY_TEST_DB_URL`.

---

## 5. Session 47 stats

| Metric | Before session 47 | After session 47 | Delta |
|---|---|---|---|
| Total knowledge-service unit tests | 1049 | **1154** | **+105** |
| chat-service unit tests | 169 | **177** | **+8** |
| glossary-service api test status | 2 failing (stale) | **100% green** | 2 fixed |
| book-service api test status | green | **green + new tests** | new units |
| Deferred items open | ~6 naturally-next + 4 re-deferred + 2 partial | **~6 naturally-next / partial only (no re-deferrals)** | ~4 cleared |
| Cycles complete (original Track 2 roadmap) | 6/9 | **9/9** | +3 |
| T2-close extended plan cycles | 0 | **9/9** (1 scoped out) | +9 |
| T2-polish extended plan cycles | 0 | **4/4** (1 scoped out) | +4 |
| Session commits | 0 | **20** | +20 |
| Review-impl follow-up catches | — | ~20 HIGH/MED/LOW findings across cycles | — |
| New deps | — | `prometheus/client_golang v1.23.2` on glossary + book | +1 dep × 2 services |
| New env knobs | — | — | stable |
| Services with /metrics | 1 (provider-registry) | **3** (+ glossary + book) | +2 |
| Chaos scripts (scripted live runs) | 0 | **3** (C05/C06/C08) | +3 |

---

## 6. Housekeeping note

This file is the single, unversioned handoff. **Future sessions MUST update this file in place — do NOT create a `_V48.md` or similar.**

Track 2 is **code-complete**. The repo is in a clean state to either (a) execute the Gate 13 human loop to formally seal Track 2, or (b) begin Track 3 planning — neither blocks the other. All deferrals have explicit target phases; no "we'll come back to it" rows remain.

When the Gate 13 human loop is run, append §10 attestation to [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md) with the captured evidence, and move the T2-close-2 row out of "remaining" in SESSION_PATCH's header metadata.
