# Plan — Extraction Raw-Output Log + Reuse Cache

**Spec:** [docs/specs/2026-06-12-extraction-raw-output-cache.md](../specs/2026-06-12-extraction-raw-output-cache.md)
**Date:** 2026-06-12 · **Size:** L · **Services:** translation-service (primary), book-service (1 field)
**Status:** ⏸ **DEFERRED** (2026-06-12) — do NOT BUILD yet. Blocked on `world-core-foundation`.

> **Deferral note.** `knowledge-service` is now built and has become a "god service"; system-wide
> scope/logic boundaries are being violated without control. A large refactor,
> **`world-core-foundation`, must complete first**, then the **extraction-pipeline refactor** runs —
> and **raw-extraction-outputs (this plan) is one slice of that refactor**, not a standalone task.
> Dependency chain: `world-core-foundation` → extraction-pipeline refactor → this plan. Re-baseline
> the build order below against the new boundaries when the extraction-pipeline refactor begins
> (table placement may move out of translation-service). Tracked as DEFERRED 077. See the spec's
> deferral note for full context.

## Build order (TDD per phase; each phase commits independently)

### Phase 1 — Schema + repository (translation-service)
- [ ] Add `extraction_raw_outputs` DDL to the `DDL` string in
      [services/translation-service/app/migrate.py](../../services/translation-service/app/migrate.py)
      (new `-- V9: Extraction raw-output cache` block, after the `extraction_chapter_results`
      table at line ~267). Idempotent `CREATE TABLE IF NOT EXISTS` + 3 indexes.
- [ ] Add `source` column to `extraction_chapter_results`
      (`ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'llm'` — values `llm|cache|mixed`).
- [ ] New module `app/workers/extraction_cache.py` with pure helpers (unit-testable, no I/O):
  - `content_hash(text: str) -> str` — `sha256` hex of the prepared extraction text.
  - `covered_kinds(rows) -> set[str]` / `missing_kinds(requested, covered) -> list[str]`.
  - `cached_entities_for_kinds(rows, kinds) -> list[dict]` — pull `parsed_entities` for the
    covered kinds, ready to merge into the glossary POST body.
- [ ] DB access fns (asyncpg) in the same module or `glossary_client`-style helper:
  - `insert_raw_output(db, **row)` — write one call's row.
  - `fetch_cache_rows(db, book_id, chapter_id, content_hash) -> list[Record]`.
- **Tests:** `tests/test_extraction_cache.py` — hash stability, covered/missing set math,
  entity-merge shape. Migration smoke (table + columns exist) in existing migrate test.

### Phase 2 — Worker cache-gate + raw persistence
- [ ] Thread `force_reextract: bool` and `mode: str` ('extract'|'replay') from the broker
      message into `_run_extraction_job` → `_process_extraction_chapter`
      ([extraction_worker.py](../../services/translation-service/app/workers/extraction_worker.py)).
- [ ] Resolve `model_name` once per job (provider-registry, via existing resolution path; NULL
      on failure — no hardcoded names, per provider rule). Carry into the chapter fn.
- [ ] In `_process_extraction_chapter`:
  - Compute `content_hash` from `chapter_text` (line ~299, after `prepare_chapter_text`).
  - `fetch_cache_rows` → compute `missing_kinds`.
  - If `mode=='replay'` or (`not force` and `missing == ∅`): **no LLM** — build entities from
    `cached_entities_for_kinds`, mark chapter `source='cache'`.
  - Else: re-plan batches over `missing_kinds` only (or all kinds if force/empty cache); run
    the existing LLM loop; **after each batch**, `insert_raw_output(...)` with raw_response +
    parsed_entities + tokens + model + thinking + profile snapshot + content_hash + draft_version.
    Mark chapter `source='llm'` (or `'mixed'` when some kinds came from cache).
  - Merge cached(covered) + fresh(missing) entities before the single
    `post_extracted_entities` call (unchanged downstream).
- [ ] Skipped batches contribute 0 tokens; `extraction_chapter_results.source` written in the
      job loop alongside the existing token UPDATE (lines ~194-202).
- **Tests:** worker unit tests with a fake LLM client + asyncpg mock (follow existing worker
  test patterns): (a) empty cache → LLM called, row written; (b) full cache-hit → LLM **not**
  called, entities replayed; (c) one new kind → LLM called only for that kind; (d)
  `force_reextract` → LLM called despite cache.

### Phase 3 — Replay + retention endpoints (translation-service)
- [ ] `POST /v1/extraction/books/{book_id}/replay`
      ([app/routers/extraction.py](../../services/translation-service/app/routers/extraction.py)) —
      EDIT grant; create an extraction_job with `mode='replay'` (no LLM cost estimate), insert
      chapter_result rows, publish `extraction.job` with `mode='replay'`. 422 if a selected
      chapter has no cache row. Reuses worker + progress/cancel plumbing.
- [ ] Add `mode` + `force_reextract` to `CreateExtractionJobPayload` and the publish body in
      `create_extraction_job`; persist `mode` on `extraction_jobs`
      (`ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'extract'` in Phase 1 DDL).
- [ ] `DELETE /v1/extraction/books/{book_id}/raw-outputs?before=&job_id=` — EDIT grant.
- [ ] `GET /v1/extraction/books/{book_id}/raw-outputs/usage` → `{rows,total_bytes}` — VIEW grant.
- [ ] Surface `source` (cache|llm|mixed) per chapter in `GET /jobs/{job_id}` response
      (chapters[] already returned at lines ~236-246) + a job-level reused/spent rollup.
- **Tests:** router tests — replay with cache → 0 tokens + correct counts; replay missing
  cache → 422; delete by before/job; usage shape; grant gating (non-grantee → 404/uniform).

### Phase 4 — book-service `draft_version`
- [ ] `getInternalBookChapter` ([services/book-service/internal/api/server.go](../../services/book-service/internal/api/server.go),
      ~line 2192 SELECT + ~2200 writeJSON) — add `d.draft_version` to the SELECT and
      `"draft_version"` to the response map.
- [ ] Worker reads `chapter.get("draft_version")` into the raw row (NULL-safe).
- **Tests:** book-service handler test asserts `draft_version` present in the internal
      chapter response.

### Phase 5 — VERIFY (cross-service live smoke) + gate-board wiring
- [ ] Rebuild touched service images before smoke (stale-image guard — memory
      `live-smoke-rebuild-stale-images-first`).
- [ ] Live smoke on the running stack:
  1. Extract a chapter → assert one `extraction_raw_outputs` row, tokens > 0.
  2. Re-extract same chapter, same profile → assert **0 new tokens**, entities still upserted,
     chapter `source='cache'`.
  3. Add a kind → assert only the new kind hits the LLM.
  4. `POST .../replay` with a flipped `attribute_actions` → assert 0 tokens, glossary updated.
- [ ] VERIFY evidence string carries `live smoke: <one-liner>` or
      `LIVE-SMOKE deferred to D-EXTRACT-RAWCACHE-LIVE-SMOKE`.

## Workflow-gate
```
size L 6 8 1        # ~6+ files, multi logic, side effects (schema/API)
```
Run via PowerShell: `python scripts/workflow-gate.py ...` (memory: bash wrapper fails on this box).

## Files touched (estimate)
- `services/translation-service/app/migrate.py` (table + columns)
- `services/translation-service/app/workers/extraction_cache.py` (new)
- `services/translation-service/app/workers/extraction_worker.py` (cache-gate + persist)
- `services/translation-service/app/routers/extraction.py` (replay + retention + payload)
- `services/book-service/internal/api/server.go` (draft_version)
- tests across all of the above
- `contracts/api/` — extraction OpenAPI (replay + retention routes) if present for this domain

## Deferred rows to add at SESSION
- `D-EXTRACTION-REHOME-KNOWLEDGE` — move extraction worker + `extraction_jobs` /
  `extraction_chapter_results` / `extraction_raw_outputs` to knowledge-service when it exists.
- `D-EXTRACT-RAWCACHE-LIVE-SMOKE` — only if Phase 5 smoke is deferred.
- (fast-follow) frontend raw-log viewer + prune UI.

## Open questions for PO at CLARIFY (if any surface)
- Replay job as a first-class `extraction_job` row (chosen) vs a synchronous endpoint —
  chosen async for progress/cancel parity; confirm acceptable.
- `source='mixed'` semantics on partial-kind reuse — confirm the job summary should count a
  partially-reused chapter as spent (it did call the LLM for some kinds).
