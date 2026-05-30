# P1 / DEFERRED 056 + 057 — archive-worker live-wiring

> **Task size:** XL. **Mode:** full human-in-loop. **Branch:** `mmo-rpg/foundation-mega-task`.
> Closes `DEFERRED.md` **056** (archive_state migration) + **057** (archive-worker
> live-wiring incl. real Parquet+ZSTD + restore CLI, per operator decision).

## 1. Goal
Turn the archive-worker from a skeleton into a functional cold-storage pipeline,
live-smoked on docker-compose:
```
events partition (past 90d cutoff) → archive_loop:
  pick oldest un-archived → load rows → Parquet+ZSTD encode → MinIO Put
  → verify-after-upload → archive_state RecordArchived → DETACH+DROP partition
+ archive-restore CLI: archive_state List → MinIO Get → decode → re-INSERT temp
```

## 2. Operator decisions (locked 2026-05-30)
- **Parquet = real now.** Swap the stub encoder for `parquet-go` + `klauspost`
  ZSTD, KEEPING the `LWP1` header/footer ABI (so `VerifyHeader` + archive_state
  stay valid). Bump SchemaVersion → 2 (Parquet body; no v1 prod data exists).
- **Restore CLI = wire now.** `cmd/archive-restore` does the read path
  (List → Get → Decode → re-INSERT into a temp table) for a full round-trip.

## 3. Existing surface (verified)
- Pure-libs tested: `partition_picker` (Catalog + StateReader), `archive_loop`
  (orchestrator; CRITICAL invariant verify+record BEFORE drop), `state.Store`,
  `object_store.Store`, `parquet_writer` (stub Encoder/Decoder/VerifyHeader).
- `types.EventRow` mirrors the `events` columns; `types.ArchivedObject` →
  archive_state row; `types.Partition` (name + bounds + estimate).
- Schema: `events` (per_reality 0002, partitioned monthly on recorded_at);
  next per_reality migration number = **0011**.

## 4. Design
### 4.1 migration 0011 archive_state (per_reality)
PK (reality_id, partition_name); object_key, byte_size, row_count,
format_header BYTEA, archived_at; nonneg CHECKs.

### 4.2 pgx adapters (new `pkg/pgio`)
- `Catalog.ListPartitions` → `pg_inherits` children of `events`, parse
  `events_p_YYYY_MM` → bounds (cross-check via name; estimate from pg_class.reltuples).
- `RowSource.LoadPartition` → `SELECT … FROM <partition>` (old partitions are
  immutable past the 90d cutoff — a plain SELECT is safe, no ATTACH-staging needed).
- `PartitionDropper.Drop` → `ALTER TABLE events DETACH PARTITION <p>; DROP TABLE <p>;`
  in one tx (validate the name against `events_p_[0-9]{4}_[0-9]{2}` — no SQL injection).
- `state.Postgres` → archive_state AlreadyArchived / RecordArchived (ON CONFLICT
  DO NOTHING) / List. Implements state.Store + partition_picker.StateReader.

### 4.3 minio ObjectStore (`pkg/miniostore`)
minio-go Put/Get/Exists on `lw-event-archive` (ensure-bucket on boot, public
NOT needed — internal cold storage).

### 4.4 real Parquet (`parquet_writer` swap)
Convert EventRow ↔ a parquet-tagged row struct (uuid→string, time→unix nanos,
nullable AuditRef/RegistryVersion → optional). parquet-go writer with ZSTD
column compression → body; wrap in the LWP1 header/footer; SchemaVersion=2.
Decoder reverses. VerifyHeader unchanged. Round-trip + corrupt-byte tests updated.

### 4.5 main.go (archive-worker) + archive-restore
- archive-worker: meta pool → active realities → per-reality pools + minio +
  build Loop per reality → ticker (per-reality scheduler) → graceful shutdown →
  /healthz+/readyz+/metrics.
- archive-restore: flags (reality, month or all) → state.List → minio Get →
  Decode → re-INSERT into `events_restore_<ts>` temp table; print summary.

### 4.6 live-smoke (`tests/integration/archive_worker_live_smoke_test.go`)
Seed a past-cutoff partition with N events → archive_loop.Run → assert: MinIO
object present + decodes to N rows; archive_state row; partition DROPped. Then
restore: decode the object → row count + a sample row match. On foundation-dev
(PG :55432 + MinIO :59000). Bootstrap `scripts/archive-worker-live-smoke.sh`.

### 4.7 CI: db-smoke + MinIO service + archive live-smoke.

## 5. Risks / follow-ups
- ATTACH-to-staging RowSource (lock-avoidance for hot partitions) NOT needed at
  V1 (only past-cutoff immutable partitions) — note if hot-archive ever needed.
- per-reality partition pre-creation (partition manager) is a separate concern.

## 6. Exit gate
archive-worker build+vet+test green · write+restore live-smoke on foundation-dev
· CI wired · DEFERRED 056+057 ADDRESSED · SESSION_PATCH.
