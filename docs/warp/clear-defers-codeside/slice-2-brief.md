# Slice 2 — lore-enrichment-compose-task-hardening

**Write-set:** `services/lore-enrichment-service/**` only. **Config = defaults in `app/config.py`** (NEVER edit `infra/docker-compose.yml`). Migrations go in the service's own migrate module (additive, idempotent).

## Context
M2 added `enrichment_compose_task` (kind∈{profile_suggest,intent_resolve}, status, request/result JSONB) + `app/compose/compose_task.py` (`create_compose_task`, idempotent `run_compose_task` [completed→skip], the two compute fns) + a resume worker branch (`dispatch_resume_message` → `run_compose_task`). Single worker container, one consumer, serial loop today.

## Defers to clear
### D-M2-COMPOSE-TASK-RACE (MED)
`run_compose_task` guards only `status='completed'` with **no FOR-UPDATE / claim** → concurrent double-compute + last-write-wins IF the worker ever scales. **Do NOT use a naïve `pending→running` CAS — it breaks crash recovery** (a crashed 'running' row would never re-drive). Use the **worker-ai Wave-1b pattern**: a `SELECT … FOR UPDATE` claim that skips a row another worker is *actively* on (recent `updated_at`) but lets the sweeper re-drive a *stale* 'running' row. Bump `updated_at=now()` on every status write so idle-detection is accurate.

### D-M2-COMPOSE-TASK-SWEEPER (LOW, coupled with the race fix)
A redis-miss at submit strands a 'pending' task with no runtime recovery. Add a **stuck-task sweeper** mirroring worker-ai's `_sweep_once`/`run_resume_sweeper`: periodically find `enrichment_compose_task` rows `status IN (pending,running)` idle > timeout, re-drive the idempotent `run_compose_task`. Config defaults `..._sweep_interval_s`=60 / `_timeout_s`=900 / `_batch`=20 in `app/config.py`; wire the loop in `main.py` (inside the worker startup). If the table lacks `updated_at`, ADD it (additive migration, `TIMESTAMPTZ NOT NULL DEFAULT now()`) + a partial index for the scan.

### D-M2-COMPOSE-TASK-POISON (LOW)
A malformed `request_json` (missing key) → `KeyError` not in the consumer's `_BUSINESS_ERRORS` → un-ACK **poison loop**. Catch `KeyError` (and other malformed-input errors) as a **business-fail** (mark the task failed + ACK), not an infra error.

## Acceptance
`python -m pytest -q` green in `services/lore-enrichment-service` (existing + new race/sweeper/poison tests). Use a fake asyncpg pool/conn harness if one exists in the repo's tests; otherwise mock the repo.

## Gotchas
- The dedup invariant (a task row already existing) must survive; the FOR-UPDATE only prevents concurrent *double-compute*, not the legitimate idempotent skip.
- Config defaults only; no compose edits. Migration is additive + idempotent (`IF NOT EXISTS`).
