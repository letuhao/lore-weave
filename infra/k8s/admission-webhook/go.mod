module github.com/loreweave/foundation/infra/k8s/admission-webhook

go 1.22

require github.com/loreweave/foundation/contracts/capacity v0.0.0

require gopkg.in/yaml.v3 v3.0.1 // indirect

replace github.com/loreweave/foundation/contracts/capacity => ../../../contracts/capacity
