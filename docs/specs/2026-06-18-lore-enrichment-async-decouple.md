# Spec — Lore-enrichment async decouple (close `D-JOBS-P4-RETRY-LORE`)

> **Status:** DESIGN — awaiting PO approval before BUILD (PO chose "spec first, build later", 2026-06-18).
> **Origin:** the architecture-debt sweep — lore-enrichment is the LAST LLM-job service still running
> synchronously in-process; every other (translation, extraction, knowledge, video_gen, composition,
> campaign) is on the decoupled/async model. Root of `D-JOBS-P4-RETRY-LORE` (🔴 BLOCKED in DEBT-BATCHES B1).
> **Size:** M (revised down from L after the 2026-06-18 RISK INVESTIGATION — see §1.1: the FE's real
> create path is ALREADY async/worker-driven; only a vestigial no-caller demo endpoint is synchronous, so
> there is no public contract to change. The remaining real work is cancel/pause-mid-run honoring + retry
> wiring + a per-job claim).

> **⚠ SCOPE REVISED 2026-06-18 (risk investigation, §1.1).** The original framing ("flip the synchronous
> create path to async") was largely MOOT: `auto-enrich` + `compose` (the FE's actual entrypoints) already
> create → `save_job_request` → XADD → worker → `redrive_one`. The synchronous `POST /v1/lore-enrichment/jobs`
> is a **vestigial demo endpoint with no production caller**. So `D-JOBS-P4-RETRY-LORE`'s "runs synchronously
> in-process" premise is STALE — the real path is already worker-driven. Refocused scope: §7.

---

## 1. Current state (grounded in code)

`POST /v1/lore/jobs` ([api/jobs.py:261](../../services/lore-enrichment-service/app/api/jobs.py#L261)) runs
`await bundle.runner.run_job(...)` **INLINE in the HTTP request handler**. The whole enrichment job —
every gap × (retrieval → generate → verify), sequentially — blocks the client's HTTP connection for the
full duration (the handler comment at L266 literally says "release the per-owner job slot once the
**synchronous run** ends"). The handler returns the *complete* outcome (proposals list, spent, etc.).

What this costs us:
- **No retry** — `D-JOBS-P4-RETRY-LORE` is BLOCKED precisely because there is no async job a control
  action can re-drive; the run only exists as a stack frame in one HTTP request.
- **No real cancel** — cancel is DB-state-only (a `cancelled` row), but the in-flight in-request loop
  keeps running to completion (it never checks the flag). ([[llm-seam-pull-blocking-rearch]])
- **No pause/resume parity** — cost-cap pause works, but a *manual* pause / unified-control pause can't
  interrupt the in-request loop.
- **Fragility** — a client disconnect or gateway timeout on a long multi-gap job orphans the run; the
  HTTP layer holds a connection for minutes.
- **Control-plane gap** — lore is invisible to the unified Jobs control plane's action gating
  (`derive_control_caps`) for retry/cancel because there's no durable async job to act on.

### 1.1 RISK INVESTIGATION (2026-06-18) — the real create path is ALREADY async

Before flipping `POST /jobs`, a blast-radius investigation traced every caller. Result — the synchronous
endpoint is NOT the path that matters:

- **`POST /v1/lore-enrichment/jobs/projects/{id}/auto-enrich`** ([gaps.py:309-347](../../services/lore-enrichment-service/app/api/gaps.py#L309)) — the FE's primary "enrich" entry — does `create_job` → `save_job_request` (targets + model refs + book scope) → **XADD** `{job_id,…}` to `LORE_ENRICHMENT_RESUME_STREAM` → worker → `redrive_one`. **Already async, worker-driven, on the compose precedent.**
- **`POST …/projects/{id}/compose`** — the other FE entry — already returns 202 + enqueues (§ above).
- **`POST /v1/lore-enrichment/jobs` (`create_job`, [jobs.py:132](../../services/lore-enrichment-service/app/api/jobs.py#L132))** — the synchronous in-request run — has **NO production caller**: the FE (`features/enrichment/api.ts`) calls auto-enrich + compose, never this; the only references are the gateway's GET proxy-smoke + lore's own unit tests/demo scripts. Its docstring literally says "Synchronous for the demo".

**Conclusion:** the async worker-driven create path is already live for the FE's real entrypoints. The
"synchronous in-process" blocker behind `D-JOBS-P4-RETRY-LORE` describes a vestigial endpoint, not the
production path. The remaining REAL gaps are **(a)** a per-job claim so concurrent triggers can't double-run
(HIGH-2 — benefits the already-live async paths), **(b)** honoring an external cancel/pause MID-run
(HIGH-1), and **(c)** wiring retry into the control plane (the actual retry blocker — a small wiring task,
NOT an async refactor). The vestigial sync endpoint is a low-priority cleanup (align-to-202 or remove; no
caller either way).

### 1.2 Pre-existing async building blocks
**The async infrastructure ALREADY EXISTS in this service** — and the FE create path already uses it:
- `LoreEnrichmentResumeConsumer` ([worker/resume_consumer.py:153](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L153)) — a `loreweave_jobs.BaseTerminalConsumer` on `LORE_ENRICHMENT_RESUME_STREAM`.
- `redrive_one` ([worker/resume_consumer.py:43](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L43)) — rebuilds the runner + runs `run_job` **off the HTTP request**, with `skip_gap_refs` (idempotent re-drive).
- **Compose mode is already async** — `POST …/compose` returns `202 + job_id` and a background worker re-drives `run_job` ([api/compose.py:28](../../services/lore-enrichment-service/app/api/compose.py#L28)). The same consumer dispatches both compose tasks and resume re-drives ([worker/resume_consumer.py:131](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L131)).
- `save_job_request` already persists the request shape for re-drive; `JobStateMachine` already has the full DAG incl. `paused⇄running` + `cancelled`; lore already emits create events to the unified projection (`D-JOBS-P4-LORE-MODEL`, B1 M1).
- P5 fair-sched lease (`fair_sched.acquire/release_job`) already wraps the run.

So the gap is narrow: **the initial run is the one path that runs inline instead of on the worker.**

## 2. Goal / acceptance criteria

1. **(Already met for the real path)** the FE create entrypoints (`auto-enrich` + `compose`) run on the
   worker, not in-request. NEW: a **per-job claim** so concurrent triggers (create / resume / retry /
   stranded-sweeper) for the same job can never run two LLM-spending runners (HIGH-2). The vestigial
   synchronous `POST /jobs` is aligned-to-202 or removed (no caller — low priority, no contract risk).
2. **Cancel** interrupts an in-flight job between gaps (graceful: finish/abort the current gap, mark
   `cancelled`, emit) — not just a DB flag.
3. **Retry** a `failed` lore job via the unified Jobs control plane re-enqueues it (reuses
   `redrive_one` + skip-done) → `D-JOBS-P4-RETRY-LORE` CLOSED.
4. **Pause/resume** parity: manual pause via the control plane interrupts between gaps; resume re-drives.
5. Lore appears in `derive_control_caps` with its real caps (retry on `failed`; cancel on
   `running`/`paused`; resume on `paused`).
6. **Invariants preserved** (regression-gated): H0 quarantine (never canon), cost-cap pause, idempotent
   resume (`UNIQUE(job_id,gap_ref)` + skip-done + seeded spend), P5 fair-sched lease, eval-gate
   enforcement, no model-name literals, provider-gateway-only LLM.

## 3. Reference pattern (already proven in this repo)

Translation/extraction/campaign decoupled model: create row → enqueue → worker drives → terminal event
to the unified `job_projection`; control actions (`cancel`/`retry`/`pause`/`resume`) route through
jobs-service → the owning service's control endpoint → re-enqueue / status-CAS. Lore's compose + resume
paths ALREADY follow the worker half of this; we extend it to the create path.

### 3.1 Consistency — the platform's TWO-mechanism pattern (the "outbox?" question)

There are **two distinct concerns** handled by **two distinct mechanisms**, uniformly across every
job-bearing service — and lore is ALREADY conformant on both except for one bypass:

| Concern | Mechanism | Why this one | Lore today |
|---|---|---|---|
| **Job lifecycle EVENTS** (pending/running/terminal → unified `job_projection` / Jobs GUI) | **Transactional outbox** — `emit_job_event` inserts a `JobEvent` into `outbox_events` (aggregate_type=`jobs`) in the **SAME tx** as the status write → worker-infra relay → `loreweave:events:jobs` → projection | A dropped event leaves a job stuck "running" forever in the GUI → emission must be atomic with the status change (H1). Standardized by the producer-emit backfill across ALL services. | ✅ **conformant** — `job_events.py` + `internal_job_control.py` already emit via `emit_job_event`; reconcile-sweep endpoint present. |
| **Work DISPATCH** (create → the worker that runs it) | **Direct Redis `XADD`** to a service stream (`LORE_ENRICHMENT_RESUME_STREAM`), consumed by a `loreweave_jobs.BaseTerminalConsumer`, **backed by** (a) the durable `save_job_request` row and (b) a **stranded-job sweeper** that re-drives any non-terminal job whose trigger was lost | The durable state is the job row + persisted request; a lost XADD is recovered by the sweeper (at-least-once). NOT a transactional outbox — dispatch intent is reconstructable from the row, so it doesn't need exactly-once relay. compose explicitly does this ("the job + request persist; re-triggerable", [compose.py:332](../../services/lore-enrichment-service/app/api/compose.py#L332)). | ✅ **auto-enrich + compose + resume conformant** (the FE's real entries already XADD→worker). Only the vestigial no-caller `POST /jobs` runs inline. |

**Conclusion for the design:** lore does NOT diverge from the outbox pattern. Event emission already uses
the transactional outbox; work dispatch uses the direct-XADD-+-durable-row-+-sweeper pattern that compose
already follows. **Option A introduces NO new outbox and NO new mechanism** — it routes the create path
through the EXACT compose precedent (create row + `save_job_request` + XADD trigger + 202), reusing the
event-outbox and the stream+consumer+sweeper that already exist. The lone fix is moving the run off the
HTTP request onto the worker (+ the between-gap cancel/pause checkpoint).

## 4. Design options

### Option A — job-level async via the existing worker  ★ RECOMMENDED

`POST /jobs`: keep the fast pre-checks (P5 cap → 429; eval-gate probe → 409; bad strategy → 400) so the
**synchronous rejection contract is preserved**; then create the row (`pending`), `save_job_request`,
**enqueue** a `{job_id, project_id, user_id}` "run" message to `LORE_ENRICHMENT_RESUME_STREAM` (or a
sibling run-stream), and return `202 + job_id`. The worker's `dispatch_*` gains a "run" kind that calls
`redrive_one`-shaped logic with `skip_gap_refs=∅` (a fresh run is just a re-drive with no done gaps —
`api/gaps.py:227` already notes "the SAME consumer as resume; a fresh job has no done gaps").

`run_job` gains a **cancel/pause checkpoint between gaps**: before each gap, re-read the job status (or a
cheap cancel/pause signal); `cancelling` → stop gracefully + `machine.cancel()` + emit; `paused` (manual)
→ stop + leave resumable. The cost-cap pause already does exactly this shape — we generalize it.

- **Cost-reconcile invariant UNCHANGED** — the worker still runs gaps sequentially in one process, so the
  `meter.total_tokens` snapshot reconcile ([runner.py:419](../../services/lore-enrichment-service/app/jobs/runner.py#L419)) stays valid. No metering redesign.
- **Reuses** `BaseTerminalConsumer`, `save_job_request`, `redrive_one`, `fair_sched`, the state machine,
  and the existing emit wiring. Net new code is small.
- **Cancel/pause become real** via the between-gap checkpoint.
- **Retry** = jobs-service `control_job` → lore control endpoint → enqueue a run message (skip-done).

### Option B — full per-LLM-unit decouple (provider_job_id + terminal-event resume)

Each gap's LLM call submitted to provider-registry as a separate async job; worker released between
calls; resumed on the `llm_job_terminal` stream; cost from the provider job's usage (not in-process
metering). Matches translation's *per-unit* decoupling.

- **Much larger + riskier:** a gap's `run_gap` chains retrieval(embed) → generate(LLM) → verify(LLM) —
  multiple seam calls, not one — so per-call decoupling fragments the per-gap unit and needs a
  multi-step resumable SM per gap ([[decouple-loop-chain-under-producer-lock]]). The cost-reconcile must
  move off in-process metering. This is the XL the debt row assumed.
- **Marginal benefit today:** the per-gap unit is already a natural checkpoint; jobs are bounded
  (gap-count) and the cost-cap already pauses between gaps. Per-call resumability only matters if a
  single gap's LLM call is itself long enough to need mid-call recovery — not the case today.

## 5. Recommendation

**Option A.** It delivers every acceptance criterion (retry/cancel/pause-resume parity + 202 + control
plane), reuses infrastructure already built and proven in this service, and preserves the cost-metering
invariant — so it carries far less risk than Option B for the same user-visible outcome. Option B is
recorded as a *future* "if per-call resumability ever matters" item, not part of this effort.

## 6. Size — M (was L; risk investigation shrank it)

The debt row tags this XL (assumed Option B green-field per-unit decouple). The risk investigation (§1.1)
then showed the FE create path is ALREADY async/worker-driven — so the create-flip + the FE create rework
(the bulk of the old L) are MOOT. What remains is **M**: (a) a per-job claim (HIGH-2, DONE), (b) the
between-gap cancel/pause checkpoint with a guarded transition (HIGH-1), (c) retry control-plane wiring,
(d) a low-priority vestigial-endpoint cleanup. No new service, no new transport, **no migration** (job
row, request table, status vocab, control endpoint, outbox emission all already exist).

## 7. Milestones (REVISED post-risk-investigation)

The old S1 (flip the create path) + S4 (FE create rework) are MOOT — the FE create path is already async
(§1.1). The effort refocuses on the per-job claim + the cancel/pause-mid-run gap + retry wiring.

- **M1 — per-job claim (HIGH-2) ✅ DONE.** A status-agnostic Postgres **session advisory lock** on a 64-bit
  key derived from `job_id`, held for the run on a dedicated connection in `redrive_one`
  ([resume_consumer.py](../../services/lore-enrichment-service/app/worker/resume_consumer.py)); a 2nd
  concurrent trigger no-ops. Placed at the SHARED chokepoint, so it protects the already-live async paths
  (auto-enrich / compose / resume) + the future retry. **REFINED during build:** a `pending→running` CAS
  would WRONGLY reject a resume (the resume endpoint pre-flips `paused→running` before its XADD), so the
  claim is the lock, not a status CAS. Remaining for M1: the fake-pool unit tests must answer the
  advisory-lock queries (a build detail). NO migration.
- **M2 — cancel/pause MID-run honoring (HIGH-1) — the real cancel-parity gap.** `run_job` re-reads the
  job's persisted status before each gap; `cancelling`→graceful stop + emit; manual `paused`→stop
  resumable. Generalize the existing cost-cap-pause early-return shape.
  - **HIGH-1 (guarded transition — MUST):** the runner and the control endpoint
    ([_transition_job](../../services/lore-enrichment-service/app/api/jobs.py#L438)) are TWO independent
    writers to `enrichment_job.status` with no CAS — so an external `cancel`/`pause` mid-run is silently
    CLOBBERED when the runner's `machine.complete()` (trusting in-memory `running`) writes `completed` over
    it (**latent today even on the live async path**). Every runner status write MUST be a **guarded**
    transition: re-read the DB status (under row lock) and only advance if the DB wasn't externally moved
    to terminal/paused — the runner YIELDS to a concurrent control action. The between-gap checkpoint is
    the read half; the conditional terminal write is the write half.
- **M3 — retry control-plane wiring (closes `D-JOBS-P4-RETRY-LORE`).** This is the ACTUAL retry blocker —
  a small wiring task, NOT an async refactor (the row was mis-tagged "blocked on async"). jobs-service
  `derive_control_caps`: lore `enrichment_job` → retry(failed) [cancel/pause/resume already wired]. Add
  the kind to `_RETRYABLE_KINDS`. Extend lore's EXISTING [internal_job_control.py](../../services/lore-enrichment-service/app/api/internal_job_control.py) `_HANDLERS` with `retry` → re-enqueue a `{job_id,…}` trigger on a `failed`
  row (owner-scoped 404 / 409-unless-failed); `redrive_one` skip-done = no re-spend. The M1 claim makes a
  retry-while-still-running a safe no-op.
- **M4 — vestigial endpoint + FE control caps (LOW).**
  - Vestigial `POST /jobs` (no caller): **align to enqueue+202** (reuse the auto-enrich body) for internal
    consistency, OR mark demo-only / remove. No contract risk (no production caller). Decide cheaply.
  - FE: create flow needs NO change (already async via auto-enrich/compose). Retry/Cancel/Pause/Resume
    render off `control_caps` (data-driven; likely just an `enrichment_job` kind label + i18n×4 if
    missing). **MED-4 is largely resolved** — the FE never consumed the synchronous proposals.

## 8. Invariants & risks

- **Synchronous-rejection contract** (P5 cap 429 / eval-gate 409 / bad-strategy 400): the live async
  entries (auto-enrich/compose) already pre-check before enqueue. If M4 aligns the vestigial `POST /jobs`
  to 202, keep these as fast pre-checks there too.
- **~~API contract change~~ (RESOLVED by risk investigation — §1.1):** the FE create path is `auto-enrich`
  + `compose`, already async — it never consumed the synchronous outcome. The only synchronous endpoint
  (`POST /jobs`) has NO production caller, so aligning it to 202 (M4) is NOT a breaking contract change.
  The original "biggest consumer impact" concern does not apply.
- **Cancel granularity:** between-gap, not mid-gap (a gap in flight finishes or is abandoned). Acceptable
  (gaps are bounded units); document it.
- **Idempotent at-least-once:** the run stream is at-least-once; `redrive_one` is already idempotent
  (UNIQUE + skip-done + seeded spend), so a redelivered "run" is safe.
- **H0 / provider-gateway / no-model-literal** gates unchanged (the worker runs the same pipeline).
- **LOW-6 (double `build_live_runner`):** the gate pre-check on POST + the real build on the worker build
  the runner twice. Accept (it's cheap relative to the run), or replace the POST pre-check with a light
  gate-only probe. Decide in S1; not blocking.

## 8a. Design-review findings (REVIEW-design, 2026-06-18 — folded in above)

Adversarial self-review against the code surfaced 6 findings; the 2026-06-18 risk investigation then
resolved/rescoped several:
- **HIGH-1** concurrent status-writer clobber (runner vs control endpoint, no CAS) → **M2** guarded transition. *Latent today on the live async path.* OPEN.
- **HIGH-2** per-job double-run wastes LLM spend (per-owner lease ≠ per-job) → **M1 per-job claim ✅ DONE** (advisory lock, refined from the naive CAS).
- **MED-3** gap-rebuild parity → **VERIFIED ✅** — both paths use the identical `_gap_from_target(targets)`; no extra persistence needed.
- **MED-4** FE create UX → **RESOLVED ✅** — the FE create path (auto-enrich/compose) is already async and never consumed the synchronous proposals.
- **MED-5** P5 acquire semantics → only relevant if M4 aligns the vestigial endpoint; the live paths already pre-check. Deferred to M4.
- **LOW-6** double `build_live_runner` → only relevant to the vestigial endpoint (M4). Deferred.
**Net after risk investigation:** the only OPEN load-bearing item is **HIGH-1 (M2)**; HIGH-2 is done. The
effort is M2 (cancel/pause-mid-run) + M3 (retry wiring) + M4 (low cleanup).

## 9. Test plan

- **Unit:** worker "run" dispatch drives a fresh job; cancel checkpoint stops between gaps + marks
  cancelled + emits; manual pause stops resumable; retry re-enqueues (skip-done); `derive_control_caps`
  gives lore the right caps per status; the `POST` pre-checks still 429/409/400 before enqueue.
- **Live-smoke (≥2 services — lore + jobs + provider-registry + redis):** `POST /jobs` → 202 → worker runs
  on local Qwen → `job_projection` shows pending→running→completed; cancel a mid-run job → `cancelled`
  lands; retry a failed job → re-enqueued → terminal. Token = `D-LORE-ASYNC-DECOUPLE-LIVE-SMOKE`.

## 10. Out of scope

- Option B per-LLM-unit decouple (future, if per-call resumability is ever needed).
- `D-EXTRACTION-RAW-OUTPUT-CACHE` (separately gated behind world-core-foundation; do-not-pick-standalone).
