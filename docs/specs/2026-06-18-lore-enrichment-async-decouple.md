# Spec — Lore-enrichment async decouple (close `D-JOBS-P4-RETRY-LORE`)

> **Status:** DESIGN — awaiting PO approval before BUILD (PO chose "spec first, build later", 2026-06-18).
> **Origin:** the architecture-debt sweep — lore-enrichment is the LAST LLM-job service still running
> synchronously in-process; every other (translation, extraction, knowledge, video_gen, composition,
> campaign) is on the decoupled/async model. Root of `D-JOBS-P4-RETRY-LORE` (🔴 BLOCKED in DEBT-BATCHES B1).
> **Size:** L (NOT XL — see §6; the async worker infra already exists, so this is "route the primary create
> path through the path compose+resume already use", not a green-field decouple).

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

**The async infrastructure ALREADY EXISTS in this service** — the primary create path just bypasses it:
- `LoreEnrichmentResumeConsumer` ([worker/resume_consumer.py:153](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L153)) — a `loreweave_jobs.BaseTerminalConsumer` on `LORE_ENRICHMENT_RESUME_STREAM`.
- `redrive_one` ([worker/resume_consumer.py:43](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L43)) — rebuilds the runner + runs `run_job` **off the HTTP request**, with `skip_gap_refs` (idempotent re-drive).
- **Compose mode is already async** — `POST …/compose` returns `202 + job_id` and a background worker re-drives `run_job` ([api/compose.py:28](../../services/lore-enrichment-service/app/api/compose.py#L28)). The same consumer dispatches both compose tasks and resume re-drives ([worker/resume_consumer.py:131](../../services/lore-enrichment-service/app/worker/resume_consumer.py#L131)).
- `save_job_request` already persists the request shape for re-drive; `JobStateMachine` already has the full DAG incl. `paused⇄running` + `cancelled`; lore already emits create events to the unified projection (`D-JOBS-P4-LORE-MODEL`, B1 M1).
- P5 fair-sched lease (`fair_sched.acquire/release_job`) already wraps the run.

So the gap is narrow: **the initial run is the one path that runs inline instead of on the worker.**

## 2. Goal / acceptance criteria

1. `POST /v1/lore/jobs` returns **`202 + job_id`** immediately (job row `pending`/`queued`); the run
   happens on the worker, not in the request.
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
| **Work DISPATCH** (create → the worker that runs it) | **Direct Redis `XADD`** to a service stream (`LORE_ENRICHMENT_RESUME_STREAM`), consumed by a `loreweave_jobs.BaseTerminalConsumer`, **backed by** (a) the durable `save_job_request` row and (b) a **stranded-job sweeper** that re-drives any non-terminal job whose trigger was lost | The durable state is the job row + persisted request; a lost XADD is recovered by the sweeper (at-least-once). NOT a transactional outbox — dispatch intent is reconstructable from the row, so it doesn't need exactly-once relay. compose explicitly does this ("the job + request persist; re-triggerable", [compose.py:332](../../services/lore-enrichment-service/app/api/compose.py#L332)). | ◐ compose + resume conformant; **the primary `POST /jobs` create path BYPASSES it** (runs inline). |

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

## 6. Size — L, not XL

The debt row tags this XL because it assumed Option B (green-field per-unit decouple). With the worker,
resume consumer, state machine, request persistence, fair-sched, and emit wiring **already present**,
Option A is **L**: the work is (a) flip the create path from inline-run to enqueue+202, (b) add a "run"
message kind to the existing dispatch, (c) add the between-gap cancel/pause checkpoint, (d) wire lore
into the unified control plane. No new service, no new transport, **no migration** (the job row, request
table, and status vocabulary already exist).

## 7. Slices (Option A)

- **S1 — async create** (reuses the compose precedent verbatim). `POST /jobs` → pre-checks (preserve
  429/409/400) → create row + `save_job_request` → **XADD** a "run" trigger to `LORE_ENRICHMENT_RESUME_STREAM`
  → `202 {job_id, status:"pending"}`. Worker `dispatch_resume_message` gains the "run" kind (a fresh run
  = `redrive_one` with `skip_gap_refs=∅` — already noted at [gaps.py:227](../../services/lore-enrichment-service/app/api/gaps.py#L227)). Move the P5 acquire/release into the worker (lease the slot where the work
  runs; the create pre-check still rejects at cap). Emit `pending`→`running`→terminal via the existing
  transactional-outbox `emit_job_event` (unchanged). **Durability:** confirm/extend the **stranded-job
  sweeper** so a create-enqueued `enrichment_job` left non-terminal (lost XADD) is re-driven — symmetric
  with the existing compose-task sweeper (the lost-XADD backstop; matches the §3.1 dispatch pattern).
  - **HIGH-2 (per-job claim — MUST):** before a worker runs a job it MUST atomically CLAIM it (CAS
    `pending`→`running` on the row, OR a `pg_advisory_xact_lock(hashtext(job_id))`), and a delivery that
    fails to claim (job already `running`/terminal) NO-OPs + acks. Without it, create-XADD +
    stranded-sweeper-XADD + resume-XADD can drive the SAME job concurrently — P5's lease is per-OWNER not
    per-job, and `redrive_one` dedups proposals only at PERSIST (after the LLM spend), so two concurrent
    runners double-spend real tokens. The claim is the serialization point.
  - **MED-3 (gap-rebuild parity — VERIFY):** the in-request path computes `gaps` then passes them to
    `run_job`; `redrive_one` rebuilds gaps from `request["targets"]` via `_gap_from_target`. CLARIFY-S1
    must confirm the persisted targets reconstruct the IDENTICAL gap set the sync path computed (else the
    async run diverges). If the sync path does richer detection than the targets carry, persist the
    detected gap refs too.
  - **MED-5 (P5 acquire semantics — DECIDE):** when the POST pre-check passes but the worker can't acquire
    (cap full at run-time), the worker **acquire-or-requeue** (leave the job `pending`, re-trigger later)
    rather than fail — preserves "no work runs over cap" while keeping the pre-check as the fast 429.
  - **Contract change to flag:** the handler no longer returns the synchronous outcome (proposals list) —
    FE must poll/stream the job. (See §9.)
- **S2 — cancel/pause checkpoint (with the HIGH-1 guard).** `run_job` re-reads the job's persisted status
  before each gap; `cancelling`→graceful stop + emit; manual `paused`→stop resumable. Generalize the
  existing cost-cap-pause shape.
  - **HIGH-1 (guarded transition — MUST):** the runner and the external control endpoint
    ([_transition_job](../../services/lore-enrichment-service/app/api/jobs.py#L438)) are TWO independent
    writers to `enrichment_job.status` with no CAS today — so an external `cancel`/`pause` mid-run is
    silently CLOBBERED when the runner's `machine.complete()` (trusting its in-memory `running`) writes
    `completed` over it. Every runner status write MUST become a **guarded** transition: re-read the DB
    status (under the same tx / row lock) and only advance if the DB hasn't been externally moved to a
    terminal/paused state — i.e. the runner YIELDS to a concurrent control action instead of overwriting
    it. The between-gap checkpoint is the read half; the conditional terminal write is the write half.
- **S3 — control-plane wiring + retry.** jobs-service `derive_control_caps`: lore kind →
  cancel(running|paused) + resume(paused) + retry(failed). lore `internal_job_control` (new, mirrors
  knowledge/translation) routes cancel→status-CAS, resume/retry→enqueue (skip-done). Add lore to
  `_RETRYABLE_KINDS`. → closes `D-JOBS-P4-RETRY-LORE`.
- **S4 — FE/SDK.** Retry/Cancel/Resume are data-driven off `control_caps` (likely zero FE change beyond a
  kind label + i18n×4). The FE create flow switches to 202+poll (the S1 contract change).
  - **MED-4 (FE create UX — VERIFY):** check whether the FE create flow renders the proposals INLINE from
    the synchronous POST response. If so, 202+poll is a UX redesign (submit → loading → poll job →
    show proposals from the list endpoint), not just a wire-contract swap — scope S4 accordingly.

## 8. Invariants & risks

- **Synchronous-rejection contract** (P5 cap 429 / eval-gate 409 / bad-strategy 400): keep these as fast
  pre-checks on `POST` BEFORE enqueue, so callers still get the immediate rejection (don't move them into
  the worker where they'd only surface as a failed row).
- **API contract change (biggest consumer impact):** `POST /jobs` currently returns the full outcome;
  after S1 it returns `202 + job_id`. Every caller (FE create flow, any SDK/test) must switch to polling
  the job + reading proposals from the list endpoint. **PO must confirm** this contract change; consider
  a deprecation note. *(Enumerate callers in CLARIFY of S1.)*
- **Cancel granularity:** between-gap, not mid-gap (a gap in flight finishes or is abandoned). Acceptable
  (gaps are bounded units); document it.
- **Idempotent at-least-once:** the run stream is at-least-once; `redrive_one` is already idempotent
  (UNIQUE + skip-done + seeded spend), so a redelivered "run" is safe.
- **H0 / provider-gateway / no-model-literal** gates unchanged (the worker runs the same pipeline).
- **LOW-6 (double `build_live_runner`):** the gate pre-check on POST + the real build on the worker build
  the runner twice. Accept (it's cheap relative to the run), or replace the POST pre-check with a light
  gate-only probe. Decide in S1; not blocking.

## 8a. Design-review findings (REVIEW-design, 2026-06-18 — folded in above)

Adversarial self-review against the code surfaced 6 findings, all folded into the slices:
- **HIGH-1** concurrent status-writer clobber (runner vs control endpoint, no CAS) → S2 guarded transition. *Latent today.*
- **HIGH-2** per-job double-run wastes LLM spend (per-owner lease ≠ per-job) → S1 per-job claim.
- **MED-3** gap-rebuild parity (sync `gaps` vs worker rebuild-from-targets) → S1 verify.
- **MED-4** FE create UX (inline proposals vs poll) → S4 verify.
- **MED-5** P5 acquire semantics on the worker → S1 acquire-or-requeue.
- **LOW-6** double `build_live_runner` → S1 decide.
HIGH-1 + HIGH-2 are correctness/money-path requirements, NOT polish — they gate BUILD acceptance.

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
