# Plan — Extraction raw-output CACHE (M6 / P5)

**Status:** PLAN. Branch `feat/extraction-knowledge-architecture`. The FINAL lane. Design refs:
architecture rev 2 §8.1 (two-ledger), §2.1 (`extraction_raw_outputs` DDL), §3.3 (executor
cache-gate), §8.7 (replay/tenancy). Gate decision (already made): **Option A** — build in
translation-service now, the cache **behind an interface** so the physical re-home to
knowledge-service is a later impl swap (`D-EXTRACTION-REHOME-KNOWLEDGE`).

## The gap
The worker re-spends LLM tokens on every re-extraction of an unchanged chapter. The WRITEBACK
ledger (`extraction_writeback_log`, FND/M1) records "landed in glossary" but there is no
EXECUTE ledger recording "the LLM produced this parse" — so a retry/replay/re-run re-calls the
model. The two-ledger model (§8.1): LLM-skip keys on `extraction_raw_outputs`; writeback-skip
keys on the writeback log.

## Slices

### Slice 1 — the cache-gate (LLM-skip) — THIS run
- **Migration** `extraction_raw_outputs` (translation-service `migrate.py`, §2.1): per-batch
  raw + parsed cache, `UNIQUE(owner_user_id, book_id, chapter_id, chapter_chunk_idx,
  content_hash, effort_band, batch_idx)`. owner_user_id + book_id carry tenancy (cross-tenant
  reuse FORBIDDEN — the key is tenant-scoped forever, §8.7).
- **Cache interface** `extraction_cache.py` — `RawCacheKey` + `get_cached_batch(pool, key)` +
  `put_batch(pool, key, …)` (idempotent `ON CONFLICT DO NOTHING`). The interface IS the
  re-home seam: a future knowledge-service impl swaps behind it.
- **Cache-gate in the worker batch loop** (`_process_extraction_chapter`): before the LLM
  call, look up the key (incl. `effort_band` derived from `thinking_enabled`); on HIT reuse the
  cached `parsed_entities` + `finish_reason`, spend **0 new tokens**, record the batch outcome
  from the cached result; on MISS call the LLM → parse → `put_batch`. Best-effort cache (a
  cache read/write failure falls back to a normal LLM call — never fails extraction).
- **Tests:** cache key stability; get/put round-trip + idempotency on real PG; the worker
  unit test proves a cache HIT skips `submit_and_wait` and reuses entities with 0 tokens.

### Slice 2 — wire the planner into the executor (TRACKED `D-CACHE-PLANNER-WIRING`)
Replace `plan_kind_batches` with `loreweave_extraction.plan()` (split-down + fan-out guard +
Unplannable surfaced to the cost-gate). Higher risk (changes live batching) → its own slice +
live cross-service smoke.

### Slice 3 — replay + retention (TRACKED `D-CACHE-REPLAY`, `D-RAWCACHE-MINIO-OFFLOAD`)
Grant+confirm-gated replay (re-drive writeback from cached `parsed_entities`, $0 LLM but the
write authorization is real, §8.7); retention (keep-latest + bounded history K; cold
`raw_response` → MinIO).

## Invariants honored
INV-9 (cache keys tenant-scoped forever — owner_user_id in the key + every lookup; cross-tenant
reuse forbidden; replay is a grant+confirm-gated write — Slice 3). INV-F (a `truncated` cached
parse stays truncated). No hardcoded model/price (model_ref/name stored as data).

**Note on the C5 TOCTOU:** in the current service split the raw-output cache lives in
translation-service and the per-book writeback lock lives in glossary; the worker's cache-gate
is therefore an **idempotent best-effort LLM-skip optimization** (concurrent misses both call
the LLM once, then `ON CONFLICT DO NOTHING` dedups the write — wasted tokens on the race, never
a wrong result). Writeback CORRECTNESS (dedup + content-hash precondition) remains the glossary
per-book advisory lock + `writeback_key` idempotency from FND/M1 — unchanged by this lane.

## Size
L (migration + new interface + hot worker-loop wiring). Own plan (this doc). Slice 1 this run;
Slices 2–3 tracked.
