module github.com/loreweave/loreweave_mcp

go 1.25.0

require (
	github.com/google/jsonschema-go v0.4.3
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/grantclient v0.1.0
	github.com/modelcontextprotocol/go-sdk v1.6.1
)

require (
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/segmentio/asm v1.1.3 // indirect
	github.com/segmentio/encoding v0.5.4 // indirect
	github.com/yosida95/uritemplate/v3 v3.0.2 // indirect
	golang.org/x/oauth2 v0.35.0 // indirect
	golang.org/x/sync v0.21.0 // indirect
	golang.org/x/sys v0.41.0 // indirect
	golang.org/x/text v0.39.0 // indirect
)

replace github.com/loreweave/grantclient => ../grantclient
