module github.com/loreweave/foundation/tests/workload-gen

go 1.24

require (
	github.com/google/uuid v1.6.0
	github.com/lib/pq v1.12.3
	github.com/loreweave/foundation/contracts/events v0.0.0
)

require gopkg.in/yaml.v3 v3.0.1 // indirect

// Monorepo pattern: no modules are published; cross-module deps use a local
// replace (mirrors tests/integration/go.mod). Reusing events.Envelope +
// events.OutboxWrite keeps the generator's wire shape + outbox write byte-
// identical to production (no drift).
replace github.com/loreweave/foundation/contracts/events => ../../contracts/events
