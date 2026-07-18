# S-02b · Manuscript parts — close the reachability dead-ends (reorder · restore · create-into-act)

> **Follow-up to S-02, driven by the live GUI audit** ([`S-02_GUI-AUDIT-2026-07-18.md`](S-02_GUI-AUDIT-2026-07-18.md)).
> S-02 shipped the parts data layer + agent tools + a working navigator GUI (create / drag-file / trash /
> un-home all verified live). But **two backend-complete verbs have NO GUI path** — a user cannot reach
> them at all. This spec is pure **FE wire-up over routes that already exist and are tested**; it adds no
> new backend surface. **Theme: no S-02 verb is unreachable.**

## 1. Goal / user stories
- *"I have Act I, Act II, Act III and want Act III to come first"* → **reorder acts** (today: impossible).
- *"I trashed an act by mistake — put it back"* → **restore a trashed act** (today: gone from the UI forever;
  chapters survive but the act's name/grouping is unrecoverable).
- *(lower)* *"Add a new chapter straight into this act"* → **create-into-act** (today: create via Plan, then drag).

## 2. Current state (verified against code)
- **Reorder — backend READY, FE ABSENT.** `POST /v1/books/{id}/parts/reorder` (`parts.go` `reorderParts` /
  `storeReorderParts`) + `book_part_reorder` MCP tool + `partsApi.reorder(token, bookId, orderedIds)`
  (`partsApi.ts:67`) all exist + are tested. **Gap:** `useManuscriptTree` returns only
  `createAct/renameAct/trashAct/moveChapterToAct` (`useManuscriptTree.ts:258`) — no `reorderAct`; the
  navigator renders no reorder control; act header rows are `draggable=false` (audit DOM check).
- **Restore — backend READY, FE ABSENT.** `GET …/parts?include_trashed=true` + `POST …/parts/{id}/restore`
  (`parts.go` `restorePart` / `storeRestorePart`) + `book_part_restore` MCP + `partsApi.restore`
  (`partsApi.ts:81`) + `partsApi.list(token, bookId, {includeTrashed})` all exist. **Gap:** the navigator
  fetches active-only, exposes no trashed view, no restore, no undo.
- **Create-into-act — partial.** `createChapter`/`createChapterRecord` (`server.go`) do NOT accept a
  `part_id` (a new chapter is always born un-homed). The move route can re-home it after.

## 3. Tenancy — nothing new
Every route reused here is already grant-gated (EDIT) and book-scoped (`authBook` / `mcpRequireGrant`);
reorder validates the id-set is exactly the book's active parts, restore is `id + book_id` scoped. **No new
scope key, no new tenancy surface** — this spec only adds FE callers of vetted routes.

## 4. Design decisions

### 4.1 Reorder acts — **up/down move buttons** (primary), drag-to-reorder (optional)
- **Decision: primary UX = ↑/↓ "move act" buttons** in each act header's affordance group (disabled at the
  ends). Rationale: the act rows already own **drag-a-chapter-INTO-act**; overloading the same draggable
  surface with **drag-act-TO-reorder** makes drop-intent ambiguous. Up/down buttons are unambiguous,
  **keyboard- and touch-friendly** (directly answers the audit's accessibility finding), and need no
  drag-kind discrimination.
- Hook: add **`moveAct(partId, dir: 'up'|'down')`** — reads the current ordered active `parts`, swaps the
  target with its neighbour, calls `partsApi.reorder(orderedIds)`, then `reload()`. No-op at the boundary.
- Optional enhancement (defer unless cheap): make act headers draggable for desktop drag-reorder; the drop
  handler distinguishes a dragged **act** from a dragged **chapter** via a `dataTransfer` kind marker.
  Deferred — the buttons cover the need.
- Only rendered when the book has **≥2 acts**.

### 4.2 Restore a trashed act — **undo toast** (immediate) + **"Trashed acts" section** (durable)
- **Decision: trash becomes INSTANT + UNDOABLE.** On trash, show a **sonner** toast *"Act '<name>' trashed ·
  Undo"* whose action calls `partsApi.restore`. (`sonner` is already mounted — `App.tsx` `<Toaster/>`.) This
  is the fast recovery path and mirrors the MCP `undo_hint` the tools already emit. **It also lets us drop
  the blocking `window.confirm`** (trash is reversible, so a modal gate is unnecessary — see S-02c §native-dialogs).
- **Durable view:** a collapsible **"Trashed acts"** section pinned at the bottom of the manuscript navigator,
  shown only when `partsApi.list({includeTrashed:true})` returns any trashed rows. Each lists the act name +
  a **Restore** button (`partsApi.restore`). Covers the "I closed the toast / came back later" case.
- Hook: add **`restoreAct(partId)`** + surface **`trashedActs: Part[]`** (a parallel include-trashed fetch,
  filtered to `lifecycle_state==='trashed'`), refreshed on every `reload()`.
- **Restore does NOT re-home chapters** (S-02 sealed) — the restored act comes back **empty**; the UI copy
  must say so ("restored empty — re-file chapters as needed") so it isn't mistaken for a bug.

### 4.3 Create-into-act — **create-then-move** (MVP), backend `part_id` optional
- **Decision (MVP): FE compose, no backend change.** An empty act shows a subtle **"+ chapter"** affordance;
  it runs the existing chapter-create, then `partsApi.setChapterPart(newId, actId)`. Two calls, zero new BE.
- Optional later: add an optional `part_id` to `createChapter` so it's one atomic call. Deferred (the
  compose path is correct and cheap; **lowest priority in this spec** — the drag workaround already exists).

## 5. Frontend surface (all in files S-02 already owns)
- `useManuscriptTree.ts`: add `moveAct`, `restoreAct`, `trashedActs`; keep `trashAct` but route its UX through
  the undo toast. Return them alongside the existing mutators.
- `ManuscriptNavigator.tsx`: ↑/↓ buttons in the act affordance group; a "Trashed acts" collapsible section;
  the undo-toast call on trash; the empty-act "+ chapter" affordance.
- `partsApi.ts`: already complete — no change (reorder/restore/list already there).
- **No registry / i18n-registry edits** — new strings use `defaultValue`; locale entries land at convergence
  (same rule as S-02).

## 6. Tests (evidence gate)
- **Unit (hook):** `moveAct('p2','up')` on `[p1,p2,p3]` → calls `reorder(['p2','p1','p3'])`; no-op at ends.
  `restoreAct` calls `partsApi.restore` + reload. `trashedActs` reflects the include-trashed fetch.
- **Unit (navigator):** ↑/↓ render only with ≥2 acts, disabled at boundaries, call `moveAct`. Trash fires the
  undo toast whose action calls `restoreAct`. The "Trashed acts" section renders + Restore calls `restoreAct`.
- **Live smoke (rebuilt stack, isolated FE port):** create 3 acts → reorder via ↑/↓, order persists on reload;
  trash an act → Undo toast restores it; trash again → restore from the Trashed-acts section. Screenshot each.

## 7. Out of scope / by-design
- No nested acts, no OCC on parts (S-02 sealed decisions stand).
- Backend `part_id`-on-create is optional/deferred (§4.3).
- Drag-to-reorder acts is an optional enhancement, not the MVP (§4.1).
