# Job Control Plane — P2: `jobs-service` projection + read API + SSE

**Epic:** [Unified Background-Job Control Plane](../specs/2026-06-15-unified-job-control-plane.md) · **Phase:** P2 (L)
**Predecessor:** P1 + P1-tail DONE (SDK + 11/12 consumers migrated + `emit_job_event` wired across 6 job-owning services → `loreweave:events:jobs`; producer-half live-proven). **This phase consumes that stream** and closes the producer-half caveat.

## Goal (req 2 backend)

A NEW `jobs-service` (Python/FastAPI, PO decision 2026-06-15) that:
1. Consumes `loreweave:events:jobs` → upserts a unified `job_projection` table (`PK (service, job_id)`).
2. Serves `GET /v1/jobs` (list, paged, searchable, **children grouped under parent**) + `GET /v1/jobs/{service}/{job_id}` (detail) + `GET /v1/jobs/stream` (SSE live).
3. Derives **state-aware `control_caps`** per job (the GUI gates its buttons on these). Control ROUTING is P3.
4. Runs a **reconcile-sweep scaffold** (the H1 backstop). The cross-service `GET /internal/jobs?since=` endpoints fold into P3 (same service surface as control) — tracked, NOT silently dropped.

Out of P2: per-service control endpoints (P3) + the GUI (P4).

## Architecture (mirrors campaign-service — the closest analog)

```
services/jobs-service/
  Dockerfile · requirements.txt · requirements-test.txt · pytest.ini
  app/
    main.py        FastAPI + lifespan (pool → migrate → projection consumer task → SSE pub/sub → reconcile task)
    config.py      Settings (JOBS_DB_URL, JWT_SECRET, INTERNAL_SERVICE_TOKEN, REDIS_URL, reconcile knobs, per-service internal URLs)
    database.py    asyncpg pool (create/close/get)
    deps.py        get_current_user (VERIFIED HS256 JWT — owner scoping is a security boundary), get_db
    migrate.py     job_projection + dead_letter_events DDL (idempotent) + run_migrations/run_down
    contract.py    control_caps derivation (state-aware, per-kind pause capability) — pure
    projection/
      store.py     upsert_job_event (convergent + idempotent, monotonic on status/updated_at) · list_jobs (cursor, parent-group) · get_job
      consumer.py  JobProjectionConsumer(BaseProjectionConsumer) → parse payload → upsert → publish SSE notify
    sse.py         per-user Redis pub/sub bridge (consumer publishes loreweave:jobs:user:<owner>; SSE endpoint subscribes, owner-scoped)
    reconcile.py   ReconcileSweeper scaffold (periodic; per-service /internal/jobs?since= = P3)
    routers/jobs.py  GET /v1/jobs · GET /v1/jobs/{service}/{job_id} · GET /v1/jobs/stream (SSE)
  tests/  conftest + unit (store/control_caps/consumer/api/sse)
```

### Consistency model (H1)
Outbox (in-tx emit, P1) = primary; reconcile = backstop. The projection is a **mirror** (domain rows are SSOT).
`upsert_job_event` is **idempotent + monotonic**: a terminal status is never overwritten by a late non-terminal
event (at-least-once + reclaim can redeliver/reorder). Consumer uses **retry→DLQ** (`dead_letter_events`); the
reconcile sweep heals anything dead-lettered.

### control_caps (M5, state-aware) — pure derivation in `contract.py`
- `completed | failed | cancelled` (terminal) → `[]`
- `running` → `[cancel]` + `[pause]` iff the kind is multi-unit (extraction, campaign, translation)
- `paused` → `[resume, cancel]`
- `pending` → `[cancel]`
- `cancelling` → `[]` (already in-flight)
Single-LLM-call kinds (video_gen, composition.*) are **cancel-only** (no pause cap). The multi-unit kind set is a
small allowlist; unknown kinds default to cancel-only (conservative — never offer a pause that the owner can't honor).

### owner scoping (security)
Every list/detail/stream query filters `owner_user_id = <verified JWT sub>`. No cross-tenant leak — the spec's
load-bearing invariant. Detail on a job the caller doesn't own → 404 (anti-oracle, not 403).

## Milestones (risk-boundary commits)

| M | Scope | Risk boundary |
|---|---|---|
| **M1** | scaffold + migrate (job_projection + dead_letter_events) + store.upsert + projection consumer | **DB + consumer** — closes the producer-half caveat (events land in a table) |
| **M2** | store.list/get + control_caps + routers (list/detail) + gateway route + infra (compose svc, 01-databases.sql, db-ensure.sh) | **cross-service seam** (new deployable + gateway) |
| **M3** | SSE `/v1/jobs/stream` (per-user Redis pub/sub bridge) + consumer publish | live path |
| **M4** | reconcile-sweep scaffold; defer per-service `/internal/jobs?since=` to P3 (tracked) | backstop |

## VERIFY
- Per-milestone pytest (store upsert idempotence/monotonicity, control_caps table, consumer parse→upsert, API owner-scoping + pagination + parent-grouping, SSE owner filter).
- **Live-smoke (≥2 services — this is the whole point):** bring up jobs-service on the stack, trigger a real extraction start+cancel, confirm the events flow emit→outbox→relay→`loreweave:events:jobs`→**jobs-service projection** and surface via `GET /v1/jobs` (the producer-half caveat closed end-to-end). Token: `live smoke: …`.

## Deferred (tracked)
- `D-JOBS-P2-RECONCILE-CROSS-SVC` — the per-service `GET /internal/jobs?since=` endpoints the reconcile sweep calls fold into P3 (same service surface as control). The sweeper scaffold ships in P2; outbox (proven) is the primary path until then.
- `D-JOBS-P2-SSE-LIVE-SMOKE` — the real SSE push (consumer upsert → pub/sub → connected client receives) on the stack, if not driven this run.
