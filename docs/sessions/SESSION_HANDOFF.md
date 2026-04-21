# Session Handoff — Session 50 (K19b opened; K19b.1 + K19b.4 FS shipped)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-21 (session 50)
> **HEAD:** (pending K19b.1 commit) (K19a.8 @ `2061b2d`; K19a.7 @ `2cbcc7c` + `c6ee80a`; K19a.6 @ `2226283` + `7cf394f`; K19a.5 @ `3148751` + `1156193`)
> **Branch:** `main` (ahead of origin by sessions 38–50 commits — user pushes manually)

## Session 50 — K19b cluster opened (K19b.1 + K19b.4 FS batched [L])

```
Track 3 K19b progress (session 50)

Cycle 1  K19b.1 + K19b.4    User-scoped jobs endpoint + hook + JobProgressBar    (pending commit)
                            BE: list_all_for_user repo + GET /v1/knowledge/extraction/jobs
                            FE: listAllJobs, useExtractionJobs hook (2s/10s dual-poll),
                                JobProgressBar (6 statuses, indeterminate, Intl USD format)

Remaining K19b tasks: K19b.2 JobsTab, K19b.3 JobDetailPanel, K19b.5 retry, K19b.6 CostSummary, K19b.7 i18n
```

**Test deltas at session 50 end:**
- Frontend knowledge: **125 pass** (was 112 at session 49 end; +13 — 9 new hook+component + 4 added during review-impl fixes)
- Backend (new this session): +6 router unit tests (test_extraction_job_status.py 7→13) + 5 repo integration tests (test_extraction_jobs_repo.py 23→28)
- BE unit full: 1171 pass (was 1154; +17 ambient)
- /review-impl caught 5 LOW findings, all fixed in-cycle (L1 job_id tiebreaker, L2 per-group errors, L3 user_id queryKey, L4 Intl USD format, L5 rich aria-label)
- Review-code caught 1 MED fixed pre-review-impl (`LIST_ALL_MAX_LIMIT` shared constant between router + repo)

**What shipped (11 files):**
- BE: `ExtractionJobsRepo.list_all_for_user(user_id, *, status_group, limit=50)` in `extraction_jobs.py` + new `GET /v1/knowledge/extraction/jobs?status_group=active|history&limit=50` on `jobs_router` in `extraction.py`. Shared `LIST_ALL_MAX_LIMIT = 200` module constant keeps router-level `Query(le=...)` and repo-level `min(limit, ...)` clamp in lock-step.
- FE: `knowledgeApi.listAllJobs()` in `api.ts`; new `hooks/useExtractionJobs.ts` (dual `useQuery`, user_id-scoped queryKey, per-group error fields); new `components/JobProgressBar.tsx` (Intl.NumberFormat USD, status-coloured bar, indeterminate shimmer, progress-aware aria-label).
- Tests: 5 new BE repo integration + 6 new BE router unit + 4 new FE hook + 9 new FE component.

### What K19b.2 can now assume

- `useExtractionJobs()` returns `{ active, history, isLoading, error, activeError, historyError }`. Consuming `ExtractionJobsTab` can:
  1. Import from `@/features/knowledge/hooks/useExtractionJobs`.
  2. Filter `active` into Running vs Paused sub-sections by `status === 'running' | 'paused' | 'pending'`.
  3. Filter `history` into Complete vs Failed vs Cancelled by `status === 'complete' | 'failed' | 'cancelled'`.
  4. Render `<JobProgressBar ... />` per row in each section (status-aware visuals built in).
  5. Surface `activeError` as a banner above the Running/Paused sections; `historyError` above Complete/Failed/Cancelled — each section can keep rendering last-good rows while the error persists.
- Polling cadence is handled inside the hook (2s active, 10s history, not-in-background via React Query default). Tab component has no timer logic to own.
- Brief transition gap (≤10s) when a job flips `running → complete` between the 2s active poll and the 10s history poll — job temporarily absent from both lists. Acceptable per REVIEW-DESIGN; K19b.2 can choose to mask by invalidating the history queryKey from a `useProjectState`-style local action, but not required for correctness.
- `JobProgressBar` has no i18n today (scope carve-out for K19b.7). The aria-label carries English `"Job {status}, N% complete"`. When K19b.7 lands, swap to a t() template passed via a new optional prop (don't let i18n leak into the pure component).

### FS-cycle audit lesson (K19b.1)

The CLARIFY-phase BE audit (per `feedback_fe_draft_html_be_check.md`) caught the user-scoped-list gap before any FE was drafted. Options presented were:
- (a) Reclassify to FS, add new endpoint — chosen
- (b) Expose `list_active` at HTTP layer only, defer history
- (c) Pure-FE N-fanout across `listProjects` + per-project `listExtractionJobs`

Option (a) won because K19b.2's layout sections (Running/Paused/Complete/Failed) map 1:1 to the `status_group` binary, so pushing the filter down to SQL is both cheaper (O(1) query per group) and less code-complex than any FE merging. The option-(c) N-fanout would have worked for a demo but broken at ~10 projects per account. This is exactly the class of call the `feedback_fe_draft_html_be_check.md` rule exists to force before CLARIFY is closed.

### Still deferred after K19b.1

- **D-K19b.1-01** → Track 3 polish: cursor pagination for history once users cross ~150 historical jobs. Current hard cap `limit ≤ 200`. ORDER BY is already deterministic thanks to review-impl L1 tiebreaker.
- **D-K19b.4-01** → K19b.3 (detail panel is its natural home): ETA "time remaining". Either BE ships `progress_rate_items_per_sec` on `ExtractionJob` or FE computes client-side EMA in the hook keyed on job_id.
- **D-K19a.5-03** → K19b.6: monthly budget remaining in BuildGraphDialog. Needs `/v1/me/usage/monthly-remaining`.
- **D-K19a.5-04 + D-K16.2-02b** → Track 3 (paired): chapter_range picker + runner-side enforcement.
- **D-K19a.5-06** → Track 3 polish: `glossary_sync` scope option in BuildGraphDialog.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog.
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests for `useProjectState` (supersedes D-K19a.5-05 for action-fire-path coverage).
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
