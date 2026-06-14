# Plan — Glossary list overhaul (pagination · sort · raw search · shared browser)

**Date:** 2026-06-14 · **Branch:** `feat/auto-draft-factory-gaps` · **Status:** PLAN ONLY (no build yet — user: "cả FE/BE nhưng chỉ lên plan")

## 1. Problem

A book with 4000+ chapters can grow a glossary to **20K+ entities**. The current
`GlossaryTab` is unusable at that scale:

- **Loads only the first 100 rows** (`listEntities({limit:100, offset:0})`) — the
  other 19,900 are unreachable except by narrowing search/filter.
- **No pagination UI** (the backend already returns `total` + accepts `limit`/`offset`).
- **No sort UI**; backend sort is **only `updated_at` asc/desc**.
- **Search is plain `ILIKE '%q%'`** on the `name`/`term` original_value (+ the active
  display-language translation) — no exact/raw mode, no alias/all-attribute coverage,
  and **no trigram index** → a sequential scan per keystroke (it also refetches on
  every keystroke, no debounce).

## 2. Goal

Make the glossary list scale to 20K+ with: server-side pagination, multi-column
sort, a **raw lexical search mirroring the chapter raw-search**, and the list
extracted into a reusable browser component — FE + BE, phased so the FE-safe work
lands without waiting on the RAID-owned backend file.

## 3. Current state (verified in code)

### Backend — `services/glossary-service/internal/api/entity_handler.go` `listEntities`
- Route: `GET /v1/glossary/books/{book_id}/entities`
- Filters (server-side): `kind_codes`, `status`, `chapter_ids` (or `unlinked`),
  `search` (ILIKE on `entity_attribute_values.original_value` for `ad.code IN ('name','term')`,
  + `attribute_translations.value` when `display_language` set), `tags` (`@>`).
- **Pagination:** `limit` (default 50, **max 200**), `offset`; returns `total` (COUNT).
- **Sort:** only `ORDER BY e.updated_at DESC` (default) / `updated_at_asc`.
- ⚠️ **RAID is actively editing this service** (entity_stats_handler.go + server.go) →
  backend changes here must be coordinated / merge-risk-managed.

### Frontend — `frontend/src/pages/book-tabs/GlossaryTab.tsx` + `features/glossary/api.ts`
- `glossaryApi.listEntities` already plumbs `limit/offset/sort/search/displayLanguage`.
- `GlossaryTab` hardcodes `limit:100, offset:0`; no Pager, no sort control; search box
  writes `filters.searchQuery` → server (no debounce). Has filter panel + multi-select
  + bulk status + Gmail-style "select all N" loop-fetch.

### Reference — chapter raw search — `services/book-service/internal/api/search.go`
- `GET /v1/books/{book_id}/search?q=&limit=&surface=&granularity=` (mode=lexical).
- **ILIKE exact-substring is PRIMARY** (escaped via `escapeLikePattern`, catches short
  CJK terms trigram misses); `similarity()` / `%` trigram only **ranks**; both legs use
  the `idx_chapter_blocks_trgm` GIN index. Exact match boosts `score = 1 + sim`,
  `relevance = 1.0`. Returns verbatim `snippet` + **rune-offset** `highlights` +
  `location`. Query cap 256 runes (cost/injection guard). Pure `buildLexicalHit` for
  unit-testability. Spec: `docs/specs/2026-06-07-raw-search.md`.

## 4. Design

### Feature A — Server-side pagination (FE-only; backend already supports)
- Replace the hardcoded `offset:0/limit:100` with page state. Reuse the shared
  `<Pager>` + a server-paged hook (NOT `usePagedList`, which slices a client array):
  new `useServerPagedQuery` wrapping the react-query call with `page`/`pageSize` →
  `offset = page*pageSize`, `pageCount = ceil(total/pageSize)`.
- Page-size selector (50 / 100 / 200 — backend max is 200).
- Show "X–Y of N". Reset to page 0 when filters/search/sort change (the query key
  changes anyway; clamp page if it lands past the new last page).
- Keep "select all N" loop-fetch (already paginates) for cross-page bulk.

### Feature B — Sort (FE UI + BE extension)
- **FE:** a sort dropdown / clickable column headers. Sort key + direction → `sort` param.
- **BE (`entity_handler.go`):** extend the `sort` whitelist beyond `updated_at`:
  `name` (display/original — sort by the `name`/`term` `original_value`, or the
  display-language translation when set), `kind` (`ek.sort_order`/`ek.name`),
  `status`, `chapter_link_count`, `evidence_count`, `created_at`, `alive`.
  Whitelist-mapped to fixed `ORDER BY` clauses (no string interpolation of user input).
  When `search_mode=raw`, default sort = **relevance** (score desc), tiebreak name.
- Counts (`chapter_link_count`, `evidence_count`) already exist in the row projection
  — confirm they're sortable without a heavy subquery-per-row (may need a LATERAL or
  precomputed count column; note for the BUILD spike).

### Feature C — Raw search (BE new + FE UI) — mirrors chapter raw search
The user's ask: "we already have chapter raw search — build a similar one." Mirror
`search.go`'s lexical leg, adapted to the entity text surface.

- **Surface searched:** the entity's lexical text —
  `entity_attribute_values.original_value` across **all** text attributes (not just
  `name`/`term`: include aliases + every text attr value) **+** `attribute_translations.value`
  (all languages, or the display language when set). Configurable; default = name +
  aliases + translations.
- **Matcher:** ILIKE exact-substring **primary** (escaped, CJK-safe) **+** `pg_trgm`
  similarity for ranking — identical strategy to chapters. Exact boosts score.
- **API shape — extend `listEntities`, don't fork a separate results view.** Glossary
  search must stay *paginated + sortable + selectable* (you search → page → bulk-act),
  unlike the chapter search's standalone results list. So add:
  - `search_mode=simple|raw` (default `simple` = today's behavior; `raw` = the new leg).
  - When `raw`, each returned row carries a `match` object: `{ field_code, snippet,
    highlights: [[start,end]] }` (rune offsets, via a pure `buildEntityMatch` mirroring
    `buildLexicalHit`) so the UI shows *why* an entity matched at 20K scale.
  - `sort=relevance` becomes valid (score desc) and is the default while `raw` searching.
  - Query cap 256 runes (reuse the chapter guard rationale).
- **Alternative considered:** a dedicated `GET .../entities/search` endpoint like
  chapters. Rejected for the primary list (breaks pagination/selection unification);
  could still be added later for an assistant/tool caller.

### Feature D — Shared `<EntityListBrowser>`
- Extract the list scaffold so the other entity-list surfaces
  (`UnknownEntitiesPanel`, `AiSuggestionsPanel`, `MergeCandidatePanel`, the
  `ai-suggested` query) can reuse it. **Per the B1 lesson, extract only the genuinely
  shared shell**, keep divergent bits as props/render-props:
  - Shared: toolbar (search input w/ debounce + sort control + filter slot), body
    (rows via `renderRow` render-prop), footer (`<Pager>` + page-size + "X–Y of N"),
    selection (`Set` + select-all + select-all-N loop-fetch hook).
  - Per-call-site: row content, bulk actions, the specific query fn.
- Build incrementally: first make `GlossaryTab` consume it; migrate the panels only if
  it fits without contortion (don't force-fit — same call as B1's `<ChapterListBrowser>` remainder).

### Performance — migration (glossary-service)
- Add `pg_trgm` extension (if not present) + **GIN trigram indexes** on the searched
  columns: `entity_attribute_values.original_value` and `attribute_translations.value`
  (partial/where-text-attr if feasible). Without this, even today's `ILIKE` is a seq
  scan that won't survive 20K × per-keystroke. This is the single most important BE
  change for scale.

## 5. Phasing (RAID-aware)

| Phase | Scope | RAID risk | When |
|---|---|---|---|
| **P1 — FE-safe** | Pagination UI + page-size + debounce + sort UI wired to the *existing* `updated_at` sorts + `<EntityListBrowser>` extraction (GlossaryTab only) | none (FE only) | build now (separate /loom) |
| **P2 — BE sort** | Extend `sort` whitelist + counts sortability + tests | edits `entity_handler.go` (RAID) | after RAID clears glossary-service, or coordinate |
| **P3 — BE raw search** | `search_mode=raw` lexical leg + `match` payload + trigram migration + FE raw-search toggle & match highlights | edits `entity_handler.go` + migration (RAID) | with/after P2 |
| **P4 — shared reuse** | Migrate Unknown/AiSuggestions/Merge panels onto `<EntityListBrowser>` | FE only | opportunistic |

P1 is independently shippable and removes the worst pain (only-100-rows). P2/P3 are
the RAID-coordinated backend work.

## 6. Testing
- **BE (P2/P3):** Go table tests for each `sort` whitelist value → expected ORDER BY;
  raw-search SQL on a real-PG harness (the glossary suite already has bulk_status_test
  patterns) — exact-substring-primary, trigram ranking, `match` field/snippet/rune
  offsets (mirror `buildLexicalHit` tests), CJK offset correctness, 256-rune cap → 400.
  EXPLAIN to confirm the GIN trigram index is used.
- **FE:** Pager↔server-query wiring (page change → new offset → new rows), page clamp
  on filter change, debounce fires once, sort param plumbed, raw-search `match`
  snippet/highlight render. `<EntityListBrowser>` unit tests (selection, select-all-N).
- **Live smoke:** seed a book to ~20K entities (bulk insert) → page to the last page,
  sort by name/counts, raw-search a CJK token → assert ranked hits + index used.

## 7. Risks / open questions
- **RAID conflict on `entity_handler.go`** — P2/P3 must rebase/coordinate; keep the
  diff surgical (whitelist map + one search branch) to minimize conflict.
- **Counts sortability** — `chapter_link_count`/`evidence_count` may be computed per
  row; sorting on them at 20K may need a precomputed column or LATERAL — spike in P2.
- **Raw-search surface breadth** — searching *all* attribute values + all translations
  is the most useful but the widest scan; the trigram index + the exact-first ILIKE
  keep it bounded. Confirm the default surface (name+aliases+translations) with the user
  at P3 BUILD.
- **`displayLanguage` interaction** — raw search + display-language translation column
  must both be trigram-indexed or one leg falls back to seq scan.

## 8. Acceptance criteria
- Glossary list pages through all 20K (not capped at 100); "X–Y of N" + page-size.
- Sort by name/kind/status/counts/recency/alive (P2) + relevance when raw-searching (P3).
- Raw search: ILIKE-exact-primary + trigram-ranked over name/aliases/translations, each
  hit shows which field matched + a highlighted snippet (P3); GIN trigram index used.
- The list is a reusable `<EntityListBrowser>` consumed by GlossaryTab (P1), extensible
  to the entity panels (P4).
- Backend changes land without breaking the RAID glossary-service work.

## 9. Deferred rows to add to SESSION_HANDOFF
- `D-GLOSSARY-LIST-P1-FE` — pagination/sort-UI/debounce/`<EntityListBrowser>` (FE-safe, buildable now).
- `D-GLOSSARY-SORT-BE` — extend `sort` whitelist + counts sortability (RAID-coordinated).
- `D-GLOSSARY-RAW-SEARCH-BE` — `search_mode=raw` lexical leg + `match` payload + pg_trgm GIN migration (RAID-coordinated).
- `D-GLOSSARY-BROWSER-PANEL-REUSE` — migrate Unknown/AiSuggestions/Merge panels onto the shared browser.
