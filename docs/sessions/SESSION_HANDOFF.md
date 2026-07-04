# ▶▶ NEXT SESSION STARTS HERE

**#18 BOOK-OPEN ROUTING + COMMAND PALETTE DOMAIN GROUPING — SHIPPED 2026-07-05** (branch `feat/context-budget-law`, spec [`18_book_open_and_palette_grouping.md`](../specs/2026-07-01-writing-studio/18_book_open_and_palette_grouping.md)). Workspace-browser book-open (`BooksPage.tsx` row) now links directly to `/books/:id/studio` instead of the classic `BookDetailPage` — classic routes are unchanged and still reachable by direct URL, just no longer the default landing surface. `StudioPanelDef` gained a `category` field (9 domain groups: editor/storyBible/knowledge/translation/enrichment/sharing/platform/discovery/jobs, assigned to all 46 openable panels, verified zero orphans); the Command Palette's flat "Panels" bucket now sub-groups by category via a fixed `CATEGORY_ORDER` sort in `useStudioCommands.ts` (i18n under the existing `palette.group.*` namespace, not a new one — reused the existing helper). A mechanical test (`panelCatalogContract.test.ts`) now fails loudly if a future panel omits `category`. **VERIFY:** 690/690 unit tests green, tsc + eslint clean, live Playwright E2E against the real vite dev server (not mocks) — new tests in `writing-studio.spec.ts` (row→Studio; `BooksPage.openBook()`→classic, no `/studio` suffix) and `studio-palette.spec.ts` (3 distinct category headers render, old flat "Panels" header gone) all pass. **Found + fixed incidentally:** `demo-pipeline-3a/3b/3c.spec.ts` all call `BooksPage.openBook()` post-creation — since the row's click target moved, `openBook()` now navigates directly to the classic route (extracted from the row's `href`) instead of clicking, so all 3 specs keep working unchanged; added `openBookInStudio()` for the new default path. **Deferred (gate #1, out of scope — different concern, found incidentally, not caused by this milestone):** `D-E2E-BOOKCREATE-SELECT-FILL` — `BooksPage.ts`'s `createBook()` calls `.languageInput.fill()` but the language field is a `<select>`, not an `<input>`/`<textarea>` — breaks `demo-pipeline-3a/3b/3c.spec.ts` at the create-book step (confirmed pre-existing; this milestone never touched that form or POM method). Fix: change to `.selectOption()`. **NEXT:** [`19_onboarding_and_user_guide.md`](../specs/2026-07-01-writing-studio/19_onboarding_and_user_guide.md) Wave 1 (Studio onboarding overlay + catalog-driven User Guide panel + `core` react-joyride tour) — spec adversarially reviewed already (found + fixed a DOCK-9 hand-rolled-overlay defect in the original draft before any code was written).

**CHAPTER BROWSER + KG UX FIXES + TRANSLATION/ENRICHMENT/SHARING/BOOK-SETTINGS DOCK FANOUT — ALL SHIPPED 2026-07-05** (this session, branch `feat/context-budget-law`, HEAD `56c8e17c6`).

1. **`D-CHAPTER-BLOCKS-STALE-EXTRACTION` cleared** (commit `a22d03642`): `fn_extract_chapter_blocks` read ONLY the client `_text` snapshot; a sibling `7b9cd4fda` fix unioned `_text`+nested-text-leaves for 4 READ paths but missed this WRITE-side trigger — any chapter saved without a client `_text` annotation got permanently-empty `chapter_blocks`, invisible until Chapter Browser's word_count/export made it visible live. Also found + fixed: the established `$.**.text` jsonpath ran in Postgres lax mode, double-visiting single-text-node blocks (silently duplicating text) — fixed to `strict $.**.text` across all 5 call sites (the trigger + 4 pre-existing reads). Added a batched backfill (`backfillChapterBlocksExtraction`), live-verified against the real dev DB: all 12 POC-book chapters got correct word counts, full-text search now finds previously-invisible chapters, bulk export returns real text.
2. **3 Knowledge-panel UX bugs fixed** (commit `73e6d9704`): `D-KG-HUB-EXTERNAL-OPEN` (opening THIS book's own KG project popped a new tab instead of the in-studio `kg-overview` panel — Phase B's 13 panels made the old fallback unnecessary for the same-book case); `D-KG-NO-CREATE-CTA` (every book-scoped `kg-*` panel's "no project yet" state had copy but no button — new shared `KgNoProjectState` component, reuses `ProjectFormModal` AS-IS with a new `initialBookId` lock); `D-KG-HUB-BOOK-SCOPE` (user-requested follow-up: the Knowledge hub panel defaulted to the global cross-book list even though it's opened FROM a book — `ProjectsBrowser` gained an optional `scopedBookId` prop, toggle-able back to "all books", never a silent narrowing).
3. **Translation/Enrichment/Sharing/Book-Settings dock fanout** (commit `56c8e17c6`, spec [`17_translation_enrichment_sharing_settings_docks.md`](../specs/2026-07-01-writing-studio/17_translation_enrichment_sharing_settings_docks.md)): 9 new panels — `sharing`, `book-settings`, `translation` + `translation-versions` (hidden singleton), and `enrichment-{compose,proposals,gaps,sources,jobs,settings}` (DOCK-8 split of `EnrichmentView`'s former 6-way tab switch, no hub). Built via 4 parallel background agents, one BE-touching fix-now along the way (`TranslateModal`/`SegmentDrilldownModal` DOCK-9 migration to `FormDialog`; `GapsPanel`'s dead-end "extract first" message got a real CTA opening `ExtractionWizard`). **`/review-impl` caught + fixed 1 real HIGH finding before commit:** the first version of `BookSettingsPanel` forked `SettingsTab`'s ~400 lines of logic instead of reusing it (DOCK-2 + SDK-First violation) — fixed by threading an optional `onOpenWorld` prop through `SettingsTab` itself (mirroring `BookWorldSection`'s own shape) so the panel could become a genuine thin wrapper. All 9 panels live-smoked in a real browser session (real API calls, Sharing's visibility toggle + full TranslateModal flow exercised as real actions). Full frontend suite green (4198/4199 — the 1 failure is a concurrent session's own in-flight work).
4. **Deferred (tracked, gate #2 — large/structural):** `D-SETTINGS-NO-GENRE-CTA` — Book Settings' "no genres" empty state has no create-CTA either, but genre-authoring's actual home (Glossary? a new admin surface?) needs a PLAN-time decision first.
5. **Multi-session note:** this branch ran several concurrent sessions throughout (context-budget-law/editor-craft, a JWT-auth refactor touching `services/translation-service/*`, a tenant-boundary-audit track) — every commit above was staged with exact pathspecs, verified via `git diff --cached --name-only` before committing, never `git add -A`.

**CONTEXT INSPECTOR GUI (Context Budget Law §11) — M1 + M2 SHIPPED 2026-07-05.** Plan [`docs/plans/2026-07-04-context-inspector-gui.md`](../plans/2026-07-04-context-inspector-gui.md) (3 milestones). **M1 BE telemetry (`54d3872c9`):** a `loreweave_context.TraceAccumulator` threads through chat assembly recording each tier decision it can MEASURE (T6 C_persist via `persist_auto_compact`, in-turn compaction, T0 wire-hygiene); the persisted per-turn `contextBudget` frame gained `raw_tokens` (= compiled + Σ savings), `reduction_pct`, ordered `trace[]` spans, `status_flags[]`, `retrieval_mode`, `intent` — all additive. New `GET /v1/chat/sessions/{id}/context-trace` (full frames + user message). `contracts/context-trace.contract.json` + `test_context_trace_contract` (conformance on the REAL emit fn) + `scripts/context-inspector-trace-gate.py` (live GATE, §13b). **Honesty:** chat claims only measurable savings (gated-grounding = status flag delta 0, not a fake cut); raw==compiled when nothing cut. *Also fixed broken HEAD:* the T3 `budget.py`/`plan.py` the committed kernel `__init__` imported were left untracked. VERIFY: chat 937 tests, provider-gate, **live real-turn GATE PASS** (every field non-null, raw==compiled+savings). **M2 FE (`6c5dea2e6` core + `887f4b246` registration):** dockable `context-inspector` panel — `features/chat/inspector/` (pure `inspectorMath` gauge/KPI/filters + `useContextTrace` self-contained hook + PressureGauge/AllocationMap[reuses ContextBreakdownPanel computeBreakdown+colors, extended to 15 cats]/CompileTrace waterfall/TurnList + ContextInspectorView container) → `ContextInspectorPanel` (studio dock) + registered in catalog/`ui_open_studio_panel` enum/contract/4 i18n. **Responsive** (rail stacks below `md`, top-bar/KPIs wrap). VERIFY: 46 FE tests + tsc clean + **live browser smoke** (vite→gateway→chat, 0 console errors, real `/context-trace` data rendered: gauge state + allocation segments). **ENTRY POINTS + AUDIT — DONE 2026-07-05 (user-requested "check lại rồi clear"):** (1) standalone `/context-inspector` route ✅ RESOLVED (App.tsx settled — route present + import; the page now reads `?session=` → `initialSessionId`). (2) Added a chat-header **Context Inspector icon** (`Gauge`, `ChatHeader`/`ChatView`) that deep-links `/context-inspector?session=<id>` on the full chat page only (embedded editor/studio surfaces withhold it — a nav-away would tear down the host). (3) Studio **command-palette** "Studio: Open Context Inspector" already catalog-driven — added a real-catalog assertion test. **All three LIVE-PROVEN in browser** (0 console errors): chat icon → deep-linked inspector renders real `/context-trace` (allocation map, compiled tokens, honest "nothing was cut" empty trace); palette opens the dock panel; empty session → honest empty state. **"(no message)" is smoke-data-only** — the W1 synthetic rows have null `parent_message_id`; real turns resolve the user message via the `parent_message_id` LEFT JOIN the normal insert path sets (`stream_service.py:2857`). 4 FE tests (`ChatHeader.inspector`, `ContextInspectorPage`, palette) + tsc clean. **M3 = §13 ENFORCEMENT — SHIPPED 2026-07-05.** Every §11a item (84) now carries `✓test:<path>::<needle>` (82) or `⊘manual:<reason>` (2 pure CSS animations). `scripts/context-inspector-checklist-gate.py` parses §11a + FAILS on any unproven box / dangling ref / needle-not-on-a-test-declaration-line; `--run` also EXECUTES the referenced pytest+vitest suites (§13c "(b) in the passing set"). Wired into `.githooks/pre-commit` (guarded to fire on spec/inspector changes) + the `lint-foundation` CI `p1-lints` matrix (static). Wrote the missing EFFECT-tests: PressureGauge/AllocationMap/CompileTrace/TurnList component tests + extended ContextInspectorView (click-load, j/k, filter-resets-page, loading/error, poll, enabled-gate, state-split, header chips, KPI values) + `test_context_trace_router.py` (endpoint/owner-gate/pagination) + ContextInspectorPanel mount/self-title. Fixed 2 real impl gaps en route: allocation tooltip missing `%`; a real interval **poll + focus-refetch** in `useContextTrace` (the "live update" item was only a manual refresh button). **§13d adversarial refute-pass** (cold-start subagent, refuted-unless-proven) found **6 real gaps — ALL FIXED**: NEW-cats (summary/chapter/reasoning) unasserted → new AllocationMap test; "live update" proven by a manual button → genuine poll; endpoint `?page&filter` over-claim → honest client-side clarifier; gate static-only → CI + parser now requires the needle on a real `it/test/def test` line (not a comment); KPI avg/saved asserted by label only → assert computed values. Gate teeth proven by 3 negative tests (unproven box / dangling needle / comment-only needle → exit 1). VERIFY: gate `--run` green (2 pytest + 12 vitest files), 72 inspector FE tests + tsc clean. **Committed live E2E** `frontend/tests/e2e/specs/context-inspector.spec.ts` (4 tests, real login/gateway/dockview; `/context-trace` mocked for determinism — BE already covered by pytest+trace-gate): chat-header icon deep-links `?session=<id>` + renders gauge/allocation/turn-list, status filter narrows live, studio Command Palette mounts the dock panel, empty session → honest empty state — **4/4 pass live** (vite :5210→gateway :3123; added `data-testid="chat-session-row"`). **`D-CHAT-URL-SESSION-ACTIVATION` — ✅ FIXED same session:** the `ChatSessionContext` restore-from-URL effect now falls back to a direct `chatApi.getSession` when the URL session is NOT in the loaded list (deep-link to an old session past page 1, or a fresh 0-message session sorting to the bottom by last-activity), so `/chat/{id}` always activates instead of silently showing an empty chat. Functional `setActiveSession` → no re-fetch loop; only fetches once the list settles (`sessionsLoading` guard). Regression-guarded by the direct-URL E2E (red pre-fix → green) + 11 chat-provider unit tests. *Multi-session note: committed via `git commit --only <paths>` to isolate from a concurrent #18 enrichment/translation-docks session's large staged index; that session also re-grouped the palette by domain (`context-inspector` now under the `editor` category) — my catalog-membership proof-ref survives it.*


**CONTEXT BUDGET LAW — T4 story_state PROJECTION WIRED 2026-07-05** (branch `feat/studio-agent-raid`, spec [`2026-07-03-context-budget-law.md`](../specs/2026-07-03-context-budget-law.md) §8 T4 row). The T4 substrate (distill/cadence/render `services/chat-service/app/services/story_state.py` + persistence/OCC `db/session_blocks.py`) was fully built + tested but had **ZERO callers** — the block was never projected. Now connected at the `stream_service.py` assembly seam via a new orchestrator `db.session_blocks.project_story_state`: each turn (flag on) it maintains the cached, bounded (≤1200 tok) story-bible block from the grounding prefix (refresh via `should_refresh` — hash/lore-gate/scene/cadence) and projects it as the **leading tail block ONLY when the turn has NO live grounding** (`kctx.context` empty — degraded / future T5-gated-empty) = the D4 safety net. New flag `story_state_block_enabled` (**default OFF** — while T5 gating is off, `build_context` returns a live prefix every turn so unconditional projection would only DUPLICATE it, a token regression; flip on together with `t5_intent_gate_enabled`). Added a `story_state` token-breakdown category. **REVIEW caught + fixed my own trigger bug:** keyed the projection on `full_context` not `stable_context` — `multi_project` mode has `stable_context=""` but a full live `context`, so keying on the prefix would false-fire and duplicate live lore (regression-guarded). **VERIFY:** 34 T4 tests green — 9 orchestrator decision-logic (incl. multi-project false-fire guard + degraded-projects-cache net) + **real-Postgres end-to-end** (maintain→degraded→project through actual `chat_session_blocks` SQL) + 3 stream wiring effect-tests (block in system prompt when on; absent + orchestrator-never-called when off) + existing story_state/session_blocks suites; **full chat suite 954 green** (1 unrelated pre-existing failure = a concurrent session's `frontend_tools.py` studio-panel enum drift, NOT T4 — I never touched that file); provider-gate clean. **D4 "unconditional projection that SUPERSEDES the live prefix" (killing the per-turn build_context pull) deferred with T5.** **NEXT for Context Budget Law:** flip T5/T4 defaults on + the answer-correctness gold Q&A set (sealed #7, user-validated) to measure the continuity-with-gating GATE; then T6 single-item-overflow (D7) + reversible collapse (D13a); T1 tail; T2 LOW-2 FE⊆BE contract test.

**▶ P2 ENTERPRISE STRUCTURAL HARDENING** (spec [`2026-07-04-enterprise-p2-structural.md`](../specs/2026-07-04-enterprise-p2-structural.md) = system-of-record). SHIPPED this run: **G** (no-op, verified) · **B1** (KEK sha256) · **A1** (10-Go-main obs fleet + `/review-impl` Standards gate) · **A2a** (Python `setup_logging`) · **B2** (retention sweeper + embed cost + route-parity D-S4C fix + outbox purge) · **C 4/6** (dedup, noop-warn, PII-redact, opt-out; 2 slices tracked) · **D** (latency SLO SoT + lint) · **F** (tenant-boundary audit — `tenant_access_audit` append-only table + coalesced first-per-window emit in book-service `authBook` + glossary-service `checkGrant`; injectable `emitTenantAudit` hook; 9 decision tests + insert-shape/bucket tests green). **E** (salience↔learning — ✅ RESOLVED, documented keep-separate: [`2026-07-05-salience-learning-boundary.md`](../specs/2026-07-05-salience-learning-boundary.md); tracked `D-E-SALIENCE-LEARNING-BRIDGE` revisit-gated) · **A2b** (✅ SHIPPED — RETIRED `contracts/logging` Go module [0 adopters] + repointed lint/inventory/standard to slog+`sdks/go/observability`; 0 backend TS `console.*` [api-gateway-bff & ai-gateway NestJS Logger + game-server `src/log.ts`]; tsc clean ×3, ai-gateway tests green). **✅ P2 STRUCTURAL HARDENING COMPLETE — all workstreams A1 · A2a · A2b · B1 · B2 · C-core · D · E · F · G shipped or resolved.** **✅ `/review-impl` DONE (2 cold-start adversarial reviewers on F tenant-iso + A2b deletion) + all findings fixed:** F MED-1 (glossary logged OD-8-denied as `granted` → fixed + regression test), MED-2 (write-amplification → in-process dedup cache), MED-3 (real-PG dedup test, **LIVE-PROVEN** vs dev PG); A2b MED (sdk-first.md contradicted the retire → fixed) + LOW (sdk-dup-gate/dashboard cleanup). **Recently cleared defers:** `D-A2B-TS-CONSOLE-LINT` (✅ BUILT — HARD backend-`console.*` lint check, baseline 0, negative-proven; A2b's regression gate); `D-F-AUDIT-LIVE-SMOKE` **partially cleared** (DB-effect dedup/ON-CONFLICT/CHECK live-proven; only the full HTTP cross-tenant E2E remains). **P2 Deferred tail (tracked, none blocking):** `D-F-AUDIT-HTTP-E2E` (cross-tenant read through the real HTTP stack → row; needs scratch stack) · `D-A1-CALLSITE-SWEEP` (per-service slog ctx-thread, Tempo-gated) · `D-D-PERF-NIGHTLY` (p95 assertion, no harness) · `D-C-PRODUCER-OUTBOX` · `D-C-FE-I18N` · B2 live-smokes (`D-B2-{RETENTION,PARITY}-LIVE-SMOKE`, `D-B2-RERANK-WEBSEARCH-PRICING`) · `D-C-DEDUP-LIVE-SMOKE`.

**▶ P3 = SDK-first: JWT verifier + shared types** (user-chosen next tier; audit had no P3). **CLARIFY finding: the audit was STALE** — the JWT consolidation was ~90% already done (Go: all 7 domain services import `contracts/platformjwt`, auth is minter, 0 left; `TerminalEvent` already aliased to `contracts/notifyevent`). **Slice 1 ✅ SHIPPED — the last 2 Python hand-rollers migrated** to `loreweave_authn`: translation-service (deps.py `get_current_user` + confirm-replay `verify_access_token` + removed dead `verify_request_jwt`) + video-gen (`extract_user_id`); test fixtures updated to mint realistic tokens (`exp` required + UUID `sub`, the SDK's stricter+correct posture). Full suites green (**translation 1038, video-gen 58**). **Slice 2 ✅ SHIPPED — TS alg-confusion fix:** 3 un-pinned `jwt.verify` sites in api-gateway-bff (notifications.controller / ws.events.gateway / ws.ticket-endpoint) now pin `{algorithms:['HS256']}` (matching tools.controller); tsc clean, 104 tests green. **Enforcement:** new `py-jwt-verifier` rule in `sdk-duplication-gate.py` (assignment-anchored HS256 `jwt.decode` → red; negative-proven, ignores docstrings/RS256-admin/verify_signature=False stub); baseline clean. **Slice 3 = `BaseInternalClient` — IN PROGRESS (user chose FULL build).** INVENTORY (subagent): ~48 client impls / ~40 files / 10 services. **Key design finding: a "one base, uniform policy" would be WRONG** — fail-posture is per-METHOD (degrade/raise/swallow/verbatim-passthrough coexist in one class), so the SDK provides COMPOSABLE MECHANICS, not imposed policy. **SDK built: `sdks/python/loreweave_internal_client`** (`build_internal_client` factory [token+JSON headers + uniform per-request X-Trace-Id event-hook + httpx.Timeout], `InternalClientError`+`is_retryable_status`/`RETRYABLE_STATUSES`={429,502,503} collapsing ~5 dup error classes, `resolve_model_name` collapsing the 5 byte-identical copies; 8 SDK tests green). Registered in shared `sdks/python/pyproject.toml` include (else `pip install /sdk` omits it → runtime ImportError). **Wave 1 ✅ — model_name collapse:** all 5 `model_name.py` (translation/knowledge/composition/campaign/video) → thin shims over the SDK; per-service tests green (video 6, campaign 7, composition 65, knowledge 26, translation 41 — respx/monkeypatch intercept the SDK's httpx transparently). **NEXT waves (risk-ordered):** W2 error-class unification (LE `*ServiceError`, worker-ai result dataclasses, both `EmbeddingError` → `InternalClientError`); W3 trace-uniformity + `build_internal_client` adoption for the simple degrade clients; W4 the 6 HARD cases LAST with per-method care (chat knowledge_client [2 hosts + MCP transport], comp book/knowledge [dual-auth per-method], the "one fail-closed method" book clients, knowledge glossary [circuit breaker], campaign dispatch [404/409-as-success], LE writeback [semantic non-2xx], jobs control [verbatim passthrough]). Also fix the live bug the inventory found: comp `grant_client` shim forgot to wire `trace_id_provider`. **P3 deferred:** `D-P3-LORE-ENRICH-JWT` (lore-enrichment's intentional `verify_signature=False` stub).

**WIKI DOCKABLE MIGRATION — FULLY DONE 2026-07-04** (follows the same pattern as Glossary/KG:
CLARIFY → design-review-before-PLAN → BUILD → adversarial `/review-impl`). Narrow surface (no
Phase A/B split needed): `wiki` + `wiki-editor` (params-retargeting singleton, editor/book-reader/
json-editor precedent) are real dock panels; both classic routes (`WikiTab`, `WikiEditorPage`) are
now thin callers of shared `WikiWorkspace`/`WikiEditorWorkspace` components (DOCK-2). Fixed 2
DOCK-9 hand-rolled modals, 6 DOCK-7 navigate/Link sites, wired a previously-dead History button,
and — the one genuine new-risk finding from design review — added a **G7 dirty-guard** on
`wiki-editor`'s params-retargeting (a naive singleton would have silently discarded unsaved prose
the instant a user opened a different article mid-edit; also fixed the same pre-existing bug on
the classic page's Back button, which had no dirty-guard at all before this).
**Follow-up same day, user-requested — second `/review-impl` + live E2E + live smoke, ALL
CLOSED (`cc707dfd8`, `d42a00d69`, `88cbf0133`):** a fresh review-impl pass found a DOCK-10 gap
(unsaved edit lost on dock-tab CLOSE, not just retarget) — fixed with a module-level draft cache.
A new live Playwright E2E suite (`wiki-panels.spec.ts`, real backend/dockview/TiptapEditor, no
mocks) then found 3 MORE live-only bugs unit tests structurally couldn't catch (title-refinement
parent/child effect race, TiptapEditor's own spurious unmount `onUpdate`, a StrictMode-exposed
non-idempotent cache-restore effect) — all fixed. A manual live-smoke via Playwright MCP at
narrow dock widths (user asked "is this responsive?") then found and fixed 5 more overflow bugs
across both `wiki`/`wiki-editor` panels (clipped Save button, off-screen action buttons, a
fixed-width float squeezing prose unreadably narrow, a hardcoded height that first left dead
space then over-corrected into hard-clipping content, and an oversized fixed sidebar). Full
narrative + verify evidence for all three rounds: [`15_wiki_panels.md`](../specs/2026-07-01-writing-studio/15_wiki_panels.md).
**No defer/debt rows for Wiki** — every finding across all three rounds was fixed in-session, not
deferred. **Note for the next session:** this branch is running several concurrent sessions
at once (KG, Chapter-Editor-Parity/COHERENCE, context-budget-law, utility-panels all landed
commits mid-way through this one) — re-verify shared spine files (`catalog.ts`, `studio.json` x4,
`frontend_tools.py`, the contract) before trusting this note's file list is still current.

**KNOWLEDGE/KG DOCKABLE MIGRATION — FULLY DONE 2026-07-04** (commits `4c50f7ae2` Phase A, `5c43a36c9` Phase B, `d9d21a262`/`b88e07ba7` docs, `9098f9ce0` studioLinks wiring, `21bae112a` E2E). All 13 panels (`knowledge` hub + 12 `kg-*` capability panels) built, wired into the studio link resolver, and **live-proven**: `frontend/tests/e2e/specs/kg-panels.spec.ts` opens every one through the real Command Palette against the real backend — 17/17 passing (ran via `docker` stack + `vite --port 5199`; the baked `:5174` image is stale for this work). Decision recorded: `KnowledgePage`/`ProjectDetailShell`/`KnowledgeOntologyTab` are **NOT** retired into redirects — matches wave-1's own documented precedent (`11_dockable_migration.md`) of keeping classic routes as multi-device/non-studio entry points; Knowledge's case is harder than wave-1's (no reliable book to redirect a global hub or standalone project into, Studio is desktop-first). See [[kg-dockable-migration-phase-a]] memory for full detail. Remaining, still deferred: cross-panel E2E beyond what's already covered (hub → other capability panels).

> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE Phase 2 ✅ COMPLETE 2026-07-05** (spec
> [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md),
> plan [`2026-07-04-writing-studio-phase2-editor-craft.md`](../plans/2026-07-04-writing-studio-phase2-editor-craft.md)).
> All 11 editor-craft UX gaps from the Phase 1 capability audit shipped in one continuous L-size
> run: grammar check, glossary inline decoration/autocomplete, mention heatmap, AI-provenance
> tracking+toolbar, selection toolbar/inline-AI, focus mode, auto-save (300s debounce),
> progress-reporting, image/video upload-context (**redesigned** module singleton →
> per-editor-instance via `editor.storage.mediaUpload` — a module singleton is a multi-tab/
> multi-window landmine), original-source viewer (`OriginalSourcePanel`, new dock panel), and
> popout Compose (`StudioPopoutHost` at `/studio/popout` — a REAL OS-window pop-out per the
> user's explicit ask for multi-monitor support, reusing the T5.4 M4 `PopoutBridge`/
> `popoutChannel` mechanism generalized with a `route` prop). M7 (Classic/AI editor-mode
> toggle) — user decision: **do NOT port**, conscious won't-fix (Studio has no such toggle
> concept; recorded in spec 16).
>
> **`/review-impl` found + fixed 1 HIGH:** the popout Compose Apply path was fire-and-forget —
> if the user pops out Compose on chapter A then switches the main-window editor to chapter B,
> the opener's `usePopoutInsertRelay` unsubscribes from channel (book, A) on chapterId change,
> so an Apply from the still-open popout would **silently drop the edit while reporting
> "Applied ✓"** to both user and LLM. Fixed with a request/ack correlation protocol: optional
> `reqId` on `insert-prose`, matching `insert-ack` reply, `Promise<boolean>` + 4s-timeout on the
> sender — backward-compatible with the legacy un-acked `PopoutHost` sender (no `reqId` ⇒ no ack
> expected). 6 new tests across `usePopoutInsertRelay`/`StudioPopoutHost`/`ProposeEditCard`.
> **1 MED accepted, not fixed:** `EditorPanel.tsx`/`ManuscriptUnitProvider.tsx` are now ~370
> lines each, over the React MVC ~100/200-line guideline — deliberate (avoids re-fragmenting 8
> file-convergent sub-tasks across a merge-collision-prone split mid-effort); a size-debt
> refactor is its own follow-up, not blocking.
>
> **VERIFY:** `tsc --noEmit` clean; 268 files / 1926 tests green (a 4-file KG-panel flake seen
> mid-sweep was confirmed cross-file test-pollution on rerun, not a regression — passes both
> isolated and on a clean full-sweep rerun). Live browser smoke (vite :5199, real backend, real
> local `google/gemma-4-26b-a4b-qat`): grammar/heatmap/focus/glossary-autocomplete/
> provenance-tag all exercised; cross-window relay proven end-to-end with a real second OS
> window (pop out → agent drafts → Apply → main-window editor updates). **2 pre-existing bugs
> found during smoke, confirmed NOT caused by Phase 2 (untouched by its diff), left as-is:**
> LanguageTool 500s (reproduces identically on the legacy route — infra flakiness) and a React
> "Cannot update ManuscriptUnitProvider while rendering TiptapEditor" warning (Phase 1's
> `content`/`onUpdate` wiring, predates Phase 2).
>
> **Environmental incidents hit + resolved mid-session on this shared checkout (not code
> defects):** (1) `git worktree remove --force` on a fan-out worktree followed a Windows
> junction back to the main checkout's real `node_modules` and deleted its TARGET content —
> fixed via `npm install` (785 packages restored, lockfile unchanged). Lesson: never let a
> worktree's `node_modules` be a junction to the main checkout's real one — run `npm install`
> fresh inside each worktree instead. (2) a concurrent session's `git reset` + `commit` on this
> shared checkout cleared the entire shared staging index (34 files) mid-review — recovered via
> the [[shared-file-collision-safe-staging-multi-agent-checkout]] reconstruct-stage-restore
> technique, re-verified via diff that no staged content was lost.
>
> **Playwright E2E added same day (`87e8508cd`), user asked "did you enforce standards + write
> E2E?" before greenlighting Phase 3** — `tests/e2e/specs/studio-editor-craft.spec.ts` (4 tests,
> real backend, no mocks, kg-panels/wiki-panels precedent): grammar/heatmap toggle round-trip,
> focus-mode hides the flanking Revision History strip, Original Source panel opens+loads, and
> the popout Compose full lifecycle (real second OS window via `window.open` → Dock-back closes
> it → opener re-enables Pop out) — the exact boundary the `/review-impl` HIGH lived on. Found 2
> dev-server-ONLY testing artifacts while writing it (not production bugs, both worked around in
> the test): `React.StrictMode` (main.tsx) double-invokes `PopoutBridge`'s open effect in `vite
> dev` (open → cleanup closes it → open again) — collect every new page, wait for whichever one
> stays open; and `window.close()` inside Dock-back's handler fires synchronously, so
> `waitForEvent('close')` must race the click instead of awaiting it first (same pattern as the
> popup-open wait) or the event can fire before the listener attaches. 4/4 green ×3 runs; the 4
> pre-existing studio specs (12 tests) still green. Standards gate (Dockable Panel Standard —
> `panelCatalogContract.test.ts`+`dockablePanelHygiene.test.ts`) was already confirmed passing
> during the `/review-impl` pass above; no new cross-cutting standard was introduced by Phase 2,
> so nothing further to enforce.
>
> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE Phase 3 ✅ COMPLETE 2026-07-05 (Translate
> workmode).** Kickoff capability audit found the base port (`translation`/`translation-versions`
> panels) had **already shipped independently** via a parallel track on this shared checkout
> (`17_translation_enrichment_sharing_settings_docks.md`, commit `56c8e17c6`) — same deliverable,
> different framing. Re-verified against the post-commit code and found 3 real gaps (the Phase 3
> delta): no Studio panel for the block-aligned review workflow (`TranslationReviewPage`'s
> per-block correction + the "confirm corrected name into glossary" flywheel + the AC4 "adopt
> newer machine translation" banner); `TranslationViewer`'s Review button still `navigate()`d to
> the full-page route (DOCK-7 violation invisible to `dockablePanelHygiene.test.ts`, which only
> scans `features/studio/panels/**`); no one-click "Translate this chapter" affordance from an
> open `EditorPanel` (Studio only reached Translation via the matrix/palette/agent).
>
> **Explicitly rejected: porting legacy's Write/Translate/Read/Compose Workmode tab-switch
> itself** — would make `EditorPanel` internally swap its whole subtree by mode state, the exact
> DOCK-8 violation spec 17 just fixed for `EnrichmentView`'s 6-way switch. Shipped instead: (1)
> extracted `TranslationReviewView` (DOCK-2, props-based) out of `TranslationReviewPage.tsx` so
> the classic route and a new `translation-review` Studio panel (params-retargeting singleton,
> `{bookId, chapterId, versionId}`, hidden from palette + outside the agent enum — same precedent
> as `translation-versions`/`original-source`) both render it; (2) threaded an optional
> `onReview` callback through `TranslationViewer` → `ChapterTranslationsPanel` (both existing
> callers omit it, unchanged `navigate()` fallback proven via a new test) → `TranslationVersionsPanel`
> supplies `host.openPanel(...)`; (3) a "Translate" quick-access button in `EditorPanel.tsx`,
> same `host.openPanel` pattern as Phase 2's "Original Source" button.
>
> **`/review-impl`:** 1 LOW — `TranslationReviewView.tsx` sits outside `dockablePanelHygiene.test.ts`'s
> scan scope (same structural gap that let the original bug through), manually verified clean
> today; accepted as a repo-wide gap (Wiki/KG/Enrichment have the same exposure), not fixed
> narrowly here. **VERIFY:** tsc clean; 430/431 unit tests (the 1 failure is `user-guide`, a
> DIFFERENT concurrent session's in-flight panel not yet enum-synced — confirmed unrelated).
> **Live smoke with a REAL translate job** (local $0 model, ~10s): Editor → Translate button →
> Translation Versions → Review button → Translation Review panel renders real bilingual content,
> studio never navigates away. New committed `tests/e2e/specs/studio-translation-review.spec.ts`
> (2 tests, real job not a mock) green ×3 runs.
>
> **NEXT (register order, per spec 16's own roadmap):** Phase 4 (mobile-shell decision + full
> route retirement + `ChapterEditorPage` deletion), gated on a soak period per spec M9. #4
> AGENT-MODE (autonomy mission-control GUI) remains the largest unstarted "Cursor-for-novels"
> item — needs its own CLARIFY+DESIGN when picked up.

> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE Phase 1 ✅ COMPLETE 2026-07-04.** User approved the
> spec+plan (`approve, go`) and asked to proceed into BUILD; all of Phase 1 (spec
> [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md))
> shipped in one continuous run, 4 commits:
> - **P1 `f548859db`** — `ManuscriptUnitProvider.applyProposedEdit({operation, text, provenance})`
>   added as a real Tier-4 hoist action (thin wrapper over the same `editorRef` — the write and its
>   `onUpdate→setBody` wiring are byte-identical, only the CALL SITE moved off the global
>   `editorBridge` singleton). `editorBridge.ts` gained an optional `applyProposedEdit` field;
>   `ProposeEditCard.tsx` prefers it when present, falls back to `target.handle.*` otherwise —
>   legacy `ChapterEditorPage` (no hoist, omits the field) untouched.
> - **1.2/1.3/1.4 `16286995e`** — Checkpoints, Revision History, Publish Gate, built as 3 parallel
>   background agents (disjoint new files: `useManuscriptCheckpoints`+`ManuscriptCheckpoints`,
>   `useRevisionHistory`+`RevisionHistorySection`, `EditorPublishGate`), then integrated serially
>   into `EditorPanel.tsx`. Both restore paths are G7-guarded (refuse to overwrite a dirty hoist).
>   **`/review-impl` found + fixed a MED cross-hook bug**: Checkpoints and Revision History are
>   independent hook instances that both restore the SAME chapter's revision spine, built by
>   separate agents who didn't know about each other — a Revision-History-triggered restore left
>   Checkpoints' internal "latest revision" pointer stale, so the next AI-edit checkpoint would
>   capture the WRONG restore point. Fixed by watching `state.version` (bumped by any
>   save/reload/restore, whoever triggers it) instead of each hook's own narrower signal; a new
>   `crossHookRevisionSync.test.tsx` mounts both hooks against one real `ManuscriptUnitProvider`
>   and proves the fix in both directions.
> - **1.5 `f9ca330f3`** — `ChaptersTab.tsx`'s row-click, pencil icon, and post-create navigation now
>   open `/books/:id/studio?chapter=<id>` instead of the legacy `/chapters/:id/edit` route (Phase 1
>   parity reached — Studio is no longer strictly worse). `WritingStudioPage`/`StudioFrame` gained a
>   small `?chapter=` deep-link seam calling `host.focusManuscriptUnit()` once on mount — the same
>   seam Quick Open/Navigator already use, not a new mechanism. Legacy route untouched, still
>   reachable by direct URL (deletion is Phase 4, gated on a soak period per spec M9).
>
> **VERIFY:** 1108+ tests green across `features/chat`+`features/studio`+`features/books`+`pages`,
> `tsc --noEmit` clean (2 unrelated errors seen mid-session in `PressureGauge.tsx`/`WikiEditorPanel.tsx`
> were concurrent-session WIP, confirmed via `git status`, not mine). **3 separate live browser
> smokes** (each on a fresh vite port + fresh login, real backend, book `019ef35c`): (1) propose_edit
> insert → hoist-routed Apply → editor updated live → saved; (2) full Phase 1 combined — propose_edit
> → Checkpoints strip appears → Restore disabled while dirty → Save → Restore enabled → click Restore
> reverts the editor content live, Revision History shows real v1-v8 data, Publish Gate's
> Re-publish/Unpublish reflect dirty state correctly; (3) the route switch — clicking a chapter row
> on the book detail page opens Studio with the CORRECT chapter's actual content auto-focused (not
> whatever was last active).
>
> **NEXT:** superseded — see the Phase 2 ✅ COMPLETE entry above (2026-07-05).

> **"CURSOR-FOR-NOVELS" REGISTER — #1 COHERENCE SPEC+PLAN DONE 2026-07-04 (docs only, no build
> yet — user-scoped this pass as CLARIFY+DESIGN+PLAN only).** After #2 APPLY-DIFF shipped
> (`fb98f161f`, below), user asked to continue straight to #1 COHERENCE. Dispatched an Explore
> agent for a full capability audit of `ChapterEditorPage.tsx` (legacy) vs Studio v2 before
> designing anything — found **15 legacy-only capabilities with no Studio equivalent**
> (Checkpoints, Revision History, Publish Gate, Translate workmode, grammar check, glossary
> inline decoration/autocomplete, mention heatmap, AI-provenance tracking, selection
> toolbar/inline-AI, focus mode, auto-save, progress-reporting, original-source viewer,
> image/video upload-context+version-history, mobile shell, popout-insert-relay) plus 2 route
> entry points that don't coordinate (every chapter-row click → legacy; only one promoted header
> CTA → Studio). User confirmed via `AskUserQuestion`: **retire `ChapterEditorPage`, Studio
> becomes the sole surface** (not just unify entry points); this pass writes **spec + plan only**.
> Shipped: [`16_chapter_editor_parity_and_retirement.md`](../specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md)
> (locked decisions M1–M9, a risk-ordered 4-phase roadmap: data-safety → editor-craft UX →
> Translate → route-retirement, mobile shell left as an explicit OPEN product decision not
> resolved here) + [`2026-07-04-chapter-editor-studio-merge.md`](../plans/2026-07-04-chapter-editor-studio-merge.md)
> (Phase 1 build plan: fan-out shape, phase-agent contract, risk notes) + a new row 16 in
> [`00_OVERVIEW.md`](../specs/2026-07-01-writing-studio/00_OVERVIEW.md). **Self-caught correction
> during spec-writing:** the initial audit claimed the G7 dirty-guard (spec 09) was an
> unimplemented design hole — re-checked against code and found it's **already implemented** for
> the Lane-B reconciler (`bookEffects.ts` calls `isChapterDirty` before reloading); corrected both
> docs so Phase 1 has only ONE true prerequisite (P1: replace the `editorBridge` global singleton
> with a real `ManuscriptUnitProvider.applyProposedEdit` Tier-4 hoist action, per spec 08's own
> "Migration: editorBridge → bus + reconciler" section which already described this target shape
> without building it) rather than two. **NEXT:** BUILD Phase 1 — start with P1 (isolated,
> load-bearing, touches the exact files `fb98f161f` touched today), then fan out
> 1.2 Checkpoints / 1.3 Revision History / 1.4 Publish Gate (disjoint new files, serial
> integration into `EditorPanel.tsx`), then 1.5 the `ChaptersTab.tsx` route switch. Read the plan
> doc's Risk Notes before starting (unconfirmed `ChaptersTab.tsx` path, re-verify P1's target
> files haven't drifted under concurrent-session edits).

> **"CURSOR-FOR-NOVELS" REGISTER — #2 APPLY-DIFF FIXED + COMMITTED 2026-07-04 (`fb98f161f`).** Resumed the
> parked register (memory [[writing-studio-fragmented-not-underbuilt]]) — user asked to pick up
> the GUI-quality gaps now that context-budget-law is being carried by a separate concurrent
> session. Re-verified all 4 items against CURRENT code (the memory was 3 days stale) before
> picking one: **#1 COHERENCE** still broken (`ChapterEditorPage.tsx` vs Studio v2 still two
> workspaces) · **#2 APPLY-DIFF** confirmed still broken, root cause pinned exactly · **#3
> LIVE-SYNC** turned out far more built than the memory said (`bookEffects`/`glossaryEffects`/
> `knowledgeEffects` handlers all real, G7 dirty-guard implemented — grew via the Glossary/KG
> dockable-migration work, not a dedicated LIVE-SYNC effort) · **#4 AGENT-MODE** confirmed still
> 0% frontend (grep for `authoring_run`/`autonomy` across `frontend/src` = 0 hits). User picked
> **#2 (cheapest, already pinned)** to build first via `AskUserQuestion`.
>
> **Fix:** `EditorPanel.tsx` already calls `registerEditorTarget` (the `propose_edit` write-back
> target) whenever a chapter is open, but `ComposePanel.tsx` only ever passed `studioContext` to
> `<Chat>` — never `editorContext` — so chat-service (`stream_service.py` `_editor = bool(editor_context)`,
> ~line 1924/1685) never advertised `propose_edit` on the studio surface; the agent had no way to
> initiate a human-gated prose diff there. Fix: `ComposePanel.tsx` now derives
> `editorContext = { book_id, chapter_id: unitMeta.activeChapterId }` (same shape the legacy
> `ChapterEditorPage.tsx` already passes) whenever a chapter is open in the manuscript hoist,
> `undefined` otherwise (no false advertisement with no chapter open). Verified no side effects:
> `book_scoped` was already `true` in studio via `bookContext`, so skill injection / hot-domains /
> tool-iteration counts are unchanged — the only behavioral delta is `propose_edit` becoming
> advertised, which was the whole point. 2 new `ComposePanel.test.tsx` cases (editorContext
> present/absent) + 3 pre-existing pass unchanged (5/5); `tsc --noEmit` clean; full
> `features/studio` suite 479/479 green (1 unrelated contract-test failure was a `--root` CLI
> invocation artifact of my own test run, not a regression — re-ran in isolation, 3/3 green).
> **LIVE BROWSER SMOKE (evidence, not raw-stream — vite :5199 → gateway :3123, real local
> `google/gemma-4-26b-a4b-qat` model, $0 spend, book `019ef35c` "Dracula (fresh agent journey)"):**
> opened Studio → opened Chapter II in the Editor panel → opened Compose → asked the agent to
> rewrite the first paragraph → agent called `composition_get_prose` then **`propose_edit`** → the
> C6 hunk-review card rendered in the Studio Compose panel for the first time ever → clicked
> Apply → the Studio manuscript editor updated live (55→74 words, "● unsaved") → Save persisted
> it. Closes the loop end-to-end on the surface where it was previously impossible. **`/review-impl`
> caught + fixed a HIGH before commit:** `AssistantMessage.tsx` renders `<ProposeEditCard record={tc} />`
> with no `chapterId` prop, so the card's own "never write into a different chapter" guard was
> DEAD CODE in production — on Studio's persistent Compose dock (unlike the legacy page, which
> only keys `<Chat>` by `bookId` and thus shares the same latent gap, just less reachable),
> switching chapters while a proposal is pending then clicking a stale Apply would silently splice
> text into the wrong chapter. Fixed in `ProposeEditCard.tsx` by self-deriving the guard's target
> chapter from the live editor bridge AT MOUNT instead of the never-supplied prop — 3 new
> regression tests, no prop-threading needed through the shared message-list chain. **Committed
> `fb98f161f`** (both the wiring fix and the review-impl fix, 4 files). #1 COHERENCE picked up
> next per the memory's own priority order — see the block above for its spec+plan output. #3
> LIVE-SYNC should still get an audit pass (does `composition_generate`/authoring-run/
> translation-job writes reach the reconciler?) before assuming full coverage. #4 AGENT-MODE
> (autonomy mission-control GUI) remains the largest unstarted lift (engine exists server-side,
> zero FE) — needs its own CLARIFY+DESIGN when picked up.

**KNOWLEDGE/KG DOCKABLE MIGRATION — PHASE A + PHASE B ✅ SHIPPED 2026-07-04.** Spec: [`docs/specs/2026-07-01-writing-studio/14_kg_panels.md`](../specs/2026-07-01-writing-studio/14_kg_panels.md) (row 14 in `00_OVERVIEW.md`). Phase A (commit `4c50f7ae2`, see prior entry below for detail) shipped the shared foundation: `useBookKnowledgeProject` hook, the `knowledge` hub launcher panel, `VersionsPanel`'s DOCK-9 fix, `knowledgeEffects.ts` Lane-B wiring. **Phase B — all 12 capability panels shipped via parallel fanout** (12 background agents, each building one panel + its own tests with zero shared-file edits, followed by ONE serial integration pass adding all catalog/i18n/BE-enum entries together — avoided the N-way race on `catalog.ts`): `kg-overview` (book-scoped, DOCK-7 fix on `OverviewSection`'s 2 backlink `<Link>`s → callback props), `kg-entities`/`kg-timeline`/`kg-evidence` (shared scope via optional `params.scopedProjectId`, K4), `kg-gap` (book-scoped), `kg-proposals` (book-scoped via `host.bookId`, DOCK-7 fix on `ProposalsInboxTab`'s `<Link>` → `onOpenRow` callback), `kg-schema` (book-scoped, the K6 bundle — absorbs the whole ontology adopt/schema/views/sync flow as ONE panel; 2 more DOCK-9 fixes — `GenerateSchemaDialog`+`SchemaWorkbench` → `FormDialog`/`ConfirmDialog` — plus a DOCK-7 fix on `CreateSchemaEntry`'s Link), `kg-graph` (book-scoped), `kg-insights`/`kg-jobs`/`kg-bio`/`kg-privacy` (user-scoped, global, no book/project resolution). All 12 use `followStudioLink`/`host.openPanel` instead of `navigate()` where they link out — unmapped paths fall through to a new-tab open today (honest, not a silent no-op), upgrading in-tab automatically as sibling routes gain panel mappings. **`/review-impl` (1 MED, fixed):** `useBookKnowledgeProject` filtered client-side over only the first cached page of the user's projects (`useProjects(false)` + `.find()`) instead of using the BE's existing server-side `book_id` query filter — a user with >100 KG projects whose linked project sorted past page 1 would silently get a false "no project linked" empty state across all 5 book-scoped panels. Fixed by threading a `bookId` param through `useProjects`/`ProjectsQueryParams` into the BE filter (confirmed live in `services/knowledge-service/app/routers/public/projects.py`), with a regression test simulating 150 filler projects. **VERIFY:** FE 562 files/3892 tests green + tsc clean; chat-service 927 tests green; `ai-provider-gate.py` clean — all re-run after this landed alongside Glossary's own Phase B and the separate "utility panels" dockable track on the same checkout (additive merges throughout, no collisions; contract regenerated to include every track's panel ids). **NEXT:** cross-panel E2E wiring (hub → capability panel drill-down) may defer per the spec's debt-stack convention until ≥2 panels are used together in a real flow; otherwise Phase B is feature-complete per the spec. **studioLinks.ts wiring done same session:** mapped every global KG path (`/knowledge`, `/knowledge/projects`, `/knowledge/{jobs,global,entities,timeline,raw,insights,privacy}`) to its `kg-*` panel, and same-book `/books/:id/glossary` → the `glossary` panel — these upgrade `kg-proposals`/`KnowledgeHubPanel`'s links from new-tab to in-tab automatically, zero panel-side changes needed. Deliberately did NOT map `/knowledge/projects/:id/:section` (project-id-keyed): the `kg-*` panels resolve "the CURRENT book's project" via `useBookKnowledgeProject`, not an arbitrary `:id` — mapping it would silently show the wrong project whenever `:id` isn't this book's project (e.g. the hub browsing a different book's or a standalone project). Wiki/enrichment pages stay external too (no dock panel exists for them yet).

> **UTILITY PANELS (Jobs / Books Browser+Reader / Leaderboard) — ✅ COMPLETE 2026-07-04.** Spec
> [`14_utility_panels.md`](../specs/2026-07-01-writing-studio/14_utility_panels.md) + fan-out plan
> [`2026-07-04-utility-panels-fanout.md`](../plans/2026-07-04-utility-panels-fanout.md). Scoped from
> a 5-area ask ("user settings, notifications, job monitor, book browser, leaderboard") down to 3
> real build items after investigation: **Settings/Notifications were already fully dockable** (no
> action), **Books/Leaderboard were structural mismatches** for a per-book studio dock (global,
> cross-book surfaces) but the user explicitly wanted them anyway — redesigned Books as a pure
> browse-then-read capability (no DOCK-7 exception needed) and Leaderboard as a DOCK-8 fix (4
> sibling panels instead of one internal tab-switch). **Shipped:** `jobs-list`+`job-detail`
> (`20e6019c5`), `books`+`book-reader` (`e4d64903e`), `leaderboard-{books,authors,translators,
> trending}` (bundled into `b767fb4c0` by a concurrent session's commit — see below), spine wiring
> (`e72f73b59`), `/review-impl` fixes (`37898fc16`: 2 HIGH — a campaign-kind job clicked inside the
> new Jobs panel opened the wrong detail view because the injectable onOpenDetail callback ignored
> job.kind, fixed in `JobRow.tsx`+`JobsMobile.tsx`; 1 MED — `useReadingTracker` could flush with an
> empty chapterId during BookReaderPanel's async first-chapter resolve, guarded in the shared hook).
> **Caught a real contract gap:** `panelCatalogContract.test.ts` enforces the agent enum ==
> palette-openable set EXACTLY (not a subset as the spec assumed) — `books` + all 4 leaderboard
> panels had to join `ui_open_studio_panel` too, not just `jobs-list`. **3 parallel Agent-tool
> subagents built B/C/D concurrently** (no worktree isolation — disjoint files only), then this
> session integrated serially (re-diffed spine files before each apply). **Live proof multi-session
> contention is real, not theoretical**, on this exact branch during this exact task: a concurrent
> session's bare `git commit` (no pathspec) swept this session's 11 already-staged Phase D files
> into an unrelated `docs(eval)` commit mid-integration; another concurrent session committed KG
> Phase A between this session's `git diff --cached` check and its next edit. Nothing was lost —
> content is correct and tested — but attribution in `git log` is muddled for `b767fb4c0`. No
> further utility-panel phases queued.

> **GLOSSARY DOCKABLE MIGRATION — ✅ PHASE A + PHASE B BOTH COMPLETE 2026-07-04 (committed `97e1b5a2a` + `4f0e1a1b8`).** Full history was in this file's top block before a concurrent commit (Knowledge Hub track, `4c50f7ae2`) overwrote it — detail lives in [`docs/specs/2026-07-01-writing-studio/13_glossary_panels.md`](../specs/2026-07-01-writing-studio/13_glossary_panels.md) (both phases, verify evidence, the `/review-impl` findings) and [`docs/standards/dockable-gui.md`](../standards/dockable-gui.md) (the new DOCK-8/DOCK-9 rules this effort authored). Short version: all 5 Glossary capabilities are now real studio dock panels (`glossary`/`glossary-ontology`/`glossary-unknown`/`glossary-ai-suggestions`/`glossary-merge-candidates`), all 6 hand-rolled modals are DOCK-9 compliant (`FormDialog` or raw `Dialog.*`). No further Glossary phases queued. **Note for future sessions:** this repo currently runs multiple concurrent Claude Code sessions against the SAME working tree/branch (`feat/context-budget-law` — unrelated name, just where everyone happened to be checked out) — shared spine files (`catalog.ts`, `frontend_tools.py`'s panel enum, all 4 `studio.json` locales, `contracts/frontend-tools.contract.json`, this file's top block) get swept into whichever session commits next, sometimes before the "owning" session's own commit. Verify `tsc --noEmit` after any commit involving these files — a dangling import (catalog.ts referencing a component file another session hasn't committed yet) is the concrete failure mode this hit once already.

**KNOWLEDGE/KG DOCKABLE MIGRATION — PHASE A ✅ SHIPPED 2026-07-04.** Spec: [`docs/specs/2026-07-01-writing-studio/14_kg_panels.md`](../specs/2026-07-01-writing-studio/14_kg_panels.md) (registered in `00_OVERVIEW.md` row 14). Scoping found the KG/Knowledge surface bigger than Glossary's (#13): 2 route-driven tab hubs (`KnowledgePage` 8 tabs + `ProjectDetailShell` 9 sections) collapsing to ~13 unique panels once shared components are recognized; a global cross-book hub (a KG project's `book_id` is optional) migrates too, per the human's K1 call, as **user-scoped** panels (same tenancy tier as Settings/Usage) rather than fighting the book-scoped Studio model. Shipped this session (A1-A4, shared foundation): **A1** `useBookKnowledgeProject(bookId)` hook extracted from `KnowledgeOntologyTab`'s inline lookup. **A2** `knowledge` hub launcher panel (DOCK-8's "launcher, not host" escape hatch) — `ProjectsBrowser` extracted from `ProjectsTab` (DOCK-2/DOCK-7, shared by the classic route and the new panel), opens a project via the studio link resolver (`followStudioLink`) instead of `navigate()` — falls through to a new-tab open on the classic route today (no Phase-B panel registered yet), upgrades to in-tab automatically once one lands; catalog+i18n×4+BE enum+contract all wired. **A3** `VersionsPanel`'s 2 hand-rolled `fixed inset-0` modals migrated to `FormDialog`/`ConfirmDialog` (the DOCK-9 adoption precedent) — the 4th grep hit (`MemoryIndicator`) was investigated and found to be a FALSE POSITIVE (an accepted anchored-popover pattern shared with `NotificationBell`, not a hand-rolled modal — spec corrected). **A4** `knowledgeEffects.ts` Lane-B handler for `kg_*` MCP writes, invalidation keys verified 1:1 against every actual read-hook query key (no drift) — wired into `useStudioEffectReconciler`. **`/review-impl` (1 MED, fixed):** the FormDialog/ConfirmDialog migration introduced a flash-of-blank-content during Radix's ~150ms close animation — same bug class already fixed once in `ProjectsBrowser`'s archive/delete dialogs (K8.2-R6); fixed with the same last-shown-value ref pattern (not jsdom-testable — same limitation as the precedent it mirrors). **VERIFY:** FE 546 files/3777 tests green + tsc clean · chat-service 927 tests green · `ai-provider-gate.py` clean — re-run AFTER a concurrent Glossary Phase B landing in the same shared spine files (`catalog.ts`, all 4 `studio.json` locales, the `ui_open_studio_panel` enum + contract) merged in cleanly (additive, no collision). **NEXT: Phase B fanout** — 12 disjoint panel slices (overview/entities/timeline/evidence/gap/proposals/schema-bundle/graph/insights/jobs/bio/privacy), safe to parallelize per [[fanout-independent-slices-parallel-build-serial-integrate]] now that Phase A's shared foundation exists.

> **⚠ BRANCH NOTE:** the work below (Dockable Panel Standard + Glossary Phase A+B) was done on the checked-out branch `feat/context-budget-law`, but is UNRELATED to that effort (studio/dockable-migration track vs. context-budget-law track — multiple parallel tracks landed on the same checkout, incl. a concurrent Knowledge Hub dockable-panel effort). Consider splitting onto its own branch. The context-budget-law history is preserved below, untouched.

**DOCKABLE PANEL STANDARD + GLOSSARY MIGRATION — ✅ PHASE A + PHASE B BOTH COMPLETE 2026-07-04 (Phase A committed `97e1b5a2a`; Phase B uncommitted).** Triggered by scoping the Glossary dockable migration (next in the [`12_json_document_standard.md`](../specs/2026-07-01-writing-studio/12_json_document_standard.md) cycle queue after chapter editor) — found the studio's dockable-panel rules were never consolidated into a standard doc (a known gap in `docs/standards/README.md`).

1. **[`docs/standards/dockable-gui.md`](../standards/dockable-gui.md)** (new) — consolidates 08/11/12 into DOCK-1..11, adds **DOCK-8** (no internal page-replacement view-switch) and **DOCK-9** (no hand-rolled `fixed inset-0` overlay — adopt `FormDialog`/`ConfirmDialog`, or raw `Dialog.*` from `@radix-ui/react-dialog` for custom-chrome dialogs like `EntityEditorModal`). Enforced by `dockablePanelHygiene.test.ts` (recursive scan, order-independent token check — a `/review-impl` pass caught and fixed 2 real gaps in the test itself).
2. **[`13_glossary_panels.md`](../specs/2026-07-01-writing-studio/13_glossary_panels.md)** (new) — Glossary re-scoped as **shared-foundation-then-fanout** (7 sub-features, 3 DOCK violations found — too large for a flat single cycle). **Phase A (serial, A1-A6):** `useGlossaryEntity` hook + `loreweave.glossary-entity.v1` JSON provider extracted from `EntityEditorModal` (→ raw `Dialog.*`) · `GlossaryEntityList` extracted from `GlossaryTab` (DOCK-2, shared with the new `glossary` panel) · `glossary` panel added to catalog + agent enum (contract regenerated) · `ResolveKindModal` → `FormDialog` (the DOCK-9 precedent) · `glossaryEffect` Lane-B handler · `StepConfig`'s settings link fixed via `useOptionalStudioHost()`. **Phase B (8-way parallel fanout, this session):** the 4 remaining glossary capabilities promoted to real sibling dock panels (`glossary-ontology`/`glossary-unknown`/`glossary-ai-suggestions`/`glossary-merge-candidates` — `GlossaryPanel`'s temporary internal view-switch is GONE, replaced with real `host.openPanel(...)` cross-panel jumps) + the last 4 hand-rolled modals migrated (`CreateEntityModal`/`BatchTranslateDialog` → `FormDialog`; `GlossaryTranslateWizard`/`ExtractionWizard` → raw `Dialog.*`, both having a pinned step-indicator FormDialog's template can't hold). Serial integration (catalog/i18n×4/BE-enum/contract, done by the orchestrating session, NOT the fanout agents) avoided the shared-file collision the parallel build would otherwise hit.
3. **NEW DEFERRED (tracked, gate #1 out-of-scope):** `AddModelCta.tsx` + ~14 consumers (incl. **already-shipped** `PlannerPanel`, `CompositionPanel`) have the SAME DOCK-7 route-navigate defect A6 just fixed locally — needs one fix at the shared component, not per-site. See `13_glossary_panels.md` for detail.

**VERIFY (Phase B):** full FE suite 545 files/3768 tests (1 unrelated failure — `VersionsPanel.test.tsx`, uncommitted WIP from the concurrent Knowledge Hub track, not this effort) · `tsc --noEmit` clean · the 14 Phase-B test files in isolation 112/112 · BE `test_frontend_tools.py`+`test_frontend_tools_contract.py`+`test_agent_surface.py` 74/74 (checked both known snapshot locations, learning from the Phase-A miss) · i18n parity clean for the 4 new key sets. **NEXT:** decide whether to commit Phase B (staged carefully to exclude the concurrent Knowledge Hub / context-budget-law files, same discipline as the Phase A commit) — Glossary's dockable migration is then fully done (all 5 capabilities are real panels, all 6 modals DOCK-9 compliant); no further Glossary phases queued.

**VERIFY:** FE full suite 524 files / 3628 tests green · `tsc --noEmit` clean · chat-service `test_frontend_tools_contract.py` 21/21 (regenerated + reverified) · i18n parity clean for new keys (pre-existing unrelated gaps untouched). **NOT committed** — user has not yet asked to commit. **NEXT:** Phase B fanout (4 remaining panels: ontology/unknown/ai_suggestions/merge_candidates + 4 remaining modal migrations: CreateEntityModal/ExtractionWizard/GlossaryTranslateWizard/BatchTranslateDialog) — genuinely disjoint files now, safe to parallelize per [[fanout-independent-slices-parallel-build-serial-integrate]]. Consider the `AddModelCta` sweep too (small, independent, high-value since it's a live bug in shipped panels).

---

**CONTEXT BUDGET LAW — IMPLEMENTATION IN PROGRESS on branch `feat/context-budget-law` (off merged main), 2026-07-04. STANDING RULES (autonomous run): test-model = local `google/gemma-4-26b-a4b-qat` (12b is 8K, too small); DEFER-DON'T-BLOCK (anything needing the user's judgment → a Deferred row here + continue, never hard-stop); quality-gate = a judge subagent CHATS the live agent + scores a rubric + writes an md report ([`docs/specs/context-budget-quality-gate.md`](../specs/context-budget-quality-gate.md)) → decide PASS/REGRESS/NEEDS-HUMAN; durability = git commits + spec §8a + this block (on resume: `git log --oneline`, spec §8a, the todo list); REVIEW-IMPL GATE = every todo item gets a cold-start adversarial review (parallel subagents) before it's marked done → fix HIGH/MED now, defer the rest (tracked here). DONE (committed): T0 wire-hygiene (−3.6% real), T1-flagship response-contract (outline −74%/−99% live + jobs_list + kit helper `apply_response_contract` + worst-first manifest), T2 task-elastic target + meter accuracy (live gate ±22% safe-high), T4-SUBSTRATE (`chat_session_blocks` + `story_state` + OCC, real-PG tested). REVIEW-IMPL GATE applied to T0/T1/T2/T4 (4 cold-start review subagents, commit `5706295a0`): all MED fixed (T0 meter over-counted VI/CJK; T1 get_outline_node had no IDOR test + was missing from the public-MCP allowlist; T4 distill blew the token cap 2-3× for CJK/VI) + cheap LOWs; only the T2 FE↔BE breakdown-vocab drift deferred → Inspector-FE. **⚠ DEFERRED — EVAL-BOOK GAP (D-EVAL-BOOK, gate #4 blocked-on-infra→BUILDABLE):** no dev-DB book currently has agent-retrievable KG lore (POC books have no knowledge project; `entity_canonical_snapshots` + knowledge passages are EMPTY globally, incl. Dracula). The quality-gate's *answer-correctness* A/B needs a lore-populated book → must SEED one (extraction pipeline; scripts `run_dracula_fresh_journey_kg.py`/`seed_fengshen_demo.py`). Unblocks: the T5 answer-correctness judge run + the harness real A/B. NOT blocked: T5 gate-decision correctness + token-savings smoke (a no-lore MESSAGE skips build_context regardless of book lore). NOW: quality-gate harness CODE (driver+judge+report — smoke-able on any session) → T5 grounding intent-gate (+T4 wiring: skip build_context on no-lore turns, project `story_state` net) validated by gate-decision + token-savings; answer-correctness deferred to D-EVAL-BOOK. Family B (MCP SET tools) + Inspector + §13 are fully unblocked in parallel. **FAMILY-B REFACTOR DONE (2026-07-04, commits `d856…`+`b458…`):** 18 SET tools refactored to reference-first across translation + composition-motif + knowledge (3 parallel disjoint-service subagents, each review-gated + re-verified; suites 1039/1490/3496 green), 6+ `@small_return` exemptions; see [`context-budget-t1-refactor-manifest.md`](../specs/context-budget-t1-refactor-manifest.md) §Family-B-completion. **Remaining B:** contract-snapshot harness (§13b) + live-e2e per tool (composition/outline drop proven −74%; knowledge/translation live drop gated on D-EVAL-BOOK data). **⏩ SESSION-CONTINUED 2026-07-04 (autonomous, 5 commits): (1) §13b RESPONSE-SHAPE SNAPSHOT HARNESS ✅ `78fcaa885` — `contracts/mcp-response-shapes/{composition,knowledge,translation,jobs}.json` pins all 15 ref-field constants; shared kit helper `loreweave_mcp.assert_or_write_shape_snapshot` (regen `WRITE_MCP_SHAPES=1`); catches drift BOTH ways; guard proven-to-bite; coverage-audited. (2) QUALITY-GATE HARNESS ✅ `1e2d84e6c` — `scripts/eval/{run_quality_gate.py,context_budget_scenarios.json,judge_prompt.md,README.md}`; in-container DRIVER (minted JWT, SSE+GET fallbacks) captures reply+contextBudget+tools/turn; BLIND judge template; mechanically proven live (gemma-4-26b). (3) T5 SLICE 1 ✅ `4f1d73ecb` — entity-presence gate substrate (`entity_presence.detect_entity_presence` word-bounded ASCII/CJK, BIAS-TO-INCLUDE on empty-set/anaphora/lore-intent) + `known_entities_client` (glossary `/internal/books/{id}/known-entities` VERIFIED route + TTL cache + degrade-to-empty) + config + lifespan. (4) T5 SLICE 2 ✅ `c9a6c46ad` — knowledge `build_context`+route take `grounding:bool=True` (False→light static path, ROUTING-only, mode fns byte-identical, +3 tests); chat forwards it + threads `entity_presence` telemetry through `_emit_chat_turn`; `T5_INTENT_GATE_ENABLED` kill-switch. **T5 LIVE A/B (docs/eval/context-budget/T5-2026-07-04.md):** gate CORRECT+SAFE cross-service (status_op gates OUT, all lore/discovery/continuity stay grounded, ZERO false-negatives, no correctness regression); **token-saving INCONCLUSIVE on Dracula POC** (gating status_op saved 0 tok — build_context retrieval is already query-relevance-scaled) → token win needs D1 pull mode OR a heavy-retrieval seeded KG (folds into D-EVAL-BOOK); gate ships safe/flag-gated/tested (114 chat+12 knowledge green). (5) §13 COVERAGE META-CHECK ✅ `41e3414ac` — `assert_or_write_shape_snapshot(…, scan_modules=[…])` introspects each service's tool modules for every `*_REF_FIELDS` and asserts it is snapshot-pinned (a new un-pinned constant → RED; "checklist→test not self-report"); bite-proven in the kit test; CI-wired via each service suite. **⚑⚑ SESSION SELF-AUDIT (2026-07-04) — the strategic decision-point below was RETRACTED.** A 3-reviewer cold-start audit + a T5 measurement re-audit found: (1) the T5 "token thesis weakened → T3 optional" decision was INVALID — the gate had a production NO-OP bug (fed a knowledge project_id to a book_id route → always []→ never fired) AND the A/B was confounded (Dracula book has no KG project → grounding degraded in both arms) AND the 28K→120K split was the 41K MCP tool catalog × tool-loop passes, not grounding. (2) A summary-truncation HIGH regression I introduced (D6 made summaries longer, no finish_reason guard → silent tail loss). (3) §13 meta-check over-claimed (convention- not call-site-scoped). FIXES SHIPPED: `f6707d65c` summary-truncation guard · `0c0b212cc` §13 call-site (reject inline ref literals) + eval-harness MEDs (_budget_total order, session cleanup, WRITE_MCP_SHAPES CI guard) · `33a954036` T5-BUG (project→book_id resolution route + cached resolve_book_id + multilingual bias-to-include CJK/VN/question, meta carve-out) · `b6ef10ba6` 2 live-caught gate bugs (em-dash non-ascii, junk 1-char token). **T5-BUG fix LIVE-VALIDATED** (Dracula-linked KG project `019f2be0`): the gate now FIRES correctly (smalltalk/status→gated out, lore/discovery/anaphora→open). **T5 token-SAVINGS NOW QUANTIFIED = ~0 → KILLED as a token optimization.** Pushed the full pipeline: created Dracula KG project `019f2be0` → fixed a `kg_run_benchmark` NameError (`c8edb30ec`) → benchmark PASSED → extracted 2 chapters (full mode) → clean gate ON vs OFF A/B on the SAME no-lore turn: **gate saves ~48 tok (~0.16%)** — grounding block is ~1.1K in BOTH static and full mode, negligible next to the **~41K `mcp_tool_schemas` catalog** that dominates every turn (lore turn 120K = catalog × tool-loop passes). **ACTION:** `t5_intent_gate_enabled` **defaulted OFF** (config+compose); code kept (correct/safe/tested — residual value = compute/latency + telemetry + D1 pull substrate). **⚠ CORRECTION #2 (same day): the "41K catalog is the real lever" was ALSO a measurement artifact** — the driver used LEGACY stream format (full catalog); the real frontend uses AGUI where tool DISCOVERY trims the catalog to **368 tok** (agui turn=4.9K vs legacy=29.7K on the same turn). So tool-catalog trimming is NOT a real-user lever — RETRACTED. Driver now defaults to agui. Real agui turns are lean (~5K simple; a lore turn's ~21K is AGENT BEHAVIOR — subagent spawn + kg_graph_query — not catalog/grounding). The effort's real wins were T0 (ensure_ascii) + T1 (reference-first tool RESULTS, the original 146K fix). **T5 net: default OFF stands, but honest reason = full≈static grounding for a THINLY-extracted book (gate saves ~40 tok); genuinely UNPROVEN for a rich book.** ROOT CAUSE the rich-book A/B couldn't be produced: the Dracula KG project `019f2be0` was created via SQL WITHOUT a graph schema → extraction yielded entities=0 → thin grounding (memory_knowledge 88–1126 tok, no passages section). A real rich-grounding seed needs the FULL KG authoring pipeline (schema→benchmark→extraction), several gates deep (a 2nd extraction also wedged — likely LM Studio queue). So T5's rich-book value is unmeasured-not-disproven; the honest measurement bottoms out here on the available infra. Bonus: `019f2be0` (Dracula KG, benchmark-passed, 2ch extracted) partially resolves D-EVAL-BOOK. Full findings: `docs/eval/context-budget/T5-2026-07-04-CORRECTED.md`. **⚑ NEW TRACKED BUG (user-identified during the seed) — D-EXTRACTION-SILENT-NOOP (MED, gate #2):** the extraction pipeline can report `status=complete` (success) having made 0 LLM calls / produced 0 entities, with NO signal — an observability + data-validation gap (no output-validation, no input schema-check, no stall detection). Evidence + fix plan in `docs/deferred/D-EXTRACTION-SILENT-NOOP.md`. A correct fix needs the extraction saga's finalization chokepoint located (distributed worker+saga+event; NOT `extraction_jobs.complete()`). **RETRACTED** ▼ (kept for history):
**⚑ STRATEGIC DECISION-POINT for the user (defer-don't-block, rule #3):** the T5 live A/B showed the token-saving thesis for intent-gating is largely REDUNDANT with build_context's existing query-relevance scaling on real workloads (the big 146K wins were already banked by T0 ensure_ascii + T1 reference-first). This weakens the token-win justification for the remaining PURE-REFACTOR **T3 kernel extraction** (byte-identical, no token win — its value is code-reuse for the roleplay consumer, not tokens). T6 (long-conversation fact-retention) + Inspector (observability, surfaces entity_presence) remain valuable REGARDLESS of the token thesis. **Recommendation pending user:** do T6 + Inspector next (valuable independent of tokens); treat T3 as OPTIONAL (do it only if the roleplay-consumer code-reuse is wanted). (6) T6/D6 FACT-PRESERVING SUMMARY ✅ `c7eddba66` — compaction summarizer now emits a two-section FACTS/SYNOPSIS structure (verbatim entity/decision/established/open-thread list = system of record, then prose; names EXACT; max_tokens 700→900). LIVE-PROVEN gemma-4-26b: 4/4 planted facts KEPT incl. VN name "Lâm Uyển" verbatim (docs/eval/context-budget/T6-summary-2026-07-04.md). NEXT unblocked (all LARGER central-path, for a fresh context): **T6-remainder** = atom-safe reversible collapse + resume-monotonic ([[compaction-resume-path-carries-tool-pairs]] class, partly handled by existing `_atoms`) + `conversation_search` recovery tool (design: where a session-history-search tool lives) + flip the compaction TRIGGER to the T2 task-elastic `compute_target`; **Inspector GUI** (BE TraceSpan telemetry + dockable FE panel + `context-trace.contract.json` + §11 86-item checklist — note `entity_presence` + `grounding` are ALREADY in the frame, ready to surface); **live-e2e per SET tool** (composition proven; rest gated on D-EVAL-BOOK data); **T3 kernel** — **IN PROGRESS (user chose to continue T3 as the optimization testbed). Plan: [`2026-07-04-t3-context-kernel.md`](../plans/2026-07-04-t3-context-kernel.md). T3.1 ✅ DONE (see COMMIT): new `sdks/python/loreweave_context` kernel + `build_system_message` renderer unifies chat's two lockstep system-prompt ladders (A1 footgun) into ONE ordered `tail_blocks` list, byte-identical (7 golden cases + 926 chat tests green — the 1 red is the parallel studio track's `ui_open_studio_panel` glossary-enum drift, NOT mine). NEXT SLICES: T3.2 CompilePlan+Planner (the swappable policy seam for A/B), T3.3 Compiler+CompactionStrategy, T3.4 package + voice/roleplay consumer. Then A/B optimization hypotheses via the quality-gate harness.** (7) T6/D6 CONVERSATION_SEARCH RECOVERY ENGINE ✅ `a910b415f` — `app/db/conversation_search.py::search_session_messages`: the search half of the D6 safety net (pull back a fact dropped from the summary; raw turns stay in PG). Case-insensitive ILIKE SUBSTRING (multilingual — a recovery query is a NAME `Lâm Uyển`/`万古神帝` that English `to_tsvector` stems wrong), session+owner+branch-scoped, error rows excluded, limit-clamped, LIKE-metachars escaped. Real-PG tested (7 — the live test CAUGHT a broken ESCAPE clause a mock passed). **PRECISE NEXT SLICES (all touch the central stream_service tool-dispatch loop / a large GUI — best for FRESH context):** (a) ✅ **DONE this session (see COMMIT below)** — conversation_search FULLY WIRED into the tool loop: advertised at depth 0 in `_stream_with_tools` ONLY when the pass already offers tools (guards `test_no_tools_no_schema_chunk`); local dispatch branch before run_subagent using `get_pool()` (pure read, no write-budget decrement, never a silent no-op); `run_conversation_search` SHAPER added to `app/db/conversation_search.py` (empty-query prompt / no-hits message / hits shape / DB-error→`{"error"}`); `conversation_search`→`SERVER_KEY_CHAT` in `agent_surface.server_key_for_tool`. 7 new tests (5 shaper + 2 dispatch-EFFECT proving the model call runs in-process + maps error→not-ok) + 5 exact-surface test updates (test_stream_tools/test_agent_surface/test_permission_modes/test_plan_mode). Full chat suite **917 green**. The ENGINE + tool DEF were already DONE+tested (`a910b415f`+`99188c5c1`). (b) ✅ **BUILT + LIVE-VALIDATED this session (see COMMIT below), default OFF** — task-elastic compaction trigger wired: `compact_messages(target=…)` fires at `compute_target(context_length, task_weight)` instead of flat `0.75×effective_limit`; `task_weight` = 1.0 for a grounding turn (T5 `entity_presence.grounding_needed`) else `compact_light_task_weight` (0.5); flag `COMPACT_TASK_ELASTIC_ENABLED` (config, default OFF) + 3 unit tests. **LIVE A/B (gemma-4-26b 40K reg, plant→pad→recall, `docs/eval/context-budget/T2-compaction-trigger-2026-07-04.md`): candidate compacts 17.5K→4.7K (~73% cut) at the soft 14K target AND recalls all 3 buried facts from the summary FACTS (tools=[]) — ZERO quality loss; baseline (flat 28K) never fires. The live run CAUGHT a `_grounding_presence` scope NameError (flag-ON path, unit-tests missed) → fixed to read the `entity_presence` telemetry dict.** DEFAULT STAYS OFF pending a broader gate (multi-fact-type + light-target judge run + summarizer-call-frequency cost across all users; big-window models rarely reach the target so the win is mainly small-window / long sessions). Safe to enable per-deployment. **BROADER JUDGE RUN (user-requested, same doc): 4 fact-types + LIGHT target (T5 gate ON + Dracula-KG-bound → status turns classify light ~9K) + blind judge subagent. Result MIXED — SAFE but LOSSY: candidate compacted 18.0K→5.6K (~69% cut), recalled 8/9 fact-tokens but DROPPED one number (the "seven star-anchors" count), and critically did NOT confabulate (honest "I don't have that info") — blind judge scored candidate correctness 4/5 vs baseline 5/5, `critical_confabulation=false` both. gemma did NOT self-recover via conversation_search (tools=[]) — the net is built but unused. DECISION: default STAYS OFF (safe but a real minor recall regression at the aggressive light target). Highest-leverage unblock to justify default-ON = a system hint to CALL conversation_search on a post-compaction turn (the net exists; the gap is USAGE).** **⇒ FIX SHIPPED (user insights): (1) recovery HINT (nudge model to call conversation_search post-compaction) — built + tested, but gemma IGNORES it (4 runs, 0 tool calls) → default OFF, kept for stronger models. (2) DETERMINISTIC BREADCRUMB (`compaction.extract_breadcrumb`, default ON): regex-extract number-sentences+quoted-names+proper-phrases VERBATIM from the compacted turns BEFORE the lossy LLM summary + a `Keywords:` recovery-index line in the summarizer prompt + a "don't over-compress" nudge. RESULT: light-target recall floor 1/9→9/9, variance ELIMINATED (3/3 runs 9/9 = matches uncompacted baseline) at ~68% token cut (~150 tok breadcrumb cost). QUALITY BLOCKER RESOLVED — task-elastic is now much closer to default-on-ready; remaining gate = operational (summarizer-call frequency cost + broader-scenario sweep), user's call. Full detail in the eval doc.** **⇒ FLIPPED DEFAULT-ON 2026-07-04 (user call) after a broader sweep: 2 scenario shapes (ALLCAPS + natural-cased date/qty/relationship/list, 8-turn) × 2 runs on the shipped default (task-elastic + breadcrumb ON) = ~9/9 recall all 4 (one 1-char name-spelling model slip) at ~68% cut. `COMPACT_TASK_ELASTIC_ENABLED` now True; operational notes stand (big-window 200K ≈ no-op since target caps ~32K; more summarizer calls on long chats; raise `_TARGET_MAX_CAP` for heavy-context headroom; set flag False to revert to flat 0.75×window).** Remaining (c); (c) INSPECTOR GUI (BE TraceSpan telemetry + dockable FE panel + `context-trace.contract.json` + §11 86-item checklist; `entity_presence`+`grounding`+`breakdown` ALREADY in the frame, ready to surface). This session: **11 commits** (78fcaa885 §13b · 1e2d84e6c quality-harness · 4f1d73ecb+c9a6c46ad T5 · 41e3414ac §13-meta · c7eddba66 T6/D6-summary · a910b415f T6/D6-convsearch-engine · 4 handoff). All green + live-proven; branch always-green.** ▼prior: NEXT unblocked: contract-snapshot harness · T5 gate-decision+token-savings · T3 kernel · T6 · Inspector · §13 CI-meta. REMAINING (maximal scope, user-approved 2026-07-04): **B** = ALL ~28 MCP SET tools reference-first + contract-snapshot harness + live-e2e each; **T3** = extract Planner/Compiler → `sdks/python/loreweave_context` kernel (reuse STANDARD, byte-identical, retire the roleplay byte-copy coupling); **T6** = atom-safe collapse + resume-monotonic + fact-preserving summary + `conversation_search` + flip compaction to the target; **Inspector GUI** (dockable studio panel + BE TraceSpan telemetry + `context-trace.contract.json`, §11 86-item checklist); **§13** full enforcement (CI meta-check unproven=red + adversarial refute-pass). THEN the Cursor-for-novels register [[writing-studio-fragmented-not-underbuilt]]. Tier-by-tier measured detail lives in spec §8a. ▼ superseded design-seal note (that prior work merged to main): CONTEXT-MANAGEMENT DESIGN SEALED 2026-07-03 (spec-only; implementation is a NEW SESSION + NEW BRANCH per the user). Spec: [`docs/specs/2026-07-03-context-budget-law.md`](../specs/2026-07-03-context-budget-law.md) v2 + memory [[context-budget-law-and-kernel]]. Root pain: the chat agent has NO per-request context planning — one real turn ("change scene status to drafting") cost 146K tokens (composition_list_outline dumps the whole outline; json.dumps ensure_ascii=True → Vietnamese \uXXXX 2-3×; full skill bodies + blind RAG for a turn needing neither). Deliverables designed: a repo-wide Context Budget Law SPLIT BY ENFORCEABILITY (L3 concise-wire = lint now; L1/L2 reference-first+detail/fields/limit = contract-snapshot tests + versioned default flip; L4/L5/L6 = compiler behavior), Planner(policy) vs Compiler(mechanism), 13 decisions folded from 2 cold-start adversarial reviews, a tier build T0–T6 with per-tier GATES (T0 ensure_ascii=false is shippable NOW & measurable on the 146K replay; committed T0–T3, re-decide T4–T6 after T0–T2 numbers), a reusable Context Kernel STANDARD (`sdks/python/loreweave_context`, ports via provider-registry, uniform TraceSpan telemetry — chat is consumer #1, role-play #2 [roleplay-service is thin Rust delegating to chat-service via a byte-compatible working_memory_seed], composition packer #3), and a dockable Inspector GUI (draft `design-drafts/context-management/context-compiler-inspector.html` + §11 86-line item-level BE/FE checklist; the TraceSpan telemetry is NEW BE work beyond today's context_breakdown). ▶ CURSOR-FOR-NOVELS REGISTER (north-star, don't drift) in [[writing-studio-fragmented-not-underbuilt]]: after context-mgmt, return to (1) merge the 2 workspaces, (2) pass editorContext in ComposePanel so propose_edit works in studio, (3) fill the Lane-B reconciler stub, (4) autonomy mission-control GUI, + Compose grouping/launcher, discuss→content, [[llm-client-first-tool-refactor]], C6 setDone-before-await shared-card refactor.** Prior: **C6 HUNK-REVIEW ✅ SHIPPED 2026-07-03 — the last RAID FE tail item is cleared. The `propose_edit` card now lets the user accept/reject INDIVIDUAL changes of an AI-proposed rewrite instead of all-or-nothing Apply. Pure FE, no contract/backend change. New pure helper `features/chat/utils/proseHunks.ts` — SENTENCE-granularity diff (ProseMirror hands the selection space-joined via `textBetween(...,' ')`, so line-granularity is impossible; sentence reads naturally for prose; Latin+CJK splitter with a lowercase-next guard for dialogue/abbrev; reuses wikiDiff `diffLines` LCS) → hunks → `reconstruct(accepted)`. ProposeEditCard renders per-hunk old/new with checkboxes (default accept-all); Apply writes the reconstructed merge, accept-all stays byte-identical to the old whole-text path, reject-all routes to Dismiss. Applies to `replace_selection` only; `insert_at_cursor`/no-selection fall back to the whole-text card. /review-impl (cold-start subagent) found 1 HIGH + 2 fixed + 1 deferred: HIGH — a partial accept flattened the NEW proposal's paragraph breaks to single spaces (accept-all preserved them) → reconstruct now carries a per-unit `breakAfter` and rejoins with `\n\n` at NEW-side paragraph seams. MED — mount-snapshot selection vs live selection: a partial merge re-injects OLD sentences, so Apply now re-checks the live selection still equals the mount snapshot and aborts with a toast on drift (no stale-range splice; run stays suspended for a re-ask). LOW — reject-all→Dismiss moved ABOVE the editor/chapter guards (dismissing needs no editor). DEFERRED (tracked): the optimistic `setDone`-before-`await submitToolResult` with no `catch` is a PRE-EXISTING shared pattern across every propose/confirm card (RecordDiffCard, ConfirmCard, …) — fixing it correctly (retry-RESUME-only, since the doc is already mutated) is a cross-card refactor, out of scope for C6. VERIFY: proseHunks 15 + ProposeEditCard 7 + full chat suite 438 green · tsc clean. FE-only (entirely under frontend/). The LLM-CLIENT-FIRST REFACTOR remains the user-chosen NEXT (new session; memory [[llm-client-first-tool-refactor]]).** Prior: **4-DEBT /review-impl HARDENING DONE 2026-07-03 (content on remote; my labeled commit was dropped as a duplicate on rebase after the concurrent agent-registry track swept the index — the FIXES ARE LIVE, verify by grep not by commit message). 4 adversarial reviewers over the 4 debts: 1 HIGH + 8 MED, all verified-then-fixed. HIGH: C1 steering list is a {items,total} ENVELOPE the FE consumed as a bare array → panel CRASHED on every load (mock-only-coverage trap; api.list now unwraps .items + a transport-level contract test). MED: (8) reorder race (NULL-all now locks ALL owner rows — the `IS NOT NULL` predicate locked nothing when all-NULL → concurrent corruption; + dedupe); (8) ModelPicker now flat-renders in server order when ANY model is ordered (favorites-hoist + provider-grouping were discarding the custom order); (5) context-history limit ge=1 (negative→500), CATEGORY_HEX⇄COLORS lockstep pin, useContextHistory race-guard + stale-clear, History tab mounted-hidden so enabled gates the fetch; C6 TurnCheckpoints filters to the CURRENT chapter (stale other-chapter row silently restored the wrong chapter), capture() TOCTOU closed via a sync-held latestRevIdRef, revKey bump + first-snippet fold; C1 code-point char count + 403 "no permission" message. VERIFY: FE 1262 (182 files) + tsc clean · chat 735 · provider-registry go (DB-gated reorder incl. dedupe). The LLM-CLIENT-FIRST REFACTOR is DEFERRED to a NEW SESSION per the user (memory [[llm-client-first-tool-refactor]]).** Prior: **4 DEBTS CLEARED 2026-07-03 (`1302d9f55` + 3 prior; 3 parallel sub-agents + C6 by hand). The user decided NOT to wait for the (still-active) studio track — the dockable migration is long done + the panel catalog is now additive-safe, so C6/C1 were built directly. (8) MODEL sort_order: `user_models.sort_order` + `PUT /user-models/reorder` + ModelOrderCard drag-reorder (favorites-first fallback; DB-gated live). (5) TOKEN HISTORY chart: `GET /sessions/{id}/context-history` over the persisted context_breakdown JSONB + a recharts Now/History tab on the ContextBreakdownPanel. C1 STEERING panel: features/steering CRUD + dockview SteeringPanel + catalog entry + `steering` added to the ui_open_studio_panel enum (contract JSON + frontend_tools.py + test pins). C6 TURN-CHECKPOINTS: useTurnCheckpoints captures the pre-edit revision at all 3 AI-apply seams (onAccept/applyPolish/popout-relay) → TurnCheckpoints UI above RevisionHistory restores "before the agent touched it" (pure FE over the existing restore spine; ChapterEditorPage not hot in the studio track). VERIFY: chat 734 · provider-registry go (DB-gated) · FE full sweep 181 files/1251 tests · tsc clean. REMAINING: C6 hunk-review (per-hunk accept on the propose_edit card — separate surface, deferred). NEXT (user-chosen): the big LLM-CLIENT-FIRST TOOL REFACTOR (memory [[llm-client-first-tool-refactor]]) — make every agent tool self-describing/enum-in-schema/tolerate-extras/self-correcting/explicit-context, the Frontend-Tool Contract swept across the whole MCP surface.** Prior: **W0 TOOL-ERROR SOAK ✅ DONE 2026-07-03 (`632077380`): baseline reconfirmed 27.7% over 30d (glossary_book_patch 58.5% = the base_version 409 storm = ~22% of ALL errors). The base_version root cause is ELIMINATED — deterministic live proof through chat→gateway→glossary: read emits base_version on all 13 kinds, patch round-trips one-shot, stale→409 WITH current version, OCC bump real again; the fresh-window storm = 0. The soak CAUGHT a systemic residual: the go-sdk infers additionalProperties:false on every MCP tool struct, so a weak model's harmless EXTRA field hard-fails validation before the handler runs — live-caught on glossary_book_patch's `changes` tolerance shim (gemma's `old_value` killed it) AND glossary_propose_batch (100%-error tool; stray root `type` + op-item extras). Fixed via `relaxAdditionalProps` (opens additionalProperties on model-constructed object/array schemas; ENUMS stay strict) + 2 schema tests + 2 deterministic live proofs. Remaining soak tail: fresh-window sample is small (gemma non-deterministic); residual errors are model hallucination (wrong codes) which is inherent — a longer real-usage soak will show the true steady-state (target <10%).** Prior: **WAVE /review-impl HARDENING ✅ SHIPPED 2026-07-03 (`3ce92d101` chat-surface + `6036dfc6a` MCP-surface; 4 parallel adversarial reviewers, every finding VERIFIED against code before fixing): 3 HIGH — (1) edit-below-compact-boundary made user messages INVISIBLE to the model → clear-compact-on-edit + branch-scoped assistant seq; (2) glossary reads NEVER emitted `base_version` (the W0 shim had become the MAIN path = silent overwrite of concurrent human edits; the 22% error bucket was a broken CONTRACT) → reads/creates emit it, OCC loop DB-proven completable end-to-end; (3) session reasoning "off"/"auto" crashed every tool-approval RESUME (raw session vocab ≠ wire vocab) → `_resolve_and_stash_reasoning` on all 3 paths (fresh/resume/voice). 13 MED fixed: Deep-effort persistence via the panel contract ({reasoning_effort, thinking:null}), manual-compact race-guard 409 + `{"clear":true}` escape for poisoned summaries + FE button, ModelPicker recents cross-USER pref pollution (per-user cache keys), serverKey FE/BE pinned to contracts/frontend-tools.contract.json, gateway 408/429/-32603→retryable, `kg_project_list` added to the public tool policy (the self-correct directive pointed at a denied tool), settings_model_set_default parity via shared defaultModelCapQuery, rack 0-tok flash, toast late-join replay, edit_attribute stale-error embeds current version, sanitizer host:port redaction, enum VALUE-SET pins. Accepted+documented: enum-rejects-"" (self-correcting 1-retry), voice-path compact splice, threshold-marker drift. Suites: chat 729 · FE 3349+13 · glossary (incl. DB-gated OCC-loop) · provider-registry · ai-gateway 114 · mcp-public 205 · tsc clean · provider-gate clean.** Prior: **CHAT QUALITY & UX WAVE ✅ COMPLETE 2026-07-03 ([plan](../plans/2026-07-03-chat-quality-ux-wave.md)) — ALL 7 MILESTONES SHIPPED + LIVE/BROWSER-SMOKED: W0 MCP reliability `8e870b363` (26-30% tool-error rate attacked at root; /internal/tool-health measures the after) · W1 breakdown spine `a3dd678ba` · test-infra xdist `a374d6807` (composition 418s→55s · translation 770s→37s; CLAUDE.md rule) · W2 context GUI + W4 effort/mode dropdowns `c18fdba1c` (browser-smoked: meter "until auto-compact: 72%", panel Skills 1,907/UI-tools 1,484/MCP 193, always-on token footer, both dropdowns) · W3 manual steerable compact `c5373c5a2` (PERSISTED; live: 200 {4 compacted}, steered summary kept "the moon fact", SPLICE PROVEN BY EFFECT — post-compact turn answered from the summary alone; live-caught fix: summarizer thinking-OFF, gemma burned max_tokens on ReasoningEvents → empty prose) · W5 shared ModelPicker `735598a47` (ALL ~19 sites swept; browser-smoked: chat picker = 6 chat-capable only, rerank/embed/tts GONE, provider groups + ctx/$0-local badges; BE: pricing exposed, favorites-first, chat default whitelisted) · W6 tool/skill visibility `7a69f2ded` (agentSurface +advertised/servers/schema_tokens grounded in the gateway federation map; rack grouped per server + live dot + "N tools · X tok" chip; rack/inspector i18n gap closed ×4 locales). Suites at close: chat 719 · FE full 3277 · knowledge 3374 · translation 1031 · composition 1472 · glossary/jobs/ai-gateway/provider-registry green. Post-wave tail: tool-error-rate soak check via /internal/tool-health (target <10%) · Playwright compose e2e needs a stack run (page object migrated to selectModel/data-model-id) · deferred-vs-loaded count on the frame (needs catalog size — small) · D-RAID-ALLOWLIST-ENFORCE + RAID FE tail (C6/C1 panels) unchanged.** · Prior: **RAID ✅ COMPLETE 2026-07-02: Track 4 + C5/C4/C1/C2/B2 + WAVE D (D2 FSM `ecf0d410c` · D3 report/accept-reject `004d49ad9` · D4 durable sweep/claim/notify `037831e1d` · D5 real-judge critic `1d6f2960b` · post-RAID /review-impl hardening: HIGH >100-chapter gate false-reject `6c2ba94e0` + 4 MED fixes, see block below). B2 browser-smoked PASS (real gemma plan-mode, wire `permission_mode:plan` proven). REMAINING (small tail): full C2 approval-card browser loop (D-RAID-C2-LIVE-SMOKE — needs a clean session + tool-strong model; card surface itself proven live via the frontend-tool loop), C6 FE wiring + C1 FE panel (both wait for the dockable track to release the editor/panel seams), end-to-end autonomous-run live drive (create→gate→start→report on the POC book — all layers live-DB-proven separately; ⚠️ FE tsc is BROKEN at HEAD in the dockable track's committed studio files — manuscriptUnitDocument/ManuscriptUnitProvider/EditorPanel — their track owns the fix; smoke images build from a patched worktree meanwhile). Draft PR #54 open. Contract stands: local LLM only, exact-file staging, hard-stops = destructive-ops-outside-test-account + 3-strike.** Spec [`salience-track4`](../specs/2026-07-02-knowledge-salience-track4.md) + [`07S`](../specs/2026-07-01-writing-studio/07S_studio_agent_standard.md) + DRs [`raid-loadbearing-decision-records`](../specs/2026-07-02-raid-loadbearing-decision-records.md). · 2026-07-02**

> **▶ KG ARCHITECTURE — TRACK A (schema authoring) ✅ SHIPPED + LIVE-PROVEN 2026-07-03.** Plan
> [`2026-07-03-kg-architecture-schema-authoring-multi-kg`](../plans/2026-07-03-kg-architecture-schema-authoring-multi-kg.md)
> (spec-review edge cases folded, `175e6eb53`). The "flop" (humans can't define/edit a KG schema) is
> fixed end-to-end — the schema editor now follows the KG **project** (not the book) and is full CRUD.
> **A1 `9844d94ef`** — full-CRUD repo+routes: revive-on-recreate (EC-A1: total UNIQUE kept, `add_*`
> un-deprecates a soft-deleted code — no partial-unique migration; keeps sync single-row + graph-data
> ref unambiguous), PATCH attribute-only (code IMMUTABLE), `add_vocab_set`, tier-aware DELETE (user
> HARD / project SOFT), + `glossary_gate` UUID guard (500→422) & 2 stale route tests from the
> auto-create-glossary feature. **A2 `3080a4693`** — create-blank (`POST /projects/{id}/schema`,
> one-active under lock) + clone (`POST /graph-schemas`, user-scoped, `_assert_source_adoptable`
> visibility gate = no read-oracle, auto-suffix `-copy`). **A3 `c00d0da3f`** — redesigned full-CRUD
> SchemaWorkbench (inline edit+delete per component, editable name, new EdgeTypeRow/NodeKindRow/
> FactTypeRow/VocabSetCard), `ProjectSchemaSection` is now the authoring home (active schema→workbench,
> else CreateSchemaEntry blank/clone/adopt), book tab redirects (Navigate); **live-smoke-caught fix**:
> `getSchema` now forwards `project_id` (a project-scoped schema 404'd on `_visible` without it) —
> threaded through `useGraphSchema` + both callers; i18n ×4. **VERIFY:** 3417 knowledge unit+integration
> (live PG :5555) · 757 knowledge FE + 0 tsc · **LIVE BROWSER SMOKE** (vite :5199→gateway :3123→rebuilt
> knowledge-service): create-blank→editor mounts→add edge→inline PATCH, `schema_version` v1→v2→v3, 0
> console errors. **A4 `867e05fec`** — live-delete orphan-count guard: `count_component_usage` (Neo4j:
> Entity-of-kind + live RELATES_TO-of-predicate, subject-scoped) + `GET /projects/{id}/schema/usage`; FE
> SchemaWorkbench `getUsage` → confirm dialog only when count>0 (else direct delete; never blocks —
> project DELETE is soft). 3387 unit + 760 FE + 0 tsc; live-smoke: delete edge → usage 200 (count 0) →
> DELETE 204, no confirm. **⇒ TRACK A COMPLETE (A1-A4).**
>
> **▶ KG SCHEMA EDITOR MODERNIZATION — COMPLETE (M1–M3b), 2026-07-03.** User: the Track-A editor felt
> like "mấy cái text box thông thường". Spec [`2026-07-03-kg-schema-editor-modernization`](../specs/2026-07-03-kg-schema-editor-modernization.md)
> (`7f923afe5`), 4 milestones ALL shipped + live-proven: **M1 `172e576fc`** typed KindMultiSelect
> pickers (source/target from real kinds, no typos) + inline "· used by N" usage badges (one
> `GET /schema/usage-summary`) + empty-state coaching — live: picker offered real kinds, "character → —"
> persist. **M3a `7c9361569`** infer-from-graph: `GET /schema/observed` (distinct Entity.kind +
> RELATES_TO.predicate) → InferFromGraphPanel promotes missing components (kinds first, then edges).
> **M3b `b73f04614`** AI generate: single-shot LLM pipeline (exempt MCP-first like wiki-gen — NOT
> multi-step agentic) `POST /schema/propose` (BYOK model_ref, JSON parse+salvage) + GenerateSchemaDialog
> (premise+ModelPicker → review checklist → adopt) — **LIVE LLM-PROVEN via Qwen2.5 7B**: 5 kinds/5
> edges/2 facts, correct source→target wiring (KILL elder→master, SEEK_REVENGE character→elder).
> **M2 `a978e0060`** visual type-graph canvas (reuses composition GraphCanvas SVG): kinds=boxes,
> edge-types=arrows; **click-to-connect** (⇢ handle → target node → inline new-edge popover), Canvas/List
> toggle, zoom/pan/drag-arrange — live: character⇢sect → MENTOR_OF arrow renders + persists. Also fixed
> the KG-schema GUI **theme** (`d9bcfab09`): inputs `bg-input`, primary buttons `text-primary-foreground`.
> VERIFY at close: 766 knowledge FE + ~10 schema_usage/9 schema_propose BE unit + 0 tsc. **DEFERRED
> (thin follow-ups):** an agent-facing `kg_schema_propose` MCP tool wrapping the M3b engine; M2 detailed
> attribute-editing on the canvas (today edits stay in List); canvas node-position persistence
> (per-device localStorage). **TRACK B (agent multi-KG) — not started:** B1(1) world-rollup
> as an MCP tool (`resolve_world_project_ids`+`get_world_subgraph` exist, read-only/FE-only today; take
> `world_id` as EXPLICIT arg — gateway drops X-Project-Id; owner-only, report partial not silent-drop) →
> B1(2) multi-project context (cross-project ranker+dedup, real work) → B1(3) arbitrary project set.
> Note: `⚠️` a stray dev vite server may still be running on :5199 from the A3 smoke; the smoke created
> a throwaway project "KG Schema Smoke" on the test account.

> **▶ AI-TASK STANDARD — single-shot LLM generate: shared engine + composable UI (2026-07-03).**
> Trigger: the KG schema-generate re-implemented plumbing every other "generate" dialog also
> hand-rolls. Discovery found **21 FE surfaces + 10 BE engines** each re-deriving the same slices.
> Spec [`2026-07-03-ai-task-standard`](../specs/2026-07-03-ai-task-standard.md). Boundary (LOCKED,
> non-goal): NOT the Agent-Extensibility Standard — these are non-agentic MCP-exempt pipelines;
> agent-facing MCP/subagent wrappers are deferred and compose ON TOP of this engine.
> **M1a `a7240e189`** — BE `loreweave_llm.structured_generate` (reasoning-off by DEFAULT → closes the
> empty-prose footgun; required max_output_tokens; typed StructuredGenerateError on transport/non-
> completed/empty) + `parse_json_object` (consolidates the ~5 `_extract_json_object` copies);
> `schema_propose` migrated onto it, byte-preserved (10+10 unit green). **M1b `037bbf540`** —
> `no_thinking_fields()` + footgun disable in `working_memory/executive.py` (max_tokens=500, was
> nothing) + `summarize_level`. **M2 `5bb2dd517`** — FE `components/ai-task/`: `EffortSelect` (extracted
> from ChatInputBar's inline W4 menu, now the single source; chat re-exports), `SpendCapField`+
> `isValidSpend`, `useAiTask` (propose→review→confirm controller), `lib/readBackendError` (moved shared).
> **M3 `a2430c721`** — GenerateSchemaDialog→useAiTask+readBackendError, GenerateWikiDialog→SpendCapField.
> **M4 `22c63b41c`** — BuildGraphDialog→SpendCapField (LAST DECIMAL_* regex copy gone). VERIFY: BE
> 33 unit + FE 94 (ai-task 9 + readBackendError 5 + chat effort 22 + wiki 22 + schema 2 + buildgraph 34)
> + tsc 0. Live: stack up but running knowledge :8216 image predates the SDK change (stale-image caveat)
> → schema_propose is byte-preserving + unit-asserts the exact wire + was live-proven (Gemma, 8 edges)
> last session; a fresh live smoke needs a knowledge-service rebuild.
> **CONVERGENCE M5-M7 — "standard vs exception" re-examined (the user challenged that my initial
> deferrals were mostly standard-covered, and was right):** **M5 `145810f0a`** unify reasoning-
> effort to ONE 5-level vocab (off|low|medium|high|auto) — chat-service had TWO (session vs per-msg
> fast|standard|deep); chat FE now uses the shared EffortSelect; BE tolerant-first (no flag-day).
> **M6 `8be4e6c63`** ComposeView `<select>`→EffortSelect; SpendCapField `compact` variant →
> ComposeConfig; GapsPanel raw `<select>`→ModelPicker (the one outlier). **M7 `b4ae23d38`**
> extraction wizard thinking-checkbox→EffortSelect (translation-service extraction router ALREADY
> accepted `reasoning_effort` — the "field already exists" lesson; pure FE); wiki `"none"`=no-op made
> an EXPLICIT documented exception (prose≠JSON + graceful degrade), not a silent fork. **Framework:**
> standard = PLATFORM concept + presentation/config variation → prop; exception = domain SEMANTICS,
> declared as an EXPLICIT param, never a silent re-implementation. Of the 5 I'd deferred, 4 were
> standard-covered (migrated) and only wiki was a true exception.
> **BOTH remainders CLEARED — the standard is 100% closed.** **`D-ENRICH-COMPLETE-BUDGET`
> `372d98e31`** — lore-enrichment `complete.py` stream body now carries max_tokens=4000 (was
> unbounded) + `no_thinking_fields()` (the seam already DROPS reasoning frames, so disabling wastes
> nothing + closes the footgun); the Go stream endpoint already accepts both. **`D-AITASK-GLOSSARY-
> TRANSLATE-EFFORT` `4714171b4`** — glossary-translate wizard boolean→EffortSelect (5-level), a
> byte-for-byte MIRROR of the extraction path (M7): router `+reasoning_effort` + grant-clamp
> (off/auto→'none'), worker swaps the local boolean `thinking_llm_fields` for the SDK
> `reasoning_fields` (drops the dup), FE across 5 wizard files. No migration (reasoning lives in the
> metadata JSONB). VERIFY: enrichment 9 + glossary router 7 + worker 12 (graded path pinned) + tsc 0.
> **/review-impl `28b8681ef`** earlier pinned the executive/summarize footgun disables + narrowed a
> dead type. **AI-Task Standard status: DONE** — every one-shot AI surface consumes the shared
> primitives; reasoning-effort is ONE unified 5-level vocab platform-wide (chat + compose + extraction
> + glossary-translate); the 4 footgun engines all disable hidden reasoning; the only remaining
> LOW/opportunistic items are CLOSED as a conscious won't-fix (gate #5), verified against code:
> the `_extract_json_object` "dedup" is 7 copies, and **2 of them (composition plan_forge
> `json_extract`, lore-enrichment `profile_suggest`) are DELIBERATELY more robust** (string-aware
> balanced-brace depth counting — correctly handle `{...} {...}` and braces-in-strings, which the
> shared regex `\{.*\}` does not) — consolidating them would be a REGRESSION. The other 5 are simple,
> stable, self-contained utils with their own exception contracts; folding them into
> `parse_json_object` adds cross-package coupling (loreweave_eval→loreweave_llm) + per-site contract
> churn for ZERO functional benefit. None violate the standard (its real surface — effort / spend /
> error / structured_generate / footgun — is fully consolidated). `plan_forge` engine is gated-off
> (rules-mode default), so migrating it to structured_generate is also no-value. **Won't-fix; the
> AI-Task Standard is closed.**

> **▶ KG TRACK B — agent multi-KG (2026-07-03). Plan §Track B in
> [`2026-07-03-kg-architecture-schema-authoring-multi-kg`](../plans/2026-07-03-kg-architecture-schema-authoring-multi-kg.md).**
> **B1(1) DONE `487f78c9c`** — `kg_world_query` MCP tool: the agent loads a whole WORLD's KG (union
> of member-book canon + world lore) in one call. Wraps the existing `resolve_world_project_ids` +
> `get_world_subgraph` across all 4 KG-tool sources (FastMCP sig + arg model + OpenAI def + handler).
> EC-B1 (explicit `world_id` arg — gateway drops envelope scope), EC-B2 (owner-only; new
> `resolve_world_partitions` REPORTS `partitions_read`/`partitions_unreadable`, never silent-drop;
> `resolve_world_project_ids` kept as a byte-compat shim for the subgraph+timeline endpoints),
> EC-B5 (WorldNotFound/BookServiceUnavailable → self-correcting tool-error). 101 tests + drift-locks
> (28→29 tools) + live: world-subgraph endpoint (uses the refactor) runs clean, service healthy.
> **B1(2) Layer 1 DONE `cf309f89b`** — knowledge multi-project CONTEXT union (the hard core). New
> `app/context/modes/multi_project.py` `build_multi_project_mode`: fans out the SAME Mode-3 retrieval
> per project (reuses `_safe_l2_facts/_safe_l3_passages/_safe_summary_blend` + glossary + salience),
> then EC-B3/B4 cross-project MERGE+DEDUP (entities by name→highest salience; facts by text; passages
> by source_id; summaries by level/path) + GLOBAL rank, one `<memory mode="multi">` block per-item
> tagged, ONE SHARED budget trimmed reverse-priority. `build_context` +`project_ids` (precedence over
> single `project_id`, owner-scoped, ≥2→union / 1→single / all-stale→404); `ContextBuildRequest`
> +`project_ids` (≤16). 55 tests (4 dispatch routing + 5 merge/dedup/budget + existing). Back-compat
> preserved. **B1(2) Layers 2+3 DONE (chat-service + FE) —** L2: migration `chat_sessions
> +project_ids UUID[]` (guarded additive, empty-default) + `project_ids` on Create/Patch/ChatSession
> models + sessions router (INSERT/UPDATE set-via-`model_fields_set`, `memory_mode="multi"` when ≥2)
> + `knowledge_client.build_context` +`project_ids` param + a shared `resolve_grounding_target` helper
> threaded into BOTH the text (`stream_service`) and voice (`voice_stream_service`) build calls (≥2 →
> union, sent WITHOUT a single `project_id` so the router's salience write-back can't misattribute the
> union's surfaced entities; 1 → single so salience still learns; 0 → legacy `project_id`). L3 FE: new
> `MultiProjectPicker` (multi-select sibling of `ProjectPicker`, chips + ≤16 cap + archived-fallback)
> wired into `SessionSettingsPanel` (seeds from `project_ids` else the legacy `project_id`; writes
> `project_ids` + keeps `project_id`=first as the tool-scope anchor); `MemoryIndicator` gains a `multi`
> mode ("N knowledge graphs" chip + popover). **VERIFY:** chat-service 803 unit (grounding_target 6 +
> sessions +7 + knowledge_client +2 + migrate +1) · FE tsc 0 + 14 picker tests. **LIVE-SMOKE (rebuilt
> chat+knowledge images):** real chat API create with `project_ids=[A,B]` → the live asyncpg `uuid[]`
> INSERT round-trips + `memory_mode="multi"` (the mock-hidden binding risk proven live); knowledge
> `/internal/context/build` with `project_ids=[A,B]` → `HTTP 200 mode="multi"`, rendered
> `<memory mode="multi" projects="2">` union block. Throwaway smoke projects+session cleaned up.
> **CLEARED D-MULTI-SALIENCE-WRITEBACK** (was mislabeled gate #2 "cross-service Layer-1 change" — on
> re-verification it's knowledge-service-LOCAL): the multi-mode write-back keyed on the single
> `req.project_id` (None in multi) so multi sessions never LEARNED salience. Fixed knowledge-local +
> additive: `build_multi_project_mode` already holds each surfaced entity's SOURCE project in the
> `(proj, e)` tuple (it was discarded) → new `BuiltContext.surfaced_by_project` maps entity→source
> project; the `/internal/context/build` router now records salience PER SOURCE PROJECT in multi mode
> (each entity attributed to its own book, no misattribution). 2 router wiring tests + full unit 3460
> green. **LIVE-DB smoke (rebuilt knowledge-service):** drove the REAL
> `/internal/context/build` handler with a real `EntityAccessRepo` over live Postgres + a multi
> `surfaced_by_project={A:[e1,e2], B:[e3]}` → the fire-and-forget task wrote exactly those 3 rows to
> `entity_access_log` attributed to each SOURCE project (test_context_salience_multi_integration.py,
> self-cleaning). Multi-KG salience learning proven end-to-end on real DB.
>
> **B1(3) DONE (knowledge-service) — `kg_multi_query` MCP tool (arbitrary owner-owned project
> set).** The agent-tool analog of B1(2): loads the UNION knowledge graph across an ARBITRARY
> set of the caller's own `project_ids` (canon KG + fan-theory KG, two unrelated books) — vs
> `kg_world_query` (B1(1)) which rolls up one whole world. New `KgMultiQueryArgs`
> (`project_ids` list 1–16, extra='forbid') + `_handle_kg_multi_query`: order-preserving UUID
> dedup → owner-scope via `projects_repo.get` (foreign/stale skipped) → reuse
> `get_world_subgraph` (already project_ids-generic; binds user_id+project_id per read so no
> bleed) → EC-B2 `partitions_read`/`partitions_unreadable` reporting (never silent-drop);
> invalid id → self-correcting tool-error; all-unreadable → empty-but-honest. Registered
> across all 4 KG-tool sources + the FastMCP signature (`mcp/server.py`). NOT in the public
> allowlist (follows kg_world_query's authenticated-only precedent — `tool-policy.ts` has only
> graph_query/entity_edge_timeline). **VERIFY:** 148 graph/definition + 69 mcp/executor unit
> green; drift-locks bumped 29→30 tools + `_LANE_LF_TOOLS` +1; the real loopback MCP server's
> `tools/list` == EXPECTED_TOOLS advertises `kg_multi_query` (proves the FastMCP wiring, not
> just the arg model). Single-service change → no cross-service smoke needed.
>
> **B1(4) DONE (knowledge-service) — cross-partition entity unification ("world-core").** Spec
> [`2026-07-03-kg-cross-partition-merge.md`](../specs/2026-07-03-kg-cross-partition-merge.md) (PO-signed-off:
> Q1=b on-demand embed, Q2=ephemeral-first, Q3=pairwise; 24 edge cases). The forest exists because a
> node id folds project_id into its hash, so "Alice" in two books = two ids. New `app/tools/kg_unify.py`:
> a **query-time app-side** pass (NEVER a cross-partition Cypher, NEVER a Neo4j write — propose-don't-assert
> D2/D3) that recognizes the same entity across ≥2 owned partitions and emits confidence-scored
> `unification_clusters` + inferred `SAME_AS` `bridge_edges` + `disagreements`. Opt-in `unify` enum on
> `kg_world_query` + `kg_multi_query` (all 4 schema sources + FastMCP, drift-locked); **`unify="off"`
> default = byte-identical forest (EC-M5)**. Tiers shipped:
> **T0 `3d1e20d4d`** — lexical (`canonicalize_entity_name` + alias overlap), kind-gate (EC-M3),
> cross-partition-only (EC-M10), union-find, per-method bands, deterministic ephemeral cluster_id (EC-M22),
> degenerate/common-name guards (EC-M18/M20), size/count caps confidence-desc (EC-M7/M11/M21).
> **T1 `14a5edb04`** — semantic: in-Python pairwise cosine, model-space-gated (EC-M1), lexical-fallback
> blend (D1); **Q1=b on-demand embed** of discovered seeds under the anchored model, **in-memory only**
> (reuses provider-registry BYOK EmbeddingClient, NEVER set_entity_embedding — EC-M16), spend-capped
> (EC-M15 `unify_embed_skipped`), degrade-safe (EmbeddingError→lexical); zero-norm guard (EC-M19).
> **T2 `5e5fd55ea`** — disagreement detection: same cross-book entity asserting different predicates to
> the same unified target → one `disagreements` record (agreement rides the bridge). **VERIFY:** knowledge
> unit 3454 green (23 new kg_unify + enum-drift + wiring + MCP CLOSED_SET machine-check) · FastMCP loopback
> advertises `unify` (inputschema-mirror) · provider-gate OK · **LIVE Neo4j integration `3746ee9d5`**
> (`bolt://localhost:7688`, 2 passed): real `_SEED_DETAIL_CYPHER` + `get_world_subgraph` forest → 2
> clusters + 2 bridges + 1 disagreement (Alice LOVES→KILLS Bob across books); semantic reads stored
> embeddings + honours the model gate. **DEFERRED T3** (persisted cross-book substrate + `SAME_AS` Neo4j
> edge + human-confirm spine — gate #2 structural, re-decide with precision numbers) **+ T4** (cross-partition
> salience/rank renorm + reranker — gate #4 profiling). Track B B1(1)–B1(4) COMPLETE.

> **▶ KNOWLEDGE GUI FIXES + MODEL-ROLES SETTINGS — 2026-07-03 (3 items, all shipped).**
> **#1 `cancel_check` extraction blocker (`591e54ad7`)** — bug #34 added `cancel_check` to the
> loreweave_extraction protocol + every extractor (which ALWAYS forward it), and to
> composition-service's wrapper, but the **knowledge-service + worker-ai** LLMClient wrappers were
> left behind → EVERY KG extraction died `TypeError: submit_and_wait() unexpected keyword argument
> cancel_check`. Both wrappers now accept + forward it to wait_terminal (additive). Tests use the
> REAL wrapper (the extractor fakes' `**kwargs` swallowed the drift). LIVE: Retry on "Ma Nữ Nghịch
> Thiên (POC)" → failed→ready, **43 entities/15 facts/129 events/181 passages** extracted, zero
> TypeError. **#2 dead detail-view edit pen (`652899564`)** — `OverviewSection` passed
> `onEdit={noop}` (silent no-op); now opens ProjectFormModal edit mode (embedding/rerank pickers),
> reusing the ProjectsTab modal + If-Match update via the deduped useProjects cache. LIVE: pen →
> "Edit project" dialog. **#3 model-roles settings + default fallback** — every LLM role gets a GUI
> setting + a default fallback (PO: "both" scopes — precedence **role override → project default
> (`extraction_config.llm_model`) → user-global default (provider-registry `user_default_models`
> cap=chat, already built) → env floor → off**). Plan `docs/plans/2026-07-03-knowledge-model-roles-settings.md`.
> Slices: **A foundation `36a8f76b7`** (pure `resolve_role_model` + user-global client, 10 tests);
> **A-wire `4f32071e5`** (endpoint resolves per-job `entity_recovery` config → threads through
> extract-item → `_run_pipeline` → `_maybe_apply_entity_recovery`; env-only stays byte-identical;
> fail-soft); **B `f95cc46a5`** (contract `EntityRecoveryOverride`/`LlmModelOverride` already
> existed; persisted project-default beats job model); **C `f9513b9f4`** (tuning-panel Default-LLM +
> entity-recovery pickers, empty=use default; i18n ×4). Suites: knowledge 70 touched-unit + 750 FE
> + 40 i18n parity; tsc clean. **D live**: new pickers render (theme-correct) + conditional
> recovery picker on enable; **Save persisted `entity_recovery.enabled=true` to the DB via the real
> PUT** (read-modify-write kept the rerank knob); A-wire image healthy. Runtime consumption
> unit-proven (orchestrator threading test); a live rebuild re-dispatch wasn't observable on the dev
> stack (worker-ai idle — rebuild-flow timing, NOT an A-wire regression: the only failed jobs are
> pre-#1-fix). **Defer-clears (`10089586e`):** rebuild-with-model-change — a rebuild now uses the
> project's persisted default LLM over the prior job's (pure `resolveRebuildModels`, unit-tested);
> `max_items_per_batch` now in the FE contract (`EntityRecoveryOverride` bounded 1-20 + tuning-panel
> batch input). wiki-gen model consistency (`1243677a8`) — the Generate-Wiki dialog pre-selects the
> user global default chat model once the AI path is active (mirrors NewChatDialog), so wiki
> generation inherits the "one default model" like every other role; the deterministic stub default
> (anti-spend) is untouched, FE-only, no stub-vs-LLM routing change. **Model-roles defers: all clear.**

> **▶ AGENT EXTENSIBILITY REGISTRY — AUTONOMOUS RUN IN FLIGHT (2026-07-03).** New track: user-registered
> plugins/skills/MCP-servers + agent self-registration. Spec [`agent-extensibility-registry`](../specs/2026-07-02-agent-extensibility-registry.md),
> plan+tasks+E2E+GUI-checklist in [`docs/plans/2026-07-02-agent-extensibility-registry/`](../plans/2026-07-02-agent-extensibility-registry/).
> Design SEALED; running continuously to completion, human gate at final release only; mid-run forks → `DECISION_LOG.md`.
> **P0 + P1-backend + chat-injector SHIPPED ✅ (3 commits):**
> **P0** (`512cedfda`): Go svc `agent-registry-service` (:8099, DB `loreweave_agent_registry`) — plugins CRUD +
> enablement (D1) + effective-catalog v0 + audit + quotas; BFF proxy `/v1/agent-registry/*`; OpenAPI frozen; real-stack
> E2E 20/20 (`p0_smoke.ps1`). **P1 backend**: skills (prompt-only) CRUD + SKILL.md import/export + draft/publish +
> revisions + shadow-check + per-user toggle; 5 System skills seeded (slugs byte-identical; bodies stay in chat-service
> — DL-4); `/internal/skills` (merge/shadow/surface + system_overrides + shadowed_system); proposals propose→approve/
> reject/expiry (JWT-owner approve — DL-5); registry MCP server (/mcp, 5 tools: list/get/propose/update/set_enabled)
> federated via ai-gateway `registry_` prefix. E2E 25/25 (`p1_rest_smoke.ps1`) + MCP `registry_propose_skill` call →
> pending proposal row proven. **chat-injector** (`c61fac319`): `user_skills_client` (degrade→built-ins) + stream_service
> injects user/book skill L1+L2 alongside SYSTEM_SKILLS, honours disable/shadow; 6 unit tests.
> **FE panels SHIPPED** (`+1 commit`): `features/extensions` (api/types/hooks + SkillsView + ProposalsView, browser-standard,
> call real /v1/agent-registry) + 3 studio panels (ExtensionsPanel hub, ProposalsPanel, SkillEditorPanel singleton) +
> `ui_open_studio_panel` enum(extensions,proposals) + contract regen. Verified: **panelCatalogContract 3/3 + BE contract 20
> + FE tsc clean (all NEW files; pre-existing common.json errors are the OTHER track's uncommitted ModelPicker i18n, not ours)**.
> **STACK-REBUILD E2E DONE ✅ (2026-07-03, full live stack):** `p1_edge_smoke.ps1` 6/6 — BFF proxy CRUD + ai-gateway
> federates all 5 `registry_` tools (prefix) + agent-propose THROUGH the gateway → proposal row (envelope owner survived
> federation). **Full-turn injection PROVEN LIVE:** published user skill (real test account) → `/internal/skills` (fetched
> INSIDE the chat container) → `user_skills_block` → a real **Qwen-7B** turn EMITTED the skill's marker `XYZZY-INJECTED`
> (assistant content == the marker). Post-rebuild /review-impl fixes committed (`02f2a3bbd`: robust `errors.As` dup-detection
> + precise `shadowed_system`; p1_rest_smoke 29/29). **ALL DEFERRALS CLEARED 2026-07-03:** D-REG-BOOK-GRANT (grantclient
> wired → book-tier grant-gated, live 404 fail-closed), REG-X-02 (50-skill quota → live 429), D-REG-SKILLPROPOSAL-CARD
> (chat approve/reject card — AssistantMessage clean again after chat-quality landed; 159 FE tests green), standalone
> /extensions route + save-as-skill affordance shipped, D-REG-P1G-BROWSER (deterministic: registryPanels.test 4/4 mount +
> panelCatalogContract 3/3; live Playwright = when-free follow-up, browser held by concurrent agent). **P1 COMPLETE.**
> **P2 BACKEND SHIPPED ✅ (REG-P2-01/02):** `mcp_server_registrations` + `mcp_server_enablement`; CRUD with mandatory
> `u_<hash8(owner)>_` anti-shadow prefix; internal-only guard (external public host → 400, deferred to P3); book-tier
> grant-gated + Active(); D2 quota (10/user); `/internal/effective-mcp-servers` per-user resolver (endpoint+prefix+version).
> Live `p2_backend_smoke.ps1` 10/10 — **per-user isolation proven** (B can't see A's server), toggle+version-bump, delete.
> **P2 COMPLETE ✅ (REG-P2-03/04):** ai-gateway per-user OVERLAY (`overlay.ts` + handlers) — tools/list merges the caller's
> registered MCP servers over the static System catalog under a u_/b_ prefix; per-(user,book) cache on catalog_version +
> 30s TTL; **fail-open** (resolve error → System catalog only); zero-reg fast path; flag `REGISTRY_OVERLAY_ENABLED` (default
> OFF = byte-identical to today). ai-gateway jest **35/35** + tsc clean. **Live through the rebuilt gateway (flag ON,
> `p2_overlay_smoke.ps1`):** register agent-registry's own /mcp as A's server → A sees 5 `u_<hash>_registry_*` tools, **B
> sees NONE (cross-tenant isolation)**, System providers intact for both (9-provider regression); calling
> `u_<hash>_registry_list_skills` through the gateway DISPATCHED to A's server + returned skills. **THE WHOLE SPEC now works
> end-to-end: a user registers an MCP server / skill → it federates into THEIR catalog only → the agent calls it.**
> **P3 BACKEND COMPLETE ✅ (M1–M4 of 6, 4 commits):** external arbitrary-URL MCP registration + full security.
> **M1 SSRF+vault** (`…`): `classifyRegistrationURL` rejects loopback/RFC1918/ULA/link-local(169.254 metadata)/CGNAT/
> unspecified incl. DNS-rebind (unit fixture suite); model-capability URLs → 400 (provider invariant); bearer secret
> sealed in AES-GCM vault (public = `has_secret` only); `/internal/mcp-servers/{id}/credentials` sole decrypt path;
> external server registers QUARANTINED (pending). Dev flag `AGENT_REGISTRY_ALLOW_INTERNAL_MCP=1` (compose) keeps
> in-cluster targets smokeable; DEFAULT OFF = prod. **M2 scan+quarantine** (`…`): a Go streamable-http MCP probe
> (`probe.go`, SSRF-safe dial + response cap) fetches tools/list; `scan.go` lints descriptions/schemas (OWASP-Agentic
> injection markers + hidden-unicode) → status machine pending→active(clean)/suspended(flagged)/error(unreachable);
> `POST …/rescan`, `GET …/{id}` detail, `POST …/accept-risk`. **M3 egress control** (`ad5bce682`): ai-gateway overlay
> dispatch/list wrap a custom egress fetch (SSRF re-guard + per-server allowlist + 1 MiB cap + manual redirect
> re-validation — closes the round-3 redirect-SSRF defer) + per-server circuit breaker (5-fail→open 30s). **M4 OAuth**
> (`…`): OAuth 2.1 authorization-code + PKCE(S256) + RFC 8707 resource-scoped tokens; `/oauth/start` + PUBLIC
> `/oauth/callback` (single-use state, replay-proof) + background refresh worker; tokens in vault. **SECURITY FIX:** the
> overlay no longer sends the internal envelope (X-Internal-Token) to external servers (would leak our service token) —
> `chooseOutboundHeaders` sends internal servers the envelope, external servers ONLY their own bearer/oauth token.
> **Live-proven:** M1 (`p3_m1_ssrf_smoke` model/scheme reject + vault round-trip), M2 (`p3_m2_scan_smoke` Go probe scanned
> the REAL registry /mcp 5 tools clean→active + down→error), M3 (overlay dispatch through egress fetch, isolation intact),
> M4 (`p3_m4_oauth_smoke` FULL loop vs a host fake AS: start→callback→exchange→vault→decrypt→single-use replay-reject).
> Suites: agent-registry go green; ai-gateway jest 129/129; tsc clean.
> **P3 COMPLETE ✅ (all 6 milestones + review, 8 commits).** M5 FE (`4a8cb8a87`): the two-shell external-MCP surface —
> `McpServersView` (browser list + status chips + paging), `AddMcpWizard` (4 steps: Connection→Auth→Health&Scan→Review),
> `McpServerDetail` (connection + scan report w/ per-finding review + tool browser + **accept-risk**), wired into BOTH the
> studio ExtensionsPanel MCP tab (hidden-not-unmount so wizard state survives §13b) AND the standalone /extensions route.
> M6 QA: OpenAPI mcp-servers contract (`5912bdb61`); **live browser render PASS** (`p3_m5_browser_smoke.mjs`: /extensions
> → MCP tab → Add → wizard advances). **`/review-impl` DONE (`ba576e410`, 2 adversarial reviewers):** token-leak
> boundary / OAuth replay+PKCE / RFC 8707 / token-endpoint SSRF / secret non-serialization / quarantine filter /
> anti-oracle 404s all VERIFIED correct. Fixed: **HIGH** DNS-rebind TOCTOU in the TS egress (now IP-pinned via an undici
> Agent connect-lookup, mirroring the Go probe) · **MED** breaker didn't re-open on a failed half-open trial · LOWs
> (strip Authorization on cross-origin redirect, probe refuses cross-host redirect so X-Internal-Token can't leak,
> accept-risk restricted to scanned+flagged 'suspended' only, /internal token constant-time + deny-on-empty, refresh
> store-failure logged). Re-verified live (rebuilt stack): M2 scan + overlay federation + an actual tool DISPATCH
> through the new pinned-dispatcher egress path. Suites: agent-registry go green; ai-gateway jest 131/131; FE
> extensions+studio 35/35; tsc clean.
> **REAL EXTERNAL-MCP E2E DONE ✅ — `D-REG-P3-EXTERNAL-LIVE` CLEARED** (`p3_external_live_smoke.ps1`): registered a
> GENUINE public third-party MCP server (**DeepWiki**, `https://mcp.deepwiki.com/mcp`, no-auth streamable-http) through
> the real path → classified `is_external=true` + QUARANTINED (pending) → the Go probe scanned its 3 REAL tools
> (`read_wiki_structure` etc.) → clean → active → federated into the user's overlay through ai-gateway → **CALLED
> `read_wiki_structure` through the gateway and got real DeepWiki content back via the pinned egress dispatcher** (external
> + no-auth ⇒ `{}` headers; the internal token is NOT sent) → cross-tenant isolation confirmed (user B saw nothing). The
> only untaken variant is OAuth against a real server (DeepWiki is no-auth) — but the OAuth loop is live-proven vs a
> conformant fake AS (`p3_m4_oauth_smoke`), so the full external path is now end-to-end proven on a real server.
> **P4 COMPLETE ✅ (slash commands + declarative hooks, 5 commits + review).** M1 registry backend
> (`slash_commands` + `hooks` tables + CRUD + `/internal/commands`+`/internal/hooks` resolvers; reserved-built-in
> rejection; DECLARATIVE-only hook actions). M2 chat-service **command expansion** — `/name args` expands in the messages
> router BEFORE persist+stream (so transcript AND model agree; caught live: expanding inside stream_service missed the
> already-persisted history row); pure `expand_command` ({{args}}/positional/named). M3 chat-service **hook engine** —
> pre_turn inject_text folded into the prompt; pre_tool_call **deny** short-circuits the tool at the seam;
> **require_approval** routes to the C2 approval suspend. M4 FE **Commands & Hooks builder** in both shells (studio panel
> tab + /extensions), offering only the wired (event,action) combos. **`/review-impl` DONE** (1 reviewer): tenancy /
> reserved-shadow / action-validation(create+patch) / substitution(no ReDoS) / expansion-placement / deny-loop-accounting
> all VERIFIED correct; **HIGH** require_approval was a silent no-op → WIRED; **MED** annotate/post_tool_call/post_turn
> advertised-but-unwired → gated to the wired matrix at the API (create+patch) + FE; +hook quota. **Live-proven:**
> command expansion (`p4_command_expansion_e2e` — real Qwen turn: /echotest → EXPANDED user msg → assistant echoed the
> marker), hook inject_text (`p4_hook_engine_e2e` — injected secret ZORP-777 retrieved by the model), backend CRUD +
> wired-combo gating (`p4_commands_hooks_smoke`), FE builder (`p4_fe_browser_smoke` — create-via-builder round-trip).
> Suites: agent-registry go green; chat 14 P4-unit; FE extensions+studio green; tsc clean.
> **Deferred (gate #1, out-of-scope collision):** `D-REG-P4-SLASH-AUTOCOMPLETE` — the in-chat `/` autocomplete
> (REG-P4-02) touches the chat-input component under concurrent-track edits; the builder is the primary authoring surface.
> **P5 COMPLETE (buildable slices) ✅ — the AGENT EXTENSIBILITY REGISTRY track is DONE end-to-end (P0→P5).** 5 commits +
> review. **P5-M2 plugin bundle export/import** (`p5_bundle_smoke`): a portable bundle (manifest + skills + commands +
> hooks; MCP servers excluded — secrets aren't portable); import validates EVERY member (same validators as create,
> incl. the skill prompt-only `scripts/` guard) in ONE transaction (all-or-nothing), semver-enforced; the full AC
> roundtrip proven — import→live→export→delete(cascade)→re-import→restored, tampered/scripts/bad-semver → 400.
> **P5-M1 subagent_defs CRUD + resolver** (`p5_subagent_smoke`): named persona (system_prompt + tool_scope subset +
> model_ref) + /internal/subagents + tenancy. **P5-M4 FE plugins + bundle UX** (`p5_fe_browser_smoke` — live file-upload
> import round-trip + export download). **`/review-impl` DONE** (1 reviewer): txn correctness / export-tenancy /
> MCP-secret-exclusion / FK-cascade / subagent authz all VERIFIED; **2 MED** fixed (import bypassed the skill validators
> → validateSkill parity closes the `scripts/` prompt-only hole; unvalidated plugin version → filename injection →
> semver on create+patch + filename strip) + 2 LOW (subagent quota, System UNIQUE index). Suites: agent-registry go
> green; FE extensions+studio green; tsc clean.
> **▶ `D-REG-P5-SUBAGENT-RUNTIME` ✅ SHIPPED + LIVE-PROVEN 2026-07-03 (this session; plan
> [`2026-07-03-subagent-runtime.md`](../plans/2026-07-03-subagent-runtime.md)).** The scoped nested execution is live:
> `run_subagent` is a **chat-service loop primitive** (peer to `find_tools`, consumer-local — NOT federated → no
> cross-service cycle), advertised iff the user has ≥1 enabled subagent, as a **closed-set enum** of names. On call it
> runs a nested isolated `_stream_with_tools` with **FRESH messages** (`[system: persona, user: task]` — no parent
> history), the persona's **scoped tool set** (caller catalog ∩ `tool_scope` globs, minus meta/frontend tools), and returns
> ONLY the capped synthesized text (nested messages never enter the parent `working`; nested chunks consumed, not re-yielded
> — isolation held). **Scope enforced TWICE** (advertise-time set + execute-time `allowed_tool_names` whitelist rejecting a
> fabricated out-of-scope/meta/frontend call with `result.error`). **No-escalation:** clamped read-only
> (`permission_mode='ask'`) — even a subagent scoped to a write tool can't write (ask filter drops it at advertise AND the
> ask-block rejects at execute). **Depth=1** (advertise gated depth 0 + whitelist excludes `run_subagent` + handler gated
> depth 0 = triple guard). Nested tokens sum into the turn total (D10); a `subagent_run` activity carries name + tools_used.
> Files: `app/services/subagent_runtime.py` (pure) · `_run_subagent_call` + loop wiring in `stream_service.py` ·
> `registry_subagents_client.py` (degrade-safe → no delegation) · `main.py` lifecycle. `_meta` stripped before the wire in
> the nested run (top-level path byte-identical). **`/review-impl` DONE** (self, load-bearing = nested exec + privilege):
> 1 LOW **fixed** (nested-suspend token attribution now read from the suspend chunk); 2 LOW **accepted+documented** (a
> `require_approval` hook on a scoped tool ends the sub-run early — fails SAFE; a reasoning subagent model on a tight budget
> yields empty answer content — handled gracefully). VERIFY: **30 subagent units** (pure resolver, nested isolation/clamp,
> loop-level whitelist via the real `_stream_with_tools` harness) + full chat suite **774 green** · **LIVE E2E-P5-A** —
> Part A in-container (`p5_subagent_runtime_incontainer.py`): a REAL nested LLM turn through chat→provider-registry→lm_studio
> (Qwen 7B, in=38/out=33, synthesized isolated answer); Part B full HTTP loop (`p5_subagent_runtime_smoke.ps1`): the gemma
> tool-calling model **chose** `run_subagent` → nested lore-scout ran → dragon answer reached the main turn, **no write tool
> in the transcript** (scope held). **Follow-up (tracked, gate #2):** `D-REG-P5-SUBAGENT-WRITE-DELEGATION` — lift the
> read-only clamp so a subagent can perform an approved write (needs nested approval-suspend bubbling up through
> `run_subagent`; today ask-clamp is the safe v1).
> **▶ `D-REG-P5-REGISTRY-INGEST` ✅ SHIPPED + LIVE-PROVEN 2026-07-03 (this session; plan
> [`2026-07-03-registry-ingest.md`](../plans/2026-07-03-registry-ingest.md)).** Admin populates the System-tier MCP
> catalog from the **official MCP Registry** via a curation queue instead of hand-typing each server. New
> `registry_ingest_queue` (source+registry_id unique; pending|approved|rejected; `approved_server_id` FK) +
> `uq_mcp_reg_system` partial UNIQUE(endpoint_url) for approve-time dedup. **Pull** (`POST /admin/ingest/pull`) fetches
> `{base}/v0/servers` through the **SSRF-safe probe client** (IP-pinned dial + cross-host-redirect refusal), cursor-paged
> (cap 10), body-capped (8 MiB), fail-soft. `mapUpstreamEntry` is tolerant (flat + nested-`server` shapes,
> type/transport_type variants, `version_detail` fallback, id→reverse-DNS-name); picks the first streamable-http remote,
> **counts** no-remote skips (never silent). Idempotent upsert on `(source,registry_id)` that refreshes descriptive fields
> but **never downgrades** an approved/rejected row → pending. **Approve** (`POST /admin/ingest/queue/{id}/approve`)
> **reuses the P3 pipeline wholesale** — `looksLikeModelEndpoint` → `classifyRegistrationURL` (SSRF) → INSERT System-tier
> `mcp_server_registration` (`is_external`, `pending`) → `scanAsync` (pending→active/suspended) → link + mark approved.
> Endpoint dedup links an existing System row instead of duplicating; a guard failure leaves the row pending. Admin-only
> (`requireAdmin` → 403) + anti-oracle 404 + audit. **verification ≠ safety:** an official listing still runs the full
> SSRF guard + supply-chain scan before it federates. Files: `internal/api/ingest.go` + `server.go` routes +
> `migrate.go` + `config.go` (`OfficialRegistryURL`). **`/review-impl` DONE — a 2nd DEEP pass (`3659ba203`) found + FIXED
> 2 MED + 4 LOW/COSMETIC** (the 1st pass's "no MED" missed the cross-service federation angle): **MED#1 tool-shadowing** —
> an ingested external System server federated UNPREFIXED (`tool_name_prefix=''`), so once scanned-clean it could shadow a
> platform tool name with an attacker-controlled schema (and its tools weren't even dispatchable). FIX: external System
> servers (ingest + `createMcpServer`) now namespaced `s_<hash8(endpoint)>_`; the ai-gateway overlay owns the `s_` prefix
> (`OVERLAY_NAME_RE /^[ubs]_/`) so they're dispatchable AND can't shadow. Live-verified (`s_c3d80a4e_`). **MED#2 boot
> safety** — the new `uq_mcp_reg_system` UNIQUE index would crash-loop startup on a pre-existing dup System endpoint; FIX:
> wrapped in a `DO`-block catching `unique_violation` (skip+NOTICE; check-before-insert still guards new dups). **LOW#3**
> the `isUniqueViolation` race-recovery branch now tested (pgxmock: dedup-miss→INSERT 23505→re-SELECT→link). **LOW#4**
> `pullCounts.Truncated` flags a partial pull (timeout/mid-error/page-cap) +httptest unit. **LOW#5** `clampStr` caps
> upstream strings (rune-safe) +unit. **COSMETIC#6** idempotency-coverage comment. ⚠️ **ai-gateway needs redeploy** for
> the `s_` overlay change (done in dev; the `s_` DISPATCH itself is inspection+tsc-verified — no controllable external MCP
> server exists for a live dispatch smoke). VERIFY: full agent-registry Go suite green (+race/truncated/prefix/clamp
> units) · ai-gateway tsc 0 errors · **LIVE E2E-P5-C re-run ALL-PASS** incl. the new `s_` prefix assertion — Part 1
> (DB-seeded queue → real HTTP): admin-gate, approve→System is_external row **namespaced s_<hash>_** + scan, re-approve
> 409, endpoint DEDUP held (exactly ONE row), reject, idempotent upsert; Part 2 (**real official MCP Registry pull**):
> fetched 100, mapped 43 new + 70 updated, 30 no-remote skips (SSRF-safe fetch + mapper proven on real /v0 data).
> **Deferred (tracked):** `D-REG-P5-INGEST-SCHEDULED-WORKER` (gate #2 — the hourly pull worker + denylist/retroactive-
> removal sync §7b#1 + rug-pull periodic rescan §7b#2; folds `D-REG-P3-SCHEDULED-RESCAN`; needs a background loop);
> `D-REG-P5-INGEST-ADMIN-FE` (gate #3 — the admin curation table lands in an admin/CMS surface that **does not exist yet**
> in `frontend/src`; the backend is fully driveable via the admin API).
> **Still deferred:** `D-REG-P4-SLASH-AUTOCOMPLETE` (gate #1). `D-REG-P5-SUBAGENT-WRITE-DELEGATION` (gate #2).
> **The whole track is production-usable:** a user registers skills / external MCP servers (OAuth+SSRF+scan) / slash
> commands / declarative hooks / subagent personas (**live scoped execution**), bundles + shares them; an admin **curates
> the System catalog from the official registry**; and the agent federates + expands + delegates to them — all
> tenancy-scoped, adversarially reviewed, live-proven.
> **▶ TRACK CLOSE-OUT (2026-07-03) — 5 of 6 remaining defers CLEARED + the 6th SPEC'D**, each with tests + a commit. Plan
> [`2026-07-03-registry-track-closeout.md`](../plans/2026-07-03-registry-track-closeout.md).
> **M1 `D-REG-P5-INGEST-SCHEDULED-WORKER`** (+folds `D-REG-P3-SCHEDULED-RESCAN`) `15bcbfe82` — Go worker (off by default):
> re-pull + denylist/retroactive-removal sync (absent-upstream approved → suspended + `revoked_upstream`, only on a
> COMPLETE pull) + rug-pull rescan; 4 tests. **M2 `D-REG-P5-INGEST-ADMIN-FE`** `f408a7d09` — admin curation surface
> (role-gated tab; jwtRole show/hide, API is the real gate); 7 tests. **M3 `D-REG-P4-SLASH-AUTOCOMPLETE`** `56afe9b71` —
> the in-chat `/` picker now surfaces the user's registry `/name` commands above templates (picker owns the fetch → no
> ChatInputBar churn); 8 tests. **M4 `D-REG-BOOK-TIER-FE`** backend `47609a7f6` + FE `ae8152ff8` — NOT "additive FE": the
> 5 list endpoints returned only system+user, so added a grant-gated `book_id` filter to ALL (`resolveListBookScope`,
> anti-oracle 404) + a shared ExtensionScope context wiring book-scope into all 5 capability hooks; tests + studio default-
> context safe (30 green). **M6 `D-REG-P5-SUBAGENT-WRITE-DELEGATION`** `44ce1f501` — SPEC ONLY (user-gated): bubble the
> nested Tier-A suspend up through run_subagent (subagent_frame) + two-level resume; read-only v1 stays the safe default.
> VERIFY: agent-registry Go green · FE extensions+chat **71 green** · tsc clean.
>
> **▶ CLOSE-OUT FINISHED 2026-07-03 — M5 + M7 DONE; TRACK FUNCTIONALLY CLOSED.**
> First restored git coherence: the **Subagents + Activity GUIs were on disk but never committed** (a prior shared
> commit that supposedly carried them was reset by the concurrent ai-task agent) while my M4 tests already imported
> `SubagentsView` — committed the 4 files + studio wiring `4e15711d2` (14 tests).
> **M5 `3729d3213` — HONEST checklist, NOT a rubber-stamp.** The `01_GUI_CHECKLIST` enumerates the FULL draft-ui.html
> vision (270+ boxes); most is genuinely unbuilt rich polish. Per [[checklist-is-self-report-enforce-by-tests]] I ticked
> ONLY lines a passing test proves: wrote `skills.test`(8) + `proposals.test`(5) for the two richly-built-but-untested
> views (search/tier/sort/pager/empty/error/rows · status-filter/approve/reject/empty), then rewrote the checklist to
> **59 test-backed ticks (up from 0)**, each citing its test. The unbuilt remainder (bulk actions, shared Pager, skills
> editor+revisions, 24h health charts, per-step wizard validation, typed-confirm cascade, **i18n vi/en**, **a11y
> focus-traps**) is honestly tracked as **D-REG-GUI-RICH-POLISH** (defer gate #2), not fake-ticked. Extensions suite 47 green.
> **M7 `977dc8536` — LIVE E2E (rebuilt agent-registry image).** M4 book-tier tenancy 5/5 live through the gateway
> (`m4_book_tier_tenancy_api.mjs`): create-on-owned→200 · list?book_id→visible · list-no-book_id→**hidden (no cross-tenant
> leak)** · list?book_id=FOREIGN→**404 anti-oracle** · create-on-FOREIGN→denied. M1/M2 ingest routes → **403 for non-admin**
> (wired + admin-gated). Re-ran `p5_subagents_fe_browser.mjs` vs vite :5199 on current FE → shell+Subagents+Activity+real
> POST/audit round-trip PASS. **Honest live gaps (not fake-claimed):** the external public-registry PULL (admin JWT + live
> `registry.modelcontextprotocol.io`) = gate #4, cycle unit-proven (4 tests); M2 admin-FE + M3 slash + M4 book-scope-FE are
> unit-proven, not yet in a browser smoke (the shell IS). **The 5 defers are CLEARED; the track is functionally closed.**
>
> **Deferred (gate #2 — earns its row): `D-REG-GUI-RICH-POLISH`** — the draft-ui.html rich layer (bulk actions · shared
> `Pager`/`useServerPagedList` across all lists · skills 3-col editor + revision history · 24h health-history charts + p50/p95
> · full 4-step wizard per-step SSRF/OAuth validation UI · typed-confirm cascade-delete dialogs · **i18n vi/en** · **a11y
> focus-trap sweep**). Large/structural, needs its own plan. See `01_GUI_CHECKLIST.md` Tally (58/288 test-backed).
>
> **▶ POST-CLOSE-OUT FOLLOW-UPS SHIPPED (2026-07-03).**
> **(1) Nav entry point `ed879b764`** — the `/extensions` GUI was an **orphaned route with NO nav entry** (users couldn't
> find it; it's not a Settings tab). Added an **Extensions** item (Puzzle) to the Sidebar manage group + `nav.extensions`
> i18n (en/vi/zh/ja); Studio path already worked (catalog `OPENABLE_STUDIO_PANELS`). Test: `Sidebar.test` asserts the
> `/extensions` link renders. **Frontend image rebuilt** (:5174 now current). *(NOTE for future: "MCP Access" in Settings is
> a DIFFERENT feature — public MCP API keys for EXTERNAL clients to reach IN; the Extensions registry is capabilities for
> the agent INSIDE. Opposite directions.)*
> **(2) `D-REG-P5-SUBAGENT-WRITE-DELEGATION` ✅ SHIPPED `61a617094`+`f523c86f6` (defer CLEARED).** A capability audit (2
> Explore agents, evidence-backed) confirmed the architecture is "strict data boundary + absolute enforcement AT THE TOOL
> LAYER": every MCP tool re-auths the `X-User-Id`+internal-token envelope + grant-gates scope (never a model arg;
> `ForbidExtra`), and Tier-W/destructive/priced ops are **mint→browser-JWT-confirm only** (structurally unrunnable from a
> loop). So the read-only subagent clamp was a *conservative default, not the security boundary* — a subagent write is safe
> by construction (bounded to the caller's tenant + its `tool_scope`). **Dropped the heavy nested-suspend/two-level-resume
> spec** as over-engineered; shipped the SIMPLER "allowlisted Tier-A, no suspend": `clamp_permission_mode = min(caller,
> write)`; fixed the plain-path tier resolution (was hardcoded "R" → would've let a subagent auto-commit ANY Tier-A); a
> write sub-run auto-commits ALLOWLISTED Tier-A, but un-allowlisted Tier-A / require_approval-hook / the volume-cap all
> return a `result.error` (headless sub-run can't raise the card) instead of a swallowed suspend. `/review-impl` caught the
> volume-cap-suspend gap (fixed). 116 chat-service tests green. Spec updated to SHIPPED.
>
> **▶ EXTERNAL-MCP INTEGRATION — FULL LOOP LIVE-PROVEN end-to-end (2026-07-03).** Registered a REAL free public MCP
> server (**DeepWiki** `https://mcp.deepwiki.com/mcp`, no-auth) on the test account and drove the whole chain live:
> **register** (SSRF pass · egress-allowlist auto · transport auto `streamable_http` · namespace `u_a2bbc662_`) → **scan**
> (health 3 tools · injection-scan clean · auto-active) → **federation** → **model autonomously calls it** → **dispatch to
> the real server** → **result rendered in the agent's answer**. The live test found + fixed **two real consumer-wiring
> bugs** (both committed, tested):
> **(a) `fix(chat): wire the per-user overlay into the turn catalog` `a5cf762ec`** — `get_tool_definitions()` sent no
> `X-User-Id` + cached process-wide, so the ai-gateway federation overlay (REG-P2-03, `u_/b_/s_` external tools) NEVER
> reached a real chat turn's LLM. Fix: pass `user_id` (→ `X-User-Id`) + PER-USER cache with a 60s TTL (`_TOOL_CATALOG_TTL_S`;
> overlays differ per user + change on register/remove). Both turn callers updated.
> **(b) `fix(chat): accept plain-text results from external overlay tools` `e1932b40c`** — `mcp_execute_tool` `json.loads()`
> every result, but external tools return PLAIN TEXT (DeepWiki returns prose) → every external result died as "unparseable
> content". Fix: on decode-fail, if the tool matches `_OVERLAY_TOOL_RE` (`^[ubs]_[0-9a-f]{8}_`) wrap as `{"text":…}` success;
> internal tools stay strict-JSON. **Final live turn (Gemma-4 26B): MODEL_CALLED_DEEPWIKI=True, DISPATCH_OK=True**, the real
> wiki structure of `modelcontextprotocol/servers` rendered in the reply. 78 chat-service tests green for these.
> **Ops note:** the overlay is flag-gated — `REGISTRY_OVERLAY_ENABLED=true` (default false, a rollout gate). Set via shell
> env at `docker compose up` time (NOT persisted; a stack recreate without the env reverts to false — add to `.env`/compose
> for permanence). CAVEAT: `docker compose up -d <svc>` re-evaluates `${VAR:-false}` for dependencies, so it can silently
> flip the gateway's overlay off — set the env in the SAME shell. The overlay dispatch also has a circuit-breaker that trips
> under repeated hammering of a flaky free server (fail-open → no overlay that turn); a gateway recreate resets it.
>
> **▶ CORRECTION (2026-07-03) — the earlier "TRACK COMPLETE P0→P5" claim was WRONG: it was BACKEND-complete but 2 FE
> screens shipped as backend-only.** A design↔shipped reconcile vs `design-drafts/screens/plugin-register/draft-ui.html`
> (nav: Plugins/MCP/Skills/Commands/Hooks/**Subagents**/**Activity log**) found the FE missing Subagents + Activity —
> and `01_GUI_CHECKLIST.md` (273 boxes, **0 ever ticked**) proves the checklist was authored but never used as a gate
> (see memory [[checklist-is-self-report-enforce-by-tests]]: a checklist is self-report; DONE = a test asserts the EFFECT).
> **BUILDING NOW** `D-REG-P5-SUBAGENTS-FE` (persona CRUD GUI — backend CRUD+resolver+runtime all shipped, FE was zero) +
> `D-REG-P5-ACTIVITY-FE` (Activity-log over `/audit` — U4 in EVALUATION, never built). Plan
> `2026-07-03-registry-missing-guis.md`. Remaining backend rows unchanged (scheduled-worker, admin-FE, slash-autocomplete,
> subagent-write-delegation) — all tracked, none blocking.
> **Decisions:** `DECISION_LOG.md` (DL-1..9 + 6 review rounds). **Defers: P4 autocomplete + P5 write-delegation + P5 ingest-scheduled-worker + P5 ingest-admin-FE; P3/subagent-runtime/registry-ingest CLEAR.**
>
> **▶ CHAT QUALITY WAVE — W0 + W1 SHIPPED + LIVE-SMOKED 2026-07-03 (parallel sub-agent build, disjoint files,
> combined verify).** Trigger: user's 8-item quality pass (plan + 5-investigation evidence base incl. a LIVE MCP
> failure audit: 26-30% hard-error rate). **W0 MCP reliability:** base_version hallucination-trap killed (409 embeds
> current version; implausible timestamp = not-read shim — top bucket, 22% of errors), real JSON-schema enums at 22
> glossary sites + jobs, filter args accept the one-element-list shape (jobs/knowledge/translation), pydantic errors
> rewritten to one-line model directives at the FastMCP chokepoint, "must be in scope" errors now name `project_id` +
> the NEW `kg_project_list` tool, ai-gateway classifies errors (transport vs sanitized-upstream vs unknown-tool — no
> more blanket "provider error"), CLOSED_SET_ARGS contract tests extended to MCP servers. **W1 context-breakdown
> spine:** 12-category per-turn token map measured at the assembly seam (incl. the previously-unmeasured TOOL-SCHEMA
> buckets), contextBudget frame extended additively (+breakdown/+baseline_tokens/+until_compact_pct), new `compaction`
> frame (was log-only), `chat_messages.context_breakdown` persisted, knowledge build_context returns per-section
> tokens, `GET /internal/tool-health` (per-tool error rates — W0 improvement measurable). **LIVE smokes (real chain):**
> chat-container→gateway→domain: enum survives federation + kg_project_list federated + list-unwrap e2e +
> self-correcting scope error passes the gateway unlaundered; REAL gemma turn: frame carries breakdown (live insight:
> bare turn = skills 1907 tok + FE-tool schemas 1484 + MCP 193 — the invisible buckets now visible) + DB row persisted.
> **Also:** translation's 13 stale failures CLEARED (confirm_action header-auth drift ×11, default-vs-fill drift,
> offload test now hermetic via TEMP-table shadow); **pytest-xdist adopted** (CLAUDE.md rule; composition 418s→55s,
> translation 37s; 8 PG-hitting files carry `xdist_group("pg")`). Suites at close: chat 665 · knowledge 3374 ·
> composition 1472 · translation 1031 (was 13 red) · jobs 95 · glossary ok (+DB-gated live) · ai-gateway 110.

> **▶ #12 CYCLE-1c — F4 SCENEMARKER-EMIT + J1 MULTI-INSTANCE JSON EDITOR — SHIPPED + LIVE-SMOKED 2026-07-03.**
> `D-SCENEMARKER-EMIT` CLEARED (RAID quiet window opened): a generated chapter now lands **pre-anchored** — no ⚓
> needed. Root finding: composition's `prose_doc.text_to_tiptap_doc` mirrored only tiptap.go's *plain* variant; the
> *markdown* heading variant was never mirrored, so the server persist path flattened `###` lines into paragraphs.
> **F4a** `prose_doc.py` lifts leading ATX headings into heading nodes (tiptap.go byte-shape, level≤3) and, given
> `scenes`, sets `attrs.sceneId` on a normalized **unique**-title match (`normalize_title` = exact port of FE
> `SceneAnchor.normalizeTitle`, diacritics significant; ambiguous/duplicate/unmatched → unmarked, never wrong);
> canary extended to pin the Go heading tokens. **F4b** `chapter_scene_drafts` returns `{title,text}` rows; stitch
> input becomes `### <title>\n\n<text>` per scene (`prepend_scene_headings`, skip when already headed); stitch
> prompt gains a keep-headings-verbatim guard (injected only when headings present); the degraded concat carries
> markers deterministically. **F4c** `_persist_chapter_draft(scenes=…)` wired at all 3 chapter persist sites
> (inline chapter-generate, inline stitch, `POST /jobs/{id}/persist` — best-effort scene fetch, never blocks).
> **LIVE E2E** (POC book, Qwen2.5-7B LM Studio): stitch job kept **3/3** `###` headings through the real merge →
> persist → book draft v3 carries 3 heading nodes each with the EXACT outline sceneId (psql-verified, VN titles).
> Caught live: `infra-composition-worker` is a **separate image** from `infra-composition-service` — rebuilding only
> the service left the worker stale (first smoke ran old code). **J1** json-editor is now **multi-instance**:
> `host.openPanel` gains `component` (dock id ≠ catalog component); "Open as JSON" opens
> `json-editor:{docType}:{chapterId}` per chapter (re-open focuses); panel self-titles (`JSON · <id8>`) and no
> longer registers in the host registry (two instances corrupted register/unregister). **Suites:** composition
> **1526** unit green · FE studio+editor **272/272** + tsc clean. Plan: `docs/plans/2026-07-02-chapter-editor-completeness.md` §Cycle-1c.

> **▶ WAVE D — COMPLETE 2026-07-02 (autonomous run, sub-agent build + orchestrator verify).** The autonomy dial's
> full backbone in composition-service: **D2** `authoring_runs` FSM (7 states, OCC-guarded transitions, all-or-nothing
> start-gate: validated plan + scope-fence unique-index (1 active run/book) + budget + allowlist snapshot; sequential
> driver over the REAL drafting seam — EngineDraftingSeam mirrors actions.py's in-process generate_chapter, worker-off
> inline + worker-on 202-poll). **D3** `authoring_run_units` ledger (pre_revision pinned BEFORE each draft — no draft
> without a rollback spine; book-service snapshots every PATCH so latest revision = a TRUE pre-run restore point);
> Run Report (partial-reviewable, downstream indexes); accept/reject (reject restores with the CALLER's bearer,
> restore-failure leaves drafted, cascade_warning); Revert-All (reverse order, closes the run). **D4** durability:
> driver_id+heartbeat, startup+periodic sweep (FOR UPDATE SKIP LOCKED claim — live-proven on real PG), per-unit
> heartbeat-claim closes the late-result race (late draft lands failed "run closed mid-flight", spend kept);
> completion notify via notification-service HTTP ingest (category=system, operation=autonomous_authoring in
> metadata — mirrors the translation producer); background flag + DRIVER_MAX_INFLIGHT. **D5** per-unit critic wired
> to the REAL M6/Q1 judge (judge_prose 4-dim + canon violations; critic_model_ref anti-self-reinforcement); severe →
> PAUSE with breaker {critic_severe, unit, summary} (human reviews report); critic failure → warn "critic
> unavailable", never breaks a run; verdict on the unit row + in the report; params.critic_enabled default TRUE.
> **Suites:** composition tests/unit **1516** green (fresh tails per milestone; +105 across D2-D5). Honest stubs
> recorded in-code: canon grounding headless (empty rules), unit+critic costs are estimates (SDK exposes no metered
> cost — real cost only where generation_job.cost_usd populates).

> **▶ /review-impl over Wave D — 1 HIGH + 4 MED found, ALL FIXED 2026-07-02 (user: "fix all").**
> **HIGH `6c2ba94e0`:** start-gate false-rejected books >100 chapters — `BookClient.list_chapters` asked limit=200 but
> book-service clamps every page to 100 (chapter-list-limit100 bug class); client now PAGINATES (100/page, 2000 cap),
> all 3 call sites (gate, planner A3, plan verify) see the whole book. **MED fixes (same follow-up commit):**
> (1) late writes driver-fenced — `mark_drafted` gains `run_driver_id`, `record_unit_progress` cursor is CASE-fenced
> (spend always lands); a sweep-STOLEN run's superseded driver can no longer double-draft or rewind the cursor
> (plausible here: worker-off inline has no poll timeout, slow local model >40min → steal). (2) late-swallow now
> RESTORES content — close/fail mid-flight already swallowed the row, but the engine had PATCHed the draft;
> the driver now best-effort restores the pinned pre_revision (honest error_message either way). (3) breaker pauses
> NOTIFY (budget | critic_severe) — 07S "interrupt on severe" now actually reaches the human (same ingest channel).
> (4) book-OWNER-grant may pause/close a collaborator's run (acts AS the run owner; scope fence is per-book, so an
> abandoned grantee run used to lock the book forever; start/resume stay owner-only — they spend the owner's budget).
> **LOW fixes:** deferred-at-cap claim now RELEASED (NULL heartbeat → next sweep picks it up; was a 40-min stall);
> gate maps book-service 401/403 → 403 (was 502 "outage"). New SQL live-proven on real PG (CASE fence, release_claim,
> driver guard). Deferred: `D-RAID-ALLOWLIST-ENFORCE` — tool_allowlist is gate-validated+snapshotted but the v1
> driver never consults it (v1 seam calls no agent tools — vacuously safe; enforcement gate #3 naturally-next-phase,
> lands with agentic tools riding runs). COSMETIC accepted: `level` 3|4 stored, runtime-indistinguishable in v1.

> **▶ AUTONOMOUS RUN — RAID waves C5/C4/C1/C2/B2 SHIPPED 2026-07-02 (sub-agent build + orchestrator verify pattern).**
> **C5 MCP resources+prompts** (`99bc63215`, LIVE-PROVEN): knowledge exposes 2 project resource templates
> (summary/entities) + 2 prompts (recap/dossier); ai-gateway federates resources/templates/prompts (scheme==provider
> gate; -32601-tolerant); chat client list/read/get (degrade pattern). Live: chat→gateway→knowledge real entity data.
> **C4 @-mention** (`554373f33`): inline mention popover in the chat input (books/chapters/entities, startsWith>
> contains, keyboard nav) attaching through the SAME ContextBar seam; useContextCandidates extracted (ContextPicker
> adopted); chat i18n parity test added. **C1 steering store** (`e7917a72d`, LIVE-PROVEN, DR-C1): book_steering in
> book-service (scope UNIQUE(book_id,name), owner+E0-EDIT writes, VIEW reads, 20-row/8000-char caps, execGuarded
> migration); chat renders <steering> after the system prompt on both paths (always ∪ #name ∪ scene_match(title),
> 2000-token soft cap, degrade-to-skip). Live: gateway-create→internal→select→render with real VN entry. **C2 HITL
> modes** (`a0b926dab`, DR-C2): permission_mode ask|write; ask = tier-R+frontend surface (advertise-chokepoint filter
> + defense-in-depth); write gains the Tier-A prompt-once approval via the EXISTING suspend/resume machinery
> ({kind:tool_approval} rides pending args — NO new frontend tool); user_tool_approvals (fail-open reads);
> suspended-run carries the mode (no escalation); surface snapshot test pins write==pre-C2. FE toggle + ToolApprovalCard.
> **B2 Plan mode** (`28a275ced`): permission_mode 'plan' = ask surface + plan_* tools (no C2 prompt for plan_*, pinned
> write-only); plan_forge skill auto-injects on book/editor; PLAN nudge on both paths; 3-way FE toggle. Sub-agent
> FIXED an M4 bug: plan_forge L2 body was silently dropped even when pinned. **Suites at close:** chat-service 631 ·
> knowledge 3349 · book-service green (DB-gated) · ai-gateway 103 · FE chat 287+parity. All services rebuilt live.

> **▶ Track 4 SALIENCE — COMPLETE 2026-07-02 (autonomous run).** All buildable phases shipped flag-gated (defaults =
> byte-identical): **P0** access telemetry (live-proven) · **P1** access blend (eval verdict: KEEP w=0 — explicit-query
> REGRESSION, spec §8b) · **P2** cross-encoder L3 rerank (live-proven e2e via local bge-reranker; per-project opt-in)
> · **P3a** graph-native promotion (evidence/mention/edit-recency) · **P3b** thumbs→entity attribution (user
> challenged the deferral; verification DISPROVED it — consumer existed, 1 additive column sufficed; `4635f3dfb`) ·
> **P4** pointer demotion instead of glossary drop (+`memory_recall_entity` as the expand affordance — no new tool
> needed) + widened 2-hop L2 retry on fact-miss (default ON, kill-switch; `d535293fd`). **P5 = 4 decision records**
> (R-T4-03 prune / 04 auto-merge / 08 metadata / 09 compaction-LFU-bridge), each verified + trigger-gated in spec §5
> — unlike P3b these survive scrutiny (data-safety / no-signal / hot-path-cost reasons, not effort). Salience flip
> gate = ambiguous-query eval (P1's explicit-query set penalizes re-ranking by construction). Eval CLI:
> `python -m eval.run_salience_eval`. Also cleared en route: book `_text` bug class (5 sites), worker skip
> false-green, config write-path, FE PUT-replace clobber.

> **▶ STUDIO DOCKABLE MIGRATION — WAVE 1 SHIPPED 2026-07-02** (spec [`11_dockable_migration.md`](../specs/2026-07-01-writing-studio/11_dockable_migration.md),
> human-in-loop track running IN PARALLEL with the autonomous run — conflict-first ordering per W1-5). Foundation
> seams: **F2 status-bar contribution API** (`registerStatusBarItem`/`useStatusBarItems` — ⚠️ **RAID A3 status-bar
> meter MUST register through this, never edit `StudioStatusBar.tsx` directly**; first consumers shipped: unread
> badge + 24h cost meter, bus-owned `notificationsUnread`), **F1 `openPanel(…, {params})`** deep-link (+
> `updateParameters` when open), **F3 `resolveStudioLink`/`followStudioLink`** (same-book chapter→focus, panel
> paths→openPanel, fallback = NEW TAB — `navigate()` in panels is a defect). Panels: `usage`/`trash` thin wraps
> (TrashPage `embedded` prop), `notifications` (resolver + bus unread sync), `settings` (route tab → `params.tab`).
> `ui_open_studio_panel` enum +4 + contract JSON regen done INSIDE the Track-4 window (W1-7 — later RAID B/C waves
> regen on top, no race). VERIFY: FE 3085/3085 + chat-service frontend-tools 43 green.
> **`D-DOCKW1-LIVE-SMOKE` CLEARED 2026-07-02 (Playwright live browser smoke, vite:5199 + rebuilt chat-service):**
> status-bar badge `99+` + meter `$1.17` live with real data; meter-click → Usage panel (1531 real rows); badge-click
> → Notifications panel; palette lists+opens all 7; Settings 6 tabs (mcp Q-GATE on); Trash embedded (no breadcrumb);
> **agent loop by EFFECT:** gemma-26b (LM Studio) got "mở panel Trash" → `ui_open_studio_panel(trash)` (NEW enum
> value) → Lane-A → dock tab FOCUSED in 6s → model confirmed truthfully. Side-findings (pre-existing, not W1):
> `D-TRASH-GLOSSARY-404` — TrashPage's per-book `GET …/glossary/entities?lifecycle_state=trashed` 404s (glossary
> trash tab dead; gate #1 out-of-module); notification SSE reconnect dies on jwt-expired (`?token=` never refreshes —
> long studio session loses the live badge); **LM Studio queue can WEDGE after a client disconnects mid-stream**
> (`lms ps` says IDLE but completions hang ∞) — fix: `lms unload <model> && lms load <model> --context-length N`.
> **/review-impl (b1dca941b): 2 MED + 2 LOW found + FIXED** — protocol-relative `//` external-origin escape
> (notificationLink + resolver both hardened), settings same-value deep-link swallowed (now `onDidParametersChange`),
> badge pre-fetch-0 clobber (`unreadLoaded` gate), catalog⇄panel import cycle (i18n-convention titleFor). 3089/3089.
> **Side-findings CLEARED (user-mandated fix-before-wave-2):** `D-TRASH-GLOSSARY-404` FIXED — root cause FE-only:
> `useTrashItems` guessed `/v1/books/{id}/glossary/entities?lifecycle_state=trashed` (never existed) while
> glossary-service already ships the FULL recycle-bin API (`/v1/glossary/books/{id}/recycle-bin` + `/{eid}/restore` +
> `DELETE /{eid}`, `permanently_deleted_at` soft-purge + snapshot trigger). 3 URLs re-pointed; live-proven e2e in the
> studio Trash panel (real backlog rows listed; GUI Restore → `deleted_at` NULL; GUI purge → `permanently_deleted_at`
> set). *The "blocked on a missing route that already exists" pattern struck again.*
> **SSE jwt-expiry FIXED** — `useNotificationStream` on error checks the JWT `exp` (fail-open for opaque tokens):
> expired → single-flight `refreshAccessToken()` (now exported from api.ts) → `lw-auth-refreshed` → effect reconnects
> with the fresh token; refresh-fail → idle. No more infinite dead-token reconnect loop in idle studio tabs. +3 tests.
> LM Studio wedge stays an external-tool recipe (memory); a chat-service first-token timeout guard belongs to RAID
> Wave-A's LLM seam if wanted. FE suite 3092/3092.
> **▶ #12 CYCLE 1 (chapter editor) — BUILT + partial live proof; gate retest needs a QUIET WINDOW · 2026-07-02.**
> Shipped: M-A JSON substrate (registry #4, DocumentHandle, CM6 json-editor panel) `849e5fa1e` · M-B manuscript-unit
> provider + hoist scenes[] + `GET /works/{pid}/chapters/{cid}/scenes` `c4e0dbf27` · M-C **Scene Rail** (navigator
> scene click finally does something) `b268ade0e` · M-D Lane-B outline handler `c60ad95b8` (the MCP tool
> `composition_outline_node_update` already existed — audit corrected) · **`story_search` universal manuscript
> search** `3b3ac9263` (AS1–AS4 research-locked in spec 12: ONE simple tool over `run_hybrid_search`; NO temp-file
> workspace — the DB indexes ARE the engine, GitHub-Blackbird evidence; ZERO required location args via ambient
> ToolContext; knowledge suites 216/216; image rebuilt). **Browser-verified:** Scene Rail renders real scenes;
> json-editor shows the full envelope; two live-caught bugs fixed (resolveWork ENVELOPE `{status,work}` — a bare
> `.project_id` read returns undefined; EditorPanel missing `host` ref).
> **M-E LIVE GATE ✅ PASSED 2026-07-02 — `D-C1-GATE-QUIET-WINDOW` CLEARED** (retest after the RAID chat wave, per
> AS4 natural-language-only). Full loop proven in the browser on gemma-4-26b, NO hand-fed ids: VN prompt → agent
> `composition_get_work(book_id)` → `composition_list_outline(project_id)` → self-located the right scene node →
> **C2 Tier-A Approve** → DB `outline_node` synopsis v1→2 + status→drafting v2→3 (psql-verified) → truthful
> confirmation → **Scene Rail updated REALTIME (Lane B, no reload)**. Model even self-corrected an arg-name miss AND
> an OCC stale-version conflict (refetch→retry) — the schema/error-message contracts held. **5 live-caught fixes
> shipped en route (each unit-regression-tested):**
> 1. **Studio nav-kill** — the chat's generic C-NAV executor ran inside the Compose panel; an agent `ui_open_book`
>    on the CURRENT book navigated the SPA to `/books/{id}`, unmounting the WHOLE studio and orphaning the agent's
>    own resumed run (response lost). Fix: `UiNavInterceptorContext` seam in `useUiToolExecutor` +
>    `makeStudioNavInterceptor` (same-book `ui_open_chapter`→`focusManuscriptUnit`, same-book `ui_open_book`/
>    `ui_navigate`→already-here success; cross-book falls through) provided by ComposePanel.
> 2. **book→project bridge** — `composition_get_work` now also accepts `book_id` (resolve_by_book, 0→H13 deny,
>    >1→candidates); the model had dead-ended retrying the book_id AS a project_id (no tool bridged them).
> 3. **CTX-1 position pointer** — `studio_context` now carries `project_id` + `active_chapter_id` (FE: stable
>    `ManuscriptUnitMeta` context — no per-keystroke chat re-render; BE: `StudioContext` model + the system-message
>    note "this book's project is project_id=… (a book_id is NOT a project_id)").
> 4. **composition hot-domain** — the studio compose surface now seeds `composition_*` HOT (`_STUDIO_HOT_DOMAINS`,
>    fresh + resume paths); before, the family was find_tools-lazy and the local model spun in memory/glossary
>    searches concluding "no list_scenes tool exists".
> 5. **Lane-B envelope unwrap** — `chapterIdFromResult` read `chapter_id` top-level but the live stream delivers the
>    chat-service `{ok, result}` TOOL_CALL_RESULT envelope (inner result may be a JSON string) → Scene Rail never
>    reloaded while the DB was already updated (unit tests fed the payload unwrapped — the
>    cross-boundary-normalization bug class, again).
> Also: `manuscriptUnitDocument` TS narrow fix; json-editor empty-buffer-seed commit that was missed from
> `c8906f07a` landed as `a92f10217`. Residual (tracked, not studio-scoped): C-NAV navigation on the PLAIN /chat
> surface still unmounts that page mid-run (same orphaned-resume class — chat-service persists nothing for the
> continuation); intermediate multi-tool turns render "No response generated" chips (cosmetic); knowledge indicator
> flashes "Degraded" occasionally during heavy runs.

> **▶ #12 CYCLE-1b EDITOR COMPLETENESS (M-F…M-I) — SHIPPED + LIVE-SMOKED 2026-07-03** (plan
> [`2026-07-02-chapter-editor-completeness.md`](../plans/2026-07-02-chapter-editor-completeness.md); PO sign-off:
> sceneMarker NOW not later, ▲/▼ reorder, all 4 milestones). **M-F sceneMarker:** marker = `sceneId` ATTR on the
> heading node (`SceneAnchorExtension` GlobalAttributes — load-bearing: without it Tiptap's schema STRIPS markers
> on load→save); `jumpToScene` (rail title click / navigator / ⌘P via the bus scene slice) scrolls + sets the
> cursor; ⚓ backfill anchors headings↔scenes by unique normalized-title match in ONE transaction (explicit action
> → dirty → user ⌘S; diacritics preserved — VN tone marks are significant). LIVE: ⚓ 2/2 on Chương 1, markers
> persisted in the draft body (psql `sceneId` grep), jump scroll 0→856 with the cursor inside
> `h3[data-scene-id=<node id>]`. **`D-SCENEMARKER-EMIT` — CLEARED 2026-07-03 (cycle-1c, see block above):** emit
> at generation-persist time shipped once the RAID quiet window opened. **M-G rail CRUD:** ＋ create (uses the NEW `chapter_node_id` the scenes endpoint returns — works
> at 0 scenes), ✕ soft-archive with Undo (restore), ▲/▼ reorder (after_id + If-Match; BE renumbers story_order) —
> LIVE round-trip verified vs composition DB. **M-H word count:** real F2 status item (`\p{L}` NOT `\w` — JS \w is
> ASCII-only even under /u and shreds Vietnamese; CJK per-char); ManuscriptUnitProvider moved ABOVE the status bar
> (still above every chrome conditional → no remount on sidebar/bottom toggles); hoist derives textContent from the
> body when the server projection is empty ("1046 words" live). **M-I:** dirty-on-mount KILLED (setBody equality
> guard on the first update) — "Maximum update depth" went 8+→0 live; residual: ONE setState-in-render warning from
> mount-normalize (cosmetic; a real fix = microtask-defer inside the SHARED TiptapEditor — not worth it now);
> languagetool 500s on :5199 are a dev-proxy issue, not studio scope. Tests: FE +22 (SceneAnchor 5, SceneRail 15,
> WordCount 5), composition outline 19/19 + full 1459 unit green, image rebuilt.
> **⚠️ Parallel-run lesson (live hit):** Track-4 commit `ab0523df6` swept this track's STAGED F1/F3 files into its
> own commit (shared working tree) — protocol now: `git add … && git commit -- <explicit paths>` in ONE invocation.

> **▶ Track 4 SALIENCE (knowledge) — P0+P1+P2 SHIPPED + REVIEWED 2026-07-02.** Spec `85a0fb961`. **P0 substrate**
> (`20cf1e626` + review `e7e96fa13`): `entity_access_log` (tenancy PK user+project+entity), `EntityAccessRepo`
> (fire-and-forget, never raises), `BuiltContext.surfaced_entity_ids`, router records off-latency-path (strong task
> ref — GC footgun fixed), 19 tests. **P2 cross-encoder rerank** (`b514f6282`): step 7b in `select_l3_passages` via
> existing `RerankerClient` (BYOK `extraction_config["cross_encoder_rerank_model"]`), degrade→MMR on any bad shape,
> +8 tests. **P1 salience blend** (`a66f27bd8` + review `b53ed5de0`): `rank' = rank + w·norm(decayed_access)`,
> read-time Ebbinghaus (no cron), `salience_access_weight=0.0` default = byte-identical (no DB read), **pins ALWAYS
> lead** (review caught pin-vs-budget-trim drop), +12 tests. 483 context unit tests green.
> **Eval standup (in progress):** POC book = `019f1783-ebb4` (12ch VN, ~118K chars), knowledge project
> `019f1783-ecca`, embed bge-m3 `019eeb08-8bff` (dim 1024, benchmark PASS r@3=1.0), extraction LLM gemma QAT
> `019ebb72-27a2`. **Found+fixed a HIGH book-service bug class live:** publish guard + revision-text + getRevision +
> compare + canon-search all extracted ONLY the editor `_text` projection → standard-tiptap chapters false-rejected
> from publish AND silently skipped by extraction ("text unavailable") AND invisible to canon search. Fixed with
> `_text ∪ $.**.text` union (`12a702b2d`, `7b9cd4fda`; +4 DB-gated tests vs real PG18, BOOK_TEST_DATABASE_URL).
> Also: worker-ai image was STALE (cancel_check SDK drift — chat-scope job failed) → rebuilt worker-ai +
> knowledge-service. **Eval CLI** `python -m eval.run_salience_eval` seed/measure (`0170a414c`, +9 tests).
> **NEXT: extraction completes → seed (5 passes × 4 focus) → measure → P1/P2 flip decision by data → P3.**
>
> **▶ Track 4 EVAL EXECUTED + reviewed 2026-07-02 (`b1de69a13`, `ab0523df6`).** KG: 40 entities/125 events/181
> passages (re-publish re-armed passage ingest after the `_text` fix window). **P0 LIVE-PROVEN** (20 HTTP builds →
> access-log rows). **P1 verdict: KEEP w=0** — REGRESSION on explicit queries (MRR .531→.513; tier/FTS near-optimal
> when the query names the entity; seed boosts the whole co-surfaced cluster). Revisit trigger: ambiguous-query eval
> or P3 per-entity signals. **P2 LIVE-PROVEN** e2e (build → /internal/rerank 200 local bge-reranker → reorder logged;
> passage-hit .75→.80 n=12) — stays per-project opt-in. Spec §8b has the table. **Review fixes:** config write-path
> was unreachable (extra=forbid) → added; FE editor PUT-replace would silently CLEAR the rerank keys → preserved-on-
> omit/clear-on-explicit-empty (+2 tests). **`D-WORKER-SKIP-FALSE-GREEN` CLEARED (`b24143d2f`, user fix-now):**
> `extraction_jobs.items_skipped` column + `skipped_delta` threaded through `_advance_cursor(_and_emit_run)` (both
> skip sites, tx-fallback preserved) + `_complete_job` stamps error_message when skipped ≥ total ("no work
> performed") — status stays complete (failed would trip campaign breakers). +4 tests, worker-ai 299 green, DDL
> applied live, worker-ai rebuilt.

> **▶ STUDIO AGENT RAID — IN PROGRESS 2026-07-02 (`feat/studio-agent-raid`, autonomous run).** Big RAID: agentic
> chat to industry standard (context meter+compaction, plan-mode, steering, MCP resources/prompts, HITL modes,
> checkpoints, memory-for-canon, autonomy dial). **Wave P (PlanForge takeover) — DONE through M4:** P0 committed
> inherited M3 checkpoint (38 tests); **P1 review-impl** fixed patch no-spec 409→422 (+tests); **M4** shipped 8 MCP
> `plan_*` tools + chat `plan_forge` skill + D-PF-APPLY-HONESTY (`no_change` on unchanged refine) + review_checkpoint
> / handoff_autofix service methods (73 composition MCP + 9 chat skill + 50 plan_forge + provider-gate green).
> composition-service rebuilt. **M5 (Studio planner dock) DONE + browser-smoke-proven** (palette→Planner→paste→
> propose(rules)→run+artifacts→validate→S1-S8 report; a null `fidelity_score.toFixed()` crash was caught live
> and fixed + regression-tested). **Wave P COMPLETE (7 commits).** **NEXT: Wave A — context spine** (A1 script-aware
> tokenizer for VN/CJK → A2 budget + `contextBudget` event → A3 FE meter → A4 hybrid compaction micro→full→fail →
> A5 Anthropic overlay → A6 manual compact). Grounding facts in the RAID plan §1: `context_length` in chat-service
> `models.py:466`, provider_kind at `:462`, Anthropic passthrough via `streamRequest.Extra` + `anthropic_streamer.go:251`.
> Reconciliations: gateway forwards X-Project-Id (memory `gateway-drops-xprojectid-envelope` stale); saga breaker
> is probe-reconcile not XADD.
>
> **▶ Wave A (context spine) — CORE DONE + BROWSER-PROVEN 2026-07-02.** A1 script-aware tokenizer (CJK≈1 tok/char,
> VN denser, ASCII chars/4 — fixes edge #1; 8 tests, Chinese >3× the broken chars/4) → A2 `contextBudget` AG-UI event
> on RUN_FINISHED (used vs `context_length−max_tokens−safety`; NULL→"—") → A3 FE `ContextMeter` in the chat header
> (bands 70/85; 10 tests) → A4 provider-agnostic compaction (`compaction.py`: micro-evict tool-results keep-N+exclude
> web_search → optional summarize → hard-truncate; edge #2 summarize-fail→truncate, edge #4 overflow flag; 9 tests;
> wired GUARDED before the provider call, summarize=None). **LIVE browser proof:** the meter shows "46% · 18056/39488
> tokens" on a real gemma-26b turn; compaction correctly inert at 46%<75% (turn intact). **DEFERRED (tracked):**
> `D-RAID-A5-ANTHROPIC-OVERLAY` (Claude-only context-editing `clear_tool_uses`+memory tool via provider-registry Go
> plumbing — low ROI for the local-model POC that A4 already covers) · `D-RAID-A6-MANUAL-COMPACT` (manual Compact
> button + New-from-summary — enhancement over the working auto-compaction; needs a summarize endpoint). **NEXT: Wave C**
> (C1 steering store · C2 HITL modes+per-tool approval · C3 SKILL 3-tier · C4 @-mention · C5 MCP resources/prompts ·
> C6 turn checkpoints+hunk review), then Wave B (Plan mode — mostly delivered by Wave P PlanForge), then Wave D (autonomy dial).
>
> **▶ Wave C — C3 DONE 2026-07-02; comprehensive VERIFY green.** C3 SKILL 3-tier: L1 available-skills metadata block
> (`skill_metadata_block`, `SkillDef.description`) injected always (cheap discoverability) + the resolved skill's full
> L2 body; wired into both system-prompt paths (Anthropic parts + plain); 12 skill tests. **RAID-so-far VERIFY: BE 183
> (chat-service 110 + composition-service 73) + FE 385 (plan-forge+studio+chat) green; 2 live browser smokes (M5
> planner, A2/A3 meter) with auto-fix loops; provider-gate + tsc + i18n-parity clean.** ~17 commits on `feat/studio-agent-raid`.
> **REMAINING Wave C — classified for the resumer:** SAFE-ADDITIVE (do next): **C5** MCP resources/prompts (ai-gateway
> `src/mcp/handlers.ts`+`proxy-server.factory.ts`+`federation.service.ts` add List/Read handlers; server `@resource`/
> `@prompt` decorators; chat client `knowledge_client.py` add get_resource/read; X-Project-Id IS forwarded — no workaround).
> **C4** @-mention (FE `ContextPicker` inline). LOAD-BEARING (warrant a human POST-REVIEW — tenancy/schema/permission,
> the CLAUDE.md-flagged bug class): **C1** steering store (new `book_steering` table + owner+E0 tenancy + inclusion modes
> + `steering` bucket render), **C2** HITL modes + per-server-tool approval (tool-surface filter — can regress tool
> availability), **C6** turn checkpoints (book-service revision-restore endpoint + hunk review). **Wave D autonomy dial**
> (D2 start/end-gate FSM + guardrails) is the biggest load-bearing piece — reuse campaign-saga + PlanForge + Quality Report.

> **▶ CHECKPOINT — Wave A (context spine) SOLIDIFIED 2026-07-02 (user: "make previous implement solid before we
> continue").** Ran `/review-impl` over the whole context spine (token_budget, compaction, wiring, ContextMeter).
> **Caught + fixed a stale test first:** the A2 `contextBudget` CUSTOM frame was never added to the AG-UI happy-path
> exact-sequence assertion → the FULL chat-service suite was RED (prior "green" was a subset). Fixed (`128941136`),
> full suite now 525. **HIGH bug found + fixed (`42d003f42`):** compaction on the **resume path** (agent→GUI 2nd pass,
> `resume_stream_response` passes the live `working` array w/ assistant `tool_calls` + `role:tool` results) could
> orphan a tool-call/result pair on hard-truncate / summarize tail-slice → provider **400**. Unit tests missed it
> (plain user/assistant msgs). Fix: truncate on whole tool-exchange **atoms** (`_atoms`/`_recent_tail`) — keep/drop
> whole exchanges, never split. +3 TestToolPairSafety. **Summarizer WIRED (`356527c26`, per user decision "wire now"):**
> `compact_messages` now async; tier-2 compresses the droppable MIDDLE via the session's own model
> (`_summarize_for_compaction`, provider-agnostic gateway); failure → hard-truncate (edge #2). Cross-turn history is
> flattened `{role,content}` (no pairs there — safe); memory [[compaction-resume-path-carries-tool-pairs]].
> **LIVE SMOKE PASS (per user decision "do the live smoke"):** in-container against real gemma QAT (200K) — forced
> compaction (10034→~2880 tok), asserted **no orphan**, sent the compacted tool-containing array back to gemma →
> **provider accepted on BOTH paths** (run1 summarize-success w/ real synopsis; run2 summarize-fail→truncate fallback,
> both orphan-free + accepted). chat-service **525 passed**; compaction 13 tests. **Wave A is now solid.**
> **LOW items CLEARED (`2b25bd923`):** (1) the tool loop now re-compacts `working` at the top of EVERY pass
> (atom-grouped, guarded, summarizer=session model; `effective_limit` threaded into `_stream_with_tools`) so a long
> multi-tool turn can't overflow mid-turn — +2 wiring tests (fires per pass with limit / skips when None); (2)
> `estimate_messages_tokens` now counts assistant `tool_calls` (name + arguments JSON) — +1 test. In-loop compaction
> reuses the already-live-proven `compact_messages` (provider-accepts the compacted tool array) — covered transitively,
> not separately live-smoked. **chat-service 528 passed; provider-gate green. Wave A fully closed.**

> **▶ Writing Studio foundation SHIPPED + PROVEN + PR'd 2026-07-02 (`feat/writing-studio`, 130 commits → `main`).**
> Frame + palette (⌘P/⌘⇧P) + share-data (StudioHost/bus/registry #08) + navigator (#02 search/totals) + Compose
> panel (chat AS-IS via `actionBar`) + Tier-4 editor hoist (#04) + navigator→editor + agent Lanes A/B/C. **Live
> Playwright browser smoke** (real stack, gemma-26b, POC book) verified every axis AND caught a real bug the
> unit/integration/raw-stream tests all missed: `ui_open_studio_panel` schema↔resolver drift (model sent `panel`
> not `panel_id`, resolver silent no-op, model hallucinated success — `f1f9e9966`). **Standardized the fix into a
> machine-checked FRONTEND-TOOL CONTRACT (`0df466d15`)**: `contracts/frontend-tools.contract.json` +
> `test_frontend_tools_contract.py` (BE snapshot + closed-set-must-be-enum) + `frontendToolContract.test.ts`
> (FE Proxy-access proves each resolver reads every required arg + no-silent-no-op) + `panelCatalogContract.test.ts`
> (enum ⊆ dock catalog). CLAUDE.md § "Frontend-Tool Contract (LOCKED)". FE 232 chat + full studio green, BE 50 green.
> **NEXT = the agentic-chat deep-dive** — research + standard in [`07R_chat_agent_industry_research.md`](../specs/2026-07-01-writing-studio/07R_chat_agent_industry_research.md)
> (industry map: Claude Code/Cursor/Antigravity/Kiro/Copilot/Zed/Aider/Continue + cross-cutting; LoreWeave gap map;
> 3-tier recommended standard). **Priority 🥇1–3:** context meter + tiered warnings + typed buckets; compaction
> (auto microcompact + manual button; Anthropic context-editing/memory OR provider-agnostic — OPEN Q); web-search
> surfaced. Open questions (07R Part 7): paradigm depth, compaction ownership (BYOK-Claude vs local-model portable),
> bible-as-steering vs charter, sub-agent scope. **Decide the standard doc first, then build.**

> **▶ PlanForge BLUEPRINT SHIPPED 2026-07-01** — POC frozen at `scripts/plan-forge-poc/` (fidelity 1.0, elaboration 1.0, chat HIL I1–I4 100%). **SSOT implement handoff:** [`09_PLANFORGE_BLUEPRINT.md`](../specs/2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md) (acceptable bar tier A/B/C, MCP sketch, M1–M5, deferred). Eval chain: [`04_PO_REVIEW.md`](../specs/2026-07-01-plan-forge/04_PO_REVIEW.md) GO → [`06`](../specs/2026-07-01-plan-forge/06_FIDELITY_POC_EVAL.md)–[`08`](../specs/2026-07-01-plan-forge/08_CHAT_HIL_POC_EVAL.md). **NEXT (PlanForge implement session — not this Writing Studio track):** M1 port engine → `composition-service/app/engine/plan_forge/` per blueprint §6 + [`docs/plans/2026-07-01-plan-forge-promote.md`](../plans/2026-07-01-plan-forge-promote.md). POC CLI kept for regression until M2 green.
>
> **▶ PlanForge Deferred (implement session):** `D-PF-APPLY-HONESTY` (no false success when fidelity_delta=0), `D-PF-NORMALIZE` (placeholder name, VN mechanics), `D-PF-PARTIAL-REFINE` (focus_paths slice), `D-PF-CONVENIENCE-EVAL` (TTAS + Opus vs local), `D-PF-MULTI-DOC` (3 doc profiles). See blueprint §7.

> **▶ #02 Manuscript Navigator — BUILT + solid 2026-07-01 (`feat/writing-studio`, full-stack).** An adaptive
> **arc→chapter→scene** tree that scales to 10k+ chapters (VS Code Explorer recipe: virtualized rows + cursor
> paging + lazy expand). **Chapters spine = book-service keyset cursor** endpoint `GET /chapters/page?cursor&limit`
> (`(sort_order, id)` keyset, UUIDv7 tiebreak, `idx_chapters_keyset`, opaque base64 cursor, `402a92e1a`).
> **Arc/scene overlay = composition lazy-children** `GET /works/{id}/outline/children?parent_id&cursor` (keyset on
> `rank COLLATE "C", id`, `de893dae7`). **FE** `@tanstack/react-virtual` over a flattened row array; two data
> sources behind `useManuscriptTree` (no Work → flat chapters; Work → outline tree); pure `tree.ts` flatten;
> lazy expand + infinite paging + client filter; wired into `StudioSideBar` (`b21ed648e`). **`/review-impl`
> (cold-start) found + fixed:** H1 composition keyset index missing collation → full Sort (added
> `idx_outline_node_children_keyset (parent_id, rank COLLATE "C", id)`); M1 stale-response race on book switch
> (generation guard); L2 collation-qualified the `rank =` equality; C1 keyset default limit 100. M2 adaptive
> degenerate-collapse tracked as spec Debt #4. **Verified:** Go + Python unit tests, FE 19 manuscript unit
> tests (incl. M1 stale-guard, beat-filter, lazy-expand), tsc+eslint+i18n clean, **live E2E through the gateway**
> (rebuilt book+composition) — renders chapters, **keyset page-boundary no gap/dup**, filter. **Debt (spec 02):**
> #1 navigator→dock link (needs #03), #2 server chapter-search (shared `useManuscriptJump`/#06a), #3
> partial-outline merge, #4 adaptive collapse. Outline-path live E2E deferred (needs a parent-linked outline seed helper).

> **▶ Writing Studio (v2) — FRAME SKELETON built 2026-07-01 (`feat/writing-studio`, FE-only).** Incremental
> **build-while-plan** track (inverts plan-then-build): master spec + one file per component, written
> just-in-time — `docs/specs/2026-07-01-writing-studio/` (`00_OVERVIEW.md` + `01_skeleton.md`); frame mockup
> `design-drafts/screens/studio/screen-writing-studio-frame.html`. Shipped the full **fixed frame** as
> `features/studio/` (MVC): `StudioTopBar` (back·title·⌘P palette placeholder·settings), `StudioActivityBar`
> (icon rail: Manuscript/Bible/Search/Quality — switches the navigator; re-click active = collapse),
> `StudioSideBar` (active navigator, **content STUBBED**), `StudioDock` (dockview + Welcome + per-book layout
> persistence), `StudioBottomPanel` (toggle; Jobs/Generation/Issues stubs), `StudioStatusBar` (lang·⌘P·bottom
> toggle). Hooks: `useStudioChrome` (activeView/sidebar/bottom, per-book `lw_studio_chrome_<bookId>`) +
> `useStudioLayout` (dockview onReady+persist). **Verified:** tsc+eslint clean, studio i18n ×4 parity-clean,
> **browser-smoke** — all regions render, activity-switch + sidebar-collapse + bottom-toggle work, **dock never
> remounts** through chrome changes, chrome+layout persist & restore on reload, 0 console errors.
> **Solid (this track's stricter no-defer rule — unit+E2E per component):** 30 unit tests + 7 Playwright E2E
> (frame regions · activity-switch · collapse · bottom-toggle · persistence · **per-book isolation** ·
> **dock-no-remount**) all green; **`/review-impl`** (cold-start) found 2 HIGH — per-book state was frozen to the
> first `bookId` (in-session book switch corrupts the other book's storage) → fixed via a **keyed `StudioFrame`**
> remount — plus MED/LOW (persist-after-seed to dodge the upgrade trap; dropped a misleading disposable; stable
> `studio-dock` testid; removed dead `persist`), all fixed & re-verified. Debt tracked **LIFO** in the spec
> (nav→dock link · two-left-rails · top-bar Generate/Save). **NEXT (#02):**
> Manuscript navigator — real chapters→scenes tree in the Side Bar that opens/focuses a unit in the dock (the
> navigator→dock "wiring"); then #03 Compose panel (first stateful dock panel → wires the D4 state-hoist rule).
> See memory `[[editor-workmode-and-compose-must-keep-editor-mounted]]`.

> **▶ Writing Studio (v2) — BLANK SHELL shipped 2026-07-01 (branch `feat/writing-studio`, FE-only).** A NEW,
> from-scratch surface — does NOT touch `ChapterEditorPage`. **Build-vs-buy decided:** our in-house dock layer
> (`WorkspaceLayoutProvider`/`DockRail`/`FloatingWindow`/`PopoutBridge`) is a single linear tab-rail — it CANNOT
> do VS Code-style multi-region docking (splits, tab groups, nested regions, drag-split-merge). Adopted
> **`dockview-react` v7.0.2** (zero-dep, MIT, React-18, real tab-groups + split grids + floating groups + pop-out
> windows + `toJSON/fromJSON`). **Shipped:** `pages/WritingStudioPage.tsx` (empty dockview shell, `themeAbyss`,
> single Welcome panel, **per-book layout persistence** via `localStorage` `lw_studio_layout_<bookId>` on
> `onDidLayoutChange`); route `/books/:bookId/studio` under `EditorLayout`; **book-level** "Studio" CTA in
> `BookDetailPage` header (opens directly, no chapter needed); new i18n `studio` ns × en/vi/ja/zh-TW +
> `books.detail.open_studio`. **Verified:** tsc + eslint clean, production `vite build` OK (dockview bundles),
> browser-smoke — studio renders, welcome panel, layout persists (1 panel saved), 0 console errors, CTA links
> correctly. **Architecture rule carried forward:** live/in-flight state (co-writer streams, editor docs) must
> live ABOVE dockview; panels are thin views over hoisted state so closing/moving a panel never drops work —
> wire when the first stateful panel lands. **Next:** user directs which panel to add first (compose, planner,
> cast, quality…), one at a time. See memory `[[editor-workmode-and-compose-must-keep-editor-mounted]]`.

> **▶ GUI Workmode overhaul (M0 + M1 + Read) — SHIPPED 2026-07-01 (FE-only).** The chapter editor's
> "three overlapping hidden mode systems" collapse into ONE dropdown: **Write · Translate · Read · Compose**
> (`hooks/useWorkmode.ts` persisted `lw_editor_workmode`; `components/editor/WorkmodeSwitcher.tsx`). Folded
> away the scattered Pen/Sparkles toggle (now a Write-only sub-control), the Co-write bridge, the one-shot
> `handleTranslate` button (deleted), the view-translations Eye button, and the compose right-panel tab.
> **Center swaps by mode:** Write/Compose keep the manuscript editor mounted (Compose shows the studio in the
> right companion panel — the editor MUST stay mounted or the studio's insert/applyPolish ref no-ops:
> regression-tested); Translate embeds the full **`ChapterTranslationsPanel`** (extracted from
> `ChapterTranslationsPage`, which is now a thin wrapper seeding `?lang=`/`?vid=`); **Read** opens the
> existing full `ReaderPage` route (guarded) — reader already reads the draft with TTS/theme/TOC/lang-switch,
> so it's reused, not rebuilt. i18n `editor.workmode.*` × en/vi/ja/zh-TW. E2E page-object `openComposeTab`
> updated to drive the dropdown. **Tests:** useWorkmode 4 + WorkmodeSwitcher 4 + ChapterEditorPage 5 (incl.
> the Compose-keeps-editor-mounted regression guard); translation/composition/editor/pages/hooks **853 green**,
> tsc + eslint clean. **Not done:** live browser-smoke (mocked heavy components ≠ visual proof — do next);
> mobile still uses its own group shell (workmode switch is desktop-only, conscious).

> **▶ Q3 Book-level promise coverage — SHIPPED 2026-07-01.** Reframed from "auto arc-conformance":
> verified `compute_arc_report` hard-requires an `arc_template_id`, and arc templates come ONLY from the
> reference-import (`motif_deconstruct`) / authored path — the mainstream premise→pipeline flow creates
> none (no `work→arc_template` link), so auto arc-conformance is a **no-op for mainstream works** (already
> has a manual Tier-W path). The GUI-free, mainstream-valuable Q3 is the **book-level escalation of the
> promise audit** (v2 API): `quality_report.build_promise_coverage` = `extract_tracked_promises(premise,
> plan_text)` (STABLE set from the SPEC, not the prose) → `score_promise_coverage(full_book)` →
> **paid/progressing/abandoned/absent** + rates. Worker op `promise_coverage` (+ SUPPORTED_OPERATIONS +
> dispatch) + `POST /v1/composition/works/{id}/promise-coverage` (renders `plan_text` from the outline tree
> + assembles every ACTIVE chapter's prose — the ENDPOINT resolves, the worker runs). FE `promiseCoverage`
> api + `useBookPromiseCoverage` + `BookPromiseCoverageSection` in the **project-scoped `QualityPanel`**
> (threaded `modelRef`; NOT the per-chapter Polish gate). Read-only. Also fixed a duplicate `composition-quality`
> testid (QualityReportSection → `composition-quality-report`). **Live smoke** (Gemma-4-26b, vi plan+book):
> 4 tracked promises from the outline; 3 paid + **1 ABSENT** = the outline-promised "missing brother" thread
> the book never delivers — exactly the "does the book pay off the outline?" signal. `err:None`. Tests:
> quality_report 9 + worker_jobs (dispatch+serialize) + FE BookPromiseCoverageSection 5; FE 735 green.
> **Deferred:** `D-QUALITY-COVERAGE-CHUNK` (very long books overflow one score call — window it; gate #4).
> **★ Ceiling note (user):** the rest of the constellation (arc templates, motif library) each need a whole
> **CRUD GUI** — big features to plan separately, not just "wiring". See memory `constellation-wiring-ceiling-crud-guis`.

> **▶ Quality Report in the Polish gate (Q1+Q2) — SHIPPED 2026-07-01.** New track: make the **planner

> **▶ Quality Report in the Polish gate (Q1+Q2) — SHIPPED 2026-07-01.** New track: make the **planner
> exploit its own judges** (audit found the auto-loop runs critic/canon/narrative-thread/motif-conformance
> as advisory-but-BURIED, and `promise_audit` never runs at all). Q1+Q2 surface them as a **read-only
> Quality Report** in the M6 Polish gate: `engine/quality_report.py` runs the 4-dim **critic** +
> **promise_audit** (introduced/resolved/**dropped**) concurrently, degrade-safe; worker op `quality_report`
> (+ SUPPORTED_OPERATIONS + dispatch) + `POST /v1/composition/works/{id}/quality-report` (mirrors self-heal);
> FE `qualityReport` api + `useQualityReport` + `QualityReportSection` mounted in `PolishPanel` (diagnostic,
> NO accept/apply — do-no-harm). **Design:** promises are phrases not spans ⇒ read-only, not an EditProposal;
> Q2 re-runs critic FRESH (stale per-scene `_critic` is wrong after edits) — documented. **Live smoke**
> (composition→ai-gateway→provider-registry→LM Studio, Gemma-4-26b, vi CH1-style): critic scored 4 dims +
> caught the planted pronoun violation; promise audit caught the planted Chekhov's-gun as a **dropped promise
> (rate 1.0)**; both `err:None`. **Also fixed 3 PRE-EXISTING branch reds** (not mine, proven by stash):
> `test_motif_repo_signatures_frozen` (create/patch grew additive kwargs vs its exact-`==` — aligned to the
> file's own `[:N]`+`kw in` convention) + 2 `test_canon_reflect` (SimpleNamespace profile fake missing newer
> `BookProfile` fields → use real `BookProfile`). Plan: `docs/plans/2026-07-01-quality-report-polish-gate.md`.
> Tests: quality_report 4 + worker_jobs (dispatch+serialize) + FE QualityReportSection 5; full BE suite +
> FE 747 green. **Deferred:** `D-QUALITY-MOTIF-ROLLUP` (motif beat-not-realized rollup, gate #2),
> `D-QUALITY-ARC-LEVEL` (arc/book-level promise coverage v2, gate #1/#2).

> **▶ MERGE 2026-06-30: `origin/main` (Temporal-Knowledge / KAL) merged in (55 commits).** The
> knowledge-gateway (**KAL**) unifies glossary/KG reads under INV-KAL: composition's cast-roster read
> moved from `glossary.list_entities` → **`kal.roster()`** (drains the cursor — fixes the ~100-cast
> truncation). Conflict was ONLY `SESSION_HANDOFF.md`; router `plan.py` + `glossary_client.py`
> auto-merged (our `thread_state`/`exit_state`/`seed_entities` survived alongside KAL). Our `seed_entities`
> WRITE (glossary `extract-entities`) passes **both** INV-KAL gates (knowledge-access + http-surface).
> **Verified:** composition unit suite **1209 passed**; `kal.roster()` returns the 10 seeded cast;
> **e2e** on the rebuilt KAL stack — seed → KAL roster → decompose → **34/34 scenes grounded** with
> `present_entity_ids`. Our code is fully on the new standard (roster via KAL; `cast_plan`/`self_heal`
> don't touch glossary directly).


> **What this track is:** the editor/compose UX overhaul **pivoted (PO)** to fixing **output QUALITY first** — POC chapters read as concatenated scenes. Two design docs:
> - **[`docs/specs/2026-06-30-editor-compose-overhaul/`](../specs/2026-06-30-editor-compose-overhaul/)** — the GUI track (validate-first, milestones M0–M5 are a backlog menu, NOT a build order).
> - **[`docs/specs/2026-06-30-chapter-synthesis-self-healing.md`](../specs/2026-06-30-chapter-synthesis-self-healing.md)** — the synthesis track: **Phase 0** (planning connectivity, DO FIRST) → **Phase 2** (multi-pass self-heal). Ordering is locked: garbage-in (disconnected plan) can't be polished out.
>
> **▶ Shipped this session (validated, committed):**
> - **Phase 0 slice 1 (intra-chapter connectivity)** — enriched the decompose prompt (goal·conflict·outcome + causality + ending-guided). Fixed the 3 worst reviewer defects (causeless pursuit, grimoire-from-nowhere, disconnected scenes) at the synopsis level, prompt-only.
> - **Phase 0 slice 2 (cross-chapter threading)** — `engine/plan.py`: typed `ChapterExitState` (Character/World/Plot + `advances`) emitted as a same-call delta, threaded chapter→chapter (`thread_state` flag, **default OFF ⇒ today's concurrent fan-out byte-identical**; sequential when ON: prev-chapter exit = fine-grained backbone + cumulative advances = global anti-repeat). Wired through worker + router (additive optional). **Live worker smoke** (Gemma, `thread_state=True`, 12ch/36sc): chapters now open *"Tiếp nối từ…"* the prior exit-state, **arc repetition gone**. `/review-impl`: **0 HIGH**, 4 findings fixed (inline/worker response parity for `exit_state`; both-flags no-op warning; degrade-path test; advances-cap documented). **Tests:** composition unit suite **1180** + slice tests (test_plan 19, router 16, worker_jobs 18 — fixed 5 pre-existing `cancel_check` fake drift) green.
>
> **▶ Self-heal POC — the whole approach was de-risked this session (see the synthesis spec for the data):**
> - **stitch baseline** — the existing 1-pass `stitch` smooths transitions but is NOT a dedup/repair pass, and it **inflates length +68%** (a prompt cleanup did NOT fix it: Gemma rewrites-and-expands by nature; the token cap isn't a clean lever). ⇒ whole-chapter rewrite is the wrong primitive.
> - **L1 dropped** — the "scene-titles mid-chapter" complaint was a POC HARNESS artifact (`to_tiptap_doc` heading-per-scene), not a pipeline defect.
> - **Satellite editing is the answer (PO insight)** — surgical edit of a SMALL isolated span. Mechanism (2) structural isolation works on a small model: `selection-edit` on a 446-char span → ×1.01 length, motif 2→0, meaning preserved (vs whole-chapter ×1.68). Mechanism (1) trust-the-model fails on small models (the stitch result).
> - **The detector must be an LLM JUDGE, not code** (PO) — POC: Gemma returned **7 real findings** (2 logic holes incl. the fall-physics one, emotion-loop, motif, flat villain), each with a `fix` guide, **7/7 locatable (3 exact + 4 fuzzy)** ⇒ the locate step uses **fuzzy/shingle match, not exact**.
> - ⇒ **Full pipeline proven end-to-end:** `LLM JUDGE → fuzzy-locate (code) → satellite-edit (selection-edit) → splice → re-judge loop`. (POC scripts: `poc/judge_poc.py`, harness phases `satellite`/`stitch`.)
>
> **▶ Orchestrator BUILT + live-validated** — `engine/self_heal.py` (`run_self_heal`): judge→fuzzy-`locate_span`→satellite-edit→splice→re-judge; advisory skips (not-located/overlap/runaway-expansion). 12 unit tests. Live on ch1: 6 findings, **6/6 located, 4 edits, length ×1.014** (vs stitch ×1.68), surgical on-target edits. Fixed a false-zero re-judge bug (degraded re-judge now reports None). NOT yet wired to an endpoint (in-container script POC).
>
> **▶ PIVOT (PO) — re-architect PLANNING before drafting.** Reviewing the committed 12-ch plan surfaced many holes at once (no motif binding, empty cast / scene-presence, anonymous new characters, ch1 telescoped). Root cause = `decompose` is **one-shot** (same anti-pattern as whole-chapter stitch). Fix = a multi-step planning pipeline (decompose-and-refine, ONE arc). Spec: [`docs/specs/2026-06-30-planning-pipeline-architecture.md`](../specs/2026-06-30-planning-pipeline-architecture.md) · Build plan + **capability audit** (planning uses ~2/30 engines — the judge constellation promise_audit/succession_entailment/arc_conformance is idle): [`docs/plans/2026-06-30-planning-pipeline.md`](../plans/2026-06-30-planning-pipeline.md). Stages: 0 cast/world · 1 motif-select · 2 arc+tension · 3 char-arc/intro · 4 grounded decompose · 5 plan self-heal · 6 orchestration+checkpoints. Reuse-heavy (motif retriever, templates, arc_apply, self_heal pattern, the idle judges).
>
> **▶ PLANNING PIPELINE COMPLETE (Stages 0–6, all live-validated)** — replaced the one-shot decompose with a multi-step planner, each stage committed + unit-tested + live-POC'd on the Lâm Uyển premise:
> - **0 cast** (`cast_plan.py` propose_cast + `glossary_client.seed_entities`) — 10 cast (6 named + 4 new), seeded → roster → present_entity_ids.
> - **1 motifs** (`motif_plan.py` select_arc_motifs) — 4 arc motifs with roles (spine/recurring/foil/climax).
> - **2 tension** (`arc_plan.py` shape_tension_curve, deterministic) — fixes ch1=100; 100 only at climax.
> - **3 char-arcs** (`character_plan.py` plan_character_arcs) — arcs + introduction schedule (new chars @ fitting beats).
> - **4 grounded decompose** (`grounded_plan.py` + grounding block in `plan.py`) — feeds cast/motifs/tension/intros into the threaded L2.
> - **5 plan self-heal** (`plan_heal.py`) — plan-judge → satellite-edit a scene synopsis by (chapter,scene).
> - **6 orchestration** (`planning_pipeline.py` run_planning_pipeline) — chains 0→1→L1(once)→3→4→5.
> - **Capstone live POC** (`poc/io/full_pipeline.txt`): cast=10 · motifs=4 · arcs=10 · 12ch/30sc/30-with-present · **plan-heal 7/7 findings edited** (4× cross-chapter repetition, a character-before-introduction, a tension-vs-beat, a dangling setup — all real, all fixed).
>
> **▶ Production hardening DONE + the drive STARTED:**
> - **Task A (wired)** — `DecomposeRequest.pipeline=true` → the `/outline/decompose` endpoint runs `run_planning_pipeline` via the worker (`plan_pipeline` op + dispatch + allowlist). **Live e2e:** endpoint→202→worker→cast=9/motifs=4/12ch·35sc/plan-heal 8-8→committed to the outline.
> - **Task B (D-PLAN-CAST-ATTRS, resolved)** — `cast_attributes` maps role/traits/archetype/relationships/summary → the character kind's attr codes; `seed_entities` sends `attributes`+`attribute_actions`. Live-verified: glossary EAV persists role/personality/relationships/description. Drafting grounding now has DEPTH.
> - **Task C (the drive, in progress)** — the full grounded+healed 12-ch plan was generated + committed through the production endpoint; CH1 drafted (grounded) + chapter self-healed (`engine/self_heal.py`) as the prose sample. **NEXT:** draft + self-heal the remaining chapters (drive identically) for the full-story PO evaluation; optional: wire `self_heal` to its own endpoint (currently a script).
> - review-impl on the pipeline: 0 HIGH, 2 MED fixed (motif unrecognised-role drop; L1-once on degrade).
>
> **▶ Cheap quality stack — judge upgrade (SHIPPED 2026-07-01, `engine/self_heal.py`):** the bare judge
> was blind (0 findings on CH1 while real xưng-hô/canon errors stood; confabulated when prompted broad).
> Root cause = no canon grounding, not model size. POC'd 5 layers on the $0 local Gemma (data:
> `poc/io/poc_stack_out.json`), then implemented the validated subset — all **default-OFF ⇒ legacy
> byte-identical**: `canon` (grounds judge **and** satellite editor in a story bible + 2 false-positive
> guards), `vote_k`/`min_votes` (grounded judge ×K, must-quote folded in), `verify` (skeptical
> refute-or-confirm, fail-open), `prefilter` (dup-word + full-recall pronoun findings), `_snap_to_sentence`
> (edit whole sentences ⇒ no splice artifact). **Lesson:** voting alone does NOT kill *systematic*
> confab — only grounding suppresses it + verify refutes the leak. **CH1 re-healed:** 7 defects → near-zero,
> **x0.997**, incl. the canon contradiction (`từng dốc lòng che chở`→`luôn khinh miệt`) fixed by the grounded
> editor; remaining = 1 cosmetic + 1 borderline repetition left for the human/stronger gate. **Tests:**
> self_heal **21** (12 legacy + 9 new) green; full composition unit suite green. Result file:
> `poc/io/ch01_healed_cheapstack.txt`. Spec §"Cheap quality stack".
>   - **Full-book drive (CH1–12, book-level canon of all 9 cast) — `story-export-v2/` + `poc/io/heal_v2_summary.json`:**
>     **modern pronouns `ông/bà/ông ta/bà ta` = 0 real residuals book-wide** (deterministic prefilter is the
>     reliable workhorse); **no inflation anywhere** (x0.998–1.005). Two honest findings: (1) **verify is
>     stochastic + fail-toward-refute → occasionally drops a real finding** (CH01 `mẫu thân ngươi` regressed
>     vs the dedicated run; refuted=5/5 on CH03) — a precision/recall knob to tune (lower aggression, or vote
>     the verify), the human gate still matters most for the *semantic* findings. (2) **bug FIXED this commit:**
>     the dup-word collapser would flatten VALID Vietnamese reduplication (`chằm chằm`, `rắc rắc`) — now gated
>     OFF for `_REDUP_LANGS` (vi/zh/ja/ko/th/id/ms); only NFD-diacritic luck spared the v2 corpus, so the
>     exported v2 prose is unaffected.
>   - **(A) verify-recall + (B) canon-from-pipeline — SHIPPED 2026-07-01:**
>     **(A)** `run_self_heal(verify_k=…)` VOTES the verify (`_verify_vote`, majority-refute, tie→keep) so a
>     stochastic single refute can't drop a real finding. **(B)** new `engine/heal_canon.py`
>     (`render_canon` / `convention_for` / `canon_from_proposed`) builds the heal bible from the SAME
>     designed cast drafting grounds on; `PipelineResult.canon` now carries it (rendered in
>     `run_planning_pipeline`). **Live-validated on CH1** ($0 local, canon auto-rendered 2701 chars,
>     `verify_k=3`): the CH01 `mẫu thân ngươi` false-refute is **GONE** (residual=False; refuted 4→1), and
>     the rendered canon enabled a new canon catch (Hắc Sát Lão Nhân's role). Tests: self_heal 24 +
>     heal_canon 5.
>   - **⚠ CORRECTION (full-book re-drive, 2026-07-01) — the verify_k=3 "fix" was a lucky dedicated-run
>     sample.** Re-driving CH1–12 (`heal_all_v3.py` → `story-export-v3/` + `poc/io/heal_v3_summary.json`):
>     **pronouns ông/bà = 0 book-wide** (deterministic prefilter — rock-solid), **no inflation** (x0.998–1.007),
>     BUT **CH01 `mẫu thân ngươi` STILL residual** (present in both v2 and v3). Two real findings: (1) the
>     verify-vote was **mis-tuned** — majority-refute on a "default-REFUTED" prompt COMPOUNDS the refute-lean
>     (over-refuted: CH11 4/4, CH12 7/7). **Fixed:** `_verify_vote` now drops only on a **UNANIMOUS** refute
>     (keep if any vote confirms) — recall-biased, the human gate culls the rest. (2) **The verify model has a
>     genuine BLIND SPOT on `mẫu thân ngươi`** — it refutes 3/3 even grounded + recall-biased (0 confirms), so
>     NO vote threshold rescues it. **Conclusion (validates the M6 design):** the cheap stack is reliable on
>     CLOSED-CLASS (pronouns/dup, deterministic); semantic blind-spots are real + bounded → that residue is
>     exactly what the **human gate (M6 Polish) + stronger-model escalation** (deferred, story C7 #4) exist for.
>     Track **D-VERIFY-BLINDSPOT-ESCALATE**: wire the stronger-model gate for verify-refuted-but-real findings.
>   - **★ REDESIGN — DIRECT high-recall propose (PO diagnosis, 2026-07-01): the JUDGE pipeline was the bug,
>     not self-heal.** PO proved a BARE prompt on the same Gemma finds 7 splice-ready `{original,replacement,
>     explanation}` edits where our `judge→vote→verify→satellite` chain kept ~4 (verify default-REFUTED muted
>     real edits → v2≈v3). "The model detects + proposes correctly; only the judge is dumb." **Fix shipped:**
>     `propose_self_heal` now uses **`propose_edits_direct`** — ONE high-recall judge call that emits the
>     replacement inline (`build_direct_judge_messages`/`parse_direct_findings`), must-quote locate + dup-word
>     merge, **NO vote/verify** (the human gate IS the filter). Canon is CONTEXT, not a suppression guardrail.
>     **Live CH1:** 5 splice-ready edits incl. `mẫu thân ngươi`→`của ta` AND the canon contradiction
>     `dốc lòng che chở`→`khinh miệt` — the two cases the old pipeline never fixed — in 1 call (vs vote×5+verify×3).
>     Autonomous `run_self_heal` keeps the conservative `_compute_edits`. Tests: self_heal+worker 49 passed.
>   - **★ "Make the judge smart" — (1) surface rules + (2) comparative re-ranker (2026-07-01).** Smart-judge
>     POC pinned the root cause: the verifier wasn't dumb, it was **UNDERFED** — the rule was BURIED in an
>     800–2700-char bible. Fed the SAME rule concisely + with the example, EVEN the old skeptical judge
>     confirms `mẫu thân ngươi` 3/3 AND refutes the `lão` confab 3/3 (`poc/smart_judge_poc.py`). Two fixes:
>     **(1)** `heal_canon` — terser `render_canon` (description + relationship only, personality dropped) +
>     a NEGATIVE-example line in the convention (`hắn/y/lão/nàng/thị are VALID`) so the rule stands out + confabs
>     are pre-empted. **(2)** `_rerank_edit` — a COMPARATIVE re-ranker ("is the replacement better?", CoT,
>     default-APPLY, surfaced rules) that sets each semantic proposal's `EditProposal.recommended` (UI pre-check)
>     — it **RANKS, never vetoes** (every proposal still shown; recall preserved). `propose_edits_direct(rerank=)`,
>     worker op defaults rerank ON; FE pre-checks `recommended` (+ `rerank_reason`). Tests: self_heal+heal_canon+worker
>     57 + FE 142 vitest, tsc clean. **Live e2e CONFIRMED** (after a `docker compose up` recovered a cascading
>     Postgres→provider-registry/ai-gateway/composition drift): on v3-healed CH1 the direct+rerank returned 4
>     proposals — 3 PRE-CHECKED (`mẫu thân ngươi`→`ta` "violates third-person self-reference"; `che chở`→
>     `khinh miệt` "contradicts the canon Tô Yến never protected her"; dup-`từng`) + 1 UN-checked (a weak edit
>     "emotional weight is lost") — i.e. it RANKS, never vetoes, and each carries a cited reason. The exact case
>     the old verify pipeline refused 3/3 is now pre-checked with the rule cited.
>   - **Re-ranker made OPT-IN (default OFF) + 12-ch compare + no-op filter (2026-07-01).** Cost concern: rerank =
>     one extra LLM call PER semantic edit. **(A)** FE toggle "auto-tick (AI, costs more)", default OFF; worker/
>     endpoint default `rerank=False`; hook holds the toggle. **(B)** 12-ch compare (`poc/compare_rerank.py` +
>     `poc/io/compare_rerank_summary.json`): 55 splice-ready proposals, re-ranker approved 41 / declined 14 — and
>     **~all 14 declines are NO-OPs** (`replacement == original`; the direct auditor emits ~25% of these). The 41
>     approvals are real (pronouns, `mẫu thân ngươi`, canon: CH09 Lâm Tử Hàn/ma công, CH05 `Uyển nhi`-tone,
>     redundancy trims, CH04 bloat-delete x0.827). **(C) Cheap win found → shipped:** `propose_edits_direct` now
>     drops no-op edits (`after==located span`) in CODE (free) — so the human/re-ranker never sees the ~25% no-ops;
>     even without the paid re-ranker the human gets ~41 clean proposals not 55. Tests: self_heal 31 (+noop) + FE
>     PolishPanel 8 (+toggle).
>   - **★ Re-ranker made TYPE-ROUTED (RULE vs CRAFT) — a general judge is weak for novels (2026-07-01).**
>     PO: a general "is it better?" judge is shallow for fiction (quality isn't one axis). POC
>     (`poc/typerouted_compare.py` + `poc/io/typerouted_compare.log`) ran BOTH on all 50 proposals: the
>     **general judge APPLYed 47/50 (94%) — a rubber stamp that would AUTO-DELETE CH04's 8 passages**; the
>     type-routed auto-approved only **10 RULE** fixes (pronouns, `mẫu thân ngươi`, role/genre-term/typo) and
>     deferred **39 CRAFT** to the author + flagged 1 BAD. **Wired:** `_RERANK_SYSTEM` now classifies
>     **RULE** (objective convention/canon/typo/dup-word/grammar → auto-tick) vs **CRAFT** (rephrase/trim/
>     DELETE-passage/pacing/tone → author decides) vs **BAD**; `recommended = (verdict==RULE)`; degrade →
>     not-pre-checked (safe). Passage-deletion forced to CRAFT; RULE bucket widened to include typos (fixed
>     the POC's `món món` miss). Live CH1: all 5 = RULE, each citing the rule. Errs SAFE (defers borderline).
>     Tests: self_heal 31. **NEXT:** stronger-model escalate for the rare true blind spot.
>   - **M6 Polish — BE done (M6.1 engine + M6.2 wiring), 2026-07-01:**
>     **M6.1** (`c4db3792`) — `_compute_edits` shared step ⇒ `propose_self_heal` returns `EditProposal[]`
>     (id/tier deterministic|semantic/start/end/before/after) WITHOUT splicing; `apply_self_heal_edits(accepted_ids)`
>     splices the accepted subset; `run_self_heal` = propose+apply-all (byte-identical).
>     **M6.2** — worker op `self_heal_propose` (+ SUPPORTED_OPERATIONS + dispatch) + REST endpoint
>     `POST /v1/composition/projects/{id}/self-heal/propose` (resolve draft Tiptap→text + canon [override
>     or roster+convention] → propose → proposals; worker/inline like `plan_pipeline`). **Apply reuses the
>     existing `composition_write_prose`** — no new write tool / no confirm-token surgery. **Live-smoke:**
>     resolve path proven on the stack (get_draft `body` key + draft_version=2 → 7473-char prose; KAL roster
>     12 cast → 823-char canon); propose engine separately live-validated. Tests: self_heal 27 + worker_jobs
>     (dispatch + serialize).
>   - **M6.3 FE — DONE (Polish panel), 2026-07-01:** `PolishPanel` + `usePolishProposals` hook + `api.proposeSelfHeal`
>     / `applySelfHealEdits` (JS mirror of the engine splice); registered `polish` in the **Quality** group
>     (`workspace/types.ts` + `CompositionPanel` SubTab/stripIds/DockSlot, no-remount preserved); accept/reject
>     diff list (deterministic pre-checked, semantic unchecked); Apply → `ChapterEditorPage.handleApplyPolish`
>     replaces the doc via `setContent` (mirrors `handleTranslate`). Endpoint path fixed `/projects`→`/works`.
>     i18n `polish` label ×4 locales. Tests: tsc clean + **722 composition vitest** (incl. 6 new).
>     **NEXT:** re-drive CH1–12 with `verify_k=3` to refresh `story-export-v2/`.
>   - **Deferred D-POLISH-FE-BROWSER-SMOKE** (gate #4, needs FE image rebuild) — full click-through (open
>     chapter → Polish tab → Run → proposals → Apply) on a rebuilt FE image (running infra-frontend is the
>     old baked build). BE resolve-path + propose engine already live-smoked; FE↔BE call is typed + unit-tested.
>   - **/review-impl on M6 (2026-07-01):** **HIGH fixed** — stale cross-chapter proposals would Apply onto the
>     wrong chapter; fixed by `key={chapterId}` on PolishPanel (remount resets the snapshot). **MED fixed** —
>     FE `applySelfHealEdits` UTF-16-sliced Python code-point offsets; added a fail-safe (skip when
>     `slice≠before`). Tests: PolishPanel 7 + tsc clean. **Two MED deferred for a PO decision (snapshot
>     tradeoffs of whole-doc replace):** **D-POLISH-OCC** — Apply uses the propose-time `source_text` +
>     ignores `draft_version`, so edits made after Run (incl. unsaved buffer) are lost → compare version &
>     warn, or apply spans to the live doc. **D-POLISH-MARKS** — Apply rebuilds plain paragraphs ⇒ strips
>     inline marks (AI-provenance/bold) chapter-wide (same shape as handleTranslate). Plus LOW: no router
>     test for the propose endpoint.
>   - **Deferred D-SELFHEAL-CANON-ATTRS** (gate #2, structural) — heal canon is currently convention +
>     roster NAMES (KAL roster is names-only); rich per-character canon (descriptions → catches canon
>     contradictions like Tô Yến "che chở") needs a glossary "full cast WITH attributes" read. The
>     convention already grounds the dominant xưng-hô class; attribute-canon is the enrichment follow-up.
>
> **▶ Broader evaluation pass — DONE 2026-07-01 (`tests/e2e/eval_compose_quality.py` + `docs/specs/2026-06-30-editor-compose-overhaul/eval/2026-07-01-quality-eval.md`).** Drove all 3 surfaces × 12 real chapters + book coverage. Verdict: **critic** (10/10 violations real, 0 FP) + **book coverage** (v2, after windowing) are trustworthy; **self-heal** good (49 props, 0 no-ops) but hides its objective wins; the **per-chapter "dropped promises" is a false-positive machine** (30 flagged vs 0 abandoned book-wide — v1 audit mislabels still-*progressing* threads as dropped; the LLM's own "chưa/not-yet" annotations prove it). Ranked backlog below.
>
> **▶ Deferred (this track):**
> - ~~**D-QUALITY-DROPPED-FP**~~ — **RESOLVED 2026-07-01 (backlog #1).** The per-chapter Quality Report promise section is reframed from the misleading "dropped promises" alarm to **"threads RAISED in this chapter"** (informational) + any RESOLVED here; the false-positive "dropped" verdict is gone, and the book-level coverage owns paid/abandoned. `quality_report` now returns `{critic, threads:{raised, resolved, raised_count, resolved_count}}` (was `{critic, promises:{...dropped...}}`); `_chapter_threads` reshapes the audit; FE `QualityThreads` + `QualityReportSection` render "N thread(s) raised" (neutral) + "M paid off here" (green). E2E-confirmed (`raised` present, `dropped` absent). Tests: quality_report + worker + FE QualityReportSection updated green.
> - ~~**D-QUALITY-HONORIFIC-PRECHECK**~~ — **RESOLVED 2026-07-01 (backlog #2).** Data-driven: re-ran the eval with rerank=ON — the LLM re-ranker only pre-checked **8/15** honorific fixes (misclassifies ~half as CRAFT) at the cost of 49 extra calls. So "default rerank ON" was the WRONG fix. Instead: `self_heal._is_convention_fix(type)` code-detects the objective xưng-hô/address/typo class (a closed convention the auditor labels) and pre-checks it **deterministically + FREE** — even with rerank OFF, and it short-circuits the re-ranker when ON. E2E-confirmed on real ch1: 4/4 ADDRESS/HONORIFIC pre-checked, LOGIC/REPEATED (CRAFT) left unchecked. Tests: self_heal 34 (+3: _is_convention_fix, precheck-without/with-rerank).
> - ~~**D-QUALITY-CRITIC-HEAL-LINK**~~ — **RESOLVED 2026-07-01 (backlog #3).** The critic's canon violations ≈ self-heal's honorific edits (same issue, shown as diagnostic AND edit). `QualityReportSection` now takes the current `proposals` and marks each critic violation whose `span` overlaps a proposal's `before` with a **"fix proposed ↓"** badge (`_hasProposedFix`, normalized substring-either-way, min-len guard) — so the author sees "this violation already has a fix below" instead of double-counting. FE-only; PolishPanel passes `p.proposals`. Tests: QualityReportSection +2 (match / no-match); FE composition 737.
> - **D-QUALITY-COVERAGE-VARIANCE — LOW, DEFERRED (backlog #5, conscious).** Book-coverage paid↔progressing flips run-to-run (LM Studio/Gemma isn't fully deterministic even at temp 0). Stabilizing = a multi-sample majority vote per window = 3× the LLM cost for marginal gain on an ADVISORY signal. Gate #4 — fix only if the variance ever misleads a real decision. Trigger: a user reports a promise's verdict flipping confusingly.
> - **D-QUALITY-CH4-REGEN — LOW, NOT-A-CODE-FIX (backlog #4, conscious).** ch4's draft has a repetition LOOP; both critic (coh=2, "looping") and self-heal (10 "repeated") correctly flagged it — i.e. the TOOLS WORK. The resolution is regenerating ch4's DATA (a generation op), not a code change; near-zero product value on one POC chapter. Won't-fix as code; regenerate the draft opportunistically if the POC book is re-driven.
> - **D-QUALITY-MOTIF-ROLLUP** — surface `motif_conformance` beat-not-realized per chapter in the Quality Report (needs per-outline-node motif bindings aggregated across scenes). Gate #2 (structural). Target: a Q-follow-on to the Quality Report track.
> - ~~**D-QUALITY-COVERAGE-CHUNK**~~ — **RESOLVED 2026-07-01** (found by E2E → fixed → E2E-confirmed, the full loop). `build_promise_coverage` now WINDOWS the book (`_split_windows`, 12K-char paragraph-aligned) and scores each window against the same fixed promise set, MERGING per-promise by strongest engagement (paid > progressing > abandoned > absent); all windows failing → honest `coverage_unavailable`. **E2E-confirmed on the real 12-ch book:** was `coverage_unavailable` + all-10-absent → now `error:None`, 9 promises all **"progressing"** (a sensible read of a setup-heavy opening: promises live, none resolved/dropped yet). Tests: quality_report 12 (+3 windowing) + an E2E regression guard (`error != coverage_unavailable`).
>
> **▶ E2E harness — SHIPPED 2026-07-01 (`9687f6910`), replaces live-smoke/POC (per user).** `tests/e2e/quality_harness.py` + `tests/e2e/test_compose_quality_e2e.py`: drives the REAL `/v1/composition/*` quality endpoints through the gateway as the claude-test account, discovering a real target black-box (books → work → a DRAFTED chapter → chat model) + job-poll. 4 E2E green. First run surfaced (a) a STALE-IMAGE trap (running composition image predated the endpoints → 404; rebuilt composition-service+worker) and (b) the coverage-chunk bug above — both invisible to a crafted-input smoke. **Methodology (LOCKED, see memory `prefer-e2e-and-evaluation-over-live-smoke-poc`):** validate compose-quality via real E2E + evaluation analysis over the real book, not hand-fed smoke. **NEXT:** either fix D-QUALITY-COVERAGE-CHUNK (make Q3 work on real books) or run a broader evaluation pass across all 3 surfaces × 12 chapters to build the improvement backlog.
> - **D-ARC-TEMPLATE-CRUD-GUI / D-MOTIF-LIBRARY-CRUD-GUI** — auto arc-conformance + the motif-library judges are gated on GUI-managed artifacts (arc templates only from reference-import/authored; no `work→arc_template` link). Making them useful needs whole CRUD GUIs — big features. Gate #2 (structural). Target: discuss + plan as their own features.
> - **Recently cleared:** ~~D-QUALITY-ARC-LEVEL~~ — SHIPPED as Q3 (book-level promise coverage, 2026-07-01).
> - **D-THREAD-MOTIF-COMBINED** — `thread_state` + `motifs_enabled` together: typed-state threading is skipped on the motif path (motif `prev_effects` carry used; warned, not silent). Gate #2 (needs interleaving the motif sequential select with the threaded invent loop). Target: when motifs + threading are both wanted in one run.
> - **Book-service universal formatter** (slice 01: `tiptap.go`/`server.go` markdown→Tiptap) — built, **uncommitted**, awaiting the PO's read-mode test before a separate commit.
> - GUI milestones M0–M5 — paused behind the synthesis track (output quality first).

> ---

# ▶▶ (merged from origin/main 2026-06-30) **Temporal Knowledge — COMPLETE (foundation + close_fact + full fanout X1–X7 + FE temporal surfaces + REAL per-episode translation); branch ready for review/merge** · branch `feat/temporal-knowledge-architecture` · HEAD `pending` · 2026-06-30

> **▶ PER-EPISODE TRANSLATION — now a REAL feature (this run), not a degrade.** The §7.6 surface translates the
> entity's as-of folded canonical into the reader's display language, on-demand + cached immutable per (content,
> language) — mirror of KG-TL M3. NEW: glossary migration **0050** `canonical_snapshot_translations` (single-flight
> claim + background fill), `translation_client.go` (→ translation-service `/internal/translation/translate-text`,
> BYOK via provider-registry — no LLM in glossary), `canonical_translation_handler.go`; KAL read
> `GET …/canonical-translation?lang=&as_of=` + contract `CanonicalTranslation`; FE `useCanonicalTranslation` (polls
> while `translating`) + rewritten `EpisodeTranslationPanel` (language selector reuses the shared per-book
> `useGlossaryDisplayLanguage` → lockstep with the glossary browser; picks original ⇒ shows original, no LLM).
> **Verified:** glossary go tests (incl. state-machine integration on the real `loreweave_glossary` DB) · KAL jest
> 19 · FE 45 + tsc clean · both INV-KAL lints + provider-gate PASS · **live-smoke** FE→BFF→KAL→glossary→translation
> →provider-registry→lm_studio: zh canonical → `ready/translated/cached` real EN translation, single-flight = 1 call.
> Plan: `docs/plans/2026-06-30-per-episode-translation-surface.md`.
> **/review-impl pass (1 MED + 2 LOW, all fixed):** a per-user config error (no_model/no_user) no longer poisons the
> shared book-tier row / exhausts the retry budget — it's caller-specific + costs no LLM, so a configured viewer
> always heals it (provider/quota failures still respect `foldRetryBudget`); success-UPDATE got the `status='pending'`
> guard; added a heal-path integration test. **User-mode e2e through the BFF** (real login JWT → KAL dual-auth + book
> grant): owned book → `ready` real EN translation, no-auth → 401, non-granted book → 403.

> **▶▶ ENTIRE EFFORT COMPLETE — the Incremental Temporal Knowledge Architecture is built, verified, and
> committed end-to-end (F0–F4 foundation + close_fact + X1–X7 fanout + X6 FE). The branch is production-ready
> for review/merge.**
> - **Foundation** (bi-temporal `entity_facts` SSOT, `maintain_chain` single writer, episodes, fold loop, KG
>   ordinal valid-time, KAL service) — hardened across **4 /review-impl passes** (4 HIGH + 6 MED + LOWs fixed, e2e green).
> - **close_fact** — pinned valid-time close (0049 pin-aware maintain_chain); reviewed + live-smoked.
> - **Fanout:** X1 composition / X2 lore-enrichment / X5 translation → KAL (consumers read bi-temporal knowledge
>   through the KAL); X3 wiki / X4 chat verified no-ops; **X7 — BOTH INV-KAL lints ENFORCED** (table-read +
>   HTTP-surface); cross-service smoke green.
> - **X6 FE:** KAL **dual-auth** (JWT + book grant-check, anti-spoof) + BFF `/v1/kal` route (reviewed + live-verified
>   200/403/401); **6 temporal surfaces** (canonical card, time slider, change timeline, diff, retrieval,
>   per-episode translation) — 45 tests, tsc clean, real-KAL shapes validated, mounted in the entity panel's
>   "Temporal" tab.
> - **Honest limitations (not bugs, future enhancements):** per-episode translation is now REAL (built this run —
>   see the block above); KG `as_of` honored (F3 landed). A full browser/Playwright smoke of the Temporal tab is the
>   one remaining nice-to-have (shapes + the FE→BFF→KAL path + 45 component tests + the HTTP-chain live-smoke are verified).



> **▶ FOUNDATION COMPLETE — all verified (real DB / build / tests):** F0 KAL contract · F1a-h substrate
> (entity_facts/maintain_chain/episodes/cold-start) · F1d producer (facts flow from extraction, idempotent) ·
> F1f fact-chain merge + split · F1g bi-temporal name/aliases + as-of-name (0048 reconcile) · F2 canonical
> versioned-cache + the **fold loop** (glossary dirty/fetch/snapshot/degrade + the translation fold worker, LLM via
> provider-registry) · F3 KG ordinal valid-time + in-story dates · F4 KAL NestJS service (auth-guarded) with the full
> read surface (facts/timeline/attr-values/roster/canonical) + write surface (episode/append/close/retract/merge/
> resolve/split/fold) + the INV-KAL table-read lint (pre-commit). Three /review-impl passes, all HIGH/MED fixed
> (security: KAL inbound auth; tenancy: fact book-scoping; correctness: same-ordinal supersede, merge attr-set).
>
> **▶ PRE-FANOUT HARDENING REVIEW (this run) — 5 parallel adversarial reviewers over the whole foundation; 4 HIGH +
> 6 MED + LOWs found and ALL FIXED (15 files, 4 services), cross-service e2e GREEN on the rebuilt glossary image:**
> - HIGH: split cross-book leak (`internalSplitEntity` had no `entityInBook(source)` guard) · KG same-ordinal
>   `[base,base)` empty-interval data loss (4 cypher blocks → strictly-greater, mirrors PG core) · KAL `fold` write
>   unroutable → built the `internalTriggerFold` glossary backing + route (live-smoked HTTP 200) · KAL `facts/close`
>   doubled path. · MED: fold fingerprint lexical-vs-numeric max **livelock** (now numeric, live fingerprint `1638578`) ·
>   NULL-unsafe staleness probe · degrade-read book-scope + `refreshEAVProjection` hardcoded `'zh'` · 0048 re-run cold-start
>   scope · KAL downstream abort-signal + non-JSON-2xx guard + strict array coercion + NaN guard. · LOWs: fold worker
>   model_ref skip / cancelled≠backoff / prompt-injection delimiting. (The summary's `_cast_roster` drain bug = phantom.)
> - Verify: Go build/vet + 12 temporal Go tests (real DB) · jest 5/5 · fold pytest 3/3 · KG 15/15. E2E: KAL→glossary
>   forwards incl. the new fold write route + 401 auth guard, as-of reads, degrade-to-canon — all green.
> - **close_fact — DONE** `1e80637e` (PO: build-now): the frozen KAL close verb is now backed. Migration 0049 adds
>   `valid_to_pinned` + a pin-aware maintain_chain (CREATE OR REPLACE) — a manual close is an authored INPUT the single
>   deriver RESPECTS, never a competing deriver (the LOCKED §12.3.3 invariant holds). closeFact core + internalCloseFact
>   (book-scoped, validates in-book + valid_to > valid_from). Live-smoked: as-of 30 present, as-of 60 absent, 422/404 guards.
> - **/review-impl on close_fact — DONE** `fb3a34ed` (PO: commit-then-review): 3 MED found + fixed — overlap guard
>   (close past a successor → 422, was a double-value hole), split now PRESERVES the pin (`valid_to_ordinal`+`valid_to_pinned`
>   copied), and TestFactsHTTP regression-locks close half-open + overlap-422 + cross-book-404.
>
> **▶ FOUNDATION FULLY HARDENED + COMPLETE (incl. close_fact).**
>
> **▶ BACKEND FANOUT COMPLETE (X1–X5, X7) — consumers now read bi-temporal knowledge through the KAL; both
> INV-KAL lints ENFORCED:**
> - **X1 composition** `ae4016ea` — `KalClient.roster` DRAINS `next_cursor` (fixes the D4 truncation-at-100 bug);
>   `_cast_roster` migrated; dead `list_entities` removed. 1181 tests green.
> - **X2 lore-enrichment** `9af1c255` — `KalClient` (roster drain + facts/canonical/search); full-book cast from
>   the drained roster. Residual: `kind`/`short_description` supplemented from the authored entity-list (catalog,
>   not bi-temporal — out of INV-KAL scope, like the table-read gate's `glossary_entities` exemption).
> - **X5 translation** `0471b48c` — `KalClient` (get_facts/get_canonical) with **as-of-N inject** (threads
>   `chapter_sort_order`) + **immutable-once cache** (keyed on chapter content-hash + as-of). Default (no
>   `KNOWLEDGE_GATEWAY_URL`) byte-identical to today.
> - **X3 wiki / X4 chat — verified NO-OPs:** wiki is owner-side (glossary, lint-exempt); chat's entity reads are
>   MCP tools federated by name through ai-gateway (MCP-first invariant — must stay that way). No dead code added.
> - **X7** `7fb6e692` — built the INV-KAL **HTTP-surface lint** (was DEFERRED `D-KAL-HTTP-SURFACE-LINT`); BOTH
>   halves now ENFORCED in pre-commit. Both lints PASS full-scan (zero direct bi-temporal knowledge reads in consumers).
> - **KAL in docker-compose** `b695ab7d` — built + healthy in-stack; cross-service smoke: composition container →
>   `knowledge-gateway:3000` roster returns the contract shape.
>
> **▶ X6a/b — FE→KAL bridge DONE + live-verified** `bf772913` (PO: dual-auth chosen):
> - **KAL dual-auth** (read surface; writes stay internal-only): SERVICE mode (X-Internal-Token) OR USER mode —
>   validate the platform HS256 Bearer JWT (Node crypto, no dep; rejects alg=none/wrong-sig/expired, timing-safe) +
>   GRANT-CHECK the book against book-service (`/internal/books/{id}/access`) since the BFF is a dumb proxy. X-User-Id
>   PINNED from the JWT sub (anti-spoof). Fail-closed + 5s grant timeout + bounded positive-grant cache.
> - **BFF** `/v1/kal` → knowledge-gateway (dumb JWT passthrough, 503-on-down). KAL compose env: JWT_SECRET + BOOK_SERVICE_URL.
> - **Reviewed** (/review-impl: MED grant-timeout + LOW cache-bound fixed) + **live-smoked** the full FE path with a
>   REAL login JWT: owned-book→200, non-granted→403, no-auth/garbage→401, service-mode→200. KAL jest 17 green.
>
> **▶ ONLY REMAINING: X6c — the net-new FE TEMPORAL SURFACES (React, this branch):** canonical card (as-of folded
> canonical), time/version slider (scrub chapter ordinal), change timeline w/ citations, diff view (state between two
> ordinals), retrieval-not-scroll, per-episode translation (§7). Reads go through the BFF `/v1/kal/*` (now live).
>
> **▶ REMAINING = the consumer/FE FANOUT (parallel worktree agents, the locked strategy):**
> X1 composition→KAL (+fix `_cast_roster` cursor drain) · X2 lore-enrichment→KAL · X3 wiki→KAL (kill direct-EAV) ·
> X4 chat→KAL · X5 translation→KAL (as-of inject + immutable-once cache) · X6 FE temporal surfaces (canonical card,
> time slider, change timeline, diff, retrieval) + migrate FE reads to KAL · X7 flip BOTH INV-KAL lints (table-read +
> the new HTTP-surface lint) to ENFORCING. Each binds ONLY to the frozen `kal.v1.yaml` → provably disjoint, parallel-safe.

> **▶ Shipped this run (production-ready, all verified on real DB / build / tests):**
> - **F1d (producer)** `d5662b64` — facts FLOW from extraction: translation worker passes `chapter_ordinal`,
>   glossary writeback ingests the episode + opens append-only facts per written attr, idempotent. (`TestBulkExtract_EmitsTemporalFacts`)
> - **F4-live core** `c13d11bb` — glossary `/internal/facts/*`: GET facts/timeline/attr-values (bounded, as-of) + POST
>   episode/append/retract; KAL paths aligned. (`TestFactsHTTP`: append supersedes, retract restitches over the router)
> - **F4-writes** `41070247` — internal merge/resolve-entity/split routes + KAL wiring (resolve-or-create idempotent).
> - **in-story dates** `a5d0d80e` (merged) — `event_date_iso` additive valid-time on KG facts/relations (19 tests; chapter-ordinal stays primary).
> - **prod bugfix** `94caea91` — world-timeline `NameError: q` (pre-existing crash) fixed.
>
> **▶ Remaining foundation (then fanout):**
> - **F2-app — fold handler:** dirty queue + canonical_snapshot write + lazy rebuild-on-read + ordinal-bucketed re-ground
>   (B1) + compare-and-clear + backoff. LLM via provider-registry (likely a worker/knowledge pass like #26/#7 summarize).
>   Makes `get_canonical` return the FOLDED canonical (today it serves canon-content). Adds the KAL `fold` route.
> - **F1g — bi-temporal names:** name as `fact_kind='name'` (single) + aliases as `'alias'` (multi); as-of-name; resolver
>   matches the across-time alias set. RECONCILE: migration 0048 converts the cold-start/F1d `attribute` name/aliases
>   facts → name/alias kind, and `refreshEAVProjection` + the D5 check must project name-kind facts to the name EAV.
> - then **fanout X1–X7** (parallel worktree agents per the locked strategy).


> **What this branch is:** implementing the Incremental Temporal Knowledge Architecture
> ([spec](../specs/2026-06-29-incremental-temporal-knowledge-architecture.md) §12/§12.7.8 govern;
> [plan](../plans/2026-06-30-temporal-knowledge-architecture-impl.md)). Append-only bi-temporal facts as the
> sole SSOT (INV-FACTS §12.0); everything else a rebuildable cache. Execution = **serial foundation → parallel
> fanout** (user-directed: build foundation serially, checkpoint, then fan out consumer migrations).
>
> **▶ Shipped this session — the SSOT substrate spine, all real-DB verified on `loreweave_glossary`:**
> - **F0** `fc4c9a80` — froze the **KAL v1 contract** (`contracts/api/knowledge-gateway/kal.v1.yaml`), the keystone
>   every consumer binds to; `knowledge-gateway: missing` row in `language-rule.yaml` (→ typescript at F4 scaffold).
> - **F1a** `ae6f17fd` — `0044` **entity_facts + episodes** bi-temporal SSOT schema (content-addressed natural key,
>   `valid_to_eff` INT64_MAX null-sink, `coverage_xid` xid8, merge_journal fact/episode-move cols). Idempotent 2×.
> - **F1b** `728efaf9` — `0045` **maintain_chain** the single `valid_to` writer (§12.3.3). Verified all 3 scenarios:
>   out-of-order backfill (A2), retract restitch (A3), oscillation (A4).
> - **F1c** `8a2b8e6d` — **fact core** Go (`facts.go`): appendFact (idempotent NK), retractFacts (restitch),
>   ingestEpisode, refreshEAVProjection (repair/cutover), per-(entity,attr) chain lock. `TestFactCore` PASSES (real DB).
> - **F1h** `8eb419f9` — `0046` **cold-start seed**: 22,056 facts seeded from live EAV; **projection==flat_eav 0 mismatches** (§12.5.4/D5).
> - **F2 schema** `fdf6c0d8` — `0047` **canonical versioned-cache** tables (canonical_snapshot + canonical_fold_state), §12.1.
>
> ⚠ Migrations **0044–0047 are applied to the running dev `loreweave_glossary`** (by F1c's `RunChain`); a fresh stack
> picks them up from the ledger on boot.
>
> **▶ PARALLEL track (background agent, worktree):** **F3 — KG ordinal valid-time unify** in `knowledge-service`
> (Python/Neo4j) — substrate-independent from glossary. Ordinal valid-time unified with `from_order`, ordinal-aware
> close (A2 on the KG side), extraction-driven invalidate/retract, quote-on-citation, per-entity ordinal snapshot.
> **Merge its worktree branch at the integration node before F4.**
>
> **▶ F3 — KG ordinal valid-time unify — MERGED `f2d5ca3e`** (was a parallel worktree agent); 24 F3 unit tests
> re-verified green post-merge. All under `services/knowledge-service/` (disjoint from glossary).
>
> **▶ F1f — fact-chain merge + split (DONE):** `ecc7e587` **merge** (§12.4.1, `mergeFactChains`/`revertFactChains`,
> journal `repointed_fact_ids`+`invalidated_fact_ids`, same-ordinal tiebreak, chain locks both sides) +
> `f52e50f7` **split** (§12.4.2, `splitFactsByEpisode` re-attribute-by-provenance, originals reason='split').
> `TestMergeFactChains`/`TestSplitFactsByEpisode` green; existing Merge/Revert/Dedup suites green (no regression).
>
> **▶ F4 — KAL gateway service + INV-KAL lint (DONE, structure):**
> - `2ab5f710` **KAL NestJS service** (`services/knowledge-gateway`) implementing `kal.v1.yaml`: config/main/health +
>   `KalReadController` (get_canonical/get_facts/timeline/list_attr_values/roster/search/neighborhood/retrieve, each with
>   per-substrate `temporal_capability`, KG `as_of` dropped when `temporal_unsupported`) + `KalWriteController`
>   (append/close/retract/merge/split/fold/ingest_episode/resolve_entity forwarding to glossary `/internal/facts/*`).
>   **Verified: npm install + nest build clean; boots + serves /health + /health/ready (kgTemporal=ordinal_valid_time),
>   16 routes mapped.** `language-rule.yaml` `missing`→`typescript`; lint PASS.
> - `434894d8` **INV-KAL table-read lint** (`scripts/knowledge-access-gate.py`, wired into `.githooks/pre-commit`): no
>   consumer reads the glossary EAV / Neo4j directly. Full-scan PASS.
>
> **▶ NEXT — F4-FOLLOW-ON + remaining foundation, then fanout:**
> 1. **F4-follow-on (live writes):** add the glossary **`/internal/facts/*` HTTP routes** (Go handlers wrapping the F1c/F1f
>    fact core — appendFact/retract/mergeFactChains/splitFactsByEpisode/fold) so the KAL write verbs hit a real target;
>    then a **cross-service live-smoke** (KAL → glossary fact route → DB) + verify the read endpoints' downstream path
>    mapping against the actual glossary/KG routes. (KAL reads/writes build + the service boots; full delegation is the
>    cross-service smoke, currently unverified end-to-end.)
> 2. **F2 app** — the fold handler: lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff
>    (needs a provider-registry LLM call). Enhances `get_canonical` behind the frozen contract.
> 3. **F1g** — bi-temporal name/aliases (§12.4.3) + as-of-name. **Value partly gated on F1d** (deferred writeback wiring);
>    reconciles `D-TK-F1G-NAME-RECONCILE`.
> 4. **CHECKPOINT** → then parallel **fanout** X1–X7 (consumer migrations onto the KAL, FE temporal surfaces).
>
> **▶ SCOPE (locked 2026-06-30): this branch is the PRODUCTION-READY refactor — NO deferrals.** Everything below is
> in-branch work to COMPLETE (the repo adopts the KAL immediately after merge, so nothing core may be stubbed/parked).
> Includes the full consumer + FE fanout (X1–X7) and both INV-KAL lints flipped to ENFORCING. The items that were
> "deferred" are now must-complete work:
> - **F1d — writeback Path-A emission (must complete):** wire fact emission into the glossary writeback; extend the
>   bulk-extract request with `chapter_ordinal` and update the translation-service extraction caller to pass it.
> - **F4-live — glossary `/internal/facts/*` HTTP routes** wrapping the Go fact core (append/close/retract/merge/split/
>   fold/ingest_episode/resolve_entity) so the KAL writes are real; cross-service KAL→glossary→DB live-smoke.
> - **F2-app — fold handler:** lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff (LLM via provider-registry).
> - **F1g — bi-temporal name/aliases** (§12.4.3) + as-of-name + RECONCILE the cold-start name/aliases representation
>   (supersede the cold-start `attribute` name/alias facts → `name`/`alias` kind facts; the old `D-TK-F1G-NAME-RECONCILE`).
> - **In-story dates (must build — user pulled into v1):** detected in-story time (`event_date_iso`) as an additional KG
>   valid-time source (spec §9 dec-3). Knowledge-service.
> - **Fanout X1–X7 (in-branch):** migrate composition, chat, lore-enrichment, translation, wiki, FE to read/write through
>   the KAL; kill every direct EAV/KG read; flip BOTH INV-KAL lints (table-read + HTTP-surface) to ENFORCING.
>
> **▶ /review-impl (2026-06-30) — 7 findings, ALL FIXED (no HIGH):** MED-1 same-ordinal single-valued conflict → last-write-wins supersede + deterministic projection tiebreak (`TestFactSameOrdinalConflict`); MED-2 unenforced chain-lock → strengthened contract doc + `TestFactChainLockSerializes` (same-chain blocks, disjoint free); LOW-2 cold-start ordinal `0→-1` (chapter_index is 0-based); LOW-5 targeted `ON CONFLICT` on the natural-key expression index; LOW-3 `refreshEAVProjection` attr_def_id-coupling doc; LOW-4 `reconcileEpisode` F1d-obligation doc + now exercised; LOW-1 → `D-TK-F1G-NAME-RECONCILE` above. All 3 facts tests green on real DB; cold-start re-verified `projection==flat_eav` 0 mismatches with the `-1` sentinel.

---

# ▶▶ (prior) **Motif book-collaboration tier (model B) + shared-graph links + MCP edit SHIPPED** · branch `feat/narrative-pattern-library` · HEAD `8c4c45c2`+ · 2026-06-29

> **▶ MERGE 2026-06-29:** `origin/main` merged into this branch (179 commits — the **public-MCP gateway + lazy tool-loading** track, critical-UX fixes, glossary/knowledge/campaign work). Conflicts resolved (composition `actions.py` confirm = JWT-identity ∪ public-MCP spend-attribution; engine `plan.py`/`stitch.py` signatures = both; studio panels = `canonview` ∪ `motifs`/`conformance`; gateway test `mcpPublicGatewayUrl`). The motif MCP tools are exposed to the public-MCP gateway: `find_tools` (lazy discovery) picks them up dynamically from the federation catalog, and they are classified in the edge `TOOL_POLICY` allowlist (commit `2aa65765`). Below is this branch's motif work; the merged-in main tracks + all prior history are archived (see the pointer at the bottom).

> **▶ Follow-up this session (2nd commit) — both model-B deferrals CLOSED:** `D-MOTIF-LINK-SHARED-TIER` (shared-graph link editing — guard rewrite + repo/MCP book_id paths) and `D-MOTIF-MCP-PATCH-SHARED` (the `composition_motif_patch` MCP edit tool). Details in the "Deferred … BOTH NOW CLEARED" block below. 150 motif unit tests + 38 motif DB integration tests green; migration re-smoked idempotent on real `loreweave_composition`; provider-gate clean.

> **▶ Shipped this session — the two NEW future-feature rows (now CLOSED):**
> - **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER` (model B) — a THIRD tenancy tier (the book SHARED library).** Spec: [docs/specs/2026-06-29-motif-book-collab-tier.md](../specs/2026-06-29-motif-book-collab-tier.md). A `motif.book_shared=true` row is owned by its creator (attribution) but VISIBLE to the book's VIEW-grantees and WRITABLE by its EDIT-grantees — access is the **book grant resolved at the caller**, never row ownership. User decisions (this session): **context-scoped reads** (per-book gate, no global "all my books"), **any-EDIT-grantee writes** (edit + archive), **adopt + create + mine** all produce shared rows. The base read predicate is **UNCHANGED** (a foreign shared row is fail-closed invisible to get_visible/list_for_caller/catalog/get_by_codes); shared rows surface ONLY through the gated book-context methods. Touch-points: schema (`book_shared` col + `motif_book_shared_shape` CHECK [shared ⇒ book+owner+private, the public-catalog-orthogonality guard] + per-book `uq_motif_book_shared` + re-narrowed `uq_motif_user_book WHERE …AND NOT book_shared`); repo (`clone/adopt/create/_clone_with_code` thread book_shared; new `list_in_book/get_in_book/patch_shared/archive_shared`; adopt locks per-BOOK + dedups per-(book,code) for the shared tier); MCP (`adopt target=book_shared`, `create target=book_shared`, `mine promote_target=book_shared`, `archive book_id=`, new `composition_motif_book_list`); confirm dispatch (`book_shared` rides the payload, re-gated EDIT); FE (3rd adopt target "Share with collaborators" + `Shared` badge).
> - **`D-MOTIF-HTTP-ADOPT-BOOK` — HTTP parity.** `POST /motifs/{id}/adopt` now takes `target=user|book|book_shared`+`book_id`, **EDIT-gated before the clone** (no softer than MCP); `GET /motifs/book/{id}` (VIEW-gated list); `PATCH`/`DELETE …?book_id=` (EDIT-gated shared edit/archive, visibility-flip refused 400). A book-shared pattern root does NOT auto-adopt its members (the half-shared-pattern guard).
>
> **VERIFY:** 90 motif unit tests + new repo/mcp/router cases green; **integration (real PG)**: new `test_motif_book_shared_db.py` (shape CHECK, per-book dedup, list/get scoping, any-grantee patch/archive) + 32 existing motif DB tests pass on a throwaway DB; **migration live-smoked idempotent on the REAL existing model-A `loreweave_composition`** (added book_shared col + CHECK + uq_motif_book_shared + re-narrowed uq_motif_user_book; two runs, no error). FE 152 motif tests + tsc + provider-gate clean. **`/review-impl` adversarial tenancy review: 0 HIGH / 0 MED** — all 9 read/write/leak/confirm/dedup checks PASS with file:line evidence; 3 LOW/COSMETIC notes (deferred below).
>
> **▶ Deferred (from the model-B review — BOTH NOW CLEARED 2026-06-29):**
> - ✅ **`D-MOTIF-LINK-SHARED-TIER`** — **CLEARED:** the `motif_link_guard` was rewritten (NULL-safe) to a precise 3-arm same-tier rule — both SYSTEM, or both the SAME book's SHARED tier (owners may differ — the point of a collaborator graph), or both the SAME user's PRIVATE tier. A shared↔private/system/cross-book link is rejected at the DB. Repo `list_links/create_link/delete_link` gained a `book_id` path (anchor via get_in_book; both endpoints must be `book_shared AND book_id`); MCP link tools take `book_id` (VIEW for list, EDIT for create/delete). Live-PG tested (same-book allowed, 3 cross-tier rejections, 3rd-grantee list/delete) + migration re-smoked idempotent on real `loreweave_composition`. **Caught+fixed a SQL three-valued-logic bug**: `owner = owner` with a NULL operand yields NULL so `IF NOT NULL` wouldn't fire (a user→system link would have slipped) — every arm is now NULL-guarded.
> - ✅ **`D-MOTIF-MCP-PATCH-SHARED`** — **CLEARED:** new `composition_motif_patch` MCP tool (Tier-A) — owner-keyed by default, or a SHARED-tier edit with `book_id` (EDIT-gated → patch_shared). Optimistic-lock `expected_version` (stale → applied_conflict), visibility/publish deliberately NOT editable (separate flow), honest undo that patches changed fields back to prior values. Owner path denies a foreign row before any write; shared path confirms the row is shared-in-this-book.
>
> ---
>
> # ▶▶ (prior) **Motif library COMPLETE — audit 7/7 closed (WI-1…WI-6)** · HEAD `04bab448`+ · 2026-06-29

> **What this branch is:** the narrative-pattern (motif/arc) library — Tier-W cost-gated MCP flows for mining, conformance, adopt, and 3-way publish-sync, fronted by the FE→MCP-tool bridge. The feature body landed across prior sessions; this session closed the **completeness-audit tail** AND shipped **WI-5 per-book adopt**.
>
> **▶ Shipped this session (all green — 1083+ backend unit + 151 FE motif tests, tsc + provider-gate clean):**
> - **Audit tail (committed `f1157b25`…`b8f0ddb3`):** BYOK model_ref threading through `motif_mine`/`arc_import`; the **tag-beats LLM extractor** (knowledge `POST /internal/extraction/tag-beats` → composition mine pre-pass; cross-tenant injection neutralized); **WI-3 arc semantic retrieve** (`composition_arc_suggest`); **WI-1/WI-2/WI-4 FE** (mine panel, full editor, publish-sync); `/review-impl` fixes (arc back-fill scoped to own/system; editor edit-loss). Completeness audit: [`docs/reports/2026-06-29-motif-completeness-audit.md`](../reports/2026-06-29-motif-completeness-audit.md).
> - **WI-5 per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`) — model A "book-scoped filter" (user-chosen, NOT the tier-reversal):** `motif.book_id` is a per-book LABEL on a clone the adopter still owns. The read predicate + 2-tier tenancy are **UNCHANGED** (book_id only narrows the owner's view, never widens visibility). Design: [`docs/plans/2026-06-29-motif-adopt-per-book.md`](../plans/2026-06-29-motif-adopt-per-book.md). Touch-points: schema (`book_id` col + `uq_motif_user` scoped to `book_id IS NULL` + new `uq_motif_user_book` partial + `idx_motif_book`); `MotifRepo.clone/adopt/_clone_with_code/list_for_caller`; `_MotifAdoptArgs.target=Literal['user','book']`+`book_id` (EDIT-gated at propose **and** confirm); FE adopt-to-book toggle (api/hook/AdoptTargetModal/MotifLibraryView). **Live-smoked** on real `loreweave_composition`: migration idempotent; global+per-book coexist; same-book dup blocked by `uq_motif_user_book`; 0 leaked rows.
> - **WI-6 motif_link edge-walk (`D-MOTIF-LINK-EDGEWALK`) — the FINAL §5 gap, closing the audit 7/7:** 3 MCP tools — `composition_motif_link_list` (R, traverse out/in/both with neighbor code+name), `composition_motif_link_create` + `_delete` (A). User-scoped; WRITE requires **BOTH endpoints owned by the caller** (the system↔system hole the DB `motif_link_guard` same-tier check misses — a user may never reshape the shared graph). `MotifRepo.list_links/create_link/delete_link`. **Live-smoked**: own→own create/list/delete OK; own→system rejected by the guard; 0 leaked rows. The completeness audit is now **7/7 closed, nothing deferred**.
>
> **⚠ Two already-built misfires earlier this session** (memory [[verify-built-before-building]]): `D-W8-MOTIF-BEAT-EXTRACTOR` and `D-MOTIF-SYNC-3WAY-BASE` backend were **already shipped** — I rebuilt a duplicate sync router and reverted it (`a24d99ea`). **Before building ANY "missing"/deferred motif item: `git grep` the route/module/test first.**
>
> **▶ NEXT:** **PR `feat/narrative-pattern-library` → main** — the feature body + audit tail + WI-5 are complete, green, and live-smoked. (Note: the WI-5 migration was applied to the *running* dev `loreweave_composition` by the live-smoke; a fresh stack picks it up from `migrate.py` on boot.)
>
> **▶ Deferred (motif — the §5 audit tail is 7/7 CLOSED; these were NEW future-feature rows):**
> - ✅ **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER`** — **CLEARED (2026-06-29):** model B shipped (see the top block). The shared book tier landed with a 0-HIGH/0-MED adversarial tenancy review.
> - ✅ **`D-MOTIF-HTTP-ADOPT-BOOK`** — **CLEARED (2026-06-29):** the HTTP adopt route exposes `target`+`book_id`, EDIT-gated (see the top block).

---

> **▶ Archived 2026-06-30** — older / other-track handoffs moved to [`SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md) to keep this file to the **active branch** only. The 2026-06-29 merge pulled in main's `Critical UX` + `Public MCP` tracks and all prior session history (glossary / composition / roleplay / extraction / KG / campaign / Sessions 66–71); all of it (incl. each track's open-defer register) lives in the archive and on its own branch + `main`. Search `SESSION_ARCHIVE.md` for a `D-…` id if you need a prior-track defer.
