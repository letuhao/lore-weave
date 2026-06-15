# Unified Background-Job Control Plane

**Status:** DESIGN (PO-approved direction 2026-06-15). Epic — phased build.
**Problem owner:** the user has long-running background jobs (e.g. a multi-hour glossary/
knowledge extraction) with **no way to see, cancel, pause, or resume** them. Jobs are
**scattered** across services, each hand-rolling its own worker/consumer.

## Goals (the 3 requirements)

1. **Every background job belongs to a user** — uniform `owner_user_id` + a canonical job shape.
2. **One centralized GUI** to monitor ALL background jobs across services, with **cancel /
   pause / resume** per job.
3. **A shared component per job type** — one abstraction every worker/consumer is built on
   (no more 5 hand-rolled copies + bug-copy drift).

## PO decisions (2026-06-15)

- **Aggregation = a central job-projection service** (not BFF fan-out). Every job emits
  lifecycle events → a `jobs-service` maintains a unified projection table → serves
  list/search/detail + **real-time SSE** + routes control. Scalable, searchable, live.
- **Build order = the shared consumer SDK FIRST** (L2), then projection (L3), control
  endpoints, then GUI (L4). The SDK is the foundation the projection consumes from.

## Current state (survey 2026-06-15)

- **Ownership ~80% done:** campaigns, knowledge `extraction_jobs`, provider-registry
  `llm_jobs`, composition `generation_jobs`, translation `translation_jobs`,
  lore-enrichment, video-gen all already carry `owner_user_id`/`user_id`. Gaps: a few
  `resume_state` blobs + naming inconsistency (`owner_user_id` vs `user_id`).
- **Control partial:** campaigns (pause/resume/cancel + GUI ✅), knowledge extraction
  (pause/resume/cancel endpoints, no GUI button), provider-registry llm_jobs (cancel ✅).
  **No control:** composition generation_jobs, translation jobs, video-gen; lore-enrichment
  has pause/resume but no cancel.
- **Scattered consumers:** 5+ hand-rolled terminal-event consumers (translation
  `llm_terminal_consumer`, worker-ai `llm_extract_consumer`, knowledge, video-gen,
  learning) — no shared base; a PEL-reclaim bug was copied between two.
- **Reusable:** the `loreweave:events:llm_job_terminal` stream; provider-registry's
  `CancelFunc` abort + reservation release; campaign saga pause/resume semantics; the
  `CampaignMonitor`/`MonitorControls` FE (to generalize for L4).

## Architecture

### L0 — Canonical job contract
A standard shape every service exposes + emits:
```
JobRecord {
  job_id: uuid            # the DOMAIN job id (extraction_job, generation_job, …)
  owner_user_id: uuid     # REQUIRED — req 1
  kind: str               # "extraction" | "translation" | "composition.generate" | "video_gen" | "campaign" | …
  status: pending | running | paused | cancelling | completed | failed | cancelled
  progress: {done:int, total:int} | null
  control_caps: [cancel?, pause?, resume?]   # what the GUI may offer for THIS kind
  title: str              # human label ("万古神帝 — knowledge extract ch 1-40")
  provider_job_id: uuid | null   # the in-flight LLM job, if any (for live cancel)
  error: {code, message} | null
  service: str            # owning service (for control routing)
  created_at / updated_at
}
JobStatus enum + ControlCap flags live in the SDK (L2), shared by every service + the FE.
```

### L1 — Ownership (req 1)
Audit every job table; backfill/standardize `owner_user_id`. The contract's list query
keys on it. Jobs with no owner (e.g. system sweeps) are out of the user GUI by design.

### L2 — `sdks/python/loreweave_jobs/` shared SDK (req 3) — **PHASE 1**
Three pieces:
1. **`contract.py`** — `JobStatus`, `ControlCap`, `JobRecord`, `JobEvent` (the lifecycle
   event), `job_event_stream` constant.
2. **`consumer.py` — `BaseTerminalConsumer`** — encapsulates the proven pattern the 5
   copies share: BUSYGROUP-safe `xgroup_create`, startup drain of the PEL, main loop
   (`socket_timeout=None`, `block=`, redis-py-8 `TimeoutError`-as-idle), **operation
   pre-filter** (skip events not ours before the DB lookup), bounded retry + DLQ, and a
   `sweep_once`/`run_sweeper` stuck-job backstop. Subclass implements `async fold(job)` +
   `operation` + `claim/persist`. (Codifies the lessons: PEL-reclaim correctness, the
   wake redis-py-8 TimeoutError fix, the operation pre-filter, FOR UPDATE SKIP LOCKED.)
3. **`emit.py` — `emit_job_event(redis, JobEvent)`** — publishes a lifecycle event to
   `loreweave:events:jobs` on every status transition. The projection service (L3)
   consumes this. Best-effort + idempotent (status+job_id dedup).

**Phase 1 migration:** move the 5 consumers onto `BaseTerminalConsumer` ONE at a time,
preserving exact behavior, suite-green per service. Each migration also wires
`emit_job_event` on its status transitions (feeds L3).

### L3 — `jobs-service` projection (req 2 backend) — PHASE 2
- Consumes `loreweave:events:jobs` (via `BaseTerminalConsumer`!) → upserts a
  `job_projection` table (the JobRecord, keyed by `(service, job_id)`, owner-indexed).
- **API:** `GET /v1/jobs?owner=me&status=&kind=&q=&cursor=` (paged, searchable),
  `GET /v1/jobs/{service}/{job_id}` (detail), `GET /v1/jobs/stream` (SSE live updates —
  reuse the notifications SSE-bridge pattern).
- **Control routing:** `POST /v1/jobs/{service}/{job_id}/{cancel|pause|resume}` →
  validates `control_caps` + ownership → forwards to the owning service's control endpoint
  (internal-auth). Cancel reuses provider-registry `CancelFunc`; pause = stop new dispatch.
- Gateway routes `/v1/jobs/*` → jobs-service.

### L4 — Unified Jobs GUI (req 2 frontend) — PHASE 4
- A "Jobs" dashboard: list the user's jobs (live via SSE), filter by kind/status, per-row
  status + progress + **cancel/pause/resume** buttons gated on `control_caps` (generalize
  `MonitorControls`). Job detail reuses the `CampaignMonitor` panels.

### Per-service control endpoints (req 2) — PHASE 3
Add the missing cancel/pause/resume to: composition `generation_jobs`, translation jobs,
video-gen, lore-enrichment (cancel). Pause semantics = capability-based: a multi-unit job
(extraction over chapters) supports pause (stop dispatching new units, let in-flight
finish — like campaigns); a single-LLM-call job supports only cancel. The SDK's
`control_caps` declares per-kind what's offered.

## Phasing

| Phase | Deliverable | Size |
|---|---|---|
| **P1** | `loreweave_jobs` SDK (contract + BaseTerminalConsumer + emit) + migrate the 5 consumers | L |
| **P2** | `jobs-service` projection (consume job events → table → list/detail/SSE API) | L |
| **P3** | Per-service cancel/pause/resume control endpoints + ownership backfill + control routing | M-L |
| **P4** | Unified Jobs GUI (dashboard + controls, generalize CampaignMonitor) | M-L |

Campaign-service control + its monitor stay as-is (already complete); campaigns appear in
the unified list as `kind=campaign` and the GUI deep-links to the existing monitor.

## Invariants / gotchas to carry

- Provider-gate: no hardcoded models; control routing goes service→service via internal auth.
- Cancel must free the provider governor slot (reuse `CancelFunc` + reservation release).
- Pause must not strand in-flight (drain), and resume must re-arm from `resume_state`.
- The `BaseTerminalConsumer` must bake in: redis-py-8 idle `TimeoutError`, PEL reclaim,
  operation pre-filter, FOR UPDATE SKIP LOCKED sweep, CAS bill/finalize-once.
- Per-user scoping everywhere — never a cross-tenant job leak in the list or control.

## Acceptance (epic)

- A user opens "Jobs", sees every running/recent background job they own across all
  services, and can cancel/pause/resume each per its capabilities — including a long
  glossary/knowledge extraction.
- One shared consumer base; the 5 hand-rolled copies deleted.
- Cross-tenant isolation proven (user A never sees/controls user B's jobs).
