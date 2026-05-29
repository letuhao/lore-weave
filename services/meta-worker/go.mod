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

go 1.22

replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

require github.com/google/uuid v1.6.0 // indirect
