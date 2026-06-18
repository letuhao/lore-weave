# Plan — Translation resume-sweeper (Wave 2a · D-2B-SUBMIT-PERSIST-GAP)

**Goal:** give the decoupled-translation path the same runtime backstop worker-ai got in
Wave 1b — a periodic sweeper that re-drives a `chapter_translations` row whose
`resume_state` has been idle past a timeout, recovering a consumer crash/poison, a lost
terminal event, or a submit→persist gap (the Redis stream gives no redelivery after ack).

**Scope:** translation-service only. Flag-gated (`translation_decouple_enabled`), inert when
off. Translation's finalize keeps its `status <> 'completed'` idempotency (no strict-tx
amplification like worker-ai), so this is a backstop, not load-bearing — but it closes the
same gap class.

## Acceptance criteria
1. A `chapter_translations` row with `resume_state IS NOT NULL` idle > timeout is re-driven
   by re-checking its `provider_job_id`'s terminal status and replaying the consumer's
   existing resume dispatch (block/text), idempotently.
2. A still-in-flight job is left alone (only `job.is_terminal()` replays).
3. Inert when the decouple flag is off; tunable via config (interval/timeout/batch).
4. No regression to the synchronous path or the event-driven consumer.

## Changes (7 files)
- **migrate.py** — additive: `ALTER TABLE chapter_translations ADD COLUMN IF NOT EXISTS
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` + a partial index
  `(updated_at) WHERE resume_state IS NOT NULL` for the sweep scan. (No `updated_at` existed.)
- **decoupled_block_translate.py / decoupled_translate.py** — bump `updated_at=now()` in each
  `_persist_inflight` so idle-detection reflects real progress.
- **config.py** — `translation_resume_sweep_interval_s`=60 / `_timeout_s`=900 / `_batch`=20.
- **events/llm_terminal_consumer.py** — extract `_resume_loaded(ct_id, rs, job)` from `_handle`
  (the campaign-bind + block/text dispatch), reused by both the event path and the sweeper;
  add `sweep_once(*, timeout_s, batch)` + `run_sweeper(*, interval_s, timeout_s, batch)`.
- **main.py** — start `run_sweeper` as a lifespan task inside the decouple-flag block; cancel
  it in cleanup.
- **tests/** — sweep_once: re-drives a terminal job; skips an in-flight job; continues past a
  get_job error; query filters on resume_state + idle.

## Added per /review-impl (finding #1) — `D-2B-TRANSL-RESUME-RACE` fixed in the same commit
Both engines' `resume()` now serialise the fold under `SELECT … FOR UPDATE` on the chapter row
+ re-verify `provider_job_id` still equals THIS job. The next-step submit + its provider_job_id
advance run UNDER the lock (the loser re-reads the advanced id → skips → no double batch-submit);
finalize runs AFTER the lock (idempotent; nesting `_finalize_chapter` would deadlock the same
row). `_persist_inflight`/`_submit_next(_batch)`/`_record_chunk` take an executor (Pool or the
locked Connection). New tests: `tests/test_decoupled_resume_race.py` (superseded-job skip,
gone/cleared-row skip, updated_at bump — both engines).

## Known limitation (deferred, mostly moot today)
- `D-2B-TRANSL-SWEEP-BYOK-OWNER` (LOW): the sweeper resolves `get_job` via `msg["user_id"]`,
  matching the consumer's existing no-event fallback. Translation decouple sets **no** billing
  contextvar (grep-confirmed), so jobs are owned by `msg["user_id"]` and the sweeper resolves
  correctly. Only bites IF translation decouple later adopts BYOK; then thread the billing id
  (or the event's `owner_user_id`) into the sweep path.
