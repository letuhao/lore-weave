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
