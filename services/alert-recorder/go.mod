module github.com/loreweave/alert-recorder

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/alerts v0.1.0
)

replace github.com/loreweave/foundation/contracts/alerts => ../../contracts/alerts
