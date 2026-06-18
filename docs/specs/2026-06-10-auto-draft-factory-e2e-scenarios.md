# E2E Scenario Spec — Auto-Draft Factory

**Date:** 2026-06-10 · **Branch:** feat/advanced-translation-pipeline
**Purpose:** exhaustive end-to-end scenario coverage (happy path + every state transition + edge/failure phases) for the Auto-Draft Factory, to drive a live-smoke / acceptance pass and guard regressions post-merge.
**Companion:** review `docs/reviews/2026-06-10-auto-draft-factory-draft-vs-impl-review.md` + recheck `docs/reviews/2026-06-11-auto-draft-factory-draft-vs-impl-RECHECK.md` (gaps CLEARED), gap plan `docs/plans/2026-06-10-auto-draft-factory-gap-implementation-plan.md`.
**Runnable spec:** `frontend/tests/e2e/specs/campaign-factory.spec.ts` (Playwright API-level, deterministic subset) + helper `frontend/tests/e2e/helpers/campaigns.ts`.

> **Update 2026-06-11:** the gap-fix work landed (G1–G4 + polish). Scenarios previously tagged `[GAP:Gx]` are now `[NOW]` (evidence in the RECHECK). New surfaces added: L6 activity log, L7 in-flight panel, C5 switch verifier/eval model.

## Legend
- **[NOW]** runnable against the current build. **[GAP:Gx]** ~~needs a gap fix first~~ — **all cleared 2026-06-11**. **[HARNESS]** needs load/fault injection. **[MODEL]** needs a JSON-clean judge model (LM-Studio gemma streaming bug). **[STALE]** rebuild touched images first (CLAUDE.md stale-image rule).

## Prerequisites / fixtures
- Stack up (`infra/docker-compose.yml`): campaign-service(8223), translation(+worker), knowledge(+worker-ai), provider-registry, usage-billing, learning, redis, rabbitmq, postgres, book-service, worker-infra (relay). **Rebuild any service touched since the running image** (stale-image false-greens).
- DBs: `loreweave_campaign` (+ `loreweave_campaign_test` with `TEST_CAMPAIGN_DB_URL` for the integration suites).
- Fixture user `019d5e3c…` with: a book of published chapters (封神演義), a knowledge project, BYOK models registered (a **non-reasoning chat** judge/translator model, an embedding model, optionally a reranker). For free local runs: LM Studio (`host.docker.internal:1234`) + a JSON-clean instruct model (e.g. qwen2.5-7b-instruct) for any judge step.
- Embedding-benchmark gate: a `passed=true` row in `project_embedding_benchmark_runs` for the project's embedding model (or run the golden-set benchmark).
- `STUCK_DISPATCH_TIMEOUT_S` lowered (e.g. 20) for reconcile scenarios.

---

## A. Happy path (full pipeline)

**A1 [NOW] Create → estimate → launch → complete (small range).**
1. `POST /v1/campaigns/estimate` (book + small range + models) → 200; cost band + time band + per-stage table (lm_studio stages = $0).
2. `POST /v1/campaigns` (same + budget) → 201, status `created`, `campaign_chapters` seeded all `pending`.
3. `POST /v1/campaigns/{id}/start` → `running`; `started_at` set.
4. Driver dispatches knowledge → `knowledge.chapter_extracted` → projection `knowledge=done`.
5. (phase_barrier) once all knowledge settled, translation dispatches → `chapter.translated` → `translation=done`.
6. `translation.quality` → `eval=done` (+ `eval_fidelity_score` set **[MODEL]**).
7. All stages settled → status `completed`, `finished_at` set.
**Expect:** GET `/{id}` chapters all done; `/{id}/progress` per-stage done==total; spent_usd reflects usage (≥$0).

**A2 [NOW] Estimate-only (no launch)** — estimate returns a band; no campaign row created.

**A3 [NOW ✅G1] Completion report** — `GET /{id}/report` after A1 → `CampaignReport{status, started_at, finished_at, duration_seconds, total_chapters, stages{knowledge,translation,eval}, spent_usd, budget_usd, est_usd_low, est_usd_high, error_groups[]}`. With no failures `error_groups==[]`. FE "Review draft" CTA resolves to the book's reader/review route. (Evidence: campaigns.py:426 + cause.py:31 + CampaignReport.tsx.)

---

## B. Lifecycle controls

**B1 [NOW] Pause → Resume.** Running → `POST /pause` → `paused` (new dispatch stops; in-flight drains, projection still advances). `POST /start` → `running` (resumes dispatch). No re-spend on already-done chapters (idempotency skip-gate).

**B2 [NOW] Cancel (running).** `POST /cancel` → `cancelling`; driver propagates cancel to in-flight downstream jobs, terminalizes `dispatched` stages → `cancelled`, `finished_at` set. No new dispatch.

**B3 [NOW] Cancel (created/paused).** Immediate → `cancelled`.

**B4 [NOW] Update budget.** `PATCH /{id}` `{budget_usd}` → raises/lowers cap; does NOT auto-resume; lowering below spent does not retro-pause a running campaign (next accumulate may pause).

**B5 [NOW] Pause guard.** `POST /pause` on a non-running campaign → 409 (only running can pause).

---

## C. Budget cap (S4d) — VERIFIED 2026-06-10

**C1 [NOW] Accumulate + auto-pause.** Running campaign, budget `$B`. Inject/produce usage to `loreweave:events:campaign_usage` summing ≥ `$B` → `spent_usd` accumulates → status `running→paused`, `error_message="budget cap reached"`.

**C2 [NOW] Dedup.** Re-deliver a counted `request_id` → no double-count (`campaign_usage_seen` PK) → spent unchanged.

**C3 [NOW] Over-budget resume guard (D-S4D-RESUME-GUARD).** Paused at cap, `spent ≥ budget` → `POST /start` → 409 `CAMPAIGN_OVER_BUDGET`. Raise budget via `PATCH` so `budget > spent` → `POST /start` → `running`.

**C4 [NOW ✅polish] Switch-to-local-model resume.** Paused campaign → `PATCH /{id}` `{translation_model_source, translation_model_ref}` (a $0 local model) → 200 (allowed in `created/paused`) → `POST /start` → `running`. Remaining chapters use the new model; completed chapters keep their version. (campaigns.py:271 gate + SwitchModelControl.tsx.)

**C5 [NOW ✅polish] Switch verifier / eval-judge model.** Same PATCH supports all 4 LLM roles (translation/knowledge/verifier/eval_judge). `PATCH` a model field on a **running/terminal** campaign → 409 `CAMPAIGN_MODELS_LOCKED` (campaigns.py:298). Empty PATCH body → 400 `CAMPAIGN_PATCH_EMPTY`.

---

## D. Money path (S4a/b/c) — VERIFIED 2026-06-10

**D1 [NOW] campaign_id threading.** A campaign-dispatched job → `llm_jobs.job_meta.campaign_id` = the campaign id.
**D2 [NOW] Usage relay.** Job completion → `usage_outbox.campaign_id` set + `published_at` stamped → event on `loreweave:events:campaign_usage`.
**D3 [NOW] Usage audit.** `loreweave:events:usage` → usage-billing `usage_logs` row (`billing_decision='recorded'`, purpose, cost). (Bug fixed this session: constraint widened.)

---

## E. Idempotency & resume

**E1 [NOW] Re-run an already-translated chapter → skip (no re-spend).** Re-dispatch translation for a fresh-completed chapter → translation-service skip-gate excludes it → `chapter.translation_skipped` → projection `translation=done`, 0 new provider spend.
**E2 [NOW] Stale (glossary-changed) re-translation** → not-skipped → re-translated → new version. Campaign job auto-promotes to active (D-CAMPAIGN-AUTONOMOUS-PUBLISH) when `unresolved_high_count=0`.
**E3 [NOW] Crash-resume.** Kill+restart campaign-service mid-run → driver re-derives all state from `campaign_chapters` (stateless) → continues; no double-dispatch (claim-first + dispatched-guard).

---

## F. Failure & recovery phases (EDGE)

**F1 [NOW] Lost completion event → self-heal (reconcile-by-truth).** Force a stuck `dispatched` row (drop the completion event) with `updated_at` past `STUCK_DISPATCH_TIMEOUT_S`:
- knowledge stuck + project extraction `complete` → reconcile marks `done`.
- translation stuck + job terminal & no fresh version → reset to `failed` (re-dispatch); + job alive → leave; + fresh version exists → `done`.
- (VERIFIED 2026-06-10.)

**F2 [HARNESS] Provider 429 / transient → backoff.** Induce repeated 429 → translation worker routes retries through `translation.chapters.retry.{1000,2000,4000}` rungs (1/2/4s) → eventual success or DLQ after budget. (Rungs declared; timing needs load/fault injection.)

**F3 [HARNESS] Circuit-breaker open → auto-pause.** Induce ≥`BREAKER_THRESHOLD` transient provider failures for a kind → breaker opens → `LLM_CIRCUIT_OPEN` → `knowledge.chapter_failed`/`chapter.translation_failed` with that code → campaign auto-pauses. After `BREAKER_COOLDOWN_S`, half-open → recover.

**F4 [NOW] Empty body / dead-letter.** A chapter with empty source body → extraction/translation marks it skipped/dead-letter (no infinite retry); projection settles it (not a perpetual failure).

**F5 [NOW] 0-output (model) failure.** Provider returns empty content → chapter `failed` (retryable up to `max_attempts`), then settled-failed.

**F6 [STALE] Stale-image false-green.** A service image predating the integration → missing route/emit (404 / stuck stage). Mitigation: rebuild touched services first. (Hit twice historically — knowledge 404, worker-ai missing emit.)

**F7 [NOW] Attempt exhaustion.** A stage failing `max_attempts` times → terminally `failed`; campaign can still `complete` with that chapter failed (gating treats exhausted-failed as settled).

**F8 [NOW ✅G2] User re-run failed.** After exhaustion, `POST /{id}/rerun-failed {chapter_ids?}` (omit body = all settled-failed) → reset those failed stages to `pending` + attempts 0 + clear `last_error` → campaign re-arms `running` → driver re-dispatches → succeed/settle. **Refuse on `cancelled`/`cancelling`**; over-budget guard applies (re-run dispatches → spends). Skip-gate prevents re-spend on already-completed stages. (campaigns.py:504 + reset_failed_stages repositories.py:789.)

---

## G. Gating modes

**G1 [NOW] phase_barrier (default).** Translation for ANY chapter holds until EVERY chapter's knowledge is settled (done/skipped/exhausted). Verify: with one knowledge chapter still pending, no translation dispatches.
**G2 [NOW] cold_start.** A chapter's translation dispatches as soon as ITS knowledge is terminal-success, regardless of other chapters. Verify: chapter A knowledge done → A translation dispatches while chapter B knowledge still pending.
**G3 [NOW] Wizard selection.** The wizard "Translation pacing" selector sends `gating_mode` (D-S5C-GATING); default phase_barrier.

---

## H. HA / concurrency (EDGE) — VERIFIED 2026-06-10

**H1 [NOW] Two-driver disjoint claim.** Two driver_ids claim concurrently → `FOR UPDATE SKIP LOCKED` + lease → disjoint sets; a peer skips a live foreign lease; claims after lease expiry; owner renews its own lease each tick. (VERIFIED via SQL replay.)
**H2 [HARNESS] Two replicas, full run.** Two campaign-service replicas on one campaign → no double-dispatch (claim-first + lease). (Single-replica safe today; D-CAMPAIGN-DRIVER-SINGLETON note.)
**H3 [NOW] Concurrent campaigns, same book/chapter/language.** Both advance on the shared `chapter.translated` (convergent, language-guarded); a reconcile mark-done is cross-campaign; reset is per-campaign.

---

## I. Ownership / multi-tenant (EDGE)

**I1 [NOW] Foreign book → 403.** Create with a book the user doesn't own → `CAMPAIGN_FORBIDDEN`.
**I2 [NOW] Foreign/absent project → 400.** Create with a knowledge_project_id not owned → `CAMPAIGN_PROJECT_NOT_FOUND` (D-CAMPAIGN-KPROJECT-OWNERSHIP, early 400 — was fail-closed at dispatch).
**I3 [NOW] Embedding conflict.** Embedding model differs from the project's current AND the project has a graph, `confirm_embedding_change=false` → 409 `CAMPAIGN_EMBEDDING_CONFLICT`. Resubmit with confirm → graph deleted + applied.
**I4 [NOW] Cost owner.** Every provider job from the campaign bills the **owner's** BYOK provider (campaign_id → job_meta → usage). Cross-tenant tag isolation (contextvar) — no leak to non-campaign jobs.

---

## J. Scope / data edges (EDGE)

**J1 [NOW] Empty range (no published chapters in range) → 400 `CAMPAIGN_NO_CHAPTERS`** at create.
**J2 [NOW] No knowledge_project_id → 400 `CAMPAIGN_NO_KNOWLEDGE_PROJECT`.**
**J3 [NOW] All-skipped re-run** (whole range already translated) → all `chapter.translation_skipped` → campaign converges to `completed` with 0 new spend.
**J4 [NOW] Whole-book (blank range)** → enumerates all published chapters.
**J5 [NOW] Invalid gating_mode → 422** (payload validation).
**J6 [NOW] Budget ≤ 0 or ≥ 1e8 → 422** (payload validation).
**J7 [NOW ✅polish] >200 chapters paging.** `GET /{id}/chapters?status=all&limit=200&offset=0` → `{rows[≤200], total}`; `offset=200` → the next page; `limit` clamped 1–500. `status=attention|inflight|all` filters. Detail `GET /{id}` no longer embeds chapters. (campaigns.py:339.)

---

## K. Eval-judge tail (S5b-eval)

**K1 [MODEL] eval_fidelity_score populated.** Campaign with an eval-judge model → V3 translation emits `translation.quality` (carrying the judge model + texts) → learning runs the M7d-2 fidelity judge → `translation.eval_judged` → `campaign_chapters.eval_fidelity_score` set. **Blocked on a JSON-clean judge model** (LM-Studio gemma/qwen3.5 stream empty content — `D-LEARNING-JUDGE-EMPTY-CONTENT`); the wiring is otherwise validated.
**K2 [NOW] eval observed-not-dispatched.** eval stage advances on `translation.quality` (never directly dispatched); a campaign without a judge still completes (eval=done from the quality event; fidelity null).

---

## L. Monitor / UX (presentation)

**L1 [NOW] Live polling.** Running campaign → progress polls 6s, detail 15s; stops on terminal.
**L2 [NOW] Stage progress + spent/budget bar + status badge** reflect live state; chapter table filters failed+in-progress, "Show all" toggle.
**L3 [NOW ✅G3] Elapsed / ETA / throughput / in-flight stats** on the monitor (pure `deriveRunStats(progress, startedAt, now)` — runStats.ts:19; unit-tested runStats.test.ts).
**L4 [NOW ✅G1/G4] Terminal campaign shows a report + "Review draft" CTA** (CampaignReport.tsx rendered on `completed|failed|cancelled`).
**L5 [NOW ✅polish] Campaigns list progress bar + paused banner + inline actions** (CampaignsList.tsx + ingest row StageProgress.tsx:19).
**L6 [NOW ✅polish] Recent activity log.** `GET /{id}/activity?limit&before_id` → recent-first keyset page `{rows[], next_before}`; each `campaign_chapters` stage UPDATE appends a row via the AFTER-UPDATE trigger (migrate.py:166). FE `ActivityLog` renders relative times (relTime). Paging via `before_id`.
**L7 [NOW ✅polish] In-flight "processing" panel.** `GET /{id}/chapters?status=inflight` → only rows with a stage currently `dispatched`; FE `InFlightPanel` lists chapter+stage with "+N more" overflow (inFlightStages).

---

## Coverage status summary (updated 2026-06-11)
- **Verified live (2026-06-10):** A1(core pipeline, prior), C1–C3, D1–D3, F1, H1, plus all unit/integration suites.
- **Scripted in `campaign-factory.spec.ts` (API-level, deterministic — run on a stack-up):** A2, A3, B1–B5, C3, C4/C5, F8, I1–I4, J1–J6, J7, L6, L7. These need no model (they assert route contracts, lifecycle transitions, gating/ownership errors, report/activity/paging shapes).
- **Runnable now, not yet scripted (UI / model-coupled):** E1–E3, F4/F5/F7, G1–G3, H3, K2, L1–L5.
- **Blocked (tracked):** F2/F3/H2 [HARNESS], K1 [MODEL], F6 [STALE-discipline].
- **✅ All prior gap-fix dependencies cleared** — A3/L4 (G1), F8 (G2), L3 (G3), C4/C5/J7/L5/L6/L7 (polish). Evidence: `docs/reviews/2026-06-11-auto-draft-factory-draft-vs-impl-RECHECK.md`.
