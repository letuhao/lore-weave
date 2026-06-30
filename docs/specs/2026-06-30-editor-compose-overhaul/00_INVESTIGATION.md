# 00 — Canonical Investigation (current state)

> **Purpose:** the single source of truth for *what exists today*. Written once so no future session
> re-greps. All paths are under `frontend/src/` unless noted. Line numbers are approximate anchors.
> Evidence gathered 2026-06-30 via 3 Explore agents + 1 Plan agent (dock-infra validation).

---

## 1. Editor shell

`pages/ChapterEditorPage.tsx` — route `/books/:bookId/chapters/:chapterId/edit` (App.tsx ~121),
layout `EditorLayout`. Structure:
- **Toolbar** (~783): breadcrumb + prev/next chapter; editor-mode toggle (~816-843); co-writer bridge
  button (~852); grammar toggle (~862); **Translate** button (~880-891) + **View translations** (~897);
  panel toggles + focus mode (~908-920); save-status badge; discard (dirty-only); Save; publish gate.
- **Left panel** (resizable, ~1003-1150): tabs **Chapters / Source / Glossary / Outline** (all wired).
- **Center** (~602-701): title input; metadata bar (language, char/word/para counts); provenance
  toolbar (T5.3, only when `composeProjectId` exists); `TiptapEditor`; optional `selectionMenu`
  (`SelectionToolbar`) + `aiLayer` (`InlineAiLayer`) — both only when `composeProjectId` exists; save
  note input. Or `VersionHistoryPanel` when viewing a revision.
- **Right panel** (resizable, ~1156-1243): tabs **History** (`RevisionHistory`) / **AI Chat**
  (`Chat` + Agent/Compose toggle) / **Co-write** (`WorkspaceShell → CompositionPanel`).
- **Status bar** (~1246) + always-mounted modals (discard, unsaved-guard, mode-switch guard,
  glossary tooltip, provenance tag).

### Save model
- `isDirty = bodyChanged || titleChanged` (~275); synced to context for the sidebar (~288).
- **Manual Save** button + **autosave 5 min after last change** (`setTimeout(..., 300_000)`, ~511-519).
- `beforeunload` leave-guard when dirty (~560-566).

---

## 2. The THREE overlapping "mode" systems (the core confusion)

| # | State / file | localStorage | Controls |
|---|---|---|---|
| (a) | `useEditorMode()` → `'classic'\|'ai'` (`hooks/useEditorMode.ts`); toolbar Pen/Sparkles (~816-843); passed to `TiptapEditor editorMode=` (~663) | `lw_editor_mode` | Tiptap feature gating — **media/callout blocks only render in `ai` mode** |
| (b) | `composeMode` boolean Agent\|Compose (`ChapterEditorPage.tsx:133`); toggle inside AI Chat panel (~1204-1223) | `lw_editor_compose_mode` | `<Chat>` tools-on vs prose-only (model behavior axis) |
| (c) | `rightTab` `'history'\|'ai'\|'compose'` (`ChapterEditorPage.tsx:172`) | (none) | which right-panel tab; `compose` hosts `studioMain` (~1240) |

These are orthogonal and unnamed → no mental model. The overhaul collapses the user-facing layer into
one **Workmode** (`write|translate|compose`) that *derives* (a) and (c); (b) stays (it's a real
separate axis).

---

## 3. Manual / "Write" editing surface (the strongest, most finished part)

Core: `components/editor/TiptapEditor.tsx` (forwardRef `TiptapEditorHandle`). Extensions: StarterKit
(H1-3, hr; codeBlock replaced by lowlight `CodeBlockExtension`), Image/Video/Audio block nodes +
`MediaGuardExtension`, Link, Underline, Highlight, Sub/Superscript, `CitationMark`, GlobalDragHandle,
Placeholder, Typography, `CalloutExtension`, `GrammarExtension`, `GlossaryExtension`,
`SlashMenuExtension`, `FocusLineExtension` (T5.1 typewriter), `HeatmapExtension` (T5.2),
`ProvenanceMark` (T5.3 AI-span review), `TrackedPositionsExtension` (WS-C).

- **FormatToolbar** (`components/editor/FormatToolbar.tsx`): paragraph, H1-3, bold/italic/strike/
  underline/inline-code, link, highlight, sub/superscript, bullet & ordered list, blockquote, code
  block, hr, undo/redo. **Image/Video/Audio buttons gated to `mode === 'ai'`** (~188-209).
- **SlashMenu** (`components/editor/SlashMenu.tsx`): `/` menu. Items image/video/audio/**callout**
  gated to `modes: ['ai']` (~32-36).
- Glossary live-highlight + tooltip + autocomplete; grammar toggle; focus/typewriter mode; source view.
- Programmatic write-back handle: `insertAtCursor` / `replaceSelection` / `getSelection` (flow through
  `onUpdate` so they dirty+autosave) — used by AI tools.

**Key finding (manual-mode defect):** media + callout insertion is locked behind the **`ai`**
editor-mode, so pure "Classic" manual writing **cannot insert an image/video/audio/callout** and
nothing signals why. This is a mode-coupling bug, not a missing feature.

---

## 4. The ~24 compose panels

`features/composition/components/CompositionPanel.tsx` mounts ~24 sub-panels **always-on, CSS-hidden**
via a `DockSlot` system (no-remount is **load-bearing** for in-flight generation state). An existing
**flag-gated** windowing layer exists: `WorkspaceLayoutProvider` + `DockRail` + `FloatingWindow` +
`PopoutBridge` + `MobilePanelSwitcher`; when the flag is OFF a fixed `TabScrollStrip` is used.

**Single source of truth for the registry:** `features/composition/workspace/types.ts` —
`WorkspacePanelId` (~9), `PANEL_IDS` (~15), `DOCK_ORDER` (~45). Runtime lists: `CompositionPanel.tsx`
`stripIds` (~439) and `workspace/dock.ts` `visibleDockIds()`. The `SubTab` union is at
`CompositionPanel.tsx:82`.

Panels: `compose` (ComposeView live gen), `cowriter` (CoWriterChat), `assemble`, `planner`
(PlannerView scene CRUD/reorder), `beats`, `graph` (SceneGraphCanvas), `cast`, `relmap`, `timeline`,
`arc`, `worldmap`, `grounding`, `canonview`, `references`, `style`, `canon`, `critic`, `threads`,
`progress`, `quality`, `flywheel`, `motifs`, `conformance`, `settings`.

### Dock-infra validation (why re-grouping is cheap — NO re-architecture)
- The 24 panels are a **flat `order`-sorted registry**; a `group` field is purely additive.
- `DockSlot` mount list (`CompositionPanel.tsx` ~685-872) is **decoupled** from rail/strip chrome —
  `slot(id).active` is computed from `activeTab === id` only. Re-grouping changes navigation chrome
  only; the mount list stays byte-identical. `DockSlot.tsx:46` = `className={active ? '' : 'hidden'}`
  (CSS hide, never unmount).
- `DockRail.tsx` takes `visibleIds: WorkspacePanelId[]`; `computeReorder` (`dock.ts:30`) is
  group-agnostic. `mergeLayout` (`WorkspaceLayoutContext.tsx:71`) forward-merges new panels → adding
  panels/groups never breaks persisted layouts.
- **Recommendation:** keep `group` in code (a new `workspace/groups.ts`), NOT in persisted layout
  (avoids any localStorage/server-pref migration).

---

## 5. Scenes — partially wired

- Wired: select / create / mark-done — `useChapterScenes` (`hooks/useWork.ts:84`), `useCreateScene`
  (~96), `useSetSceneStatus` (~111). Scene controls live in `CompositionPanel.tsx:450-496`.
- **No editor UI** for reorder/arrange/archive/restore. `features/composition/api.ts` exposes but
  **leaves unused**: `reorderNode` (~202, drag-reorder+reparent, If-Match), `archiveNode` (~190),
  `restoreNode` (~195), `getOutline(..., includeArchived)` (~136). Reorder exists only inside
  `PlannerView` (a different job: template→preview→commit decomposition).
- Scene status model: `'empty' | 'outline' | 'drafting' | 'done'`. M9 chapter-gate requires all scenes
  `done` before publish.

---

## 6. Translation — a button, not a mode

- Today: one-off toolbar `Translate` (`handleTranslate` ~524-556) → `POST
  /v1/translation/translate-text`, replaces the whole doc. Not persistent; no side-by-side; all-or-nothing.
- **The full lifecycle already exists in the FE, just not mounted in the editor:**
  - `features/translation/api.ts`: `versionsApi` (list/get/`setActiveVersion`/`saveEditedVersion`/
    `patchBlock`) and `translationApi` (`getBookCoverage`, `createJob`, `listJobs`, `getJob`,
    `cancelJob`, `getBookSettings`, `getSegmentStatus`, `retranslateDirty`).
  - `pages/ChapterTranslationsPage.tsx` is a **complete** persistent experience: `VersionSidebar`
    (language + version picker + retranslate/compare), `TranslationViewer`, `SplitCompareView`,
    `TranslateModal` (job start). Body to extract: ~133-209 (minus breadcrumb ~163-169).
- **Wire = extract** `ChapterTranslationsPanel({bookId, chapterId})` and mount under Translate
  workmode. Optional live job progress = poll `translationApi.getJob` (same pattern as `_pollJob`,
  composition `api.ts:58`).

---

## 7. Two "Compose" features collide on the name

- `features/enrichment/components/compose/*` — glossary **entity enrichment** (Book Detail →
  Enrichment Tab). Modes draft/context/files/intent/gap; results → Proposals tab. API:
  `enrichmentApi.compose()` → `POST /v1/lore-enrichment/projects/{bookId}/compose` (202 + async job).
- `features/composition/*` — chapter **writing studio** (the editor's Co-write tab).
- Same word, different feature, different entry point, different scope (book-level vs chapter-level).

---

## 8. Discuss→content bridge EXISTS but is hidden

- `features/composition/components/CoWriterChat.tsx` already wires **Insert** (`onAccept`) +
  **Use-as-guide** (`onUseAsGuide` → pre-fill compose guide + `selectTab('compose')`) —
  `CompositionPanel.tsx:700-711`. It's tab #2 of 24, so users never find it.
- `hooks/useGuidedFirstRun.ts` already produces next-step guidance + first-scene creation
  (`guided.guidedCue`, `CompositionPanel.tsx:594-615`).
- `features/chat/BookAssistantDock.tsx` (glossary assistant, floating "Ask AI" on Glossary/Reader)
  **dead-ends** — no "use this discussion as input" action; it only does `propose_edit` /
  `propose_record_edit` write-backs.

---

## 9. Backend / MCP surface (what the GUI can call)

| Capability | REST | MCP | Notes |
|---|---|---|---|
| Scenes/outline CRUD | ✗ | ✓ `composition_outline_node_*` | MCP-only |
| Scene links | ✗ | ✓ `composition_scene_link_*` | MCP-only |
| Canon rules | ✓ | ✓ | both |
| Motifs library | ✗ | ✓ `composition_motif_*` | MCP-only |
| Prose read/write | ✓ `/prose` | ✓ `composition_(get\|write)_prose` | both; OCC `expected_draft_version` |
| Generation (cowrite) | ✓ `POST /generate` (SSE) | ✓ `composition_generate` (confirm-token) | REST=direct spend, MCP=cost-gated |
| Chapter CRUD + revisions | ✓ book-service | ✗ | REST-only |
| Translation lifecycle | ✓ | ✓ (job start/resume confirm-gated) | both |
| Work get/create | ✓ get / ✗ create | ✓ both | create is MCP-only |
| Lore enrichment | ✓ (C3 stubs, 501) | ✗ | not wired |

OCC tokens throughout (`expected_draft_version` for prose/draft; `If-Match` node `version` for outline).
Tenancy: user from JWT only; book/project from path or X-Project-Id; grant-gated (VIEW read / EDIT write).

**Implication:** "wiring it up" surfaces already-built FE + already-existing backend. **No
schema/contract/backend changes are required** for the planned milestones.

---

## 10. Critical files (quick map)

| Concern | File |
|---|---|
| Editor page (modes, toolbar, save, mounts) | `pages/ChapterEditorPage.tsx` |
| Rich editor + handle | `components/editor/TiptapEditor.tsx` |
| Manual toolbar / slash (media gating) | `components/editor/FormatToolbar.tsx`, `SlashMenu.tsx` |
| Compose studio shell + 24-panel mount | `features/composition/components/CompositionPanel.tsx`, `components/workspace/WorkspaceShell.tsx` |
| Panel registry (annotate with `group`) | `features/composition/workspace/types.ts` |
| Dock/rail/layout infra | `features/composition/components/workspace/` (`DockRail`, `DockSlot`, `TabScrollStrip`, `MobilePanelSwitcher`) + `workspace/dock.ts` + `WorkspaceLayoutContext.tsx` |
| Scene hooks + unused APIs | `features/composition/hooks/useWork.ts`, `features/composition/api.ts` (~136-212) |
| Translate panel to extract + API | `pages/ChapterTranslationsPage.tsx`, `features/translation/api.ts` |
| Discuss→content bridge | `features/composition/components/CoWriterChat.tsx`, `hooks/useGuidedFirstRun.ts` |
| Glossary chat dead-end | `features/chat/BookAssistantDock.tsx` |

---

## 11. Deep-dive investigations (2026-06-30, cont.) — detail lives in the story files

These were mapped during the story-by-story discussion. **Full evidence is in the linked story files;
this section is the index + the key facts so nothing is re-explored.**

### 11.1 AI chat agent/tool/model surface → [`stories/04-ai-chat-core.md`](stories/04-ai-chat-core.md)
- Per-session config persisted in `chat_sessions` (model + composer + planner models, system prompt +
  presets, `generation_params`). MCP tool-calling with **lazy-load via `find_tools`** over the
  ai-gateway federated `/mcp` catalog (~200 tools); tiers **R/A/W/S** + Tier-W confirm gating = a
  permission model. **No per-chat tool selection, no first-class skills** (skills only auto-injected by
  surface: `inject_glossary/universal/knowledge_skill`). **`top_p` bug:** stored/PATCHed but not
  forwarded to the LLM on streaming turns. Config home = `chat_sessions`.

### 11.2 Media generation (image/video/TTS) → [`stories/05-compose-toolbox.md`](stories/05-compose-toolbox.md)
- **Image gen WIRED** (`components/editor/ImageBlockNode.tsx:267` → `booksApi.generateImage`); MediaPrompt
  default `regenerateDisabled=true` is overridden by the block. **Video** = `features/video-gen/api.ts`
  `videoGenApi.generate` (`/v1/video-gen/generate`, decoupled job poll). **TTS** = `hooks/useAutoTTS.ts`
  (reader/chat). Scattered + gated behind `editor` mode `ai`. **No media/asset browser** (only
  motif/arc-template libraries). PO decision: **Media tool DEFERRED** (classic books have no media).

### 11.3 The Photoshop-style toolbox windowing → [`stories/05-compose-toolbox.md`](stories/05-compose-toolbox.md)
- Already built, **flag-OFF**: `context/WorkspaceLayoutContext.tsx` flag `loom.workspace.enabled`
  (default off, FLAG_KEY:16). Dock / **float** (`FloatingWindow.tsx`) / **pop-out** to a separate OS
  window (`PopoutBridge`/`PopoutHost`/`popoutChannel.ts`). Persists per-device + server-synced (WS-D);
  live SSE state survives moves. ⇒ "make it feel like Photoshop" = flip default ON + polish + group.

### 11.4 The 24 tools as a creative WORKFLOW → [`stories/06-compose-journey.md`](stories/06-compose-journey.md)
- Tier-0 prereqs: a **Work** (`project_id`) + a chat model. Ideation entry = **CoWriter chat** (no
  premise→outline wizard exists; the **Planner** IS that tool but isn't surfaced). 6 phases: Idea →
  Structure → Story-bible → Draft → Refine → Assemble. Compose preconditions = `sceneId + modelRef`
  only. Motifs = refinement, not first. **GOTCHA:** Planner **does NOT mint chapters** (`plan.py`) — it
  decomposes existing chapters → a fresh book needs a chapter created first. The GUI encodes no
  process ⇒ guided journey needed. Ideal target = [`compose-ideal-journey.html`](compose-ideal-journey.html).

### 11.5 Structure templates vs motif/arc-templates → [`stories/06-compose-journey.md`](stories/06-compose-journey.md) §Structure
- `structure_template` is **read-only seeded** (6 built-ins, no POST/PATCH/DELETE, no editor); table has
  `owner_user_id` + repo filters by it ⇒ per-user schema-ready, no write path. **Motif/arc-template have
  full CRUD + proven tenancy** (owner-stamp, clone-to-edit, System read-only); motif `beats[]` =
  Planner-consumable shape. Arc-template is richer (multi-thread layout) — not a flat-beats drop-in.
  Three scales: motif → arc-template → structure-template. Options A (motif `kind="structure"`) vs
  **B (rec: CRUD on `structure_template` + unified library UX)**. Tenancy: System read-only +
  clone-to-edit (copy motif uniform-404 pattern).
- Backend paths (composition-service): `db/models.py:99-105` (StructureTemplate), `:357-408` (Motif/
  MotifBeat), `:444-467` (ArcTemplate); `routers/plan.py` (decompose consumes `tmpl.beats`),
  `routers/motif.py` + `routers/arc.py` (CRUD); `repositories/structure_templates.py` (read-only).
