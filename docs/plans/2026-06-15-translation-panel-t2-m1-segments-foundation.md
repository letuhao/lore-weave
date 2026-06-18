# Plan — T2-M1: Block-range Segments Data Foundation (`D-TRANSL-PANEL-T2-SEGMENTS`, milestone 1)

> Part of XL T2 (spec [`2026-06-15-translation-panel-overhaul.md`](../specs/2026-06-15-translation-panel-overhaul.md) §4). Milestone 1 of 3. Default v2.2 (no /amaw). Model **A** (source-side, language-independent segments).

## Scope (M1 only — data foundation, no pipeline/FE change)
Segments are **source-side ranges of `chapter_blocks`**, language-independent. Per-language translation status + dirty-only re-translate = M2; coverage rollup + matrix FE = M3.

## Acceptance criteria
- AC1 book-service exposes per-block rows: `GET /internal/books/{book_id}/chapters/{chapter_id}/blocks` → ordered `{block_index, block_type, text_content, content_hash, heading_context}` (internal-token, IDOR+active guarded).
- AC2 translation-service has a `chapter_segments` table (per chapter, language-independent): `id, chapter_id, segment_index, start_block_index, end_block_index, segment_text, block_hashes TEXT[], token_estimate, source_content_hash, created_at, updated_at`, `UNIQUE(chapter_id, segment_index)`.
- AC3 pure segmentation: group adjacent blocks up to ~2000 tokens (reuse `estimate_tokens`), **start a new segment at a heading** when the current segment is non-empty; never overflow a single block.
- AC4 `ensure_chapter_segments(pool, book_id, chapter_id)` fetches blocks → segments → **idempotent upsert** (skip when `source_content_hash` unchanged; replace when changed). Re-runnable/resumable.
- AC5 an internal trigger route `POST /internal/translation/chapters/{chapter_id}/segments/rebuild` (+ a backfill helper that loops books→chapters for the full up-front backfill at deploy).

## BE — book-service (Go)
1. Route after the chapter route (server.go ~159): `GET /books/{book_id}/chapters/{chapter_id}/blocks` → `getInternalChapterBlocks`.
2. Handler: IDOR+active guard (chapter ∈ book ∈ active), `SELECT block_index, block_type, text_content, content_hash, heading_context FROM chapter_blocks WHERE chapter_id=$1 ORDER BY block_index`. (book-service `internal/api` has no test harness → live-smoke.)

## BE — translation-service (Python)
3. `migrate.py`: add `chapter_segments` table + indexes (`idx_cseg_chapter`) to the DDL string (idempotent).
4. `clients/book_client.py` (or inline): `get_chapter_blocks(book_id, chapter_id) -> list[dict]` (httpx + internal token).
5. `workers/segmentation.py` (pure): `segment_blocks(blocks, max_tokens=2000) -> list[Segment]` where Segment = {segment_index, start_block_index, end_block_index, segment_text, block_hashes, token_estimate}. Heading-aware grouping; `source_content_hash` = sha256 of joined block_hashes.
6. `ensure_chapter_segments(pool, book_id, chapter_id)`: fetch → segment → per-chapter idempotent replace (compare a chapter-level hash; if changed, delete+insert in a txn; else skip). + a `backfill_all` loop.
7. Internal route `POST /internal/translation/chapters/{chapter_id}/segments/rebuild` (internal-token) → ensure_chapter_segments.

## Tests
- `segmentation.py` pure unit (mock-free): single-block fits; many small blocks group to ~2000; heading starts a new segment; one block over the cap stays whole; block_hashes captured in order; deterministic source_content_hash.
- `ensure_chapter_segments`: mock pool — upsert/skip-unchanged SQL shape; delete+insert on change.
- Real-PG (skip if no DB, mirror test_promote_active_pg.py): insert segments + round-trip query.

## VERIFY
- BE pytest translation green; go build/vet book-service; FE untouched.
- **Cross-service (2 services)** → live-smoke: rebuild segments for a real chapter via the internal route on a stacked-up book-service+translation-service (or `live infra unavailable`).

## Risks / decisions
- Model A: language-independent segments → M2 adds per-(segment,language) status (no rework of M1 table).
- Idempotent replace keyed on a chapter-level content hash → re-import/draft-edit re-segments only changed chapters.
- Rollback: additive table + additive endpoint → drop table / remove route.
