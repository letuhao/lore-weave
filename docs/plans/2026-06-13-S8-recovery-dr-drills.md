# S8 — Recovery / DR drills: implementation plan

**Plan date:** 2026-06-13 · **Size:** L · **Spec:** `docs/specs/2026-06-13-S8-recovery-dr-drills.md`
**Build order:** Inc 1 (G1 kill-restart, reuses S6 harness) → Inc 2 (G2 rebuild) → Inc 3 (G3
archive round-trip, heaviest) → Inc 4 (G4 replay-determinism) → Inc 5 (conformance + CI).
Each increment is independently committable; verdict convention from S6 (notrun=exit2 / fail=exit1).

---

## Inc 1 — G1 kill+restart → convergence  (`scripts/chaos/recover-kill-restart.sh`)
- Reuse the S6 setup (meta+shard DBs, the real Go publisher, the bash history checker from
  `fault-redis-partition.sh`). Differences from S6: the fault is a **SIGKILL of the publisher
  process** mid-drain (not a network toxic), then a **restart of the same binary**.
- Flow: migrate meta+shard → emit (multi-reality) → register realities → start publisher
  (POLL_INTERVAL=1s BATCH_SIZE=5) → once `published>0` and `<NEVENTS`, `kill -9` it → restart →
  poll until `published=FALSE` count is 0 (quiesce, ≤30s) → assert no dead-letter → C3 (`wg -verify`)
  → **history checker (at-least-once, review HIGH-1):** `distinct(event_id) == events` (no-loss, no
  spurious id) AND `XLEN >= events` (duplicates ALLOWED — the publisher XADDs auto-id + marks
  separately, so a kill between XADD and mark re-emits the same event_id on restart). The consumer
  dedups by event_id; exactly-once is NOT the contract.
- Verdict: publisher won't start / didn't drain in time → notrun; **loss** (`distinct < events`) or a
  spurious/unknown event_id or dead-letter → fail. A duplicate (`XLEN > events`, same event_id) is
  NOT a fail.
- `--bite`: **XDEL a stream entry** after quiesce → `distinct(event_id) < events` → loss caught →
  exit 1. (Injecting a duplicate is NOT a bite — it is expected behavior.)

## Inc 2 — G2 rebuild-from-events → B∧C∧C2  (`scripts/chaos/recover-rebuild.sh`)
- Resolve `wg`, `rebuilder` (target/debug), `ic` (mirror S5). migrate shard → emit → record
  per-table row counts → **TRUNCATE the populated projection tables** (S5's 6: pc_projection,
  pc_inventory_projection, npc_projection, npc_session_memory_projection, region_projection,
  session_participants) → `REALITY_DB_URL=… rebuilder --reality-id … --projection <t>` per table →
  assert: **B** (`wg -verify`), **C** (`wg -check-projections`), **C2** (row counts match the
  pre-truncate snapshot).
- Verdict: rebuild infra error → notrun; B/C/C2 violated → fail.
- `--bite`: skip the rebuild loop → `wg -verify` (B) fails on the empty projections → exit 1.
- Note (review LOW-6): the 6 projection tables are independent derived state (no inter-projection
  FK), so TRUNCATE/rebuild order is free; if a future inter-projection FK lands, TRUNCATE order would
  matter — tracked here, not a today-bug.

## Inc 3 — G3 archive-restore (Parquet round-trip) → C3 byte-match  (`scripts/chaos/recover-archive-restore.sh`)
- Build/resolve `archive-worker` + `archive-restore` (`go build -C services/archive-worker -o aw
  ./cmd/archive-worker` + `-o arx ./cmd/archive-restore`). Check **MinIO reachable** (foundation-dev
  minio) → else notrun.
- Flow:
  1. migrate meta+shard. **Create a last-month partition** (review MED-2) `events_p_<YYYY_MM>
     PARTITION OF events FOR VALUES FROM ('<lastmonth>-01') TO ('<thismonth>-01')`. Land rows there
     with a **backdated `recorded_at`**: `wg -emit` into the shard (default partition), then
     `INSERT INTO events (<cols>) SELECT <cols-with recorded_at:='<lastmonth>-15'> FROM events
     WHERE recorded_at >= '<thismonth>-01'` and delete the originals — so the archivable set sits in
     the month partition, not `events_p_default` (which `partition_picker` never sees). Confirm the
     partition key column at BUILD. Register the reality.
  2. **C3 digest the window** via a deterministic SQL digest (review MED-4) over a FIXED column list:
     `SELECT md5(coalesce(string_agg(event_id::text||'|'||payload::text,'|' ORDER BY global_seq),''))
     FROM events_p_<YYYY_MM>` → `$pre`. (Column list = the intersection present in both `events` and
     `events_restore_*` — review LOW-5: event_id, payload, global_seq, reality_id; verify at BUILD.)
  3. run `archive-worker` once with **`ARCHIVE_CUTOFF=0`** + MINIO_* env → it picks the eligible
     partition → Parquet→MinIO (`lw-event-archive`)→verify→**DROP** the partition. Confirm the
     partition is gone + `archive_state` row written (else notrun: not eligible / didn't archive).
  4. `RESTORE_DB_URL=… arx restore --reality <uuid> --month <YYYY-MM>` → rows in
     `events_restore_<YYYYMM>`.
  5. **C3 digest the restored rows** (same SQL digest, same column list) → `$post`; assert
     `$pre == $post`.
- Verdict: MinIO down / archive-worker didn't archive (partition not eligible) / restore found no
  blob → notrun; digest mismatch → fail.
- `--bite`: after restore, `UPDATE events_restore_<YYYYMM> SET payload = payload || '{"x":1}' …` one
  row (or delete a row) → `$post ≠ $pre` → exit 1. (Stronger blob-corruption bite if cheap: overwrite
  a byte in the MinIO object → restore decode mismatch.)

## Inc 4 — G4 replay determinism across two rebuilds  (`scripts/chaos/recover-replay-determinism.sh`)
- migrate shard → emit → rebuild `pc_projection` → snapshot → `a.txt` → TRUNCATE → rebuild again →
  snapshot → `b.txt` → assert `a.txt == b.txt` (byte-identical). Note in-script: this is C's
  deterministic-replay facet, NOT H0 (cross-language).
- **Deterministic-columns snapshot (review MED-3):** FIRST inspect `pc_projection`'s columns
  (`\d pc_projection` / information_schema) at BUILD. If it has a per-run `updated_at`/`rebuilt_at`/
  serial surrogate, snapshot `SELECT to_jsonb(t) - 'updated_at' - '<surrogate>' FROM pc_projection t
  ORDER BY <pk>` (jsonb minus the non-deterministic keys); else snapshot `to_jsonb(t)` whole and add
  an in-script comment that pc_projection carries no non-deterministic column. Without this, a
  rebuild timestamp makes two rebuilds differ and G4 falsely fails.
- Verdict: rebuild error → notrun; snapshots differ → fail.
- `--bite`: emit a **different seed** into a second shard, rebuild, snapshot → assert it DIFFERS from
  `a.txt` (proves the byte-compare distinguishes — a vacuous always-equal compare fails this).

## Inc 5 — conformance cases + CI
- 4 live-probe catalog YAMLs (`recover-kill-restart`, `recover-rebuild`, `recover-archive-restore`,
  `recover-replay-determinism`), `kind: live-probe`, `requires:[foundation-stack]` (G3 self-checks
  MinIO). Descriptions name the oracle + bite.
- `.github/workflows/conformance-ci.yml`: add a **`recovery-nightly`** job (schedule/workflow_dispatch)
  — rust+go+docker, build `rebuilder`/`replay-aggregate`/`wg`/`ic`/`pub`/`archive-worker`/
  `archive-restore`, boot PG+Redis+MinIO, run the 4 drills (exit 1 → fail; 2 → notrun green). Mirrors
  the S5/S6/S7 nightly pattern (dormant until merged to main).
- Run the conformance suite locally (Git-Bash-first) → the 4 recover cases notrun on the bare runner
  (no stack), nothing fails; live-verify each drill against the booted foundation-dev stack.

## Cross-cutting
- Reuse S6 chaos `lib`/patterns; no provider SDKs / model names / secrets (dev creds foundation/
  foundation, minio foundation/foundation-secret-dev-only).
- SESSION + deferred + memory at COMMIT; `/review-impl` on plan before BUILD + on impl before commit.
- Live-verify on the foundation-dev stack (PG 55432/55600, Redis 56379, MinIO 59000) — the drills
  need the real publisher/rebuilder/archive-worker, so this is genuinely cross-component (the §6
  live-smoke evidence token applies).
