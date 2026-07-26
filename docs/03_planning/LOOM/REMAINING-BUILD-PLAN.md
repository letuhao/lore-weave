# LOOM — Remaining V1 Build Plan (T5.1 → T5.4)

> Source: parallel scout of the 9 remaining composition-studio features (2026-06-24, 9 Explore agents).
> Product spec = `docs/specs/composition-studio-mockup-v3.html`. All features are **sequential** — every one
> edits a hot shared shell file (`CompositionPanel.tsx` ×7, `ChapterEditorPage.tsx` ×4, `TiptapEditor.tsx` ×2),
> so none is parallel-safe. Each built as its own human-in-loop `/loom` cycle (STOP at CLARIFY-end + POST-REVIEW).

## Locked order (PO 2026-06-24)
**T5.1 → T4.2 → T3.5 → T5.2 → T5.3 → T4.1 → T5.5 → T3.6 → T5.4** · T3.6 + T5.4 are in V1 (built last; T5.4 behind a feature flag + fixed-strip fallback).

## Per-feature digest (from scout)

### T5.1 Focus/Typewriter · S · pure FE
Toggle that hides side panels, dims non-current paragraphs (28% opacity), shows a floating continuity pill. Mockup lines 109–118 (`app.focus`, `focusbtn`, `focuspill`, `focusline`). **Files:** `ChapterEditorPage.tsx` (focus state lives here), `CompositionPanel.tsx` (hide on focus), `TiptapEditor.tsx` (paragraph dim/click), i18n×4. **BE:** none. State persists per-session (localStorage).

### T4.2 Progress Stats · M · new BE table
Daily word count vs editable goal, consecutive-day streak (local-midnight safe), 7/30-day sparkline (recharts), book totals. Server-side SSOT. **Files:** `ProgressPanel.tsx`, `useProgress.ts`, `CompositionPanel.tsx` (subtab), `api.ts`, `engine.py`, `db/{models,migrate,repositories/daily_progress}.py`, i18n×4. **BE gaps:** `composition_daily_progress(user_id,project_id,date,words)` table; `GET .../progress` + `POST .../progress/report` (idempotent per date); `daily_goal` in work.settings; timezone-aware date keyed to user-supplied local date.

### T3.5 Style & Voice · M · new BE tables + packer
Density/Pace sliders (0-100) + per-character voice profiles (editable tag chips). Mockup 378–384. **Files:** `StyleVoicePanel.tsx`, `useStyleVoice.ts`, `CompositionPanel.tsx`, `api.ts`, `types.ts`, `engine.py`, `pack.py`, `db/{models,repositories/style_voice}.py`, i18n×4. **BE gaps:** `style_profile` (density/pace, scene|chapter-scoped) + `voice_profile` (entity_id FK, tags[] json) tables + CRUD; `GET/PUT .../style-profile` + `.../voice-profiles`; packer prepends to system prompt; grounding `profile` field includes them. Non-agentic prompt assembly — no MCP.

### T5.2 Mention Heatmap · S · pack (no new table)
Entity mention heatmap in the Grounding panel (name + bar + count, desc) + "show heatmap in prose" toggle (TiptapEditor h1/h2/h3 density bands). Mockup 340–344. **Files:** `GroundingPanel.tsx`, `CompositionPanel.tsx` (lift toggle), `TiptapEditor.tsx` (color bands), `grounding.py`, `pack.py`, i18n×4. **BE:** `pack()` assembles `heatmap[]` from knowledge `mention_count` (already exposed via entity list `sort_by=mention_count`), spoiler-safe to the scene's chapter cutoff. Add `heatmap` to PackedContext.

### T5.3 AI Provenance Highlight · M · pure FE (Tiptap mark)
Mark AI-written vs human prose; faint underlay + hover tag on unreviewed AI spans; click → reviewed (fades). Rides as a Tiptap mark in chapter JSON (CitationMark pattern). **Files:** `ProvenanceMark.ts`, `useProvenance.ts`, `ProvenanceToolbar.tsx`, `ProvenanceTag.tsx`, `TiptapEditor.tsx`, `ComposeView.tsx` (apply on accept), `SelectionToolbar.tsx`, `InlineGhost.tsx`, `ChapterEditorPage.tsx`, i18n×4, Playwright spec. **BE:** none — but verify book-service doesn't strip the unknown mark (Open Q2). Depends on T3.1/T3.2/T3.3 (done). Split-on-edit deferred.

### T4.1 Flywheel Panel · S · cross-service (knowledge BE delta)
After publish→extraction, show +N entities/relations/events with named highlights + deep-links to Cast/Timeline/Relations. Advisory. **Files:** `FlywheelPanel.tsx`, `useFlywheel.ts`, `CompositionPanel.tsx`, i18n×4. **BE gap (knowledge-service):** extend `ExtractionJob` with `entities_added/relations_added/events_added` + `new_items[]` ({kind,id,name}); `GET .../extraction/jobs` returns them. **Cross-service** → live-smoke token required.

### T5.5 Story Map Power-view · M · pure FE frame
Full-screen overlay hosting existing views (Scene Graph T1.3 / Timeline T2.3 / Beat Sheet T1.2 / Relations T2.2 / World Map T2.5) behind a switcher; CSS show/hide (no remount) preserves pan/zoom/selection; Esc closes. Mockup 388–441. **Files:** `PowerViewOverlay.tsx`, `CompositionPanel.tsx`, `ChapterEditorPage.tsx`, i18n×4 (`view.power_view`, `view.back_to_editor` + reuse view titles). **BE:** none. Minimal overlay works before T5.4.

### T3.6 References · M · new BE table + embeddings (V1, build late)
Reference-material panel (docked subtab) of semantically-retrieved influences/passages with source attribution; pin/exclude-able (reuse `SceneGroundingPin` with `item_type='reference'` — needs CHECK extension). **Files:** `ReferencesPanel.tsx`, `useReferences.ts`, `CompositionPanel.tsx`, `api.ts`, `references.py` (router), `db/{models,repositories/references}.py`, `pack.py`, `lenses.py` (`gather_references`), i18n×4. **BE gaps:** `reference_source` table (+ embedding vector); `GET .../references?scene_id=`; embedding pipeline on insert; packer reference lens. ⚠️ Depends on an embedding pipeline existing.

### T5.4 Dock/Float Windowing · XL · pure FE, architectural (V1, build LAST, behind flag)
Replace the fixed sub-tab strip with dock/float/pop-out windowing (dnd-kit rail, draggable in-app windows, OS pop-out via BroadcastChannel). **AH-2 decision:** hoist live state (co-writer stream, chat SSE, Tiptap) to a shared owner (`LiveStateContext`/SharedWorker); docked/floated/popped windows are thin synced views (preserves the no-remount invariant). **Files:** `WorkspaceLayoutContext.tsx`, `LiveStateContext.tsx`, `useWorkspaceLayout.ts`, `WorkspaceShell.tsx`, `ComponentPicker.tsx`, `DockRail.tsx`, `FloatingWindow.tsx`, `types.ts`, `CompositionPanel.tsx`, `ChapterEditorPage.tsx`. **BE:** none (per-device localStorage; server-prefs sync deferred). Feature-flagged with fixed-strip fallback. Write spec + plan (XL).
