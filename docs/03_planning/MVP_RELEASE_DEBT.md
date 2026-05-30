# MVP Release Debt — Inventory & Tracker

## Document Metadata
- Document ID: LW-MVP-DEBT
- Version: 0.1.0 (DRAFT — under discussion)
- Status: Draft
- Owner: Full-Stack Lead
- Created: 2026-05-30
- Branch: `mvp-release-debt`
- Summary: Single source of truth for **unshipped MVP debt** that must be resolved (or consciously cut) before public release. The existing `docs/deferred/DEFERRED.md` tracks only geo-generator / tilemap / AMAW work — it does **not** cover the MVP product surface (translator, writing assistant, GUI polish, cloud-readiness). This doc fills that gap.

> **Why a separate doc:** several feature branches develop in parallel (geo-generator, lore-enrichment, knowledge-service). This file is intentionally self-contained and additive to avoid merge conflicts with those branches. It does not edit `DEFERRED.md` or `SESSION_PATCH.md`.

---

## 0. Context (how we got here)

- The 5 MVP modules (M01–M05: Identity, Books, Provider Registry, Translation, Glossary) are all marked **"Closed (smoke)"** in the Module Status Matrix (`docs/sessions/SESSION_PATCH.md`): code exists, smoke tests pass, but **no formal acceptance evidence pack** has been produced.
- Development focus shifted ~end of April 2026 from MVP product polish to the **geo-generator / world-gen / eval / tilemap** track (RAG quality measurement). Evidence (last commit touching each area):
  - Translation feature/service: **2026-04-27**
  - Chapter editor: **2026-04-08**
  - Grammar feature: **2026-04-04** (rename only)
  - vs. world-gen / eval / tilemap: active through **2026-05-30**
- Net effect: MVP completion debt accumulated but is **untracked**. This doc is the catch-up inventory.

**Verification note:** findings below are from a code-vs-plan scan (file evidence cited). Plans 71/72 were not verified line-by-line — only that their principal artifacts exist. Items marked ⚠️ need deeper confirmation.

---

## 1. Debt Inventory

Legend — **State**: `SHIPPED` (done, just needs sign-off) · `PARTIAL` (built but incomplete) · `STUB` (placeholder visible in UI) · `NOT-BUILT` (planned, no code) · `OPS` (deploy/readiness, not a feature).

### 1.1 Translator Pipeline

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| TR-1 | Chunking + session context + AI compaction (Plan 71) | SHIPPED | `services/translation-service/app/workers/session_translator.py`, `chunk_splitter.py`, `coordinator.py` | Plan 71 still labelled *"implementation in progress"* — needs DONE sign-off |
| TR-2 | Compact prompts + BCP-47 list + timestamps (Plan 73) | SHIPPED | `migrate.py:137-146` (compact_system_prompt / compact_user_prompt_tpl columns) | Verify FE wiring (PromptEditor / AdvancedTranslationSettings) |
| TR-3 | Translation UX redesign: version mgmt, coverage matrix, language dropdown (Plan 72) | ⚠️ SHIPPED? | `features/translation/components/{VersionSidebar,SplitCompareView,BlockAlignedReview}.tsx`, `pages/ChapterTranslationsPage.tsx` | Need line-by-line check vs Plan 72 to confirm % complete |
| TR-4 | M04 acceptance evidence pack | NOT-BUILT | Matrix shows "⚠️ Smoke only" | Formal acceptance test run, not just smoke |
| TR-5 | **"Start Translation" inline flow is broken (FE↔BE contract drift)** | ✅ FIXED 2026-05-30 | Was: `PUT /settings` 422 + `POST /jobs` 422 `TRANSL_NO_MODEL_CONFIGURED`, silent. Now: live smoke `PUT /settings` 200 + `POST /jobs` 201 + chapter "Running" via LM-Studio. | Fixed by T1 (A: BE atomic-COALESCE PATCH settings; B: FE partial PUT + error toast; C: per-job model override so the job is self-sufficient). See plan T1 + commit. |

### 1.2 Writing Assistant  *(largest gap)*

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| WA-1a | "Classic/AI" editor mode toggle | ✅ WORKS (my walkthrough misread) | `hooks/useEditorMode.ts` + `TiptapEditor` — mode drives mediaGuard (classic = text-only, media blocks locked, minimal slash menu; AI = full blocks + media + AI prompts). Designed in `design-drafts/screen-editor-modes.html`. | NOT a dead control — earlier "changes nothing" note was wrong (the diff is media/slash capability, not the toolbar). |
| WA-1b | In-editor "AI Chat" assistant panel | **ATTEMPT REJECTED → ARCH-1/2** | `EditorChatPanel.tsx` built + live-smoked (session-create + streaming worked), but **NOT committed**. PO 2026-05-30: it's a low-quality duplicate of the canonical Chat-page chat (which has voice mode + more) = architecture rot; and the RAG pipeline looped infinitely on "summarize this chapter". | Don't build a second chat. See plan **ARCH-1** (unify chat, embed the one canonical component) + **ARCH-2** (RAG pipeline consolidation / loop-guard). Editor AI tab stays "Coming soon" until that rework. |
| WA-2 | Standalone chat (`/chat`) | SHIPPED | `pages/ChatPage.tsx`, `services/chat-service/`. Live: conversation list + search render; existing convo from ~33d ago. | Works, but NOT integrated into the writing/editor flow. (Last used ~late-April — matches the pivot.) |
| WA-3 | Grammar checking | ✅ **graceful-degrade DONE (T9) 2026-05-30** | `components/editor/GrammarPlugin.ts` wired; LanguageTool in compose. Live 500 root-caused: the `languagetool` container **was not running** in the smoke; product code fine. | NOT product debt. **T9:** added a circuit breaker in `features/grammar/api.ts` — on network-error/5xx the breaker opens for a 60s cooldown so `checkGrammar` short-circuits to `[]` without hammering the dead service (kills the console-500 spam); 4xx stays closed (per-request); self-heals on success. 5 unit tests. |
| WA-4 | Continuation / assisted creation (roadmap Phase 4) | NOT-BUILT | No feature folder; roadmap §Phase 4 | Large epic — decision needed whether in MVP scope |

### 1.3 GUI Polish

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| UI-1 | Notifications center page | ✅ **DONE 2026-05-30** | `pages/NotificationsPage.tsx` (route wired, replaced PlaceholderPage), per `design-drafts/screen-notifications.html` §2. Backend unchanged (already complete). Extracted shared `features/notifications/{constants,components/NotificationItem}` + refactored `NotificationBell` to use them (no copy-paste drift) + added bell "View all" footer. Live: renders real notifications (200), filter tabs refetch, load-more, click→mark-read+navigate. 13 FE tests. /review-impl fixes folded in (see discussion log). |
| UI-2a | Profile "Wiki Contributions" tab | ✅ **DONE 2026-05-30 (FS, (a) full-social)** | Was NOT backend-ready (correction): wiki was per-book only, no cross-book by-user listing. Added BE `GET /v1/glossary/users/{id}/wiki-contributions` (optional auth; self sees all, others see published-in-public-wiki only via per-book projection) + FE `WikiTab` (replaces StubTab). Live: self=4 drafts, anon=0 (drafts correctly filtered). BE helper test (7 cases) + FE WikiTab (3) tests. **LOW (accepted):** N+1 projection per distinct book (bounded+cached); visibility filter after LIMIT → non-self may get short pages with many drafts + few public (no load-more yet). |
| UI-2b | Profile "Reviews" tab | ✅ **DROPPED 2026-05-30** | Was `ProfilePage.tsx` `<StubTab>` "Reviews". There is NO book-review/rating system (only wiki-suggestion review exists) and no design draft / product definition for it. | **Decision: drop, not defer.** Removed the tab + deleted the now-unused `StubTab.tsx` + cleaned dead i18n keys (`tabs.reviews`, `comingSoon` ×4 locales). No dead control. Re-add only if a rating/review system is ever specced (would need new backend). |
| UI-3a | Reader: auto-load next chapter | ✅ **DONE 2026-05-30 (was DRIFT, not missing)** | The feature was already built+working in `ReaderPage` (IntersectionObserver on chapter-end → 5s countdown → navigate next, reading `lw_reader_auto_next`). Only the `ThemeCustomizer` toggle was a dead "coming soon" disabled checkbox not wired to it. Fix: wired the toggle (props + setter + localStorage; cancels pending countdown on disable). 2 tests; tsc clean. |
| UI-3b | Reader: auto-scroll TTS | ✅ **DONE 2026-05-30 (re-classified: NOT deferred — feature exists)** | Correction: auto-scroll-during-TTS already works client-side (`useBlockScroll` + `autoScrollTTS`, toggled via TTSBar) — it is NOT the Voice-Pipeline backend. Its `ThemeCustomizer` toggle was the same dead "coming soon" drift; wired it (second control alongside the TTSBar one, same `lw_reader_tts_scroll`). |
| UI-4 | Frontend V2 rebuild Phase 3+ | PARTIAL | `99_FRONTEND_V2_REBUILD_PLAN.md` "Phase 3 PAUSED" (session 12) | frontend-v2 → frontend/ rename done; most pages built; audit remaining gaps |
| UI-5 | UI/UX consistency pass (Plan 97: unified DataTable, filters, pagination) | ⚠️ PARTIAL | `97_UI_UX_IMPROVEMENT_PLAN.md` (2026-03-28) | Completion % unknown — needs audit |

### 1.4 Ops / Release Readiness

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| OPS-1 | Cloud readiness tasks (CRA) | **TRACK 2** (backlog) | `CLOUD_READINESS_AUDIT.md` — ~8 CRA tasks open | **De-scoped 2026-05-30:** release target is local/self-host hobby, no paid infra / no platform company. Cloud is "maybe later" → keep in backlog so a future cloud move doesn't redo work, but NOT an active blocker. Most items (service discovery, RDS pooling, multi-region) are N/A locally. Already-done items (CRA-01/02 secrets) stay. |
| OPS-2 | Voice Pipeline V2 (43 tasks) | **TRACK 2** (backlog) | Referenced in `CLOUD_READINESS_AUDIT.md`; no spec doc found | Out of hobby-MVP scope; revisit only if pursued deliberately. |
| OPS-3 | Acceptance evidence packs (all 5 modules) | **DOWNGRADED** | Matrix "⚠️ Smoke only" across M01–M05 | Formal governance acceptance packs are overkill for a hobby release. Replace with **lightweight live functional verification** (does each flow actually work end-to-end on the local stack — like the T1 walkthrough that found TR-5). |

### 1.5 Cross-cutting (found during live walkthrough)

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| UI-6 | **i18n coverage incomplete / inconsistent** | 🔄 **IN PROGRESS — full i18n epic (W0 done)** | Live 2026-05-30: nav rendered in Japanese (メイン/ワークスペース/チャット…) while many strings stayed English. Root cause: `books.json` was en-only + ~500–700 hard-coded strings never wrapped in `t()`. | **PO decision: full i18n all 4 locales** (not lock-English). Spec: [`docs/specs/2026-05-30-i18n-full-coverage.md`](../specs/2026-05-30-i18n-full-coverage.md) (10 waves). **W0 done:** created `books.json` ×3 (vi/ja/zh-TW), fixed `common`(trash/voice)+`profile`(plural) drift, registered `books` in index.ts (the en-only bug), added `npm run i18n:check` parity guard. **W1 done:** extracted workspace + nav/sidebar + book-detail shell + full trash surface (~60 strings) into `books.detail.*`/`books.trash.*` + `common.nav`/`common.theme_name`, translated ×4, wired `t()` in BooksPage/BookDetailPage/TrashPage/Sidebar/FloatingTrashBar/TrashCard. Parity OK, tsc 0, 0 leftover hardcoded. Live per-locale sweep deferred to W9. **W2 done** (book-detail tab contents): W2a ChaptersTab/GlossaryTab/SharingTab; W2b-1 SettingsTab/TranslateModal; W2b-2 KindEditor/AttrEditorModal → `books.{chapters,glossary,sharing,settings,translate,kind_editor,attr_editor}.*` ×4 (~200 strings total). Note: `pages/book-tabs/EntityEditor.tsx` is **dead code** (never imported; superseded by `components/entity-editor/EntityEditorModal`) → skipped, candidate for deletion. Parity OK, tsc 0, 0 leftover per wave. Waves W3–W9 = editor/reader/chat/settings/glossary-components/tail + guard. |
| UI-7 | Book stats/view calls bypass gateway → CORS fail | ✅ **FIXED (F-3)** | Same root cause as the chat break — the `localhost:3000` hardcoded base. Resolved by the F-3 consolidation (all FE callers now use the shared `apiBase`, relative→proxy→gateway). |
| **F-3** | **Architecture rot: no single FE API base (8 divergent copies)** | ✅ **FIXED 2026-05-30** | `src/api.ts` already exported a correct shared `apiBase` (relative `''` default) for SSE/WS/upload callers, but **8 call-sites re-declared a local `base` defaulting to `http://localhost:3000`** — the gateway's *container-internal* port, unreachable from the browser → those features silently broke whenever `VITE_API_BASE` was unset. Also 4-way port-doc drift (CLAUDE.md/api.ts said `:3001`; real dev host `:3123`; container `:3000`). **Fix:** all 8 now import the shared `apiBase`; WS callers use `apiBase() \|\| window.location.origin`; port docs corrected (CLAUDE.md + api.ts); added a guard comment in `api.ts` against re-declaring a hardcoded base. This is the same class of defect that hid TR-5 — divergent paths that unit tests (which mock the api layer) never exercise. |

> **What actually works well (don't touch):** rich TipTap chapter editor (formatting, image/video/audio embed, word/char/paragraph counts, autosave, revision history); Reader (read-time estimate, theme customizer, TTS button, progress); Workspace book list + book-detail tabs; Translation Matrix + 13-language native-name dropdown + live LM-Studio BYOK model resolution; Chat shell. The product *shell* is solid — the debt is concentrated in the AI/translation *actions* and finishing polish.

---

## 2. Proposed Prioritization (DRAFT — to be decided together)

**Release target (decided 2026-05-30): local / self-host hobby; cloud "maybe later" (backlog).** So "done" = every advertised flow works end-to-end on the local Docker-Compose stack, with the **draft-design surface implemented or consciously deferred** (not "dead controls"). Cloud/scale/governance items move to Track 2.

> **Framing (PO 2026-05-30):** the "coming soon" / stub controls are NOT dead controls — they are part of the **draft design** (`design-drafts/screen-*.html`). The accurate lens is **missing / deferred / drift**, governed by CLAUDE.md "No Defer Drift" (every postponement is tracked with a target, nothing silently rots):
> - **Missing** — designed, never implemented.
> - **Deferred** — consciously postponed, tracked with a target/track.
> - **Drift** — implemented but diverged from the design (or from the rest of the app).

| Priority | Items | Rationale |
|---|---|---|
| **P0 — functional: does it actually work?** | ✅ TR-5 + full live sweep done (F-1/F-3/F-4 fixed). | TR-5 proved a mock-green "Closed (smoke)" module can be broken live. |
| **P1 — close the designed surface (missing/deferred/drift)** | Backend-ready **missing** (cheap wiring): UI-1 Notifications page (`screen-notifications.html`), UI-2a Profile Wiki, WA-1b in-editor AI Chat panel (`screen-editor-workbench/splitview.html`). **Deferred** (track, don't build now): UI-3b reader TTS → Voice Pipeline; WA-4 continuation. **Decide**: UI-2b Profile "Reviews" (no backend — define or drop), UI-3a auto-load-next (cheap FE). | These are design-spec'd features, not dead buttons. Implement the backend-ready ones, explicitly defer the rest with a target so nothing silently rots. |
| **P2 — polish/drift** | UI-6 (i18n drift — partial locale), UI-5 (Plan 97 DataTable/filters), TR-3 (verify Plan 72 drift) | Improves feel; not blocking personal use. |
| **Track 2 — backlog (not now)** | OPS-1 (cloud readiness), OPS-2 (voice), WA-4 (continuation), capability_flags schema cleanup (F-4 follow-up) | Re-scoped: no paid infra / no platform company. Tracked so a future move doesn't redo work. |

**Design-intent source of truth:** `design-drafts/screen-*.html` (e.g. `screen-notifications.html`, `screen-editor-modes/workbench/splitview.html`, `screen-chat-enhanced.html`). Classify each P1 item against its draft screen before implementing or deferring.

---

## 3. Discussion Log

> Decisions and scope cuts get recorded here as we work through each item. (Empty — discussion starts next.)

| Date | Item | Decision | By |
|---|---|---|---|
| 2026-05-30 | First task | Start with **T1** (translation fix) — highest ROI, root-caused. | PO |
| 2026-05-30 | T1 BE settings semantics | PATCH-semantics (keep existing on omit), implemented **atomically** via single COALESCE upsert (no read-modify-write race — multi-device safe). | PO + Lead |
| 2026-05-30 | T1 scope | Pull **Fix-C (per-job model override)** into T1 instead of deferring — "avoid debt-begets-debt". Job no longer depends on a settings write. | PO |
| 2026-05-30 | T1 resolver | Consolidate the duplicated effective-settings fallback into one `resolve_effective_settings` (used by GET book-settings + create-job). PUT uses the atomic upsert directly. | PO (option a) |
| 2026-05-30 | T1 /review-impl | All findings fixed: MED-1 (atomic upsert), MED-2 (verified provider-registry scopes model_ref by user_id — no IDOR), LOW-1 (model_source⇒model_ref validator), LOW-2 (documented), LOW-3 + COSMETIC (test hardening). | Lead |
| 2026-05-30 | Deferred from T1 | `put_preferences` could carry the same partial-update sharp edge — not exercised by current UI; left strict. Logged, not actioned. | Lead |
| 2026-05-30 | **Release target** | Local / self-host hobby; cloud "maybe later". No paid infra, no platform company. → OPS-1 (cloud-readiness) + OPS-2 (voice) move to **Track 2 backlog**; formal acceptance packs (OPS-3) downgraded to lightweight live functional verification. "Done" = every flow works locally + no dead controls + polish. | PO |
| 2026-05-30 | Live sweep + **F-3** | Live functional sweep found F-1 (extraction no-op) + F-2/F-3 (FE API base rot). Prioritized **F-3 first** (architecture rot — root cause of F-2 + UI-7 + the same defect-class as TR-5). Fixed by consolidating 8 divergent FE base decls onto the shared `apiBase`. F-1 still open. | PO + Lead |
| 2026-05-30 | Pre-existing test debt (logged, not fixed) | `useEditorPanels.test.ts` has 3 failing tests; vitest is misconfigured to collect Playwright e2e specs (`tests/e2e/specs/*`) → 4 suite-collection failures. Both confirmed pre-existing via git-stash; separate test-infra task. | Lead |
| 2026-05-30 | **UI-2a Profile Wiki — scope correction** | Re-classified mid-CLARIFY: NOT backend-ready (wiki was per-book only). PO chose **(a) full-social** (cross-book + respect book wiki-visibility). Shipped: new glossary endpoint (optional-auth, pure `wikiContributionVisible` helper for self/published+public gate) + FE WikiTab. Live-verified self vs anonymous visibility. | PO + Lead |
| 2026-05-30 | **Notifications i18n** (post-UI-1, PO-reported: content was English-only) | Content (title/body) was server-rendered English. Approach (A) client-localizes from machine-readable metadata, done in 2 chunks. **Chunk 1 (FE-only):** `NotificationItem` composes the title from `metadata.operation`+`status` (already emitted by the consumer) via `event.*` i18n keys; verified live (JP: エンティティ抽出完了 / チャット完了…). **Chunk 2 (BE+FE):** the interpolated-title emitters — translation `chapter_worker` (completed/partial/failed) + auth follow — now also emit `metadata.i18n_key` + `i18n_params`; FE prefers the key (`notif.*`). English `title` kept as fallback. Both ends unit-tested (BE +3, FE i18n_key path from Chunk 1); cross-service e2e (fresh job → localized notification) verifiable on demand. **Note:** old pre-change rows have no key → still English until re-emitted (acceptable). | PO + Lead |
| 2026-05-30 | **UI-1 Notifications page** | Implemented FS-correctly (backend was already complete → FE page only, per CLARIFY). MVC: `useNotificationList` hook + presentational `NotificationItem` + page. Extracted shared constants/item and refactored the bell onto them (avoid the F-3 copy-paste drift) + added bell "View all". **/review-impl fixes (all applied):** MED-1 bell unread badge re-syncs on route change (was drift vs page mark-read); MED-2 category-switch stale-response guard (reqId ref); LOW-1 added `NotificationBell` test; LOW-2 dedupe on load-more append; LOW-3 Mark-all visibility from authoritative unread-count (not loaded items); LOW-4 link-follow restricted to http(s)/in-app-path. **Deferred:** §3 Email Preferences = separate item (new table + Settings UI + emitter wiring); a shared notifications store (vs route-change refetch) is a possible future cleanup. | PO + Lead |
| 2026-05-30 | **WA-1b rejected → ARCH-1/2** | In-editor chat attempt (`EditorChatPanel`) built + live-smoked but rejected by PO: it duplicates the higher-quality canonical Chat-page chat (voice mode + more) = architecture rot, and the RAG pipeline looped infinitely on "summarize". Recorded **ARCH-1** (unify chat, embed the one component) + **ARCH-2** (consolidate the fragmented RAG pipelines, add loop-guards; design-only first) in the plan. EditorChatPanel left uncommitted as reference; editor AI tab stays "Coming soon". `0859226b`. | PO |
| 2026-05-30 | **Quick wins: UI-2b + T9** (1 commit) | **UI-2b** drop Profile Reviews tab (no backend / no product def) — removed tab + deleted `StubTab.tsx` + cleaned dead i18n keys ×4. **T9** grammar graceful-degrade — circuit breaker in `features/grammar/api.ts` (network-err/5xx → 60s cooldown short-circuit → kills console-500 spam; 4xx stays closed; self-heals). Phase-7 self-review tightened the breaker to 5xx-only. tsc 0, 5 grammar tests, 4 locales parse OK, 0 dangling refs. | PO + Lead |
| 2026-05-30 | **Reframe P1** | The "coming soon"/stub controls are NOT dead controls — they're part of the **draft design** (`design-drafts/screen-*.html`). Correct lens = **missing / deferred / drift** (CLAUDE.md "No Defer Drift"). Reclassified: UI-1/UI-2a/WA-1b = MISSING (backend-ready, cheap wiring); UI-3a = MISSING (FE-only); UI-3b/WA-4 = DEFERRED (tracked); UI-2b Reviews = DECIDE (no backend). Corrected WA-1a (editor mode toggle WORKS — earlier walkthrough misread). | PO |

## Live functional sweep (2026-05-30) — does each flow actually work?

Exercised on the running local stack (writer→reader), using network 4xx/5xx + actual effect as the signal (the method that caught TR-5).

| Flow | Result | Evidence |
|---|---|---|
| Translation (Start Translation) | ✅ works | T1 — PUT 200 + POST /jobs 201 + chapter Running |
| Wiki generate-from-glossary | ✅ works | POST `/v1/glossary/.../wiki/generate` → 200 |
| Chat: create session | ✅ works | POST `/v1/chat/sessions` → 201 (relative path) |
| **Glossary extraction (per-chapter)** | ✅ **FIXED (F-1)** | Was: POST with `chapter_ids: []` → 0-chapter no-op. Root cause: the always-mounted `ExtractionWizard`'s `useState` initializer seeded `chapterIds` once (closed → preselected undefined → `[]`) and ignored the later prop. Fix: `key={extractChapterId}` on the wizard in `ChaptersTab.tsx` → remounts per chapter so the initializer re-seeds. Live: Confirm now shows "1 chapter / 1 LLM call"; POST body `chapter_ids:["…57d2"]` → 202. +regression test `useExtractionState.test.ts`. |
| **Chat: send message (+ 7 other features)** | ✅ **FIXED (F-3)** | Was: POST to **`http://localhost:3000`** → `net::ERR_FAILED`. Now: POST `localhost:5174/v1/chat/.../messages` → **200** (relative→proxy→gateway), 0 console errors, message persisted + stream connected. Fixed by F-3 consolidation below. |
| **Knowledge graph build** | ✅ **FIXED (F-4)** | Was: LLM picker `?capability=chat` → `{"items":[]}` → Build button disabled. **Real root cause (deeper than first thought):** `capability_flags` exists in **two schemas** in the data — canonical `{"chat":true}` vs legacy `{"_capability":"chat"}` (+ null/`{}`) — and the `@> {"chat":true}` filter only matched the canonical one. The test model is `{"_capability":"chat"}` → hidden. Fix (BE, server.go `listUserModels`): `capability=chat` now matches **both** schemas OR undeclared `{}` (undeclared → chat-capable by default; most BYOK/local models never self-declare and there's no UI to set flags). Non-chat caps stay strict. Live BE smoke: `?capability=chat` now returns the `{"_capability":"chat"}` model (was empty). +DB-integration test `capability_filter_integration_test.go`. |
| Reading-view + stats tracker | ✅ FIXED (F-3) | `POST /v1/books/{id}/view` → 204, `GET .../stats` → 200 (was `:3000` ERR_FAILED). 0 console errors on book detail. |
| Sharing (set visibility) | ✅ works | `PATCH /v1/sharing/books/{id}` → 200 (Unlisted), 0 errors. |

**Sweep tasks all resolved:** F-1 ✅, F-2/UI-7 ✅ (via F-3), F-3 ✅, F-4 ✅.

**Deferred follow-up (Track 2, from F-4):** `capability_flags` data-schema rot — two coexisting shapes (`{"chat":true}` vs `{"_capability":"chat"}`) plus null/`{}`. The read path now tolerates all, but (a) the write path that emits the legacy `{"_capability":"chat"}` shape should be found and normalized, and (b) a one-off data migration could canonicalize existing rows. Also: no FE UI exists to set/edit capability flags. Low urgency (read-side fix unblocks usage); needs the DB-migration guardrail when done.

## Recently completed

- **T1 — translation "Start Translation" flow (TR-5)** — shipped on branch `mvp-release-debt`. BE: `effective_settings.py` (new), `models.py`, `routers/settings.py`, `routers/jobs.py`. FE: `features/translation/api.ts`, `pages/book-tabs/TranslateModal.tsx`. Tests: +5 (BE 3, FE 2); full BE suite 297 pass (5 pre-existing `test_chapter_worker` failures unrelated — confirmed via git-stash). Live cross-service smoke green.
