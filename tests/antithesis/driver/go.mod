// S11 (Technique H2) — Antithesis-readiness test driver.
//
// The "test template" entrypoint Antithesis would drive: it emits a workload
// through the spine and asserts DELIVERY-CONVERGENCE (publisher drains
// outbox->Redis with no-loss) + C3, wrapped in antithesis-sdk-go assertions.
// Those assertions are NO-OPS outside the Antithesis environment, so the driver
// is locally runnable (it still drives the cycle and exits 0/1) — see README.md.
//
// Isolated module (own go.mod), like tests/perf and tests/conformance.
module loreweave.dev/antithesis-driver

go 1.25

require (
	github.com/antithesishq/antithesis-sdk-go v0.4.4
	github.com/lib/pq v1.10.9
	github.com/redis/go-redis/v9 v9.7.0
)

require (
	github.com/cespare/xxhash/v2 v2.2.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
)
