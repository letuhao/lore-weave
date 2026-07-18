// services/meta-outbox-relay — P2/101 slice B.
//
// Drains the meta DB's meta_outbox table (written by MetaWrite's
// sdks/go/metaoutbox appender, migration 030) to Redis Streams: the home
// stream lw.meta.events + an xreality.* bridge for cross-reality events.
//
// Per-tree module (same pattern as services/publisher). It REUSES
// services/publisher/pkg/retry (a stdlib-only, generic backoff/dead-letter
// policy) so the relay's drain semantics match the spine's exactly.

module github.com/loreweave/foundation/services/meta-outbox-relay

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/services/publisher v0.0.0
	github.com/prometheus/client_golang v1.23.2
	github.com/redis/go-redis/v9 v9.21.0
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
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

replace github.com/loreweave/foundation/services/publisher => ../publisher

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

replace github.com/loreweave/foundation/contracts/events => ../../contracts/events
