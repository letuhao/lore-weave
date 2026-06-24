# Slice 1 — composition-reaper-conflict

**Write-set:** `services/composition-service/**` only. **Config = defaults in `app/config.py`** (NEVER edit `infra/docker-compose.yml`).

## Defers to clear
### D-M4-REAPER-WORKER-CONFLICT (MED)
composition-service has a **stale-job reaper** (`created_at`-based, ~1800s, marks `running`→`failed`) that assumes "no producer resumes a running job". But the **M4 worker IS a producer** — a decompose/stitch/generate op running >1800s wall-clock is **spuriously failed**. Separately, the worker's **`updated_at`-based 900s sweeper** (`app/worker/job_consumer.py::run_sweeper`/`sweep_once`) can **double-drive** a job the consumer is still running.

- Locate the reaper: grep `services/composition-service` for `reap`, `job_reaper_sweep_secs`, `chapter_inflight_stale_secs` (likely a repo method on `generation_jobs` + a loop in `main.py`).
- **Fix:** exclude worker-owned jobs from the `created_at` reaper — a job is worker-owned when `input->>'worker_op' IS NOT NULL` OR `operation = ANY(SUPPORTED_OPERATIONS)` (see `app/worker/operations.py::SUPPORTED_OPERATIONS`). Those are governed by the worker's own `updated_at`-based sweeper instead. Align the reaper/sweeper timeouts so they don't fight (the sweeper's `composition_job_sweep_timeout_secs` should be ≤ the reaper window, and the reaper skips worker-ops entirely). Keep flag-OFF behavior byte-identical (the inline path creates non-worker-op jobs the reaper still governs).

### D-M4-DECOMPOSE-ENDPOINT-TEST (LOW)
The decompose 202 branch + `job.input` JSON-serializability (`tmpl.beats` assumed JSON-safe) are untested (worker tests mock the repo).
- Add an endpoint test (flag ON via monkeypatching `settings.composition_worker_enabled`): POST decompose → 202 + a job row whose `input` round-trips through `json.dumps` with realistic `beats`; plus a worker==inline equivalence assertion (same result shape).

## Acceptance
`python -m pytest -q` green in `services/composition-service` (existing + new). Reaper unit tests must still pass (adjust them only if they enshrined the buggy "fail worker-op jobs" behavior — fix root cause, don't weaken).

## Gotchas
- Worker-op dispatch key: generate carries its canonical op in `input['worker_op']`; decompose/stitch use `operation`. Match BOTH.
- Config knobs get defaults in `app/config.py`; do NOT touch compose.
