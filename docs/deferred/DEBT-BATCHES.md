# Debt-Clearing Batches — `feat/auto-draft-factory-gaps`

**Created:** 2026-06-16 · **Source:** full-branch sweep of `docs/sessions/SESSION_HANDOFF.md` (open deferrals) + production-code debt markers (`services/*/app|internal|src`, `frontend/src`, `sdks`). Items already `✅/CLEARED` are excluded.

**Purpose:** turn the scattered deferral backlog into **coherent long-run batches**, each drivable as one continuous `/loom <batch>` flow. Batches are sequenced top-down by priority. A separate **Park bucket** lists items that are *not* debt to clear (R&D / perf-when-pain / HA-scale / wontfix) — do NOT spend long-runs there.

**Legend:** severity `high|med|low` · type `correctness|telemetry|feature-gap|live-smoke|perf|cleanup` · source `[H]`=handoff `[C]`=code.

**How to use:** pick the top open batch → `/loom <batch goal>` → clear its items → tick them here in the same commit. Live-smoke batches: rebuild touched images first (stale = false-green), bring the relevant stack up once, run all smokes in the batch.

---

## Sequencing overview

| # | Batch | Type | ~Items | Size | Status |
|---|---|---|---:|---|---|
| **B0** | Correctness sweep (cross-service, small + high-value) | correctness | 7 | M | ☐ |
| **B1** | Jobs GUI telemetry completeness (P4) | telemetry | 9 | L | ☐ |
| **B2** | Jobs control completeness (P3) | feature-gap | 3 | M | ☐ |
| **B3** | Live-smoke sweep — Job Control Plane + P5 | live-smoke | 4 | M | ☐ |
| **B4a** | Live-smoke sweep — Auto-Draft Factory (S1–S6) | live-smoke | ~17 | L | ☐ |
| **B4b** | Auto-Draft Factory functional/correctness gaps | feature/correctness | ~10 | L | ☐ |
| **B5** | Live-smoke sweep — Wiki + Glossary + E0 | live-smoke | ~9 | L | ☐ |
| **B6** | Translation V3 functional gaps | feature/correctness | ~13 | L | ☐ |
| **B7** | Knowledge Projects FE (K19) — mobile + filters + polish | feature-gap (FE) | ~20 | L | ☐ |
| **B8** | Search/Rawsearch + cosmetic cleanup + misc code gaps | mixed/low | ~18 | M | ☐ |

Recommended order: **B0 → B1 → B2 → B3** (Job Control Plane warm + de-risk money-path), then **B4a/B5** (live-smoke confidence sweeps), then **B4b → B6 → B7 → B8**.

---

## B0 — Correctness sweep
Small, well-defined fixes that reduce latent risk. Cross-service but each is independent.

| ID / location | Description | sev | src |
|---|---|---|---|
| `D-JOBS-EMIT-STATUS-PASSTHROUGH-ROLLBACK` | campaign/knowledge/translation pass unknown native status verbatim → `JobStatus()` raises in-tx → rolls back a legit transition. Switch to map-or-skip (return None). | high | [H] |
| `provider-registry server.go:2712` | validate `providerModelName` is embedding-capable before dispatch (TODO) | high | [C] |
| `D-S5B-EMBED-CREATE-ATOMICITY` | project embedding patch must precede campaign insert (ordering) | med | [H] |
| `D-TRANSL-VERSION-NUM-RACE` | platform-wide `version_num` collision fix | med | [H] |
| `D-REDIS8-CONSUMERS` | port the `TimeoutError` catch + pin redis across remaining consumers | med | [H] |
| `D-S4A-MIGRATION-ORDERING` | ensure knowledge migration runs before worker-ai starts | low | [H] |
| `worker-infra outbox_relay.go:108` | confirm the quiet-retry on a not-yet-created `outbox_events` table is intended (video-gen flag-gated) or guard it | med | [C] |

---

## B1 — Jobs GUI telemetry completeness (P4)
Make the unified jobs dashboard show complete cost/model/tokens for **every** kind + wire retry. All in the jobs-projection emit path.

| ID | Description | sev |
|---|---|---|
| `D-JOBS-P4-TRANSLATION-COST` | translation has no job-level cost column → cost shows `—` | med |
| `D-JOBS-P4-LORE-MODEL` | lore-enrichment model NAME not emitted (ref in separate `enrichment_job_request`) | med |
| `D-JOBS-P4-CAMPAIGN-MODEL-NAMES` | per-stage campaign model names not emitted (HTTP-in-tx concern) | med |
| `D-JOBS-P4-COMPOSITION-GUARDED-MODEL` | guarded auto-draft path emits `model=None`+ref-in-params | low |
| `D-JOBS-CAMPAIGN-SPEND-EMIT` | campaign cost updates only on status transition, not per SpendConsumer write | low |
| `D-JOBS-P4-SUMMARY-TOPLEVEL` | active count is top-level-only → completed parent w/ running child undercounts | low |
| `D-JOBS-P4-TRANSL-TOKENS-PG` | translation tokens-SUM SQL only FakeConn-tested → add real-PG coverage | low |
| `D-JOBS-P4-RETRY` | failed-job "Retry" — BE retry action + FE button (mockup shows it) | med |
| `D-JOBS-P4-OVERLAY-EVICT` | SSE overlay Map never evicts terminal jobs (slow growth) | low |

---

## B2 — Jobs control completeness (P3)
Finish the control surface gaps.

| ID | Description | sev |
|---|---|---|
| `D-JOBS-P3-TRANSLATION-PAUSE` | translation stop-dispatch pause/resume + re-add to `_MULTI_UNIT_KINDS` (`jobs-service contract.py:29`) | med |
| `D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT` | video-gen cancel doesn't abort the in-flight provider job (reclaim slot/cost) | med |
| `D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL` | one-shot `enrichment_compose_task` not control-wired | low |

---

## B3 — Live-smoke sweep — Job Control Plane + P5
Stack up with `P5_SCHED_ENABLED=true`, seed one extraction-ready project. Run all in one session.

| ID | Description | sev |
|---|---|---|
| `D-P5-M3-EXTRACTION-LIVE-SMOKE` | decoupled extraction with P5 on; assert `p5:knowledge:extraction:inflight:{user}` ZCARD ≤ cap | high |
| `D-P5-M2-MULTI-OWNER-LIVE-SMOKE` | 2-user interleave on the stack (single-owner cap-hold already proven) | med |
| `D-JOBS-P2-SSE-LIVE-SMOKE` | real consumer-upsert → pub/sub → connected-client push | med |
| `D-JOBS-P3-KNOWLEDGE-CANCEL-SUCCESS-LIVE-SMOKE` | a successful cancel mutating a real running extraction row | med |

---

## B4a — Live-smoke sweep — Auto-Draft Factory (S1–S6)
The campaign 4-service stack: bring up once, run the chain. The single biggest live-smoke cluster.

`D-CAMPAIGN-S1-LIVE-SMOKE` (high) · `D-S2-IDEMPOTENCY-LIVE-SMOKE` · `D-CAMPAIGN-CLAIM-LIVE-SMOKE` · `D-CAMPAIGN-CANCEL-LIVE-SMOKE` · `D-CAMPAIGN-BREAKER-PAUSE-LIVE-SMOKE` · `D-S3A-GOVERNOR-LIVE-SMOKE` · `D-S3B-BACKOFF-LIVE-SMOKE` · `D-S4A-THREADING-LIVE-SMOKE` · `D-S4B-RELAY-LIVE-SMOKE` · `D-S4C-CONSUMER-LIVE-SMOKE` · `D-S4D-LIVE-SMOKE` · `D-S5A-ESTIMATE-LIVE-SMOKE` · `D-S5B-LIVE-SMOKE` · `D-S5BEVAL-LIVE-SMOKE` · `D-S5C-LIVE-SMOKE` (high, browser) · `D-S6-LIVE-SMOKE` · `D-RERANK-BYOK-LIVE-SMOKE` (high). *(~17 — may split a1 backend / a2 S5–S6+browser.)*

---

## B4b — Auto-Draft Factory functional / correctness gaps

| ID | Description | sev |
|---|---|---|
| `D-CAMPAIGN-CANCEL-PROP` | propagate campaign cancel to in-flight jobs | med |
| `D-CAMPAIGN-BREAKER-PAUSE` | auto-pause campaign on provider circuit-open | med |
| `D-S4-SUMMARY-ATTRIBUTION` / `D-S4A-SUMMARY-COST` | thread summary-generation LLM spend attribution | med |
| `D-S5BEVAL-LEARNING-OUTBOX` | transactional outbox for `eval_judged` emit | med |
| `D-CAMPAIGN-KPROJECT-OWNERSHIP` | pre-validate campaign user owns the knowledge project | low |
| `D-CAMPAIGN-CONSUMER-NO-DLQ` | projection consumer drops on error, no DLQ | low |
| `D-S3A-INTERACTIVE-GOVERNANCE` | wrap interactive stream + media workers in the governor | low |
| `D-RERANK-COHERE-SHAPE` / `D-RERANK-LOCAL-NOKEY` | non-Cohere rerank adapter shapes + local empty-secret parity | low |
| `D-S5A-RERANK-COST` / `D-S5A-TARGET-LANG-RATIO` | estimator: rerank cost dim + per-language expansion ratio | low |
| `D-S4C-STREAMING-REALCOST` | real per-model cost for the streaming `/record` path | low |

---

## B5 — Live-smoke sweep — Wiki + Glossary + E0
Wiki + glossary + collaborator (E0) cross-service round-trips on a real stack.

`D-WIKI-M1-LIVE-SMOKE` · `D-WIKI-M3-LIVE-SMOKE` · `D-WIKI-M4-LIVE-SMOKE` · `D-WIKI-M5-LIVE-SMOKE` · `D-GLOSSARY-LIVE-SMOKE-BROWSER` (diff-card Apply + schema-confirm) · `D-E0-3-P2B-LIVE-SMOKE` (summary billing E2E). Plus the small Wiki correctness gaps that pair naturally: `D-WIKI-P2-SWEEP-DISMISS-RESWEEP` (med), `D-WIKI-M6-CONSUMER-GROUP` (med, HA), `D-WIKI-M4-NEUTRALIZED` (med), `D-WIKI-M6-PRECISE-COST` (med).

---

## B6 — Translation V3 functional gaps

| ID | Description | sev |
|---|---|---|
| `D-TRANSL-M7D-INLINE-JUDGE` | move inline fidelity judge out-of-band/sampled (latency) | high |
| `D-TRANSL-RESUME` | skip-completed batch logic | med |
| `D-TRANSL-VERIFY-WHOLEWORD` | whole-word matching for name compliance | med |
| `D-TRANSL-M4B-RESIDUALS` | multi-fetch abort + injection neutralization | med |
| `D-TRANSL-M2-VERIFY-BATCHING` | batch LLM verifier (40-block cap) | low |
| `D-TRANSL-M2-LLM-ADVISORY` | surface LLM issues vs auto-correct | low |
| `D-TRANSL-M3-DIALOGUE-HEURISTIC` | balanced-quote dialogue detection | low |
| `D-TRANSL-M4B-FANOUT-CACHE` | per-book/project TTL cache for entity fetches | low |
| `D-TRANSL-M4C-HARVEST-LATIN` | false-positive guard for name harvesting | low |
| `D-TRANSL-CORRECTOR-LIMITS` | corrector max_tokens + list-structure preservation | low |
| `D-TRANSL-M7C2-DIRTY` | Tiptap dirty-check + onSaved + unsaved warning | low |
| `D-TRANSL-VERIFY-COARSE` / `D-TRANSL-VERIFY-2ND-FETCH` | refined number/CJK-leak detection; share one glossary fetch | low |
| `D-TRANSL-M6B2-PERLANG-JOB` | one-click per-language re-translate UI | low |

---

## B7 — Knowledge Projects FE (K19) — mobile + filters + polish
Coherent FE feature batch on the knowledge-projects surface.

- **Mobile-responsive:** `D-K19d-β-01` (EntitiesTable grid), `D-K19d-β-02` (Timeline grid).
- **Filters:** `D-K19e-α-01` (entity_id), `D-K19e-α-02` (ISO range), `D-K19e-α-03` (chronological toggle), `D-K19e-γa-01` (source_type), `D-K19e-γa-02` (drawer-search embed cost).
- **Job-history UX:** `D-K19b.1-01` (cursor pagination ~150 jobs), `D-K19b.2-01` (show-more), `D-K19b.3-01/02` (human-readable current-item + ETA), `D-K19b.8-02/03` (orchestrator pipeline logs + tail-follow).
- **Scope/build:** `D-K19a.5-04` (chapter_range picker + runner enforcement, med), `D-K19a.5-06` (glossary_sync scope), `D-K19a.5-07` (run-benchmark CTA), `D-K19c.4-01` (archive variant keeping `glossary_entity_id`).
- **Test cov:** `D-K19a.7-01` (useProjectState action smokes), `D-K19a.8-01` (MSW dialog stories).

---

## B8 — Search/Rawsearch + cosmetic cleanup + misc code gaps

- **Search:** `D-RAWSEARCH-CANON-WIRING` (med — surface=canon|all through orchestrator+FE), `D-RAWSEARCH-P3C-ROBUST-MAP`, `D-RAWSEARCH-SEED-PAGINATION`, `D-RAWSEARCH-EVAL-CI-PLUS`, plus low cosmetic (`E5/E5B/E6/TITLE-FORMAT`).
- **Cleanup:** `D-S4C-ACCOUNTBALANCES-DROP` (drop inert table+endpoint), `D-S4B-RELAY-SHUTDOWN` (graceful SIGTERM), `D-RERANK-I18N`, `D-WIKI-SEED-ROBUSTNESS`, `D-WIKI-DELETEKIND-CONTRACT`, `D-WIKI-M5-SUGGESTION-DEDUP`, `D-WIKI-M7B-GEN-LIMIT`, `D-WIKI-M7B-RUNNING-CANCEL`, `D-TRANSL-M6A-NOTES`, `D-TRANSL-M5D-SYNC-NOTES`, `D-FACTORY-ACTIVITY-TRIM`.
- **Glossary/versioning:** `D-GLOSSARY-VERSIONING` (VG-2/3, med), `D-GLOSSARY-SORT-BE` (counts-sort BE, `glossary entity_counts.go:10`), `D-E0-4-PY-GRANT-SDK-EXTRACT` (extract shared grant SDK, 4 copies, med).
- **Misc code gaps:** `provider-registry worker.go:400` (non-streamable ops 501 → implement, med), `book-service media.go:506/527` (`D-PHASE5E` expose provider_model_name + provider_kind analytics), SDK low gaps (`grantclient` instant-revoke v1.1, `llmgw` batch partial-success, `loreweave_llm` multi-video, `pass2_filter` entity-FK canonical form), `knowledge extraction.py:843` (project-scoped active-job lookup — also fits Park/perf).

---

## 🅿️ Park bucket — NOT debt to clear (acknowledge only)

**Knowledge eval / extraction R&D** (fix when eval shows pain, not a task to "clear"):
`D-PASS2-FILTER-*` (NEO4J-REALIZED-F1, FACTS-SUPPORT, RELATION-ONLY-OPT, CLOUD-CALIBRATION, RUNTIME-FLAG, CACHE, PER-USER-UI, CATEGORIES-AB-TUNE, PER-JOB-OVERRIDE), `D-PASS2-WRITER-*`, `D-PASS2-CASCADE-*`, `D-EVENT-RULE-*`, `D-CYCLE71/1-*`, `D-EVENT-AGGREGATOR-FUZZY-MATCH`, `D-CLAUDE-JUDGE-VS-GEMMA-*`, `D-EVAL-FRAMEWORK-*`, `D-LM-STUDIO-RESPONSE-FORMAT-*`, `D-JUDGE-EVAL-ASYNCIO-TEARDOWN`, `D-EXTRACTION-PARALLEL-CONCURRENCY-FLAKE`, `D-AGGREGATOR-REASONING-CONTAMINATION-GUARD`, `D-MCP-TASKS-MIGRATION`, `D-MCP-DIRECT-RETURN`.

**Perf-when-pain:** `D-S3A-GOVERNOR-FAIRNESS`, `D-S4C-CONSUMER-PEL`, `D-S4D-CONSUMER-PEL`, `D-TRANSL-M6B-USAGE-BATCH`, `frontend useJobProgressRate.ts:46` (>10k jobs), `knowledge benchmark runner.py` (distributed lock at scale).

**Blocked on a larger refactor (do NOT pick up standalone):** `D-EXTRACTION-RAW-OUTPUT-CACHE` (ex-DEFERRED #077; persist+reuse raw extraction output) — PO-gated behind `world-core-foundation` → extraction-pipeline refactor; it is ONE slice of that refactor, not a standalone feature. Full spec/plan: `docs/specs|plans/2026-06-12-extraction-raw-output-cache.md`. *(Re-filed here at the 2026-06-16 origin/main merge — DEFERRED.md was reset to main's authoritative foundation ledger.)*

**HA / scale (document constraint, don't build now):** `D-CAMPAIGN-DRIVER-SINGLETON` (single-replica until HA claim dispatch).

**Won't-fix / superseded:** `D-RAWSEARCH-P2-COSINE-RANK` (superseded by E5B rerank), `D-JOBS-SPEND-CONSUMER-MISFIT` (money-safety micro-pattern, intentionally hand-rolled), `D-JOBS-EMIT-RECONCILE-BACKSTOP` (by-design), `D-JOBS-VIDEOGEN-OUTBOX-FLAGGATED` (flag-gated by-design).

**Low-value backfill/contract notes:** `D-TRANSL-M6B-USAGE-BACKFILL`, `D-P1-CHAPTER-RAW-AUDIT`, `D-P1-CONTRACT-DRIFT-TEST`, `D-P1-LEAF-TEXT-NESTED`, `D-DOCKER-RESTART-INVESTIGATION`, `D-WORKER-INFRA-CONFIG-TEST`, `D-CYCLE73F-LIVE-SMOKE` (when stable).

---

### Notes
- Counts are approximate; the handoff is the SSOT for exact wording — confirm each row's current state at batch start (some may have been cleared in flight).
- Live-smoke batches assume the rebuild-stale-images-first discipline (a stale image false-greens).
- When a batch completes, tick its row in the Sequencing overview + move cleared items to a "Recently cleared" note (or delete after a couple of sessions), per the project's defer-drift discipline.
