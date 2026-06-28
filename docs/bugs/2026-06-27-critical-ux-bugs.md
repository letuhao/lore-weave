# Critical UX Bugs — 2026-06-27

Branch: `fix/critical-ux-bugs` (off `origin/main` @ 0cc8ff6c)

Reported by user. These are critical bugs causing bad user experience. We investigate
and fix **one by one**. Each item carries the user's original description verbatim plus a
working section for root-cause + fix notes.

Status legend: `[ ]` open · `[I]` investigating · `[F]` fix in progress · `[x]` done · `[D]` deferred

---

## Theme index (for batching related work)

- **Jobs / progress / monitoring**: 1, 2, 3, 34, 37, 38, 9, 16
- **Parallelism / config GUI**: 4
- **Glossary extraction & merge correctness**: 7, 26, 36, 38, 39, 13
- **Translation glossary**: 8
- **Glossary GUI / paging / kinds / standards**: 6, 21, 22, 25, 31, 33, 35, 40
- **Knowledge Graph (KG)**: 9, 10, 11, 13, 14, 15, 28, 29
- **Timeline**: 10, 12, 15
- **Chat / AI assistant / planner**: 17, 18, 19, 27, 30
- **Auth**: 20
- **Billing / LLM provider tracing**: 24, 32
- **Workspace tabs**: 23

---

## Bugs

### [x] 1. Glossary extraction cannot be stopped; no show/hide toggle
Glossary extraction cannot stop after running. No button to hide or show it again.

> RC: The glossary `ExtractionWizard` is a self-contained modal with its own polling
> (`useExtractionPolling` → `/v1/extraction/jobs/{id}`), disconnected from the unified
> Jobs dashboard (`features/jobs`, which already streams + cancels and lists
> `glossary_extraction` as a kind). During the running ("progress") step the wizard was
> **hard-locked open**: `useExtractionState.canClose = state.step !== 'progress'` → the
> header X was hidden and backdrop-click was a no-op (`ExtractionWizard.tsx`), trapping the
> user behind a modal they couldn't dismiss. The job lived only in local React state, so
> there was also no re-entry to a backgrounded run. (A Cancel button *did* exist in
> `StepProgress`; backend honoring it promptly is bug #34.)
> Fix (FE-only): `canClose = true` always (job continues server-side, tracked in Jobs);
> added a **"Run in background"** button on the progress step + a toast handoff with a
> "View in Jobs" action linking to `/jobs`. Strings added to all 4 locales. Tests: extraction
> suite 9/9 (added a background→Jobs-handoff test asserting toast + navigate), tsc clean.
> Review (/review-impl): the new "reopen + start a 2nd run" path is bounded server-side —
> translation-service admission control caps concurrent extraction jobs per user (429
> `EXTRACT_TOO_MANY_JOBS`, `extraction.py:207`) + a per-book advisory lock; `StepConfirm`
> surfaces the 429 via toast and does not advance. No concurrency-guard change needed.

> NOTE for later bugs found while here: glossary extraction already has a "Parallel LLM
> calls" concurrency input (`StepConfirm.tsx:116`, D-EXTRACTION-BATCH-CONCURRENCY) → relevant
> to #4 (translation glossary lacks it). The LLM-call estimate `llmCalls = chapters *
> ceil(schemaTokens/2000)` (`StepConfirm.tsx:53-59`) is the likely culprit for #36's
> under-prediction. The estimate is shown on confirm but NOT on the running job (→ #37).

### [x] 2. Job detail page cannot monitor realtime job progression
Want to monitor the glossary extraction live but cannot — job detail page has no realtime progression.

> RC: The unified Jobs detail page (`JobMonitor`) IS fully wired for live updates — it overlays
> the jobs-service SSE stream (`useJobLive` + `effectiveJob`) and `JobProgressPanel` renders a
> live bar + %/done-total + throughput/ETA from `job.progress`/`detail_status`. The gap was
> backend: the translation-service extraction worker emitted per-chapter progress only on its
> OWN `publish_event` channel (legacy translation UI), while the unified stream got just the
> single `running` transition + the terminal event via `emit_job_event_safe`. So the detail
> page's progress bar/detail_status sat frozen for the whole run.
> Fix (BE-only, `extraction_worker.py`): added `_emit_unified_progress()` which calls
> `emit_job_event_safe(status='running', progress={done,total}, detail_status='k/N chapters')`
> — invoked once as a pre-loop baseline (accurate on resume) and again after each chapter's
> existing progress write. Each emit carries a fresh `occurred_at`, so the monotonic projection
> applies it (forward-in-time) and the consumer pushes an SSE frame → the detail page advances
> live. Best-effort: a failed emit never disturbs the run; terminal rollup + reconcile sweep
> backstop accuracy. Tests: extraction-worker suite 19/19 (added a unified-progress-emit test);
> job-emit-wiring + jobs suites 43/43. FE needs no change.
> Live-smoke: deferred — full stack (translation-svc + jobs-svc + RabbitMQ/Redis + a real LLM
> extraction) not bootable here. Reuses the proven emit path already used for running/terminal
> on this same job, so cross-service contract risk is low. D-JOBS-EXTRACT-LIVE-PROGRESS-LIVE-SMOKE.
> /review-impl: no HIGH/MED. Verified single sequential progress site (no bypass via the
> within-chapter gather), no consumer reacts to job.running except the SSE notify (no
> notification spam), late running events can't regress a terminal row (monotonic WHERE), and
> the relay→projection→SSE→FE path for `progress` is PRODUCTION-PROVEN by book-service's
> book_import (import.go:519, outbox_test.go) — extraction is just a new producer onto it.

### [x] 3. Job detail missing total cost; token cost not updated until job done
Job detail doesn't show total cost. Current token cost is not updated until the job is done — should update frequently.

> RC: Two gaps in the extraction worker's unified-stream emits. (1) COST was never computed:
> the LLM gateway `usage` carries only tokens (no cost), and unlike the translation worker
> (D-JOBS-P4 `resolve_job_cost_usd`) the extraction worker never priced its tokens — its
> terminal emit passed `tokens_in/out` but no `cost_usd`, so the projection's `cost_usd` stayed
> NULL → the detail "Cost so far" showed "—" forever. (2) TOKENS only rode the terminal event,
> so they appeared only at completion. The FE `JobCostUsagePanel` was already built for live
> updates ("Cost so far"); the gap was purely producer-side.
> Fix (BE-only): `_emit_unified_progress()` (the bug-#2 helper) now also resolves cost via the
> provider-registry oracle from the running token totals and carries `cost_usd` + `tokens_in/out`
> on every per-chapter emit (live). Finalize resolves the final cost, persists it to the new
> `extraction_jobs.cost_usd` column (mirrors `translation_jobs.cost_usd`, idempotent migration),
> and the terminal emit carries it too. Pricing comes ENTIRELY from provider-registry (no
> hardcoded pricing/model). Best-effort: a 0-token baseline skips the HTTP; a registry blip
> shows cost null for that frame and self-corrects next chapter (projection + `effectiveJob`
> both COALESCE cost, so it never flickers to null).
> Tests: extraction-worker 20/20 (added a live-cost/tokens + persisted-cost_usd test).
> Live-smoke: deferred with #2 (D-JOBS-EXTRACT-LIVE-PROGRESS-LIVE-SMOKE) — same stack/path;
> reuses the translation worker's proven `resolve_job_cost_usd` oracle call.
> Follow-up (optional, not blocking): the extraction GET endpoint (`extraction.py`) still returns
> only `cost_estimate`, not the new actual `cost_usd` — the unified Jobs detail page (the bug
> surface) reads the projection so it's fixed; exposing actual cost on the wizard's own results
> is a minor nicety.
> /review-impl (MED, fixed): the first cut re-priced cost EVERY chapter — and pricing is a
> 5s-timeout call to provider-registry inside the chapter loop, so a degraded registry would
> inject up to 5s PER chapter (~+58min on a 700-ch job). Fixed with a throttle (`_COST_REPRICE_EVERY=5`):
> reprice on the first chapter + every 5th + finalize, reuse the last figure between; TOKENS still
> update every chapter. Added a regression test asserting reprices < chapter count. Column drift
> verified safe (GET maps by-name; `SELECT *` ignores the extra key). LOW (accepted): if registry
> is down AT finalize, `extraction_jobs.cost_usd` stays NULL though the projection still has the
> last live cost (GET doesn't expose cost_usd anyway). Tests: extraction-worker 21/21.

### [x] 4. Translation glossary cannot be configured to run parallel; need GUI for parallel workers
Translation glossary cannot be configured to run parallel like the glossary extraction job. May happen in other jobs too. Need a GUI to set parallel workers.

> RC: The glossary-translate worker (`glossary_translate_worker.py`) processed entities strictly
> sequentially (`for ent in items:` — one awaited LLM call each), with no concurrency param at all
> — unlike extraction, which already had `concurrency` (Semaphore+gather over batches) and a
> "Parallel LLM calls" input in its confirm step. So the translation-glossary wizard had no way to
> parallelize, making large glossaries (15000+ entities) painfully slow.
> Fix (FS, mirrors extraction):
>  - Worker: added `_GLOSSARY_TRANSLATE_MAX_CONCURRENCY=16` + reads `concurrency` from the msg
>    (clamped). Refactored the per-entity body into a `_process_entity` coroutine bounded by an
>    `asyncio.Semaphore(concurrency)`, run via `asyncio.gather` per page. Shared counters mutate
>    between awaits only (single-threaded asyncio). Added a per-entity catch-all so one entity's
>    unexpected error fails only that entity (more robust than the original, which aborted the job).
>  - Route: `CreateGlossaryTranslatePayload.concurrency_level` (ge=1, le=64) → published `concurrency`.
>  - FE: ported the "Parallel LLM calls" number input to the glossary-translate StepConfirm; sends
>    `concurrency_level` when >1.
> Tests: glossary-translate-worker 9/9 (added parallel-bounded + default-sequential tests proving
> max-in-flight == cap / == 1); router + structured-output + internal-control + prompt suites 35/35
> all green; FE tsc clean + state suite 6/6.
> Live-smoke: deferred (D-GLOSSARY-TRANSLATE-CONCURRENCY-LIVE-SMOKE) — needs translation-svc +
> glossary-svc + a real LLM. Only the ORCHESTRATION changed (per-entity LLM/apply contracts are
> unchanged); parallelism is unit-proven. "Other jobs": chapter translation already has its own
> P5 coordinator/fairness concurrency; extraction already had this — glossary-translate was the gap.
> Cancellation stays per-page granularity (same as before; finer interrupt = bug #34).
> /review-impl (MED, fixed): the first cut wrote per-entity progress to the DB INSIDE the
> semaphore — each `pool.acquire()` while holding a slot. On a fast/cache-hit burst, up to
> `concurrency`(16) entities would grab connections from the SHARED `max_size=10` pool
> (database.py:9), starving the rest of the service (other jobs + HTTP handlers) — a
> multi-tenancy hazard extraction doesn't have (it writes once per chapter, sequentially).
> Fixed: write the page's accumulated progress in ONE DB write after the gather; per-entity
> live progress stays on the broker `publish_event` channel (no pool). LOW (fixed): added a
> route test asserting `concurrency_level` rides the published message as `concurrency`.
> LOW (accepted, matches extraction): route allows le=64 but the worker caps at 16 (FE caps at
> 16, so the API never receives >16). Verified safe: atomic counter mutation (single-threaded
> asyncio), `except Exception` doesn't swallow CancelledError, gather never orphans a task
> (catch-all), failed entities aren't retried (same as original). Tests: worker 9/9 + router 8/8.

### [x] 6. Glossary page should allow 1000 entities per page
Need to activate glossary but have >15000 entities — current paging makes this really annoying. Want 1000 entities per page.

> RC: Two-part cap. (a) FE page-size `<select>` only offered `[10,20,50,100,200]`
> (`EntityListBrowser.tsx`). (b) The glossary-service list handler clamped `limit` to `<=200`
> (`entity_handler.go:723`) AND silently fell back to the default 50 for anything larger — so
> even hand-editing the URL to limit=1000 gave 50, not 1000.
> Fix (FS): FE options → `[10,20,50,100,200,500,1000]`; BE cap `v<=200` → `v<=1000`. The FE
> already passes `pageSize` straight through as `limit` (no client clamp); verified no test
> asserted either old value. tsc clean, glossary-service builds, EntityListBrowser 4/4.
> Live-smoke: low-risk permissive bound widening (the FE already sent `limit`; this just allows
> larger values through the generic /v1/glossary passthrough) — not separately smoked.

### [I] 7. Glossary extraction forgets to update attributes for frequent characters (merge bug)
Extraction almost forgets to update some attributes for frequent characters. Seems like the description is only extracted/set the first time. Need to investigate the current merge method. Suspect data already updates in the DB or a glossary version but is never reflected to the **current active version** shown on the GUI. (User will give evidence.)

> RC (investigated): the `fill_if_empty` merge strategy — the default for identity/descriptive text fields (`seedMergeStrategy`, `glossary-service/internal/api/extraction_handler.go` ~1128-1146) — locks in the FIRST extracted value. On re-extraction `mergeExtractedEntity` (~1438-1463) sees `existingValue != ""` and SKIPS with `skip_reason="fill_occupied"`. A skipped write fires no event, so the projection/revision consumer records no change and the GUI keeps the stale value. There is NO separate "active version" model — the current EAV row IS the active view; the update simply never lands.
> Fix (proposed): switch the default merge strategy for descriptive fields (description/detail) from `fill_if_empty` to `overwrite` (or the new "rewrite" mode of #26); surface skip reasons in the FE so a skipped update is visible.

### [x] 8. Translation glossary usually fails (output structure bug; no chunking/budget)
Translation glossary usually fails — maybe an output-structure bug. Happens with translation glossaries that exceed ~4000 output tokens. Suspect the token limit cuts off the model mid-generation. Do we calculate a budget for this job? Models have large context windows. The glossary has so much info but we don't do a **structured chunk** — putting everything into translation without a plan is bad.

> RC (investigated): the glossary-translate worker sets a HARDCODED `max_tokens=4096` per entity (`translation-service/app/workers/glossary_translate_worker.py` ~202), disconnected from glossary size. `estimate_glossary_translate_cost` computes an output estimate but the worker IGNORES it. A large / many-attribute entity exceeds 4096 output tokens → the structured JSON is truncated mid-output → `parse_translation_response` fails → entity marked failed. No chunking/budget.
> Fix (proposed): derive `max_tokens` from the per-entity output estimate × a safety margin (and/or chunk attributes across calls); surface a real output budget from the estimator.
> Fix: DONE — new `entity_output_budget(attributes)` (`glossary_translate_prompt.py`) mirrors the REAL payload (each attribute's actual `original_value` × a 3× CJK→Latin expansion + per-key JSON overhead), replacing the flat `max_tokens=4096` in the worker (`glossary_translate_worker.py` ~206). Clamped to `[4096 floor, env ceiling GLOSSARY_TRANSLATE_MAX_OUTPUT_TOKENS=32768]` — the floor keeps the old default for small entities (no regression), the budget scales above it so a long-description entity is no longer truncated. 9 tests (5 budget unit incl. CJK-expands-more + floor/ceiling clamps, 2 worker-wiring incl. >4096 large + ==4096 small back-compat). Per-attribute **chunking across calls** for a pathologically huge single entity stays #26's scope. Live e2e (lm_studio + real large-entity job) deferred → **D-GLOSSARY-TRANSLATE-BUDGET-LIVE-SMOKE**.

### [x] 9. Build-KG progression shows "1/100" — meaning unclear
Built KG from the first 700 chapters (700+ chapters, 15000+ glossary entries). Progress shows "1/100" — what does that mean?

> RC (investigated): KG-build progress is `items_processed / items_total` where items_total = chapters+chat_turns+glossary_entities estimated at create (`knowledge-service/.../extraction.py` ~283-330). But `StartJobRequest.items_total` (~190) is an OPTIONAL caller-supplied int not validated against actual counts — a placeholder 100 gets stored and shown. The FE label also doesn't say what an "item" is.
> Fix (proposed): compute items_total server-side (drop/ignore the client field); clarify the FE i18n label ("extraction window X/Y — chapters/chat/glossary items").
> Fix: DONE — new shared `_count_scope_items()` ([extraction.py](../../services/knowledge-service/app/routers/public/extraction.py)) returns the real per-scope counts (chapters published-gated + pending chat turns + glossary entities), reused by BOTH the cost **estimate** AND the job **create** paths (`start` + `rebuild`), so the stored `items_total` is the true denominator and can never diverge from the preview. `StartJobRequest.items_total` is now **deprecated/ignored** (kept on the schema for back-compat, value discarded) — the "1/100" placeholder is gone. Best-effort: a transient count failure stores NULL (FE indeterminate bar) instead of blocking the job start or persisting a wrong number; the count runs OUTSIDE the tx (H1). Bonus: a correct `items_total` also tightens the bug-#37 `estimated_llm_calls` budget. FE i18n label clarified ×4 — "{{processed}} / {{total}} items **(chapters + chat + glossary)**". **VERIFY:** lifecycle test + 2 new (server-compute ignores a client `99999` → stores 345; best-effort NULL on glossary-count failure) + 25 estimate/caller-pays tests green; 4 locale JSON valid. Live full-stack smoke deferred → **D-KG-ITEMS-TOTAL-LIVE-SMOKE**.

### [x] 10. Timeline events still in English despite multilingual KG; entities untranslated
Timeline shows English: "Chi Yao kills her fiancé, Zhang Ruochen." But the book origin is `zh`. We were supposed to have multilingual KG support. Also the English translation was never made — "Chi Yao" and "Zhang Ruochen" are unknown entities (nobody knows them).

> RC (VERIFIED on live data — project `019effe4…`, book 万古神帝): Neo4j `:Event` nodes store **English summaries** ("Chi Yao kills her fiancé, Zhang Ruochen.") while `participants` stay zh (`["张若尘","池瑶"]`). The FE multilingual path is ALREADY complete (`TimelineTab`→`useTimeline`→`listTimeline` all pass `language`; M1-M3 implemented) — the agent's "FE drops language" was WRONG. The real cause: the event-extraction prompt's INSTRUCTION said "keep summary in the original script", but its **only few-shot example was English** (English TEXT→English summary). Few-shot dominates instruction → the model copies participant NAMES verbatim (zh) but GENERATES the summary in English. The `event_text_translations` cache then holds en (308) + vi (14) and NO zh — the Chinese original was never the stored source.
> Fix: DONE (`03042965`, prompt-only) — strengthened the instruction (GENERATED summary/name must match TEXT's language; never translate/romanise) + added a Chinese few-shot example. Fixes FUTURE extractions; existing books need **re-extraction** to replace the English summaries → D-KG-EVENT-LANG-REEXTRACT (user-driven, token cost). Prompt change should be eval-validated. **Lesson:** [[feedback_verify_explore_rootcause_before_fixing]] — verified the agent's FE hypothesis was wrong before touching the FE.

### [x] 11. KG entities have no description/information (only nodes + edges)
Entities in the KG have no description or information — the GUI only shows nodes and edge relationships. Is this our design or did we implement the KG standard wrong? Unclear on the difference between KG and glossary, but an entity with only a name and relationships — is that correct?

> RC (VERIFIED): the knowledge-service Neo4j `Entity` model carries NO description/summary field, and no LLM pass generates one; the `summaries` target produces project-level summaries, not per-entity. So the KG entity genuinely has only name/kind/aliases/edges. BUT a canonical KG entity anchored to a glossary entity (`glossary_entity_id`) has access to that entry's authored `short_description` — which the glossary entity GET already returns (`entity_handler.go:106`), though the FE `GlossaryEntity` type **omitted the field** (drift) and `EntityDetailPanel` only used the anchor for pin/unpin, never to show prose.
> **FIXED (interim, FE-only):** added `short_description` to the FE glossary type (fixing the drift); new `useAnchoredGlossaryEntity` hook fetches the anchored glossary entry; `EntityDetailPanel` renders a **Description** section (from the linked glossary entry) when present. No BE change (the data was already served). Tests: EntityDetailPanel +2 (renders when present / omitted when absent); knowledge+glossary 802/802; tsc clean; +`entities.detail.description`/`descriptionSource` ×4 locales.
> **Deferred (full version):** a native KG per-entity description (model field + gated LLM pass) for UNanchored discovered entities → D-KG-ENTITY-NATIVE-DESCRIPTION. The interim covers anchored/canonical entities (the ones with authored prose).

### [x] 12. Timeline GUI is low quality; browsers across platform are scattered
Timeline GUI is bad quality — not a rich browser mode like other GUIs (especially glossary). Browsers across the platform are scattered and annoying. Want consistency.

> RC (CORRECTED after reading the code): the timeline is NOT a thin MVP — `TimelineTab` already
> surfaces project filter, narrative/chronological sort + direction, entity filter, chronological +
> ISO-date ranges, pagination, expandable rows; `TimelineEventRow` already shows order, importance,
> localized title, chapter, participant chips (+ summary/all-participants on expand). The real gaps
> (user picked all 4 aspects): (1) no shared browser SHELL across timeline/entities/evidence, (2)
> in-story `time_cue` was only in the expanded detail, (3) NO text search — the BE `timeline.py`
> endpoint (a Neo4j Cypher query) has no `q` param, so search needs a BE change, (4) polish/density.
> **L overhaul — plan: [docs/plans/2026-06-28-timeline-browser-overhaul.md]. Part 1 SHIPPED:**
> surfaced `time_cue` (localized + source-marker) on the COLLAPSED row so the list reads as a
> chronology at a glance (#2). +1 test (chip shows only where present); TimelineTab 16/16; tsc clean;
> +`timeline.row.timeLabel` ×4.
> **Part 2 SHIPPED — text search (#3):** added a `q` param to the timeline endpoint + the
> `list_events_filtered` Cypher (`AND ($q IS NULL OR toLower(coalesce(e.title/summary,'')) CONTAINS
> toLower($q))` — parameterized, no injection; matches SOURCE text, deterministic regardless of
> reader language) + a debounced search box in `TimelineTab` (resets offset; `q` added to the
> `useTimeline` queryKey so it refetches). **Live smoke:** count + page Cypher executed against the
> dev Neo4j with `q="duel"` (valid). +1 FE test (q forwarded + clear empties input); TimelineTab
> 29/29; tsc clean; py_compile clean; +`timeline.search.*` ×4.
> **Part 3 SHIPPED (bounded) — polish/consistency (#4/#1):** added a **page-size control**
> (10/25/50/100, default 50) to the timeline pagination, matching the glossary entity browser.
> +1 FE test (page size → limit, offset reset); TimelineTab 18/18; tsc clean; +`timeline.pagination.pageSize` ×4.
> **DONE for the user-visible asks** (time_cue rows + text search + page-size/polish). **Deferred
> (the heavy structural piece):** extracting a single shared `BrowserShell` and porting timeline +
> entities + evidence onto it is a genuine L refactor with regression surface across 3 browsers —
> not rushed here → **D-KG-SHARED-BROWSER-SHELL** (full cross-browser consistency).

### [D] 13. Glossary extraction also rebuilds KG (should be decoupled)
Glossary extraction seems to also rebuild the KG. When building glossary, the KG also updates. Want to build glossary **first**, then build KG **on demand**. We already have a Campaign GUI, but I used glossary extraction in the **workspace**, not in a campaign. Investigate.

> RC (VERIFIED — NOT a code coupling; WON'T-FIX): re-confirmed in code (parallel-investigation sweep + manual grep). Glossary extraction writes glossary + emits entity outbox events to **learning-service ONLY**; there is NO listener that auto-triggers a KG build, and the only `rebuild`/`build` paths in glossary-service are the unrelated internal `rebuildItemsCache` (an attribute-value cache, not the KG). KG build fires **solely** from explicit user actions (`/extraction/start` or the build confirm-card). The decoupling the user wants ALREADY EXISTS in code — the reported coupling is a UI-perception issue from manually triggering both in sequence.
> **Resolution: won't-fix (no defect).** Optional future polish: clearer workspace labels distinguishing "extract glossary" vs "build KG" (folds into the #16/build-UX work). Closed as not-a-defect.

### [x] 14. Rebuild KG destroys old KG (no update path, no confirmation)
Rebuild KG seems to destroy the old KG — had 12000+ entities and it destroyed all to rebuild from scratch. There's supposed to be an **update KG** feature. Very bad design, and it destroys without any warning/confirmation. We should never do that. (AWS-style: require typed confirmation without copy-paste to destroy important data.)

> RC (VERIFIED): `rebuild_extraction` (`knowledge-service/app/routers/public/extraction.py` ~1183-1261) calls `_delete_project_graph` — DETACH DELETE of ALL Entity/Event/Fact/Source for the project (~1013-1033) — UNCONDITIONALLY at ~1234 before starting the new job. Guards exist for active-jobs/missing-neo4j, but there is NO user confirmation and NO incremental update mode; the delete is non-atomic (graph lost if the restart fails — acknowledged in the docstring ~1207-1209).
> Fix: DONE (`bf30eed3`) — BE `?confirm=true` guard returns a destructive-warning preview (live node counts) and deletes nothing without it; FE reusable typed-confirmation (paste blocked) requiring the project name + live count. The incremental `mode: update` (merge instead of delete) is the remaining follow-up → D-KG-UPDATE-MODE.

### [I] 15. Event timeline lacks metadata (chapter/scene/block); needs in-book time detection
Event timeline should carry metadata: chapter, block/scene, etc. — needed to trace events because some novels are non-linear; hard to build a timeline without metadata. Also need to detect the **real in-book time** mentioned in the book — an advanced feature because time in a book is rarely stated.

> RC (investigated): chapter provenance + in-book time ARE already captured — events carry `chapter_id`/`chapter_title`, `event_date_iso` (parsed wall-clock), `time_cue` (free-text narrative hint), and `chronological_order` (for non-linear books) (`knowledge-service/app/db/neo4j_repos/events.py` ~129-151). What's MISSING: block/scene-level provenance (events are extracted per-chapter; intra-chapter position is lost), and the BE date/chronological filters aren't exposed in the FE (same gap as #12).
> Fix (proposed): expose date/chronological filters in the FE (with #12); add `block_index`/scene anchor to the Event model + extraction for scene granularity (larger, schema change); in-book-time detection beyond `event_date_iso`/`time_cue` is an advanced follow-up.

### [x] 16. "Build full" KG option — fact/summary/etc not visible (stopped early)
Chose "build full" for KG but don't see fact, summary, and other parts. Unsure if they build later — stopped at item 4/100 due to the many bugs above, don't want to waste tokens before they're fixed.

> RC (CORRECTED after verification — the prior "no target picker" RC was WRONG): the build dialog **already has** a `TargetPicker` (`BuildGraphDialog.tsx:690`), and it's on **step 1** which is the DEFAULT step (`wizardStep` inits to `1`) — so the user CAN see/select targets up front. The real gap is at RUN time: the running card (`BuildingRunningCard.tsx`) shows only an aggregate `items_processed/items_total` with NO indication of which targets were requested or that passes run in STAGES (entities → relations/events/facts → summaries). So when a user stops at item 4/100, facts/summaries genuinely haven't run yet and nothing tells them they're queued. Also `ExtractionJobSummary` + the BE job-status response do NOT echo the selected `targets` (the `targets` column exists on the job row but isn't surfaced).
> Fix (proposed, ~M cross-layer): surface the job's `targets` in the status response + FE type, and render a staged target checklist + "facts/summaries run after entities" note in the running card. (NOT a target-picker-placement fix.)
> **FIXED (FE-only, right-sized):** added a **build-stages explainer** to `BuildingRunningCard`
> (`Entities → Relations · Events · Facts → Summaries` + a note that later passes run AFTER earlier
> ones, so stopping early skips them). Directly answers the "unsure if facts/summaries build later"
> confusion with **no BE change** (the aggregate counter stays; the staging is now explicit).
> Tests: ProjectStateCard +1; suite 28/28; tsc clean; +`stagesTitle/stages/stagesNote` ×4 locales.
> **Deferred (fuller version):** echo the job's selected `targets` in the status response + per-target
> progress in the running card → D-KG-BUILD-PER-TARGET-PROGRESS (the cross-layer M).

### [x] 17. Cannot open a fresh AI assistant in workspace (old session is huge)
Cannot open a fresh AI assistant in the workspace — the old chat session is too huge.

> RC: Multi-session was fully built (chat-service CRUD + `SessionSidebar`/`NewChatDialog`/`useSessions` on the `/chat` page), but the **embedded/workspace chat** (BookAssistantDock + editor AI panel) auto-binds exactly ONE session per book via `useEmbeddedChatBinding` and exposed NO switcher or new-chat affordance — so once a book's chat grew huge, there was no in-workspace way to start a fresh one. The embedded `ChatEmptyState` "Start new chat" button was also inert (its `setShowNewDialog(true)` was never read by `EmbeddedChat.dialogOpen`).
> Fix: New shared `features/chat/components/SessionSwitcher.tsx` — a compact in-header dropdown (reads everything from `useChatSession`) to switch between this book's chats, archive a stale one, and start a fresh chat. Mounted via a new host-injected `headerSlot` on `ChatView`→`ChatHeader` (page mode unaffected; the static title shows when no slot). `EmbeddedChat` now threads the binding's `projectId` into the switcher's `scopeProjectId` so it lists ONLY this book's sessions — which also prevents the binding from re-patching a foreign session into this book on switch — and folds `showNewDialog` into `dialogOpen` so "New chat" (and the empty-state CTA) open the dialog even with an active session. 7 new unit tests; 185/185 chat tests green; tsc clean.

### [I] 18. Glossary assistant planner loops forever (self-recheck loop)
The glossary-assistant planner usually loops, even with a very strong local model. Seems stuck in a self-recheck loop forever. Investigate what our planner does — does it hand the whole plan to the model? A plan's progress needs multiple pieces of work controllable by logic. Tools like Kiro actively inject important info to control the model's work. (Web search + investigate.)

> RC (investigated): there is NO ReAct re-check loop in the planner/executor CODE — `runPlanner` (`glossary-service/internal/api/action_plan_tools.go` ~122-169) makes one model call + at most one repair round; `sdks/go/loreweave_mcp/execute.go` is a single-pass deterministic executor. The "loops forever" is the CHAT-AGENT loop re-calling `glossary_plan`, governed only by a SOFT skill rule (`chat-service/app/services/glossary_skill.py` ~108-126: "call once" / "MAY re-ask … stop after 2") — no hard stop.
> Fix (proposed): hard-stop in the skill ("MUST NOT call glossary_plan more than once per turn"); drive step progress with logic + injected step-state (the user's Kiro point) rather than handing the whole plan back to the model each turn.
> **P1 SHIPPED (partial):** skill now states the one-card-per-turn HARD rule + "call glossary_plan AT MOST ONCE per turn" + prefer the deterministic `glossary_propose_batch`. Server-side hard-stop enforcement is P2 (run-loop coalesce).

### [I] 19. Hardcoded `google/gemma-4-26b-a4b-qat` planner called after stopping session
A critical bug: `google/gemma-4-26b-a4b-qat` is called even after stopping the glossary planner. It uses the **default** planner, but I already selected another planner in the chat session. Also, after stopping the session the planner MCP should never be called. Changing the default planner in user settings still calls `google/gemma-4-26b-a4b-qat` — suspect it's hardcoded.

> RC (investigated — NOT a hardcoded literal): grep finds NO `gemma-4-26b` literal in Go production code (Python hits are test/eval fixtures only). The planner model resolves via provider-registry `resolvePlannerModel` (`providerregistry_client.go` ~92-130) from the session's `planner_model_ref` (`action_plan_tools.go` ~74-82; injected at `chat-service/.../stream_service.py` ~695-704), falling back to the user's default→chat model. So "gemma after stop / despite a different selection" is likely UPSTREAM: the session `planner_model_ref` isn't being read/sent, session-stop doesn't halt in-flight planner MCP calls, OR the user's default-model fallback itself resolves to gemma.
> Fix (proposed): NEEDS a live capture of the actual `model_ref` sent on a planner call (verify session planner model is threaded); ensure stopping the session aborts in-flight planner MCP calls. Not a hardcoded-model fix.
>
> RC (FULL STATIC TRACE, 2026-06-28 — both paths verified WIRED, no defect found): traced every layer end-to-end. **Session-selected planner:** `SessionSettingsPanel` picker → `patchSession({planner_model_ref})` → gateway **transparent `createProxyMiddleware`** (no typed DTO → cannot drop fields) → chat-service PATCH persists via `model_fields_set` ([sessions.py](../../services/chat-service/app/routers/sessions.py) ~199-217) → `stream_service.py` ~895 reads it → ~707-711 injects it as `model_ref` into `glossary_plan` args when the model didn't pick one → glossary `toolPlan` uses `in.ModelRef` ([action_plan_tools.go](../../services/glossary-service/internal/api/action_plan_tools.go) ~73-83). **Settings default:** `DefaultModelsCard` → `defaultModelsApi.set('planner', id)` → provider-registry `upsertDefaultModel` (validates `capability='planner'`) → `user_default_models` → `internalResolvePlannerModel` reads `capability='planner'` FIRST ([default_models_handler.go](../../services/provider-registry-service/internal/api/default_models_handler.go) ~184-219), else falls back to best tool-calling chat model (UUID-ordered → gemma-4-26b plausibly wins when no planner default is set — matches the MED-6 smoke). **Conclusion:** no hardcoded literal AND no static drop; all 3 symptoms unify into ONE likely runtime cause — the planner call is an **in-flight MCP call** that captured its resolution at turn start, and **stopping the chat turn does not abort the in-flight `glossary_plan` call** (~39s, completes on the model it resolved at start). **This is not a bounded fix** — it's (1) a cross-service CANCELLATION feature (chat-turn abort → cancel the in-flight ai-gateway MCP call → ideally the provider call) and (2) blocked on a live capture to confirm the race. Deferred → **`D-PLANNER-INFLIGHT-ABORT`** (gate reason 2: structural/cross-service; reason 4: blocked on live capture). [[feedback_verify_explore_rootcause_before_fixing]] — static trace disproved the "threading broken" hypothesis.
>
> Partial fix (DONE — /review-impl caught a static gap the trace above missed): the `glossary_plan` tool EXPOSES a `model_ref` arg to the LLM ([action_plan_tools.go](../../services/glossary-service/internal/api/action_plan_tools.go) ~47), and chat-service only injected the session pin when the model OMITTED it (`not args_obj.get("model_ref")`) — so a weak model that fills `model_ref` silently overrode BOTH the user's session selection AND their Settings 'planner' default (glossary resolves the default only when `in.ModelRef` is empty). Choosing the planner is a user/config decision, never the agent's. **Fix** ([stream_service.py](../../services/chat-service/app/services/stream_service.py) ~705): chat-service is now AUTHORITATIVE — a session pin always wins; with no pin, any model-supplied `model_ref` is STRIPPED so the downstream Settings-default→fallback resolver applies. 3 tests (session-pin-injected, session-pin-overrides-model-ref, model-ref-stripped-when-no-pin) + 35 existing stream-tool tests green. This closes the static authority-inversion; the remaining in-flight-abort (likely the primary runtime cause) stays `D-PLANNER-INFLIGHT-ABORT`.

### [x] 20. Active user gets logged out on JWT expiry (loses working data)
User is active but the JWT expires and forces logout. Critical — causes loss of working data.

> RC: The refresh infrastructure fully existed — auth-service `POST /v1/auth/refresh`
> (`handlers.go:180`, rotates the refresh token) and the FE already stored both tokens — but the
> central fetch wrapper's 401 handler (`api.ts`) **never used it**: any 401 wiped `lw_auth` and
> hard-redirected to /login, discarding in-progress work. Access tokens are short-lived, so an
> active user got bounced the moment the token expired.
> Fix (FE-only): on a 401 for an authenticated request, `api.ts` now does a SINGLE-FLIGHT silent
> refresh (the refresh ROTATES server-side, so concurrent 401s must share one in-flight refresh
> or the 2nd reads an already-rotated token → logout), persists the new pair, retries the request
> once, and only force-logs-out if the refresh itself fails. AuthProvider listens for a
> `lw-auth-refreshed` event to sync React state (so consumers send the new token). Auth endpoints
> are excluded (no loop); a `retried` flag bounds it to one retry.
> BUG CAUGHT BY TESTS (real, would ship): the first cut cleared `refreshInFlight` in the IIFE's
> `finally` — but on the synchronous no-refresh-token path the finally runs BEFORE the outer
> `refreshInFlight = p` assignment, leaking a resolved-null promise that permanently short-circuits
> every later refresh (→ instant logout on the next expiry). Fixed with `p.finally(reset)` AFTER
> assignment + an identity guard.
> Tests: api suite (added refresh-and-retry, single-flight, refresh-fails→logout) + auth 7/7;
> tsc clean.
> /review-impl (MED, fixed): multi-tab race — the refresh token ROTATES, so two tabs of the same
> user both 401'ing on expiry would both refresh with the same r0; one wins (rotates r0→r1), the
> other hits a revoked r0 → logout (one of two active tabs loses work). Fixed: before forceLogout,
> re-read localStorage — if the access token changed (another tab refreshed), retry with it instead
> of logging out. Added a `storage`-event listener in AuthProvider so a tab proactively adopts
> another tab's refresh (and cross-tab logout). Tests: +multi-tab-recovery, +retried-401→logout
> (api 13/13). Follow-ups (not blocking): SSE/WebSocket streams carry the token outside apiJson so
> they won't auto-refresh on expiry; no timeout on the refresh fetch (a hung /v1/auth/refresh blocks
> 401'd callers until the browser default fires).

### [x] 21. Custom `romantic_scene` kind in Xianxia Harem genre not wired in GUI
Created `romantic_scene` in a custom Xianxia Harem genre, but the GUI doesn't wire it — can't edit `romantic_scene` kind anymore.

> RC (investigated): no FE UI calls the existing `setUserKindGenres` (`frontend/.../glossary/tieringApi.ts` ~161) / `PUT /v1/glossary/user-kinds/{id}/genres` — a user can create a user-kind but cannot link it to a genre, so it's invisible in any genre context and uneditable. BE CRUD exists; FE wiring is missing.
> **VERIFIED ALREADY-FIXED (not a code change this round):** the original RC was stale. The
> **Standards Library** (`frontend/src/features/standards/`) shipped 2026-06-20 (3 milestones
> `FE-STANDARDS-LIBRARY` — commits `73998267`/`2b5601ef`/`62a9c68a`, all on this branch) and IS
> routed (`/standards/:tab`, sidebar nav, 4-locale i18n). The user-kind↔genre link editor is
> `KindsPanel.tsx` → `KindGenresModal.tsx`, wired to `setUserKindGenres`. So a user CAN create a
> user-kind and link it to genres. Confirmed live: standards suite 20/20 green (not dead code).
> The earlier "no Standards GUI" RC was another Explore-agent miss caught by verifying in-code.

### [x] 22. System/user/book kinds never wired correctly to FE (no edit GUI)
System kind, user, and book are never wired correctly — critical UX bug. Users can't edit them due to lack of GUI. Happens on **Glossary Standards** (no GUI to write genre, kind, attribute), and on the **book** too (no ability to edit/wire them). Seems like BE exists but was never wired to FE.

> RC (VERIFIED): all 3-tier CRUD endpoints exist (`glossary-service/internal/api/server.go`: user-kinds/genres/attributes ~213-300, system-* admin ~273-290 RS256-gated, book ontology ~305-340). FE has the book-tier Manage workspace (`ManageWorkspace.tsx`) + the `tieringApi` client, but there is NO per-user "Standards" GUI to browse/CRUD user kinds/genres/attributes, and no kind↔genre link UI (#21). System tier is intentionally read-only (admin-seed) but has no discoverability surface either.
> **VERIFIED ALREADY-FIXED (Standards) + FIXED HERE (book).** The per-user Standards GUI exists
> (see #21): `StandardsShell` tabs **Genres / Kinds / Attributes**, each a full CRUD panel
> (`GenresPanel`/`KindsPanel`/`AttributesPanel` + `StandardFormModal`/`AttributeFormModal` +
> `TrashDrawer` recycle bin). System tier is surfaced **read-only via "Clone into your tier"**
> (`KindsPanel.tsx:66`) — the correct tenancy pattern (System is admin-seed, users clone, never
> mutate the shared row). The **book** half of the complaint ("no ability to edit/wire them on
> the book") is the same gap as **#25** and is fixed in this commit (book-tier kind↔genre editor
> in `ManageWorkspace`).

### [x] 23. Sharing tab in workspace is redundant with Settings tab
Sharing tab in the workspace is redundant — we already have a Settings tab. Consider merging them or removing the sharing setting in the Settings tab.

> RC: The book SettingsTab had a "Visibility" section (private/unlisted/public radios) that
> wrote via the EXACT same `booksApi.patchSharing` (sharing-service) endpoint as the dedicated
> SharingTab — pure duplication. SharingTab additionally owns the unlisted share-link + token
> rotation + collaborators, so it's the more complete home for sharing.
> Fix (chose "remove sharing setting in setting tab"): deleted the Visibility section from
> SettingsTab + its state/useEffect-sync/isDirty term/handleSave block/discard reset/now-unused
> `Visibility` import. SharingTab is untouched and remains the single place for visibility/sharing
> (no backend path changes — both used the same patchSharing). tsc clean; book-tabs suites 16/16;
> no leftover refs. (Unused `settings.visibility*` i18n keys left in place — harmless.)

### [x] 24. Usage GUI mislabels LLM call kind (background jobs shown as "chat")
The "kind" of LLM call in the Usage GUI is incorrect — almost everything shows as `chat` kind but they're background jobs. Review this parameter when calling the LLM provider.

> RC: The provider-registry `operation` field is **overloaded** — it selects the
> worker's result aggregator AND the cost-estimate path AND the over-budget
> max_tokens-cap salvage AND the usage-billing `purpose` label. Every background-job
> caller (glossary extraction, prose drafting, KG summaries, judges, …) submits
> `operation="chat"` because it parses the chat-shaped result + wants the chat
> aggregator/estimate/salvage — so all of them billed as "chat". (Expanding the
> operation enum would have forced parallel changes in 4 Go branch points + risked
> changing budget-edge behavior.)
> Fix: Decoupled the *billing label* from `operation` via the existing free-form
> `job_meta`. Each background caller now tags `job_meta.usage_purpose` with a
> distinct per-operation label (`glossary_extraction`, `prose_draft`,
> `prose_critic`, `canon_check`, `kg_summary`, `reward_judge`, …). provider-registry
> `FinalizeWithUsageOutbox` overrides ONLY `usage_outbox.operation` (→ billing
> `purpose`) from it (fail-soft, charset-gated against injection); the job's real
> `operation` stays `chat`, so aggregator/estimate/salvage are byte-for-byte
> unchanged. FE: widened `Purpose` to an open string set, data-drove the filter from
> `by_purpose`, family-based color/badge, +19 labels ×4 locales. ~18 callers across
> translation/composition/knowledge/learning. Go test proves the override reaches
> the INSERT op-arg + falls back on malformed. (Cross-service live-smoke deferred →
> D-USAGE-PURPOSE-LIVE-SMOKE.)

### [x] 25. "Adopt genre" is useless (genre never wired to kind + attribute)
Adopt genre is useless because there's nothing to adopt — genre is never wired to kind and attribute.

> RC (VERIFIED): `adoptBookOntology` DOES copy kind↔genre links + attributes into the book tier (`book_adopt_handler.go` ~132-206) — so adopt wires them on the BE. The complaint is post-adopt: `ManageWorkspace.tsx` exposes no UI to add/change kind↔genre links afterward (the `PUT /books/{book_id}/ontology/kinds/{id}/genres` endpoint + the `ont.setKindGenres` hook wrapper exist, but NOTHING called them). **Second BE gap found while here:** `createBookKindCore` (`book_ontology_core.go:100`) inserts the kind but creates **no** `book_kind_genres` link — so a book kind created via the Manage QuickCreate had zero links → invisible in the genre-first drilldown (the book-tier twin of #21's "created a kind, can't find it").
> **FIXED (FE-only; BE already there):**
> 1. **Book kind↔genre editor** — new `BookKindGenresModal.tsx` + a "Linked genres" (chain) action on each kind row in `ManageWorkspace`'s kinds column, wired to `ont.setKindGenres`. Toggles the book's genres as a replace-set. Enforces a **≥1-genre invariant** (Save disabled on an empty set): a kind with no link is unreachable in a genre-first view and can hold no attributes (attrs are per kind×genre), so the invariant guarantees every kind stays reachable under ≥1 genre column. Wiring the link also unblocks attribute creation, covering the "…and attribute" half.
> 2. **Auto-link on create** — creating a book kind in Manage (with a genre selected) now links it to that genre immediately, fixing the create-then-vanish.
> **/review-impl follow-ups (all fixed):** (a) the ≥1-genre invariant is now **load-bearing
> server-side** — `setBookKindGenres` rejects an empty replace-set with 422 (`book_ontology_handler.go`;
> user-tier kinds still allow zero since they're listed flat); (b) added a `ManageWorkspace` test
> guarding the auto-link-on-create + links-action wiring (the headline fix was previously untested);
> (c) ManageWorkspace clears a stale kind/attr drilldown selection when you unlink the kind from the
> genre in view; (d) keyed the modal by kind id.
> Tests: `BookKindGenresModal` (3) + `OntologyColumn` onLinks (2) + `ManageWorkspace` (2) + book
> CRUD empty-set 422 (Go) — full tiering+standards 47/47; glossary-service green; tsc clean;
> +`col.links_kind`/`links.*`/`toast.links_*` ×4 locales.
> **Known minor edge (deferred → D-BOOK-ORPHAN-KIND-RELINK, LOW):** a book kind can still end up
> with zero links and thus invisible in Manage via two narrow paths — (1) created through the *old*
> pre-fix QuickCreate; (2) a transient failure of the link call *after* create succeeds (the toast
> says "Save failed" though the kind exists). New/adopted kinds via the current flow are unaffected;
> a proper fix is BE-atomic create-with-genres. Revisit only if it surfaces.

### [I] 26. Glossary merge needs a "merge/summary/overwrite" mode (dedup + rewrite)
Glossary merge/append lacks an important type — call it merge or summary. A character's description changes each chapter but is almost the same; normal append produces lots of nearly-identical/useless data. Better to have a "merge overwrite" mode: take new raw extracted data, append to old data, and **rewrite a better version** with dedup. (User will give more detail on why.)

> RC (investigated): merge supports only `fill_if_empty` / `overwrite` / `append` (`extraction_handler.go` ~1438-1549). `append` dedups per-item by normalized text, so slightly-different LLM phrasings of the same fact ("a warrior" vs "a skilled warrior") accumulate as near-duplicate list items across chapters/runs. There is no "merge+rewrite/summarize" mode.
> Fix (proposed): add a "merge/summary" strategy — after append, run an LLM pass that rewrites the accumulated raw values into one deduped canonical description (the user's "merge overwrite" request). Larger (new LLM pass + prompt).

### [I] 27. Multiple agent confirm cards — only the first works (later cards expire)
Agent proposes multiple confirm cards but only the first works; later cards expire because confirming the first card invalidates them.

> RC (VERIFIED — user was right, it's NOT time-expiry): each card's `confirm_token` IS unique (`uuid.NewString()`, `action_propose_tools.go:59`) and single-use per `jti` server-side (`consumeToken` `ON CONFLICT (jti)`, `action_confirm.go:48-56`) — so the token isn't the problem. The shared id is the **agent RUN** (`run_id`). A confirm card commits via the write (`POST /actions/confirm`) AND a *resume* — `submitToolResult(run_id, tool_call_id, outcome)` (`useChatMessages.ts:252-262`) wakes the suspended run. N cards in one turn share ONE `run_id`; confirming the first resumes the run and streams a new turn that SUPERSEDES/orphans the sibling cards → they can't be confirmed. The system is DESIGNED for ONE card committing all rows (`ConfirmActionCard.tsx:23` "Apply — never N cards. The single confirm_token commits all rows server-side"). Same root as #29/#30.
> Fix (proposed): make the agent propose ONE batched card (one token committing all rows) — enforce batching in the propose tools/skill, not N cards.

### [x] 28. No way to review KG schema on either book or knowledge GUI
There is no way to review the KG schema on both the book and knowledge GUIs.

> RC (VERIFIED — and the real ask is bigger): the user clarified they "can only command AI to
> set up the schema, cannot view or edit by myself." In-code: every BE schema endpoint exists and
> `useGraphSchema` already wires every mutation (addNodeKind/addEdgeType/deprecateEdgeType/
> addFactType/addVocabValue/patchMeta). The ONLY schema UI mounted was a read view + one
> "deprecate edge" button (`KnowledgeOntologyTab` → Schema); an `AddEdgeTypeForm.tsx` existed but
> was **never mounted** (dead code), and no forms existed for node-kinds/fact-types/vocab. The
> standalone Knowledge GUI (`ProjectDetailShell`) had **no Schema section** at all. Schema model is
> additive + deprecate-edge-only (mirror of the AI's edits).
> **FIXED (L, FE-only — plan [docs/plans/2026-06-28-kg-schema-view-edit.md]):**
> - **Part A — view** (commit `be1cea7b`): a read-only **Schema** section in the Knowledge GUI
>   resolving the effective schema (`useResolvedSchema` → `GET /v1/kg/projects/{id}/schema`,
>   `ProjectSchemaSection` renders `SchemaEditor` readOnly) + an "Edit schema" CTA deep-linking to
>   the book editor (`?view=schema`).
> - **Part B — edit**: `SchemaWorkbench` in the book GUI Schema tab — mounts the previously-dead
>   `AddEdgeTypeForm` + new `AddNodeKindForm`/`AddFactTypeForm`/`AddVocabValueForm` + an
>   `allow_free_edges` toggle, all on the wired `useGraphSchema` mutations (toast-guarded, 403→clear
>   message); deprecate-edge kept. `KnowledgeOntologyTab` honors `?view=schema`.
> Tests: ProjectSchemaSection 4 + SchemaWorkbench 6; knowledge suite 689/689; tsc clean; kgOntology
> +17 keys & knowledge +schemaSection ×4 locales.
> **Known limitations (by API surface, not bugs):** you must **adopt a template first** before
> editing (the editor targets the project's active schema; `_writable_schema_for_caller` gates to
> project scope), and you can add **vocab values** but not create a new **vocab set** (no
> create-set endpoint — still AI-only). → D-KG-SCHEMA-FROM-SCRATCH / D-KG-VOCAB-SET-CREATE-FE.
> **/review-impl → 1 MED fixed:** the schema endpoints (BOTH tree + resolved) return vocab
> **values separately** (`vocab_values`, keyed by set code) while `SchemaEditor` reads **nested**
> `vocab_sets[].values` — so vocab values **never rendered** in either surface (a pre-existing
> latent bug my "view the schema" feature surfaced). Fixed at the `ontologyApi` read boundary
> (`nestVocabValues` on `getSchema` + `getResolvedSchema`) + the FE types now declare
> `vocab_values`. +6 tests (3 boundary-nesting, 1 inspector-renders-values, 2 add-edge/add-fact
> wiring); knowledge suite 695/695; tsc clean. **Accepted LOWs:** `?view=schema` honored only on a
> fresh route mount (the cross-route CTA always remounts, so it works); deprecate toasts the generic
> "Schema updated"; pre-adopt the Knowledge-GUI inspector shows the system-default schema while the
> book editor says "adopt first".

### [I] 29. KG schema lacks batch operations (agent proposes only 1–2 edges, second expires)
KG schema lacks batch work. Told the agent to update the whole KG schema but it doesn't work well — only proposes 1–2 edges, and the second edge always fails (expired/something).

> RC (CORRECTED after verification — the "same root as #27" claim is only PARTLY right): `kg_propose_edge` (`graph_schema_tools.py:1021`) does NOT suspend the run or mint a confirm card — it **parks each edge to the triage INBOX** (`triage_repo.park`) and returns immediately, so N calls all park fine with no run-orphan. So the #27 orphan mechanism does NOT apply to edge *instances*. The bug is about KG **schema edge-TYPES** (the `DESC_SCHEMA_EDIT` confirm-card path used to author the schema — the same surface as #28's editor), where the run-suspend/orphan CAN apply, AND/OR the agent (LLM) simply stops after 1–2 proposals (#30-style "loses track"). Needs a focused trace of the schema-edit confirm-card path before fixing.
> Fix (proposed): EITHER a `kg_schema_propose_batch` tool (mirror `glossary_propose_batch`) for the schema-edit path, OR fold into the #27/#30 P2 server-coalesce. Defer until the schema-edit path is traced (ties to #27/#30 P2, both deferred).

### [I] 30. Batch logic is poor; agent loses track mid-list — planner/executor must be stricter
Batch logic is bad — after the agent lists many kinds, it only batches very few items. The agent gets lost in the middle. Make the planner/executor stricter: the agent should only **propose** and send the proposal to the MCP; the MCP does the whole work instead.

> RC (investigated): batch propose tools cap a single call (e.g. `toolProposeKinds` ≤20 kinds, `action_propose_tools.go` ~203), and the agent calls them in a LOOP emitting many cards — which then hit the #27 run-orphan failure — instead of one batch. The skill permits but doesn't ENFORCE single-proposal batching (`chat-service/app/services/glossary_skill.py` ~108-126 is soft: "call once" / "stop after 2 re-plans"). The agent "loses track mid-list" = the loop, not a planner defect.
> Fix (proposed — matches the user's ask): the agent ONLY proposes; the MCP/executor commits the whole batch deterministically in one confirm card (loop/raise the batch internally, never N cards). Pairs with #27/#29 and the #18 hard-stop.
> **P1 SHIPPED:** new deterministic `glossary_propose_batch` MCP tool — the agent passes ALL ops explicitly; they go through `ValidatePlan` → ONE `execute_plan` card → the existing deterministic executor (no planner LLM). Skill hardened (one-card-per-turn HARD rule + no-loop prohibition). Round-trip DB test green (mint→confirm→N kinds). P2 (server auto-coalesces stray multi-card turns in the chat run loop) still pending — see [docs/plans/2026-06-28-confirm-card-server-coalesce.md](../plans/2026-06-28-confirm-card-server-coalesce.md).

### [x] 31. Glossary GUI can't view `select`-type attributes (combobox empty)
The glossary GUI cannot view attributes with `select` type — the combobox is empty.

> RC (VERIFIED — corrected): the empty combobox is `EntityEditorModal`'s `AttrSelectCard`, which gets `options` from the entity's embedded `attribute_def`. The entity GET (`entity_handler.go` Query 3, ~213-235) built that `attribute_def` from `book_attributes` but **never SELECTed/scanned `ad.options`** → `def.options` empty → empty `<select>`. The struct `attrDefResp.Options` and the FE `AttributeDefinition.options` already existed; only the query dropped it. (The whole create/adopt/book-ontology-read chain DOES carry options — that path was a red herring.)
> Fix: DONE (`26012411`) — add `ad.options` to the entity-GET SELECT + scan into `av.AttributeDef.Options` (mirrors `book_ontology_handler`). go build+vet clean.

### [x] 32. LLM calls not consistently logged to bill service (no request/response tracing)
LLM calls should go through the LLM provider; the provider should store all request/response logs to the bill service. Currently not every call is written to the bill service, and input/output aren't stored — can't trace or analyze LLM calls.

> RC (investigated): provider-registry DOES meter usage → `usage_outbox` → Redis → usage-billing `usage_logs` (token counts + cost). Two gaps: (a) only COMPLETED jobs are metered (`provider-registry-service/internal/jobs/worker.go` ~126 `status=="completed"`) — failed/cancelled produce NO audit row; (b) request/response PAYLOADS are never persisted (no `request_payload`/`response_payload` column anywhere) — so a call can't be traced/reproduced. (The provider-gateway invariant holds — calls route through provider-registry — so coverage is structural, not per-call bypass.)
> Fix (proposed): persist request/response payloads (new columns or a `job_payloads` table) + write audit rows for failed/cancelled jobs (cost 0). Larger; billing-side schema + relay + consumer.
>
> RC (CORRECTED — the billing STORE already existed): usage-billing `writeUsageLog` already persists encrypted `input_payload_ciphertext` + `output_payload_ciphertext` + `request_status` (AES-256-GCM, per-row session key, audited decrypt). The real gaps were pure **plumbing in provider-registry**: (a) `usage_outbox` rows were written ONLY for `status=="completed"` (worker.go ~126) and the relay HARDCODED `request_status:"success"` (usage_relay.go ~134) → failed/cancelled never audited; (b) `UsageOutbox` carried no payload fields → the consumer wrote empty `{}`. `llm_jobs.input`+`result` hold both payloads; `request_id==job_id`. [[feedback_verify_explore_rootcause_before_fixing]] — 4th misdiagnosed RC this session ("no payload column anywhere" was wrong).
> Fix: DONE (user chose full build, payloads capped). Plan [docs/plans/2026-06-28-llm-call-full-logging.md](../plans/2026-06-28-llm-call-full-logging.md). **provider-registry**: migration adds `usage_outbox.request_status/request_payload/response_payload`; `FinalizeWithUsageOutbox` `RETURNING …, input`, emits a row for EVERY terminal status (gate is now `usage != nil`, set by the worker for all statuses — cost 0 / `request_status` distinguishing failed/cancelled; usage_logs is audit-only so the cost SUM is unchanged), attaching the UTF-8-safe-truncated request+response payloads (cap `LLM_USAGE_PAYLOAD_CAP_BYTES`=16384); the relay carries `request_status` from the row + the payloads. **usage-billing**: `parseUsageEvent` reads the payloads → `writeUsageLog` (already encrypts them); `usageLogParams.Input/OutputPayload` widened to `any` (map for /record, string for jobs). Forward-compatible stream (old consumer ignored the new fields). **VERIFY:** provider-registry jobs suite (INSERT 12-col + SELECT 13-col DB-mock, `buildUsageFields` wire-contract incl. failed-status, failed-with-usage emits) + usage-billing api suite (payload+status parse) + full go test/vet green both services. **Deferred `D-32-FULL-LOGGING-LIVE-SMOKE`** (full-stack: real + forced-fail job → usage_outbox → relay → usage_logs payload/status).
> Fix Δ (/review-impl, 2 fixes): **HIGH** — a USER-cancelled job goes through `Cancel` ([repo.go](../../services/provider-registry-service/internal/jobs/repo.go) ~582), NOT the worker's `FinalizeWithUsageOutbox` (which is gated `WHERE status='running'` — already flipped to 'cancelled'), so cancelled calls were STILL unaudited. Fixed: `Cancel` now `RETURNING …, model_source, model_ref, input, result` and emits a cost-0 `request_status='cancelled'` audit row via a shared `insertUsageOutbox` helper (mutually exclusive with the worker emit by the status guards; `usage_logs` dedups on request_id regardless). **MED** — the relay XADDed the SAME fields (incl. PLAINTEXT payloads) to the campaign_usage stream, but the campaign spend consumer reads only cost/ids → needless plaintext footprint; `campaignFields` now strips the payloads from the campaign copy. +3 tests (Cancel-emits-outbox, campaignFields-strips, drain-campaign-stripped).

### [x] 33. Platform lacks kind description (not attribute) — model extracts wrong kind
The platform lacks a **kind description** (distinct from attribute), so the model doesn't understand and extracts the wrong kind.

> RC (VERIFIED): the kind `description` column EXISTS in schema/domain (system_kinds/user_kinds/book_kinds; `EntityKind.Description`) but is never threaded to extraction — `kindOut` (`extraction_handler.go` ~125) doesn't SELECT/return it, and `build_extraction_prompt` (`extraction_prompt.py`) only uses ATTRIBUTE descriptions (`attr_meta.get("description")`), never a kind-level one. So the LLM gets a kind code/name with no definition → wrong-kind extraction. **Root cause feeding #38.**
> Fix: DONE (`73f87476`) — glossary extraction-profile now returns `book_kinds.description`; `build_extraction_prompt` emits it under the `## <kind>` schema header. (Exposing kind-description EDITING in ManageWorkspace is folded into the #22 standards-GUI work.)

### [x] 34. Some jobs are very hard to interrupt (30 min from cancel to stop)
Some jobs are very hard to interrupt — 30 minutes from cancelling until actually cancelled because the job keeps running. Need an enforce feature + GUI to accept data loss and stop the job immediately (user doesn't want to waste tokens).

> RC: Long-running workers checked cancellation only **cooperatively between units**
> (per-chapter/per-block) and **never aborted the in-flight provider call**, so the
> current LLM call(s) burned tokens to natural completion — compounding toward ~30
> min on a slow local model across many units. provider-registry already aborts an
> in-flight jobs-path call on `DELETE /v1/llm/jobs/{id}`; the missing piece was
> propagating the user's job-cancel down to it.
> Fix (keystone + 4-worker wiring): SDK `loreweave_llm.wait_terminal` gained a
> `cancel_check` async predicate — on first fire it issues the DELETE (`cancel_job`,
> aborting the upstream call) and returns the cancelled Job (same terminal a UI
> DELETE produces). Both check + DELETE are fail-soft. The 3 service wrappers forward
> it; each worker passes a fail-soft closure reading its parent-job status:
> **extraction** (`extraction_jobs.status`), **chapter translation**
> (`translation_jobs.status` — also fixed a mid-flight cancel surfacing as a chapter
> FAILURE: new `_CancelledError` → clean stop, no circuit-breaker trip), **KG build**
> (worker-ai → threaded through the `loreweave_extraction` SDK `extract_pass2` +
> entity/relation/event/fact extractors → `submit_and_wait`; reads knowledge-DB
> `extraction_jobs.status`), **composition prose-gen** (`generation_job.status` —
> threaded `run_job`→engine; streaming `.sdk` edit path skipped). FE: existing Cancel
> button is now an immediate stop; confirm copy clarified ("stops now, discards
> in-progress, keeps completed parts") ×4 locales. The in-flight call (and all
> concurrent batch calls) abort within one poll interval (~0.25–5s). Shipped in two
> milestones: M1 `473143c0` (keystone + extraction + FE), M2 (composition +
> translation + KG-build).
> **LIVE-SMOKE (D-CANCEL-IMMEDIATE-LIVE-SMOKE — DONE):** end-to-end on the real stack via
> glossary **extraction** (4×~30 KB Dracula chapters, local lm_studio `gemma-4-26b-a4b-qat`).
> Cancel → worker `cancel_check` fired → `DELETE /internal/llm/jobs/{id}` (204) → provider-registry
> aborted the live upstream call (`POST host.docker.internal:1234/v1/chat/completions: context
> canceled`); job reached terminal **~1.9 s** after cancel, keeping the 68 entities already
> extracted (in-progress chapter discarded). NOTE: the deployed images had to be rebuilt first
> (the running worker predated M1 — see [[feedback_verify_deployed_image_matches_source]]).
> The smoke ALSO surfaced + fixed a label bug: a cancel landing on the LAST chapter aborted its
> in-flight calls but fell through finalize, which overwrote `cancelling` with the
> chapter-aggregate (`completed_with_errors`) instead of `cancelled`. Fixed in
> `extraction_worker._run_extraction_job` (cancel-aware finalize + canonical event) + regression
> test `test_late_cancel_on_last_chapter_finalizes_as_cancelled`.
> **DECOUPLED TRANSLATION (D-CANCEL-IMMEDIATE-TRANSLATION-DECOUPLED — DONE):** the
> chapter-translation path runs DECOUPLED in the default deployment
> (`TRANSLATION_DECOUPLE_ENABLED=true`): event-driven submit→release driven by
> `llm_terminal_consumer`, never sitting in `wait_terminal(cancel_check)`. Fixed with a
> path-specific equivalent (no SDK cancel_check there): (A) the cancel endpoint (`_do_cancel`)
> now DELETEs every in-flight `chapter_translations.provider_job_id` for the job's non-terminal
> chapters → provider-registry aborts the upstream call NOW (best-effort; no-op for the sync
> path, which doesn't persist provider_job_id); (B) the terminal consumer's `_resume_loaded`
> gained a parent-cancel gate — once the job is cancelled it clean-stops the chapter
> (`job_cancelled`, clears resume_state/provider_job_id, releases the WFQ lease) instead of
> folding the aborted job as a batch-failure and submitting the next batch (which
> `decoupled_block_translate.resume`'s `status != 'completed'` branch would otherwise do,
> defeating the cancel). Live-smoked: 4-chapter Vietnamese job, cancel → `DELETE` (204) →
> provider-registry `operation:translation ... context canceled` ~2.5 s later → job `cancelled`,
> in-flight chapter `job_cancelled` with provider_job_id cleared. +4 unit tests (cancel-gate
> ×2, abort-sweep, best-effort-on-fault) + a drive-by fix of a pre-existing stale finalize
> assertion. Composition + KG-build share the proven keystone (same SDK `wait_terminal` +
> provider-registry abort), unit-verified for forwarding, not separately live-smoked.

### [x] 35. Platform lacks a language picker (user must type language code)
The platform lacks a language picker — the user must input the language code. Bad design.

> RC: Four flows asked the user to free-type a language code (BooksPage create dialog, book SettingsTab, Campaign wizard target-language, EntityEditorModal "add translation language"). A canonical list (`lib/languages.ts` `LANGUAGE_NAMES`, 13 codes) and `LanguageDisplay` already existed, but no reusable picker — TranslateModal and glossary-translate had each hand-rolled their own `<select>`.
> Fix: New shared `components/shared/LanguagePicker.tsx` — a dropdown over `LANGUAGE_NAMES` rendering "Native name (code)", with `placeholder`/`exclude` props and a data-loss guard that keeps an unrecognised current value selectable (so editing a book whose `original_language` is outside the 13 never silently blanks it). Wired into the 4 free-text sites. Enrichment `ProfileForm.language` left as free text — it is a prose style descriptor (beside voice/era), not a code. 6 unit tests, tsc clean.

### [x] 36. Extraction glossary LLM-call prediction is wrong (predicts ~2/chapter)
The total-LLM-call prediction for extraction doesn't work well. With 30 glossary kinds (many attributes), the number of calls is >30, but the prediction shows only ~2 per chapter.

> RC (investigated): the original Explore RC was **WRONG** — verified empirically (probe: 30 attr-heavy kinds). `plan_kind_batches` is NOT overloading: it correctly caps at `MAX_KINDS_PER_BATCH=3` → 30 kinds = 10 batches. And the fallback heuristic does NOT "ignore kinds×attributes" — it uses `batches_per_chapter` (which IS kind-derived). The REAL cause: **both estimate call-sites fed the windowing-aware planner a HARDCODED `[{"text_length": 8000}] * N`** (`extraction.py` ~186, `mcp/server.py` ~735) — every chapter the same fake 8000 chars. The planner can only window a chapter that exceeds the model context, but a flat 4000-token stand-in never windows, so the estimate collapses to exactly `chapters × batches_per_chapter` and is BLIND to real chapter size. The executor (`extraction_worker.py` ~1183) does `windows × batches`, so on a book with large chapters (or a small-context local model) reality fans out into windows the estimate never predicted → the undercount. (The probe confirms the planner IS size-sensitive: a 400k-char chapter at an 8k context → many more calls than the flat 8000.)
> Fix: DONE — new best-effort `book_client.build_chapters_meta(book_id, chapter_ids)` ([book_client.py](../../services/translation-service/app/book_client.py)) fetches the REAL per-chapter `word_count_estimate` from the existing `GET /internal/books/{id}/chapters` (the same endpoint knowledge-service uses for ITS estimate) and feeds genuine `text_length` to the planner; both call-sites (HTTP `extraction.py`, MCP `mcp/server.py`) now use it. An unfetchable size falls back to the legacy 8000 (no regression); any fetch error → all-default (a cost estimate must never fail job creation). **VERIFY:** 8 new tests (word-counts filter/paginate/error/empty + build-meta real-sizes/all-default + planner size-sensitivity) + admission/book_client suites green; client field reads verified against the live book-service handler (`items[].chapter_id`/`word_count_estimate`). **Deferred `D-EXTRACT-ESTIMATE-SCHEMA-PERBATCH`** — a SEPARATE, opposite-direction over-count noticed during the probe: `estimate_extraction_cost` adds the schema of ALL profile kinds to EVERY per-batch unit's input (should be the batch's ≤3 kinds), inflating the INPUT/cost estimate and coupling into windowing — needs its own analysis. **Deferred `D-EXTRACT-ESTIMATE-SIZES-LIVE-SMOKE`** (real FE estimate against a book with large chapters — also covers the /review-impl LOW findings: the handler→`build_chapters_meta`→estimate wiring is compile-checked but not behavior-tested, and the `wc×5` conversion deliberately leans high ~2× — a real smoke exercises both empirically).

### [x] 37. Job GUI should show number of LLM calls and estimated total calls
The job GUI should display the number of LLM calls and the estimated total calls.

> RC: the unified Job had no LLM-call notion — only chapter/item progress + cost/tokens.
> Fix: contract via the existing whitelisted `params` JSONB (no projection schema change):
> `estimated_llm_calls` (create event) + `llm_calls_done` (running events). FE renders
> "LLM calls: done / total" in JobProgressPanel (generic, all producers). Wired all 3 estimable
> producers — extraction + glossary-translate (commit 27253a36) + KG-build (this commit). KG-build
> runs DECOUPLED by default, so its count is a persisted `extraction_jobs.llm_calls_made` column
> incremented at the submit chokepoints (inline entity submit + the consumer `_submit_map` fan-out)
> and emitted at the per-chunk finalize (also fixed its frozen progress bar). Required changing the
> jobs-service projection to MERGE params (jsonb `||`) instead of whole-replace, so static create
> params coexist with live keys. Live-smoked all 3 on the real stack (KG-build: projection params
> `{llm_calls_done, estimated_llm_calls:16}` advancing per chapter). NOTE: realized can exceed the
> estimate (windowed extraction chapters / KG recovery+filter calls the estimate omits) — honest
> "estimate, not quote"; the realized count is exact.

### [x] 38. Extraction creates impossible entity counts (duplicates across kinds)
Extraction progression has a critical bug: 30 glossary kinds but it extracts 360 entities with an error message. A chapter can't have that many kinds. Suspect this is part of why extraction is slow. 739 entities created for only 5 chapters — impossible. Maybe glossary duplication (one glossary duplicated across multiple kinds because kind definitions are bad, or LLM mistakes).

> RC (VERIFIED): the entity dedup unique index is `(book_id, kind_id, normalized_name)` (`glossary-service/internal/migrate/extraction_concurrency.go:54-56`) and the resolver `findEntityByNameOrAlias` scopes lookups to `kind_id` (`extraction_handler.go` ~1173-1282) — so the SAME name extracted under N kinds creates N separate entities. Compounded by **#33** (no kind description in the prompt → the LLM tags one name under several ambiguous kinds). 30 kinds × per-chapter ⇒ hundreds of phantom entities.
> Fix: DONE (**user decision: cross-kind dedup at write time** — keep the per-kind structure, but resolve a name across ALL kinds before creating). New `findEntityCrossKind` ([extraction_handler.go](../../services/glossary-service/internal/api/extraction_handler.go)) matches a name across every kind via the app-maintained `normalized_name` column (the SAME `textnorm.Normalize` fold the per-kind resolver + dedup backstop use — so 張若塵/张若尘/full-width/case variants collapse cross-kind too). The writeback loop calls it on a same-kind miss and **merges into the matched entity under THAT entity's own kind** (`attrDefMap` already holds all book kinds → compatible attrs land, incompatible ones skip), oldest-wins, race-safe under the existing per-book writeback advisory lock. Migration `0042` adds a `(book_id, normalized_name)` partial lookup index so the cross-kind lookup is a seek, not a per-book scan (addresses the "extraction is slow" angle). Plus **#33** (kind description in the prompt, shipped `73f87476`) cuts wrong-kind tagging at the source. VERIFY: glossary build/vet clean; **3 cross-kind tests** (same-name-different-kind reuses + merges, distinct name still creates, traditional↔simplified folds to one) + the extraction/resolver/pipeline/dedup suites green; migration chain (incl. 0042) applies. **Residual `D-CROSSKIND-DEDUP-REMEDIATION`**: this PREVENTS new cross-kind dups; EXISTING ones in a book need cleanup — via #40 bulk-delete, or a future cross-kind extension of the `/dedup-name-variants` remediation (it currently groups by (kind, name)).

### [x] 39. Re-running extraction produces 100% duplicate entities
Glossary extraction has a bug when run many times: 30 kinds, 10 chapters generates 3000+
glossary entries — 100% duplicated. Need to investigate. (Likely the same root cause as #38 —
the merge/dedup path failing to recognize an already-extracted entity on a re-run, so each run
re-creates instead of merging.)

> RC (investigated): the chapter-level idempotency gate keys on `extraction_writeback_log.writeback_key` = hash(book, chapter, content, kinds, profile) (`extraction_handler.go` ~620-641). Change the profile/kinds and the key changes, so a re-run bypasses idempotency; the resolver then re-creates rather than matching prior-run entities (same per-kind scope limitation as #38). Net: re-run ⇒ ~100% duplicates.
> Fix: DONE together with **#38** — the same `findEntityCrossKind` cross-kind name match is independent of the chapter `writeback_key` AND independent of kind, so a re-run with a changed profile/kind set (the key bypass) now reuses the prior run's entity instead of re-creating. (Same-kind re-runs were already caught by `findEntityByNameOrAlias`; the residual duplication was the cross-kind case.)

### [x] 40. No way to batch-delete glossary entities
There is no way to batch delete glossary entities (e.g. to clean up the duplicates from #38/#39).

> RC (investigated): single-entity DELETE exists (`/v1/glossary/books/{book_id}/entities/{entity_id}`), but there is NO bulk-delete endpoint and NO multi-select UI in the glossary browser (`EntityListBrowser.tsx` has no checkbox/selection/bulk-action toolbar). Deleting #38/#39's duplicates means clicking each row one at a time.
> Fix: DONE — **BE** `POST /v1/glossary/books/{book_id}/entities/bulk-delete` (`entity_handler.go` `bulkDeleteEntities`) mirrors `bulkSetEntityStatus` + the single-`deleteEntity` soft-delete: book-scoped, **Manage-grant** gated (destructive, matches single delete), ≤1000 ids, drops malformed, soft-delete (`deleted_at`), returns `{deleted: N}` (foreign/already-deleted ids ignored = the partial-success report); no outbox event (mirrors single delete). **FE** — the multi-select infra (checkboxes, select-all, `FloatingActionBar`) ALREADY existed for bulk-status; added a destructive **Delete** button → reusable `ConfirmDialog` (destructive variant) → `bulkDeleteEntities` API → invalidate + clear selection. i18n ×4. VERIFY: glossary `go build`+`vet` clean; **5 bulk-delete handler tests** (soft-delete book-scoped, already-deleted-not-recounted, empty→400, all-malformed→0, auth→401) + the **grant-mapping guard** (view-grantee→403, confirms Manage) green on the live test DB; FE tsc + eslint clean, 4 locales valid. **Residual `D-BULK-DELETE-UI-SMOKE`** (optional): a browser smoke (select N → Delete → confirm → gone) — the FE mirrors the already-working bulk-status pattern, so low-risk. Pairs with the #38/#39 dedup decision (this is the cleanup tool for the duplicates they produce).

---

## Notes
- Items 7, 26 have promised follow-up evidence from the user.
- Several items cluster around the **glossary extraction → merge → KG flywheel** (7, 13, 26, 36, 38, 39) and the **agent planner/MCP batch** flow (18, 19, 27, 29, 30) — likely shared root causes.
- **#39 is almost certainly a duplicate of #38** (re-run dedup failure). Investigate together; #40 (batch-delete) is the cleanup tool needed after fixing them.
