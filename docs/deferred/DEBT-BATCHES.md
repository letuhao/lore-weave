# Debt-Clearing Batches — `feat/auto-draft-factory-gaps`

**Created:** 2026-06-16 · **Source:** full-branch sweep of `docs/sessions/SESSION_HANDOFF.md` (open deferrals) + production-code debt markers (`services/*/app|internal|src`, `frontend/src`, `sdks`). Items already `✅/CLEARED` are excluded.

**Purpose:** turn the scattered deferral backlog into **coherent long-run batches**, each drivable as one continuous `/loom <batch>` flow. Batches are sequenced top-down by priority. A separate **Park bucket** lists items that are *not* debt to clear (R&D / perf-when-pain / HA-scale / wontfix) — do NOT spend long-runs there.

**Legend:** severity `high|med|low` · type `correctness|telemetry|feature-gap|live-smoke|perf|cleanup` · source `[H]`=handoff `[C]`=code.

**How to use:** pick the top open batch → `/loom <batch goal>` → clear its items → tick them here in the same commit. Live-smoke batches: rebuild touched images first (stale = false-green), bring the relevant stack up once, run all smokes in the batch.

---

## Sequencing overview

| # | Batch | Type | ~Items | Size | Status |
|---|---|---|---:|---|---|
| **B0** | Correctness sweep (cross-service, small + high-value) | correctness | 7 | M | ✅ 2026-06-16 |
| **B1** | Jobs GUI telemetry completeness (P4) | telemetry | 9 | L | ✅ 2026-06-17 |
| **B2** | Jobs control completeness (P3) | feature-gap | 3 | M | ✅ 2026-06-17 |
| **B3** | Live-smoke sweep — Job Control Plane + P5 | live-smoke | 4 | M | ☐ |
| **B4a** | Live-smoke sweep — Auto-Draft Factory (S1–S6) | live-smoke | ~17 | L | ☐ |
| **B4b** | Auto-Draft Factory functional/correctness gaps | feature/correctness | ~10 | L | ☐ |
| **B5** | Live-smoke sweep — Wiki + Glossary + E0 | live-smoke | ~9 | L | ☐ |
| **B6** | Translation V3 functional gaps | feature/correctness | ~13 | L | ☐ |
| **B7** | Knowledge Projects FE (K19) — mobile + filters + polish | feature-gap (FE) | ~20 | L | ☐ |
| **B8** | Search/Rawsearch + cosmetic cleanup + misc code gaps | mixed/low | ~18 | M | ☐ |

Recommended order: ~~B0~~ ✅ → ~~B1~~ ✅ → ~~B2~~ ✅ → **B3** (Job Control Plane warm + de-risk money-path), then **B4a/B5** (live-smoke confidence sweeps), then **B4b → B6 → B7 → B8**. **Next open: B3** (+ a NEW finding: glossary-extract pipeline never wired into the control plane — see `D-JOBS-GLOSSARY-EXTRACT-UNWIRED` below; suspected to be one of several un-wired producers — audit needed).

---

## B0 — Correctness sweep — ✅ CLEARED 2026-06-16
Small, well-defined fixes that reduce latent risk. Cross-service but each is independent.
CLARIFY refined 7 items → **3 real fixes** + **4 no-ops** (handoff-confirmed won't-fix / confirmed-intended / already-resolved).

| ID / location | Description | sev | resolution |
|---|---|---|---|
| `D-JOBS-EMIT-STATUS-PASSTHROUGH-ROLLBACK` | `JobStatus()` raised in-tx on an unmapped native status → rolled back a legit transition | high | ✅ **FIXED** — `emit.py` tolerant `_coerce_status` (canonical/case-insensitive/alias-map) → **map-or-skip** (skip logs `[EMIT_STATUS_SKIPPED]` + `skipped_emit_total()` counter, never raises); reconcile sweep backstops |
| `provider-registry server.go` (embed) | validate model is embedding-capable before dispatch (K12.1 TODO) | high | ✅ **FIXED** — `canEmbed()` rejects only **affirmatively-detected** non-embedding caps (rerank/stt/tts/image_gen/video_gen), fail-OPEN on empty/`chat`-default; `[]byte`+Unmarshal scan (review-impl HIGH×2) |
| `D-TRANSL-VERSION-NUM-RACE` | `version_num = MAX+1` collided on `idx_ct_version` → 500 | med | ✅ **FIXED** — `pg_advisory_xact_lock` at the 2 unguarded insert sites (create-loop sorted for deadlock-safety + save-edited), same key as `patch_translation_block`; wiring pinned by tests (review-impl MED) |
| `D-S5B-EMBED-CREATE-ATOMICITY` | project patch precedes campaign insert (ordering) | med | ⊘ **no-op** — handoff (SESSION_HANDOFF L408) classifies won't-fix (benign post-patch mutation) |
| `D-REDIS8-CONSUMERS` | port `TimeoutError` catch + pin redis across consumers | med | ⊘ **no-op** — already resolved: every blocking consumer (campaign/worker-ai raw + knowledge/learning/video-gen via shared `BaseProjectionConsumer`/`BaseTerminalConsumer`) catches the redis-py-8 idle `TimeoutError`; `redis>=5.0` is version-tolerant given the catch |
| `D-S4A-MIGRATION-ORDERING` | knowledge migration before worker-ai starts | low | ⊘ **no-op** — handoff (L408) won't-fix (inert: running jobs exist only post-migration) |
| `worker-infra outbox_relay.go:108` | confirm quiet-retry on a missing `outbox_events` table | med | ⊘ **no-op** — confirmed intended: video-gen creates `outbox_events` unconditionally at migration → missing-table is transient cold-start, already logged once-per-transition via `noteTableState` |

**Verify:** SDK emit 9/9 (+ skip-counter) · SDK jobs suite 47 passed · provider-registry `canEmbed` 13/13 + pkg compiles · translation versions+jobs 74/74 · provider-gate OK.
**Live-smoke:** deferred to **B3** (Job-Control + P5 sweep, rebuild-stale-first) — tracked as `D-B0-LIVE-SMOKE`. Fixes are unit-proven + low-risk.

---

## B1 — Jobs GUI telemetry completeness (P4) — ✅ CLEARED 2026-06-17
Make the unified jobs dashboard show complete cost/model/tokens for **every** kind + wire retry.
Shipped as 4 milestones (plan `docs/plans/2026-06-16-b1-jobs-telemetry.md`): M1 model-names+spend
(`92850509`/`2e2c8977`) · M2 translation cost (`7354ce5b`) · M3 summary+overlay (`f3fe9430`) ·
M4 retry=re-submit (this commit). **All 9 items done.** Retry shipped for **translation** only;
the other kinds are tracked deferrals (each needs its own work — see Park/below):
`D-JOBS-P4-RETRY-COMPOSITION` (clean — input JSONB; just not wired), `D-JOBS-P4-RETRY-KNOWLEDGE`
(needs stored model-ref UUIDs / a request_json blob), `D-JOBS-P4-RETRY-VIDEOGEN` (map the
submit-then-create path), `D-JOBS-P4-RETRY-LORE` (sync in-process → incompatible with the
deferred control contract; re-arch or leave as manual re-submit). Live-smoke → `D-B1-LIVE-SMOKE` (B3).
`D-JOBS-P4-RETRY-CAMPAIGN-GATE` (low) — a campaign-dispatched translation job's Retry button
still renders (the cap-gate can't see `campaign_id` — not on the projection); clicking it safely
409s (`TRANSL_CAMPAIGN_MANAGED`). Hiding the button needs the projection to carry campaign
membership. Safe today (server refuses); cosmetic UX wart.

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

## B2 — Jobs control completeness (P3) — ✅ CLEARED 2026-06-17
Finished the control surface gaps. Plan: `docs/plans/2026-06-17-b2-jobs-control-completeness.md`.
All 3 closed, no new deferrals (live-smoke → B3). `/review-impl` caught 1 HIGH (resume re-driving a
`failed` chapter over-counted completed+failed past total → stuck job; fixed: resume re-drives
`pending` only) + 1 MED (best-effort abort broadened to `except Exception`).

| ID | Description | sev | resolution |
|---|---|---|---|
| `D-JOBS-P3-TRANSLATION-PAUSE` | translation stop-dispatch pause/resume + re-add to `_MULTI_UNIT_KINDS` | med | ✅ contract + pause/resume cores (running↔paused, resume re-drives pending-only from stored row) + worker paused-drop + stale-aware guarded claim (dup-safety vs parked WFQ units) |
| `D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT` | video-gen cancel doesn't abort the in-flight provider job (reclaim slot/cost) | med | ✅ best-effort `Client.cancel_job(provider_job_id)` after the local CAS (reclaims slot+reservation; local row canonical) |
| `D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL` | one-shot `enrichment_compose_task` not control-wired | low | ✅ status-only cancel (option a) — endpoint + claim-skip + `_mark` guard + status-CHECK widen migration |

**Verify:** jobs 67p · translation 770p · video-gen 53p · lore 773p · provider-gate OK. Live-smoke → B3.

### Producer-emit backfill (2026-06-17) — systematic P1 gap, spec `docs/specs/2026-06-17-producer-emit-backfill.md`
Audit confirmed **4 un-wired producers** (glossary-extract, glossary-translate, wiki-gen, book-import). Slices A→C→B→D.

| ID | Description | sev | status |
|---|---|---|---|
| `D-JOBS-GLOSSARY-EXTRACT-UNWIRED` | glossary-extract (translation `extraction_jobs`) emitted nothing → invisible in Jobs screen; + FE pick inherited 'all'; + create sync freeze | high | ✅ **Slice A** — emit pending(create,in-tx)/running/terminal/cancelled(worker) + reconcile UNION (kind `glossary_extraction`) + FE clear-on-pick + bulk-insert/atomic create + kind label×4. Live-smoke → `D-PRODUCER-EMIT-GLOSSARY-EXTRACT-LIVE-SMOKE` (B3). |
| `D-JOBS-WIKI-GEN-UNWIRED` | `wiki_gen_jobs` (knowledge) emitted nothing → invisible in Jobs screen | high | ✅ **Slice C** — emit pending(create,in-tx)/running(claim)/paused/pending(resume)/cancelled/completed/failed at all 7 repo mutations (each UPDATE+emit in one tx, RETURNING user_id+cost; guarded emits only fire on a real transition) + reconcile UNION into `/internal/knowledge/jobs` (kind `wiki_gen`, `complete`→`completed`, merged oldest-first w/ extraction) + FE kind label×4. Live-smoke → `D-PRODUCER-EMIT-WIKI-GEN-LIVE-SMOKE` (B3). |
| `D-JOBS-GLOSSARY-TRANSLATE-UNWIRED` | `glossary_translation_jobs` (translation) emitted nothing → invisible in Jobs screen | high | ✅ **Slice B** — create emits pending(in-tx)+cancelling; worker emits running(claim)/cancelled(guarded settle + mid-loop)/completed(terminal, summed tokens)/failed; reconcile 3rd UNION arm (kind `glossary_translation`, `completed_with_errors`→completed); FE kind label×4; view-only gate extended (`_VIEW_ONLY_KINDS`). Live-smoke → `D-PRODUCER-EMIT-GLOSSARY-TRANSLATE-LIVE-SMOKE` (B3). |
| `D-JOBS-BOOK-IMPORT-UNWIRED` | `import_jobs` (book-service, Go) emits no JobEvent → invisible (needs Go emit via outbox+relay) | med | ☐ Slice D |
| `D-PRODUCER-EMIT-GLOSSARY-EXTRACT-COST` | glossary-extract emits tokens but not actual $cost (estimate only); price summed tokens via the billing oracle (like translation B1-M2) | low | ☐ later |
| `D-JOBS-SECONDARY-KIND-CONTROL` | Slice A/C: `glossary_extraction` + `wiki_gen` are SECONDARY kinds whose service control endpoints (translation/knowledge) handle only the PRIMARY job table → unified control would 404. Gated **view-only** in `derive_control_caps` (`_VIEW_ONLY_KINDS`) so no broken buttons; users control via native panels. Wire unified control (dispatch by kind in the service's `/internal/{svc}/jobs/{id}/{action}`) to lift view-only. | med | ☐ later |
| `D-JOBS-WIKI-GEN-RECONCILE-INDEX` | wiki-gen reconcile `list_since` filters `wiki_gen_jobs.updated_at` with no index (extraction_jobs has one). Table is tiny (1 active job/book) → seq-scan fine for now; add `idx_wiki_gen_jobs_updated_at` if the sweep shows pain. | perf | ☐ later |

---

## B3 — Live-smoke sweep — Job Control Plane + P5
Stack up with `P5_SCHED_ENABLED=true`, seed one extraction-ready project. Run all in one session.

| ID | Description | sev |
|---|---|---|
| `D-P5-M3-EXTRACTION-LIVE-SMOKE` | decoupled extraction with P5 on; assert `p5:knowledge:extraction:inflight:{user}` ZCARD ≤ cap | high |
| `D-P5-M2-MULTI-OWNER-LIVE-SMOKE` | 2-user interleave on the stack (single-owner cap-hold already proven) | med |
| `D-JOBS-P2-SSE-LIVE-SMOKE` | real consumer-upsert → pub/sub → connected-client push | med |
| `D-JOBS-P3-KNOWLEDGE-CANCEL-SUCCESS-LIVE-SMOKE` | a successful cancel mutating a real running extraction row | med |
| `D-PRODUCER-EMIT-GLOSSARY-EXTRACT-LIVE-SMOKE` | Slice A: real glossary-extract job emits pending→running→terminal that land in `job_projection` (visible on Jobs screen) | high |
| `D-PRODUCER-EMIT-WIKI-GEN-LIVE-SMOKE` | Slice C: real wiki-gen job emits pending→running→complete/cancelled that land in `job_projection`; reconcile UNION surfaces it | high |
| `D-PRODUCER-EMIT-GLOSSARY-TRANSLATE-LIVE-SMOKE` | Slice B: real glossary batch-translate job emits pending→running→completed that land in `job_projection`; reconcile UNION surfaces it | high |

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
