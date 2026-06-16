// Package dependencies holds the single source of truth for every external
// dependency the LoreWeave platform calls (LLM providers, Postgres shards,
// Redis Streams, MinIO, internal services). Owned by the platform team.
//
// Cycle 18 (L4.N) ships:
//   - matrix.yaml           — declarative registry (P0/P1/P2 deps)
//   - matrix.go             — typed Matrix + Dependency structs
//   - matrix_loader.go      — YAML loader + DAG validator (cycle detection)
//   - client_factory.go     — produces wrapped clients (timeout + breaker
//                              + retry + bulkhead per dep)
//
// The Rust mirror lives in `crates/dp-kernel::dependencies` per Q-L4-1
// (Go primary; Rust mirror). Library invariants:
//
//   - SR06 §12AI.2: every HTTP/DB/Redis client constructed in any service
//     MUST come through ClientFactory.For(depName). Raw http.NewRequest /
//     sql.Open / redis.NewClient outside this package is blocked by
//     `scripts/dependency-registry-lint.sh`.
//   - The matrix.yaml `fallback` field forms a DAG. LoadAndValidate
//     refuses to load on cycle detection (prevents unbounded failover).
//   - Adding a new dep is a PR review point (architect sign-off per
//     SR06 §12AI.2 governance) + a paired SR3 runbook entry.
package dependencies
