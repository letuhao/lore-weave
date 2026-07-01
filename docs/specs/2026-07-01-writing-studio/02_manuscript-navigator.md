# 02 · Manuscript Navigator

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: 🟡 building.
> Draft: [`design-drafts/screens/studio/screen-manuscript-navigator.html`](../../../design-drafts/screens/studio/screen-manuscript-navigator.html)

## What it is

The Side Bar's primary navigator — an **adaptive `arc → chapter → scene` tree** that scales to
10k+ chapters via the VS Code Explorer recipe (virtualized rows + cursor paging + lazy
expansion). Selecting a unit will drive the dock (the wiring lands with #03; until then,
selection highlights — Debt #1).

## Grounded data model (from code)

- **Chapters** live in **book-service** (`chapters` table; `id` UUIDv7 PK, `sort_order INT`,
  `book_id`). Authoritative list; the only source that reaches 10k. Sort key for keyset:
  `(sort_order, chapter_id)` — `chapter_id` UUIDv7 is a strict, stable tiebreak.
- **Arcs + Scenes** live in the **composition outline** (`outline_node`: `kind ∈
  {arc,chapter,scene,beat}`, `parent_id` tree, `chapter_id`→book chapter). It IS a real
  arc→chapter→scene hierarchy. Exists **only if the book has a composition Work**. The read API
  `GET /v1/composition/works/{id}/outline` returns the **whole tree, unpaged**.
- **Imports** = book-service chapters only (no Work → no arcs, no scenes). This is the
  10k-scale case.

## Design: chapters spine + outline overlay (adaptive depth)

- **Spine = book-service chapters**, cursor-paged + virtualized. Always present. Scales to 10k.
- **Overlay = the composition outline** (when a Work exists): arcs group chapters (arc→chapter
  by `parent_id`, mapped to book `chapter_id`); scenes hang under their chapter (`chapter_id`).
- **Adaptive depth** — render only levels that add grouping: **1 arc → hide the arc row; 1 (or 0)
  scene/chapter → chapter is the leaf.** Imports collapse to a flat chapter list + jump box;
  self-written render the full 3-level tree (collapse arcs to navigate 10k by group).

## Build (ONE milestone — user chose "full navigator in one go"), phased for verifiability

Built as a single #02 (chapters spine + arc/scene overlay together, incl. the composition-service
paged-outline work). Phases below are a build/verify order, not separate ships.

### Phase 1 — Chapters spine (book-service cursor)
- **BE (book-service, Go):** `GET /v1/books/{bookId}/chapters` gains **keyset/cursor** paging —
  `?cursor=<opaque>&limit=100` → `{ items, next_cursor }`. Keyset `WHERE book_id=$1 AND
  lifecycle_state='active' AND (sort_order, id) > ($2,$3) ORDER BY sort_order, id LIMIT n+1`
  (n+1 to detect has-next). Opaque base64 cursor = `sort_order|chapter_id`. New handler mirrors
  `listChapters` (server.go:1023); add `idx_chapters_keyset (book_id, sort_order, id)`. Contract
  + pure SQL-builder unit tests (book-service convention: `parseKeysetCursor`, `buildKeysetWhere`).
- **FE:** `ManuscriptNavigator` — cursor-paged book chapters, **flat**, virtualized
  (`@tanstack/react-virtual` over the visible row array), load-more sentinel near the tail,
  jump-to-#N (sort_order seek), selection highlight. Unit tests + E2E (large-list virtualization
  + paging).
- **Done when:** a book with N chapters renders a flat virtualized list; scrolling pages in via
  cursor; only visible rows are in the DOM; jump-to-#N seeks; tsc/lint/build clean; unit + E2E green.

### Phase 2 — Lazy outline reads (composition-service)
- Add a **lazy-children** endpoint: `GET /v1/composition/works/{id}/outline/children?parent_id=<id|null>&cursor&limit`
  → `{ items, next_cursor }` — direct children of `parent_id` ordered by `rank` (`parent_id`
  null → arcs; under an arc → chapters; under a chapter → scenes). This is the paged lazy-tree
  primitive so the overlay scales like the spine. Python unit tests.

### Phase 3 — FE navigator (adaptive tree, two data sources)
- A tree data-source abstraction: **has-Work → outline lazy-children** (arc→chapter→scene);
  **no-Work → book-service cursor chapters** (flat). `@tanstack/react-virtual` over the flattened
  visible rows; lazy-expand fetches a node's children page; load-more sentinel; adaptive collapse
  (1 arc / ≤1 scene-per-chapter → hide that level); jump-to-#N; selection highlight. Unit tests.

### Phase 4 — Wire + verify
- Replace the Side Bar manuscript stub; E2E (large-list virtualization + cursor paging + lazy
  expand on both paths); `/review-impl`; fix; run all.

## Jump contract (shared with #06a Quick Open)

The sidebar **jump box** and the global **⌘P Quick Open** modal ([#06a](06a_quick_open.md))
share one hook — `useManuscriptJump(bookId)` — and one search/jump backend. **Do not** implement
a second query path in #06a.

### v1 (this milestone)

| Capability | Mechanism |
|---|---|
| Jump to chapter **number** | `sort_order` seek via book-service keyset cursor |
| Jump by **title** (loaded pages only) | Client filter over pages already in the navigator store |
| Full-text over all 10k chapters | **Deferred** — book-service `GET /v1/books/{bookId}/manuscript/jump?q=` (Debt #2 below) |

Sidebar jump box: **Enter** → `resolve(result, 'tree')` (+ `'tree_and_dock'` when Debt #1 clears).
Quick Open (when built): **Enter** → `resolve(result, 'tree_and_dock')`.

Target API shape when server jump ships: see [06a §Jump contract](06a_quick_open.md).

## Debt (pushed to the studio LIFO stack — newest paid first)

1. **navigator→dock "open in group"** — data + E2E deferred until #03 (a dock panel to open into).
2. **server-side chapter search/jump** (book-service) — v1 ships jump-to-#N (sort_order seek) +
   client-filter of loaded pages; full server search over all 10k is a later book-service add.
   **Shared with #06a** — one `GET …/manuscript/jump?q=` unblocks both sidebar jump and ⌘P.
3. **partial-outline merge** — a has-Work book with undecomposed chapters: v1 drives the tree from
   the outline (authored structure); reconciling with book-service's full chapter list is later.
4. **adaptive degenerate-level collapse (outlined books)** — the two-source split already gives
   *imports* a flat list, but an outlined book with exactly **1 arc** shows a lone arc row, and a
   chapter with **≤1 scene** still shows the scene level. Collapse those in `flatten` (hide a
   single-child level) as a UX polish. Not implemented in v1 (review-impl M2).

## Out of scope (02)

Reorder/drag (uses `reorderNode` — a later editing slice); archive/restore of chapters; the
2-way sync of a book that has BOTH a partial outline and undecomposed chapters (02b resolves the
overlay for outlined chapters; undecomposed chapters render as plain leaves).
