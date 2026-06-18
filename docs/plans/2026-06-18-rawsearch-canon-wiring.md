# Plan — D-RAWSEARCH-CANON-WIRING (full feature)

**Date:** 2026-06-18 · **Branch:** feat/auto-draft-factory-gaps · **Size:** L (BE pipeline + contract + FE)
**Debt row:** `D-RAWSEARCH-CANON-WIRING` — retriever hardcodes `surface="canon"`; `raw_search` has no `surface` param.

## Problem (grounded in code)

- `passage_to_hit` ([retriever.py:69](../../services/knowledge-service/app/search/retriever.py#L69)) hardcodes `"surface": "canon"`.
- Production indexes **canon only**: the sole prod caller is the `chapter.published` handler
  → `_ingest_published_passages` → `ingest_chapter_passages(revision_id=pinned)`
  ([handlers.py:166](../../services/knowledge-service/app/events/handlers.py#L166)). The draft path
  (`revision_id=None`) is used only by the benchmark corpus + tests.
- `:Passage` nodes carry **no canon flag** — there was no non-canon content to distinguish.

So `surface=all` returning draft content needs (a) a flag, (b) a draft-indexing trigger, (c) the filter + param + FE.

## PO decisions (2026-06-18)

1. **Draft trigger = on-demand, owner-only.** A new owner-initiated endpoint embeds the book's
   *draft* chapters once (`canon=false`). No per-save embedding → bounded cost. Re-run to refresh.
2. **Draft privacy = owner-only.** `surface=all` returns drafts only when the caller **is the book
   owner**; collaborators (view/edit) get canon only even with `surface=all`.
3. **Lifecycle (obvious answer):** publish already re-ingests at the pinned revision with
   `canon=true` and `delete_passages_for_source` first → a draft chapter's passages auto-flip to
   canon on publish; unpublish already deletes them. No extra wiring.

## Design

### Storage — no migration
Add a `canon` boolean to `:Passage`. **Legacy nodes have no `canon` → treat NULL as canon**
(`coalesce(node.canon, true)`), so **no backfill** is needed. Published ingest stamps `canon=true`
(default); the on-demand draft path stamps `canon=false`.

### No collision
`ingest_chapter_passages` deletes all passages for the `source_id` (chapter) then writes. Draft
chapters have no canon passages (canon written only on publish) → indexing a draft is clean.
The index-drafts endpoint enumerates **only `editorial_status=draft` chapters** (skips published),
so it never clobbers canon. A later publish re-ingests canon + deletes the draft passages (same
`source_id`) → auto-flip.

### Changes
| File | Change |
|---|---|
| `app/db/neo4j_repos/passages.py` | `Passage.canon: bool = True`; `canon` in upsert cypher (ON CREATE+MATCH SET) + `upsert_passage(canon=True)` param; `find_passages_by_vector(include_drafts=False)` + `AND ($include_drafts OR coalesce(node.canon, true) = true)` in the find cypher. |
| `app/extraction/passage_ingester.py` | `ingest_chapter_passages(canon: bool = True)` → thread to each `upsert_passage(canon=canon)`. |
| `app/search/retriever.py` | `Surface = Literal["canon","all"]`; `run_hybrid_search(surface="canon")` → `include_drafts=(surface=="all")`; `passage_to_hit` sets `surface = "canon" if h.passage.canon else "draft"` (accurate). |
| `app/routers/public/raw_search.py` | `surface: Surface = Query("canon")`; owner gate `effective = surface if (surface=="all" and caller==project.user_id) else "canon"`; pass to `run_hybrid_search`. |
| `app/routers/public/raw_search.py` (or sibling) | `POST /v1/knowledge/books/{book_id}/index-drafts` — owner-only (`caller==project.user_id`); enumerate `editorial_status=draft` chapters; `ingest_chapter_passages(revision_id=None, canon=False, chapter_index=sort_order)` each; return `{indexed, chapters}`. Best-effort per chapter. |
| `app/clients/book_client.py` | `list_chapters(book_id, editorial_status=None)` → calls existing `GET /internal/books/{book_id}/chapters` (returns `items` w/ `chapter_id`,`sort_order`,`editorial_status`). |
| `contracts/api/.../knowledge` OpenAPI | `surface` query param on search + the `index-drafts` endpoint. |
| FE raw-search feature | `surface` canon/all toggle (drafts owner-only) + owner "index drafts" action. |

## Tests
- passages: upsert persists `canon`; `find_passages_by_vector` `include_drafts` filter (canon-only vs all; legacy null=canon).
- ingester: `canon` threads to `upsert_passage`.
- retriever: `surface=all` → `include_drafts=True`; `passage_to_hit` surface label reflects flag.
- raw_search: collaborator + `surface=all` → downgraded to canon; owner + `all` → drafts; param plumb.
- index-drafts: non-owner → 404/403; enumerate draft-only; per-chapter best-effort; ingest called with `canon=False`.

## Verify
≥2 services? knowledge-service only at runtime (book-service internal route already exists). BE unit
suites; FE typecheck. Live-smoke: `live infra unavailable` (Neo4j+stack not booted at dev time) OR a
real index-drafts→search round-trip if stack is up — note in evidence.
