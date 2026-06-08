# PLAN — Raw Chapter Search · Phase 1 (Lexical MVP)

- **Date:** 2026-06-07
- **Branch:** `raw-search/foundation` (off `origin/main`)
- **Spec:** `docs/specs/2026-06-07-raw-search.md` (DESIGN LOCKED — PART I + ATAM-lite eval PART II; all 7 confirm-at-BUILD resolved)
- **Scope:** **Phase 1 only** — the lexical leg + minimal FE. No semantic leg, no knowledge-service, no gateway change. (Phases 2–3 get their own plans.)
- **Size:** **M** — `book-service` (Go) + `frontend`; 1 idempotent additive DDL migration; 1 external endpoint. **Single backend service ⇒ no cross-service live-smoke** (single-service smoke recommended). Eval verdict: **does NOT need `/amaw`** (additive, non-destructive, trivially reversible — see Rollback in §2).

---

## 0. Ground-truth confirmed during PLAN (reads, not summaries)

| Fact | Location | Impact |
|---|---|---|
| External route group `/v1/books/{book_id}` (chi subrouter) | `book-service .../api/server.go:182` | Add `r.Get("/search", s.searchChapterText)` here (sibling of `/`, `/chapters`). |
| Auth + ownership pattern | `requireUserID` server.go:261; `ensureOwnerBook` server.go:296 (`SELECT lifecycle_state FROM books WHERE id=$1 AND owner_user_id=$2`) | Reuse verbatim — JWT `sub` → owner, 404 on mismatch. This *is* the tenant gate (QA10/INV-4). |
| Migration mechanism | `migrate.go:10` `const schemaSQL` (one idempotent-DDL string run on startup); `triggerSQL` is a *separate* const Exec'd at :298 | Append `CREATE EXTENSION` + GIN index to `schemaSQL` (all `IF NOT EXISTS`). |
| Migration assertions test | `migrate_test.go` asserts specific SQL substrings exist | Add asserts for the new extension + index lines. |
| Draft surface table | `chapter_blocks(chapter_id, block_index, block_type, text_content, content_hash, heading_context)` migrate.go:93; kept fresh by trigger `trg_extract_chapter_blocks AFTER INSERT/UPDATE OF body ON chapter_drafts` | The lexical source. `text_content` = verbatim block prose; `block_index`/`heading_context` give location + context. **Draft surface only** (trigger reads `chapter_drafts.body`). |
| Chapters table | `chapters(id, book_id, title, sort_order, editorial_status, lifecycle_state)` migrate.go:38; `idx_chapters_editorial(book_id, editorial_status)` | Join for title/sort_order/status; filter `lifecycle_state='active'`. |
| Postgres image | `postgres:18-alpine` (infra/docker-compose.yml:17) | `pg_trgm` ships in contrib; `CREATE EXTENSION` works (also an RDS trusted extension for prod). |
| FE HTTP client | `frontend/src/api.ts` `apiJson<T>(path, {token})` — relative `/v1`, Bearer JWT, auto-401 clear | All feature `api.ts` import this. |
| FE conventions | TanStack Query v5; closest models: `features/knowledge/hooks/useDrawerSearch.ts`, `components/DrawerResultCard.tsx`, `components/shared/FilterToolbar.tsx`, `lib/highlightTokens.ts` | Mirror these for `features/raw-search/`. |
| FE proxy | `vite.config.ts` `/v1 → http://localhost:3123` (gateway) | No FE infra change; gateway already proxies `/v1/books/*` → book-service. |

---

## Design adjustments (surface to PO before BUILD)

> **PO-acknowledged 2026-06-07** — ADJ-1..4 approved as recommended.

- **ADJ-1 (lexical match = ILIKE primary + trigram-similarity rank).** `pg_trgm`'s `%` operator (and `similarity()`) needs shared trigrams; for short CJK terms (1–2 chars) recall is weak. So the **exact-substring `ILIKE '%'||$q||'%'`** clause is the *primary* matcher (catches `乾坤圈` regardless of trigram threshold), and `similarity()` only **ranks**. Exact-substring hits sort first. The similarity threshold is a knob (**SP1/SP2**) — start with defaults, expose as config later.
- **ADJ-2 (short-query / GIN acceleration).** The `gin_trgm_ops` index accelerates `ILIKE`/`%` only for patterns with ≥1 full trigram (~≥3 chars). For 1–2-char queries Postgres falls back to a scan — **but it's `book_id`-scoped**, so bounded. Accept for v1 (R4); enforce a min query length of **1** (no artificial 3-char floor — exact-term hunt needs short CJK terms) and rely on book-scoping for bounds.
- **ADJ-3 (surface = `draft` only in v1).** Per spec §3.1/§3.5, the lexical leg reads `chapter_blocks` = draft surface. The `surface` param is accepted (forward-compat) but `canon`/`all` yield draft hits in v1; canon-lexical is deferred (spec open #2). Every hit is labelled `surface:"draft"`, `matchType:"lexical"`.
- **ADJ-4 (rune-based highlight offsets, not `ts_headline`).** `ts_headline` is `tsvector`-oriented (useless for trigram/CJK). The handler computes the match span itself and returns **rune** (not byte) offsets so the React layer renders multibyte CJK correctly. (Go `strings.Index` gives byte offsets → convert to rune count.)

---

## 1. Phases & order

```
BE-1 (migration: pg_trgm + GIN) ──► BE-2 (endpoint: SQL + snippet + rune-offset highlight) ──► FE-1 (feature + mount) ──► VERIFY
```
BE-1 must land before BE-2 (the handler relies on the index for acceptable latency). BE-1+BE-2 may share one commit (book-service slice); FE-1 is a second commit.

---

## 2. BE-1 (book-service) — migration  [TDD]

**File:** `services/book-service/internal/migrate/migrate.go` (append to `schemaSQL`), `migrate_test.go`.

1. Append to the end of `schemaSQL`:
   ```sql
   -- ── Raw search (Phase 1): trigram index over draft chapter text ──────────
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE INDEX IF NOT EXISTS idx_chapter_blocks_trgm
     ON chapter_blocks USING gin (text_content gin_trgm_ops);
   ```
2. Idempotent + additive: re-runs are no-ops; no data transform; no column/table change.

**Rollback:** `DROP INDEX IF EXISTS idx_chapter_blocks_trgm;` (the extension is harmless to leave). Zero data risk ⇒ no `/amaw`, no backfill, no downtime.

**Tests (Go):**
- `migrate_test.go` asserts `schemaSQL` contains `CREATE EXTENSION IF NOT EXISTS pg_trgm` and `idx_chapter_blocks_trgm ... gin (text_content gin_trgm_ops)` (mirror existing SQL-substring asserts).
- (integration, if the suite has a live PG harness) migrate runs clean twice (idempotency).

## 3. BE-2 (book-service) — lexical search endpoint  [TDD]

**Files:** `services/book-service/internal/api/server.go` (route at :182 + new handler, or a new `search.go` in the same package), `*_test.go`.

1. **Route:** under the `/v1/books/{book_id}` group → `r.Get("/search", s.searchChapterText)`.
2. **Handler `searchChapterText`** (mirror `getBook` shape):
   - `ownerID, ok := s.requireUserID(r)`; `bookID := parseUUIDParam(...)`; `ensureOwnerBook(ctx, bookID, ownerID)` → 404 on non-owner (tenant gate).
   - parse `q` (required, trimmed; empty → 400 `BOOK_VALIDATION_ERROR`; **cap length** e.g. 256 runes → SP5), `surface` (default `all`; v1 ignores per ADJ-3), `limit` (default 20, max 100).
3. **Query (parameterized — injection-safe):**
   ```sql
   SELECT cb.chapter_id, c.title, c.sort_order, cb.block_index,
          cb.heading_context, cb.text_content,
          similarity(cb.text_content, $2) AS sim
   FROM chapter_blocks cb
   JOIN chapters c ON c.id = cb.chapter_id
   WHERE c.book_id = $1
     AND c.lifecycle_state = 'active'
     AND (cb.text_content ILIKE '%' || $2 || '%' OR cb.text_content % $2)
   ORDER BY (cb.text_content ILIKE '%' || $2 || '%') DESC, sim DESC, c.sort_order, cb.block_index
   LIMIT $3;
   ```
4. **Per-row post-process (Go):** locate the match in `text_content` (exact substring, then fallback to first shared run); compute **rune** `charStart/charEnd`; build a windowed `snippet` (±~80 runes around the match, or whole block if short) with `highlights` offsets *relative to the snippet*; `score` = `sim` (+1.0 boost flag for exact-substring).
5. **Response:**
   ```jsonc
   { "query": q, "mode": "lexical",
     "results": [ { "chapterId", "chapterTitle", "sortOrder",
       "surface": "draft", "matchType": "lexical", "score",
       "snippet", "highlights": [[s,e]],
       "location": { "blockIndex", "charStart", "charEnd" } } ] }
   ```

**Tests (Go):**
- ownership: non-owner / unknown book → 404; missing JWT → 401.
- validation: empty `q` → 400; over-length `q` → 400; `limit` clamp.
- match: seeded book with a block containing `乾坤圈` → returns that block, `surface:"draft"`, `matchType:"lexical"`, snippet contains the term, `highlights` span the term (**rune offsets** — assert correct for the multibyte term).
- ranking: exact-substring hit sorts above a mere trigram-similar hit.
- scope: a block in *another* user's book / a trashed chapter is never returned.
- highlight unit: pure function `(text, q) → []rune-range` table test incl. CJK + repeated matches + no-match.

## 4. FE-1 (frontend) — `features/raw-search/`  [TDD]

**Files (new):** `frontend/src/features/raw-search/{api.ts, types.ts, hooks/useRawSearch.ts, components/RawSearchPanel.tsx, components/RawSearchResultCard.tsx}` + one mount point.

1. **`types.ts`:** `RawSearchHit` (chapterId, chapterTitle, sortOrder, surface, matchType, score, snippet, highlights, location), `RawSearchResponse`, `RawSearchParams`.
2. **`api.ts`:** `rawSearchApi.search(bookId, { q, surface, limit }, token)` → `apiJson<RawSearchResponse>(\`/v1/books/${bookId}/search?...\`, { token })` (mirror `glossary/api.ts`).
3. **`hooks/useRawSearch.ts`:** TanStack `useQuery` (mirror `useDrawerSearch.ts`) — `queryKey: ['raw-search', userId, bookId, q, surface, limit]`, `enabled: !!token && q.trim().length >= 1`, `retry: false`, `staleTime: 30_000`. Returns `{ hits, isLoading, isFetching, error, disabled }`.
4. **`components/RawSearchResultCard.tsx`:** mirror `DrawerResultCard` — verbatim snippet with the matched span highlighted (reuse/adapt `lib/highlightTokens.ts` or render `highlights` offsets), a **`draft` status badge** (`StatusBadge`), `matchType` chip, click → `onJump(chapterId, blockIndex)` (jump-to-source).
5. **`components/RawSearchPanel.tsx`:** search input (mirror `FilterToolbar` classes) + results list (`EmptyState` when none, `Skeleton` while loading, `degraded`/error inline). Render-only; logic via `useRawSearch`.
6. **Mount (confirm host at BUILD):** add to the **book workspace** (reader/editor) as a side-panel/modal so it's usable while writing — *read `features/books` page structure at BUILD to pick the exact host*; fallback = a route `/books/:bookId/search` in `App.tsx` under `RequireAuth`. Jump-to-source navigates to the chapter + scrolls to `blockIndex`.

**Tests (vitest):**
- `useRawSearch`: disabled when `q` empty; fires query + returns hits when `q` set (mock `apiJson`); error surfaced.
- `RawSearchResultCard`: renders verbatim snippet + highlighted span + `draft` badge; click fires `onJump` with (chapterId, blockIndex).
- `RawSearchPanel`: empty state, loading skeleton, list render; no crash on zero results.

## 5. VERIFY (evidence gate)

- **Unit:** Go (book-service) + vitest (FE) green — paste counts.
- **Single-service live smoke** (not cross-service, but prove it really works): book-service + gateway + FE up → open a book with a Chinese draft chapter → search an exact term (e.g. `乾坤圈`) → assert a `draft` hit with correct verbatim snippet + highlight + working jump-to-source.
  - Evidence token: `live smoke: raw lexical search returns a CJK draft hit w/ rune-correct highlight + jump-to-source` (or `live infra unavailable: <reason>` + defer row).
- Confirm latency feels interactive on a real-sized chapter set (R4 sanity).

## 6. Risk register (from eval PART II, scoped to Phase 1)

- **R1/SP1 — CJK trigram recall.** → ILIKE-primary (ADJ-1); **measure recall on 封神演义 during VERIFY**; parser upgrade (`zhparser`/Lucene-CJK) held for a later phase.
- **R4 — trigram perf at scale.** → `book_id`-scoped + `LIMIT` + GIN; sanity-check latency at VERIFY; chapter-range scope is a later option.
- **R5/INV-4 — tenant isolation.** → `ensureOwnerBook` before any query; test cross-tenant + trashed exclusion.
- **TP1/R3 — provenance.** → every Phase-1 hit is `surface:"draft"` by construction (chapter_blocks); no status-derived labeling (ADJ-3).
- **ADJ-4 — rune vs byte offsets.** → unit-tested highlight on multibyte CJK.
- **Out of scope (Phase 2+):** semantic leg, RRF, knowledge orchestrator, canon-lexical, char-offset cross-leg dedup, rerank.

## 7. Definition of Done

- [x] ADJ-1..4 acknowledged by PO (2026-06-07).
- [ ] BE-1 (migration) + BE-2 (endpoint) + FE-1 implemented, tests green (counts pasted).
- [ ] `surface:"draft"` + `matchType:"lexical"` on every hit; verbatim snippet + rune-correct highlight + jump-to-source working.
- [ ] Non-owner / trashed / cross-tenant never leak (tested).
- [ ] Single-service live smoke passed on a CJK book (or explicit deferral row).
- [ ] `docs/sessions/SESSION_HANDOFF.md` updated; committed per phase boundary (BE slice, then FE).
