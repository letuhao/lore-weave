module github.com/loreweave/foundation/services/statuspage-updater

go 1.22

require (
	github.com/loreweave/foundation/contracts/incidents v0.0.0
	gopkg.in/yaml.v3 v3.0.1
)

// Monorepo local replace — consumes the shared incidents contract DPS 1 owns.
replace github.com/loreweave/foundation/contracts/incidents => ../../contracts/incidents
