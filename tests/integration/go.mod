// `tests/integration/` — cross-service Go integration tests.
//
// Per-tree module (matches the monorepo's per-service go.mod pattern). Cycle 1
// shipped `meta_failover_test.go` but no go.mod, so the file wasn't actually
// buildable. Cycle 2 ships this go.mod as the carryforward fix.
//
// Each test file lives behind a `//go:build integration` tag so `go test ./...`
// in this module is a no-op in environments without docker; CI gates that
// require the live stack run `go test -tags=integration ./...`.

module github.com/loreweave/foundation/tests/integration

go 1.22

require github.com/lib/pq v1.10.9
