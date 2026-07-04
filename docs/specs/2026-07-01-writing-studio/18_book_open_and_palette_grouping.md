# 18 · Book-Open Routing + Command Palette Domain Grouping

> Component of [Writing Studio (v2)](00_OVERVIEW.md). Status: ✅ built 2026-07-05.
> Size: **S** (2 side effects: routing default + palette data shape — both additive, no migration, no schema).

## What this is

Two small, independent fixes bundled because they're both "Studio is now the default surface"
cleanup, both low-risk, both shippable before [#19](19_onboarding_and_user_guide.md):

1. Opening a book from the workspace browser (`/books` list) goes straight to Studio instead of
   the classic tabbed `BookDetailPage`.
2. The Command Palette's "Panels" group (currently one flat list of ~46 items) splits into
   domain-area sub-groups.

## Part A — Book-open routing

| # | Decision |
|---|---|
| A1 | `BooksPage.tsx:142` row `<Link to={...}>` changes from `` `/books/${book.book_id}` `` to `` `/books/${book.book_id}/studio` ``. This is the **only** entry-point change. |
| A2 | Classic `BookDetailPage` + its sub-routes (`/books/:bookId`, `/glossary`, `/translation`, `/kg-ontology`, `/enrichment`, `/sharing`, `/settings`, `/wiki` in `App.tsx:161-168`) are **not** deleted, redirected, or deprecated this cycle — they stay reachable by direct URL. Every panel-equivalent already exists in the Studio catalog (glossary/translation/kg-*/sharing/book-settings/wiki), so nothing is lost by no longer routing there by default — it's a discoverability change, not a capability change. |
| A3 | No new UI affordance back to the classic view is added. The ~30 existing internal deep-links to `/books/:bookId/<tab>` (translation viewer, wiki workspace, reader TOC, etc. — grepped, unchanged) keep working as-is; this milestone touches only the workspace-browser row link. |
| A4 | The bare `/books/:bookId` route itself (no `/studio` suffix) is **unchanged** — still resolves to `BookDetailPage` (Chapters tab). Only the browser's row `Link` target moves. |
| A5 | `PublicBookDetailPage.tsx` (the unauthenticated/shared public book view) is a deliberately separate route, untouched by this change — Studio requires owner/collaborator auth, so public viewers were never going to land there anyway. |

**Verified, not assumed — other paths into a book:** traced `handleCreate` in `useBooksList.ts` (the
"new book" dialog submit handler) — it closes the dialog and calls `load()` to refresh the list; it
does **not** navigate anywhere. The new book still requires a row click, same as any existing book,
so A1's single link change covers book-creation too. No other in-app call site calls
`navigate()`/`<Link>` to a bare `/books/:bookId` (checked recycle-bin restore, trash hook — neither
navigates). If a future feature adds a new "open a book" entry point, it must target `/studio` to
stay consistent with this decision — flag at review if one appears pointed at the bare route.

**Why not redirect the bare route too:** that would retire the classic surface's only remaining
entry point in one step, which is a bigger, riskier call (do all 46 catalog panels truly have
parity with every classic tab path? — not yet formally audited). Gate #1 (out of scope) applies:
that's the "retire classic entirely" track, tracked separately, not bundled here.

## Part B — Command Palette domain grouping

Current state (confirmed in code): `StudioPanelDef` has no category; `useStudioCommands.ts`
hardcodes every panel command into one `group('panels', 'Panels')` bucket. `StudioPaletteShell.tsx`
already renders sticky group headers keyed on adjacent-row `group` changes (`entry.group !==
lastGroup`) — **no new palette UI work needed**, only data.

| # | Decision |
|---|---|
| B1 | `StudioPanelDef` gains `category: StudioPanelCategory` (required for all non-hidden panels going forward; `welcome` and other `hiddenFromPalette` panels may omit it). |
| B2 | Category enum + i18n key (`studio.palette.group.<key>` — reuses the existing `palette.group.*` namespace the `group()` helper already reads from, rather than introducing a second `palette.category.*` namespace + helper), assigned per existing catalog clustering: |

| Category id | i18n key | Panels |
|---|---|---|
| `editor` | `palette.group.editor` | compose, editor, planner, steering, chapter-browser, context-inspector |
| `storyBible` | `palette.group.storyBible` | glossary, glossary-ontology, glossary-unknown, glossary-ai-suggestions, glossary-merge-candidates, wiki |
| `knowledge` | `palette.group.knowledge` | knowledge, kg-overview, kg-entities, kg-timeline, kg-evidence, kg-gap, kg-proposals, kg-schema, kg-graph, kg-insights, kg-jobs, kg-bio, kg-privacy |
| `translation` | `palette.group.translation` | translation |
| `enrichment` | `palette.group.enrichment` | enrichment-compose, enrichment-proposals, enrichment-gaps, enrichment-sources, enrichment-jobs, enrichment-settings |
| `sharing` | `palette.group.sharing` | sharing, book-settings |
| `platform` | `palette.group.platform` | usage, notifications, settings, trash, extensions, proposals |
| `discovery` | `palette.group.discovery` | books, leaderboard-books, leaderboard-authors, leaderboard-translators, leaderboard-trending |
| `jobs` | `palette.group.jobs` | jobs-list |

Params-retargeting singletons (`hiddenFromPalette: true`) — `wiki-editor`, `job-detail`,
`book-reader`, `skill-editor`, `json-editor`, `media-version-history`, `original-source`,
`translation-versions`, `welcome` — get **no** category (never rendered in the palette, so the
field is meaningless for them).

| # | Decision |
|---|---|
| B3 | `useStudioCommands.ts`: the panel-command loop groups by `group(p.category, p.category)` (the same `t('palette.group.'+k, {defaultValue: dflt})` helper the static chrome commands already use) instead of the hardcoded `group('panels','Panels')`. A panel with no `category` (forward-compat guard for anything not yet migrated) falls back to the old generic `Panels` label — never a crash. |
| B4 | **Category display order is fixed, not alphabetical**, and category groups sit directly after `Recent` (highest command volume = primary discovery surface), before `Navigate`/`Layout`: `Recent → Editor → Story Bible → Knowledge → Translation → Enrichment → Sharing → Platform → Discovery → Jobs → Navigate → Layout`. Implemented as a `CATEGORY_ORDER` array; `buildStudioCommands` sorts the panel-derived commands by this order before returning (catalog array order today is only loosely clustered — chapter-browser/context-inspector/extensions/json-editor/media-version-history currently sit outside their natural cluster in `STUDIO_PANELS`, so an explicit sort is required for headers to render correctly, not just an implicit reorder of the catalog itself). |
| B5 | `panelCatalogContract` (the openable-set ↔ `ui_open_studio_panel` enum check) is unaffected — `category` is palette-display metadata only, not part of the agent-facing contract. |
| B6 | **Enforcement is mechanical, not just a code-review convention.** `panelCatalogContract.test.ts` (or a small sibling assertion alongside it) gains: `OPENABLE_STUDIO_PANELS.every(p => !!p.category)`. Without this, a future panel added to the catalog without a `category` silently falls into the generic fallback group (B3) and the whole point of this milestone erodes one panel at a time with no signal. This is the same mechanical-gate pattern this track already uses for DOCK-6/7/9 (`docs/standards/dockable-gui.md`) — a decision without a test is not locked. |

## i18n

New keys in `studio.json` × en/ja/vi/zh-TW: `palette.group.{editor,storyBible,knowledge,
translation,enrichment,sharing,platform,discovery,jobs}` — 9 keys × 4 locales = 36 strings, short
labels (2-3 words each), no fanout needed.

## Dependencies

None new — reuses existing `StudioPanelDef`, `useStudioCommands.ts`, `StudioPaletteShell.tsx`.

## Done-criteria

1. Clicking a book row in `/books` opens `/books/:bookId/studio` directly.
2. Direct navigation to `/books/:bookId` (and its sub-tabs) still renders the classic page — no regression.
3. ⌘⇧P palette shows 9 named sub-groups under panel commands instead of one flat "Panels" list; group headers render correctly (no interleaving) for all 9 categories.
4. Unit tests: `buildStudioCommands` groups by category in the fixed order; a panel missing `category` still returns a valid command (fallback group); B6's `every(p => !!p.category)` assertion passes for all 46 openable panels.
5. E2E: book-open → studio route assertion; palette open → assert category headers present + panel search still works across categories.
6. tsc + eslint clean; `panelCatalogContract` test still green (category doesn't touch the enum).
7. Before merge: grep existing palette E2E/unit specs for any assertion that depends on the old flat "Panels" group label or on catalog-array order — B4's explicit sort changes visible command order, so an order-sensitive assertion elsewhere would false-fail, not indicate a real regression.

**Built 2026-07-05 — evidence:**
- Unit: 690/690 passing across `src/features/studio` + `src/pages/__tests__` (includes B6's mechanical category-required assertion, the updated `context-inspector` group-label expectation, and new grouping/sort/fallback tests in `useStudioCommands.test.ts`). tsc + eslint clean on all touched files.
- Live E2E (Playwright against the real vite dev server, not mocks): `writing-studio.spec.ts` gained 2 new tests (row→Studio; `BooksPage.openBook()`→classic page, no `/studio` suffix) — both pass. `studio-palette.spec.ts` gained 1 new test asserting 3 distinct category headers render and the old flat "Panels" header is gone — passes.
- **Found + fixed incidentally:** `demo-pipeline-3a/3b/3c.spec.ts` all call `BooksPage.openBook()` after `createBook()`; the row's click target moved to `/studio`, so `openBook()` was changed to navigate directly to the classic route (extracted from the row's `href`, `/studio` suffix stripped) instead of clicking — zero changes needed to the 3 spec files themselves. A new `openBookInStudio()` method covers the new default path.
- **Found, NOT fixed (out of scope, tracked in SESSION_HANDOFF):** `demo-pipeline-3a/3b/3c.spec.ts` all fail earlier than the `openBook()` step, at `BooksPage.createBook()` — `languageInput.fill()` errors because the language field is a `<select>`, not an `<input>`. Confirmed pre-existing (this milestone never touched the create-book dialog or that POM method) and unrelated to book-open routing — belongs to a different concern entirely.

## Out of scope

- Retiring classic `BookDetailPage` routes entirely (separate, larger decision — needs a per-tab parity audit first).
- Re-theming the palette shell UI beyond group headers (already supported).
- The Studio onboarding fork / user guide — see [#19](19_onboarding_and_user_guide.md).
- Fixing `BooksPage.ts`'s `createBook()` `<select>`-vs-`.fill()` bug (found incidentally above) — different concern, tracked separately.
