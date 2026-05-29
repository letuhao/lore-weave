// services/publisher — L2.D outbox publisher service.
//
// Cold-path: polls each per-reality DB's events_outbox table for unpublished
// rows, XADDs them to Redis Streams, marks published (or dead-letters after
// max_attempts). V1 single-replica per shard host (Q-L2D-1); ships a no-op
// leader-election skeleton (Q-L2-5) that V2+ wires to Redis SETNX.
//
// Per-tree module — same pattern as cycle 6's migration-orchestrator.
// `pkg/` over `internal/` so the integration tests in `tests/integration/`
// can import the implementation. (Go's `internal/` packages are not
// importable across modules.)

module github.com/loreweave/foundation/services/publisher

go 1.22

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
)

replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle
