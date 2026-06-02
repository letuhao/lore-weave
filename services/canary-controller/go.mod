module github.com/loreweave/foundation/services/canary-controller

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.9.2
	github.com/loreweave/foundation/contracts/meta v0.0.0
	github.com/loreweave/foundation/sdks/go/metapg v0.0.0
	github.com/prometheus/client_golang v1.19.0
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.2.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/prometheus/client_model v0.5.0 // indirect
	github.com/prometheus/common v0.48.0 // indirect
	github.com/prometheus/procfs v0.12.0 // indirect
	golang.org/x/sync v0.17.0 // indirect
	golang.org/x/sys v0.16.0 // indirect
	golang.org/x/text v0.29.0 // indirect
	google.golang.org/protobuf v1.32.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta

replace github.com/loreweave/foundation/sdks/go/metapg => ../../sdks/go/metapg
