# Session Handoff — Session 47 END (extended: K17.9 harness wiring; T2-close-1b next)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-19 (session 47 END — extended)
> **HEAD:** `95d336e` (Gate 13 readiness doc); session 47 T2-close-1a commit hash pending
> **Branch:** `main` (ahead of origin by sessions 38–47 commits — user pushes manually)

---

## 1. TL;DR — what shipped this session

Session 46 was a large close-out session. 12 commits landed 6 of 9 planned Track 2 close-out cycles. Key artifacts:

```
Track 2 close-out roadmap (session 46)   ✅  9 cycles defined, 6 shipped
  Cycle 1a  D-K18.3-01 passage ingestion  ✅  Mode 3 end-to-end LIVE with real data
  Cycle 1b  K12.4 FE embedding picker     ✅  users can configure embedding_model via UI
  Cycle 2   Debris sweep                  ✅  3/7 shipped (5 honest re-deferred)
  Cycle 3   Lifecycle + scheduler         ✅  3/5 full + 2/5 LIMIT-half (cursor deferred)
  Cycle 4   Provider-registry hardening   ✅  2/3 (D-K16.2-01 re-deferred)
  Cycle 5   Extraction quality + perf     ✅  4/4
  Cycle 6   RAG quality (3 sub-cycles)    ✅  3/3
  Cycle 7   K18 final polish              ⏳  NEXT
  Cycle 8   Large infra (3 commits)       ⏳
  Cycle 9   Gate-4 alignment              ⏳
```

**Test execution at session end:**
- knowledge-service unit: **1049/1049 pass** (up from 1026 at start of session)
- chat-service unit: **169/169 pass** (stable)
- glossary-service: `go build ./...` clean, `go test ./...` passes
- provider-registry-service: `go build ./...` clean, `go test ./...` passes

**Deferred-items drift reconciliation (commit `6727c2d`):** 6 items that shipped in cycles 1–3 were still listed as open in the Deferred Items table (only Cycle 4's 2 items had been struck through). Audited + reconciled — 6 struck, 2 amended to "partial" (LIMIT shipped, cursor deferred).

---

## 2. Where to pick up — Track 2 close-out extended plan (post-roadmap cycles)

```
Cycles 1–9 (original close-out roadmap)   ✅ (sessions 46 + 47)

Extended plan (negotiated session 47 — all deferrals either in-scope
or genuinely Track-3-preloaded; no more re-deferrals mid-cycle):

T2-close-1a  K17.9 harness core wiring   ✅ (session 47, pending commit)
T2-close-1b  K17.9 CI + FE gate hook      ← NEXT
T2-close-5   D-K16.2-01 model pricing
T2-close-6   D-K16.2-02 scope_range filter
T2-close-7   P-K* glossary trigger perf pass (P-K2a-02 + P-K3-01 + P-K3-02)
T2-close-3   Chaos C05 / C06 / C08 live runs
T2-polish-1  Test-isolation audit (find siblings of the 3 we fixed)
T2-polish-2a Metrics endpoint on glossary-service
T2-polish-2b Metrics endpoint on book-service
T2-polish-3  D-K18.9-01 system_prompt cache_control (fold into 2a or 2b)
T2-polish-4  CI integration-test wiring (TEST_KNOWLEDGE_DB_URL / TEST_NEO4J_URI)
T2-close-2   Gate 13 human-loop walk-through (needs BYOK + real chapters)
T2-close-4   Track 2 acceptance pack (doc)
preload      Add Track-3-preloaded section to SESSION_PATCH.md
```

### Resume recipe

1. **Read [SESSION_PATCH.md §Track 2 Close-out Roadmap](SESSION_PATCH.md#track-2-close-out-roadmap-session-46)** — especially the Cycle 8 / 9 rows for scope.
2. **Check the Deferred Items "Naturally-next-phase" table** — any item with Target phase "Cycle 8 / 9" is in scope now. Re-deferred items from earlier cycles (D-K17.10-02, D-K16.2-01, D-K16.2-02, P-K2a-02, P-K3-01, P-K3-02, D-K18.9-01) are **out of scope** for Track 2 close-out and stay deferred.
3. **Cycle 8 is 3 separate commits** — one per sub-item because each changes observable behavior that should be reviewable independently.
4. **Use the workflow gate:** `python scripts/workflow-gate.py reset && python scripts/workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <effects>` before starting each cycle, phase per phase through to RETRO.

### Things that are good to know before T2-close-1b

- **T2-close-1a shipped the K17.9 harness core (this session)**: `eval/fixture_loader.py`, `eval/mode3_query_runner.py`, `eval/persist.py`, CLI on `eval/run_benchmark.py`. Unit + integration tests pass. Live-run against a real BYOK model is a documented README step.
- **T2-close-1b wires the harness into CI + FE**: new GitHub-Actions workflow (or extension) that runs `python -m eval.run_benchmark` against a test LM Studio model on every PR, AND a K12.4 picker hook that calls the knowledge-service project-benchmark-status endpoint and blocks extraction-enable when the latest benchmark `passed=false`. New internal endpoint likely needed: `GET /internal/projects/{id}/benchmark-status` returning the latest row from `project_embedding_benchmark_runs`.
- **CLI live-run command** (for reference / README):
  ```bash
  python -m eval.run_benchmark \
    --user-id=<uuid> \
    --project-id=<uuid> \
    --embedding-model=bge-m3 \
    --runs=3
  ```
  Needs `KNOWLEDGE_DB_URL`, `INTERNAL_SERVICE_TOKEN`, `NEO4J_URI` env vars set. Exits 0 on pass, 1 on fail, 2 on unknown model.

### The extended plan's invariant

Every remaining deferral is now either **in-scope for a T2-close cycle** or **explicitly Track-3-preloaded**. No more "fix when profiling shows pain" / "wait for upstream dep" re-deferrals — each one has a concrete owner cycle.

### Lessons carried forward (session 47)

- **Don't re-import a "real" function after monkeypatch**. When a test helper `_patch_mode3_pieces` patches `foo` to an AsyncMock, a later `from pkg import foo as real_foo` binds `real_foo` to the AsyncMock, not the original. Capture the real reference at module load time (before any test runs) — see `_REAL_SELECT_L3_PASSAGES` in test_mode_full.py.
- **Opt-in features still need inner timeouts**. Cycle 8a's rerank, if slow, was consuming the whole L3 budget and returning zero passages — strictly worse than not opting in. Always clamp sub-feature budgets so enabling an opt-in never regresses below the opt-out baseline.

### What Cycle 7 shipped (session 47)

**7a P-K18.3-02** (HEAD `7c666c9`):
- `PassageSearchHit.vector: list[float] | None = None` — transient per-search field, NOT on `Passage`.
- `find_passages_by_vector(..., include_vectors: bool = False)` — opt-in vector projection via f-string-substituted `node.embedding_{dim} AS vector` (injection-safe, closed-set validation).
- L3 selector passes `include_vectors=True`; `_mmr_rerank` per-pair cosine (when both have vectors) / Jaccard (fallback) with precomputed L2 norms keyed by `id(hit)`.
- **Review-impl caught MED perf issue:** `_mmr_rerank` ranked the full pool (40) when the caller only consumed `[:top_n]`. Added `top_n` kwarg + early-exit. Benchmark: pool=40 dim=3072 full = 1196 ms, top_n=10 = 57 ms (21× win). Test proves both capped and uncapped paths.
- +5 unit tests, +2 integration tests.
- Fixed 3 stale docstrings.

**T2-close-1a K17.9 harness core** (about to land): Real-wiring pass on the scaffold from session 45 — the `[~]` in the plan row said "scaffold done, real wiring pending K17.2+K18.3"; both have shipped. New `eval/fixture_loader.py` embeds `f"{name}. {summary}"` per golden-set entity (review-impl HIGH catch — summary-only indexing would have failed easy-band queries like "Who is Kaelen Voss?") + upserts as `source_type='benchmark_entity'` tagged `:Passage`. New `eval/mode3_query_runner.py` is the live `AsyncQueryRunner`: embed query → `find_passages_by_vector` → map `source_id` → entity_id. New `eval/persist.py` writes the report to `project_embedding_benchmark_runs` (Cycle 9's table). `eval/run_benchmark.py` gains `AsyncBenchmarkRunner` + CLI `_main()`. 13 new unit tests + 5 new integration tests. 1438 pass + 1 skip.

**9 K17.9.1** (HEAD `e0a94a7`): `project_embedding_benchmark_runs` migration — one new table appended to `app/db/migrate.py` (inline-DDL convention, not a separate `.sql` file per the plan-row's stale guidance). Stores K17.9 golden-set harness output keyed on `(project_id, embedding_model, run_id)` UNIQUE; `ON DELETE CASCADE` on project; covering index `(project_id, embedding_model, created_at DESC)` serves both latest-per-project and latest-per-project-per-model queries; `passed BOOLEAN NOT NULL` is the extraction-enable gate bit; `embedding_provider_id` is cross-DB (no FK, same rule as `user_id`/`book_id`). Review-impl added a full-column INSERT test and a cascade-preserves-other-projects test. +7 unit DDL smoke tests + 7 integration tests. 1319 unit pass + 20 migration integration pass with live Postgres.

**8c D-T2-05** (HEAD `2732462`): Glossary circuit-breaker half-open single-probe guarantee. New `_cb_probe_in_flight` bool + `_cb_enter()` state machine returning `"closed"|"probe"|"open"`. Concurrent callers in the half-open window are serialized by the asyncio event loop — exactly one claims the probe (no await between check and set → atomic), the rest short-circuit. `select_for_context` wraps the HTTP retry loop in `try`/`finally` so the probe slot releases under every outcome. Validation: concurrent 5-caller test fires 1 HTTP call instead of 5. Before this fix, all concurrent callers at the cooldown-elapsed moment fired simultaneous probes, undoing the breaker's backpressure under load. +3 tests.

**8b D-T2-04** (HEAD `239b021`): Cross-process L0/L1 cache invalidation via Redis pub/sub. New `app/context/cache_invalidation.py` holds a `CacheInvalidator` (publisher + subscriber on `loreweave:cache-invalidate` channel); per-process UUID origin filters self-messages; exponential-backoff reconnect (1 s → 10 s). `cache.py`'s `invalidate_l0 / invalidate_l1 / invalidate_all_for_user` fire-and-forget publish after the local pop; a `_pending_publishes` set holds task refs so Python doesn't GC them mid-send. `stop()` drains the set before closing Redis. New `apply_remote_l0 / l1 / user` helpers do the local pop WITHOUT re-publishing (prevents echo storm). Settings-gated: empty `redis_url` → invalidator never installs → Track 1 single-worker path unchanged. Review-impl caught check-then-use race on `_invalidator` (local-capture fix), weak idempotence test (added `from_url.call_count == 1`), missing end-to-end chain test (added one). +17 tests.

**8a D-K18.3-02** (HEAD `e5aeb96`): Post-MMR listwise generative rerank via `provider_client.chat_completion` with `{"order":[int,...]}` JSON mode. Opt-in via `project.extraction_config["rerank_model"]` (no DB migration). `rerank_passages()` in `selectors/passages.py` handles prompt construction (200-char passage snippets), forgiving parse (filter out-of-range / duplicate / bool; append missing indices at tail), and fail-safe fallback to MMR order on any error. Inner `asyncio.wait_for(timeout=1.0s)` prevents slow rerank from eating the 2s L3 budget. Wiring: `provider_client` plumbed through `deps.py::get_provider_client` → router → `build_context` → `build_full_mode` → `_safe_l3_passages` → `select_l3_passages`. Review-impl caught the timeout issue + added end-to-end test proving `extraction_config["rerank_model"]` reaches `chat_completion.model_ref`. +11 tests.

**7b K18.9** (HEAD `8f282c3`):
- `BuiltContext` / `ContextBuildResponse` / `KnowledgeContext` gained `stable_context` + `volatile_context` (defaults `""`).
- New `split_at_boundary(lines, n)` helper; explicit boundary newline so `context == stable + volatile` byte-for-byte.
- Boundary: Mode 1 = whole block stable; Mode 2/3 stable ends at `</project>`.
- `_enforce_budget` threaded 3-tuple (stable, volatile, context) through every trim pass — stable prefix survives each re-render unchanged.
- chat-service `stream_service.py`: detects `creds.provider_kind == "anthropic"` + non-empty stable, emits `[{stable, cache_control: ephemeral}, {volatile}, {system_prompt}]`. Non-anthropic + empty-split keep existing concat path. LiteLLM's Anthropic adapter passes cache_control through unchanged.
- Review-impl added `test_anthropic_includes_system_prompt_as_third_segment` (third-segment ordering + cache_control only on parts[0]) and strengthened budget-trim test to prove trim fired.
- +6 knowledge-service tests, +7 chat-service tests.

### New knobs / fields / contracts (Cycle 7)

- `include_vectors: bool = False` kwarg on `find_passages_by_vector` — opt-in. Only the L3 selector sets it.
- `PassageSearchHit.vector: list[float] | None = None` — populated only with include_vectors=True.
- `BuiltContext.stable_context`, `BuiltContext.volatile_context` — invariant `context == stable + volatile`.
- `ContextBuildResponse.stable_context`, `.volatile_context` — same pair exposed over the wire.
- `KnowledgeContext.stable_context`, `.volatile_context` — defaults `""` for older-server compat.
- chat-service now emits Anthropic structured system content for `provider_kind == "anthropic"` — the rest unchanged.

### Deferred added this cycle

- **D-K18.9-01**: system_prompt cache_control on anthropic path. Second `cache_control: ephemeral` marker on session-level persona. ~3 lines. Defer until a real long-persona user surfaces.

---

## 3. What changed in the Deferred Items table this session

### Cleared this session (moved to Recently cleared)

| ID | Cycle | What was done |
|---|---|---|
| **D-K18.3-01** | 1a | Passage ingestion pipeline — K14 consumer + chunker + embedder + upsert. Mode 3 now returns real passages. |
| **K12.4** | 1b | FE embedding-model picker on project edit; auto-derives `embedding_dimension`. |
| **D-PROXY-01** | 2 | Empty-credential guard across 6 provider-registry sites. |
| **D-K17.2c-01** | 2 | Router-layer tests for K17.2c. |
| **P-K2a-01** | 2 | Glossary BackfillSnapshots → single set-based query (~100× faster). |
| **D-K11.3-01** | 3 | Lifespan startup try/except + reverse-order cleanup. |
| **D-K11.9-02** | 3 | Orphan `:ExtractionSource` sweep. |
| **D-K17.2a-01** | 4 | Prometheus /metrics on provider-registry, 4 counter vecs × 12 outcomes, 75 call sites. |
| **D-K17.2b-01** | 4 | `tool_calls` parser support (content=null + tool_calls[] accepted). |
| **D-K15.5-01** | 5 | All-caps fusion fix + multi-whitespace robust tokenization (added in review-impl). |
| **P-K15.8-01** | 5 | Pre-built sentence_candidates map shared across triple + negation extractors. |
| **P-K13.0-01** | 5 | Anchor pre-load TTLCache(256, 60s). |
| **P-K18.3-01** | 5 | Query embedding TTLCache(512, 30s) keyed by user_uuid too (review-impl). |
| **D-T2-01** | 6a | tiktoken.cl100k_base swap for CJK accuracy (with len/4 fallback). |
| **D-T2-02** | 6b | glossary FTS → `ts_rank_cd` with flag 33 (log-length + [0,1] scaling). |
| **D-T2-03** | 6c | `recent_message_count` unified behind env var `RECENT_MESSAGE_COUNT`. |

### Re-deferred this session (still in Deferred Items)

| ID | Reason |
|---|---|
| D-K16.2-01 | Needs `pricing_policy` JSONB schema design first — not a one-liner. |
| D-K16.2-02 | Blocked on book-service chapters range-filter support. |
| D-K17.10-02 | Needs user-provided xianxia + Vietnamese chapter data. |
| P-K2a-02 | Trigger redesign (pin-toggle snapshot), cross-cutting glossary perf pass. |
| P-K3-01, P-K3-02 | Trigger chain redesign, same glossary perf pass. |

### Still open partial (LIMIT shipped, cursor-state still open)

| ID | Status |
|---|---|
| D-K11.9-01 | Reconciler LIMIT-batching done; cursor-state (resumable from mid-scan) needs job-state table — targeted at K19/K20 scheduler cleanup. |
| P-K15.10-01 | Quarantine sweep LIMIT done; cursor-state same situation. |

---

## 4. Important context the next agent must know

### Workflow enforcement unchanged (v2.2 · 12-phase)

```
CLARIFY → DESIGN → REVIEW-DESIGN → PLAN → BUILD → VERIFY → REVIEW-CODE → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

- State machine: `.workflow-state.json` + `scripts/workflow-gate.py` (run from repo root).
- Pre-commit hook blocks commits without VERIFY + POST-REVIEW + SESSION completed.
- **POST-REVIEW is a human checkpoint, NOT a self-adversarial re-read.** Deep review is on-demand via `/review-impl`. Session 46 proved this again: every cycle had a `/review-impl` pass that caught real issues (Cycle 2 missed the 6th D-PROXY-01 site, Cycle 3 had an invalid Cypher `LIMIT CASE`, Cycle 4 had 62 missing counter sites, Cycle 5 embed cache missed user_uuid, Cycle 5 had a multi-whitespace tokenizer gap, Cycle 6 had docstring staleness).

### Review-impl pattern worth keeping

Every cycle this session ended with a second-pass review-impl pass — several found HIGH issues the initial self-review missed. The pattern was:
1. Commit cycle.
2. User asks "let's review implement issues" → I re-read the diff adversarially.
3. Real issues surface → separate follow-up commit.

Do this for Cycles 7–9 too. It's not ceremony; it's finding real bugs before they escape.

### Caches shipped this session (both per-worker-process)

- `knowledge-service/app/routers/internal_extraction.py` — anchor pre-load TTLCache(256, 60s). Key `(user_id, project_id)`. Exceptions NOT cached.
- `knowledge-service/app/context/selectors/passages.py` — query embedding TTLCache(512, 30s). Key `(user_uuid, project_id, embedding_model, message)`. Empty/failure NOT cached.
- Both in `cachetools.TTLCache`. No manual invalidation — short TTL handles drift.

### Cross-service env knobs introduced this session

- `RECENT_MESSAGE_COUNT` (default 50) — read by both `knowledge-service/Settings.recent_message_count` and `chat-service/Settings.recent_message_count`. Mode 3 keeps its own tighter 20 independent of this knob.

### New deps added

- `tiktoken>=0.7` — added to `services/knowledge-service/requirements.txt`. Cycle 6a. Falls back to `len/4` if import fails (air-gapped installs).

### Pre-existing failing tests to ignore

- `translation-service/tests/test_glossary_client.py` + `test_pipeline_v2.py` — pydantic Settings validation errors at module-import time (missing `RABBITMQ_URL`, `INTERNAL_SERVICE_TOKEN`, `JWT_SECRET`, `DATABASE_URL`). Pre-existing before Cycle 6a — confirmed via `git stash` during session 46. Not caused by any cycle work.

### Mode 3 is now end-to-end live

Before session 46, Mode 3 (full context mode with L3 passages) had the selector code but no passage data — all retrievals returned `[]`. After Cycle 1a (D-K18.3-01), the K14 event consumer ingests chapter.saved events through chunker → embedder → upsert. After Cycle 1b (K12.4), users can configure which embedding model from the UI. A brand-new project with an embedding model set now sees passages populate as chapters are saved.

### Counter coverage expanded in provider-registry (Cycle 4)

- `/metrics` route now live; unauthed, in-cluster scrapers only.
- Counter series: `provider_registry_proxy_requests_total`, `..._invoke_requests_total`, `..._embed_requests_total`, `..._verify_requests_total`. Each labelled on `outcome`.
- 12 outcome constants. All 48 combos pre-seeded so dashboards can `rate()` from first scrape.
- 75 call sites across 5 handlers. Don't use this as a template without understanding the initial version shipped with only 13 sites — review-impl caught missing success paths + most error paths. Every `return` in a handler should count SOMETHING.

### tiktoken swap behavior

`estimate_tokens("一位神秘的刀客的故事")` returns **14** now (was 2 under `len/4`). Any Mode-2/Mode-3 context budget that was implicitly over-promising for CJK users is now accurate. If any test fixture hardcodes expected token counts from the old heuristic, it needs to be recomputed — we did this for 4 test files already (`test_token_counter.py`, `test_no_project_mode.py`, `test_static_mode.py`, `test_public_summaries.py`). Integration tests in `tests/integration/db/test_context_build.py` still hardcode `50` for `recent_message_count` and that's the one we didn't convert; if you touch that file for other reasons, prefer `settings.recent_message_count` to stay in sync.

### Infra & test invocation (unchanged)

- Compose: `cd infra && docker compose up -d`; Neo4j profile: `docker compose --profile neo4j up -d neo4j`
- Neo4j port: **7688**, Postgres port: **5555**
- pytest from `services/knowledge-service/`. Quality eval is opt-in: `pytest tests/quality/ --run-quality`.

### Multi-tenant safety rail (unchanged)

- `entity_canonical_id` scopes by `user_id` + `project_id`. `project_id=None` → `"global"` in the hash key.

---

## 5. Session 46 stats

| Metric | Before session 46 | After session 46 | Delta |
|---|---|---|---|
| Total knowledge-service unit tests | 1026 | **1049** | **+23** |
| chat-service unit tests | 169 | **169** | stable |
| Deferred items open | ~24 | ~6 naturally-next-phase + 4 re-deferred + 2 partial + 5 won't-fix | **−16 cleared** |
| Cycles complete (of 9) | 0 | **6** | +6 |
| Session commits | 0 | **12** | +12 |
| Review-impl follow-up commits | 0 | **2** (Cycle 5, Cycle 6) | +2 |
| New deps | — | `tiktoken>=0.7` (knowledge-service) | +1 |
| New env knobs | — | `RECENT_MESSAGE_COUNT` | +1 |

---

## 6. Housekeeping note

This file is the single, unversioned handoff. **Future sessions MUST update this file in place — do NOT create a `_V47.md` or similar.**

Track 2 close-out is ~67% done. Cycles 7–9 + Gate 13 + Chaos tests are the remaining scope before Track 2 is closed and we can pick up Track 3 (or resume hobby-project features).
