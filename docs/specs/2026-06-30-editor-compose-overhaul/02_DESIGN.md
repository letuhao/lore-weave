# 02 — Design: IA, Workmode model, Milestones

> Recommended approach. Validated against the real dock code (see
> [`00_INVESTIGATION.md` §4](00_INVESTIGATION.md)). **No re-architecture, no schema/contract/backend
> changes** for the planned milestones.

## Recommended IA — one workspace, mode-driven, grouped panels

- One `Workmode = 'write' | 'translate' | 'compose'` segmented control in the toolbar
  (new `hooks/useWorkmode.ts`, mirroring the 8-line `useEditorMode.ts`). It **derives** the existing
  `editorMode` + `rightTab` state; nothing is deleted, capability is preserved.
- `Classic↔AI` (`editorMode`) → demoted from a top-level toggle to an advanced sub-setting under
  Write (it gates Tiptap block features). `Agent↔Compose` (`composeMode`) **stays** — it's an
  orthogonal model-behavior axis on `<Chat>`, NOT a workmode.
- The ~24 compose panels → grouped into **5 named sections** via a code-side `workspace/groups.ts`
  (`Draft` / `Structure` / `Story Bible` / `Quality` / `Settings`). Chrome-only change; the DockSlot
  mount list is untouched.
- A **Compose start / command-center** view turns the wall of 24 tabs into a guided launcher.
- A first-class **Scenes** panel wires the unused reorder/archive/restore APIs.

### Proposed panel → group map (tune freely; it's one data table)
| Group | Panels |
|---|---|
| Draft | compose, cowriter, assemble |
| Structure | planner, scenes*, beats, graph |
| Story Bible | cast, arc, relmap, timeline, worldmap, canon, canonview, motifs |
| Quality | critic, grounding, style, conformance, quality, threads, progress, flywheel, references, polish† |
| Settings | settings |
_(*`scenes` = new panel from M3. †`polish` = new self-heal review panel from M6, [`stories/07-self-heal-polish.md`](stories/07-self-heal-polish.md).)_

## Milestones (FE except M1's one small BE task; ordered by leverage-per-risk)

| M | Goal | Representative files | Reuse |
|---|---|---|---|
| **M0** | **Workmode switch** — one `Write·Translate·Compose` control; derive editorMode/rightTab; fold away Pen/Sparkles, CowriteBridge, Translate buttons | new `hooks/useWorkmode.ts`; `pages/ChapterEditorPage.tsx` (toolbar ~816-905, render ~1240) | `useEditorMode` pattern, existing `rightTab`/`studioMain` |
| **M1** | **Translate mode** (FS) — extract `ChapterTranslationsPanel`, mount under Translate; delete one-off `handleTranslate`; **+ manual/human-first translation** (story 02): "Write it myself" seeded from source, side-by-side | new `ChapterTranslationsPanel.tsx` (from `ChapterTranslationsPage.tsx:133-209`); `ChapterEditorPage.tsx`; **translation-service: seed-from-source human version endpoint** | `versionsApi`, `translationApi`, `VersionSidebar`, `TranslationViewer`, `TranslateModal`, `SplitCompareView`, `useEditTranslation` |
| **M2** | **Re-group 24 panels** into 5 named sections | new `workspace/groups.ts`; `CompositionPanel.tsx` (~661-670); `DockRail.tsx`; `i18n/.../composition.json` ×4 | `stripIds`, `visibleDockIds`, `t(id)` |
| **M3** | **Scenes panel** — add / drag-reorder / archive / restore | new `ScenesPanel.tsx`; `hooks/useWork.ts` (+3 hooks); register `scenes` in `types.ts` + `CompositionPanel.tsx` | `reorderNode`/`archiveNode`/`restoreNode`/`getOutline(includeArchived)`, dnd-kit from `DockRail` |
| **M4** | **Compose command-center** — guided launcher | new `ComposeStartView.tsx`; `CompositionPanel.tsx` (compose slot) | `selectTab`, `setComposeGuide`, `setSceneId`, `useGuidedFirstRun`, CoWriter `onUseAsGuide` |
| **M5** *(stretch)* | `BookAssistantDock` glossary chat → compose/enrichment input | `features/chat/BookAssistantDock.tsx` | `onUseAsGuide` seam |
| **M6** | **Polish / self-heal pass** (FS) — manual + opt-in auto; **accept/reject review-gate** over the engine's proposals (never silent-apply); deterministic edits default-checked, semantic default-unchecked; per-run controls (canon always-on, verify, vote depth, prefilter); optional stronger-model escalation | new `PolishPanel.tsx` + diff/review pane (Quality group); **composition-service: expose `self_heal` as an MCP propose→confirm tool** (engine `engine/self_heal.py` already built) | `SelfHealReport` proposals, `run_self_heal(canon/vote_k/verify/prefilter)`, planning `PipelineResult` cast bible for canon |

**Recommended first deliverable: M0 + M1 together** — M0 fixes the root-cause mode confusion
(near-zero risk, derives existing state); M1 gives the most visible relief (translation Postman→GUI
by extracting one existing page) and needs M0's Workmode for a clean home.

## Verification (per milestone)
- Build/types/lint: `cd frontend && npm run build` + lint; `npm test` for touched feature dirs.
- M0: one switch; mode-switch preserves editor/scene/glossary state (no remount); `lw_editor_workmode`
  persists.
- M1: live-smoke on running stack w/ test account (BYOK models) via Playwright/Chrome-DevTools MCP —
  coverage + version picker + start a job + side-by-side; **no Postman**.
- M2: 24 panels under 5 labelled sections, 4 locales; in-flight generation survives re-group.
- M3: add → drag-reorder (persisted via outline refetch) → archive → restore round-trip.
- M4: 4 launcher actions drive existing handlers end-to-end.
- M6: manual Polish returns proposals (no silent write); accept/reject splices only accepted edits;
  auto-polish toggle persists per-book (server); deterministic edits default-checked, semantic
  default-unchecked; live-smoke the heal through the MCP propose→confirm tool on the running stack.

## Out of scope (consciously)
No data-model/contract changes; no touching the `DockSlot` mount list or `WorkspaceShell` provider
hoist; no collapsing `composeMode` into Workmode; no rewriting the translate UI (extract, don't
rewrite); the enrichment-vs-writing "Compose" naming fix is a label/placement task folded into M2/M4.

## Open questions for PO (cross-cutting; per-story Q's live in `stories/`)
1. Confirm **M0+M1** as the opening milestone (vs M1-first, or M2-grouping-first)?
2. Translate placement: **center side-by-side** (proposed) vs right-panel?
3. OK to **demote `Classic↔AI`** to an advanced sub-setting under Write?
4. Cadence: one milestone at a time through `/loom`?
5. Polish/self-heal (M6, [`stories/07-self-heal-polish.md`](stories/07-self-heal-polish.md)): auto-polish
   default **off** vs **on-for-deterministic-edits-only**? Accepted edits → new draft version (OCC) vs
   edit-in-place+undo? Stronger-model escalation capability + cost-gate UX?
