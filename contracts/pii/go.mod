module github.com/loreweave/foundation/contracts/pii

go 1.22

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/meta v0.0.0
)

require gopkg.in/yaml.v3 v3.0.1 // indirect

replace github.com/loreweave/foundation/contracts/meta => ../meta
