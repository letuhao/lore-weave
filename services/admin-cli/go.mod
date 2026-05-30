module github.com/loreweave/foundation/services/admin-cli

go 1.22

require github.com/loreweave/foundation/contracts/adminjwt v0.0.0

require github.com/golang-jwt/jwt/v5 v5.2.1 // indirect

replace github.com/loreweave/foundation/contracts/adminjwt => ../../contracts/adminjwt
