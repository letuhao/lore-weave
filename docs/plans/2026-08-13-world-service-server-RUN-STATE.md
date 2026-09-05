# RUN-STATE — world-service: turn the scaffold into a process that serves

**Reconciles:** Foundation Invariants **I1–I19** · `contracts/service_contracts.md` · `contracts/.spectral.yaml` · `contracts/service_acl/matrix.yaml` · `contracts/language-rule.yaml` · `scripts/gate-wiring-gate.py` — the audit is §1. Two of the four claims the goal asked me to settle were **wrong as stated**, and both errors were mine rather than the tree's: `world-service` **already serves HTTP** (an axum router with `/healthz` `/readyz` `/metrics`, shipped for the embedding worker) and the contract home **already exists** at `contracts/api/world/`, declaring itself *"Cycle 0 — contract home established, no specs frozen yet."* The genuinely new finding is §1.5: this capability **already has a production caller**, and it reaches the code by `exec`.

---

## 0 · HOW TO WORK

**The binding execution contract is [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)** — adopted verbatim, not copied: the execution invariant, the source-of-truth rule, the six-step bite sequence, the hazards, the blocker rule, the continuation check, the stop-condition list, and the list of things that are NOT stop conditions.

The four hazards that have each cost time on the last three tracks:

* **Run `--run-all` DETACHED and read its REAL exit code** (`BDR-89`, `BDR-90`). The task notification reports the *outer shell's* status; it said `0` for a sweep that exited `1`, twice. A foreground call that takes SIGTERM at the 10-minute ceiling leaves a bite harness's mutation — typically a deleted assertion — sitting in the tree.
* **Byte-level I/O for anything a shell executes, and for documents** (`BDR-86`). `Path.write_text` on Windows rewrote a shell gate to CRLF and separately rewrote all 10,969 lines of `SESSION_HANDOFF.md`, which handed the staged citation gate the whole archive to scan.
* **Never restore a bite with `git checkout`** (`TLD-10`) — it restores from the **index** and deletes unstaged work. Save the bytes and copy them back.
* **A bite harness is itself an unverified check** (`TLD-11`). It has failed three times in one session, always in the same direction: calling a working arm dead. `^error(\[|:)` matched cargo's ordinary `error: test failed` line and scored 0/3 against three arms that were fine.

**Not stop conditions** (§0.6d's list, restated because this is where runs end early): a commit · a green sweep · a POST-REVIEW · a turn boundary · uncommitted work piling up · wanting a decision this file can seal.

---

## 1 · PHASE 0 — AUDIT-EXISTING

The goal named four things to settle. Each is answered with a command, and the grade is stated before the finding.

### 1.1 · Claim 1 — the `println!` scaffold. **CONFIRMED, and the discharge is stronger than argued.**

`services/world-service/src/main.rs` is 22 lines. It prints a module list and exits. Its own header:

> *"The HTTP server scaffold (and the GEO_001 aggregate) still awaits the DP-kernel (cycle 17)."*

The goal argued the blocker is discharged because we have spent three days building DP-kernel. The stronger form is that it is discharged **in the dependency graph**, not in an argument — `services/world-service/Cargo.toml` already carries:

```
dp        = { path = "../../crates/dp" }
dp-kernel = { path = "../../crates/dp-kernel" }
```

So the thing the comment waits for is already a compile-time dependency of the crate whose comment it is. The scaffold is not blocked; it is **stale**.

### 1.2 · Claim 2 — what already serves HTTP. **CONFIRMED for `service-http`, and I MISSED A THIRD ANSWER inside the crate itself.**

| what | where | shape |
|---|---|---|
| the shared skeleton | `crates/service-http/src/lib.rs` | `serve(addr, router)` + `health::routes::<S>()` + `ProblemDetails` (RFC 7807) + `require_user` / `require_internal` + `trace` + `metrics` + `config::require_env` + `db::init` |
| the shipped consumer | `services/roleplay-service/src/main.rs` | 20 lines: `init_tracing` → `Config::from_env` → `db::init` → `build_router` → `serve` |
| **already in world-service** | `services/world-service/src/embedding_queue/live/server.rs` | an **axum `Router`** with `/healthz` `/readyz` `/metrics`, `AppState { metrics, ready }`, served by the `embedding-worker` binary |

`axum` is **already a dependency** of `world-service`. This is not a service learning to speak HTTP; it is a service with one HTTP surface gaining a second.

And `service-http`'s own module doc names this track before it happened:

> *"roleplay-service is the first consumer (built on it day one). **tilemap/world migrate opportunistically when next touched** — not a forced refactor."*

We are touching world. This track **is** that migration.

### 1.3 · Claim 3 — the contract home. **FALSIFIED AS STATED.**

`contracts/api/world-service/` does not exist — but that is the wrong directory name, and checking the wrong name is how a Phase 0 question 1 fails. `contracts/api/world/` **exists**, and is the declared home:

> *"Frozen OpenAPI contracts for `services/world-service`. **Status: Cycle 0 — contract home established, no specs frozen yet.**"*

It carries a table of four planned specs — `geometry.v1.yaml`, `political.v1.yaml`, `settlement.v1.yaml`, `route.v1.yaml`. **None of them is provisioning.** So the finding is not "no contract home" but the sharper one: the home exists, is deliberately empty, and the spec this track owes **is not in its plan**. That table gets a row rather than being quietly bypassed.

`contracts/.spectral.yaml` is the index's OpenAPI lint ruleset and it is **⚠️ NOT WIRED** (DEFERRED 078 — the ruleset is real, the CI job is not). So freezing a YAML buys **no machine check at all** by itself. That is what makes `WS4` a required row rather than a nicety: the enforcement has to be written, not inherited.

### 1.4 · Claim 4 — compose. **CONFIRMED.**

```
grep -n "world" infra/docker-compose.yml
  → 125: (a comment about the I8 write rule)
  → 144: dockerfile: services/world-service/Dockerfile.orphan-scanner
```

No `world-service:` service block. And `ls services/world-service/Dockerfile*` returns **only** `Dockerfile.orphan-scanner` — there is no general image for the crate. This matches the reality-layer board's own measured row (*"game-tier services in compose: `game-server` only; `world-service`, `commit-service` absent"*), which had it right while I had it wrong.

### 1.5 · **THE FINDING the goal did not ask for — this capability already has a production caller, and it arrives by `exec`.**

`services/admin-cli/internal/commands/provision_reality.go` declares a Go interface:

```go
// ProvisionInvoker runs the provision worker. The production implementation
// (SubprocessProvisionInvoker) execs the world-service `provision` binary;
```

So `reality provision` — a live, dispatched admin command — already reaches this code. The seam is a **subprocess**, in the same shape `admin-cli` uses for `rebuilder`: secrets by env, identifiers by flag, one JSON object on stdout, exit code is the verdict.

This reframes the track. An HTTP route here is **not a new capability**; it is a **second invoker shape** for one that already ships. Which makes the orphan question — *who calls it?* — a thing to settle **before** writing it, because a route whose only caller is its own test is the mirror image of the producerless model `§0.6c` forbids. Sealed as `WS-F3`.

### 1.6 · The call shape, measured — and it is a trap

`Provisioner::provision_reality` is **synchronous**:

```rust
pub fn provision_reality<E: Effects>(&self, req: ProvisionRequest,
    snapshot: &[ShardCapacity], effects: &mut E) -> Result<ProvisionReport, ProvisionerError>
```

Every one of the 11 `Effects` methods is sync, and `LiveEffects` *"holds a runtime handle to block on the async bridge + shard I/O from the sync trait methods."* Its constructor doc is explicit: *"capture with `Handle::current()` from async context **before spawn_blocking**."*

An axum handler is async. Calling this directly would block the reactor thread, and `Handle::block_on` **panics** when called from a runtime worker thread. So the handler must `spawn_blocking`, and this is the kind of defect that is invisible until the second concurrent request. Sealed as `WS-F5`.

### 1.7 · Marker symbols, measured

`build_router` in world-service **0** · `AppState` in world-service **1** (the embedding worker's, a different struct in a different module) · any `POST` route in world-service **0** · a gateway route naming world-service **0** (`grep -rn "world-service" services/api-gateway-bff/src` → empty). The provisioning HTTP surface is genuinely greenfield; the provisioning *capability* is not.

### 1.8 · DP-R2 tier table

| Access | Aggregate / store | Tier | Why |
|---|---|---|---|
| Read live shard capacity to pick a placement | `shard_utilization` + `reality_registry` (meta Postgres) | **T3** | `capacity_glue::live_snapshot`; authoritative, no cache. The pick→register critical section holds a per-shard advisory lock. |
| Register the pending reality | `reality_registry` (meta Postgres) | **T3** | Written through the Go bridge (I8: Rust cannot write meta directly). |
| `CREATE DATABASE` + apply migrations | the shard's maintenance DB, then the new per-reality DB | **T3** | Durable, one-shot, idempotent per `Effects`. |
| Serve `/livez` `/readyz` | process-local + `PgPool` liveness | **T0** | No aggregate. `service-http::health` already owns this shape. |
| The HTTP request/response itself | *none* | — | Stateless. No new table, therefore **no new scope key** — the tenancy tier is inherited from `reality_registry.owner_user_id`, which `W6` already shipped, and this route does not widen who may write it (`WS-F4`). |

---

## 2 · SEALED FORKS

**`WS-F1` · The route wraps the EXISTING lib path. No reimplementation.**
`provision.rs` is a thin CLI over `world_service::provisioner::{Provisioner, ProvisionRequest}` + `provisioner_live::{LiveEffects, BridgeClient}` + `capacity_glue::{live_snapshot, place_reality}`. The handler calls the same four. The repo has a recorded scar here: `1b14-01` was found because a unit test was green against `FakeEffects::apply_migrations` (a `HashSet::insert`) while the live code was not idempotent — *"a second re-implementation, this time in a test, would repeat exactly that."* A second re-implementation, this time in a handler, would too. **Reversal trigger:** none. This is not a preference.

**`WS-F2` · `main.rs` becomes the server. The seven worker binaries stay exactly as they are.**
`orphan_scanner`, `embedding-worker`, `rebuilder`, `provision-drill`, `provision`, `freeze-drill`, `capacity-place`, `replay-aggregate` are workers and drills with their own entry points and their own operators. Folding them into a server would be a rewrite of eight things to ship one. **Reversal trigger:** none in scope.

**`WS-F3` · The admin-cli subprocess seam STAYS. This track does not migrate it — and the route is therefore NOT orphaned, because its consumer is named and mechanised.**
Swapping `SubprocessProvisionInvoker` for an HTTP invoker under this track would replace the *only production path that creates realities* with an untested one, at a risk boundary this track has no mandate to cross. But leaving it means answering §1.5's question honestly. The route's consumers, in order of arrival: (1) the live smoke in `WS5`, which is a real client over a real socket; (2) **`api-gateway-bff`**, which is where player-facing reality creation must arrive by `I1`, and which has no world route today; (3) `admin-cli`, if and when the subprocess seam is retired. Consumer (1) exists at close. Consumers (2) and (3) get a **tracked row with a mechanism** (`WS-GATEWAY-CONSUMER`, §4), not a prose promise — the distinction 2026-07-29 measured at 9-of-19 deferrals being prose only. **Reversal trigger:** the gateway growing a world route, which promotes (2) from open to done.

**`WS-F4` · The surface is INTERNAL. `require_internal` (X-Internal-Token), not `require_user`.**
`I1`: all external traffic through `api-gateway-bff`. World-service's HTTP is a service-to-service surface, and `service-http::auth` already ships exactly this primitive; `roleplay-service` and `tilemap-service` both use it. This also means **no new tenancy tier** — the caller is a service, the owner is whatever `owner_user_id` the request carries into `reality_registry`, and `W6` already governs that column. **Reversal trigger:** a decision to expose reality creation to end users directly, which would need a PO decision and the gateway anyway.

**`WS-F5` · The provisioning handler runs under `spawn_blocking`.**
Forced by §1.6, not chosen: the effects chain is sync and blocks on a tokio `Handle`, which panics from a runtime worker thread. The handler captures `Handle::current()` first, moves it into the blocking task, and awaits the join. **Reversal trigger:** `Effects` becoming an async trait, which is a larger refactor with its own plan.

**`WS-F6` · The contract is frozen BEFORE the route, and its enforcement is written rather than inherited.**
Contract-first is a repo rule; `contracts/.spectral.yaml` being unwired means the rule has no teeth here unless this track supplies them. The mechanism mirrors glossary-service's `TestOpenAPIRouteConformance` (walk the real router, parse the YAML, red on undocumented-or-phantom), rewritten in Rust because the router is Rust. **Reversal trigger:** spectral being wired, which would still not check router-vs-spec — it checks the spec against itself.

---

## 3 · THE BOARD

| # | row | done = |
|---|---|---|
| ~~`WS0`~~ ✅ | this file + the Phase 0 audit | `phase0-reconcile-gate.py` passes on it, output pasted |
| ~~`WS1`~~ ✅ | the OpenAPI contract, frozen first | `contracts/api/world/provisioning.v1.yaml` exists, its README table names it, and it documents exactly the routes `WS2`+`WS3` will serve |
| ~~`WS2`~~ ✅ | `main.rs` boots a real server | the binary binds, `/livez` and `/readyz` answer over a socket, `/metrics` encodes; config is fail-closed (a missing secret is a refusal, not a default) |
| ~~`WS3`~~ ✅ | the provisioning route, over the existing lib path | `POST` handler calls `Provisioner::provision_reality` through `LiveEffects` under `spawn_blocking`, returns the `ProvisionReport`; errors are `ProblemDetails` |
| ~~`WS4`~~ ✅ | route conformance, bitten | an undocumented `/v1` route reds the check naming BOTH sides; a documented-but-unrouted path reds too; both restored byte-exact |
| ~~`WS5`~~ ✅ | **the live smoke** — a running process, a real request, a real database | the process is started, a request is sent to it, a reality is provisioned **through the route**, and `SELECT datname FROM pg_database` shows the per-reality DB. Stated explicitly: live or drill |
| ~~`WS6`~~ ✅ | verify | `cargo test --workspace` and a **detached** `--run-all` sweep, both with REAL exit codes pasted |

### `WS0` — evidence

```
phase0-reconcile-gate: SELFTEST PASS — 11 case(s); it flags a missing line, a bare `none` and a
  phantom row, and does NOT flag a real citation or a reasoned `none` (non-vacuous in both directions)
phase0-reconcile-gate: OK — 10 spec(s) dated >= 2026-08-06 checked against 128 standards-index row(s)
RC=0
```

Nine specs before this file, ten after — so the gate is reading it, not skipping it.

### `WS1` — evidence

`contracts/api/world/provisioning.v1.yaml`, frozen before any handler existed. The README's Cycle-0
table gained a row rather than the spec being served without one: provisioning is an operational
surface, not a geography feature, so it was in none of the four planned specs. The README now also
states where its enforcement comes from, since `.spectral.yaml` supplies none.

### `WS2` + `WS3` — evidence

`src/server/{config,state,routes,handlers}.rs` + a rewritten `main.rs`, on `crates/service-http`.
`src/provision_flow.rs` extracts the two hard paths so the handler and the `provision` worker share
them (`WS-F1`). **151 lib tests pass, 0 fail.** The binary builds and the whole crate is green.

Two things the code does that are worth naming, because both were nearly wrong:

* The handler runs the effects chain under `spawn_blocking` with a `Handle` captured first. The
  chain is synchronous and blocks on that handle internally; calling it inline would block the
  reactor, and `Handle::block_on` **panics** from a runtime worker thread. `run_steps_blocking` is
  the single place that knows this, so no caller has to.
* `ProvisionRequest::validate` is now called at the boundary **before** the flow. `ProvisionerError`
  cannot tell "your input is bad" from "our machinery failed" — `InvalidState` carries both — so a
  handler that only mapped the error would answer 500 for a caller's typo.

### `WS4` — evidence: 5/5 green, **6/6 bitten**, every restore byte-exact

```
[BITTEN]   a route mounted in build_router but not in ROUTES
[BITTEN]   a table entry with no documented operation
[BITTEN]   a documented path this service does not serve
[BITTEN]   the contract dropping its security block
[BITTEN]   the reach floor when the tree walk stops recursing
[BITTEN]   the worker-router exclusion pointing at a file that is gone
bitten: 6/6
```

The first is the one that matters. A table checked against a document is two hand-maintained lists
agreeing with each other — a route added straight to `build_router` appears in neither, so **both**
directions pass and the route is invisible. The walk over the source tree is what makes the table a
witness instead of a restatement, and it walks the tree rather than an enumerated file list, because
an enumerated list is default-uncovered (`NV-3`) the day someone adds a file.

The fifth proves that walk is live: stop it recursing and the membership check still passes — against
almost nothing. `0 < 15 < measured`.

### `WS5` — evidence: **a LIVE test, not a drill**, 0 failures, `SMOKE_RC=0`

A real process (`target/debug/world-service`, pid logged), a real socket, and every claim about the
database asked of Postgres rather than read back out of the response.

```
=== 1. fail-closed: the binary REFUSES to start with no credentials ===
world-service: missing required env: LOREWEAVE_INTERNAL_TOKEN, PROVISION_META_DSN,
  PROVISION_SHARD_ADMIN_DSN, PROVISION_BRIDGE_URL, PROVISION_BRIDGE_TOKEN, PROVISION_SHARD_HOSTPORT
  (this server has NO credential defaults — a default would silently target the wrong stack)
  [OK] exit 2 on missing env          [OK] names the missing variable

=== 3. the probes, over the socket ===
HTTP/1.1 200 OK   x-trace-id: fbf50bad-…   {"status":"ok","endpoint":"livez"}
HTTP/1.1 200 OK                            {"status":"ok","endpoint":"readyz"}
http_request_duration_seconds_bucket{method="GET",le="0.005"} 3

=== 4. the gate ===        [OK] no token -> 401        [OK] wrong token -> 401
=== 5. a bad body ===      HTTP/1.1 422   content-type: application/problem+json

=== 6. PROVISION A REALITY THROUGH THE ROUTE ===
  HTTP 201
  {"outcome":"provisioned","reality_id":"44b0d1a3-d845-4a91-84be-4b7f46905d58",
   "shard_id":"pg-shard-0.internal","db_name":"lw_reality_44b0d1a3d845", "steps":[ …11… ]}

=== 7. THE DATABASE EXISTS — asked of Postgres, not of the response ===
  pg_database: 'lw_reality_44b0d1a3d845'          [OK] the per-reality database was created
  tables in lw_reality_44b0d1a3d845: 12           [OK] the migration set was applied
  reality_registry: active on pg-shard-0.internal [OK] registry row is active

=== 8. idempotence: re-POST the same reality_id ===
  HTTP 200  {"outcome":"already_provisioned", …,"status":"active"}
  [OK] 200, not a duplicate create   [OK] still exactly one registry row

=== 9. graceful shutdown ===  [OK] exited on SIGTERM
REALITY_ID=44b0d1a3-d845-4a91-84be-4b7f46905d58  DB=lw_reality_44b0d1a3d845  failures=0
```

**And the third outcome was proven on real wreckage rather than a synthesised state.** The first
smoke run died at migration `0006_projections` (see `WSD-3`), stranding reality
`00c7e2c5-…` in `provisioning` with a half-migrated database. That is exactly the case the resume
path exists for, so it was recovered through the route:

```
before: provisioning
HTTP 200
outcome  = resumed
steps    = validate:done, pick_shard:done, register_pending:skipped, create_database:skipped,
           apply_migrations:done, register_with_pgbouncer:skipped, register_prometheus_scrape:skipped,
           register_backup_policy:skipped, transition_to_seeding:done, transition_to_active:done,
           emit_reality_created:done
after:  active        tables in lw_reality_00c7e2c5cabc: 12
  [OK] outcome=resumed   [OK] stranded reality recovered to active
  [OK] the migrations that died mid-flow are now applied
```

`register_pending:skipped` + `create_database:skipped` + `apply_migrations:done` is the idempotent
re-entry doing precisely what it claims: skipping what was finished, finishing what was not.

### After the fixes — re-run, because a refactor invalidates the evidence that preceded it

`WSD-6` moved the handler to its own file and `WSD-7` changed how pools are built, so `WS4` and
`WS5` were both re-proven rather than assumed to still hold: **6/6 bitten** again, and the live smoke
green again end to end (`201` → `lw_reality_58663ea66315`, 12 tables, `active`, then `200
already_provisioned` with exactly one registry row).

The advisory-lock guard carries its own live test and its own bite:

```
test a_released_connection_does_not_carry_an_advisory_lock_back_into_the_pool ... ok

[BITTEN]   the advisory-lock release guard
  | assertion `left == right` failed: the connection came back into the pool holding 1 advisory
  |   lock(s). `place_reality` unlocks on every return path but not on cancellation, so a timed-out
  |   provision would wedge that shard until the pool recycled the connection.
  |   left: 1   right: 0
```

`max_connections(1)` in that test is load-bearing: with a larger pool the second acquire could land
on a fresh connection that never held the lock, and the assertion would pass while being about
nothing.

---

### `WS6` — evidence: both REAL exit codes, read from the processes

```
cargo test --workspace          EXIT=0    183 suites ok, 0 FAILED
python scripts/gate-wiring-gate.py --run-all
                                EXIT=0    85 GREEN, 0 RED
```

Both detached and both read from the process, never from a task notification —
`BDR-89`/`BDR-90`, where a notification reported `0` for a sweep that exited `1`, twice.
183 suites is +2 on the 181 this branch carried in: `route_conformance` and `pool_lock_release`.

**The first sweep of this track exited 1, and it was right to.** `reality-id-adoption-gate`
caught the two bare `reality_id: Uuid` sites my own code had introduced — see `WSD-6`. A run that
reported only the final green would be hiding the one moment a gate did its job.

The runs, in order, because the first one is the point:

| run | result | what it means |
|---|---|---|
| sweep 1 | **rc=1** — 84 GREEN, 1 RED | `reality-id-adoption-gate`: `world-service` went 0 → 2 ADOPTABLE |
| — | fix + re-bite | handler split, exemptions reasoned, baseline recorded, `WSD-7` found and fixed |
| sweep 2 | **rc=0** — 85 GREEN, 0 RED | green, but graded a tree that still received edits afterwards |
| **final sweep** | **rc=0** — 85 GREEN, 0 RED | grades the committed tree |

**Stated precisely, because "the sweep was green" is easy to say loosely.** The final sweep grades
the code exactly as committed. The only writes after it are this evidence paste and the sweep's own
numbers — a run-state edit cannot change a gate's verdict about code — and the three gates that
*do* read documents (`doc-language-gate`, `citation-gate`, `source-citation-gate`) were re-run
afterwards, in seconds, against the final text.

---

## 4 · OPEN ROWS — carried, each with a mechanism

| id | what | why it is not closing here | mechanism |
|---|---|---|---|
| `WS-GATEWAY-CONSUMER` | `api-gateway-bff` has no world route, so `I1`'s player-facing path to reality creation does not exist | gate #1 (out of scope) + #2 (structural — a second language, an auth surface, a BFF contract). **This is the NEXT BUILD, not a deferral** — the handoff names it as DO NEXT | the *internal-ness* half is mechanised three ways and delivered: `the_contract_and_the_table_agree_on_which_routes_are_gated` (table `Gate` ↔ the contract's `security:` block, both directions), `every_gated_route_in_the_table_is_versioned_and_internal` (versioned ⟺ Internal), and a live 401 for both a missing and a wrong token. So a versioned route that is not internal cannot ship quietly while the gateway is absent |
| `WS-COMPOSE` | no `world-service:` compose block and no general `Dockerfile` | gate #1 — the goal bounds scope at one route, and an image build is a separate risk boundary | the reality-layer board's measured row already tracks it (*"game-tier services in compose"*), re-measured each session |
| `WS-ADMIN-CLI-HTTP` | `SubprocessProvisionInvoker` still execs the binary | `WS-F3` — swapping the only production reality-creation path is not this track's mandate | the `provision` binary staying in `[[bin]]` is the witness; retiring it is what would force this |
| `WS-TIMEOUT-DETACH` | **a timed-out provision keeps provisioning.** `spawn_blocking` tasks are not cancelled when the outer future drops, so after the 300s ceiling returns 504 the effects chain runs to completion — creating the database and finishing the transitions for a request the caller already gave up on | gate #4-adjacent but honestly gate #1: bounding it correctly needs a cancellation token threaded through `Effects`, which is the same async-trait refactor `WS-F5` defers. Not reachable in normal operation (a provision takes ~1s against a 300s ceiling) | **the recovery is what is built, and it is proven:** the work the detached task completes leaves the reality in a state the resume path handles, and `WS5` exercised precisely that against a genuinely stranded reality. A caller's retry gets `resumed` or `already_provisioned`, never a duplicate — asserted live, and `still exactly one registry row` is the assertion that would catch a regression |
| `WS-IMAGE-DRIFT` | **nothing compares a declared container image against the running one.** `WSD-3` cost this run a failed smoke and cost the turn-loop track a deferral row, for a fix that was already written and already built | gate #2 — it is a new check with a real design question (which services, and what about locally-modified stacks) | **none, and that is the finding.** Named here rather than left implicit, because the same shape — a mechanism that exists and is not running — is what `gate-wiring-gate` was built for after six CI legs sat red on `main` for four days |

---

## 5 · DRIFT REGISTER

Append as it happens. **A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| `WSD-1` | **I asserted two Phase 0 claims that were false, and wrote them into the goal.** "No OpenAPI spec exists for world-service" was checked against `contracts/api/world-service/` — the wrong directory; the home is `contracts/api/world/` and it has existed since Cycle 0. "Only `roleplay-service` depends on `service-http`" was true but framed as *world-service does not serve HTTP*, which is false: it has shipped an axum router since cycle 16. Both errors have the same shape — **I grepped for the name I expected rather than the concept**, which is precisely question 1 of AUDIT-EXISTING failing, in the document that exists to make question 1 mechanical. The gate cannot catch this: `phase0-reconcile-gate` forces the LOOK, and I looked, at the wrong string. |
| `WSD-2` | The goal I drafted told me the scaffold's blocker was discharged *by argument* ("DP-kernel is what we've been building for three days"). It is discharged **in `Cargo.toml`** — `dp-kernel` is already a path dependency of `world-service`. I had read that file to count binaries and did not read what it depended on. |
| `WSD-3` | **The live smoke failed on its first run, and the cause was `TL-PGVECTOR` — a row opened two days earlier on the turn-loop board and explicitly marked "not fixed here".** `0006_projections` died on `could not access file "vector"`. The row is now DISCHARGED, and the fix was not code: `infra/docker-compose.yml` has declared `image: loreweave/postgres-pgvector:18` (built from `postgres-pgvector.Dockerfile`, same Alpine base, same musl, adds only `vector.so`) since 2026-08-08, **the image was already built**, and the running container was still `postgres:18-alpine`. A `docker compose up -d postgres` recreated it: `vector 0.8.1` available, **161 databases intact** (the count immediately after the recreate; it is 163 now, since the smoke created two more — stated as a point in time because that is what it evidences). The drift is that a compose file and a running container disagreed for three days and nothing said so — the same shape as the six `lint-foundation` legs red on `main` for four days. A declared-vs-running check would have caught it; there is none. |
| `WSD-4` | **The route-conformance walk's first run flagged a route that existed only inside its own doc comment.** I wrote `.route("…")` in the prose explaining what the walk looks for, and the walk found it. Prose that happens to live in a source file is exactly what defeated the deferral registry's coverage check until its stripper was fixed — arriving here from the other direction, as a false positive rather than a false negative. Loud, so safe; but a gate tripped by its own documentation is one authors learn to write around. Fixed by dropping whole comment lines only — never a trailing `//`, which would truncate a `postgres://…` DSN and could hide a real mount. |
| `WSD-6` | **The sweep found the defect the unit tests could not: I introduced two bare `reality_id: Uuid` sites and `reality-id-adoption-gate` went 0 → 2 ADOPTABLE.** Both are genuinely pre-bind — `existing_registration` reads the registry *to discover whether a bind is even possible*, and the response struct reports realities in states `bind` refuses (`archived`, `soft_deleted`). So both earned exemptions. **But the first shape I reached for was wrong**: a single `handlers.rs` would have taken a PREFIX exemption that then covered every route added beside it — including the GEO_001 geography routes, which act on open, bindable realities and *should* be held to `dp::RealityId`. Split into `handlers/realities.rs` so a new handler file is default-uncovered by the exemption table, hence default-ADOPTABLE. Under-exempting is the safe direction. The gate then refused the 52 → 54 exempt count until the baseline recorded it, which is the ratchet doing its job on me. |
| `WSD-7` | **A real cancellation bug, introduced by this track and invisible to every green test.** `capacity_glue::place_reality` takes a *session* advisory lock across pick→register and unlocks on every RETURN path. Serving it over HTTP added a path it has none: axum's `TimeoutLayer` **drops** the handler future, and a dropped future runs no unlock — so the connection returns to the pool still holding the shard's placement lock, and a session lock lives until the connection closes. Every later placement on that shard would then block on a request that had already given up. The `provision` worker could never hit it: a CLI either finishes or dies, and dying closes the connection. Found by reading the code while waiting for a sweep, **not** by a test — 183 suites were green over it. Fixed with an `after_release` hook releasing every advisory lock as a connection re-enters the pool, which is local to `server::db` and leaves the worker's path byte-identical. Bitten: remove the hook and the live test reds with *"the connection came back into the pool holding 1 advisory lock(s)"*. |
| `WSD-8` | **I edited the tree during two running sweeps, having written "edit nothing while it runs" as a hazard.** A `main.rs` doc comment during sweep 2, the `world-service` README during sweep 3 — so neither sweep graded the tree it was supposed to certify, and the fix was another 25-minute sweep each time. **This row is also a phantom-citation fix**: the authorable-surface board cites `WSD-8` for exactly this lesson and no `WSD-8` existed — I cited a drift row I had learned from and never written. A reference that resolves to nothing is the shape `design-lint` refuses, and nothing checks drift ids. |
| `WSD-9` | **`services/world-service/README.md` described the crate as *"Cycle 0 scaffold — empty-compiling Rust crate, no behavior"* and *"Blocked: … the kernel and the foundation tier do not yet exist as code"*.** Both false for months: the crate has nine binaries, ~4k lines and `dp-kernel` as a path dependency. Rewritten. Recorded late, by audit, because at the time it read as tidying rather than as **a third instance of the same rot the track had already found twice that hour** (`WSD-3`, and the four stale pipeline-index gates). A doc claiming unbuilt what is built is one finding whether it is in an index, a compose file, or a README. |
| `WSD-10` | **The pgvector Dockerfile's own comment was stale from the hour it was committed.** It said `0008_pgvector_setup` *"is unregistered from the manifest while this is unbuilt"* — and `contracts/migrations/manifest.yaml` records it as **RE-REGISTERED 2026-08-08**, the same day the Dockerfile was written, with the exclusion deleted from `migration-manifest-gate` in the same change. The author updated the manifest, updated the gate, and left the sentence in the file explaining why the manifest said the opposite. Corrected. |
| `WSD-11` | **A public API surface changed and the board recorded only its effect.** `ProvisionRequest::validate` went private → `pub` so the HTTP boundary could distinguish a caller's bad input (400) from a machinery failure (500) — `ProvisionerError` carries both in `InvalidState`. The board says validation now runs at the boundary; it did not say the type's surface grew a method. Widening a shipped type's API is a thing a reviewer should see stated, not infer from a diff. |
| `WSD-5` | **I collapsed two distinct rejection statuses into one and made a documented status code unreachable.** The handler mapped every `JsonRejection` to `ProblemDetails::bad_request`, so the contract's 422 could never be produced — a response code documented and unreachable is the same defect class as a check that cannot fail. Caught by a unit test asserting 422, which I had written from the contract and initially assumed was the thing that was wrong. It was not; the code was. |

---

## 6 · EVIDENCE LOG

Appended per row as it closes. Pasted output or it did not happen.
