# Unified Background-Job Control Plane

**Status:** DESIGN v2 (PO-approved direction 2026-06-15; revised after design review — H1–H4
+ M1–M5 folded in). Epic — phased build.
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

- **Aggregation = a central job-projection** (not BFF fan-out). Jobs emit lifecycle events →
  a projection maintains a unified table → serves list/search/detail + **real-time SSE** +
  routes control. Scalable, searchable, live.
- **Build order = the shared consumer SDK FIRST** (L2), then projection (L3), control
  endpoints, then GUI (L4).

## Current state (survey 2026-06-15)

- **Ownership ~80% done:** campaigns, knowledge `extraction_jobs`, provider-registry
  `llm_jobs`, composition `generation_jobs`, translation `translation_jobs`, lore-enrichment,
  video-gen all carry `owner_user_id`/`user_id`. Gaps: a few `resume_state` blobs + naming
  inconsistency (`owner_user_id` vs `user_id`).
- **Control partial:** campaigns (pause/resume/cancel + GUI ✅), knowledge extraction
  (endpoints, no GUI), provider-registry llm_jobs (cancel ✅). **No control:** composition
  generation_jobs, translation, video-gen; lore-enrichment has pause/resume but no cancel.
- **Scattered consumers:** 5+ hand-rolled terminal-event consumers (translation
  `llm_terminal_consumer`, worker-ai `llm_extract_consumer`, knowledge, video-gen, learning)
  — no shared base; a PEL-reclaim bug was copied between two.
- **Reusable:** the `loreweave:events:llm_job_terminal` stream; provider-registry `CancelFunc`
  abort + reservation release; campaign saga pause/resume + `_propagate_cancel`; the
  `CampaignMonitor`/`MonitorControls` FE (to generalize for L4); existing **outbox** infra
  (translation/composition/campaign) + **statistics-service** projections + **notification-
  service** SSE bridge (candidates to host the projection — see L3/M3).

---

## Architecture

### L0 — Canonical job contract  *(revised: H2, H3, M2, LOW)*
The standard shape every service emits + the projection stores:
```
JobRecord {
  service: str               # owning service — the control-routing target
  job_id: uuid               # the DOMAIN job id (unique within service); PK = (service, job_id)
  owner_user_id: uuid        # REQUIRED — req 1. The OWNER, not the BYOK biller (LOW).
  parent_job_id: uuid | null # H3 — e.g. a campaign; children group under it in the GUI
  kind: str                  # "extraction" | "translation" | "composition.generate" | "video_gen" | "campaign" | …
  status: pending | running | paused | cancelling | completed | failed | cancelled   # canonical
  detail_status: str | null  # M2 — service-native passthrough ("summarizing", stage labels…)
  progress: {done:int, total:int} | null   # LOW — null for single-call / streaming jobs; GUI handles null
  control_caps: [cancel?, pause?, resume?]  # STATE-AWARE: what's valid for THIS job in its CURRENT status
  title: str                 # human label ("万古神帝 — knowledge extract ch 1-40")
  error: {code, message} | null
  created_at / updated_at
}
```
**Removed `provider_job_id` (H2):** a domain job has 1:N provider LLM jobs (extraction ≈ 75,
the trio = 3). Live-cancel is **always domain-level** — the projection never addresses a
provider job; cancel routes to the owning service which aborts its own in-flight provider
jobs (mirrors campaign `_propagate_cancel`). Provider-job linkage stays internal per service.
`JobStatus`, `ControlCap`, `JobRecord`, `JobEvent` live in the SDK (L2), shared by every
service + the FE.

### L1 — Ownership (req 1)
Audit every job table; backfill/standardize `owner_user_id`. The list query keys on it. The
**owner** (not the BYOK `billing_user_id`) determines whose GUI a job appears in. Ownerless
system sweeps are out of the user GUI by design.

### Consistency model  *(NEW — H1; the load-bearing correctness decision)*
A control plane must NOT be a best-effort mirror — a dropped event = a job stuck "running"
forever in the GUI, or a missing failed job. So lifecycle events are emitted via the
**transactional outbox** each producing service already runs (the event row is written in
the SAME tx as the job-row status change → relayed exactly-once), NOT a fire-and-forget
publish. The projection is still a **mirror** (the domain job rows are SSOT); to heal any
residual drift (outbox lag, projection-service downtime) the projection runs a **reconcile
sweep**: periodically re-read each service's job rows (a cheap `GET /internal/jobs?since=`)
and upsert. Outbox = primary path; reconcile = backstop. The GUI tolerates brief staleness
(a cancel on an already-terminal job is a clean 409 from the owning service).

### L2 — `sdks/python/loreweave_jobs/` shared SDK (req 3) — **PHASE 1**  *(revised: H4)*
Pieces:
1. **`contract.py`** — `JobStatus`, `ControlCap`, `JobRecord`, `JobEvent`, stream constants.
2. **`consumer.py` — `BaseTerminalConsumer`** — scoped to the genuinely-shared **transport
   scaffold ONLY** (NOT the business logic), via **template-method hooks**: BUSYGROUP-safe
   `xgroup_create`, startup PEL drain, main loop (`socket_timeout=None`, `block=`, redis-py-8
   `TimeoutError`-as-idle), bounded retry + DLQ, `sweep_once`/`run_sweeper` scaffold. Subclass
   supplies `stream`/`group`/`operation` + implements `async fold(msg)` / `claim()` /
   `persist()`. This deliberately does NOT unify fold/claim (they legitimately differ per
   service) — over-unifying would re-introduce the bugs we're deduping. It codifies the
   lessons: PEL-reclaim correctness, redis-py-8 idle `TimeoutError`, operation pre-filter,
   `FOR UPDATE SKIP LOCKED` sweep, CAS finalize/bill-once.
3. **`emit.py` — `emit_job_event(...)`** — writes a `JobEvent` to the producer's **outbox**
   (same tx as the status change) for relay to `loreweave:events:jobs`. Idempotent on
   `(service, job_id, status)`.

**Migration (H4 — incremental + flagged + live-smoked, NOT big-bang):**
- Migrate ONE consumer at a time onto `BaseTerminalConsumer`, behavior-preserving.
- Each migration ships behind a **flag with the old consumer as fallback**; flip only after
  a **live-smoke** (unit-green is insufficient for these — past smokes caught real bugs).
- **Order: simplest first (video-gen) as the pattern-proof; the money-path worker-ai
  extraction LAST**, with extra scrutiny (a regression there double-spends or strands jobs).
- Wire `emit_job_event` on each migrated consumer's status transitions (feeds L3).

### L3 — Job projection + API (req 2 backend) — PHASE 2  *(revised: M3, M4)*
- **Host (M3):** evaluate reusing **statistics-service** (already event→projection) or
  **notification-service** (already the SSE bridge) BEFORE standing up a new `jobs-service` —
  prefer reuse to avoid a new deployable. Decision at P2 DESIGN.
- Consumes `loreweave:events:jobs` (via `BaseTerminalConsumer`) → upserts `job_projection`
  (`PK (service, job_id)`, `owner_user_id` + `parent_job_id` indexed) + runs the reconcile sweep.
- **API:** `GET /v1/jobs?owner=me&status=&kind=&parent=&q=&cursor=` (paged, searchable,
  **groups children under parent**), `GET /v1/jobs/{service}/{job_id}` (detail),
  `GET /v1/jobs/stream` (SSE live — reuse the notifications SSE-bridge pattern).
- **Control routing:** `POST /v1/jobs/{service}/{job_id}/{cancel|pause|resume}` → checks
  the job's CURRENT `control_caps` + owner → forwards to the owning service's control
  endpoint (internal auth). **M4: the owning service RE-VERIFIES ownership on the actual row**
  (never trust the projection's possibly-stale owner) — no cross-tenant cancel vector.
  Cancel reuses provider-registry `CancelFunc`; pause = stop new dispatch (see below).
- Gateway routes `/v1/jobs/*` → the projection host.

### Per-service control endpoints (req 2) — PHASE 3  *(revised: M5)*
Add the missing cancel/pause/resume to composition `generation_jobs`, translation jobs,
video-gen, lore-enrichment (cancel). **Pause semantics are per-kind (M5):**
- Multi-unit jobs (extraction over chapters, campaigns): pause = **stop dispatching new
  units, drain in-flight**; resume = re-arm dispatch.
- Single-LLM-call jobs (video_gen, one compose call): **cancel-only** — no pause cap.
- `control_caps` is **state-aware**: a `completed` job offers nothing; a `running` multi-unit
  job offers pause+cancel; a `paused` one offers resume+cancel.
- **Resume ≠ sweeper re-drive (M5):** manual resume un-pauses a USER-paused job (re-arms
  from `resume_state`); the auto-sweeper re-drives a STRANDED job. They are distinct states
  and must not fight (a user-paused job is NOT stranded — the sweeper skips `paused`).

### L4 — Unified Jobs GUI (req 2 frontend) — PHASE 4
A "Jobs" dashboard: list the user's jobs (live via SSE), **children grouped under their
parent** (a campaign shown once, expandable — H3), filter by kind/status, per-row status +
`detail_status` + progress (null-safe) + **cancel/pause/resume** buttons gated on the job's
state-aware `control_caps` (generalize `MonitorControls`). Job detail reuses `CampaignMonitor`
panels. `kind=campaign` deep-links to the existing campaign monitor (kept as-is).

---

## Phasing  *(revised: M1)*

| Phase | Deliverable | Size |
|---|---|---|
| **P0 (optional, M1)** | Thin "every job kind has a cancel endpoint" slice — so any job is cancellable via API/curl **before** the GUI lands (addresses the user's acute pain sooner). PO call. | S-M |
| **P1** | `loreweave_jobs` SDK (contract + `BaseTerminalConsumer` template + `emit` via outbox) + **incremental flagged + live-smoked** migration of the 5 consumers (video-gen first, worker-ai last) | L |
| **P2** | Job projection (reuse statistics/notification if possible) — consume job events → table → list/detail/SSE + reconcile sweep | L |
| **P3** | Per-service cancel/pause/resume control endpoints + ownership backfill + control routing w/ owner re-check | M-L |
| **P4** | Unified Jobs GUI (dashboard + grouped list + state-aware controls, generalize `CampaignMonitor`) | M-L |

Campaign-service control + monitor stay as-is (already complete); campaigns appear in the
unified list as `kind=campaign` (parent of their child jobs) and deep-link to the monitor.

## Invariants / gotchas to carry

- **Consistency (H1):** emit via outbox (same tx), reconcile-sweep backstop — never best-effort.
- **Control is domain-level (H2):** never address a provider job; the owning service aborts
  its own in-flight provider jobs (free the governor slot via `CancelFunc` + reservation release).
- **Grouping (H3):** `parent_job_id` — children group under the parent; never flood the GUI.
- **Base consumer is a transport scaffold (H4):** template-method hooks; migrate incrementally,
  flagged, live-smoked; money-path (worker-ai) last.
- **Owner re-check (M4):** the owning service re-verifies ownership on the row before control.
- **Pause is per-kind + state-aware (M5);** resume(un-pause) ≠ sweeper(re-drive); sweeper skips `paused`.
- Provider-gate: no hardcoded models; control routing service→service via internal auth.
- Per-user scoping everywhere — never a cross-tenant job leak in list, detail, or control.

## Acceptance (epic)

- A user opens "Jobs", sees every running/recent background job they own across all services
  (children grouped under campaigns), and can cancel/pause/resume each per its state-aware
  capabilities — including a long glossary/knowledge extraction.
- One shared transport-scaffold consumer; the 5 hand-rolled copies migrated onto it (money-path
  live-smoked); no bug-copy surface.
- Projection stays consistent with the SSOT job rows (outbox + reconcile); zero cross-tenant leak.

## Open questions for PO

1. **P0 thin-cancel slice (M1)** — pull a "cancel endpoint for every kind" slice ahead of the
   SDK so you get relief sooner, or stay strict SDK-first?
2. **Projection host (M3)** — reuse statistics-service / notification-service, or a new
   `jobs-service`? (Decide at P2 DESIGN; bias to reuse.)
