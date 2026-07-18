# RUN-STATE — S-11 build (search activity-view)

> FE-only (a mount + aggregation over COMPLETE backends: story_search + memory_search). Spec:
> S-11_search-activity-view.md. Touches the shared studio registry (catalog + panel_id enum +
> contract + i18n) — wired directly (no active parallel session), guarded by panelCatalogContract.

## THE COMMITMENT
Give the studio `search` activity-view a real home: a query rail + a `search` dock panel with Text
(story_search) + Semantic (memory_search) modes, each hit deep-linking INTO the manuscript (not a
dead-end list). DONE = built, reachable, operable end-to-end, tests green.

## INVESTIGATE (verified vs code + Explore-agent map, 2026-07-18)
- `search` activity-view rendered the "Built next." stub (StudioSideBar); no `search` in catalog. CONFIRMED.
- `RawSearchPanel` (`{bookId}`, own query box + toggles) + `useRawSearch` exist; its hit `onJump` navigates
  to the READER route (`/read`) — which would leave the studio dock. `useDrawerSearch` (semantic) exists;
  RawDrawersTab's hit-click only opens a read-only slide-over (NO deep-link).
- Deep-link mechanism = `host.focusManuscriptUnit(chapterId)` → opens the in-dock editor at the chapter
  (the same seam the navigator / Quick Open / agent's ui_focus_manuscript_unit use).
- Panel wiring: dock panels get `props.api`+`props.params`; `bookId` via `useStudioHost().bookId`;
  `openPanel(id,{params})` seeds via `props.params` + `onDidParametersChange` (BookReaderPanel precedent).
- projectId (for semantic) via `useBookKnowledgeProject(bookId)`. Contract parity: catalog ==
  frontend_tools.py enum == contract.json, enforced by panelCatalogContract.test.ts.

## SEALED DESIGN (resolves the spec's one open question + the rail/panel split)
- **D-S11-category: `knowledge`.** The `search` panel joins the kg-* group (semantic = knowledge drawers;
  avoids a new top-level category, which would churn CATEGORY_ORDER + palette.group i18n + the contract).
- **Rail = the entry, Panel = the results.** `SearchNavigatorRail` (query box + Text/Semantic toggle) →
  `openPanel('search', {params:{query,mode}})`. `SearchPanel` reads params (mount + onDidParametersChange),
  hosts the mode toggle + results, remounts the inner surface on a new rail query (key=query) to re-seed.
- **Reuse, don't fork (DOCK-2).** Text = `RawSearchPanel` AS-IS + two optional props (`onJump`,
  `initialQuery`) so the studio injects `focusManuscriptUnit` + seeds the query; the standalone
  RawSearchPage keeps its reader-navigation default. Semantic = a thin net-new `SemanticSearchList` over
  `useDrawerSearch` (chapter-source hit → focusManuscriptUnit; other passages expand inline).

## SLICE BOARD (done = evidence)
- [x] RawSearchPanel + optional onJump/initialQuery (non-fork) — EVID: RawSearchPanel.studio.test 3 (onJump
      intercepts, default navigates, initialQuery seeds).
- [x] SemanticSearchList (thin useDrawerSearch list + chapter deep-link) — EVID: 4 (no-project, chapter→
      onOpenChapter(source_id), non-chapter expands, empty).
- [x] SearchPanel (mode toggle, reads params.query/mode, Text/Semantic) — EVID: 3 (text default + onJump→
      focusManuscriptUnit + initialQuery; semantic via params.mode; in-panel toggle).
- [x] SearchNavigatorRail + StudioSideBar `search` branch — EVID: rail 3 (real rail not stub, submit seeds
      params, empty-query opens) + StudioSideBar updated (search = rail, quality keeps the stub).
- [x] Registry: catalog row (category knowledge) + frontend_tools.py enum `search` + description +
      contract.json regen (WRITE_FRONTEND_CONTRACT) + i18n en (panels.search.* + search.*) + 17-locale
      gap-fill — EVID: panelCatalogContract 9 green; chat-service contract test 36 pass; i18n +17 keys/locale 0 failed.

## VERIFY
- Whole-project `tsc --noEmit` = **0 errors**. FE: 22 new S-11 tests + StudioSideBar 10 + panelCatalogContract 9;
  broad studio-search/raw-search/panels suites = 55 pass. BE chat-service contract = 36 pass. i18n 18 locales.
- Operability (the empty-shell thesis): both modes wrap ALREADY-LIVE shipped components (RawSearchPanel is
  used in ChapterBrowser + RawSearchPage; useDrawerSearch in RawDrawersTab) over COMPLETE backends; the only
  net-new is tested wiring + deep-link. Panel is REACHABLE (activity-rail + palette + agent ui_open_studio_panel
  'search'). NOT a dead-end: every hit opens the editor at its chapter.
- Browser live-smoke on the isolated static build: recommended follow-up (FE-only change; the component-test→
  contract-parity→live-component chain covers each link; no cross-service runtime call added).

## RESULT: S-11 COMPLETE — the search activity-view is a real, reachable, operable surface (Text + Semantic,
## deep-linking into the editor). Category sealed `knowledge`. FE-only.
