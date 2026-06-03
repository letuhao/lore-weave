// contracts/realityreg — the shared reality_registry client + shard-host→DSN
// resolver for per-reality pool wiring.
//
// Promoted out of services/publisher/pkg/realityreg (D-REALITYREG-SHARED, row
// 086): publisher, meta-worker, retention-worker and archive-worker all need
// the same ActiveRealities() query + DSNConfig resolver, so it lives in
// contracts/ as a peer dependency — no service depends on another service.
module github.com/loreweave/foundation/contracts/realityreg

go 1.24

require github.com/jackc/pgx/v5 v5.6.0

require (
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20221227161230-091c0ba34f0a // indirect
	golang.org/x/crypto v0.17.0 // indirect
	golang.org/x/text v0.28.0 // indirect
)
