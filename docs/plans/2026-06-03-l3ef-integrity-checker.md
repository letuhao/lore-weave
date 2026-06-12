# L3.E/F Integrity Checker — Live Wiring Design

**Status:** Slice 1 (Rust keystone) in BUILD · Slice 2 (Go wiring) deferred to next checkpoint
**Origin:** the keystone validator that unblocks the 073 rebuild gate (DEFERRED 141/143) + clears the drift-resample deferral (118). The rebuilder is the first live projection-apply path and is `ADMIN_CLI_ENABLE_UNPROVEN_REBUILD`-gated until this validates it.

## Goal

Detect **projection drift** — cases where the live projection runner wrote a row that differs from what replaying the source events would produce. For each sampled projection row, re-derive the row by replaying its owning event aggregate(s) into a scratch copy of the table and **byte-compare** (after canonical-JSON normalization).

## Robustness principle — identical serialization on both sides

Cross-language JSON serialization (Go projection-row read vs Rust replay output) is fragile (uuid/number/timestamp formatting). So **both sides serialize through the SAME Postgres expression**: `to_jsonb(t) - <meta keys>`. The real row and the replayed temp row both go through `to_jsonb`, so a non-drifted row matches byte-for-byte. The Go comparator additionally key-sorts (already implemented in `pkg/comparator/canonicalize`).

**Meta keys stripped both sides** (the 5 VerificationMeta + HWM cols, per `0006_projections`):
`event_id`, `aggregate_version`, `applied_at`, `last_verified_event_version`, `last_verified_at`.

## Row-centric model (the skeleton's `(aggregate_id, version)` model was insufficient)

The unit of comparison is a projection **ROW**, identified by `(table, primary-key columns)`. Most tables have composite PKs (`pc_inventory` = `(pc_id, item_code)`), so the live types must carry the PK, not just an aggregate id. (Slice 2 reshapes the skeleton types accordingly.)

### Owning-aggregate resolution

Every projection row carries `event_id` (the last event that wrote it). The owning aggregate is resolved generically:

```sql
SELECT aggregate_type, aggregate_id FROM events WHERE event_id = <row.event_id>
```

So the only static per-table knowledge needed is the **PK columns** + the **cross-aggregate set** (below).

### Per-table map (from `0006_projections` + the projection crates)

| Table | PK columns | Owning aggregate(s) | Notes |
|---|---|---|---|
| pc_projection | pc_id | `pc`/pc_id | single |
| pc_inventory_projection | pc_id, item_code | `pc`/pc_id | single, multi-row |
| pc_relationship_projection | pc_id, other_entity_type, other_entity_id | `pc`/pc_id | single, multi-row |
| npc_projection | npc_id | `npc`/npc_id | single |
| npc_pc_relationship_projection | npc_id, other_entity_id | `npc`/npc_id | single, multi-row |
| region_projection | region_id | `region`/region_id | single |
| world_kv_projection | key (TEXT) | `world`/(the world aggregate) | single; key from payload |
| session_participants | session_id, participant_type, participant_id | `session`/session_id | single, multi-row |
| npc_session_memory_embedding | npc_id, session_id | `npc`/npc_id | single; VECTOR(1536) col — both sides render via the SAME pgvector `to_jsonb`, so byte-match holds if the event carries the embedding deterministically |
| **npc_session_memory_projection** | npc_id, session_id | **`session`/session_id + `npc`/npc_id** | **CROSS-AGGREGATE** — built from both `session.*` (INSERT/archive) and `npc.memory_updated` (facts/summary UPDATE). Needs BOTH replayed in global order. |

The owning-aggregate **set** for a row: resolve via event_id (gives the last writer) for the single-aggregate tables; for `npc_session_memory_projection`, derive `{(session, session_id), (npc, npc_id)}` from the PK columns. (Slice 2 decides the set per table; the keystone bin just takes a list.)

## Keystone (slice 1): the `replay-aggregate` Rust bin

A new `services/world-service/src/bin/replay-aggregate.rs` (+ testable `src/replay_aggregate/` module). Reuses the 073 rebuilder building blocks: `dp_kernel::ProjectionRunner` + `world_service::rebuild::all_projections()` + `world_service::rebuild::writer::SqlxProjectionWriter` (which targets a table BY NAME → we point it at a TEMP shadow).

### Invocation

```text
env REALITY_DB_URL=postgres://…           (password off `ps`)
replay-aggregate
  --reality-id <uuid>
  --projection <table>                    (an L3.A projection table)
  --aggregate <type>:<id>                 (repeatable: 1 for single, 2 for cross-aggregate)
  --boundary-event-id <uuid>              (replay events up to & incl. this event, global order)
  --pk '<json {col: val, ...}>'           (the sampled row's primary key)
```

### Algorithm

1. Connect a **1-connection** pool (`max_connections(1)`). The temp table is connection-local, so every statement must run on the one connection.
2. Resolve the boundary: `SELECT recorded_at FROM events WHERE reality_id=$1 AND event_id=$2`.
3. `CREATE TEMP TABLE <table> (LIKE public.<table> INCLUDING ALL)`. `pg_temp` is first in `search_path`, so the reused writer's `INSERT INTO <table>` / `jsonb_populate_record(NULL::<table>, …)` resolve to the **temp** shadow; the real table is never touched. `LIKE public.<table>` is qualified so it copies the real table (not itself). No `ON COMMIT DROP` (the writer commits per batch; temp must survive across batches).
4. Replay the specified aggregates' events, **global-ordered**, up to the boundary:
   ```sql
   SELECT … FROM events
   WHERE reality_id=$1
     AND (aggregate_type, aggregate_id) IN (…)
     AND (recorded_at, event_id) <= ($boundary_recorded_at, $boundary_event_id)
   ORDER BY recorded_at, event_id
   ```
   Each event → `ProjectionRunner::apply_one` → the writer applies target-table updates to the temp shadow. (Updates for other tables/pks are dropped or no-op against temp.)
5. Select the row: `SELECT to_jsonb(t) - <meta keys> AS payload FROM <table> WHERE <pk predicate> LIMIT 1`.
6. Emit JSON to stdout:
   ```json
   {"found": true, "events_replayed": 12, "status": "ok", "payload": { … to_jsonb-minus-meta … }}
   ```
   `found:false` (+ `payload:null`) when replay produced no row at the PK. `events_replayed:0` → the aggregate(s) had no in-bound events (pruned/never-existed) → caller marks SKIP. `status:"error"` on replay failure → caller marks SKIP (not drift).

### Comparator decision (Go side, slice 2)

- `status==ok && events>0 && found && byte-equal` → **clean**
- `status==ok && events>0 && found && !byte-equal` → **DRIFT**
- `status==ok && events>0 && !found` → **DRIFT** (orphan projection row the events don't produce)
- `events==0` or `status==error` → **SKIP** (can't verify; do not count as drift)

## Known limitations (validate in live-smoke; tracked as DEFERRED)

1. **No global sequence column** on `events` — cross-aggregate ordering uses `(recorded_at, event_id)`, which approximates but does not perfectly reconstruct the live consumer's apply order. `npc_session_memory_projection` drift should be treated as "investigate, may be an ordering artifact." A real monotonic global sequence would make it exact. → DEFERRED.
2. **Replay needs full event history** — if an aggregate's old events were archived/pruned, replay can't reproduce the row → reported as `events:0`/partial → SKIP. Acceptable (retention keeps recent; archive detaches old partitions).
3. **Per-column nondeterminism beyond the 5 meta keys** (e.g. a default-`NOW()` timestamp a projection doesn't set from event data) would surface as drift. This is correct-but-noisy; triage per-projection in the first live-smoke (pairs with DEFERRED 143).
4. **VECTOR fidelity** — `npc_session_memory_embedding`'s `to_jsonb(embedding)` float rendering must be identical both sides (same pgvector). Confirm in live-smoke.

## Slicing

- **Slice 1 (this):** the `replay-aggregate` bin + testable module + unit tests (SQL shape, PK predicate, identifier safety, meta-strip, JSON output) + a PG-gated round-trip integration test (skipped without `LOREWEAVE_TEST_PG_URL`). POST-REVIEW checkpoint.
- **Slice 2 (next):** Go live-wiring — pgx `RowSource` (`to_jsonb - meta` sample + event_id aggregate resolution), subprocess `AggregateLoader` (invokes this bin), pgx `Persister` (UPSERT `projection_drift_state`), the per-table PK/aggregate-set map, `main` per-reality ticker + `/healthz`/`/readyz`/`/metrics`, reshape the skeleton types to row-centric. Then the foundation live-smoke.

## Slice 3 (147 — D-L3EF-REPLAY-LIVE-SMOKE): the round-trip proof + the bug it found

The PG-gated round-trip test promised in Slice 1 (deferred because Slice 1 had no DB). Lives at `services/world-service/tests/replay_aggregate_live.rs`, gated on `LOREWEAVE_TEST_PG_URL` (mirrors `embedding_live.rs`): applies `0002`+`0006` via `sqlx::raw_sql`, seeds events, produces the "live" projection row **in-process** through the SAME `all_projections()` + `SqlxProjectionWriter` the bin reuses, runs the compiled `replay-aggregate` bin as a subprocess (`env!("CARGO_BIN_EXE_replay-aggregate")` — the exact subprocess the Go loader invokes), and byte-compares the bin's `to_jsonb − meta` payload against the live row's. Skips green when the env is unset.

Cases:
1. **pc clean** — `pc.spawned`+`pc.moved` → `pc_projection`. Replay payload **==** live row. The core single-aggregate proof.
2. **pc drift** — tamper the live row (`UPDATE … SET name`); replay is unchanged → payload **≠** live row, and the replayed `name` is the *correct* (pre-tamper) value. Proves the checker catches drift rather than rubber-stamping.
3. **multi-aggregate invocation** — `session.started`+`session.ended` (session agg) interleaved (by `recorded_at`) with `npc.created` (npc agg) → `npc_session_memory_projection`. Bin invoked with TWO `--aggregate` pairs; the npc event contributes no update to this target (dropped), so it exercises the 2-pair `IN`-list events query + cross-aggregate global ordering against real PG. Replay payload **==** live row (composite PK, Insert→Update sequence).

### The bug the live-smoke surfaced — generic-writer Insert NULLs omitted columns

The generic [`SqlxProjectionWriter`] Insert was `INSERT INTO <t> SELECT * FROM jsonb_populate_record(NULL::<t>, $1)`. `jsonb_populate_record` fills keys absent from the JSON with the base record's value (NULL, since the base is `NULL::<t>`), and `SELECT *` then writes an **explicit NULL into every unlisted column**. For a projection whose Insert omits a `NOT NULL DEFAULT` column — e.g. `npc_session_memory_projection.summary`/`.facts`, which `session.started` does not set — this is a `null value … violates not-null constraint`. **The 073 rebuild of `npc_session_memory_projection` was broken**, latent only because the rebuilder is operator-gated and had no live-smoke until now.

**Fix** (`services/world-service/src/rebuild/writer.rs`): emit a column list of exactly the keys the projection set, so omitted columns fall to their schema DEFAULT:

```text
INSERT INTO <t> (<keys…>) SELECT <keys…> FROM jsonb_populate_record(NULL::<t>, $1::jsonb)
```

The keys are now interpolated into SQL, so each is `ensure_ident`-validated (the Insert.row keys were previously trusted to `jsonb_populate_record`; the column-list path mirrors the Update SET path's defense). This is the root-cause fix — it repairs the whole class for every projection, not just `session.started`. (Bonus: a typo'd/phantom Insert key now fails loud — `column … does not exist` — instead of being silently dropped by `SELECT *`, which is the right posture for a recovery tool. It also fixes the same `npc_session_memory_projection` rebuild break in the 073 `rebuilder` bin, partially clearing DEFERRED 143.)

### The SECOND bug the live-smoke surfaced — the bin deadlocked on `Handle::block_on`

The first live run hung indefinitely (>1100 s) right after `read_events`, with the bin's DB connection sitting idle. Root cause: the bin built its runtime with `new_current_thread`, but the reused sync `SqlxProjectionWriter::apply_batch` bridges to async sqlx via `Handle::block_on` on that runtime's handle. **On a current-thread runtime the IO driver is ticked ONLY inside `Runtime::block_on`** — so a `Handle::block_on` future awaiting socket readiness registers interest but is never polled again → deadlock. The bin had never run live (Slice 1 had no DB), so this was latent.

**Fix** (`src/bin/replay-aggregate.rs`): build the runtime with `new_multi_thread().worker_threads(1)` — the IO driver then runs on its own thread, so the writer's `Handle::block_on` makes progress while the main thread blocks. The single-connection temp-table affinity is unchanged: it is a property of the `max_connections(1)` POOL, not the runtime flavor. This matches the `rebuilder` bin, whose author already noted `Handle::block_on` "is sound only across runtimes".

### Cross-aggregate WRITE convergence — still gated (tracked)

A *genuine* cross-aggregate case (both `session.*` AND an `npc.*` event mutating the SAME `npc_session_memory_projection` row) is NOT achievable with the current skeleton projections: `npc.said` emits an Update with a synthetic `interaction_count_increment` field that is not a real column (the generic writer has no read-modify-write/increment concept → it would error), and `npc.memory_updated` is a projection TODO. Slice 3 therefore proves the multi-aggregate *invocation/ordering* path (case 3) but documents WRITE convergence as deferred — it unblocks when those handlers + an increment-aware writer land. Pairs with DEFERRED 146 (no global sequence).

## Slice 4 (151 — D-IC-MONTHLY-REPLAY-BATCHING): long-lived replay server (DESIGN; build deferred)

**Problem.** The row-centric checker re-derives each sampled row by exec-ing the `replay-aggregate` bin once **per row** (fork + tokio runtime init + `connect` + `CREATE TEMP` + replay + `SELECT`). Daily samples ~20 rows/table — fine. The L3.F **monthly full-scan** walks EVERY row (100k+/table); one subprocess per row is operationally impractical at scale (compounds the doc's "monthly ≈ 500× daily"). The monthly path is not deployed yet, so this is a scale-readiness item, not a live bug.

**Chosen architecture (user decision, 2026-06-04): a long-lived replay SERVER.** A persistent process holds warm DB connections, eliminating the per-row fork + runtime-init + connect. The Go checker calls it per row over HTTP instead of spawning the bin.

### Server (`replay-server`, new world-service bin)

- axum HTTP service (mirrors the embedding-worker / tilemap axum convention). `POST /replay` with the existing `ReplayRequest` shape `{reality_id, projection, aggregates[], boundary_event_id, pk{}}` → `ReplayOutput` JSON (the SAME contract the bin emits today — Go parses it identically). Plus `/healthz`, `/readyz`.
- Refactor the per-row core out of `src/bin/replay-aggregate.rs::execute` into a reusable `world_service::replay_aggregate::replay_one(pool, &Invocation) -> Result<ReplayOutput, String>`. Both the standalone bin (N=1) and the server call it — the bin stays as the daily path + the live-smoke target; zero contract drift.
- **Temp-table lifecycle (the subtle part).** The temp shadow is connection-local and the reused `SqlxProjectionWriter` commits per batch, so `ON COMMIT DROP` cannot be used (it would drop the shadow before the final SELECT). On a POOLED long-lived connection a prior request's temp table lingers and a same-projection `CREATE TEMP` then fails. Per-request fix: `DROP TABLE IF EXISTS <projection>` (pg_temp resolves first) → `CREATE TEMP TABLE <projection> (LIKE public.<projection> INCLUDING ALL)` → replay → SELECT. Keeps the connection warm (connect amortized) while staying correct + isolated. Keep `max_connections` ≥ the server's concurrency; each request pins ONE connection for its temp-table affinity (acquire→DROP/CREATE→replay→select→release).
- Auth/network: in-cluster only (same posture as the other internal services); no public exposure (the gateway invariant is unaffected — this is an internal worker-to-worker call).

### Go checker wiring

- `pkg/replayloader`: add an HTTP `Replayer` (POST to `REPLAY_SERVER_URL`) alongside the existing `ExecRunner` subprocess loader; both satisfy `live.Replayer`, so `live.CheckRow` / `full_check` are unchanged. Select by config/env: monthly → server; daily can stay subprocess or also use the server.
- `main.go`: resolve `REPLAY_SERVER_URL`; build the HTTP replayer when set, else fall back to the subprocess loader (keeps the daemon runnable without the server).

### Deploy / cutover

- New k8s Deployment for `replay-server` (one per shard-DB reachability domain, or a single multi-reality server that takes the DSN per request — `ReplayRequest` would then carry/resolve the reality's shard DSN server-side via the reality registry, mirroring the daemon). The integrity-checker CronJob gains a dependency on the server being reachable.
- Cutover is config-gated + reversible: with `REPLAY_SERVER_URL` unset the checker uses the subprocess loader exactly as today, so the server can be rolled out dark then switched on.

### Slicing (build, deferred to a focused session)

1. **Server core:** refactor `replay_one` out of the bin + the axum `replay-server` bin + per-request temp lifecycle + unit tests + a PG-gated live-smoke (server up → POST /replay → assert ReplayOutput == the bin's). Self-contained, no deploy needed.
2. **Go HTTP replayer:** `replayloader` HTTP mode + `main.go` selection + tests. Cutover stays config-gated.
3. **Deploy:** k8s manifest + the per-request shard-DSN resolution decision + an e2e smoke.

**Why deferred now:** it is a brand-new networked service; the monthly path it optimizes is not deployed (the win is unmeasurable today); and slices 1–3 each warrant their own VERIFY + live validation. Tracked in DEFERRED 151 with this design as the implementation plan.
