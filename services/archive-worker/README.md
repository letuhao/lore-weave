# archive-worker (L2.J)

Per-reality cron worker that **archives old `events_p_YYYY_MM` partitions** to
MinIO as Parquet+ZSTD blobs, then **drops** the partition from Postgres.

Cycle 11 V1 ships as a SKELETON — pure-Go libraries with abstract IO interfaces
(`PartitionPicker`, `ObjectStore`, `ParquetWriter`, `StateStore`). Production
wiring (pgx ATTACH/DROP + parquet-go + minio-go) is **deferred** to cycle
11/L4 — see `D-PUBLISHER-LIVE-WIRING` (row 054) for the same shape applied to
the publisher.

## Why a dedicated service (Q-L2J-1)?

- Different ops cadence: daily archive run vs publisher's per-second poll.
- Different failure recovery: a missed archive run is recoverable next day;
  a missed publisher tick is a backlog alarm.
- Different alert SLOs: archive RTO is hours; publisher RTO is seconds.

## Why separate from retention-worker (Q-L2K-1)?

- archive-worker touches the `events` table only (DETACH + DROP partition).
- retention-worker touches `events_outbox` + `event_audit` + future
  `aggregate_snapshots` — NEVER `events` (would race archive-worker).
- Independent alert SLOs, independent scale-up triggers.

## Idempotency

- `archive_state` table records `(reality_id, partition_name, archived_at,
  object_key, byte_size, row_count)` per archived partition.
- Re-running archive-worker on a partition that already has an
  `archive_state` row exits clean (no-op upload, no DROP — partition is
  already gone). Picker filters them out.

## Restore CLI

`cmd/archive-restore/` reads back the Parquet blob and decodes into a
temp table for ad-hoc forensic query. V1 ships a skeleton; production
restore workflow is `runbooks/archive/restore.md`.

## Heartbeats

archive-worker reuses cycle-2's `publisher_heartbeats` table, namespaced
by `publisher_id = "archive-worker-<replica>"`. This keeps observability
on a single surface (vs introducing `archive_worker_heartbeats`). Documented
in DESIGN: "single observability surface, no schema sprawl".
