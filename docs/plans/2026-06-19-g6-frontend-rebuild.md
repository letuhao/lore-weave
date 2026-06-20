# G6 — Frontend rebuild (genre·kind·attribute tiered model)

**Status:** BUILD · **Size:** XL · **Owner:** frontend/src/features/glossary
**Authority:** spec [`…genre-kind-attribute-tiering.md`](../specs/2026-06-19-genre-kind-attribute-tiering.md) · build plan [`…genre-kind-attribute-build.md`](2026-06-19-genre-kind-attribute-build.md) §8 (G6)
**Drafts:** `design-drafts/glossary-tiering/` — index (model), 01-manage, 02-attribute-matrix, 03-entity-form, 04-sync
**Backend:** G1–G5 shipped — contract `contracts/api/glossary-service/kinds_genres_attributes.yaml`.

> The last epic milestone. Rebuilds the glossary kind/genre/attribute UI from the tiered
> System/User/Book model. Replaces the OLD flat model UI (`KindEditor.tsx`, `GenreGroupsPanel`).

## FE conventions (verified from the codebase)
- **Route:** `/books/:bookId/glossary` → `BookDetailPage` → `pages/book-tabs/GlossaryTab.tsx` (tabbed; `view` state). `bookId` from `useParams`.
- **API:** `apiJson<T>(path, { token, method, body })` from `src/api.ts`; base `/v1/glossary` (`BASE` in `features/glossary/api.ts`); JWT via `useAuth().accessToken`.
- **State:** `@tanstack/react-query` for server state (queryKey scoped by feature+resource+bookId; `invalidateQueries` on mutate). Simple hooks use useState/useEffect.
- **MVC:** hooks own state/effects/mutations (≤200 lines); components render-only props-driven (≤100 lines); no feature `context/` dir today (add one only if a screen needs cross-component volatile state). Toasts via `sonner`; icons `lucide-react`; Tailwind only (no shadcn prebuilts); shared `components/shared/{ConfirmDialog,Skeleton,EmptyState}` + `pagination/Pager`.
- **i18n:** `react-i18next`; new namespace `glossaryTiering` under `src/i18n/locales/{en,vi,ja,zh-TW}/`; tests return keys.
- **Tests:** Vitest + @testing-library/react + `vi.mock('../../api')`; QueryClient wrapper.

## Tier visual coding (from drafts)
`tier-system` slate · `tier-user` indigo (`#6366f1`) · `tier-book` sky (`#0ea5e9`). Field-type badge `ft` (monospace). Conflict=amber, removed/retired=rose, added=green, selection=indigo left-border.

## Sub-milestones (each VERIFY-gated: tsc + vitest green; commit at each)

| Sub | Ships | Files (≈) |
|-----|-------|-----------|
| **G6a** | **Data layer** — extend `api.ts` + `types.ts` with the tiered surface: standards (`getGenres`, user-genres CRUD+trash, `getSystemAttributes`, user-attributes CRUD, user-kinds + kind-genres), book (`adoptOntology`, `getBookOntology`, book genre/kind/attribute CRUD, `setActiveGenres`, `setKindGenres`), sync (`getSyncAvailable`, `applySync`). Types for every response/request. | api.ts, types.ts |
| **G6b** | **Manage workspace** (01) — `useBookOntology` (adopt+ontology+CRUD via react-query), `useStandards` (merged genres / system+user attrs for clone), components: `ManageWorkspace`, `OntologyColumn` (genre/kind/attr lists w/ tier chips), `AttributeEditorPanel` (system read-only + user/book editable), `AdoptPicklistModal`, `TierChip`, `FieldTypeBadge`. | ~8 |
| **G6c** | **Attribute matrix** (02) — `AttributeMatrix` (kind × active-genres table, keep-both namespacing), `MatrixCellInspector` (override-into-tier), `KindSelect`, `ActiveGenrePills`. Reuses `useBookOntology`. | ~4 |
| **G6d** | **Entity form** (03) — `useEntityForm` (merged (kind×genre) attrs from ontology, per-entity genre override D2, namespaced conflict fields), `TieredEntityForm`, `GenrePillSelector`, dynamic `AttributeField` (text/textarea/select/etc.). Wires `POST …/entities` + `PATCH …/entities/{id}/genres`. | ~5 |
| **G6e** | **Sync** (04) — `useSync` (`available` + per-row choice state + `apply`), `SyncScreen`, `SyncUpdateList`, `SyncDiffTable` (keep_mine/take_theirs/skip/adopt/drop segmented), `RetiredSourceCard`. | ~5 |
| **G6f** | **Wire + cleanup** — mount the 4 screens into `GlossaryTab` (new `view`s), retire `KindEditor.tsx` + `GenreGroupsPanel`/`GenreFormModal` + `useEntityKinds` (old model), add `glossaryTiering` i18n ×4 locales, tests for each hook+key component. | wiring + locales + tests |

## Decisions
- **No new gateway/contract work** — backend frozen (G1–G5). FE is additive in `features/glossary/` + a new i18n namespace.
- **react-query everywhere** for the ontology/sync server state (the drafts are read-heavy with mutations that must invalidate). Matches `useUnknownReview`.
- **One `useBookOntology` hook** is the shared source for G6b/G6c/G6d (single `GET /ontology` query, mutations invalidate it).
- **Cleanup is real** (R3 broken-window closes here): the old flat-model files are deleted in G6f, not left dual.
- **Grant-gating is server-side** — FE shows controls optimistically; a 403 surfaces as a toast (Manage-only writes). Mirror `useUnknownReview` error handling.

## VERIFY per sub-milestone
`npm --prefix frontend run test -- <files>` (vitest) + `tsc --noEmit` (my files; pre-existing @dnd-kit errors ignored) + a Playwright smoke at G6f on the test account (multi-genre form + matrix + adopt + sync).
