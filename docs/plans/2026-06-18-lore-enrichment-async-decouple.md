# Plan — Lore-enrichment async decouple (long-run /loom)

> **Spec:** [`docs/specs/2026-06-18-lore-enrichment-async-decouple.md`](../specs/2026-06-18-lore-enrichment-async-decouple.md) (DESIGN approved + REVIEW-design folded in, 2026-06-18).
> **Closes:** `D-JOBS-P4-RETRY-LORE` (🔴 BLOCKED, DEBT-BATCHES B1) + lore cancel/pause-resume parity.
> **Size:** M (revised down from L — the RISK INVESTIGATION, spec §1.1, found the FE create path is
> ALREADY async/worker-driven; only a vestigial no-caller endpoint is synchronous, so there is no public
> contract to change). Option A only (no per-LLM-unit decouple).
> **Mode:** continuous /loom; checkpoint/commit at each milestone boundary. 4 milestones (M1 done).

## Phases already done (this conversation)
- **CLARIFY** — scope chosen (Option A, spec-first); acceptance criteria = spec §2.
- **DESIGN** — spec authored; consistency confirmed (events=tx-outbox, dispatch=XADD+durable-row+sweeper).
- **REVIEW (design)** — adversarial self-review → 6 findings folded in (spec §8a).
- **RISK INVESTIGATION (2026-06-18)** — blast-radius trace before flipping the public API: the FE create
  path (`auto-enrich` + `compose`) is ALREADY async; `POST /jobs` (sync) has NO production caller. The
  scope shrank L→M; the "contract change" was dropped; MED-3 verified + MED-4 resolved. See spec §1.1.
- **Remaining:** BUILD (M2,M3,M4 — M1 done) → VERIFY → REVIEW(code) → QC → POST-REVIEW → SESSION → COMMIT → RETRO, per milestone.

## Invariants (regression-gated across every slice)
H0 quarantine (never canon) · cost-cap pause · idempotent resume (`UNIQUE(job_id,gap_ref)` + skip-done +
seeded spend) · P5 fair-sched cap · eval-gate enforcement · no model-name literals · provider-gateway-only
LLM · transactional-outbox event emission (unchanged) · NO DB migration (job row + request table + status
vocab already exist; the per-job claim uses an advisory lock → NO migration).

---

## M1 — per-job claim (HIGH-2)  ✅ DONE (this conversation)

**What shipped:** a status-agnostic Postgres **session advisory lock** on a 64-bit key derived from the
`job_id` UUID's first 64 bits (collision-resistant — it guards real LLM spend), held for the whole run on
a dedicated connection in `redrive_one` ([resume_consumer.py](../../services/lore-enrichment-service/app/worker/resume_consumer.py)): `pg_try_advisory_lock` at the top (not acquired → another runner owns the job → log + no-op + ack), the run extracted to `_redrive_locked`, `pg_advisory_unlock` in `finally`. Placed at the SHARED chokepoint → protects the already-live async paths (auto-enrich/compose/resume) + the future retry.

**Why advisory lock, not a `pending→running` CAS (refined during build):** the resume path
([resume_job jobs.py:523](../../services/lore-enrichment-service/app/api/jobs.py#L523)) pre-flips
`paused→running` BEFORE its XADD, so a status-CAS would reject a legitimate resume. The lock is
status-agnostic and serializes create/resume/retry/sweeper triggers uniformly.

**Remaining for M1 (rolls into the next BUILD step):** the fake-pool unit tests (`test_worker_compose.py`
etc.) must answer the `pg_try_advisory_lock`/key-derivation queries the fake conn now receives — a test
harness update, no product change. VERIFY M1 with those green.

---

## M2 — cancel/pause MID-run honoring + HIGH-1 guarded transition  ← the real cancel-parity gap

**Goal:** an external `cancel`/`pause` mid-run interrupts between gaps and is NEVER clobbered.

**Tasks**
1. **Between-gap status read:** in `run_job`'s gap loop ([jobs/runner.py:198](../../services/lore-enrichment-service/app/jobs/runner.py#L198)), before each gap re-read the persisted status (a cheap `SELECT status`). `cancelling`/`cancelled` → stop, finalize `cancelled`, emit; manual `paused` → stop resumable (leave done-gaps persisted; the resume path re-drives). Mirror the existing cost-cap-pause early-return shape.
2. **HIGH-1 guarded terminal write:** make the runner's terminal/▷ transitions conditional — `machine.complete()`/`mark_job_status('completed')` must NOT overwrite a status the control endpoint moved to `cancelled`/`cancelling`/`paused`. Implement as a CAS (`UPDATE … SET status='completed' WHERE job_id=$1 AND status='running'`) or re-read-under-row-lock; if the guard fails, the runner yields (the external action won). Apply the same guard to the `running`/`paused`/`failed` writes the runner makes.
3. **Confirm the control endpoint stays authoritative:** `_transition_job` already does SELECT→machine→UPDATE+emit in a tx; once the runner yields (task 2) the two no longer race destructively. Add a row-lock (`SELECT … FOR UPDATE`) in `_transition_job` if needed so the read-modify-write is atomic vs the runner.

**Acceptance:** cancel during a multi-gap run → job ends `cancelled` (not `completed`); manual pause →
`paused` + resumable; the runner never clobbers an external transition.

**Tests:** unit — runner yields when DB status is externally `cancelling`/`paused` between gaps (inject a
status flip via the fake store); guarded complete no-ops when DB is `cancelled`; cost-cap pause still works.

**Checkpoint:** commit M2 (concurrency-correctness seam; `/review-impl` — this is the load-bearing
money/cancel path on the LIVE async path).

---

## M3 — control-plane retry wiring (closes D-JOBS-P4-RETRY-LORE)

**Goal:** Retry a `failed` lore job. This is the ACTUAL retry blocker — a small wiring task, NOT an async
refactor (the debt row was mis-tagged "blocked on async"; cancel/pause/resume are already wired in
`internal_job_control`).

**Tasks**
1. **jobs-service `derive_control_caps`:** lore kind (`enrichment_job`) → add **`retry`(failed)** (cancel/
   resume already present); add the kind to `_RETRYABLE_KINDS`. (Compose-task kinds stay cancel-only.)
2. **lore retry handler:** extend the EXISTING [internal_job_control.py](../../services/lore-enrichment-service/app/api/internal_job_control.py) `_HANDLERS` with `retry` → a `_retry_enrichment_job` that, on a `failed` row (owner-scoped 404 / 409-unless-failed), re-enqueues a `{job_id,…}` trigger (reuses the live async path; `redrive_one` skip-done = no re-spend; the M1 claim makes a retry-while-running a safe no-op). Emit the transition.
3. **Confirm reconcile + emit parity** for the new transition (reconcile endpoint already lists rows).

**Acceptance:** a failed lore job shows a Retry cap; retry (via jobs-service) re-drives to terminal,
skipping done gaps. `D-JOBS-P4-RETRY-LORE` CLOSED.

**Tests:** unit — `derive_control_caps` gives lore retry-on-failed; retry handler 404/409/happy
re-enqueues; idempotent re-drive (skip-done) on a partially-done failed job.

**Checkpoint:** commit M3 (closes the named debt row).

---

## M4 — vestigial endpoint + FE control caps (LOW)

**Goal:** internal consistency + control-button parity; NO FE create change (already async).

**Tasks**
1. **Vestigial `POST /jobs` (no production caller):** align it to the auto-enrich pattern (create +
   save_request + XADD + `202`) for internal consistency, OR mark demo-only / remove. Decide cheaply —
   no contract risk either way (FE uses auto-enrich/compose). Update its unit tests/demo scripts to match.
2. **FE control caps:** Retry/Cancel/Pause/Resume render off `control_caps` (data-driven; no create-flow
   change — MED-4 resolved). Add the `enrichment_job` kind label + i18n×4 if missing.

**Acceptance:** the vestigial endpoint is consistent (or gone); Retry/Cancel/Pause/Resume work from the
Jobs GUI; tsc + vitest green.

**Checkpoint:** commit M4.

---

## VERIFY (cross-service live-smoke — the reconcile proof)

Token `D-LORE-ASYNC-DECOUPLE-LIVE-SMOKE` (≥2 services: lore + jobs + provider-registry + redis):
- `auto-enrich` → worker runs on local Qwen → `job_projection` shows pending→running→completed (the live path).
- Cancel a mid-run multi-gap job → ends `cancelled` (HIGH-1/M2 proof: not clobbered to completed).
- Two triggers for one job → exactly one runs (HIGH-2/M1 proof: per-job advisory-lock claim).
- Retry a failed job → re-enqueued → terminal, done-gaps skipped (M3 proof).
Rebuild lore-enrichment + worker images before the smoke (stale-image false-green trap).

## REVIEW (code) — 2-stage per slice
Spec-compliance (does it implement the slice + the folded findings?) + code-quality (CAS correctness,
claim races, no-model-literals, H0 untouched). Proactively `/review-impl` after S1+S2 (money-path
concurrency + the per-job claim are load-bearing).

## Risks / stop-conditions
- ✅ MED-3 (gap-rebuild parity) RESOLVED — both paths use the identical `_gap_from_target(targets)`.
- ✅ MED-4 (FE create UX) RESOLVED — FE create is already async (auto-enrich/compose); no inline-proposals
  consumption to redesign.
- If a DB migration turns out necessary → it shouldn't (the claim is an advisory lock), but STOP + flag
  (L+ → migration review) before applying.
- M2 is the load-bearing remainder (money/cancel concurrency on the LIVE path) → `/review-impl` before commit.
