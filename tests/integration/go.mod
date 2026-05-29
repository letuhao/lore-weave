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
// Cycle 6 (L1.D.8) adds the migration-orchestrator dep via local replace —
// the monorepo doesn't publish modules so every cross-module import in
// tests/integration uses a `replace` to the on-disk path.

module github.com/loreweave/foundation/tests/integration

go 1.22

require (
	github.com/lib/pq v1.10.9

	// Cycle 6 — migration_run_test imports runner / canary / manifest
	github.com/loreweave/foundation/services/migration-orchestrator v0.0.0
)

require gopkg.in/yaml.v3 v3.0.1 // indirect

replace github.com/loreweave/foundation/services/migration-orchestrator => ../../services/migration-orchestrator
