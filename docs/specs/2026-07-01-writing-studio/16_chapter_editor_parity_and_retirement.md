# 16 · Chapter Editor Parity & Retirement (COHERENCE)

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: 📐 specced 2026-07-04 (design only, no build this pass — user-scoped as SPEC+PLAN only).
> Origin: the "Cursor-for-novels" missing-pieces register, item #1 COHERENCE (memory `writing-studio-fragmented-not-underbuilt`) — the platform runs **two live, uncoordinated chapter-editing surfaces** and doesn't feel like one product.
> Builds on [#04](04_manuscript_editor.md) (manuscript hoist — several of its own "build notes" are still open and fold into this plan), [#08](08_studio_state_architecture.md) §"Migration: editorBridge → bus + reconciler" (the target architecture for the write-back fix was already decided there, just not built), [#09](09_agent_gui_reconciliation.md) (Lane C `applyProposedEdit`, G7 dirty-guard).

## Problem

Two routes both do "edit a chapter" and neither knows the other exists:

| Route | Page | How users reach it |
|---|---|---|
| `/books/:bookId/chapters/:chapterId/edit` | `ChapterEditorPage.tsx` (legacy) | **Every** chapter-row click and the pencil icon in `ChaptersTab.tsx` — the default, most-used path |
| `/books/:bookId/studio` | `WritingStudioPage.tsx` (Studio v2) | One promoted header CTA button on the book detail page |

A new user who clicks a chapter (the natural action) never sees Studio. A user who clicks "Studio" gets a materially different, less-capable chapter-editing experience for anything beyond drafting prose + basic AI co-writing. This is not a cosmetic gap — a full capability audit (2026-07-04) found **15 legacy-only capabilities with no Studio equivalent**, several of them data-safety features (Checkpoints, Revision History, Publish Gate).

**Decision (user-approved 2026-07-04, CLARIFY):** retire `ChapterEditorPage` — Studio becomes the **sole** chapter-editing surface once parity is reached. This spec is the parity-then-retirement roadmap. Per this track's own build-while-plan convention (see [`00_OVERVIEW.md`](00_OVERVIEW.md)), each phase below gets fleshed out into its own detailed spec **when that phase starts** — this document locks the decisions, the phase order, and the two prerequisite architecture fixes that block everything else.

## Capability audit summary (full detail: the 2026-07-04 audit findings, not duplicated here)

Legacy-only capabilities with no Studio equivalent, grouped by what they need architecturally:

| Group | Capabilities | Tier-4 home needed? |
|---|---|---|
| **Data-safety** (Phase 1) | Checkpoints (`useTurnCheckpoints`), Revision History + restore, Publish Gate (`useChapterPublishGate` + canon-contradiction/scene-completeness checks) | Yes — chapter-scoped mutable state, currently homeless in the 5-tier model |
| **Editor-craft UX** (Phase 2) | Grammar check toggle, Glossary inline decoration + `[[` autocomplete, Mention heatmap, AI-provenance tracking (unreviewed-span marks), Selection Toolbar + Inline AI layer, Focus/typewriter mode, Auto-save timer, Progress-reporting to composition SSOT, Original-source (untranslated) viewer tab, Image/video upload context + version history, Popout-insert-relay | Grammar/glossary/heatmap/provenance/focus = Tier-1 panel-local (pure editor decoration, no cross-panel need); upload-context + progress-reporting = Tier-4 side-effects of the existing `ManuscriptUnitProvider.save()` path; original-source viewer = a new thin read-only panel, no hoist |
| **Translate workmode** (Phase 3) | Full Translate mode: versions/compare/set-active/jobs (`ChapterTranslationsPanel`) | Large, standalone — already an unscoped future row in `00_OVERVIEW.md` ("Translation · Reader/Compare"). Gets its own spec when Phase 3 starts, per track convention. |
| **Structural** (Phase 4 — gates retirement) | Route unification, mobile shell, `ChapterEditorPage` deletion | See M6/M9 below |

Studio-only capabilities with no legacy equivalent (keep, no action needed): `SceneRail`, `ManuscriptNavigator` tree, `StudioEffectReconciler` (Lane B), Studio UI-intent tools, "Open as JSON".

## Prerequisite architecture fixes (block Phase 1 — do these first)

These aren't new capabilities; they're compliance debt in code that **already shipped** (including today's `fb98f161f` APPLY-DIFF fix), flagged by the audit as landmines that would get worse the more capability we pile onto the current wiring.

| # | Fix | Why it blocks Phase 1 |
|---|---|---|
| **P1** | **Lane-C compliance** — Studio's `EditorPanel`/`ComposePanel` stop using the global `editorBridge` singleton (`registerEditorTarget`/`getEditorTarget`) for `propose_edit` Apply. Add `applyProposedEdit(diff)` as a real action on `ManuscriptUnitProvider` (Tier-4) per spec [#08](08_studio_state_architecture.md)'s own "Migration: editorBridge → bus + reconciler" steps 1–3 and spec [#04](04_manuscript_editor.md)'s "Agent write-back (Lane C)" section — both already describe the target shape, neither is built. `ProposeEditCard`'s Apply path in the studio surface calls the hoist action instead of the bridge. **`ChapterEditorPage` keeps using `editorBridge` unchanged** (spec 08 step 5: "do not delete in this track") — it's being retired anyway, not worth touching. | A global mutable singleton (`registerEditorTarget`) is exactly the kind of implicit cross-surface state that gets more dangerous as Checkpoints/Revision-History (Phase 1) start reading "what chapter is currently open" from more places. Fix it before adding more consumers, not after. |
| **P2** | **Reuse the G7 dirty-guard pattern for the new Phase-1 restore paths.** Correction to the initial 2026-07-04 audit finding: G7 (spec [#09](09_agent_gui_reconciliation.md)) is **already implemented** for the Lane-B reconciler — `bookEffects.ts`'s `bookDraftEffect` checks `ctx.isChapterDirty?.(chapterId)` before reloading (confirmed in code, not just spec). P2 is narrower than "build the guard from scratch": Checkpoints-restore (1.2) and Revision-History-restore (1.3) are **two new reload-capable code paths**, and each must call the same `isChapterDirty()` check before restoring over the live document — not a new mechanism, just don't let two new call sites skip the pattern their sibling already follows. | Skipping this on a "just this once, it's not the reconciler" assumption is exactly how a guard pattern gets silently unenforced on new code paths — cheap to require now, expensive to discover after a user loses work to a restore. |

**Gate:** P1 lands with a regression test proving `applyProposedEdit` genuinely replaces `editorBridge` on the Studio path (no residual `registerEditorTarget` call site in `EditorPanel.tsx`/`ComposePanel.tsx`). P2 is folded into 1.2/1.3's own test suites (each restore path gets a "blocked by a dirty hoist" test) rather than being a separate merged commit — there's no shared new code to gate on, just a shared rule to enforce at two new call sites.

## Locked decisions

| # | Decision | Why |
|---|---|---|
| M1 | **Retire `ChapterEditorPage`; Studio becomes the sole chapter-editing surface** once parity is reached. | User-approved direction (2026-07-04) — one product, not two. |
| M2 | **Phase order: data-safety → editor-craft UX → Translate → structural/retirement.** Not file-count order — risk order. Checkpoints/Revision-History/Publish-Gate are the only gaps where a user could silently lose work or ship broken canon; everything else is UX polish or a large standalone migration. | Matches CLAUDE.md's "risk floor" sizing rule — data-loss-adjacent gaps are never the ones you defer. |
| M3 | **Route switch happens per-phase, not all at the end.** Once Phase 1 lands (data-safety parity), flip `ChaptersTab.tsx`'s row-click + pencil-icon target from the legacy edit route to `/studio` (open via `focusManuscriptUnit`). Users keep the legacy route reachable directly by URL (not deleted) until Phase 4. | Phase 1 is exactly the point where Studio stops being *strictly worse* for data safety — no reason to make users wait through Phase 2/3 UX polish before benefiting from Studio's better navigator/scene-rail/reconciler. |
| M4 | **P1 (Lane-C compliance) is a prerequisite, not part of Phase 1's capability count** — it's debt-paydown on already-shipped code (today's `fb98f161f`), gated before Phase 1 starts. P2 (G7 guard reuse) is folded into 1.2/1.3's own scope, not a separate blocking item — the guard *mechanism* already exists (`bookEffects.ts`), only two new call sites need to use it. | Building Checkpoints on top of a known-landmine singleton would bake the landmine deeper; P2 doesn't need its own gate because there's no new shared code to land, just a rule two tasks must each follow. |
| M5 | **Editor-craft UX items (Phase 2) are Tier-1 panel-local** (grammar/glossary-decoration/heatmap/provenance/focus toggle) **except upload-context + progress-reporting**, which are Tier-4 side effects wired into `ManuscriptUnitProvider.save()`/`load()`. No new Tier-3 bus events needed for Phase 2 — these are single-panel concerns, not cross-panel state (per [#08](08_studio_state_architecture.md) S1/Tier-1 definition). | Keeps Phase 2 additive and low-risk — extending `EditorPanel`'s toolbar/decorations, not new architecture. |
| M6 | **Mobile shell — NOT decided here.** `ChapterEditorPage` has a dedicated `MobileEditorShell`; Studio's dockview frame has no mobile pattern and dockview generally isn't designed for narrow viewports. **Flagged as an open product decision** before Phase 4 (retirement) can close: (a) build a lightweight mobile-only editing view that reuses `ManuscriptUnitProvider` without the dockview chrome, (b) keep `ChapterEditorPage`'s `MobileEditorShell` alive as a mobile-only fallback route even after desktop retirement, or (c) accept view/read-only-only on mobile for now. Defer-eligible (CLAUDE.md gate #1 — out of scope for the desktop-parity work; gate #4 — needs a product call, not a technical unknown). | Don't silently resolve a design decision the user hasn't weighed in on; don't block Phase 1–3 on it either — they're desktop-editing gaps regardless of the mobile answer. |
| M7 | **Classic vs AI editor mode toggle** (legacy `useEditorMode`) — tentatively **not ported**; re-check at Phase 2 start whether it's still meaningful once `propose_edit` + the Compose panel unify the AI-assist path (Studio's Chat is always tool-calling-capable; there's no "Classic" mode distinct from "just don't ask the agent to edit"). Not locked — a quick CLARIFY at Phase 2 kickoff, not a full spec. | Possibly already-subsumed by the existing propose_edit flow; confirm before building a mode toggle nobody needs. |
| M8 | **Translate workmode (Phase 3) gets its own spec file** (`17_..._translate_panel.md` or similar, numbered when started) rather than being detailed here — matches [`00_OVERVIEW.md`](00_OVERVIEW.md)'s existing convention of leaving large unscoped items as a bare row until their phase begins. | Track's own "specs grow with the code, never ahead of it" rule; Translate is genuinely large (versions/compare/set-active/jobs) and deserves its own capability audit at build time, not upfront guessing. |
| M9 | **`ChapterEditorPage.tsx` deletion is the LAST step**, gated on: Phase 1–3 complete, M6 (mobile) resolved, and the route redirect (M3) has been live for at least one full phase with no regressions reported. | Never delete a fallback before its replacement has proven itself under real use — this is a multi-week migration, not a single PR. |

## Phase 1 — Data-safety parity (buildable next; detailed enough to start)

**Gate:** P1 + P2 (prerequisite fixes above) merged first.

| # | Task | New Tier-4 surface | File(s) |
|---|---|---|---|
| 1.1 | `ManuscriptUnitProvider.applyProposedEdit(diff)` + `isChapterDirty()` guard wiring (P1+P2, see above) | Extends existing hoist | `features/studio/manuscript/unit/ManuscriptUnitProvider.tsx`, `ProposeEditCard.tsx` (studio path only) |
| 1.2 | Checkpoints — port `useTurnCheckpoints` to key off `ManuscriptUnitProvider`'s save/apply seams (propose_edit Apply, any future auto-apply path) instead of the 3 legacy seams (`onAccept`/`applyPolish`/popout-relay, which don't exist in Studio) | New Tier-4 hoist slice: `chapterId → checkpoint[]`, keyed like the manuscript unit itself | new `features/studio/manuscript/unit/useManuscriptCheckpoints.ts`, new `TurnCheckpoints` panel section (mounts inside `EditorPanel`, not a separate dock panel — matches legacy's placement above Revision History) |
| 1.3 | Revision History + restore — port `RevisionHistory`'s component + the underlying `booksApi.listRevisions`/`restoreRevision` calls; restore goes through the P2 dirty-guard (never silently overwrite unsaved keystrokes) | Reuses Tier-5 API as-is; restore result flows through `ManuscriptUnitProvider.reload()` | new `features/studio/manuscript/unit/useRevisionHistory.ts`, mounted as a section inside `EditorPanel` (matches legacy's right-panel "History" tab placement, adapted to Studio's single-column editor) |
| 1.4 | Publish Gate — port `useChapterPublishGate` + `PublishControl` (canon-contradiction/scene-completeness checks) as an `EditorPanel` toolbar control | No new hoist — reads existing Tier-5 gate-check API, gates the existing publish action | `features/studio/panels/EditorPanel.tsx` (extend toolbar) |
| 1.5 | Route switch (M3) — `ChaptersTab.tsx` row-click + pencil icon → `openPanel('editor')` + `focusManuscriptUnit(chapterId)` in Studio instead of navigating to `/chapters/:chapterId/edit`. Direct URL to the legacy route stays reachable (not deleted). | — | `frontend/src/pages/.../ChaptersTab.tsx` (path TBD — confirm exact file at build time; the audit found it under `BookDetailPage`) |

**Phase 1 gate (must pass before flipping the default route):** dockable-gui.md DOCK-1..11 compliance for any new panel-section additions; unit tests for `useManuscriptCheckpoints`/`useRevisionHistory` (port the legacy tests' assertions, don't just copy the legacy hook verbatim — Studio's save/apply seams differ); a regression test proving P2's dirty-guard blocks a Checkpoints restore over an unsaved edit; `/review-impl`; live browser smoke (propose_edit Apply → Checkpoint appears → restore works → Publish Gate blocks on a real contradiction).

## Phase 2 — Editor-craft UX parity (roadmap only — spec at kickoff)

Port as `EditorPanel` toolbar/decoration extensions (Tier-1, per M5): Grammar check, Glossary inline decoration + `[[` autocomplete (wire the existing `tiptapEditorRef.setGlossaryEntities/setGlossaryEnabled` API the shared `TiptapEditor` component already exposes — this is a wiring gap in `EditorPanel`, not new editor capability), Mention heatmap, AI-provenance tracking, Selection Toolbar + Inline AI layer, Focus/typewriter mode. Plus two `ManuscriptUnitProvider` side-effects: auto-save timer (mirror legacy's 5-minute interval) and progress-reporting (`useReportProgress`/`useEnsureBaseline` calls on save — currently Studio saves silently don't accrue to the composition "today's words" metric, a correctness gap not just a UX one). Plus two small additions: an Original-source (untranslated) read-only viewer tab, and image/video upload-context + version-history wiring (`setImageUploadContext` etc. — currently a global singleton `ChapterEditorPage` sets and `EditorPanel` never does, so image blocks in Studio silently have no upload/version-history support today).

Re-check M7 (Classic/AI toggle) at kickoff.

## Phase 3 — Translate workmode (roadmap only — own spec, M8)

Full `ChapterTranslationsPanel` port as a Studio dock panel (or panel pair, mirroring the Books Browser+Reader precedent in [`14_utility_panels.md`](14_utility_panels.md) Phase C). Large enough for its own capability audit at kickoff — do not guess the shape here.

## Phase 4 — Structural: route retirement + mobile (roadmap only)

1. Resolve M6 (mobile shell decision) — product call, not a technical spec.
2. Full route retirement: `/books/:bookId/chapters/:chapterId/edit` becomes a redirect to `/books/:bookId/studio` (not a 404 — old bookmarks/links must still work).
3. Delete `ChapterEditorPage.tsx` and its now-dead dependencies (`usePopoutInsertRelay`, the legacy `editorBridge` consumer, `MobileEditorShell` if M6 didn't keep it) — only after M9's soak period.

## Coordination — shared spine files (read before touching catalog/i18n/enum)

This branch runs multiple concurrent Claude Code sessions on the same checkout (see [[shared-file-collision-safe-staging-multi-agent-checkout]]). Phase 1's new work is almost entirely **inside existing files** (`EditorPanel.tsx`, `ManuscriptUnitProvider.tsx`) or **new files with no collision risk** (`useManuscriptCheckpoints.ts`, `useRevisionHistory.ts`) — the only shared-spine touch is `ChaptersTab.tsx`'s route-click change (1.5), which is unrelated to any other in-flight studio-panel effort's files. Re-diff `docs/specs/2026-07-01-writing-studio/00_OVERVIEW.md` immediately before adding this component's row (other concurrent specs — e.g. `15_chapter_browser.md`, `15_wiki_panels.md` — are landing rows around the same time).

## Testing discipline

Per [`00_OVERVIEW.md`](00_OVERVIEW.md): unit tests per new hook/panel-section; live browser smoke per phase (not just unit-mocked); `/review-impl` at each phase's close; DOCK-1..11 compliance for anything that touches panel registration.

## Out of scope (recorded so it isn't re-litigated)

- **Mobile shell design** (M6) — explicit open decision, not resolved by this spec.
- **Translate workmode detail** (M8) — its own spec at Phase 3 kickoff.
- **`ChapterEditorPage` deletion timing beyond "last, after a soak period"** (M9) — exact soak duration is a judgment call at Phase 4, not fixed here.
- **Cross-tab / multi-device concurrent editing** of the same chapter — pre-existing gap in both surfaces, not created or fixed by this merge.
