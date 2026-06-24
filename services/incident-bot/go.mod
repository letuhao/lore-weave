module github.com/loreweave/foundation/services/incident-bot

go 1.22

require (
	github.com/loreweave/foundation/contracts/incidents v0.0.0
	github.com/redis/go-redis/v9 v9.7.3
	gopkg.in/yaml.v3 v3.0.1
)

require (
	github.com/cespare/xxhash/v2 v2.2.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
)

// Monorepo local replace (no published modules).
replace github.com/loreweave/foundation/contracts/incidents => ../../contracts/incidents
