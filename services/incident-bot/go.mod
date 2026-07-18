module github.com/loreweave/foundation/services/incident-bot

go 1.24

require (
	github.com/loreweave/foundation/contracts/incidents v0.0.0
	github.com/redis/go-redis/v9 v9.21.0
	gopkg.in/yaml.v3 v3.0.1
)

require (
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	go.uber.org/atomic v1.11.0 // indirect
)

// Monorepo local replace (no published modules).
replace github.com/loreweave/foundation/contracts/incidents => ../../contracts/incidents
