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
| OPS-1 | Cloud readiness tasks (CRA) | PARTIAL | `CLOUD_READINESS_AUDIT.md` — ~12 of 20 CRA tasks marked DONE | **~8 remaining** = real deploy blocker for AWS/multi-device |
| OPS-2 | Voice Pipeline V2 (43 tasks) | NOT-BUILT | Referenced in `CLOUD_READINESS_AUDIT.md` as "waiting"; **no spec doc found** in planning/plans/specs | Confirm whether in MVP scope at all |
| OPS-3 | Acceptance evidence packs (all 5 modules) | NOT-BUILT | Matrix "⚠️ Smoke only" across M01–M05 | |

### 1.5 Cross-cutting (found during live walkthrough)

| ID | Item | State | Evidence | Notes |
|---|---|---|---|---|
| UI-6 | **i18n coverage incomplete / inconsistent** | BROKEN | Live 2026-05-30: nav rendered in Japanese (メイン/ワークスペース/チャット…) while many strings stayed English — sidebar "Trash", breadcrumb "My Books", book tabs (Chapters/Translation/Glossary/Wiki/Sharing/Settings). | Mixed-language UI looks unfinished. Either finish locale coverage or lock default locale for V1. |
| UI-7 | Book stats/view calls bypass gateway → CORS fail | ⚠️ ENV? | Live: `GET :3000/v1/books/{id}/stats` + `/view` blocked by CORS (6 console errors on book detail). | Likely dev-port artifact (Vite on 5174), BUT confirms `/stats` + `/view` hit `:3000` directly. Verify prod routes these through the gateway (gateway invariant). |

> **What actually works well (don't touch):** rich TipTap chapter editor (formatting, image/video/audio embed, word/char/paragraph counts, autosave, revision history); Reader (read-time estimate, theme customizer, TTS button, progress); Workspace book list + book-detail tabs; Translation Matrix + 13-language native-name dropdown + live LM-Studio BYOK model resolution; Chat shell. The product *shell* is solid — the debt is concentrated in the AI/translation *actions* and finishing polish.

---

## 2. Proposed Prioritization (DRAFT — to be decided together)

| Priority | Items | Rationale |
|---|---|---|
| **P0 — functional blocker** | **TR-5 (translation contract drift — core flow is dead)**, WA-3 (grammar 500), OPS-1 (remaining cloud-readiness) | Live walkthrough proved the headline "translate" action fails silently. Translation is the product's primary value — this is the #1 fix. Grammar 500 is the other live runtime break. |
| **P0 — close what's coded** | TR-3/TR-4 verify+close, M04 acceptance | Translator UX is mostly built; verify against Plan 72 and produce acceptance evidence. |
| **P1 — visible polish** | UI-1, UI-2 (remove/complete stubs), UI-6 (i18n), WA-1 decision | Dead buttons, stub tabs, and mixed-language UI read as "unfinished product". |
| **P2 — cut from MVP** | WA-4 (continuation), OPS-2 (voice), UI-3 (TTS/auto-load), UI-5 (full Plan 97) | Too large for "complete MVP to release"; defer post-V1. |

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

## Recently completed

- **T1 — translation "Start Translation" flow (TR-5)** — shipped on branch `mvp-release-debt`. BE: `effective_settings.py` (new), `models.py`, `routers/settings.py`, `routers/jobs.py`. FE: `features/translation/api.ts`, `pages/book-tabs/TranslateModal.tsx`. Tests: +5 (BE 3, FE 2); full BE suite 297 pass (5 pre-existing `test_chapter_worker` failures unrelated — confirmed via git-stash). Live cross-service smoke green.
