# S-11 · Search activity-view (PO decision D-a: BUILD)

> **PO decided (2026-07-17): build a real search surface** rather than retire the icon. **CLARIFY-verify
> correction:** it is SMALLER than the question implied — the search *capability* already exists
> (`RawSearchPanel` + `RawSearchPage` + `story_search` route + `memory_search`); it just was never brought
> into the studio as the `search` activity-view. So S-11 is a **mount + aggregation**, not a from-scratch
> build, and needs **no HTML draft** (`RawSearchPanel` is the design reference). **Service:** knowledge (BE
> complete; this is FE).

## 1. Current state (verified)
- `RawSearchPanel` (`features/raw-search/components/`) — full-text search over the book; already mounted
  inside `ChapterBrowserPanel`/`ChapterBrowserContentView` and as the standalone `RawSearchPage`
  (`/books/:bookId/search`).
- `story_search` (raw) + `memory_search` (drawer/semantic) routes are public + complete.
- **Missing:** no `search` panel in `catalog.ts`; the `search` activity-view renders "Coming soon"
  (F-7). The capability has no studio home in the primary nav.

## 2. Build — a `search` activity-view rail + panel (FE only)
- **Activity-view rail:** replace the `search` navStub with a real navigator — a query box + mode toggle:
  **Text** (story_search / RawSearchPanel results) and **Semantic** (memory_search / drawer results). This is
  the `StudioSideBar` `search` branch (today a stub).
- **Panel:** a `search` dock panel (category — new-or-`storyBible`?; see DECISIONS) that hosts the results:
  each hit deep-links to its owning surface (a chapter hit → open the editor at that chapter; an
  entity/drawer hit → open kg-entities / the evidence panel). Reuse `RawSearchPanel` for the text mode; add a
  thin semantic-mode list over `memory_search`.
- GG-8 shape (catalog + `panel_id` enum + contract + i18n `guideBodyKey` + CATEGORY_ORDER). A Lane-B handler
  is **not** needed (search is a read; no agent write refreshes it).

## 3. Not a from-scratch build — reuse, don't fork
`RawSearchPanel` and its `useRawSearch` hook are the text mode AS-IS (DOCK-2 — no fork). The only net-new FE
is: the activity-view rail wiring, the mode toggle, and the semantic-mode list over the existing
`memory_search` route (`useDrawerSearch` may already cover it — verify at build; reuse if so).

## 4. Tests
- the `search` activity-view no longer renders "Coming soon" — it renders the query rail.
- a text query returns story_search hits that deep-link to the right chapter (open-editor-at-chapter).
- a semantic query returns memory_search hits that deep-link to kg-entities / evidence.
- `panelCatalogContract` covers the new `search` panel (enum==openable==contract).

## 5. Out of scope
- No new backend — story_search + memory_search are complete.
- Cross-book / global search — per-book only (matches the existing capability).
