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

### [ ] 7. Glossary extraction forgets to update attributes for frequent characters (merge bug)
Extraction almost forgets to update some attributes for frequent characters. Seems like the description is only extracted/set the first time. Need to investigate the current merge method. Suspect data already updates in the DB or a glossary version but is never reflected to the **current active version** shown on the GUI. (User will give evidence.)

> RC:
> Fix:

### [ ] 8. Translation glossary usually fails (output structure bug; no chunking/budget)
Translation glossary usually fails — maybe an output-structure bug. Happens with translation glossaries that exceed ~4000 output tokens. Suspect the token limit cuts off the model mid-generation. Do we calculate a budget for this job? Models have large context windows. The glossary has so much info but we don't do a **structured chunk** — putting everything into translation without a plan is bad.

> RC:
> Fix:

### [ ] 9. Build-KG progression shows "1/100" — meaning unclear
Built KG from the first 700 chapters (700+ chapters, 15000+ glossary entries). Progress shows "1/100" — what does that mean?

> RC:
> Fix:

### [ ] 10. Timeline events still in English despite multilingual KG; entities untranslated
Timeline shows English: "Chi Yao kills her fiancé, Zhang Ruochen." But the book origin is `zh`. We were supposed to have multilingual KG support. Also the English translation was never made — "Chi Yao" and "Zhang Ruochen" are unknown entities (nobody knows them).

> RC:
> Fix:

### [ ] 11. KG entities have no description/information (only nodes + edges)
Entities in the KG have no description or information — the GUI only shows nodes and edge relationships. Is this our design or did we implement the KG standard wrong? Unclear on the difference between KG and glossary, but an entity with only a name and relationships — is that correct?

> RC:
> Fix:

### [ ] 12. Timeline GUI is low quality; browsers across platform are scattered
Timeline GUI is bad quality — not a rich browser mode like other GUIs (especially glossary). Browsers across the platform are scattered and annoying. Want consistency.

> RC:
> Fix:

### [ ] 13. Glossary extraction also rebuilds KG (should be decoupled)
Glossary extraction seems to also rebuild the KG. When building glossary, the KG also updates. Want to build glossary **first**, then build KG **on demand**. We already have a Campaign GUI, but I used glossary extraction in the **workspace**, not in a campaign. Investigate.

> RC:
> Fix:

### [ ] 14. Rebuild KG destroys old KG (no update path, no confirmation)
Rebuild KG seems to destroy the old KG — had 12000+ entities and it destroyed all to rebuild from scratch. There's supposed to be an **update KG** feature. Very bad design, and it destroys without any warning/confirmation. We should never do that. (AWS-style: require typed confirmation without copy-paste to destroy important data.)

> RC:
> Fix:

### [ ] 15. Event timeline lacks metadata (chapter/scene/block); needs in-book time detection
Event timeline should carry metadata: chapter, block/scene, etc. — needed to trace events because some novels are non-linear; hard to build a timeline without metadata. Also need to detect the **real in-book time** mentioned in the book — an advanced feature because time in a book is rarely stated.

> RC:
> Fix:

### [ ] 16. "Build full" KG option — fact/summary/etc not visible (stopped early)
Chose "build full" for KG but don't see fact, summary, and other parts. Unsure if they build later — stopped at item 4/100 due to the many bugs above, don't want to waste tokens before they're fixed.

> RC:
> Fix:

### [ ] 17. Cannot open a fresh AI assistant in workspace (old session is huge)
Cannot open a fresh AI assistant in the workspace — the old chat session is too huge.

> RC:
> Fix:

### [ ] 18. Glossary assistant planner loops forever (self-recheck loop)
The glossary-assistant planner usually loops, even with a very strong local model. Seems stuck in a self-recheck loop forever. Investigate what our planner does — does it hand the whole plan to the model? A plan's progress needs multiple pieces of work controllable by logic. Tools like Kiro actively inject important info to control the model's work. (Web search + investigate.)

> RC:
> Fix:

### [ ] 19. Hardcoded `google/gemma-4-26b-a4b-qat` planner called after stopping session
A critical bug: `google/gemma-4-26b-a4b-qat` is called even after stopping the glossary planner. It uses the **default** planner, but I already selected another planner in the chat session. Also, after stopping the session the planner MCP should never be called. Changing the default planner in user settings still calls `google/gemma-4-26b-a4b-qat` — suspect it's hardcoded.

> RC:
> Fix:

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

### [ ] 21. Custom `romantic_scene` kind in Xianxia Harem genre not wired in GUI
Created `romantic_scene` in a custom Xianxia Harem genre, but the GUI doesn't wire it — can't edit `romantic_scene` kind anymore.

> RC:
> Fix:

### [ ] 22. System/user/book kinds never wired correctly to FE (no edit GUI)
System kind, user, and book are never wired correctly — critical UX bug. Users can't edit them due to lack of GUI. Happens on **Glossary Standards** (no GUI to write genre, kind, attribute), and on the **book** too (no ability to edit/wire them). Seems like BE exists but was never wired to FE.

> RC:
> Fix:

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

### [ ] 25. "Adopt genre" is useless (genre never wired to kind + attribute)
Adopt genre is useless because there's nothing to adopt — genre is never wired to kind and attribute.

> RC:
> Fix:

### [ ] 26. Glossary merge needs a "merge/summary/overwrite" mode (dedup + rewrite)
Glossary merge/append lacks an important type — call it merge or summary. A character's description changes each chapter but is almost the same; normal append produces lots of nearly-identical/useless data. Better to have a "merge overwrite" mode: take new raw extracted data, append to old data, and **rewrite a better version** with dedup. (User will give more detail on why.)

> RC:
> Fix:

### [ ] 27. Multiple agent confirm cards — only the first works (later cards expire)
Agent proposes multiple confirm cards but only the first works; later cards expire because confirming the first card invalidates them.

> RC:
> Fix:

### [ ] 28. No way to review KG schema on either book or knowledge GUI
There is no way to review the KG schema on both the book and knowledge GUIs.

> RC:
> Fix:

### [ ] 29. KG schema lacks batch operations (agent proposes only 1–2 edges, second expires)
KG schema lacks batch work. Told the agent to update the whole KG schema but it doesn't work well — only proposes 1–2 edges, and the second edge always fails (expired/something).

> RC:
> Fix:

### [ ] 30. Batch logic is poor; agent loses track mid-list — planner/executor must be stricter
Batch logic is bad — after the agent lists many kinds, it only batches very few items. The agent gets lost in the middle. Make the planner/executor stricter: the agent should only **propose** and send the proposal to the MCP; the MCP does the whole work instead.

> RC:
> Fix:

### [ ] 31. Glossary GUI can't view `select`-type attributes (combobox empty)
The glossary GUI cannot view attributes with `select` type — the combobox is empty.

> RC:
> Fix:

### [ ] 32. LLM calls not consistently logged to bill service (no request/response tracing)
LLM calls should go through the LLM provider; the provider should store all request/response logs to the bill service. Currently not every call is written to the bill service, and input/output aren't stored — can't trace or analyze LLM calls.

> RC:
> Fix:

### [ ] 33. Platform lacks kind description (not attribute) — model extracts wrong kind
The platform lacks a **kind description** (distinct from attribute), so the model doesn't understand and extracts the wrong kind.

> RC:
> Fix:

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

### [ ] 35. Platform lacks a language picker (user must type language code)
The platform lacks a language picker — the user must input the language code. Bad design.

> RC:
> Fix:

### [ ] 36. Extraction glossary LLM-call prediction is wrong (predicts ~2/chapter)
The total-LLM-call prediction for extraction doesn't work well. With 30 glossary kinds (many attributes), the number of calls is >30, but the prediction shows only ~2 per chapter.

> RC:
> Fix:

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

### [ ] 38. Extraction creates impossible entity counts (duplicates across kinds)
Extraction progression has a critical bug: 30 glossary kinds but it extracts 360 entities with an error message. A chapter can't have that many kinds. Suspect this is part of why extraction is slow. 739 entities created for only 5 chapters — impossible. Maybe glossary duplication (one glossary duplicated across multiple kinds because kind definitions are bad, or LLM mistakes).

> RC:
> Fix:

### [ ] 39. Re-running extraction produces 100% duplicate entities
Glossary extraction has a bug when run many times: 30 kinds, 10 chapters generates 3000+
glossary entries — 100% duplicated. Need to investigate. (Likely the same root cause as #38 —
the merge/dedup path failing to recognize an already-extracted entity on a re-run, so each run
re-creates instead of merging.)

> RC:
> Fix:

### [ ] 40. No way to batch-delete glossary entities
There is no way to batch delete glossary entities (e.g. to clean up the duplicates from #38/#39).

> RC:
> Fix:

---

## Notes
- Items 7, 26 have promised follow-up evidence from the user.
- Several items cluster around the **glossary extraction → merge → KG flywheel** (7, 13, 26, 36, 38, 39) and the **agent planner/MCP batch** flow (18, 19, 27, 29, 30) — likely shared root causes.
- **#39 is almost certainly a duplicate of #38** (re-run dedup failure). Investigate together; #40 (batch-delete) is the cleanup tool needed after fixing them.
