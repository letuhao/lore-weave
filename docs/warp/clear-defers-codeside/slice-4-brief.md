# Slice 4 — translation-flag-coupling-block-obs

**Write-set:** `services/translation-service/**` only. **Config = defaults in `app/config.py`** (NEVER edit `infra/docker-compose.yml`).

## Defers to clear
### D-2B-DECOUPLE-FLAG-COUPLING (MED)
The worker's decouple branch + the API's terminal consumer both key off `translation_decouple_enabled`. A mismatch (worker ON / API consumer OFF) **silently stalls** submitted chapters (the 2h sweeper eventually fails them). Compose wires the same env to both, but it's convention not enforcement.
- **Fix:** at worker startup (the decoupled worker entry — `worker.py` / `app/workers/...` / `main.py`), when the flag is ON, emit a **loud, actionable startup log** asserting the invariant ("decouple ON ⇒ the terminal consumer MUST be running, else submitted chapters stall") and, if cheaply possible, a config-consistency check. Document the invariant in a module docstring. (A true cross-process probe is out of scope; the startup log + doc is the pragmatic enforcement.)

### D-2B-SHELL-UNIT-TESTS (LOW)
The async shells are live-smoke-only. Add unit tests for: block `resume()` failure-fold (a non-completed job folds as empty → best-effort), the consumer's bounded-retry path, and an end-to-end correction-retry in the block SM shell. Pure SMs are already covered (8+9) — target the async shells (`app/workers/decoupled_block_translate.py`, `app/events/llm_terminal_consumer.py`).

### D-2B-T3A-BLOCK-CHUNK-ROWS / -BLOCK-OBSERVABILITY (LOW)
The decoupled block path does NOT write the per-batch `chapter_translation_chunks` rows (validation errors/warnings, glossary-correction counts, V6 quality cols) NOR `record_stage("translation.batch")` that the sync path writes. **This is observability only — resume is via `resume_state`, so no correctness/resume change.** Port `_insert_chunk_row`/`_update_block_chunk_row` + the `record_stage("translation.batch")` call into the decoupled block engine (`apply_batch_result`/the async shell), matching the sync `translate_chapter_blocks` path.

## Acceptance
`python -m pytest -q` green in `services/translation-service` (existing 679+ + new shell/obs tests).

## Gotchas
- Block path writes chunk rows but resume must stay driven by `resume_state` (don't make resume depend on the chunk rows).
- Config defaults only; no compose edits. Any migration additive + idempotent.
- Keep the V3/2b finalize idempotency (`status <> 'completed'`) intact.
