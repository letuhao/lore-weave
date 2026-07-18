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

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
	github.com/prometheus/client_golang v1.23.2
	github.com/redis/go-redis/v9 v9.21.0
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/kr/text v0.2.0 // indirect
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.2 // indirect
	github.com/prometheus/common v0.66.1 // indirect
	github.com/prometheus/procfs v0.16.1 // indirect
	go.uber.org/atomic v1.11.0 // indirect
	go.yaml.in/yaml/v2 v2.4.2 // indirect
	golang.org/x/sync v0.17.0 // indirect
	golang.org/x/sys v0.35.0 // indirect
	golang.org/x/text v0.29.0 // indirect
	google.golang.org/protobuf v1.36.8 // indirect
)

replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg
