# MVP Release Improvement Plan

## Document Metadata
- Document ID: LW-PLAN-MVP-RELEASE
- Version: 0.1.0 (DRAFT — task menu for selection)
- Status: Draft
- Owner: Full-Stack Lead
- Created: 2026-05-30
- Branch: `mvp-release-debt`
- Companion: [`docs/03_planning/MVP_RELEASE_DEBT.md`](../03_planning/MVP_RELEASE_DEBT.md) (inventory + live findings)
- Summary: A menu of scoped, root-caused work items to close MVP debt before release. Each item carries root cause, fix approach, size, files, acceptance criteria, and risk so we can pick by priority and implement one at a time under the 12-phase workflow.

> **How to use:** read items top-to-bottom; pick the next task; I implement it through CLARIFY→…→COMMIT. Sizes use the repo classifier (XS/S/M/L). Anything ≥L gets its own spec file before BUILD.

---

## Wave 0 — Functional blockers (make the core flow actually work)

### T1 — Fix "Start Translation" flow (TR-5)  · size **S–M** · **highest ROI**
**Root cause (confirmed in code):**
- [`TranslateModal.tsx:79-91`](../../frontend/src/pages/book-tabs/TranslateModal.tsx#L79) builds a partial payload `{target_language, model_ref, model_source}` and `PUT`s it to `/settings`.
- BE `PUT /v1/translation/books/{id}/settings` ([`services/translation-service/app/routers/settings.py`](../../services/translation-service/app/routers/settings.py)) requires `system_prompt` + `user_prompt_tpl` (no defaults on the request model) → **422**.
- The FE `catch {}` swallows the 422 silently ("best-effort"), so the model is never persisted → `createJob` (sends only `chapter_ids`) → **422 `TRANSL_NO_MODEL_CONFIGURED`**.

**Fix approach (pick one or combine):**
- **A (BE, recommended, lowest-risk):** make `system_prompt` / `user_prompt_tpl` optional in the PUT settings request model; default to `DEFAULT_SYSTEM_PROMPT` / `DEFAULT_USER_PROMPT_TPL` when absent (mirrors how `compact_*` already default to `''`). Makes partial settings updates valid.
- **B (FE):** stop swallowing the error — surface a toast on settings-save failure; and merge loaded `settings` into the payload so a full object is sent.
- **C (design cleanup — INCLUDED per PO 2026-05-30 "avoid debt-begets-debt"):** `createJob` accepts per-job `{target_language, model_source, model_ref}` overrides so a one-off translation doesn't depend on persisting book settings at all (removes the implicit-state coupling). BE overlays overrides onto resolved effective settings before the `model_ref` check.

**Decision:** do **A + B + C** together (PO pulled C into scope).

**Files:** `services/translation-service/app/{models.py, routers/settings.py, routers/jobs.py}` (BE), `frontend/src/{pages/book-tabs/TranslateModal.tsx, features/translation/api.ts}` (FE) + tests. **Acceptance:** select language+model → Start Translation → job created (no 422) even with NO persisted settings; a real chapter translates via LM-Studio BYOK (live smoke); custom prompts never clobbered; settings-save failure shows a toast (but does not block translation). **Risk:** low–med; touches 2 services → live cross-service smoke required.

### T2 — Remaining cloud-readiness tasks (OPS-1)  · size **M–L** · **deploy blocker**
**Root cause:** [`CLOUD_READINESS_AUDIT.md`](../03_planning/CLOUD_READINESS_AUDIT.md) lists 20 CRA tasks; ~12 marked DONE → ~8 open. **First step:** read the audit, enumerate the exact open CRA IDs, classify each (some may already be done since session 32). **Files:** various services + infra. **Acceptance:** every open CRA item either DONE or consciously deferred with a row. **Risk:** medium; may include config/secrets/S3 URL items. *(This is itself a planning sub-task — T2a: produce the precise open-list before estimating.)*

---

## Wave 1 — Close what's already coded (verify + sign off)

### T3 — Verify & close Translation UX vs Plan 72 (TR-3)  · size **S**
Line-by-line check of [Plan 72](../03_planning/72_TRANSLATION_UX_REDESIGN_PLAN.md) against shipped code (coverage matrix, version management, language dropdown, split-compare, block-aligned review). Mark plan DONE or list the precise deltas. **Files:** docs + spot FE checks. **Acceptance:** Plan 72 status flipped to DONE or a delta list produced. **Risk:** none (audit).

### T4 — M04 acceptance evidence pack (TR-4)  · size **S–M**
Run the M04 acceptance test plan ([`59_MODULE04_ACCEPTANCE_TEST_PLAN.md`](../03_planning/59_MODULE04_ACCEPTANCE_TEST_PLAN.md)) end-to-end on the live stack; capture evidence. Depends on **T1** (translation must work first). **Acceptance:** evidence pack committed; Module Status Matrix M04 → "Closed (acceptance)". **Risk:** low.

---

## Wave 2 — Visible polish (remove the "unfinished" smell)

### T5 — Notifications center page (UI-1)  · size **S–M**
Replace `App.tsx:136` PlaceholderPage with a real page. Backend `notification-service` + `NotificationBell` already exist (badge shows live count). **Files:** new `NotificationsPage` + route + api wiring. **Acceptance:** `/notifications` lists notifications, mark-read works. **Risk:** low.

### T6 — i18n coverage / locale consistency (UI-6)  · size **S–M**
**Observed:** nav rendered Japanese while "Trash", "My Books", book tabs stayed English → mixed-language UI. **First step:** decide policy — (a) lock default locale to English for V1 and hide the unfinished locales, or (b) finish missing keys for the supported set. **Files:** `frontend/src/i18n/locales/*`, components using hard-coded strings. **Acceptance:** no mixed-language screen on the core flows for the chosen locale(s). **Risk:** low–medium (depends on policy).

### (T1 Fix-C absorbed) — per-job model override
*(Previously listed as a deferred follow-up; pulled into T1 on 2026-05-30 so the job no longer depends on implicit persisted settings.)*

### T7 — Decide & resolve in-editor AI surface (WA-1)  · size **S** (remove) or **L+** (build)
The "Classic/AI" mode toggle is a visual no-op and the "AI Chat" panel is a disabled "coming soon" tab.
- **Option Remove (S):** hide the AI-mode toggle + AI Chat tab + the editor Translate button until built — no dead controls at release.
- **Option Build-lite (L):** wire the existing `/chat` (chat-service) into the editor side-panel as a context-aware assistant.
- **Option Build-full (XL):** dedicated continuation/co-writing (WA-4 / roadmap Phase 4).

**Decision needed from PO** before this becomes a task. **Acceptance:** no disabled/no-op AI controls visible at release (whichever option). **Risk:** Remove = low; Build = high.

### T8 — Profile stub tabs (UI-2)  · size **S**
`ProfilePage.tsx:172-173` renders `<StubTab>` for Wiki + Reviews. Either implement or hide the tabs for V1. **Risk:** low.

### T9 — Graceful-degrade for optional services (WA-3 follow-up + UI-7)  · size **XS–S**
- Make grammar (LanguageTool) failures degrade quietly instead of console-500 spam when the LT service is absent.
- Verify book `/stats` + `/view` route through the gateway in prod (the live CORS-to-:3000 was a dev-port artifact — confirm config). **Risk:** low.

---

## Wave 3 — Explicitly deferred (NOT in MVP release)

| Item | Why deferred |
|---|---|
| WA-4 — continuation / assisted creation (roadmap Phase 4) | Multi-week epic; out of MVP scope unless PO says otherwise |
| OPS-2 — Voice Pipeline V2 (43 tasks) | No spec doc found; confirm scope separately |
| UI-3 — reader auto-load next / auto-scroll TTS | Nice-to-have; overlaps Voice Pipeline |
| UI-5 — full Plan 97 UI/UX consistency pass | Broad polish; do opportunistically, not a release gate |

---

## Suggested order (for discussion)

1. **T1** (translation fix) — unblocks the core value + T4.
2. **T2a** (enumerate open cloud-readiness) — sizes the deploy blocker.
3. **T3 / T4** (close translator + acceptance).
4. **T5 / T6 / T8 / T9** (polish, parallelizable, low-risk).
5. **T7** — after PO decides the AI-surface direction.
6. Wave 3 — schedule post-V1.

> Decisions captured here flow back into the Discussion Log of `MVP_RELEASE_DEBT.md`.
