module github.com/loreweave/foundation/services/migration-orchestrator

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/contracts/meta v0.0.0
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
	github.com/loreweave/foundation/sdks/go/metapg v0.0.0
	gopkg.in/yaml.v3 v3.0.1
)

require (
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	golang.org/x/sync v0.17.0 // indirect
	golang.org/x/text v0.29.0 // indirect
)

// W1.2 (production wiring) — the migrate CLI binds to real collaborators:
// contracts/meta MetaWrite (audit + state, I8), contracts/realityreg (DSN
// resolver + fleet), sdks/go/metapg (pgxpool→meta.DB), via pgx.
replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta

replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg

replace github.com/loreweave/foundation/sdks/go/metapg => ../../sdks/go/metapg
