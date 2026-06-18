# Extraction Raw-Output Log + Reuse Cache

**Date:** 2026-06-12
**Track:** glossary-extraction (translation-service host)
**Size:** L (new table + worker cache-gate + replay path + book-service field; ≥2 services)
**Status:** ⏸ **DEFERRED** (2026-06-12) — design approved, BUILD blocked on `world-core-foundation`. See note below + DEFERRED 077.

> ## ⏸ Deferral note (2026-06-12)
>
> This task is **blocked** and intentionally not started. Context:
> - **`knowledge-service` is now built — and has grown into a "god service".** Responsibility/scope
>   across the system is being violated heavily and without control (extraction logic, ownership
>   boundaries, cross-domain reach).
> - A **large refactor, `world-core-foundation`, runs FIRST** to re-establish controlled boundaries.
>   It is a hard prerequisite — **the extraction-pipeline refactor may not start until
>   `world-core-foundation` completes.**
> - **`raw extraction outputs` (this spec) is one piece of the larger extraction-pipeline refactor**,
>   not a standalone feature. It is sequenced *inside* that refactor.
>
> Dependency chain: **`world-core-foundation` → extraction-pipeline refactor → (this) raw-extraction-outputs.**
>
> The placement decision below (table in translation-service) and the
> `D-EXTRACTION-REHOME-KNOWLEDGE` note are **superseded in spirit** by `world-core-foundation`:
> where extraction (and therefore this log) ultimately lives is a `world-core-foundation` decision,
> not the pragmatic "co-locate with the worker" choice taken here. Re-baseline this spec against the
> new boundaries when the extraction-pipeline refactor begins.

## Problem

Glossary entity extraction is wasteful. Every run re-calls the LLM per chapter even
when nothing changed, and the **raw extraction output is discarded** the moment it is
POSTed to glossary-service. Today (`extraction_worker.py:_process_extraction_chapter`):

```
fetch chapter → LLM call (raw JSON born here) → parse_and_validate()
  → POST /internal/books/{book_id}/extract-entities → glossary UPSERT
  → raw output garbage-collected; only token counts survive in extraction_chapter_results
```

The only persisted audit is `extraction_audit_log` in glossary-service — old/new value of a
single attribute, and only on `action="overwrite"`. That is a cell-level diff, **not** the
raw extraction. Consequences:

- Re-extracting an unchanged chapter spends full LLM tokens again.
- Changing `attribute_actions` (fill→overwrite) or rebuilding glossary after a wipe forces a
  full re-extract — there is no stored result to re-apply.
- No audit of what the model actually returned, at what cost, with which kinds requested.

## Goal

Persist every LLM extraction call as an append-only log row with full provenance, then use
that log to (a) **skip the LLM** when a chapter's content + requested kinds are unchanged, and
(b) **replay** stored results into glossary without any LLM call.

## Architectural placement (decided)

The table lives in **translation-service**, alongside `extraction_jobs` /
`extraction_chapter_results`. Rationale: raw LLM text, `model_ref`, tokens, and the
extraction profile only exist in translation-service at call time; glossary-service never
sees them. Putting the log in glossary would leak extraction internals across a boundary that
does not own them.

> Note: entity extraction *conceptually* belongs to the planned `knowledge-service` (the
> semantic/extraction layer that writes through to glossary SSOT). It sits in
> translation-service today for infra reuse (LLM SDK client, broker, worker). The raw-output
> log follows the worker and will migrate **as one cluster** with `extraction_jobs` if/when
> extraction re-homes. Tracked as Deferred `D-EXTRACTION-REHOME-KNOWLEDGE`.

## Solution

### 1. New table `extraction_raw_outputs` (translation-service)

One row per LLM call = one (chapter, batch). Append-only.

```sql
CREATE TABLE IF NOT EXISTS extraction_raw_outputs (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id          UUID NOT NULL REFERENCES extraction_jobs(job_id) ON DELETE CASCADE,
  book_id         UUID NOT NULL,
  chapter_id      UUID NOT NULL,

  -- provenance: "which chapter version"
  chapter_content_hash    TEXT   NOT NULL,   -- sha256(prepared extraction text) = cache key + truth
  chapter_draft_version   BIGINT,            -- from book-service (human-readable)
  chapter_draft_updated_at TIMESTAMPTZ,
  chapter_title           TEXT,
  chapter_index           INT,

  -- "which kinds were requested at that time"
  kinds_requested    TEXT[] NOT NULL,         -- the kinds in this batch
  batch_idx          INT    NOT NULL DEFAULT 0,
  extraction_profile JSONB  NOT NULL,         -- snapshot of attribute_actions at extract time

  -- model + cost (tokens = SSOT; cost_usd best-effort snapshot)
  model_source     TEXT   NOT NULL,
  model_ref        UUID,
  model_name       TEXT,                      -- resolved once/job from provider-registry (display)
  thinking_enabled BOOLEAN NOT NULL DEFAULT false,
  input_tokens     INT    NOT NULL DEFAULT 0,
  output_tokens    INT    NOT NULL DEFAULT 0,
  cost_usd         NUMERIC(12,6),

  -- payload
  raw_response     TEXT   NOT NULL,           -- verbatim LLM string (TOAST auto-compresses)
  parsed_entities  JSONB  NOT NULL,           -- validated output = exact POST body to glossary
  parse_status     TEXT   NOT NULL DEFAULT 'ok',  -- ok | repaired | failed
  source_mode      TEXT   NOT NULL DEFAULT 'llm',  -- llm | (reserved)

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ero_book_created ON extraction_raw_outputs(book_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ero_cache ON extraction_raw_outputs(book_id, chapter_id, chapter_content_hash);
CREATE INDEX IF NOT EXISTS idx_ero_job ON extraction_raw_outputs(job_id);
```

Both `raw_response` (audit / re-parse if the parser improves) and `parsed_entities` (replay
without re-parsing) are kept. `chapter_content_hash = sha256(prepare_chapter_text(chapter))` —
the exact text fed to the LLM, so the key is the producer's own truth (avoids the
`cross-service-normalization` / `reconcile-by-truth` bug class: never key on `draft_version`
alone — an edited chapter must miss the cache).

### 2. Cache-gate (skip LLM) — default ON, with force override

In `_process_extraction_chapter`, before batching:

```
content_hash = sha256(chapter_text)
covered_kinds = union(kinds_requested) over fresh rows where
                (book_id, chapter_id, content_hash) matches      -- model-independent
requested_kinds = kinds in extraction_profile
missing_kinds  = requested_kinds − covered_kinds

if force_reextract:           run LLM for all requested_kinds (ignore cache)
elif missing_kinds == ∅:      0 LLM calls — replay cached parsed_entities → POST glossary
else:                         LLM only missing_kinds; merge cached(covered) + fresh(missing) → POST
```

- **Cache key = (content_hash, kinds), model-independent** — re-extracting identical text =
  0 tokens regardless of model. Each row still records `model_name` + `thinking_enabled` +
  `cost_usd`, so the UI can show *"cached from `qwen-7b`, thinking=off"* and the user can hit
  **Force re-extract** to override with a better model.
- `force_reextract: bool = false` added to `CreateExtractionJobPayload` + broker message +
  worker.
- Skipped (cache-hit) chapters still write `extraction_chapter_results` and emit progress
  events; tokens reported as 0 for skipped batches. A new `chapter_results.source` value
  (`cache` vs `llm`) is surfaced so the UI/job summary distinguishes spent vs reused.

### 3. Replay (re-apply cached results → glossary, no LLM)

New `mode` on extraction jobs: `extract` (default) | `replay`. A replay job reuses the entire
worker/broker/progress/cancel plumbing but, per chapter, **reads the cache instead of calling
the LLM** — then POSTs to glossary with the job's (possibly new) `attribute_actions`.

Endpoint: `POST /v1/extraction/books/{book_id}/replay`
Body: `{ chapter_ids?: UUID[], from_job_id?: UUID, attribute_actions: {...}, target_kinds?: [] }`
(selects the latest cached row per chapter+content_hash; 422 if a selected chapter has no
cache). Serves: rebuild glossary after a wipe, switch fill→overwrite, try a different profile
— all token-free.

### 4. book-service: expose `draft_version`

`getInternalBookChapter` (`services/book-service/internal/api/server.go`) returns draft fields
but not `draft_version` (exists in `chapter_drafts`). Add it to the SELECT + JSON so the worker
can store human-readable provenance. `content_hash` remains the cache key; `draft_version` is
display-only.

### 5. Retention (manual batch delete)

- `DELETE /v1/extraction/books/{book_id}/raw-outputs?before=<iso>&job_id=<uuid>` (EDIT grant).
- `GET /v1/extraction/books/{book_id}/raw-outputs/usage` → `{rows, total_bytes}` (VIEW grant)
  via `sum(pg_column_size(...))`, so the user can see accumulation and decide when to prune.
- No auto-purge (storage is cheap; ~50MB/book is fine — TOAST compresses `raw_response`).

## Acceptance criteria

1. Every extraction LLM call writes one `extraction_raw_outputs` row with job/book/chapter,
   `content_hash`, `kinds_requested`, `extraction_profile` snapshot, model fields,
   `thinking_enabled`, tokens, `raw_response`, `parsed_entities`.
2. Re-running extraction on a chapter whose prepared text is unchanged, with the same kinds,
   makes **0 LLM calls** and still upserts the same entities (replayed from cache).
3. Adding a new kind to the profile re-extracts **only** the missing kind(s); covered kinds are
   replayed from cache.
4. `force_reextract=true` bypasses the cache and always calls the LLM.
5. `POST .../replay` re-applies cached results to glossary with a new `attribute_actions` and
   makes 0 LLM calls; returns created/updated/skipped counts; 422 if a chapter has no cache.
6. book-service internal chapter response includes `draft_version`; worker stores it.
7. `DELETE .../raw-outputs` removes rows (by `before` and/or `job_id`); `GET .../usage`
   returns row count + byte size. Both grant-gated.
8. Job summary / `GET /jobs/{job_id}` distinguishes cache-hit chapters from LLM chapters
   (source = cache|llm) so reused vs spent is visible.
9. Migrations idempotent; existing extraction behavior unchanged when cache is empty.

## Out of scope

- Re-homing extraction to knowledge-service (Deferred `D-EXTRACTION-REHOME-KNOWLEDGE`).
- Frontend UI for browsing/pruning the raw log (this delivers the API + job-summary signal;
  a dedicated log viewer is a fast-follow).
- Cross-chapter or semantic dedup of raw outputs; per-attribute (sub-kind) cache granularity.
- Compressing/offloading `raw_response` to object storage (TOAST is sufficient at current scale).
- Changing glossary-service's UPSERT semantics or `extraction_audit_log`.

## Risks / guardrails

- **Stale cache after a chapter edit** → keyed on `content_hash` of the prepared text, not
  `draft_version`; an edit changes the hash and misses the cache. (Memory:
  `reconcile-by-truth-mirror-producer-predicate`.)
- **Partial-kind merge correctness** → cached(covered) + fresh(missing) entities must union by
  the same chapter_links shape `post_extracted_entities` expects; covered by a worker unit test.
- **Cache-hit must still emit progress/cancel events** → replay path runs inside the same job
  loop, not a shortcut around it.
- **Cross-service**: touches translation-service + book-service → VERIFY needs a live smoke
  (extract once → re-extract → assert 0 tokens; replay → assert 0 tokens) or an explicit
  `LIVE-SMOKE deferred` row. (Memory: `live-smoke-rebuild-stale-images-first`.)
