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

go 1.22

require (
	github.com/lib/pq v1.10.9

	// Cycle 10 — outbox_atomicity_test + xreality_propagation_test
	github.com/loreweave/foundation/contracts/events v0.0.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0

	// Cycle 7 — degraded-mode / tiered-backup / capacity-override tests
	github.com/loreweave/foundation/contracts/meta v0.0.0
	github.com/loreweave/foundation/services/admin-cli v0.0.0

	// Cycle 11 — archive_roundtrip_test + outbox_prune_test
	github.com/loreweave/foundation/services/archive-worker v0.0.0
	github.com/loreweave/foundation/services/backup-scheduler v0.0.0

	// Cycle 15 — integrity_drift_test + full_integrity_test (L3.E + L3.F)
	github.com/loreweave/foundation/services/integrity-checker v0.0.0
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
	github.com/loreweave/foundation/contracts/observability v0.0.0
	github.com/loreweave/foundation/infra/k8s/admission-webhook v0.0.0
	github.com/loreweave/foundation/pkg/metrics v0.0.0
	gopkg.in/yaml.v3 v3.0.1

	// Cycle 37 — L7.L statuspage_test (statuspage-updater + shared contract)
	github.com/loreweave/foundation/contracts/incidents v0.0.0
	github.com/loreweave/foundation/services/statuspage-updater v0.0.0
)

replace github.com/loreweave/foundation/services/migration-orchestrator => ../../services/migration-orchestrator

// Cycle 7 — local replaces for new dependencies (monorepo pattern; no modules published).
replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

replace github.com/loreweave/foundation/services/backup-scheduler => ../../services/backup-scheduler

replace github.com/loreweave/foundation/services/admin-cli => ../../services/admin-cli

// Cycle 10 — outbox + publisher + meta-worker
replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

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

// Cycle 37 — L7.L statuspage-updater + shared incidents contract
replace github.com/loreweave/foundation/contracts/incidents => ../../contracts/incidents

replace github.com/loreweave/foundation/services/statuspage-updater => ../../services/statuspage-updater
