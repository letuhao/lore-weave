module github.com/loreweave/foundation/services/integrity-checker

go 1.24

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.6.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
)

require (
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20221227161230-091c0ba34f0a // indirect
	github.com/jackc/puddle/v2 v2.2.1 // indirect
	golang.org/x/crypto v0.17.0 // indirect
	golang.org/x/sync v0.16.0 // indirect
	golang.org/x/text v0.28.0 // indirect
)

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

// 086: shared reality_registry client + shard-host→DSN resolver (peer module).
replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg
