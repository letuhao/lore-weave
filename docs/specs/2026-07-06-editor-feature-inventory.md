# Editor Feature Inventory (Writing Studio)

> Purpose: a flat, numbered, countable checklist of every discrete user-facing feature in the Writing Studio chapter editor (`EditorPanel.tsx` + everything it mounts), built by reading the CURRENT CODE — not [`16_chapter_editor_parity_and_retirement.md`](2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md), which is a decisions/task-tracking log and was found not detailed enough to drive tour design. This doc is the source-of-truth for scoping the guided-tour work (`frontend/src/features/studio/onboarding/tours.ts`).
>
> **105 discrete items across 14 groups.** Each entry: name — one-line description — `file:line` — `data-testid` (or **NO TESTID**) — control shape.

---

## A. Toolbar strip (top of EditorPanel) — 11 items

1. **Unsaved/save-state indicator** — "● unsaved" or current save state. `EditorPanel.tsx:240-242` · `studio-editor-dirty` · status label
2. **Grammar toggle** — grammar-check decoration on/off. `EditorPanel.tsx:245-252` · `studio-editor-toggle-grammar` · toggle
3. **Heatmap toggle** — mention-density tinting on/off. `EditorPanel.tsx:253-260` · `studio-editor-toggle-heatmap` · toggle
4. **Focus mode toggle** — typewriter/focus mode. `EditorPanel.tsx:261-268` · `studio-editor-toggle-focus` · toggle
5. **Scenes (Scene Rail) toggle** — show/hide right-side Scene Rail. `EditorPanel.tsx:269-276` · `studio-editor-toggle-scenes` · toggle
6. **"Open as JSON" button** — opens this unit in the generic JSON editor. `EditorPanel.tsx:280-291` · `studio-editor-open-json` · button
7. **"Original Source" button** — read-only pre-translation source viewer. `EditorPanel.tsx:293-304` · `studio-editor-open-original-source` · button
8. **"Reader" button** — opens/retargets the book-reader panel. `EditorPanel.tsx:310-317` · `studio-editor-open-reader` · button
9. **"Translate" button** — opens Translation Versions panel for this chapter. `EditorPanel.tsx:321-332` · `studio-editor-open-translate` · button
10. **Save button (+ ⌘S)** — saves the unit; global keybinding too. `EditorPanel.tsx:333-341,207-217` · `studio-editor-save` · button
11. **Publish Gate section** — mounted at toolbar's right edge (see group E, items 59a-e). `EditorPanel.tsx:343-344` · — · section

## B. Rich-text formatting toolbar (`FormatToolbar.tsx`) — 23 items

All **NO TESTID** (identified only by `title`/icon).

12. Paragraph `:57-63` · 13. Heading 1 `:64-70` · 14. Heading 2 `:71-77` · 15. Heading 3 `:78-84` · 16. Bold `:89-95` · 17. Italic `:96-102` · 18. Strikethrough `:103-109` · 19. Underline `:110-116` · 20. Inline code `:117-123` · 21. Link (prompts URL) `:128-141` · 22. Highlight `:142-148` · 23. Subscript `:149-155` · 24. Superscript `:156-162` · 25. Bullet list `:167-173` · 26. Ordered list `:174-180` · 27. Blockquote `:181-187` · 28. Insert image (AI-mode only) `:188-195` · 29. Insert video (AI-mode only) `:196-201` · 30. Insert audio (AI-mode only) `:202-207` · 31. Code block `:210-216` · 32. Horizontal rule `:217-222` · 33. Undo `:227-233` · 34. Redo `:234-240`

35. **Code-block floating toolbar** (`CodeBlockToolbar.tsx:122-166`, NO TESTID): 35a. language `<select>` (13 languages), 35b. copy, 35c. delete.
36. **Callout cycle-type button** — cycles note→warning→tip→danger. `CalloutNode.tsx:65-81` · NO TESTID

## C. Slash-command menu (`/` in editor) — 14 items

`SlashMenu.tsx:24-38`, all **NO TESTID**.

37. /paragraph · 38. /heading1 · 39. /heading2 · 40. /heading3 · 41. /bullet · 42. /numbered · 43. /quote · 44. /image (AI-mode) · 45. /video (AI-mode) · 46. /audio (AI-mode) · 47. /code · 48. /callout (AI-mode) · 49. /divider
50. **Keyboard nav** — ↑/↓ select, Enter execute, Esc dismiss. `SlashMenu.tsx:134-156`

## D. AI writing tools — selection & inline continuation — 4 items (with sub-controls)

51. **Selection Toolbar** (bubble menu on text selection) — `SelectionToolbar.tsx:106-108` · `selection-bubble`/`selection-toolbar`
    51a. model picker `selection-model` · 51b. instruction input `selection-instruction` · 51c. Rewrite `selection-rewrite` · 51d. Expand `selection-expand` · 51e. Describe `selection-describe` · 51f. "too long" warning `selection-too-long` · 51g. streaming ghost `selection-ghost` · 51h. Stop `selection-stop` · 51i. Accept `selection-accept` · 51j. Discard `selection-discard`
52. **Classic⇄AI mode toggle** (inline layer, always visible top-right) — `InlineAiLayer.tsx:52-69` · `inline-mode-classic`/`inline-mode-ai`
53. **"Continue from cursor" button** — streams an AI continuation from caret. `InlineAiLayer.tsx:75-83` · `inline-continue`
54. **Inline ghost overlay** (caret-anchored streamed continuation) — `InlineGhost.tsx:37-45` · `inline-ghost`/`inline-ghost-text`
    54a. Accept `inline-accept` · 54b. Edit `inline-edit` · 54c. Regenerate `inline-regenerate` · 54d. Discard `inline-stop`/`inline-discard`

## E. Data safety — provenance, checkpoints, revision, publish — 5 items (with sub-controls)

55. **Provenance toolbar** (unreviewed-AI-span count + controls, self-hiding) — `ProvenanceToolbar.tsx:17-52` · `provenance-toolbar`
    55a. count `provenance-count` · 55b. show/hide `provenance-toggle-visible` · 55c. mark-all-reviewed `provenance-mark-all`
56. **Provenance hover tag** (hover an AI-written span) — `ProvenanceTag.tsx:49-63` · `provenance-tag`
57. **AI-edit Checkpoints strip** (restore points per AI apply) — `ManuscriptCheckpoints.tsx:43-101` · `studio-manuscript-checkpoints`
    57a. dirty warning · 57b. Restore (per row) `studio-manuscript-checkpoint-restore` · 57c. confirm dialog
58. **Revision History section** (collapsible, past revisions + restore) — `RevisionHistorySection.tsx:51-149` · `studio-revision-history`
    58a. expand/collapse toggle · 58b. blocked-by-dirty banner · 58c. list item · 58d. Restore `studio-revision-history-restore` · 58e. Load more (NO TESTID)
59. **Publish Gate** — `EditorPublishGate.tsx:59-82` + `PublishControl.tsx:51-96`
    59a. "canon unchecked" badge `studio-publish-canon-unchecked` · 59b. status badge `editorial-badge` · 59c. Publish/Re-publish `publish-button` · 59d. Unpublish (NO TESTID) · 59e. confirm dialog

## F. Glossary — 3 items

60. **Glossary toggle** — ⚠️ **gap**: state exists (`glossaryEnabled`, defaults on), no visible toolbar control wired in `EditorPanel.tsx:62`.
61. **Glossary hover tooltip** (name/kind/translations/attributes/appearances) — `GlossaryTooltip.tsx:94-169` · NO TESTID
62. **`[[` glossary autocomplete** — `GlossaryAutocomplete.tsx:140-179` · NO TESTID
    62a. filtered list · 62b. keyboard nav · 62c. "+ create new" (wired to a no-op in `EditorPanel.tsx:402`)

## G. Mention heatmap — 1 item

63. **Heatmap tinting** — entity/alias tinting by mention-density band, toggled by item 3. `EditorPanel.tsx:136-143` + `HeatmapPlugin.tsx`

## H. Scene Rail — 12 items

64. **Scene Rail container** — `SceneRail.tsx:214-218` · `studio-scene-rail`
65. **⚓ Anchor scenes** — backfill heading↔scene anchors. `:220-227` · `scene-rail-anchor`
66. **＋ Add scene** — `:228-237` · `scene-rail-add` (+ 66a title input `scene-rail-new-title`, 66b confirm `scene-rail-create`)
67. **Notice banner** — `:255-259` · `scene-rail-notice`
68. **Delete-undo banner** — `:261-267` · `scene-rail-undo`/`scene-rail-undo-btn`
69. **Jump to prose** (per-row) — `:82-90` · `scene-rail-jump-{sceneId}`
70. **Status `<select>`** (per-row) — `:91-98` · `scene-rail-status-{sceneId}`
71. **Synopsis textarea** (per-row) — `:100-111` · `scene-rail-synopsis-{sceneId}`
72. **Move up ▲** (per-row) — `:115-122` · `scene-rail-up-{sceneId}`
73. **Move down ▼** (per-row) — `:123-130` · `scene-rail-down-{sceneId}`
74. **Delete ✕** (per-row) — `:131-137` · `scene-rail-delete-{sceneId}`
75. **Inline error** (per-row) — `:139` · `scene-rail-error-{sceneId}`

## I. Media blocks — Image — 9 items

76. Upload zone (drag/drop/paste/click, png·jpeg·gif·webp, 10MB) — `ImageBlockNode.tsx:405-448,242` · NO TESTID
77. Replace (hover + caption-bar) — `:384-392,490-498` · NO TESTID
78. Delete block (hover + caption-bar) — `:393-401,510-518` · NO TESTID
79. Resize handle — `:450-467` · NO TESTID
80. Caption input — `:476-483` · NO TESTID
81. Version History button → opens `media-version-history:{chapterId}:{blockId}` — `:500-509,313-322` · NO TESTID
82. Alt-text collapsible section — `:522-548` · NO TESTID
83. AI-Prompt section (`MediaPrompt`, shared) — model picker, Regenerate, Copy — `:260-294` + `MediaPrompt.tsx:64-156` · NO TESTID
84. Classic-mode locked placeholder — `:296-345` · NO TESTID

## J. Media blocks — Video — 10 items

85. Upload zone (mp4/webm, 100MB, client-side duration) — `VideoBlockNode.tsx:376-417,20-33` · NO TESTID
86. Replace — `:355-363,459-467` · NO TESTID
87. Delete block — `:364-372,480-488` · NO TESTID
88. Resize handle — `:419-436` · NO TESTID
89. Caption input — `:445-452` · NO TESTID
90. Version History button — `:470-479,288-297` · NO TESTID
91. Alt-text collapsible section — `:492-518` · NO TESTID
92. AI-Prompt + Generate section (`video_gen`, fixed 5s/16:9) — `:237-274,521-533` · NO TESTID
93. Native video player controls — `:341-349` · NO TESTID
94. Classic-mode locked placeholder — `:277-313` · NO TESTID

## K. Media blocks — Audio (standalone block) — 6 items

95. Upload zone (mpeg/wav/ogg/webm/mp4, 20MB) — `AudioBlockNode.tsx:330-370` · NO TESTID
96. Play/Pause + fake waveform — `:282-289,291-301` · NO TESTID
97. Replace — `:311-318` · NO TESTID
98. Delete block — `:319-326` · NO TESTID
99. Subtitle/caption input — `:379-386` · NO TESTID
100. Classic-mode locked placeholder (no version-history, unlike image/video) — `:240-256` · NO TESTID

## L. Narration audio attach (per-paragraph, distinct from the Audio block) — 3 items

101. **Per-block hover action bar** (AI-mode only; raw DOM, no React) — `AudioAttachActionsExtension.ts:302-403,45-296` · NO TESTID
     101a. Upload (📁) · 101b. Record (🎤, MediaRecorder) · 101c. AI-generate (✦, TTS via `localStorage('lw_tts_prefs')`)
102. **Attached-audio playback bar** (under any block with `audio_url`) — `AudioAttachBarExtension.ts:40-187` · NO TESTID
     102a. Play/Pause · 102b. source badge · 102c. mismatch warning · 102d. Remove (✕)
103. Audio-attrs global-attribute extension (infra, not user-facing) — `AudioAttrsExtension.ts:11-59`

## M. Editor guard-rail behaviors (observable, not clickable) — 2 items

104. **Media-guard toast** — protected-block delete/paste warning; Classic mode fully locks media/code blocks. `MediaGuardExtension.ts:19-28,53-119`
105. **Classic ⇄ AI editor mode** (document-wide, distinct from item 52's per-device toggle) — locks media into placeholders, hides AI-only slash/toolbar items. `TiptapEditor.tsx:200-221`

---

## Gaps found while enumerating (not features — flagged for whoever picks this up)

- **Glossary has no visible enable/disable control** in `EditorPanel.tsx` (item 60) — defaults on, state exists, never exposed.
- **Source-view (raw JSON) toggle** (`TiptapEditorHandle.setSourceView`) has no caller in Studio's `EditorPanel` at all — dead capability on this surface.
- **FormatToolbar (23) + SlashMenu (14) items have zero `data-testid`s** — icon/title only.
- **All media-block per-node actions (groups I/J/K/L, ~40 items) have zero `data-testid`s.**

## Tour-readiness summary

| Group | Items | Have testid | Need testid for a tour |
|---|---|---|---|
| A — Toolbar strip | 11 | 11 | 0 |
| B — Format toolbar | 23 | 0 | 23 (if tour-worthy — likely skip, self-explanatory icons) |
| C — Slash menu | 14 | 0 | 14 (likely skip — discovered by typing `/`, not a spotlight target) |
| D — AI writing tools | 4 groups (~14 controls) | 14 | 0 |
| E — Data safety | 5 groups (~15 controls) | ~13 | ~2 |
| F — Glossary | 3 | 0 | 2-3 (+ the toggle doesn't exist yet — a real gap, not just a testid gap) |
| G — Heatmap | 1 | (covered by A.3) | 0 |
| H — Scene Rail | 12 | 12 | 0 |
| I/J/K/L — Media blocks | 28 | 0 | most, if included |
| M — Guard-rail behaviors | 2 | — | N/A (not clickable) |

**Recommendation for the tour:** groups A, D, E, H already have full or near-full testid coverage and are the highest-value "first 10 minutes" surfaces — these are tour-ready NOW. Groups B/C (formatting, slash-menu) are self-explanatory/discoverable UI and are poor tour material regardless of testid gaps. Groups I/J/K/L (media) are real features but 28 items of "click this button on an image block" would make the tour exhausting — better served by 1-2 steps per media type ("here's how to add/regenerate media") than one step per micro-action. Group F's glossary toggle gap should be fixed (add the missing control) before it can be toured at all.
