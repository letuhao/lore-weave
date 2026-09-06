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

go 1.25.0

replace github.com/loreweave/foundation/contracts/events => ../../contracts/events

replace github.com/loreweave/foundation/contracts/canon/timeline => ../../contracts/canon/timeline

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

// P1 #18: reuse the shared reality_registry client + shard-host→DSN resolver
// for the per-reality pool wiring (canon_projection subscriber DBs). Promoted
// to contracts/ (D-REALITYREG-SHARED, row 086) so meta-worker no longer
// cross-imports the publisher service.
replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/contracts/canon/timeline v0.0.0-00010101000000-000000000000
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
	github.com/loreweave/foundation/sdks/go/metapg v0.0.0
	github.com/prometheus/client_golang v1.24.0
	github.com/redis/go-redis/v9 v9.21.0
)

require (
	github.com/aws/aws-sdk-go-v2 v1.42.1 // indirect
	github.com/aws/aws-sdk-go-v2/internal/configsources v1.4.30 // indirect
	github.com/aws/aws-sdk-go-v2/internal/endpoints/v2 v2.7.30 // indirect
	github.com/aws/aws-sdk-go-v2/service/kms v1.54.1 // indirect
	github.com/aws/smithy-go v1.27.3 // indirect
	go.uber.org/atomic v1.11.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/loreweave/foundation/contracts/meta v0.0.0
	github.com/loreweave/foundation/contracts/pii v0.0.0
	github.com/loreweave/foundation/sdks/go/piikms v0.0.0
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.2 // indirect
	github.com/prometheus/common v0.70.0 // indirect
	github.com/prometheus/procfs v0.21.1 // indirect
	golang.org/x/sync v0.22.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
	golang.org/x/text v0.40.0 // indirect
	google.golang.org/protobuf v1.36.11 // indirect
)

replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta

// RA1/RA3 — the cross-user read of `actor_control_binding` writes a
// `meta_read_audit` row, and the row is built from the PII SDK's shapes.
// Symmetric with `contracts/meta` above: that one is how this module writes the
// WRITE audit, these are how it writes the READ audit. Added 2026-08-21, when
// the audit turned out never to have been wired at all.
replace github.com/loreweave/foundation/contracts/pii => ../../contracts/pii

replace github.com/loreweave/foundation/sdks/go/piikms => ../../sdks/go/piikms

// Transitive: piikms' own test tree reaches metaoutbox, and `go mod tidy`
// resolves test deps too. A `replace` rather than a `require` of a published
// version, because there is no published version — this repo is the only home.
replace github.com/loreweave/foundation/sdks/go/metaoutbox => ../../sdks/go/metaoutbox

replace github.com/loreweave/foundation/sdks/go/metapg => ../../sdks/go/metapg
