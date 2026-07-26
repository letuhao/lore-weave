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

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
	github.com/minio/minio-go/v7 v7.2.1
	github.com/parquet-go/parquet-go v0.30.1
	github.com/prometheus/client_golang v1.24.0
)

require (
	github.com/andybalholm/brotli v1.1.1 // indirect
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/klauspost/compress v1.19.0 // indirect
	github.com/klauspost/cpuid/v2 v2.2.11 // indirect
	github.com/klauspost/crc32 v1.3.0 // indirect
	github.com/kr/text v0.2.0 // indirect
	github.com/minio/crc64nvme v1.1.1 // indirect
	github.com/minio/md5-simd v1.1.2 // indirect
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/parquet-go/bitpack v1.0.0 // indirect
	github.com/parquet-go/jsonlite v1.0.0 // indirect
	github.com/philhofer/fwd v1.2.0 // indirect
	github.com/pierrec/lz4/v4 v4.1.21 // indirect
	github.com/prometheus/client_model v0.6.2 // indirect
	github.com/prometheus/common v0.70.0 // indirect
	github.com/prometheus/procfs v0.21.1 // indirect
	github.com/rs/xid v1.6.0 // indirect
	github.com/tinylib/msgp v1.6.1 // indirect
	github.com/twpayne/go-geom v1.6.1 // indirect
	github.com/zeebo/xxh3 v1.1.0 // indirect
	go.yaml.in/yaml/v3 v3.0.4 // indirect
	golang.org/x/crypto v0.53.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/sync v0.22.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
	golang.org/x/text v0.40.0 // indirect
	google.golang.org/protobuf v1.36.11 // indirect
	gopkg.in/ini.v1 v1.67.2 // indirect
)

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

// P1 #20: reuse the shared reality_registry client + DSN resolver for the
// per-reality pool wiring. Promoted to contracts/ (D-REALITYREG-SHARED, row
// 086) — no longer a cross-import of the publisher service.
replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg
