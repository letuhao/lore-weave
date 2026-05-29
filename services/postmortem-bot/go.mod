module github.com/loreweave/foundation/services/postmortem-bot

go 1.22

require (
	github.com/loreweave/foundation/contracts/incidents v0.0.0
	gopkg.in/yaml.v3 v3.0.1
)

replace github.com/loreweave/foundation/contracts/incidents => ../../contracts/incidents
