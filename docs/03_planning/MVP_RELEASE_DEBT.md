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
| WA-1 | In-editor AI assist ("AI Chat" panel + "Classic/AI" editor mode) | STUB | `pages/ChapterEditorPage.tsx:698-705` — AI Chat tab disabled "Coming soon". Live 2026-05-30: toggling editor mode **Classic↔AI changes nothing visible** (no AI affordance appears). | Dead surface in product UI. The whole in-editor AI layer is hollow. |
| WA-2 | Standalone chat (`/chat`) | SHIPPED | `pages/ChatPage.tsx`, `services/chat-service/`. Live: conversation list + search render; existing convo from ~33d ago. | Works, but NOT integrated into the writing/editor flow. (Last used ~late-April — matches the pivot.) |
| WA-3 | Grammar checking | LIKELY-OK (env) | `components/editor/GrammarPlugin.ts` wired; LanguageTool in compose. Live 500 root-caused: the `languagetool` container **was not running** in the smoke (not started); product code is fine. | NOT product debt. Optional: add graceful-degrade/health surface so a missing LT service fails quietly instead of console-500 spam. |
| WA-4 | Continuation / assisted creation (roadmap Phase 4) | NOT-BUILT | No feature folder; roadmap §Phase 4 | Large epic — decision needed whether in MVP scope |

### 1.3 GUI Polish

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| UI-1 | Notifications center page | STUB | `App.tsx:136` — `PlaceholderPage` "coming in P2-09" | Backend `notification-service` + `NotificationBell` exist; only the center page is missing |
| UI-2 | Profile tabs: Wiki, Reviews | STUB | `pages/ProfilePage.tsx:172-173` — `<StubTab>` | |
| UI-3 | Reader: auto-load next chapter, auto-scroll TTS | STUB | `components/reader/ThemeCustomizer.tsx:157-161` — "coming soon", disabled | TTS overlaps with Voice Pipeline (see OPS-2) |
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
| UI-6 | **i18n coverage incomplete / inconsistent** | BROKEN | Live 2026-05-30: nav rendered in Japanese (メイン/ワークスペース/チャット…) while many strings stayed English — sidebar "Trash", breadcrumb "My Books", book tabs (Chapters/Translation/Glossary/Wiki/Sharing/Settings). | Mixed-language UI looks unfinished. Either finish locale coverage or lock default locale for V1. |
| UI-7 | Book stats/view calls bypass gateway → CORS fail | ✅ **FIXED (F-3)** | Same root cause as the chat break — the `localhost:3000` hardcoded base. Resolved by the F-3 consolidation (all FE callers now use the shared `apiBase`, relative→proxy→gateway). |
| **F-3** | **Architecture rot: no single FE API base (8 divergent copies)** | ✅ **FIXED 2026-05-30** | `src/api.ts` already exported a correct shared `apiBase` (relative `''` default) for SSE/WS/upload callers, but **8 call-sites re-declared a local `base` defaulting to `http://localhost:3000`** — the gateway's *container-internal* port, unreachable from the browser → those features silently broke whenever `VITE_API_BASE` was unset. Also 4-way port-doc drift (CLAUDE.md/api.ts said `:3001`; real dev host `:3123`; container `:3000`). **Fix:** all 8 now import the shared `apiBase`; WS callers use `apiBase() \|\| window.location.origin`; port docs corrected (CLAUDE.md + api.ts); added a guard comment in `api.ts` against re-declaring a hardcoded base. This is the same class of defect that hid TR-5 — divergent paths that unit tests (which mock the api layer) never exercise. |

> **What actually works well (don't touch):** rich TipTap chapter editor (formatting, image/video/audio embed, word/char/paragraph counts, autosave, revision history); Reader (read-time estimate, theme customizer, TTS button, progress); Workspace book list + book-detail tabs; Translation Matrix + 13-language native-name dropdown + live LM-Studio BYOK model resolution; Chat shell. The product *shell* is solid — the debt is concentrated in the AI/translation *actions* and finishing polish.

---

## 2. Proposed Prioritization (DRAFT — to be decided together)

**Release target (decided 2026-05-30): local / self-host hobby; cloud "maybe later" (backlog).** So "done" = every advertised flow works end-to-end on the local Docker-Compose stack, with no dead/coming-soon controls and reasonable polish. Cloud/scale/governance items move to Track 2.

| Priority | Items | Rationale |
|---|---|---|
| **P0 — functional: does it actually work?** | ✅ TR-5 (done). **Live functional sweep** of the other "Closed (smoke)" flows (glossary, wiki, chat, knowledge, extraction, reading/sharing) to find more TR-5-style latent breakages. | TR-5 proved a mock-green "Closed (smoke)" module can be broken live. Honest release needs each core flow exercised on the real stack. |
| **P1 — no dead controls** | WA-1 (in-editor AI: hide or wire), UI-1 (Notifications page), UI-2 (Profile stubs), UI-3 (reader coming-soon) | For a hobby release, simplest is hide/remove dead "coming soon" controls so nothing looks broken. |
| **P2 — polish** | UI-6 (i18n consistency), UI-5 (Plan 97 DataTable/filters), TR-3 (verify Plan 72) | Improves feel; not blocking personal use. |
| **Track 2 — backlog (not now)** | OPS-1 (cloud readiness), OPS-2 (voice), WA-4 (continuation) | Re-scoped: no paid infra / no platform company. Keep so a future cloud move doesn't redo work. |

**Key open decision:** Is **Writing Assistant (WA-1/WA-4)** in the MVP release?
- If **yes** → it's a multi-week epic of its own.
- If **no** → just remove the dead "AI Chat — coming soon" tab so we don't ship a dead button; MVP then reduces to *verify/close already-coded work + finish cloud-readiness*.

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

## Live functional sweep (2026-05-30) — does each flow actually work?

Exercised on the running local stack (writer→reader), using network 4xx/5xx + actual effect as the signal (the method that caught TR-5).

| Flow | Result | Evidence |
|---|---|---|
| Translation (Start Translation) | ✅ works | T1 — PUT 200 + POST /jobs 201 + chapter Running |
| Wiki generate-from-glossary | ✅ works | POST `/v1/glossary/.../wiki/generate` → 200 |
| Chat: create session | ✅ works | POST `/v1/chat/sessions` → 201 (relative path) |
| **Glossary extraction (per-chapter)** | ✅ **FIXED (F-1)** | Was: POST with `chapter_ids: []` → 0-chapter no-op. Root cause: the always-mounted `ExtractionWizard`'s `useState` initializer seeded `chapterIds` once (closed → preselected undefined → `[]`) and ignored the later prop. Fix: `key={extractChapterId}` on the wizard in `ChaptersTab.tsx` → remounts per chapter so the initializer re-seeds. Live: Confirm now shows "1 chapter / 1 LLM call"; POST body `chapter_ids:["…57d2"]` → 202. +regression test `useExtractionState.test.ts`. |
| **Chat: send message (+ 7 other features)** | ✅ **FIXED (F-3)** | Was: POST to **`http://localhost:3000`** → `net::ERR_FAILED`. Now: POST `localhost:5174/v1/chat/.../messages` → **200** (relative→proxy→gateway), 0 console errors, message persisted + stream connected. Fixed by F-3 consolidation below. |
| **Knowledge graph build** | ⚠️ **F-4 (MED) blocked** | Build dialog's LLM picker queries `GET /v1/model-registry/user-models?capability=chat` → `{"items":[]}` and embedding likewise → "グラフを構築" button permanently **disabled**. Same Qwen3 model works in chat/translation/extraction because THOSE call the same endpoint **without** the `capability` filter. Root cause: the model has no `capability_flags` set, and only Knowledge hard-gates on it → inconsistent capability enforcement + a misleading "no chat-capable models, add one" empty-state for a model that demonstrably chats. Fix is a decision: (a) populate `capability_flags` on model registration so all features agree, or (b) relax Knowledge's gate to match the others. |
| Reading-view + stats tracker | ✅ FIXED (F-3) | `POST /v1/books/{id}/view` → 204, `GET .../stats` → 200 (was `:3000` ERR_FAILED). 0 console errors on book detail. |
| Sharing (set visibility) | ✅ works | `PATCH /v1/sharing/books/{id}` → 200 (Unlisted), 0 errors. |

**Open tasks from sweep:** **F-4** (Knowledge build blocked by inconsistent capability gating) — needs a decision. F-1 (extraction no-op) ✅ fixed; F-2/UI-7 resolved by F-3.

## Recently completed

- **T1 — translation "Start Translation" flow (TR-5)** — shipped on branch `mvp-release-debt`. BE: `effective_settings.py` (new), `models.py`, `routers/settings.py`, `routers/jobs.py`. FE: `features/translation/api.ts`, `pages/book-tabs/TranslateModal.tsx`. Tests: +5 (BE 3, FE 2); full BE suite 297 pass (5 pre-existing `test_chapter_worker` failures unrelated — confirmed via git-stash). Live cross-service smoke green.
