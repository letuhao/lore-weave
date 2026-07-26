module github.com/loreweave/foundation/tests/conformance

go 1.24

require (
	github.com/google/uuid v1.6.0
	github.com/lib/pq v1.12.3
	github.com/loreweave/foundation/contracts/meta v0.0.0
	gopkg.in/yaml.v3 v3.0.1
)

// Monorepo: cross-module dep on the meta library via a local replace (mirrors
// tests/workload-gen). The I9 metaprobe drives the real AttemptStateTransition.
replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta
