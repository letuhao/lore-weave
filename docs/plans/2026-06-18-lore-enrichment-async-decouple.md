# Plan — Lore-enrichment async decouple (long-run /loom)

> **Spec:** [`docs/specs/2026-06-18-lore-enrichment-async-decouple.md`](../specs/2026-06-18-lore-enrichment-async-decouple.md) (DESIGN approved + REVIEW-design folded in, 2026-06-18).
> **Closes:** `D-JOBS-P4-RETRY-LORE` (🔴 BLOCKED, DEBT-BATCHES B1) + lore cancel/pause-resume parity.
> **Size:** L (leaning M — async worker infra + control plane + outbox emission already exist; the work
> is routing the create path through them + two concurrency guards). Option A only (no per-LLM-unit decouple).
> **Mode:** continuous /loom; checkpoint/commit at each slice boundary (a real risk seam). 4 slices.

## Phases already done (this conversation)
- **CLARIFY** — scope chosen (Option A, spec-first); acceptance criteria = spec §2.
- **DESIGN** — spec authored; consistency confirmed (events=tx-outbox, dispatch=XADD+durable-row+sweeper).
- **REVIEW (design)** — adversarial self-review → 6 findings folded into the spec/slices (spec §8a).
- **Remaining:** PLAN (this doc) → BUILD → VERIFY → REVIEW(code) → QC → POST-REVIEW → SESSION → COMMIT → RETRO, per slice.

## Invariants (regression-gated across every slice)
H0 quarantine (never canon) · cost-cap pause · idempotent resume (`UNIQUE(job_id,gap_ref)` + skip-done +
seeded spend) · P5 fair-sched cap · eval-gate enforcement · no model-name literals · provider-gateway-only
LLM · transactional-outbox event emission (unchanged) · NO DB migration (job row + request table + status
vocab already exist — re-confirm in S1; if a claim column is needed it's additive → /amaw-gate check).

---

## Slice 1 — async create + per-job claim (the keystone)

**Goal:** `POST /jobs` returns `202 + job_id`; the run executes on the worker; concurrent same-job runs
are impossible (HIGH-2).

**Tasks**
1. **Verify-first (MED-3):** trace the current `POST /jobs` gap computation vs `redrive_one`'s
   `_gap_from_target(request["targets"])`. Confirm identical gap set; if the sync path detects more than
   the targets carry, persist the detected gap refs in `save_job_request` so the rebuild matches.
2. **Worker "run" kind:** extend `dispatch_resume_message` ([worker/resume_consumer.py:131](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L131)) to route a `{job_id, project_id, user_id}` "run" message to `redrive_one(..., skip_gap_refs=∅)` (a fresh run = re-drive with no done gaps). Keep `task_id` (compose) + paused-redrive routing intact.
3. **HIGH-2 per-job claim:** at the top of `redrive_one`, atomically claim the job — CAS
   `UPDATE enrichment_job SET status='running' WHERE job_id=$1 AND status IN ('pending','paused') RETURNING …`
   (or `pg_advisory_xact_lock(hashtext(job_id))` held for the run). No row claimed → the job is already
   running/terminal → log + return (no-op) + ack. This serializes create/sweeper/resume triggers.
4. **MED-5 P5 on the worker:** move `fair_sched.acquire/release_job` into the worker run. If acquire fails
   (cap full at run-time) → leave the job `pending` + re-trigger later (acquire-or-requeue), do NOT fail.
   Keep the POST pre-check as the fast 429.
5. **`POST /jobs` flip:** pre-checks (P5 cap → 429; eval-gate probe → 409; bad-strategy → 400; LOW-6:
   decide light-probe vs full build) → create row (`pending`, emit `pending` via tx-outbox) →
   `save_job_request` → XADD "run" trigger → return `202 {job_id, status:"pending"}`. Remove the inline
   `build_live_runner`+`run_job`+the synchronous-outcome response.
6. **Durability (stranded sweeper):** confirm/extend the worker-entry sweeper to re-drive a `pending`/
   non-terminal `enrichment_job` whose trigger was lost (symmetric with the compose-task sweeper). The
   per-job claim (task 3) makes a spurious sweeper re-trigger a safe no-op.

**Acceptance:** POST returns 202; the worker runs the job to terminal; the per-job claim provably prevents
a second concurrent run (test: two "run" messages for one job → exactly one runs). MED-3 parity confirmed.

**Tests:** unit — dispatch routes "run"; claim CAS wins-once (2nd no-ops); acquire-or-requeue on cap-full;
POST returns 202 + emits pending; pre-checks still 429/409/400 before enqueue. (Reuse the fake-pool +
fake-redis harness in `tests/test_worker_compose.py` / `tests/test_jobs_api.py`.)

**Checkpoint:** commit S1 (keystone risk seam: the create-path flip + the money-path claim).

---

## Slice 2 — cancel/pause checkpoint + HIGH-1 guarded transition

**Goal:** an external `cancel`/`pause` mid-run interrupts between gaps and is NEVER clobbered.

**Tasks**
1. **Between-gap status read:** in `run_job`'s gap loop ([jobs/runner.py:198](../../services/lore-enrichment-service/app/jobs/runner.py#L198)), before each gap re-read the persisted status (a cheap `SELECT status`). `cancelling`/`cancelled` → stop, finalize `cancelled`, emit; manual `paused` → stop resumable (leave done-gaps persisted; the resume path re-drives). Mirror the existing cost-cap-pause early-return shape.
2. **HIGH-1 guarded terminal write:** make the runner's terminal/▷ transitions conditional — `machine.complete()`/`mark_job_status('completed')` must NOT overwrite a status the control endpoint moved to `cancelled`/`cancelling`/`paused`. Implement as a CAS (`UPDATE … SET status='completed' WHERE job_id=$1 AND status='running'`) or re-read-under-row-lock; if the guard fails, the runner yields (the external action won). Apply the same guard to the `running`/`paused`/`failed` writes the runner makes.
3. **Confirm the control endpoint stays authoritative:** `_transition_job` already does SELECT→machine→UPDATE+emit in a tx; once the runner yields (task 2) the two no longer race destructively. Add a row-lock (`SELECT … FOR UPDATE`) in `_transition_job` if needed so the read-modify-write is atomic vs the runner.

**Acceptance:** cancel during a multi-gap run → job ends `cancelled` (not `completed`); manual pause →
`paused` + resumable; the runner never clobbers an external transition.

**Tests:** unit — runner yields when DB status is externally `cancelling`/`paused` between gaps (inject a
status flip via the fake store); guarded complete no-ops when DB is `cancelled`; cost-cap pause still works.

**Checkpoint:** commit S2 (concurrency-correctness seam).

---

## Slice 3 — control-plane retry + caps wiring (closes D-JOBS-P4-RETRY-LORE)

**Goal:** Retry a `failed` lore job; lore exposes its real `control_caps`.

**Tasks**
1. **jobs-service `derive_control_caps`:** lore kind (`enrichment_job`) → `cancel`(running|paused) +
   `resume`(paused) + **`retry`(failed)**; add the kind to `_RETRYABLE_KINDS`. (Compose-task kinds stay
   cancel-only, per existing `internal_job_control` behavior.)
2. **lore retry handler:** extend [internal_job_control.py](../../services/lore-enrichment-service/app/api/internal_job_control.py) `_HANDLERS` with `retry` → a `_retry_enrichment_job` that, on a `failed` row (owner-scoped 404 / 409-unless-failed), re-enqueues a "run" trigger (reuses S1's path; `redrive_one` skip-done = re-spends neither budget nor tokens on done gaps). Emit the transition.
3. **Confirm reconcile + emit parity** for the new transitions (the reconcile endpoint already lists rows; no change expected).

**Acceptance:** a failed lore job shows a Retry cap; clicking retry (via jobs-service) re-drives it to
terminal, skipping done gaps. `D-JOBS-P4-RETRY-LORE` CLOSED.

**Tests:** unit — `derive_control_caps` gives lore the right caps per status; retry handler 404/409/happy
re-enqueues; idempotent re-drive (skip-done) on a partially-done failed job.

**Checkpoint:** commit S3 (closes the named debt row).

---

## Slice 4 — FE/SDK + create-flow UX

**Goal:** the FE create flow works against 202+poll; control buttons are data-driven.

**Tasks**
1. **MED-4 verify:** inspect the FE lore create flow — does it render proposals inline from the POST
   response? Scope accordingly: if inline → submit → loading → poll job status → load proposals from the
   list endpoint when terminal; if already fire-and-forget → minimal change.
2. **Control buttons:** Retry/Cancel/Pause/Resume render off `control_caps` (likely zero new FE logic —
   data-driven, as for the other kinds). Add the `enrichment_job` kind label + i18n×4 if missing.
3. **SDK:** no contract change beyond the 202 response shape on create; update any SDK/types + tests.

**Acceptance:** create → 202 → poll → proposals appear on completion; Retry/Cancel/Pause/Resume work from
the Jobs GUI; tsc + vitest green; i18n×4 complete.

**Checkpoint:** commit S4.

---

## VERIFY (cross-service live-smoke — the reconcile proof)

Token `D-LORE-ASYNC-DECOUPLE-LIVE-SMOKE` (≥2 services: lore + jobs + provider-registry + redis):
- `POST /jobs` → 202 → worker runs on local Qwen → `job_projection` shows pending→running→completed.
- Cancel a mid-run multi-gap job → ends `cancelled` (HIGH-1 proof: not clobbered to completed).
- Two "run" triggers for one job → exactly one runs (HIGH-2 proof: per-job claim).
- Retry a failed job → re-enqueued → terminal, done-gaps skipped.
Rebuild lore-enrichment + worker images before the smoke (stale-image false-green trap).

## REVIEW (code) — 2-stage per slice
Spec-compliance (does it implement the slice + the folded findings?) + code-quality (CAS correctness,
claim races, no-model-literals, H0 untouched). Proactively `/review-impl` after S1+S2 (money-path
concurrency + the per-job claim are load-bearing).

## Risks / stop-conditions
- If MED-3 reveals the sync path detects gaps the targets can't reconstruct → STOP, decide (persist gap
  refs vs re-detect on the worker) before S1 BUILD continues.
- If a DB migration turns out necessary (e.g. a claim column) → it's additive, but STOP + flag (L+ →
  migration review) before applying.
- If MED-4 reveals a heavy FE create-flow redesign → re-scope S4 (may split to its own /loom).
