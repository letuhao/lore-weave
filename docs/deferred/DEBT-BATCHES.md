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
| **B3** | Live-smoke sweep — Job Control Plane + P5 | live-smoke | 7 | M | ✅ 2026-06-17 (all 7 proven; FULL-E2E belt-suspenders remains low) |
| **B4a** | Live-smoke sweep — Auto-Draft Factory (S1–S6) | live-smoke | ~17 | L | ☐ (needs 4-svc campaign stack + browser) |
| **B4b** | Auto-Draft Factory functional/correctness gaps | feature/correctness | ~10 | L | ☐ (not yet scoped) |
| **B5** | Live-smoke sweep — Wiki + Glossary + E0 | live-smoke | ~9 | L | ☐ (needs stack + browser) |
| **B6** | Translation V3 functional gaps | feature/correctness | ~13 | L | ✅ 2026-06-17 (3 fixed + 5 verified-resolved; rest low) |
| **B7** | Knowledge Projects FE (K19) — mobile + filters + polish | feature-gap (FE) | ~20 | L | ◑ reconciled — ~5 already-shipped; rest need design/backend/browser |
| **B8** | Search/Rawsearch + cosmetic cleanup + misc code gaps | mixed/low | ~18 | M | ◑ partial — D-RERANK-I18N fixed + 3 resolved; rest open |

Recommended order: ~~B0~~ ✅ → ~~B1~~ ✅ → ~~B2~~ ✅ → ~~B3~~ ✅ → ~~B6~~ ✅ → (B7/B8 reconciled). **Remaining open batches: B4a, B4b, B5 (campaign/wiki live-smokes — need the multi-service stack + browser), plus the residual low rows in B7/B8 and the B6 perf-when-pain items.** Per the 2026-06-17 reconciliation, ~40-50% of "open" rows in B6/B7/B8 were already-shipped-but-unticked → the genuine remaining backlog is much smaller than the ~item counts suggest.

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
| `D-JOBS-BOOK-IMPORT-UNWIRED` | `import_jobs` (book-service, Go) emitted nothing → invisible in Jobs screen | med | ✅ **Slice D** — Go `emitJobEvent` (outbox `aggregate_type='jobs'` → relay → `loreweave:events:jobs`; canonicalizes native status `processing`→running, skips unmappable like the Py SDK); `startImport` emits pending(in-tx), `updateImportJobStatus` wrapped in tx + RETURNING user_id → emits the transition (404 on missing, was silent 204); new `GET /internal/book/jobs` reconcile source + jobs-service `_RECONCILE["book"]` + `book_service_internal_url` config; FE kind label×4; view-only gate (`book_import` — book-service has NO control endpoint). Live-smoke → `D-PRODUCER-EMIT-BOOK-IMPORT-LIVE-SMOKE` (B3). |
| `D-PRODUCER-EMIT-GLOSSARY-EXTRACT-COST` | glossary-extract emits tokens but not actual $cost (estimate only); price summed tokens via the billing oracle (like translation B1-M2) | low | ☐ later |
| `D-JOBS-SECONDARY-KIND-CONTROL` | Slice A/B/C secondary kinds were view-only (control would 404). | med | ✅ **DONE 2026-06-17** — `kind` now rides the control forward body (`forward_control` + `jobs.py`; other services ignore it, Pydantic `extra='ignore'`). `derive_control_caps` gives each secondary kind its NATIVE caps: glossary_extraction/glossary_translation = cancel-only (pending\|running), wiki_gen = cancel(pending\|paused)+resume(paused) (no running-cancel, D-WIKI-M7B); `book_import` stays view-only (no control endpoint). translation `control_job` dispatches glossary kinds → `_cancel_secondary_core` (owner-scoped, 404/409, UPDATE→cancelling+emit on the right table); knowledge `control_extraction_job` dispatches `wiki_gen` → `_control_wiki_gen_job` (owner re-check via repo.get, repo.cancel/resume which emit). Tests: jobs-service caps 70 · translation dispatch 15 · knowledge wiki-dispatch 16. Live-smoke → `D-SECONDARY-KIND-CONTROL-LIVE-SMOKE`. |
| `D-JOBS-WIKI-GEN-RECONCILE-INDEX` | wiki-gen reconcile `list_since` filters `wiki_gen_jobs.updated_at` with no index (extraction_jobs has one). Table is tiny (1 active job/book) → seq-scan fine for now; add `idx_wiki_gen_jobs_updated_at` if the sweep shows pain. | perf | ☐ later |

---

## B3 — Live-smoke sweep — Job Control Plane + P5
Stack up with `P5_SCHED_ENABLED=true`, seed one extraction-ready project. Run all in one session.

| ID | Description | sev |
|---|---|---|
| `D-P5-M3-EXTRACTION-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — REAL decoupled extraction proven with the per-owner cap engaging. Setup: 2 knowledge projects on a published 5-chapter book (`019eb60e`), embedding=bge-m3, LLM=Qwen2.5-7B, started via the gateway API (passing-benchmark row inserted as test fixturing for the orthogonal K17.9 gate); `P5_OWNER_CAP` lowered to 1 so the cap bites with 2 concurrent jobs. Observed for 24s: `ZCARD p5:knowledge:extraction:inflight:{owner}` pinned at **1 (= cap)**, `inflight_total=1`; job A held the slot (resume_state NOT NULL, cost $0.004), job B continuously logged "at P5 cap — deferring next chunk to a later poll" with **cost $0** (the gate runs BEFORE try_spend → a deferred chunk never inflates cost). A finding the unit tests can't show: one decoupled job submits exactly ONE chunk per poll then waits ([runner.py:1948](../../services/worker-ai/app/runner.py#L1948)), so the per-user cap only bites across MULTIPLE concurrent jobs — that's the configuration the smoke must (and did) create. | high |
| `D-P5-M2-MULTI-OWNER-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — per-owner isolation / anti-starvation proven live. With owner1 already at cap (ZCARD=1), seeded 2 running jobs for a SECOND owner (`019d4966…`, own BYOK models + book `019ebb6c`, rows direct-inserted as `status='running'` — the worker's poll + P5 acquire path is identical regardless of how the row reached running). Observed simultaneously: `inflight:{owner1}=1`, `inflight:{owner2}=1`, `inflight_total=2` — owner2 acquired its OWN slot despite owner1 being saturated, and owner2's 2nd job was independently deferred by owner2's own cap. The per-owner ZSET key (`…:inflight:{owner}`) makes the isolation structural; there is no shared counter that could cross-starve. | med |
| `D-JOBS-P2-SSE-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — subscribed to `loreweave:jobs:user:<uid>`, inserted a `jobs` event → relay → consumer upsert → pub/sub publish RECEIVED by the subscriber with the full JobEvent payload (incl. derived `control_caps:[]` for book_import). (Manual-publish isolation confirmed plumbing; the real proof needed a window > the variable relay latency.) | med |
| `D-JOBS-P3-KNOWLEDGE-CANCEL-SUCCESS-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — cancelled the actively-inflight extraction job A (above) via `POST /v1/knowledge/projects/{id}/extraction/cancel` → 200 `status=cancelled`; `extraction_jobs` row → cancelled; knowledge `outbox_events` carried `job.cancelled` (H1 same-tx emit), relayed → `loreweave_jobs.job_projection` = `knowledge\|extraction\|cancelled`. Re-proves the cancel-path producer-emit on a REAL running row. (The held P5 token releases at the chunk terminal/TTL, not synchronously by cancel — as designed.) | med |
| `D-SECONDARY-KIND-CONTROL-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — unified control dispatch PROVEN on the stack (after rebuild): glossary_extraction cancel → `extraction_jobs`→cancelling + emit landed in `job_projection`; wiki_gen resume → pending (re-enqueue ran, no 500) + emit; wiki_gen cancel → cancelled. glossary_translation shares the identical `_cancel_secondary_core` dispatch. | high |
| `D-PRODUCER-EMIT-BOOK-IMPORT-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — Slice D cross-language path PROVEN on the running stack: (1) a `book_import` `jobs` outbox event inserted into `loreweave_book` → worker-infra relay → landed in `loreweave_jobs.job_projection` (service=book, kind=book_import, status=pending, title); (2) `GET /internal/book/jobs` returns the canonical JobEvent with native `processing`→`running` mapping + `progress.done=7`. Synthetic data cleaned. | high |
| `D-PRODUCER-EMIT-RECONCILE-UNIONS-LIVE-SMOKE` | ✅ **DONE 2026-06-17** — the reconcile UNION SQL added in A/B/C validated live (200 + valid JobEvent JSON, not 500): translation 3-way UNION (translation + glossary_extraction + glossary_translation) returns rows; knowledge UNION (extraction + wiki_gen) returns valid `{"jobs":[]}`. Confirms the new tables' columns resolve against the real schema. | high |
| `D-PRODUCER-EMIT-{GLOSSARY-EXTRACT,WIKI-GEN,GLOSSARY-TRANSLATE}-FULL-E2E` | Remaining: trigger a REAL job of each kind via the gateway (JWT + real book/project + LLM) and observe pending→running→terminal land in `job_projection`. LOWER priority — the Python emit lib is proven (B1), the relay `jobs` routing is established + re-proven (book), and each worker's emit wiring is unit-tested; this is the belt-and-suspenders full path. | med |

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

**Sweep 2026-06-17 (one /loom, S):** 3 genuinely-open items FIXED + 5 found ALREADY-RESOLVED by recent T1/T2 work (verified, not trusted). translation 790 pytest (+11). Remaining rows are low polish.

| ID | Description | sev |
|---|---|---|
| `D-TRANSL-M7D-INLINE-JUDGE` | ✅ **ALREADY DONE (verified 2026-06-17)** — the fidelity judge is NOT inline: `chapter_worker._emit_chapter_done` emits a post-commit `translation.quality` transactional-outbox event (the actual judge runs downstream in learning-service M7d-2), and the text feed is already **capped + fraction-sampled** (`translation_judge_feed_max_chars`, [chapter_worker.py:964-973](../../services/translation-service/app/workers/chapter_worker.py)). Out-of-band AND sampled = the deferral's ask. No latency on the translate path. | high |
| `D-TRANSL-RESUME` | ✅ **ALREADY DONE (verified 2026-06-17)** — `jobs.py` skip-gate skips a chapter iff `status='completed' AND NOT is_glossary_stale` (fresh-completed-version EXISTS, not the active version — the correct idempotency scope), and emits `chapter.translation_skipped` so resumed campaigns converge. Covered by `test_idempotency.py`. | med |
| `D-TRANSL-VERIFY-WHOLEWORD` | ✅ **DONE 2026-06-17** — `verifier._name_present`: non-CJK glossary source names now require unicode word boundaries (kills the "King" ⊂ "Kingdom" false positive that churned the corrector); CJK keeps substring behind the `len>=2` guard (no in-service segmenter). `tgt_name not in draft` stays substring on purpose (safe direction). +3 tests. | med |
| `D-TRANSL-M4B-RESIDUALS` | ✅ **DONE 2026-06-17** — `knowledge_context._fetch_all_neighborhoods`: each entity fetch is now `asyncio.wait_for`-bounded (`_FETCH_TIMEOUT_S=5s`) + failure-isolated (`except Exception` → `WikiNeighborhood.empty()`, entity keeps its bio line) so one slow/failing entity can't abort the whole brief; `CancelledError` (BaseException) still propagates = the "abort" half. Injection neutralization was already complete (`_sanitize`). +2 tests. | med |
| `D-TRANSL-M2-VERIFY-BATCHING` | batch LLM verifier (40-block cap) | low |
| `D-TRANSL-M2-LLM-ADVISORY` | ✅ **ALREADY DONE (verified 2026-06-17)** — advisory-by-design: LLM-flagged issues are capped high→med (`decoupled_v3_verify._cap_llm_issues` + `orchestrator.py:290`), so an LLM flag never ALONE triggers the destructive corrector re-translate (only rule-tier high does). | low |
| `D-TRANSL-M3-DIALOGUE-HEURISTIC` | ✅ **ALREADY DONE (verified 2026-06-17)** — `semantic_chunker._has_dialogue` groups on any CJK bracket / smart-quote / em-dash lead; grouping is pre-batch so unbalanced quotes are harmless (no validation gate). Pragmatic + fit-for-purpose. | low |
| `D-TRANSL-M4B-FANOUT-CACHE` | per-book/project TTL cache for entity fetches | low |
| `D-TRANSL-M4C-HARVEST-LATIN` | false-positive guard for name harvesting | low |
| `D-TRANSL-CORRECTOR-LIMITS` | ✅ **DONE 2026-06-17** — `corrector.build_corrector_submit_kwargs` now sets `max_tokens = min(16384, max(2048, est_tokens(src)×3))` (source-scaled, generous — bounds runaway/looping generation, never truncates a legit one-block correction) + a system-prompt line to preserve list/line structure. +5 tests. | low |
| `D-TRANSL-M7C2-DIRTY` | Tiptap dirty-check + onSaved + unsaved warning | low |
| `D-TRANSL-VERIFY-COARSE` (`D-TRANSL-VERIFY-2ND-FETCH` ✅ done — glossary fetched ONCE at `orchestrator.py:320`, reused across verify/correct rounds) | refined number/CJK-leak detection (COARSE still open; number/CJK rules are intentionally conservative — low value) | low |
| `D-TRANSL-M6B2-PERLANG-JOB` | one-click per-language re-translate UI | low |

---

## B7 — Knowledge Projects FE (K19) — mobile + filters + polish
Coherent FE feature batch on the knowledge-projects surface.

**Reconciliation 2026-06-17 (verified each row against the FE):** ~5 rows found ALREADY-SHIPPED but never ticked. The remaining open ones need a design call, backend metadata, or are marginal — NOT clean autonomous wins.

- **Mobile-responsive:** `D-K19d-β-01` ✅ **DONE (verified)** — `EntitiesTable` has the `hidden md:block` desktop grid + `md:hidden` mobile card tree ([EntitiesTable.tsx:104-223](../../frontend/src/features/knowledge/components/EntitiesTable.tsx)). · `D-K19d-β-02` (Timeline grid) — **effectively a no-op:** `TimelineEventRow` uses `grid-cols-[56px_1fr_auto]` with a `1fr` middle + `truncate` + a flex-**wrapping** meta line, i.e. responsive-by-construction (no fixed-wide grid like EntitiesTable had). A mobile-card rewrite is marginal + needs a browser to verify — left open, low value. Reclassify perf/polish.
- **Filters:** `D-K19e-α-01` ✅ **DONE (verified)** — entity_id picker shipped (`TimelineFilters` search→chip→`entity_id` param). · `D-K19e-α-02` (ISO range) — **intentionally deferred to cycle γ** (comment at `TimelineTab.tsx:18-21`; BE `after_order`/`before_order` already supported, UI not surfaced yet). · `D-K19e-α-03` (chronological toggle) — **OPEN, needs a design call:** the tab already toggles sort AXIS (narrative↔chronological); the deferral asks for asc/desc DIRECTION (a 2nd control + a `sort_direction` param). Ambiguous scope → not autonomous. · `D-K19e-γa-01` ✅ **DONE (verified)** — source_type radio-pills shipped (`DrawerSearchFilters`, `source_type` param threaded). · `D-K19e-γa-02` (drawer-search embed cost) — **hybrid, needs backend cost metadata** (the response carries `embedding_model` but no per-search cost estimate).
- **Job-history UX:** `D-K19b.1-01` (cursor pagination ~150 jobs), `D-K19b.2-01` ✅ **DONE (verified)** — "load more" wired (`ExtractionJobsTab` + `useExtractionJobs.fetchMoreHistory`, `next_cursor`). · `D-K19b.3-01/02` ✅ **DONE (verified)** — `JobDetailPanel` shows `current_chapter_title` + ETA via `useJobProgressRate` (EMA over poll deltas). · `D-K19b.8-02/03` (orchestrator pipeline logs + tail-follow).
- **Scope/build:** `D-K19a.5-04` (chapter_range picker + runner enforcement, med), `D-K19a.5-06` (glossary_sync scope), `D-K19a.5-07` (run-benchmark CTA), `D-K19c.4-01` (archive variant keeping `glossary_entity_id`).
- **Test cov:** `D-K19a.7-01` (useProjectState action smokes), `D-K19a.8-01` (MSW dialog stories).

---

## B8 — Search/Rawsearch + cosmetic cleanup + misc code gaps

**Reconciliation 2026-06-17 (verified each row against code):** `D-RERANK-I18N` FIXED; 3 rows found ALREADY-RESOLVED (`D-S4B-RELAY-SHUTDOWN`, `D-GLOSSARY-SORT-BE`, `provider-registry worker.go 501`); 2 confirmed legitimately-blocked (`D-S4C-ACCOUNTBALANCES-DROP` needs a migration → /amaw L+; `D-PHASE5E` blocked on a gateway SDK field).

- **Search:** `D-RAWSEARCH-CANON-WIRING` (med — surface=canon|all through orchestrator+FE), `D-RAWSEARCH-P3C-ROBUST-MAP`, `D-RAWSEARCH-SEED-PAGINATION`, `D-RAWSEARCH-EVAL-CI-PLUS`, plus low cosmetic (`E5/E5B/E6/TITLE-FORMAT`).
- **Cleanup:**
  - `D-S4C-ACCOUNTBALANCES-DROP` (drop inert token `account_balances` table + the `/v1/m03/balance/{user_id}` endpoint that still reads it) — **needs a DB migration (drop table) + an endpoint-contract decision (remove vs re-map to USD `spend_guardrails`/`platform_balances`). L+ → /amaw, not autonomous.** Still open.
  - `D-S4B-RELAY-SHUTDOWN` — ✅ **ALREADY DONE (verified 2026-06-17)**: the worker-infra outbox relay exits cleanly on `ctx.Done()` ([outbox_relay.go:125-127](../../services/worker-infra/internal/tasks/outbox_relay.go)), and `cmd/worker-infra/main.go` binds the ctx to `SIGINT`/`SIGTERM`; in-flight relays are idempotent (`published_at` guard).
  - `D-RERANK-I18N` — ✅ **DONE 2026-06-17**: `ModelMatrixStep`'s `label()` was already i18n-wrapped (`t('matrix.role.{role}', {defaultValue})`), but the `matrix.role.*` keys (all 6 roles) + `matrix.projectEmbedding` were absent from ALL 4 locale bundles → non-English users saw English. Added translated `role` (extractor/translator/verifier/eval_judge/embedding/reranker) + `projectEmbedding` to en/vi/ja/zh-TW campaigns.json. (Closed the whole role-label set, not just reranker.)
  - Remaining: `D-WIKI-SEED-ROBUSTNESS`, `D-WIKI-DELETEKIND-CONTRACT`, `D-WIKI-M5-SUGGESTION-DEDUP`, `D-WIKI-M7B-GEN-LIMIT`, `D-WIKI-M7B-RUNNING-CANCEL`, `D-TRANSL-M6A-NOTES`, `D-TRANSL-M5D-SYNC-NOTES`, `D-FACTORY-ACTIVITY-TRIM`.
- **Glossary/versioning:** `D-GLOSSARY-VERSIONING` (VG-2/3, med), `D-GLOSSARY-SORT-BE` — ✅ **ALREADY DONE (verified 2026-06-17)**: server-side counts-sort exists (`entityOrderBy` `links`→`cached_chapter_link_count DESC`, `evidence`→`cached_evidence_count DESC`, [entity_search.go:204-208](../../services/glossary-service/internal/api/entity_search.go)) and is wired to the list handler ([entity_handler.go:630](../../services/glossary-service/internal/api/entity_handler.go)). *(Perf note, NOT the deferral: the list handler still computes the displayed counts via inline correlated subqueries instead of the cached columns — a perf-when-pain item, untracked.)* · `D-E0-4-PY-GRANT-SDK-EXTRACT` (extract shared grant SDK, 4 copies, med).
- **Misc code gaps:** `provider-registry worker.go:397-403` — ✅ **WORKING-AS-INTENDED (verified 2026-06-17)**: a not-yet-implemented async operation fails fast with a user-facing `LLM_OPERATION_NOT_SUPPORTED` ("not yet implemented in async-job mode"); the `streamableOperations` whitelist gates support and a new op is added with its adapter when built — no code change owed (reclassify won't-fix). · `book-service media.go:527` (`D-PHASE5E` expose provider_model_name + provider_kind analytics) — **blocked on a gateway SDK change**: book-service hardcodes `provider_kind: ""` because `llmgw.ImageGenResult` doesn't expose it; unblock when the SDK adds the field (additive). · SDK low gaps (`grantclient` instant-revoke v1.1, `llmgw` batch partial-success, `loreweave_llm` multi-video, `pass2_filter` entity-FK canonical form), `knowledge extraction.py:843` (project-scoped active-job lookup — also fits Park/perf).

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
