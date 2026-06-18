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
  correct). NO snapshot CHECK (metrics must observe over-subscription).
- **Pin the live states (review #2):** the per-shard count MUST include in-flight
  occupancy — `provisioning`, `seeding`, `active`, `migrating`, `pending_close`
  (everything holding a DB on the shard); exclude only `archived`/`dropped` (DB gone).
- **Provision-race / TOCTOU (review #2):** `count → pick → register` is NOT atomic —
  two concurrent provisions read the same count, pick the same least-full shard, both
  register → over by 1. Serialize it: take a **per-shard `pg_advisory_xact_lock`**
  around `count→register` (so the second provision sees the first's row), OR
  register-then-recount-and-roll-back-if-over. Pick the advisory lock (simpler, no
  rollback). 
- Unit + live drill (seed N realities → placement picks least-full, refuses all-full;
  + a CONCURRENT-provision drill: K parallel provisions onto a shard with M<K free
  slots → exactly M succeed, K−M re-routed/refused, never over). **Bite:** the
  concurrent provision with the advisory lock removed → over-subscription the lock
  prevents (mirrors the S13 lifecycle-CAS bite, for capacity).

## Increment 2 — W1.2 Migrate CLI live-wiring `[BE/Go]`
- NEW `dsnResolver` (reality_id → db_host/db_name → DSN from reality_registry).
- Real `pgxApplier` (run migration SQL on the per-reality DB) + Auditor/StateWriter
  bound to `reality_migration_audit` + `instance_schema_migrations` via MetaWrite.
- `cmdApply`: breaking → canary, else → runner (cap 10). Live drill = the S13
  l1-migration smoke through the REAL CLI. **Bite:** breaking migration fails on the
  canary → fan-out aborts (Phase-1 bite, live via the CLI).
- **Cross-DB non-atomicity (review #7):** the Applier runs SQL on the PER-REALITY DB
  while the audit/state writes hit the META DB — different databases, so a crash
  between them can desync `instance_schema_migrations` from the reality's real schema.
  Inherent; recovery = the runner's **idempotent re-run** (re-apply + re-mark). The
  drill exercises a re-run after an injected mid-step crash.

## Increment 3 — W1.3 Closure-drain orchestrator `[BE/Go]`
- A Go closure orchestrator: `active→pending_close` (CAS) → **freeze-settle** (W1.4:
  wait until new appends are rejected so the outbox can actually reach 0) → poll the
  reality's `events_outbox` unpublished count to 0 (publisher high-water) → `→frozen`
  (CAS); `pending_close→active` aborts/restores. All via AttemptStateTransition.
- **Drain timeout (review #6):** the poll is BOUNDED — if the publisher is down the
  outbox never drains; on timeout the orchestrator **aborts (`pending_close→active`) +
  alerts**, it does NOT hang or force `→frozen`.
- Live drill on the rig (seed unpublished outbox → drain via a stub publisher mark →
  →frozen only after 0; + a timeout case: no publisher → abort, not frozen). **Bite:**
  force `→frozen` with the drain gate disabled while outbox unpublished > 0 → stranded
  events caught.

## Increment 4 — W1.4 Relocate/closure write-freeze `[BE/Rust]`
- Guard in `crates/dp-kernel/src/event_store_pg.rs` append: reject when reality status
  ∈ {migrating, pending_close, frozen, archived}. Status via `meta_rs::MetaRead` +
  short-TTL cache. Returns a typed `RealityFrozen` error.
- **Freeze-settle (review #1 — the crux).** The transition that freezes a reality
  (`→migrating`/`→pending_close`) is driven by an EXTERNAL actor (the relocation /
  closure orchestrator), NOT the reality's own command processor — so the kernel's
  status cache is NOT synchronously invalidated by it; only the TTL catches up. That
  leaves a window where a gameplay append still sees "active" and lands AFTER the flip
  → the exact loss this item targets. Close it ONE of two ways (pick at build, measure
  R3): (a) the relocation/closure procedure, after CAS→migrating, **waits out the
  cache TTL ("settle") before copy/final-drain** so any in-flight write has either
  landed-and-will-be-copied or is now rejected; or (b) the freeze check does an
  **uncached status read** on the append path (simplest-correct; cost measured via the
  S14 D1 harness, accept if negligible). Prefer (b) unless the read cost is real.
- Live drill: append to `active` (ok) vs `migrating` (rejected); recovery after
  `→active`. **Bite (must exercise the window):** flip `→migrating` then append DURING
  the settle window with the guard off → the write lands → the relocation flip would
  lose it; with the guard on → rejected. (A naive "append while migrating" that skips
  the post-flip window would miss the real race.)

## Increment 5 — W1.5 Provisioner + Rust→Go meta-write bridge `[FS]` (the big one)
- **5a Bridge (Go) — SCOPED, least-privilege (self-review, R1):** add an internal HTTP
  listener to `cmd/meta-worker` (alongside its consumer) exposing **narrow** operations,
  NOT a raw arbitrary-MetaWrite passthrough: `POST /internal/provisioner/register-reality`
  (server builds the reality_registry INSERT intent from a narrow payload) +
  `POST /internal/provisioner/transition` (→ AttemptStateTransition for reality only).
  The server constructs the intent → the blast radius is the provisioner's own tables,
  not any allowlisted table.
  - **Reuse the canonical `meta.Config` + real actor (review #4):** the server-built
    intent goes through meta-worker's EXISTING `meta.Config` (allowlist + scrubber +
    clock + uuidgen) — never a fresh/permissive one — and the audit `Actor` is the
    real caller (`ActorType=service`, the world-service identity from the token), not a
    generic "bridge".
  - **Idempotent (review #3):** a retried `register-reality` (network blip) must treat
    a `reality_id` PK conflict as idempotent SUCCESS (not a 500); `transition` returns
    `ErrConcurrentStateTransition` on a stale FromState and the Rust client surfaces it
    (no blind retry).
  - **Auth + real internal boundary (review #5):** service token (env secret,
    fail-closed: no/!match token → 401) + a `service_to_service_audit` row per call;
    the listener **binds to the internal interface / is network-policy-restricted**
    (enforced, not just documented) — never via the gateway. A shared token grants
    register/transition on any reality, acceptable for the V1 single caller because the
    boundary is real + every call is audited.
  - Unit (handler) + Rust-side client unit (mock server) + a cross-lang live smoke
    (token ok/denied; write lands meta_write_audit; retry is idempotent). **Bite:**
    missing/wrong token → 401 (fail-closed); a raw bypass write → no meta_write_audit
    (I8 non-vacuous).
- **5b Rust client (world-service):** implement `Effects::register_pending` +
  `transition_to` against the bridge (a small HTTP client — confirm the crate at
  build: reqwest or the existing http client).
- **Dual-role shutdown (review #8):** meta-worker now runs its consumer loop AND the
  HTTP listener — wire graceful shutdown of BOTH (signal → stop accepting + drain
  in-flight on each) so it stays a clean citizen.
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
- **Cross-lang infra (review #8):** the provision-isolation drill needs meta-worker
  (HTTP bridge) + a shard + the world-service Rust client all up — heavier than the
  single-language s12/l1/s14 drills → **nightly-only**; the per-PR job stays
  build/vet + `bash -n`.

## Risks
- **R1 bridge auth surface.** A new internal endpoint that performs meta writes is
  powerful — even SCOPED to provisioner ops (review #5) it MUST be fail-closed (no
  token → deny), bind to the internal interface (network-policy-restricted, never the
  gateway), and audited (service_to_service_audit). `/review-impl` this increment hard
  (auth + injection: the server-built intent's table/op must stay
  allowlist-checked by MetaWrite, which it already is).
- **R2 cross-language testing.** The Rust→Go bridge needs both sides up; the live
  drill boots meta-worker (HTTP) + a shard. Keep a Go-side unit test for the handler
  and a Rust-side unit test for the client (mock server), plus the cross-lang live
  drill. Don't rely on mock-only (the session-59 lesson).
- **R3 write-freeze hot-path cost.** A per-append status read would add RTT to the
  spine's hottest path. The short-TTL cache mitigates; measure the overhead (reuse the
  S14 D1 harness) and assert it's negligible (cache hit) — else reconsider (e.g. push
  the freeze flag into the append's existing reality lookup).
- **R4 freeze cache staleness (CORRECTED — review #1).** Earlier I claimed I6 makes
  the per-reality cache coherent; that is WRONG — I6 serializes the reality's own
  command processor (gameplay appends), but the freeze-triggering transition is
  EXTERNAL (relocation/closure orchestrator), so it does NOT invalidate the
  processor's cache. The honest fix is W1.4's freeze-settle: either an uncached status
  read on the append (preferred, if cheap) or the orchestrator waits the TTL after the
  flip before proceeding. Do NOT rely on I6 coherence here.
- **R5 migrate CLI blast radius.** Live migration on real per-reality DBs is
  destructive; keep `--dry-run` honest + the canary gate mandatory for breaking
  migrations; the drill uses throwaway per-reality DBs only.
- **R6 provisioner partial-failure.** The 11-step flow is idempotent by design;
  the live drill must exercise a re-run (crash after create_database) → resumes, not
  double-creates (the orphan_scanner concern stays go-live).
