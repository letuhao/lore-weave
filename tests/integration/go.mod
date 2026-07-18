// `tests/integration/` — cross-service Go integration tests.
//
// Per-tree module (matches the monorepo's per-service go.mod pattern). Cycle 1
// shipped `meta_failover_test.go` but no go.mod, so the file wasn't actually
// buildable. Cycle 2 ships this go.mod as the carryforward fix.
//
// Each test file lives behind a `//go:build integration` tag so `go test ./...`
// in this module is a no-op in environments without docker; CI gates that
// require the live stack run `go test -tags=integration ./...`.
//
// Cycle 6 (L1.D.8) added migration-orchestrator via local replace.
// Cycle 7 (L1.J / L1.H / L1.L) adds contracts/meta + contracts/lifecycle +
// backup-scheduler + admin-cli for the new degraded_mode / tiered_backup /
// capacity_override integration tests.

module github.com/loreweave/foundation/tests/integration

go 1.25.0

require (
	github.com/lib/pq v1.12.3

	// Cycle 10 — outbox_atomicity_test + xreality_propagation_test
	github.com/loreweave/foundation/contracts/events v0.0.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0

	// Cycle 7 — degraded-mode / tiered-backup / capacity-override tests
	github.com/loreweave/foundation/contracts/meta v0.0.0

	// Cycle 15 — integrity_drift_test + full_integrity_test (L3.E + L3.F)
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
	github.com/loreweave/foundation/services/admin-cli v0.0.0

	// Cycle 11 — archive_roundtrip_test + outbox_prune_test
	github.com/loreweave/foundation/services/archive-worker v0.0.0
	github.com/loreweave/foundation/services/backup-scheduler v0.0.0
	github.com/loreweave/foundation/services/meta-worker v0.0.0

	// Cycle 6 — migration_run_test imports runner / canary / manifest
	github.com/loreweave/foundation/services/migration-orchestrator v0.0.0
	github.com/loreweave/foundation/services/publisher v0.0.0
	github.com/loreweave/foundation/services/retention-worker v0.0.0
)

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/canon/timeline v0.0.0-00010101000000-000000000000

	// Cycle 30 — L6.F + L6.G admission runtimes
	github.com/loreweave/foundation/contracts/capacity v0.0.0

	// Cycle 37 — L7.D incident_flow_test + L7.L statuspage_test
	github.com/loreweave/foundation/contracts/incidents v0.0.0
	github.com/loreweave/foundation/contracts/observability v0.0.0
	github.com/loreweave/foundation/infra/k8s/admission-webhook v0.0.0
	github.com/loreweave/foundation/pkg/metrics v0.0.0

	// Cycle 38 — L7.K canary_advance_test + deploy_freeze_test
	github.com/loreweave/foundation/services/canary-controller v0.0.0
	github.com/loreweave/foundation/services/incident-bot v0.0.0
	github.com/loreweave/foundation/services/postmortem-bot v0.0.0
	github.com/loreweave/foundation/services/statuspage-updater v0.0.0
	gopkg.in/yaml.v3 v3.0.1
)

require (
	github.com/jackc/pgx/v5 v5.10.0
	github.com/redis/go-redis/v9 v9.21.0
)

// 144 D-INTEGRATION-TEST-BUILD-RED: admin_cli_test.go → admin-cli/pkg/cliapi →
// internal/auth pulls contracts/adminjwt transitively; it needs a local replace
// like every other monorepo dep (was missing → the -tags=integration build
// could not resolve adminjwt from a clean checkout).
require github.com/loreweave/foundation/contracts/adminjwt v0.0.0 // indirect

require (
	github.com/andybalholm/brotli v1.1.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/golang-jwt/jwt/v5 v5.3.1 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/klauspost/compress v1.18.6 // indirect
	github.com/klauspost/cpuid/v2 v2.2.11 // indirect
	github.com/klauspost/crc32 v1.3.0 // indirect
	github.com/minio/crc64nvme v1.1.1 // indirect
	github.com/minio/md5-simd v1.1.2 // indirect
	github.com/minio/minio-go/v7 v7.2.1 // indirect
	github.com/parquet-go/bitpack v1.0.0 // indirect
	github.com/parquet-go/jsonlite v1.0.0 // indirect
	github.com/parquet-go/parquet-go v0.30.1 // indirect
	github.com/philhofer/fwd v1.2.0 // indirect
	github.com/pierrec/lz4/v4 v4.1.21 // indirect
	github.com/rogpeppe/go-internal v1.15.0 // indirect
	github.com/rs/xid v1.6.0 // indirect
	github.com/tinylib/msgp v1.6.1 // indirect
	github.com/twpayne/go-geom v1.6.1 // indirect
	github.com/zeebo/xxh3 v1.1.0 // indirect
	go.uber.org/atomic v1.11.0 // indirect
	go.yaml.in/yaml/v3 v3.0.4 // indirect
	golang.org/x/crypto v0.51.0 // indirect
	golang.org/x/net v0.53.0 // indirect
	golang.org/x/sync v0.22.0 // indirect
	golang.org/x/sys v0.44.0 // indirect
	golang.org/x/text v0.40.0 // indirect
	google.golang.org/protobuf v1.36.10 // indirect
	gopkg.in/ini.v1 v1.67.2 // indirect
)

replace github.com/loreweave/foundation/services/migration-orchestrator => ../../services/migration-orchestrator

// Cycle 7 — local replaces for new dependencies (monorepo pattern; no modules published).
replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

replace github.com/loreweave/foundation/services/backup-scheduler => ../../services/backup-scheduler

replace github.com/loreweave/foundation/services/admin-cli => ../../services/admin-cli

// 144: admin-cli/pkg/cliapi transitively needs adminjwt (auth verify) + the
// audit_emitter chain (metapg / pii / piikms / metaoutbox). Mirror ALL of
// admin-cli's local foundation replaces — Go does NOT inherit a dependency's
// replace directives, so every monorepo module admin-cli pulls needs its own
// local replace here too (was missing → -tags=integration build unresolvable).
replace github.com/loreweave/foundation/contracts/adminjwt => ../../contracts/adminjwt

replace github.com/loreweave/foundation/sdks/go/metapg => ../../sdks/go/metapg

replace github.com/loreweave/foundation/contracts/pii => ../../contracts/pii

replace github.com/loreweave/foundation/sdks/go/piikms => ../../sdks/go/piikms

replace github.com/loreweave/foundation/sdks/go/metaoutbox => ../../sdks/go/metaoutbox

// Cycle 10 — outbox + publisher + meta-worker
replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

// 086 D-REALITYREG-SHARED: realityreg promoted out of publisher to contracts/.
replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg

replace github.com/loreweave/foundation/services/publisher => ../../services/publisher

replace github.com/loreweave/foundation/services/meta-worker => ../../services/meta-worker

// Cycle 11 — archive + retention workers
replace github.com/loreweave/foundation/services/archive-worker => ../../services/archive-worker

replace github.com/loreweave/foundation/services/retention-worker => ../../services/retention-worker

// Cycle 15 — integrity-checker
replace github.com/loreweave/foundation/services/integrity-checker => ../../services/integrity-checker

// Cycle 27 — L5.J change-history timeline contract
replace github.com/loreweave/foundation/contracts/canon/timeline => ../../contracts/canon/timeline

// Cycle 30 — L6.F observability admission lib + L6.G K8s capacity admission webhook
replace github.com/loreweave/foundation/contracts/observability => ../../contracts/observability

replace github.com/loreweave/foundation/contracts/capacity => ../../contracts/capacity

replace github.com/loreweave/foundation/pkg/metrics => ../../pkg/metrics

replace github.com/loreweave/foundation/infra/k8s/admission-webhook => ../../infra/k8s/admission-webhook

// Cycle 37 — L7.D incident-bot + postmortem-bot + L7.L statuspage-updater + shared incidents contract
replace github.com/loreweave/foundation/contracts/incidents => ../../contracts/incidents

replace github.com/loreweave/foundation/services/incident-bot => ../../services/incident-bot

replace github.com/loreweave/foundation/services/postmortem-bot => ../../services/postmortem-bot

replace github.com/loreweave/foundation/services/statuspage-updater => ../../services/statuspage-updater

// Cycle 38 — L7.K canary-controller (canary_advance_test + cohort_router contract)
replace github.com/loreweave/foundation/services/canary-controller => ../../services/canary-controller
