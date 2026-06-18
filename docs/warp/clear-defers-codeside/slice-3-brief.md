# Slice 3 — worker-ai-trio-race-runsample

**Write-set:** `services/worker-ai/**` only. **Config = defaults in `app/config.py`** (NEVER edit `infra/docker-compose.yml`). **Load-bearing money-path (the extraction consumer) — preserve the Wave-1a strict-tx + FOR UPDATE finalize exactly; only ADD.**

## Context
`app/llm_extract_consumer.py` is the decoupled extraction consumer. Wave-1a made the trio fold a `SELECT … FOR UPDATE` read-modify-write and the persist finalize a single strict tx (cursor-advance + run-emit + chapter_extracted + `_record_spending` + `_clear_resume`) gated by a `FOR UPDATE` re-read. Wave-1b added `_sweep_once`/`run_resume_sweeper`.

## Defers to clear
### D-WX-TRIO-FANIN-RACE — remaining multi-replica gap (the SKIP LOCKED part)
The trio FOLD is already FOR-UPDATE-safe. The remaining gap (Wave-1b review #2): the **sweeper's row selection has no `FOR UPDATE SKIP LOCKED`** → two worker-ai replicas can both grab the same stranded row and **double-submit an ENTITY-stage re-drive**. **Fix:** add `FOR UPDATE SKIP LOCKED` to the `SELECT` in `_sweep_once` (the stranded-rows query) so concurrent replicas claim disjoint rows. (The trio fold's own FOR-UPDATE already makes the fold safe; this closes the sweep-side double-submit.)

### D-WX-RUN-SAMPLE-DECOUPLE (LOW)
The decoupled persist path **skips `persist_run_sample`** (the online-judge telemetry the sync `extract_pass2` path writes). Find where the SYNC path calls `persist_run_sample` (likely in `runner.py`/the sync persist) and wire the same call into the **decoupled finalize** (`_persist_chunk` in the consumer, or its persist helper) so decoupled runs feed the online judge identically. It's telemetry — keep it best-effort (a failure must NOT break the strict finalize tx; call it OUTSIDE the tx like `persist_pass2`).

## Acceptance
`python -m pytest -q` green in `services/worker-ai` (existing 209 + new). Add: a test asserting the sweep `SELECT` contains `SKIP LOCKED`; a test asserting `persist_run_sample` is invoked on the decoupled finalize (spy/monkeypatch). Use the existing fake asyncpg pool/conn harness in `tests/test_llm_extract_consumer.py`.

## Gotchas
- Do NOT pin a pooled conn across an HTTP call — `persist_run_sample`, like `persist_pass2`, runs outside the strict tx.
- `SKIP LOCKED` only on the sweeper's claim SELECT; the trio fold's `FOR UPDATE` (no SKIP) stays as-is (it must block, not skip).
- Config defaults only; no compose edits.
