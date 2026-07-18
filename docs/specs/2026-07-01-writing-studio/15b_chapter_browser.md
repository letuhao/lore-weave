# 15b · Chapter Browser — new studio dock panel (FE + BE)

> **Status:** ✅ **BUILT** (FE + BE) — the `chapter-browser` panel is live at `catalog.ts:183`
> (+ `ChapterBrowserTitleView`/`ChapterBrowserContentView`); the BE shipped CB3's `word_count`
> migration (`book-service/internal/migrate/migrate.go:487`) and the CB4/CB5 bulk zip-export +
> per-id-outcome status routes (covered by real-DB tests in `internal/api/bulk_chapters_db_test.go`).
> *(Un-staled 2026-07-13, X-8: the header still read "📐 specced 2026-07-04" long after the code shipped.
> Status re-checked against `catalog.ts` + `migrate.go`, not copied from a doc.)*
> · branch `feat/context-budget-law` (studio track)
> Design draft approved: [`design-drafts/screens/studio/screen-chapter-browser.html`](../../../design-drafts/screens/studio/screen-chapter-browser.html). Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), same shape as [`14b_utility_panels.md`](14b_utility_panels.md). **This is a cross-service (FE+BE) task — first one in this series that isn't FE-only.**

## Why (recap of the approved proposal)

Two components already do most of what's needed but are under-used or disconnected:
- `components/shared/ChapterListBrowser.tsx` — server-paged, debounced title/filename search, multi-select + "select all N matching" — today wired ONLY into the extraction wizard's chapter picker.
- `features/raw-search/components/RawSearchPanel.tsx` — full-text content search (hybrid/lexical, snippet+relevance+jump-to-source) — today a totally standalone page (`/books/:id/search`), unreachable from any chapter list.

This spec fuses them into ONE new studio dock panel (`chapter-browser`) with a Title-vs-Content search-mode toggle (same accepted in-panel-toggle shape `RawSearchPanel` already uses for hybrid/lexical — not a DOCK-8 violation), plus real filters/sort/grouping/bulk-actions that today's `ChaptersTab.tsx` (the "too simple" browser) lacks entirely (no search input, fixed `limit=20` offset paging, no sort, no grouping).

## Investigation findings (grounds the task list below)

| Capability | Current state | Implication |
|---|---|---|
| Bulk translate | **Already works.** `TranslateModal` takes `preselectedChapterIds: string[]`; `TranslationTab.tsx` already drives it from an arbitrary multi-select set. | Zero new BE/FE plumbing — reuse as-is. |
| Group by arc | Composition/outline API exists (`compositionApi.listOutlineChildren`) but **only for books with a Composition Work attached** — a plain-import book has no arcs, same fallback `ManuscriptNavigator` already uses. No arc chapter-range/count field from the API — roman numeral + counts are computed client-side today. | FE-only; "Group by arc" toggle must be hidden/disabled when no Work exists (same UX precedent as the Navigator). |
| Bulk status/lifecycle change | **Does not exist.** `patchChapter` only updates title/sort_order/language — no status field at all; no bulk route of any kind for status/trash. | New BE work: a bulk PATCH endpoint. |
| Bulk zip export | **Does not exist.** Only single-chapter `GET /chapters/{id}/export` (`exportChapter`). User chose the full BE build (not the lighter FE-loop v1). | New BE work: a zip-bundling endpoint. |
| `search.go` pagination | Real, undocumented gap: `LIMIT` only, `OFFSET` never applied (inline comment "v1 has no pagination (offset ignored, LOW-3)"); not tracked in `docs/deferred/` anywhere — this spec is the first place it's tracked. Minimal fix: add `OFFSET` to the 3 SQL variants; the chapter-granularity query re-ranks per request (window function), so paging is not keyset-stable across changing data — acceptable for v1 (documented caveat, not silently ignored). | Small BE fix, in scope. |
| `sort` param | `listChapters`/`listChaptersKeyset` sort is fixed to `sort_order, created_at` — no param accepted. | Small BE addition. |
| `word_count` | **Does not exist** anywhere on the public `Chapter` record (an unrelated internal endpoint has a non-multilingual byte-length heuristic, not this). User chose full v1 inclusion. | New BE work: column + backfill + maintenance trigger, multilingual-aware (CJK char-count vs Latin word-count, mirroring `computeReadingStats` in `useBookReaderContent.ts`). |

## Locked decisions

| # | Decision | Why |
|---|---|---|
| CB1 | **New panel `chapter-browser`**, palette + agent-openable (an agent plausibly wants "show me chapters missing a translation" or "chapters over N words"). Sibling to `editor`/`book-reader`/`glossary`, not a replacement for `ManuscriptNavigator` (different job: tree-for-writing vs table-for-triage-at-scale, per the draft's own framing). | DOCK-1/6. |
| CB2 | **Title-mode and Content-mode render via separate sub-components** (`ChapterBrowserTitleView.tsx`, `ChapterBrowserContentView.tsx`) composed by the panel shell, NOT inlined as one giant conditional in the panel file. | Keeps the two modes independently buildable/testable/fan-out-able (mirrors the Jobs/Books/Leaderboard precedent of thin, disjoint files) even though they live in one panel/one catalog entry (DOCK-8 doesn't require a catalog split here — see the DOCK-8 analysis below). |
| CB3 | **`word_count` ships in v1**: new column + batched backfill (no full-table lock on a 10k+-chapter book) + an `AFTER INSERT OR UPDATE OR DELETE` trigger on `chapter_blocks` that recomputes the parent chapter's `word_count` (mirrors the existing `fn_extract_chapter_blocks`/`trg_extract_chapter_blocks` pattern — same table, same trigger shape, not a new mechanism). Multilingual: char-count for CJK-detected content, word-split count otherwise (same `CJK_REGEX` heuristic as `computeReadingStats`, ported to Go). | User call (approved the heavier option over deferring). |
| CB4 | **Bulk zip export ships in v1** as a real BE endpoint (`GET /chapters/export.zip?ids=...` or `POST` with a body, TBD in PLAN), streaming `archive/zip` (Go stdlib, no new dependency) over the same `chapter_blocks`/`chapter_drafts.body` source `exportChapter` already reads per-chapter. | User call (approved the heavier option over the FE-loop v1). |
| CB5 | **Bulk status-change** ships as a new endpoint accepting `{chapter_ids: string[], lifecycle_state?, ...}`, returning a **per-id outcome** (not a single all-or-nothing success/fail) — same "report the real result" discipline this repo already applies elsewhere (e.g. `glossary_propose_entity_edit`'s outcome enum) so a partial failure across N chapters is never silently swallowed. | Matches repo convention; avoids a new silent-partial-failure class. |
| CB6 | **`search.go`'s OFFSET fix ships in v1** (small, isolated, `search.go`-only change) — but the "not keyset-stable across changing data" caveat is documented in the endpoint's own comment and in this panel's Content-mode footer copy ("results may shift if chapters change while paging"), not silently hidden. | Small enough to fix now (No-Defer-Drift default); honesty about the residual limitation instead of overclaiming stability. |
| CB7 | **`sort` param ships in v1** for `listChapters`/`listChaptersKeyset`: `sort_order` (default), `updated_at`, `word_count`, `lifecycle_state`. Keyset variant only supports stable-sort keys (`sort_order`, `updated_at`) for true cursor paging; `word_count`/`status` sort is offset-paginated only (documented, not a silent limitation) — mirrors the same "some sorts can't be cursor-stable" honesty as CB6. | Needed for the mock's sort dropdown; keyset-vs-offset split is a real constraint, not an oversight. |
| CB8 | **Group-by-arc reuses `compositionApi.listOutlineChildren`/`useWorkResolution` as-is** (DOCK-2 — no fork of `useManuscriptTree`'s logic; a thin new hook `useChapterBrowserGroups` wraps the SAME composition API calls for the browser's table-grouping need, since the shapes needed differ — Navigator needs a lazy-expandable tree, the browser needs a flat "which arc is chapter N in" lookup for table group-headers). Falls back to ungrouped (flat) when `useWorkResolution` reports no Work, same as the Navigator. | DOCK-2/SDK-First — reuse the API, not fork Navigator's tree-specific hook. |

## DOCK-8 analysis (why Title/Content stay ONE panel, unlike Leaderboard's 4-way split)

Leaderboard's 4 tabs were genuinely unrelated capabilities (books/authors/translators/trending — different data, different audiences). Title-search and Content-search here are the **same** capability (find a chapter in this book) with two search strategies — exactly like `RawSearchPanel` already toggles hybrid/lexical/granularity/surface **inside one panel** without anyone treating that as 4 panels. CB2's file-split is about **build/test hygiene**, not a DOCK-8 requirement to split catalog entries.

## Task breakdown

### Phase A — Backend (book-service, single serial builder — see Coordination note)

| # | Task | File(s) |
|---|---|---|
| A1 | `word_count` column + batched backfill (loop by `chapter_id` range, e.g. 500 rows/batch, to avoid a full-table lock) + `fn_recompute_chapter_word_count()` trigger on `chapter_blocks` (mirrors `fn_extract_chapter_blocks`/`trg_extract_chapter_blocks`), multilingual char-vs-word counting ported from `computeReadingStats`'s CJK heuristic. | `services/book-service/internal/migrate/migrate.go` |
| A2 | `sort` param on `listChapters` (offset) and `listChaptersKeyset` (cursor, restricted to stable-sort keys per CB7) + expose `word_count` on the `Chapter` JSON response. | `services/book-service/internal/api/server.go` |
| A3 | Bulk status-change endpoint: `PATCH /v1/books/{book_id}/chapters/bulk-status` (or similar), per-id outcome response (CB5). | `services/book-service/internal/api/server.go`, new `bulk_chapters.go` (or co-located) |
| A4 | Bulk zip export endpoint, `archive/zip` streaming reusing `exportChapter`'s existing per-chapter text source. | `services/book-service/internal/api/server.go` or new `export.go` |
| A5 | `search.go` OFFSET fix on all 3 SQL variants (flat block, chapter-ranked, canon) — document the re-ranking caveat (CB6) in the endpoint's own comment. | `services/book-service/internal/api/search.go` |
| A6 | FE `booksApi` client methods for A2 (`sort` param)/A3/A4/A5 (offset). | `frontend/src/features/books/api.ts` |

**Phase A gate:** Go unit + integration tests (real Postgres, matching this repo's DB-gated test convention) for the migration/backfill/trigger (word_count stays correct across insert/update/delete of `chapter_blocks`, multilingual fixtures CJK+Latin), the bulk endpoints' per-id outcome shape, and `search.go`'s OFFSET behavior. `python`/Go equivalent of "live smoke" per this repo's cross-service VERIFY convention.

### Phase B — Frontend (chapter-browser dock panel)

| # | Task | File(s) |
|---|---|---|
| B1 | New `ChapterBrowserPanel.tsx` (shell: `useStudioPanel('chapter-browser', ...)`, mode-toggle state, filter/sort state) + `ChapterBrowserTitleView.tsx` (CB2 — migrates `ChapterListBrowser` in, extended with sort dropdown, word-count column, date-range filter, group-by-arc via CB8's hook). | new `features/studio/panels/{ChapterBrowserPanel,ChapterBrowserTitleView}.tsx` |
| B2 | New `ChapterBrowserContentView.tsx` (CB2 — reuses `useRawSearch` + a restyled `RawSearchResultCard`-equivalent row density matching the mock's snippet-card design). | new `features/studio/panels/ChapterBrowserContentView.tsx` |
| B3 | New `useChapterBrowserGroups.ts` hook (CB8). | new `features/books/hooks/useChapterBrowserGroups.ts` |
| B4 | Bulk-action bar wiring: Translate → open `TranslateModal` with `preselectedChapterIds` (reuse, zero new code beyond passing the set); Set status → new bulk-status API call (A3); Export → new bulk-zip API call (A4), triggers a browser download of the streamed zip; Trash → existing single-chapter trash looped OR the new bulk-status endpoint if it also covers `lifecycle_state='trashed'` (decide in BUILD once A3's exact shape is settled — avoid a 5th bulk-trash-specific endpoint if A3 already covers it). | within `ChapterBrowserPanel.tsx` |
| B5 | Catalog entry `chapter-browser` (palette + agent enum per CB1) + i18n keys ×4 locales. | `features/studio/panels/catalog.ts`, `frontend/src/i18n/locales/*/studio.json`, `services/chat-service/app/services/frontend_tools.py`, `contracts/frontend-tools.contract.json` |

**Phase B gate:** DOCK-1..11 self-check (mirroring the systematic per-panel verification this session already did for Jobs/Books/Leaderboard, not just self-report — see [[checklist-is-self-report-enforce-by-tests]]); unit tests per new file; `dockablePanelHygiene`/`panelCatalogContract` green; `/review-impl`; **live browser E2E this time** (not just unit tests — this task's own retro flagged DOCK-11's E2E gap on the last 3 panels; don't repeat it here, at minimum smoke Title-mode search+filter+sort and Content-mode search+jump on a real running stack).

## Coordination

Phase A (BE) touches `services/book-service/internal/api/server.go` in several places (new routes + `sort` param + `word_count` exposure) — **keep this to ONE serial builder** (not fanned out to parallel agents) since multiple hypothetical concurrent edits to the same Go file's router-registration block is exactly the kind of collision this session hit repeatedly in the FE spine files this cycle; book-service is not currently contended by any other known concurrent session, so there's no *external* race to guard against here, only a *self-inflicted* one to avoid by not parallelizing within one file unnecessarily.

Phase B (FE) can fan out same as the Jobs/Books/Leaderboard precedent (CB2's file split makes B1/B2/B3 genuinely disjoint), with B5's spine-file edits held serial per the same discipline established in [`2026-07-04-utility-panels-fanout.md`](../../plans/2026-07-04-utility-panels-fanout.md) (re-diff `catalog.ts`/i18n/enum immediately before applying — other concurrent sessions may still be active on this branch).

**Sequencing: Phase A before Phase B's word_count/bulk-status/bulk-export pieces** — B1's sort-by-word-count and word-count column, and B4's status/export bulk actions, need A's endpoints to exist first. B1's base migration (title search/filter/paging), B2 (content search), and B3 (arc grouping) do NOT depend on Phase A at all and can start immediately/in parallel with Phase A.

## Out of scope

- Cross-panel filter sync between `chapter-browser` and `ManuscriptNavigator` (e.g. clicking a row in one highlighting it in the other) — not requested, no use case identified yet.
- A true keyset-stable Content-mode search (would need a ranking-stable pagination scheme beyond LIMIT/OFFSET) — CB6 ships the honest, simpler fix; revisit only if real usage shows the instability matters in practice.
- Rewriting `ManuscriptNavigator` to consume the new `word_count`/bulk endpoints — out of scope, different panel, different job.
