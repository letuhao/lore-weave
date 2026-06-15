# P1 Tail — Unified Job Control Plane (stack-dependent close-out + emit-wiring)

**Epic spec:** [`docs/specs/2026-06-15-unified-job-control-plane.md`](../specs/2026-06-15-unified-job-control-plane.md)
**P1 plan:** [`docs/plans/2026-06-15-job-control-plane-p1.md`](2026-06-15-job-control-plane-p1.md)
**Classified:** XL (discovered in DESIGN — emit-wiring spans every GUI-relevant job-owning service).
**Mode:** `/loom` continuous-flow; checkpoint/commit at each milestone (risk boundary).

## Scope (PO: "include emit-wiring now", 2026-06-15)

Three items from SESSION_HANDOFF line 229:
1. **Money-path flip + live-smoke** — `extraction_consumer_use_sdk=true`, rebuild/restart worker-ai, run a real decoupled extraction (entity→trio→persist, **no double-spend**), then make it the default.
2. **Emit-wiring** — every GUI-relevant job-owning service writes `JobEvent` rows to its `outbox_events` (aggregate_type=`jobs`) in the **same tx** as the status change → worker-infra relay → `loreweave:events:jobs`.
3. **Batched boot live-smoke (`D-JOBS-MIGRATE-LIVE-SMOKE`)** — rebuild ~12 images, confirm every migrated consumer group boots on its correct stream.

## Key design findings (DESIGN phase)

- **Relay routes by `aggregate_type`** ([`outbox_relay.go`](../../services/worker-infra/internal/tasks/outbox_relay.go)): it reads ALL unpublished rows from each configured source's `outbox_events` and XADDs each to `loreweave:events:<aggregate_type>`. So a service **already** a relay source needs **no new table/registration** — just emit rows with `aggregate_type='jobs'`.
- **Current `OUTBOX_SOURCES`** (docker-compose:1004): book, translation, chat, glossary, knowledge, composition. worker-ai shares knowledge's DB/outbox.
- **Services with `outbox_events` already:** worker-ai, knowledge, translation, composition, glossary, book, chat.
- **Services lacking it (need new table + OUTBOX_SOURCES entry):** **campaign, lore-enrichment, video-gen** (learning judges are internal-eval, NOT user-facing → out of GUI scope, like spend_consumer).
- **Emit shape is frozen**: `loreweave_jobs.emit_job_event(conn, service, job_id, owner_user_id, kind, status, …)` (in-tx, raises) + `_safe`. `job_id` must be UUID-coercible (all in-scope job ids are UUIDs). Reference pattern: [`worker-ai/app/outbox_emit.py`](../../services/worker-ai/app/outbox_emit.py).

## GUI-scope decision (emit which job kinds?)

User pain = long-running user-facing background jobs. **In scope:** knowledge/worker-ai extraction (`extraction_jobs`), translation (`translation_jobs`), composition (`generation_job`), campaign (campaign run), lore-enrichment (`enrichment_job` + `compose_task`), video-gen (`video_gen_jobs`). **Out of scope:** learning judges (internal eval), chat streams (ephemeral), campaign `spend_consumer` (`D-JOBS-SPEND-CONSUMER-MISFIT`).

## Milestones (commit at each)

- **M-T1 — money-path flip + live-smoke** (item 1). worker-ai only + docker-compose default. Live: real extraction E2E, no double-spend, group `*-extract` on the SDK base. Flip `extraction_consumer_use_sdk` default→True after green.
- **M-T2 — emit infra** (item 2a): `outbox_events` table migrations for campaign / lore-enrichment / video-gen + OUTBOX_SOURCES (+ worker-infra source pools). Additive.
- **M-T3 — emit callsites** (item 2b): `emit_job_event` at each in-scope service's status transitions (pending→running→completed/failed/cancelled), same tx; per-service wiring tests. Reuse the existing per-service outbox helper shape.
- **M-T4 — batched boot live-smoke** (item 3, `D-JOBS-MIGRATE-LIVE-SMOKE`): rebuild touched images, confirm every consumer group + the `jobs` relay source boots; spot-check a `jobs` event lands on `loreweave:events:jobs` (producer-half smoke; full consume is P2).

## Risk / caveats

- **Emit has no consumer yet** (P2 projection). M-T3/M-T4 prove only the **producer half** (row → outbox → stream XLEN grows). The shape is SDK-contract-tested; full validation lands in P2. Flagged to PO at CLARIFY; PO chose to proceed.
- Money-path = double-spend surface → M-T1 must confirm CAS bill-once on a real run before default-on.
- All emit callsites use the in-tx `emit_job_event` where the status change is a DB write we control; `_safe` only where the transition already committed.
