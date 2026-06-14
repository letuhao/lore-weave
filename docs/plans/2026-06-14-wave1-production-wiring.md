# Wave 1 — Production wiring — implementation plan

Spec: `docs/specs/2026-06-14-wave1-production-wiring.md`. Size **XL**, 6 increments,
batch cadence (autonomous → one POST-REVIEW → push-ask). `/review-impl` plan first,
then impl. Load-bearing production code (write path, meta, provisioner) → production-
shaped, `/review-impl` before each commit.

## Guiding constraints
- **Honor I8** (meta writes audited same-TX via Go MetaWrite), the **language rule**
  (Rust world/kernel, Go meta/orchestrator), and keep the bridge **internal** (service
  token + `service_to_service_audit`, not via the gateway).
- **Every item ships a non-vacuity bite + a live drill** (reuse the S13/S14 rig +
  throwaway-container patterns). Where it's a runtime check → conformance case + CI.
- **Locate-first** the exact touch points before editing (the S13 discipline) —
  several boundaries (Rust HTTP client choice, freeze-cache invalidation hook, DSN
  resolver, meta-worker HTTP listener) are confirmed at build, not assumed.

## Increment order (dependency-aware) — reordered W1.4 before W1.3 (self-review)
W1.1 → W1.2 → **W1.4 (freeze)** → **W1.3 (closure)** → W1.5(bridge+provisioner) →
Inc-6. W1.3's drain only TERMINATES if new writes are frozen (else the outbox never
empties) → W1.4 lands first. W1.5 provisioner depends on the bridge → bridge first
within Inc-5.

## Increment 1 — W1.1 Capacity routing glue `[BE/Rust]`
- **Live count from `reality_registry`, NOT the `shard_utilization` snapshot
  (self-review):** `shard_utilization` is written by an unbuilt metrics job, so reading
  it would depend on missing infra (and return empty → refuse-all). Instead derive the
  live snapshot from what's always present: `SELECT db_host, count(*) FROM
  reality_registry WHERE status IN (<live states>) GROUP BY db_host` for `used`, and
  the per-shard `capacity_max_dbs` from a **shard-capacity config** (a seeded config /
  the registered shard list) for `total`. `shard_utilization` stays the observability
  snapshot only. (Locate-first the cap-config source at build.)
- world-service `live_snapshot()` → `Vec<ShardCapacity>` → `pick_shard` (already
  correct). NO snapshot CHECK (metrics must observe over-subscription). Unit + live
  drill (seed N realities on a shard → assert placement picks least-full, refuses
  all-full). **Bite:** a stale all-empty count → mis-place that the live read prevents.

## Increment 2 — W1.2 Migrate CLI live-wiring `[BE/Go]`
- NEW `dsnResolver` (reality_id → db_host/db_name → DSN from reality_registry).
- Real `pgxApplier` (run migration SQL on the per-reality DB) + Auditor/StateWriter
  bound to `reality_migration_audit` + `instance_schema_migrations` via MetaWrite.
- `cmdApply`: breaking → canary, else → runner (cap 10). Live drill = the S13
  l1-migration smoke through the REAL CLI. **Bite:** breaking migration fails on the
  canary → fan-out aborts (Phase-1 bite, live via the CLI).

## Increment 3 — W1.3 Closure-drain orchestrator `[BE/Go]`
- A Go closure orchestrator: `active→pending_close` (CAS) → poll the reality's
  `events_outbox` unpublished count to 0 (publisher high-water) → `→frozen` (CAS);
  `pending_close→active` aborts/restores. All via AttemptStateTransition.
- Live drill on the rig (seed unpublished outbox → drain via a stub publisher mark →
  →frozen only after 0). **Bite:** force `→frozen` with the drain gate disabled while
  outbox unpublished > 0 → stranded events caught.

## Increment 4 — W1.4 Relocate/closure write-freeze `[BE/Rust]`
- Guard in `crates/dp-kernel/src/event_store_pg.rs` append: reject when reality status
  ∈ {migrating, pending_close, frozen, archived}. Status via `meta_rs::MetaRead` +
  short-TTL cache; invalidate on transition. Returns a typed `RealityFrozen` error.
- Live drill: append to an `active` reality (ok) vs a `migrating` one (rejected);
  recovery after `→active`. **Bite:** guard off → append during `migrating` lands →
  the relocation flip would lose it.

## Increment 5 — W1.5 Provisioner + Rust→Go meta-write bridge `[FS]` (the big one)
- **5a Bridge (Go) — SCOPED, least-privilege (self-review, R1):** add an internal HTTP
  listener to `cmd/meta-worker` (alongside its consumer) exposing **narrow** operations,
  NOT a raw arbitrary-MetaWrite passthrough: `POST /internal/provisioner/register-reality`
  (server builds the reality_registry INSERT intent from a narrow payload) +
  `POST /internal/provisioner/transition` (→ AttemptStateTransition for reality only).
  The server constructs the intent → the blast radius is the provisioner's own tables,
  not any allowlisted table. Service-token auth (env secret, fail-closed) +
  `service_to_service_audit` per call; internal bind only (never the gateway). Unit +
  live smoke (token ok/denied; write lands meta_write_audit). **Bite:** missing/wrong
  token → 401 (fail-closed); a raw bypass write → no meta_write_audit (I8 non-vacuous).
- **5b Rust client (world-service):** implement `Effects::register_pending` +
  `transition_to` against the bridge (a small HTTP client — confirm the crate at
  build: reqwest or the existing http client).
- **5c Provisioner shard-side Effects (Rust/sqlx):** `create_database` on the picked
  shard + per-service role + `REVOKE CONNECT` (I4 isolation) + apply the per-reality
  skeleton migration. pgbouncer/prometheus/backup Effects stay no-op (go-live).
- **Live drill:** provision a reality end-to-end on the rig (pick shard → create DB →
  roles → register_pending+transitions via the bridge) → registry row + meta_write_audit
  present + the new DB exists + a foreign service is REVOKE-blocked from it. Makes
  `db-per-service-isolation` a real probe. **Bite:** a foreign connection to the
  reality DB despite REVOKE → must be rejected.

## Increment 6 — conformance + CI + SESSION `[FS]`
- Conformance cases for the live drills (capacity-glue, migrate-CLI, closure-drain,
  write-freeze, provision-isolation) `requires:`-gated like s12/l1/s14; CI build/vet
  + nightly sweep. SESSION + memory + prune the stale cleared Deferred rows. **Close
  D-S13-CAPACITY-ROUTING-GLUE, D-MIGRATE-CLI-LIVE-WIRING, D-S13-CLOSURE-DRAIN,
  D-S13-RELOCATE-FREEZE, D-S4-I4-PROVISIONER (core).** Check the cleardown Wave-1 box.

## Risks
- **R1 bridge auth surface.** A new internal endpoint that performs ARBITRARY meta
  writes is powerful — it MUST be fail-closed (no token → deny), internal-only (bind
  to the internal network, never the gateway), and audited (service_to_service_audit).
  `/review-impl` this increment hard (auth + injection: the intent table/op must stay
  allowlist-checked by MetaWrite, which it already is).
- **R2 cross-language testing.** The Rust→Go bridge needs both sides up; the live
  drill boots meta-worker (HTTP) + a shard. Keep a Go-side unit test for the handler
  and a Rust-side unit test for the client (mock server), plus the cross-lang live
  drill. Don't rely on mock-only (the session-59 lesson).
- **R3 write-freeze hot-path cost.** A per-append status read would add RTT to the
  spine's hottest path. The short-TTL cache mitigates; measure the overhead (reuse the
  S14 D1 harness) and assert it's negligible (cache hit) — else reconsider (e.g. push
  the freeze flag into the append's existing reality lookup).
- **R4 freeze cache staleness.** A stale "active" cache could let a write through just
  after `→migrating`. **I6 simplifies this (self-review):** appends for a reality go
  through ONE command processor (one-per-session/reality), so a per-reality cache on
  that processor is the single authority for that reality — invalidate it on the
  transition and it's coherent (no distributed cache-invalidation needed in V1). Bound
  the TTL small as a backstop; the relocation/closure procedures CAS the status first,
  then act, so a synchronous invalidate on the transition path closes the window.
  Document the residual TTL window.
- **R5 migrate CLI blast radius.** Live migration on real per-reality DBs is
  destructive; keep `--dry-run` honest + the canary gate mandatory for breaking
  migrations; the drill uses throwaway per-reality DBs only.
- **R6 provisioner partial-failure.** The 11-step flow is idempotent by design;
  the live drill must exercise a re-run (crash after create_database) → resumes, not
  double-creates (the orphan_scanner concern stays go-live).
