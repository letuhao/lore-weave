module github.com/loreweave/foundation/services/integrity-checker

go 1.22

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
)

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle
