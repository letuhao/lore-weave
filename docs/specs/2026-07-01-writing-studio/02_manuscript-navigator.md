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

## Dock open contract (shared with #04 / #06a)

Chapter and scene row clicks (and the shared jump hook) open a **manuscript unit** in the dock.
Default panel is the Rich editor (`editor`); user preference `lw_studio_default_editor` may be
`editor` | `raw` | `reader`. Cross-ref: [`04_manuscript_editor.md`](04_manuscript_editor.md),
[`04b_raw_editor.md`](04b_raw_editor.md).

| Tree action | Dock target |
|---|---|
| Chapter click | `openManuscriptUnit(chapterId)` + `openPanel(defaultEditor)` |
| Scene click | Same unit + scene focus in tree; editor scoped to `sceneId` when planner exists |
| Context "Open in Raw" (v2) | `openPanel('raw')` for same `chapterId` |

Until Debt #1 clears, selection highlights only — no dock tab. Quick Open uses the same resolve
path with `mode: 'tree_and_dock'`.

**State (#08):** Navigator owns **tree UI state** (expand, scroll, selection highlight) only —
not chapter draft. On chapter/scene select it calls `host.focusManuscriptUnit(chapterId)` and
publishes `{ type: 'chapter', chapterId }` to the bus. Draft body lives in Tier-4
[`useManuscriptUnit`](04_manuscript_editor.md).

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

## Visual parity pass (2026-07-01) — matched the design mockup

The first build shipped the mechanics (virtualize + cursor + lazy + M1 stale-guard) but was
visually stripped vs [`screen-manuscript-navigator.html`](../../../design-drafts/screens/studio/screen-manuscript-navigator.html).
A follow-up brought it to parity:

- **View header** (`nav-head`): New-chapter · Collapse-all · Reload · Collapse-sidebar. The navigator
  now owns the **single** Side-Bar header (VS Code-style) — `StudioSideBar` drops its chrome header
  for the manuscript view to avoid a double header.
- **Arc rows**: roman-numeral label (`ARC I / II …`, ordinal over the loaded list) + child-count badge.
- **Chapter rows**: zero-padded number (`0005`) + **scene-count badge**.
- **Scene dot** status colour (done → success, selected → primary); **selected-row accent bar**.
- **Skeleton shimmer** on first-page load (`flatten` emits `skeleton` rows); **footer** window readout.
- **BE (additive):** composition `list_children` returns `child_count` (non-archived direct children,
  correlated COUNT on the keyset index) → the scene/chapter badges. `OutlineNode.child_count` defaults
  0 for every other query. Partially advances Debt #6: an outlined chapter with **0** scenes is now a
  leaf (no empty caret), but the 1-arc / 1-scene single-child collapse remains.

## Server-backed search pass (2026-07-01) — Debt #2 cleared

The v1 jump box was a **client-filter over loaded rows only** — a fatal blind spot for outlined
books, where the tree lazy-loads and the root shows *only arcs* (the POC book: 1 arc / 12 ch / 35
scenes → typing a chapter/scene name found nothing until you manually expanded the arc). Replaced
with a **server-backed** search — the shared `useManuscriptJump(bookId)` layer (#06a Quick Open will
reuse it, not re-implement):

- **composition-service:** `GET /works/{project_id}/outline/search?q=&limit=` — title `ILIKE`
  across the whole outline (arc/chapter/scene, non-archived, user+project scoped), each hit with a
  breadcrumb `path` (ancestor titles top-first via two self-joins). LIKE metachars escaped.
- **book-service:** the keyset endpoint **already** supports `q` (title/filename `ILIKE`) — reused
  for imports (flat chapters), no new endpoint.
- **FE:** `useManuscriptJump` resolves the source (Work → outline search; none → chapter search),
  debounced (180 ms) with a generation stale-guard; the navigator swaps the tree for a flat result
  list while a query is active, clearing returns to the tree. Live-smoked the outline search SQL on
  the POC project (found the scene "Nghịch Thiên Đảo Chuyển" under Arc 1 › Chương 10).

Selecting a result calls `onSelect` (highlight; dock-open is Debt #1). Full reveal-in-tree
(expand ancestors + scroll to the hit) is a later enhancement — v1 shows the flat result list.

## Debt (pushed to the studio LIFO stack — newest paid first)

1. **reveal-in-tree on jump select** — selecting a search hit highlights (via `onSelect`) but does
   not yet expand its ancestors + scroll the tree to it (needs lazy "load-until-target" paging).
   The flat result list is the v1; tree-reveal lands with the dock wiring (#03 / Debt #3).
2. **New-chapter create flow** — the header **+** button renders (design parity) but is **disabled**;
   wiring a create action (source-aware: book-service `createChapter` for imports / outline-node create
   for a Work, + refetch) is a self-contained slice, not part of the navigator read path.
3. **exact arc chapter-range badge** (`ch 1–40`) — v1 shows the arc's **child count** instead; the
   precise first–last book `sort_order` span needs a composition→book cross-service join (an arc's
   chapters map to book `chapter_id`s). Substituted, not skipped.
4. **navigator→dock "open in group"** — data + E2E deferred until #03 (a dock panel to open into).
5. ~~**server-side chapter search/jump**~~ — **CLEARED 2026-07-01**: composition outline search +
   book-service `q` behind the shared `useManuscriptJump`. (Number-seek `jump-to-#N` and title match
   both go through the server now.)
6. **partial-outline merge** — a has-Work book with undecomposed chapters: v1 drives the tree from
   the outline (authored structure); reconciling with book-service's full chapter list is later.
7. **adaptive degenerate-level collapse (outlined books)** — the two-source split already gives
   *imports* a flat list, and an empty chapter is now a leaf, but an outlined book with exactly **1
   arc** still shows a lone arc row, and a chapter with **exactly 1 scene** still shows the scene
   level. Collapse those in `flatten` (hide a single-child level) as a UX polish. Not implemented (review-impl M2).

## Out of scope (02)

Reorder/drag (uses `reorderNode` — a later editing slice); archive/restore of chapters; the
2-way sync of a book that has BOTH a partial outline and undecomposed chapters (02b resolves the
overlay for outlined chapters; undecomposed chapters render as plain leaves).
