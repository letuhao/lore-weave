# Story 01 — Manual "Write" mode

> **Status:** ✅ decided (QoL-only) · **Epic:** A (underlies A1 "Write") ·
> **Evidence:** [`../00_INVESTIGATION.md` §3](../00_INVESTIGATION.md)

## What "manual mode" means

The **Write** baseline: the author types prose straight into the Tiptap editor, no AI required.
Already a capable rich-text surface (`components/editor/TiptapEditor.tsx`, `FormatToolbar.tsx`,
`SlashMenu.tsx`):
- Formatting: paragraph, H1–H3, bold/italic/strike/underline/inline-code, link, highlight,
  sub/superscript, bullet & ordered lists, blockquote, code block, hr, undo/redo.
- Slash menu (`/`), drag-handle block reorder, Typography, placeholder.
- Glossary live-highlight + hover tooltip + autocomplete.
- Grammar toggle, focus/typewriter mode, source view.
- Title + live metadata (language, char/word/para). Revision history + restore.
- Save: manual Save + 5-min autosave + dirty tracking + leave-page guard.

**Assessment:** this is the **strongest, most finished part** of the whole editor. PO agrees manual
writing "is ok". The chaos is *around* it (modes/compose/translation), not in it.

## Issues found (within manual mode)

1. **"Manual" is secretly split by the Classic↔AI toggle.** Image/video/audio/callout are gated to
   `editorMode === 'ai'` (`FormatToolbar.tsx:188-209`, `SlashMenu.tsx:32-36`). A writer in **Classic**
   mode cannot insert media/callouts and gets no hint why. Inserting an image is a *manual* action
   wrongly hidden behind an "AI" label.
2. **5-minute autosave is risky** for a writing app (`ChapterEditorPage.tsx:517`,
   `setTimeout(..., 300_000)`). A crash/close can lose up to 5 min of prose. Manual Save + dirty badge
   are a backstop, but idle-based autosave (~3–5 s) would match the "server is source of truth" promise.

## Recommendation

- **Write mode = full manual block palette** — fold media + callout into Write; retire the
  "Classic gates media" coupling (part of demoting Classic↔AI to a non-mode).
- **Tighten autosave** to idle-based (~3–5 s after last keystroke). Small, high-trust win.
- Keep the rich editor otherwise **as-is** — don't touch the strongest surface.

## Decisions locked (PO, 2026-06-30)

**Verdict: keep the Classic editor as designed — it ticks the original design. QoL-only, no redesign.**

- **L1 — Name stays "Classic".** The manual writing surface keeps the **Classic** label and its
  current behavior/layout. No investigation of original design needed — PO confirms it's fine as-is.
  _(How "Classic" relates to the new Workmode switch is deferred to story **A1**.)_
- **L2 — QoL: idle autosave.** Replace the 5-min timer (`ChapterEditorPage.tsx:517`) with idle-based
  autosave ~3–5 s after the last keystroke. Keep manual Save + dirty badge + leave-guard.
- **L3 — QoL: media/callouts available while writing.** Remove the `editorMode === 'ai'` gate on
  image/video/audio/callout (`FormatToolbar.tsx:188-209`, `SlashMenu.tsx:32-36`) so manual writers can
  insert them without flipping to "AI". _(If A1 keeps a Classic/AI distinction, re-confirm there.)_

**Scope note:** these QoL items are small and land naturally with **M0** (Workmode) since they touch
the same `editorMode`/toolbar/autosave code. No separate milestone needed.

## Open decisions
- [x] D1 (media) → **L3 (yes, ungate).**
- [x] D2 (autosave) → **L2 (idle-based).**
- [ ] D3 — no other manual-writing frustrations raised by PO at this time. _(reopen if any surface.)_
