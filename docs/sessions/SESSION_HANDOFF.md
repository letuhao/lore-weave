# Session Handoff — Session 47 (Cycle 7a shipped, 7b pending)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-19 (session 47 mid-flight — Cycle 7a committed, 7b next)
> **HEAD (pre-session-47):** `9aa9910` (Cycle 6 review-impl fixes); session 47 commit hash pending
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

## 2. Where to pick up — Cycle 7b (K18.9 prompt caching)

```
Cycle 1 — 1a + 1b                        ✅
Cycle 2 — debris sweep                    ✅
Cycle 3 — lifecycle + scheduler           ✅ (3/5 + 2/5 partial)
Cycle 4 — provider-registry               ✅ (2/3)
Cycle 5 — extraction quality + perf       ✅ (4/4)
Cycle 6 — RAG quality (6a/6b/6c)          ✅ (3/3)
Cycle 7 — K18 final polish (split 7a/7b)
  ├─ 7a  P-K18.3-02 MMR embedding cosine  ✅ (session 47, +top_n early-exit via review-impl)
  └─ 7b  K18.9 prompt caching hints        ← NEXT
Cycle 8 — large infra (3 commits)         ← after Cycle 7
  ├─ D-K18.3-02  generative rerank (LM Studio)
  ├─ D-T2-04  cross-process cache invalidation
  └─ D-T2-05  glossary breaker probe half-open guarantee
Cycle 9 — Gate-4 alignment                 ← final before Gate 13
  └─ K17.9.1 migration items
Gate 13 E2E + Chaos tests C01–C08          ← after all cycles
```

### Resume recipe

1. **Read [SESSION_PATCH.md §Track 2 Close-out Roadmap](SESSION_PATCH.md#track-2-close-out-roadmap-session-46)** — especially the Cycle 7b / 8 / 9 rows for scope.
2. **Check the Deferred Items "Naturally-next-phase" table** — any item with Target phase "Cycle 7 / 8 / 9" is in scope now. The re-deferred items from Cycles 2 & 4 (D-K17.10-02, D-K16.2-01, D-K16.2-02, P-K2a-02, P-K3-01, P-K3-02) are **out of scope** for Track 2 close-out and stay deferred.
3. **Cycle 7b (K18.9) is L-sized** — originally bundled with 7a as "single commit" but CLARIFY counted ~9-10 files (mode builders × 3 + schema + 2 chat-service files + tests). Split into its own commit.
4. **Cycle 8 is 3 commits** — one per sub-item because each changes observable behavior that should be reviewable independently.
5. **Use the workflow gate:** `python scripts/workflow-gate.py reset && python scripts/workflow-gate.py size <XS|S|M|L|XL> <files> <logic> <effects>` before starting each cycle, phase per phase through to RETRO.

### Things that are good to know before Cycle 7b

- **K18.9 prompt caching** references Anthropic's `cache_control` markers on message turns. The idea is to mark stable memory-block segments (L0, project instructions, L1 summary, glossary) as cacheable so subsequent turns in the same session can skip re-tokenizing them. Chat-service opts in; no contract break for non-caching providers.
- **Boundary split:** Mode 3 memory block's stable prefix is `<user>` + `<project>` (instructions + summary) + `<glossary>`. Volatile starts at `<facts>` (intent-driven). Mode 2 has the same boundary minus facts. Mode 1 is entirely stable.
- **Contract surface:** knowledge-service's `BuiltContext`/`ContextBuildResponse` needs a new field — either `stable_context_len: int` (byte offset) or split `stable_context`/`volatile_context`. Latter is cleaner; the whole-context backward-compat field can stay alongside.
- **chat-service path:** detect `creds.provider_kind == "anthropic"` in `stream_service.py`, emit structured system content `[{"type":"text","text":stable,"cache_control":{"type":"ephemeral"}}, {"type":"text","text":volatile}]`. Non-Anthropic concatenates as today.

### What 7a shipped (session 47, HEAD to be updated)

- `PassageSearchHit.vector: list[float] | None = None` — transient per-search field, NOT on `Passage`.
- `find_passages_by_vector(..., include_vectors: bool = False)` — opt-in vector projection via f-string-substituted `node.embedding_{dim} AS vector` (injection-safe, closed-set validation).
- L3 selector passes `include_vectors=True`; `_mmr_rerank` per-pair cosine (when both have vectors) / Jaccard (fallback) with precomputed L2 norms keyed by `id(hit)`.
- **Review-impl caught MED perf issue:** `_mmr_rerank` ranked the full pool (40) when the caller only consumed `[:top_n]`. Added `top_n` kwarg + early-exit. Benchmark: pool=40 dim=3072 full = 1196 ms, top_n=10 = 57 ms (21× win). Test proves both capped and uncapped paths.
- +5 unit tests, +2 integration tests. 1273 passed + 95 skipped (live Neo4j).
- Fixed 3 stale docstrings uncovered during review (Passage class, MMR inline comment, module "ingestion deferred" note).

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
