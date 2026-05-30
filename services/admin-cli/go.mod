module github.com/loreweave/foundation/services/admin-cli

go 1.22

require (
	github.com/golang-jwt/jwt/v5 v5.2.1
	github.com/loreweave/foundation/contracts/adminjwt v0.0.0
	github.com/loreweave/foundation/contracts/meta v0.0.0
)

require (
	github.com/google/uuid v1.6.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

replace github.com/loreweave/foundation/contracts/adminjwt => ../../contracts/adminjwt

replace github.com/loreweave/foundation/contracts/meta => ../../contracts/meta
