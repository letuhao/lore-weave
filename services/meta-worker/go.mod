// services/meta-worker — L2.L sole consumer of xreality.* Redis Streams.
//
// Per I7 invariant, NO other service consumes the xreality topics. This
// constraint is enforced by ACL (contracts/service_acl/matrix.yaml) +
// codified via the dispatch package's deliberately narrow ALLOWLIST.
//
// Pattern mirrors publisher (cycle 10) + migration-orchestrator (cycle 6):
// `pkg/` over `internal/` so the integration test can import dispatch +
// consumer directly.

module github.com/loreweave/foundation/services/meta-worker

go 1.24

replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

replace github.com/loreweave/foundation/contracts/canon/timeline => ../../contracts/canon/timeline

// P1 #18: reuse the publisher's reality_registry client + shard-host→DSN
// resolver for the per-reality pool wiring (canon_projection subscriber DBs).
// FOLLOW-UP: promote realityreg to a shared contracts/ module so both
// services depend on one source instead of meta-worker→publisher.
replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

replace github.com/loreweave/foundation/services/publisher => ../publisher

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.6.0
	github.com/loreweave/foundation/contracts/canon/timeline v0.0.0-00010101000000-000000000000
	github.com/loreweave/foundation/services/publisher v0.0.0
	github.com/prometheus/client_golang v1.23.2
	github.com/redis/go-redis/v9 v9.7.3
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20221227161230-091c0ba34f0a // indirect
	github.com/jackc/puddle/v2 v2.2.1 // indirect
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.2 // indirect
	github.com/prometheus/common v0.66.1 // indirect
	github.com/prometheus/procfs v0.16.1 // indirect
	go.yaml.in/yaml/v2 v2.4.2 // indirect
	golang.org/x/crypto v0.17.0 // indirect
	golang.org/x/sync v0.16.0 // indirect
	golang.org/x/sys v0.35.0 // indirect
	golang.org/x/text v0.28.0 // indirect
	google.golang.org/protobuf v1.36.8 // indirect
)
