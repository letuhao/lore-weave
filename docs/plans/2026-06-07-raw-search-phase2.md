# PLAN — Raw Chapter Search · Phase 2 (Hybrid) · slice P2a (backend)

- **Date:** 2026-06-07
- **Branch:** `raw-search/foundation`
- **Spec:** `docs/specs/2026-06-07-raw-search.md` §3.3–3.5 + PART II eval (DESIGN LOCKED)
- **Scope:** **P2a = backend hybrid only.** Adds the semantic leg + RRF orchestrator + the book-service internal lexical mount. **P2b (FE hybrid + fallback) is a separate slice.** No /amaw (PO 2026-06-07 — eval §15: additive/read-only/reversible).
- **Size:** **L** — `book-service` (Go) + `knowledge-service` (Py); new public endpoint + new internal route + fusion; embedding call. **Cross-service (2 svcs) ⇒ live-smoke at VERIFY.**

---

## 0. Ground-truth confirmed during CLARIFY (reads, not summaries)

| Fact | Location | Impact |
|---|---|---|
| Semantic search template (project-scoped) | `knowledge .../routers/public/drawers.py:96-272` | Copy the embed→`find_passages_by_vector`→map flow; adapt project→**book** scope. |
| `embed_query_cached(embedding_client, *, user_id, project_id, embedding_model, message)` → `list[float]\|None` | `knowledge .../context/query_embedding.py:35-69` | Drop-in query embed (TTL cache). Returns None on failure → degrade. |
| `find_passages_by_vector(session, *, user_id, project_id, query_vector, dim, embedding_model, source_type, limit)` | `knowledge .../db/neo4j_repos/passages.py:333` | Semantic leg; filter `source_type="chapter"`. |
| `ProjectsRepo` by-book resolver (`AND book_id = $N`) + `get(user_id, project_id)` | `knowledge .../db/repositories/projects.py:147-152, 189-197` | Resolve `(user_id, book_id)→Project` = ownership gate + `embedding_model`/`embedding_dimension`. **Confirm the exact by-book method name at BUILD.** |
| `BookClient` (pre-set `X-Internal-Token`, graceful None) | `knowledge .../clients/book_client.py:29-355` | Add `lexical_search(book_id, q, limit)`. |
| Public router pattern (`prefix="/v1/knowledge"`, `dependencies=[Depends(get_current_user)]`) + `app.include_router` | `drawers.py:46-50`, `main.py:658` | New `raw_search.py` router, registered in main. |
| book-service `/internal` group (`requireInternalToken`) | `book .../api/server.go:146-170` | Add `r.Get("/books/{book_id}/lexical-search", s.searchChapterTextInternal)`. |
| `searchChapterText` is monolithic (ownership + query in one func) | `book .../api/search.go:139-229` | Extract a shared core (ADJ-1). |

## Design adjustments (PO-ack before BUILD)

- **ADJ-1 (book-service core extraction).** Split `searchChapterText` into: `runLexicalSearch(ctx, bookID, q, limit) ([]map[string]any, error)` (shared query+highlight core, no HTTP/auth) + the external handler (JWT + `ensureOwnerBook` + purge_pending → core) + a new internal handler (token-gated by middleware, **caller-trusted, no ownership re-check**) → core. Both return the **same hit JSON**.
- **ADJ-2 (semantic hit mapping).** A `:Passage` → unified hit: `chapterId=source_id`, `surface="canon"`, `matchType="semantic"`, `score=raw_score` (cosine), `snippet=passage.text`, `highlights=[]` (no exact span — TP2/R2), `location={chunkIndex, sortOrder: chapter_index}`. **`chapterTitle` left null in P2a** (semantic-title enrichment deferred → D-RAWSEARCH-P2-SEMANTIC-TITLES; `BookClient.get_chapter_titles` exists for a later batch-fetch).
- **ADJ-3 (RRF over heterogeneous legs).** Fuse by **rank**, not raw score (cosine vs trigram incomparable): `rrf(d)=Σ 1/(k+rank_leg(d))`, `k=60` (config). Dedup key `(chapterId, surface)`; per-chapter cap **3** (config). Since v1 lexical=draft / semantic=canon (different surfaces), `matchType="both"` won't occur yet (spec TP4) — that's expected.
- **ADJ-4 (degradation matrix).** `mode=hybrid` default. No project for (user,book) → **404 `not_indexed`** (FE falls back to lexical — P2b). Semantic leg returns `[]` on: no embedding model / `embed_query_cached`→None / vector empty / dim mismatch. Lexical leg `None` (book-service down) → semantic-only. Both empty → `200 {results: []}`. Never 500 on a partial-leg failure.

---

## 1. Phases & order

```
BK-1 (book: extract core + internal mount) ──► K-1 (BookClient.lexical_search)
                                               K-2 (fusion: RRF + dedup/cap, pure)
                                                      └──► K-3 (orchestrator endpoint + register) ──► VERIFY (unit + cross-service live-smoke)
```

## 2. BK-1 (book-service) — shared core + internal lexical mount  [TDD]

**Files:** `book .../api/search.go`, `server.go` (route), `search_test.go`.

1. Extract `runLexicalSearch(ctx context.Context, pool, bookID uuid.UUID, q string, limit int) ([]map[string]any, error)` — the SQL + per-row highlight/snippet build (current lines ~174-220). Returns the `results` slice (same maps).
2. `searchChapterText` (external) = `requireUserID` → `parseUUIDParam` → `validateSearchQuery`/`validateSurface` → `ensureOwnerBook` (+purge_pending 404) → `runLexicalSearch` → `writeJSON {query, mode:"lexical", results}`. Behaviour unchanged (Phase-1 tests still pin it).
3. `searchChapterTextInternal` (internal) = `parseUUIDParam` → `validateSearchQuery` → `runLexicalSearch` → `writeJSON {results}` (no ownership — internal-token caller is trusted, matches the other `/internal` endpoints). Route: `r.Get("/books/{book_id}/lexical-search", s.searchChapterTextInternal)` inside the `/internal` group.

**Tests (Go):** existing Phase-1 tests stay green (core extraction is behaviour-preserving); + a test that `runLexicalSearch` is called by both handlers (or a focused test of the internal handler param validation). Real SQL stays at live-smoke.

## 3. K-1 (knowledge) — BookClient.lexical_search  [TDD]

**File:** `knowledge .../clients/book_client.py`.

`async def lexical_search(self, book_id, q, *, limit=20) -> list[dict] | None` → `GET /internal/books/{book_id}/lexical-search?q=&limit=` (X-Trace-Id like siblings). Non-200/transport/parse → log + `None` (degrade). Return `data["results"]`.

**Tests (pytest):** httpx mock — 200 → results; 404/500 → None; transport error → None.

## 4. K-2 (knowledge) — fusion (pure)  [TDD]

**File (new):** `knowledge .../search/hybrid_fusion.py`.

- `rrf_fuse(ranked_lists: list[list[Hit]], *, k=60) -> list[Hit]` — assign each hit its RRF score by rank within its leg (key = `(chapterId, surface, blockIndex|chunkIndex)`), sum across legs, sort desc.
- `cap_per_chapter(hits, *, cap=3) -> list[Hit]` — keep ≤cap per chapterId (post-fusion order).

**Tests (pytest):** rank-based fusion beats either leg's raw order; a hit in both legs scores higher; per-chapter cap enforced; empty legs → []. (No DB.)

## 5. K-3 (knowledge) — orchestrator endpoint  [TDD]

**Files (new):** `knowledge .../routers/public/raw_search.py`; register in `main.py`.

`GET /v1/knowledge/books/{book_id}/search?q=&mode=hybrid|semantic|lexical&limit=` · `Depends(get_current_user)`.
1. Resolve project by `(user_id, book_id)` → **404 `not_indexed`** if none (ownership + config).
2. Run requested legs (asyncio.gather):
   - lexical → `book_client.lexical_search(book_id, q, limit)` (skip for `mode=semantic`).
   - semantic → `embed_query_cached(...)` → `find_passages_by_vector(source_type="chapter", dim, embedding_model, limit)` → map per ADJ-2 (skip for `mode=lexical`); `[]` on any failure.
3. `rrf_fuse([lexical, semantic])` → `cap_per_chapter` → truncate `limit`.
4. Return `{query, mode, results, degraded?}`.

**Tests (pytest):** mock `book_client` + `embed_query_cached` + `find_passages_by_vector`. Cases: hybrid fuses both; `mode=semantic` skips lexical; no-project → 404; embed→None → lexical-only (degraded.semantic); book_client→None → semantic-only (degraded.lexical); both empty → 200 [].

## 6. VERIFY (evidence gate — cross-service ⇒ live-smoke MANDATORY)

- **Unit:** `go test ./internal/...` (book) + `pytest` (knowledge) green — paste counts.
- **Cross-service live-smoke (≥2 svcs):** book + knowledge up → a book with a published (canon, embedded) chapter + a draft chapter → `GET /v1/knowledge/books/{id}/search?q=<CJK term>&mode=hybrid` returns a draft **lexical** hit + a canon **semantic** hit, RRF-fused. Token: `live smoke: hybrid raw-search fuses lexical(draft)+semantic(canon) on a stacked book`. Else `LIVE-SMOKE deferred to D-RAWSEARCH-P2-LIVE-SMOKE` or `live infra unavailable: <reason>`.

## 7. Risks (from eval PART II, scoped to P2a)

- **TP3/perf** — fan-out: knowledge→book HTTP per query (one local hop) + embed + Neo4j. Accepted; bounded by limit.
- **TP2/R2** — semantic snippets are chunk-bounded, `highlights=[]`; copy-exact from semantic deferred (Phase 3).
- **SP3** — per-project embedding model/dim; reuse drawers' dim-mismatch 502→here degrade-to-[] instead (search must not hard-fail).
- **R-coverage** — book without a project → 404 not_indexed (FE lexical fallback in P2b).

## 8. Definition of Done

- [ ] ADJ-1..4 acknowledged by PO.
- [ ] BK-1, K-1, K-2, K-3 implemented, tests green (counts pasted).
- [ ] Degradation: no 500 on any single-leg failure; 404 only on no-project.
- [ ] Cross-service live-smoke passed (or explicit deferral row).
- [ ] SESSION_HANDOFF updated; committed (BE cross-service slice).
