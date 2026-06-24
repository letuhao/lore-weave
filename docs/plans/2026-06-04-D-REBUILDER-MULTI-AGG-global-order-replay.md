# D-REBUILDER-MULTI-AGG — Global-order replay for multi-aggregate projections (build plan)

> **Origin:** deferred row surfaced by S3 (`npc_session_memory_projection` rebuild → `aggregates_failed:2`).
> **Status:** PLAN (written; awaiting human review before BUILD).
> **Task size:** **L–XL** — touches `crates/rebuilder` + `services/world-service/src/rebuild/{writer,event_source}.rs` + a new global-order rebuild path + the rebuilder bin (mode selection) + tests + a live re-proof (cargo build of world-service). Full 12 phases; `/review-impl` (load-bearing kernel service).
> **Approach (locked):** **B — global-order replay for multi-aggregate tables + writer increment support** (the correct fix; matches how the integrity-checker's `replay-aggregate` handles multi-aggregate tables).

---

## 1. CLARIFY — corrected root cause & scope

### Root cause (corrected — deeper than the deferred row implied)
Two stacked problems make `npc_session_memory_projection` rebuild fail:

1. **Increment pseudo-field the generic writer can't apply.** `NpcProjection`'s `npc.said` arm (`crates/projections/npc/src/lib.rs:82-86`) emits `Update { fields: { interaction_count_increment: 1 } }`. The real column is `interaction_count`; `interaction_count_increment` is a *pseudo-field* meaning "+1". The generic writer (`writer.rs:84-106`) does `SET interaction_count_increment = r.interaction_count_increment` via `jsonb_populate_record(NULL::npc_session_memory_projection, …)` → `interaction_count_increment` is **not a column** → SQL `column does not exist` → the aggregate fails. **This is the immediate `aggregates_failed:2`** (the 2 npcs with `npc.said`). Live evidence: session aggregates created the 2 rows, but `interaction_count` stayed 0.
2. **Cross-aggregate ordering.** The row is created by the *session* aggregate's `session.started`; the increment comes from the *npc* aggregate's `npc.said`. The per-aggregate-parallel `ParallelRebuilder` (`crates/rebuilder/src/lib.rs:445`) replays aggregates independently/concurrently, so even with #1 fixed an increment-via-UPDATE on a not-yet-created row affects 0 rows → wrong count (0 instead of N).

### The fix (approach B)
- **Writer increment support** — recognize the `<col>_increment` convention: `SET <col> = COALESCE(t.<col>, 0) + <bound value>`.
- **Global-order replay for multi-aggregate tables** — for tables written from >1 aggregate type, replay ALL the reality's events in `(recorded_at, event_id)` order in a single sequential pass (so `session.started` precedes `npc.said`). Single-aggregate tables keep the fast per-aggregate-parallel path.

### In scope
1. **`writer.rs` increment**: split `Update.fields` into normal vs `*_increment`; emit `SET col = COALESCE(t.col,0) + $N` (value bound separately, since the pseudo-field isn't a column); **error on 0-rows-affected for an increment** (an increment on a missing row means the ordering contract was violated — fail loud, the correct recovery-tool posture). Normal fields keep the `jsonb_populate_record`/`r.col` path.
2. **`event_source.rs` global reader**: `GlobalEventSource::events_after(cursor, batch)` → `SELECT … FROM events WHERE reality_id=$1 AND (recorded_at, event_id) > ($2,$3) ORDER BY recorded_at, event_id LIMIT $4`.
3. **Global-order rebuild path** (new `rebuild/global.rs` or a fn in the bin): TRUNCATE target → page global-order events → fan each through `all_projections()` → apply target-table updates in order. Sequential (correctness over throughput).
4. **Mode selection** (`bin/rebuilder.rs`): a `MULTI_AGGREGATE_TABLES` set (`npc_session_memory_projection`; audit the others — `npc_pc_relationship_projection`, `session_participants`). Multi-aggregate table → global path; else → existing parallel path.
5. **Tests**: writer increment SQL-shape unit test; global-order replay unit test (fake global source emits session.started then npc.said out of per-aggregate order → interaction_count == N, row present); a multi-aggregate ordering test (the failure repro → now clean).
6. **Live re-proof**: re-run `scripts/workload-gen-pipeline-smoke.sh` (S3) → `npc_session_memory_projection` rebuilds with **failed=0** and correct `interaction_count`.

### Out of scope
- Reworking the per-aggregate parallel path for single-aggregate tables (it's correct + fast — leave it).
- The live streaming-projection runtime (still none; rebuild is the apply path).
- Removing the `MULTI_AGGREGATE_TABLES` allowlist in favor of auto-detection (could derive from which projections write a table across aggregate types — a nicety; start with the explicit set).

### Acceptance gate (LOCKED)
- `cargo build -p world-service` + `cargo test -p rebuilder -p world-service` green.
- Writer increment: unit test asserts `SET interaction_count = COALESCE(t.interaction_count,0) + …` SQL + 0-rows-on-increment errors.
- Global-order replay: unit test reproduces the cross-aggregate case (session.started + npc.said from different aggregates) → row present, `interaction_count` correct, 0 failures.
- **Live:** S3 pipeline smoke → `npc_session_memory_projection` `aggregates_failed:0`, `interaction_count` matches the seeded `SaysPerSession`.
- Remove the `SOFT_FAIL_TABLES` tolerance for `npc_session_memory_projection` from `scripts/workload-gen-pipeline-smoke.sh` (it should now rebuild clean).

---

## 2. DESIGN

```
crates/rebuilder/src/lib.rs        # + a global-order replay fn (or trait) — sequential, no per-agg checkpoint
services/world-service/src/rebuild/
  writer.rs        # + increment fields (COALESCE + bound value), 0-rows-on-increment error
  event_source.rs  # + GlobalEventSource (recorded_at,event_id cursor)
  global.rs (new)  # global-order rebuild orchestration (TRUNCATE → page → apply)
  mod.rs           # + MULTI_AGGREGATE_TABLES, mode dispatch helper
src/bin/rebuilder.rs  # pick global vs parallel by table
```

- **Writer increment** — `build_stmt` Update branch: partition `fields` into `(normal, increments)`. For each increment key `k` ending `_increment`, base col `b = strip(k)`, validate `b`, add `b = COALESCE(t.b,0) + $N` to the SET list and push the value to a `binds` vec. Return `(sql, Vec<Value>)` where `binds[0]` is the jsonb payload, `binds[1..]` the increment values. `apply_batch` binds them in order. After execute, if an increment statement reports `rows_affected()==0` → error (ordering violation).
- **Global replay** — a sequential loop: `TRUNCATE target` once, then page `events_after(cursor, batch)`; for each envelope, `runner.apply_one(env)` → writer applies target-table updates (the writer drops non-target updates as today). Cursor advances by `(recorded_at, event_id)`. No per-aggregate checkpoint/dead-letter (single pass; a failure aborts the rebuild → reality stays frozen, same posture).
- **Mode dispatch** — `mod.rs`: `pub const MULTI_AGGREGATE_TABLES: &[&str]`; `pub fn needs_global_order(table) -> bool`. `bin/rebuilder.rs` branches.

---

## 3. PLAN — build increments (TDD)
1. **writer.rs increment** — split fields, COALESCE SET, bound values, 0-rows error. Unit tests (SQL shape + the multi-bind payload).
2. **event_source.rs `GlobalEventSource`** — the cursor query. (Live-tested; a small decode test.)
3. **global.rs replay** — sequential orchestration. Unit test with a fake global source: session.started + npc.said interleaved across aggregates → assert the increment applied to the existing row (recording writer).
4. **mod.rs + bin** — `MULTI_AGGREGATE_TABLES` + dispatch. Unit test `needs_global_order`.
5. **Live re-proof** — rebuild `npc_session_memory_projection` via the global path on the S3 smoke DB → failed=0, interaction_count correct; drop the `SOFT_FAIL_TABLES` tolerance.

### VERIFY gate
`cargo build -p world-service`; `cargo test -p rebuilder -p world-service` green; S3 pipeline smoke → npc_session_memory failed=0 + correct counts; language-rule PASS (Rust kernel service — I3).

---

## 4. Risks & open items
- **R1 — global-order performance.** Sequential single-pass is slower than per-aggregate-parallel. Acceptable: only multi-aggregate tables (1 today) use it; catastrophic rebuild of single-aggregate tables keeps parallelism. Note for perf if a huge multi-aggregate table appears.
- **R2 — `MULTI_AGGREGATE_TABLES` completeness.** Audit which tables are written across >1 aggregate type (npc_session_memory: session+npc; check npc_pc_relationship, session_participants). A missing one → still per-aggregate fail. Mitigation: the audit in increment 4 + a test per multi-aggregate table.
- **R3 — increment on a legitimately-absent row.** If a `npc.said` references a session whose `session.started` is genuinely missing (a real data gap), the 0-rows error fails the rebuild loudly — correct (don't silently undercount), but it conflates a data gap with an ordering bug. The error message must name both possibilities.
- **R4 — 1M-context Rust build cost.** `cargo build -p world-service` is large; first build may be slow. Pre-built artifacts exist (`target/debug/rebuilder.exe`).

**Open**
- **O1** — auto-derive `MULTI_AGGREGATE_TABLES` from the projection set (which tables a projection writes from a non-native aggregate). Nicety; defer.

## 5. Deferred-Items to clear/add at COMMIT
- **Clear D-REBUILDER-MULTI-AGG** (move to Recently-cleared) once the live re-proof is green.
- Possibly add **D-REBUILDER-MULTI-AGG-AUDIT** (O1 / R2) if the audit finds more multi-aggregate tables than fixed.
