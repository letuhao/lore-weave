// services/archive-worker — L2.J archive worker service.
//
// Cold-path: per-reality cron driver. For each per-reality DB:
//   1. discover oldest monthly events_p_YYYY_MM partition past archive_cutoff
//   2. ATTACH it to a staging table (lock-minimization vs naive COPY)
//   3. write Parquet+ZSTD blob via pkg/parquet_writer
//   4. upload to MinIO bucket `lw-event-archive` at
//      `events/<reality_id>/<YYYY>-<MM>.parquet`
//   5. verify-after-upload (read back header + row-count footer)
//   6. DROP staging table (DROP-the-partition is now safe)
//   7. record archive_state row (idempotency guard for re-runs)
//
// V1 ships as a SKELETON: cmd/archive-worker/main.go validates config +
// prints banner + exits. Real wiring (pgx ATTACH/DROP, real Parquet via
// parquet-go, real S3 client via minio-go) lands in cycle 11/L4 alongside
// the publisher's live-wiring (D-PUBLISHER-LIVE-WIRING row 054).
//
// LOCKED Q-L2J-1: archive-worker is a DEDICATED service (mirrors publisher
// pattern; clear ops boundary).
// LOCKED Q-L2K-1: archive-worker and retention-worker are SEPARATE binaries.
//
// `pkg/` over `internal/` so tests/integration can import.

module github.com/loreweave/foundation/services/archive-worker

go 1.22

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
)

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle
