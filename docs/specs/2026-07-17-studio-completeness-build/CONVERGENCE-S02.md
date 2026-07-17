# CONVERGENCE — S-02 manuscript parts: navigator wiring (for the convergence node)

> **Why this is here and not done inline:** the S-02 backend (parts CRUD + MCP tools) and the FE
> building blocks (client + pure grouping) are **built, tested, and committed**. The remaining piece —
> rendering parts as collapsible groups in the manuscript navigator with create/rename/reorder/trash
> affordances + drag-chapter-between-acts — must edit `ManuscriptNavigator.tsx` and `useManuscriptTree.ts`,
> which were carrying **another session's uncommitted work** during the S-02 build. Editing them would
> either stage that session's diff into an S-02 commit or leave my render code uncommitted for another
> session's `git commit <file>` to sweep in untested. So the wiring is handed to the convergence node,
> which owns reconciling the studio navigator. **The feature is already human-usable via the Studio
> assistant** (the MCP tools) — this adds the direct-manipulation GUI.

## What's already shipped (consume these — do not rebuild)
- **Backend** (`services/book-service`, committed): 7 REST routes + 6 MCP tools. `part_id` now flows on
  every chapter list/read (`listChapters`, `listChaptersKeyset` — the one `useManuscriptTree` pages —
  and `getChapterByID`).
- **FE client + logic** (`frontend/src/features/studio/manuscript/partsApi.ts`, committed + unit-tested):
  - `partsApi.{list,create,rename,reorder,archive,restore,setChapterPart}` — the typed client.
  - `groupChaptersByParts(parts, chapters, opts) → PartGroup[]` — the PURE two-level model (active acts
    in sort order + a trailing Unassigned bucket; a chapter pointing at a trashed/unknown act falls to
    Unassigned so none is ever dropped). 8 passing tests in `__tests__/partsApi.test.ts`.
  - `Chapter.part_id?: string | null` added to `frontend/src/features/books/api.ts`.

## Wiring to land (in the navigator, at convergence)
Design reference: `design-drafts/screens/studio/screen-manuscript-parts.html`.

1. **Scope: the FLAT branch only.** Parts apply when `useManuscriptTree.source === 'chapters'` (no
   composition Work). When a Work exists the outline (arc→chapter→scene) IS the hierarchy — do NOT also
   render parts there.
2. **`useManuscriptTree` (flat branch):** additionally fetch `partsApi.list(token, bookId)` once per
   book (few rows, no paging), and feed `(parts, pagedChapters)` through `groupChaptersByParts`. Because
   chapters are cursor-paged, a part's children fill in as pages arrive — accumulate chapters, re-group
   on each page. Keep the existing generation/stale-guard (genRef) intact.
3. **Row model:** render each `PartGroup` as a collapsible group header (caret + title + chapter count
   badge); nest its chapters as today's chapter rows. The Unassigned bucket uses the warning-styled head
   (`Unassigned · "no act"`), is NOT renamable/trashable, and is a valid drop target. Adding a `'part'`
   row kind to `ManuscriptRowKind` is the convergence node's call (it owns the exhaustive switch — widen
   it there, in one place, so the FE build stays green).
4. **Affordances (EDIT-gated on the book's `access_level`):**
   - `+ New act` → `partsApi.create` → the new empty act appears.
   - Per act: rename (✎) → `partsApi.rename`; trash (🗑) → confirm *"Chapters stay in the book, just
     un-filed"* → `partsApi.archive` → its chapters reappear under Unassigned (backend un-homes them).
   - Reorder acts (↕) → `partsApi.reorder(orderedIds)` (send EVERY active act id in the new order).
5. **Drag-chapter-between-acts:** drop a chapter row on an act head → `partsApi.setChapterPart(bookId,
   chapterId, targetPartId)`; drop on Unassigned → `setChapterPart(..., null)`. Use **trusted
   pointer-drag** (CDP mouse / real pointer events), per the `playwright-cdp-mouse-drives-d3-drag`
   lesson — synthetic DnD events won't drive a d3/native drag.
6. **`data-testid`s** for the live smoke: `manuscript-part-head`, `manuscript-part-new`,
   `manuscript-part-rename`, `manuscript-part-trash`, `manuscript-part-reorder`, `manuscript-unassigned`.

## Verify (convergence)
- Unit: extend `useManuscriptTree.test.tsx` — flat book with parts renders grouped; a Work-backed book
  ignores parts.
- Live smoke on an **isolated static FE build on a dedicated port** (multi-session HMR-confound rule):
  create an act, drag a chapter into it (network shows `PATCH .../chapters/{id}/part`), trash the act →
  chapter reappears under Unassigned. Screenshot each.
