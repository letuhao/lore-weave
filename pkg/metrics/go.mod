module github.com/loreweave/foundation/pkg/metrics

go 1.22

require github.com/loreweave/foundation/contracts/observability v0.0.0

require gopkg.in/yaml.v3 v3.0.1 // indirect

replace github.com/loreweave/foundation/contracts/observability => ../../contracts/observability
