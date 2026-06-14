# Wave 1 — Production wiring (spec)

**Status:** CLARIFY → DESIGN. Size **XL** (bundled). One task per the user's batch
cadence: spec+plan once, `/review-impl` plan + impl, autonomous through items → one
POST-REVIEW → push-ask.

## Why

The S1–S14 test program proved the L1 *designs* (lifecycle CAS, capacity planner,
migration canary, cross-shard relocation, ordering). Several are **proven but not
wired to production**. Wave 1 closes that gap so L1 is production-runnable — the
highest-leverage do-now slice from `docs/plans/2026-06-14-post-S14-deferred-cleardown.md`.

CLARIFY (2026-06-14): **full scope incl. the Rust→Go meta-write bridge**, bundled XL.

## Invariants honored
- **I8** — every `reality_registry` (and other meta-table) write lands a
  `meta_write_audit` row in the SAME TX via Go `MetaWrite`. This is WHY the Rust
  provisioner needs a bridge (it cannot write the registry directly).
- **Language rule** — world-service + the kernel stay Rust; meta + orchestrator stay
  Go. The bridge is Go-hosted; world-service calls it as a client.
- **Gateway invariant** — N/A: the meta-write bridge is **internal service-to-service**
  (not external traffic), authenticated by a service token + audited in
  `service_to_service_audit`. It is NOT exposed through the gateway.

## Items

### W1.1 — Capacity routing glue (closes D-S13-CAPACITY-ROUTING-GLUE)
- **Wire** the provision-time read: `shard_utilization` (live snapshot) → build the
  `ShardCapacity` set → `CapacityPlanner::pick_shard` (already correct). Today the
  planner takes the snapshot as a param with nothing supplying it.
- **Design correction (drops the S13 "add a DB CHECK" idea):** over-subscription is
  enforced at **provision time** by `pick_shard` (refuses when every shard ≥ full).
  A `current_db_count <= capacity_max_dbs` CHECK on `shard_utilization` is WRONG —
  that table is a metrics snapshot that must be able to *observe* a transient
  over-subscription, not forbid recording it. So: no snapshot CHECK; the planner read
  is the enforcement.
- **Bite:** feed the planner a snapshot where every shard is full → `NoShardCapacity`
  (rejected); with the live-read bypassed (stale all-empty snapshot) it would
  mis-place → caught.

### W1.2 — Migrate CLI live-wiring (closes D-MIGRATE-CLI-LIVE-WIRING)
- Bind `services/migration-orchestrator/cmd/migrate` `cmdApply` (today a no-op stub)
  to real collaborators — all **Go, in-process** (no bridge needed):
  - a **DSN resolver** (NEW): `reality_id` → (`db_host`,`db_name`) from
    `reality_registry` → per-reality DSN.
  - a real **Applier** (pgx) running the migration SQL on each per-reality DB.
  - **Auditor + StateWriter** bound to `reality_migration_audit` +
    `instance_schema_migrations` via `MetaWrite` (audit same-TX).
  - breaking → `canary.Orchestrator`; non-breaking → `runner.Runner` (cap 10).
- This is the S13 `canary-drill` pattern, productionized.
- **Bite:** a breaking migration that fails on the canary aborts fan-out (reuse the
  S13 Phase-1 abort bite, now through the real CLI).

### W1.3 — Closure-drain orchestrator (closes D-S13-CLOSURE-DRAIN)
- A Go orchestrator for R09 safe closure: on `active→pending_close`, **drain** the
  reality's outbox before allowing `→frozen` — gate `→frozen` on
  `SELECT count(*) FROM events_outbox WHERE reality_id=$1 AND published=false = 0`
  (the publisher high-water). Abort (`pending_close→active`) is allowed any time and
  restores. All transitions via `AttemptStateTransition` (CAS + I9 audit).
- **Bite:** un-drained outbox (unpublished rows) + force `→frozen` with the drain gate
  disabled → stranded undelivered events → caught.

### W1.4 — Relocate/closure write-freeze (closes D-S13-RELOCATE-FREEZE)
- A guard in the **Rust kernel append path** (`crates/dp-kernel/src/event_store_pg.rs`):
  reject an event append when the reality's lifecycle status ∈
  {`migrating`,`pending_close`,`frozen`,`archived`} — the relocation copy/flip
  (Inc-4) and the closure drain (W1.3) both rely on the source being quiesced.
- **Status source:** `meta_rs::MetaRead` with a short-TTL cache (status changes are
  rare; invalidate on a transition signal); a per-append uncached read would add RTT.
- **Bite:** an append during `migrating` succeeds with the guard off → the relocation
  flip would lose it → caught (hardens Inc-4's D-S13-RELOCATE-FREEZE assumption).

### W1.5 — Provisioner + Rust→Go meta-write bridge (closes D-S4-I4-PROVISIONER core)
- **The bridge (centerpiece):** a new **internal HTTP API on meta-worker** (it already
  owns the meta DB pool + `contracts/meta`; least new surface — add an HTTP listener
  alongside its consumer loop):
  - `POST /internal/meta/write` → `MetaWrite(intent)` ; `POST /internal/meta/transition`
    → `AttemptStateTransition(req)`. Both return the audit id / result.
  - **Auth:** a service token (env secret, fail-closed); every call audited in
    `service_to_service_audit`. Internal only (not via gateway).
  - A **Rust client** in world-service implementing the `Effects` trait's
    `register_pending` + `transition_to` against this endpoint.
- **Provisioner real Effects (shard-side, Rust/sqlx):** `create_database` on the
  picked shard + per-service **role + `REVOKE CONNECT`** privilege bootstrap (the I4
  isolation model). `apply_initial_migration` runs the per-reality skeleton.
- **Scope split:** `register_with_pgbouncer` / `register_prometheus_scrape` /
  `register_backup_policy` stay **go-live** (those subsystems aren't in dev) — the
  provisioner calls them through no-op-able Effects so the core flow runs now.
- Makes the `db-per-service-isolation` conformance case a REAL probe.
- **Bite:** a second service connecting to another reality's DB despite `REVOKE` →
  rejected (proves the isolation); and register_pending via the bridge lands a
  `meta_write_audit` row (I8) — raw bypass → no audit (non-vacuous, reuses the D2 idea).

## Out of scope (→ go-live / later)
- Provisioner pgbouncer/prometheus/backup registration (go-live infra).
- HA-meta split-brain, multi-host, Bencher CI, paid Antithesis, LLM-at-scale (triage
  go-live/post-go-live buckets).

## Acceptance
Each item: production code wired + a live drill with a non-vacuity bite + a
conformance case (where it's a runtime check) + CI. The bridge ships with
service-token auth + `service_to_service_audit`. SESSION updated; the 5 deferred rows
closed; the cleardown plan's Wave-1 box checked.
