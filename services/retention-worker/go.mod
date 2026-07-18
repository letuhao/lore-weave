// services/retention-worker — L2.K retention worker service.
//
// Cold-path: per-reality cron driver. Enforces R1-L3 retention rules:
//
//   1. events_outbox — DELETE rows where published=TRUE AND last_attempt_at
//      < NOW() - 24h. NEVER touches dead_lettered rows (per
//      runbooks/publisher/lag.md — those need SRE review). This addresses
//      D-OUTBOX-PRUNE deferred row 055.
//   2. event_audit — wraps existing scripts/event-audit-retention-cron.sh
//      (already shipped cycle 9). Per-class retention (30d non-flagged /
//      90d flagged) per R01 §12A.3.
//   3. aggregate_snapshots — placeholder for L3 retention; no-op V1
//      (L3 lands cycle 12+).
//
// LOCKED Q-L2K-1: retention-worker and archive-worker are SEPARATE binaries
// (different ops cadence: retention hourly / archive daily; different alert
// SLOs).
//
// CRITICAL INVARIANT: retention-worker NEVER touches the `events` table.
// `events` rows are managed by archive-worker (DETACH partition → archive →
// DROP partition). A retention-worker DELETE on `events` would race the
// archive-worker — code-review rejects any change that adds an `events`
// permission to this service's ACL.

module github.com/loreweave/foundation/services/retention-worker

go 1.25.0

require (
	github.com/google/uuid v1.6.0
	github.com/jackc/pgx/v5 v5.10.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
	github.com/loreweave/foundation/contracts/realityreg v0.0.0
	github.com/prometheus/client_golang v1.23.2
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	github.com/kr/text v0.2.0 // indirect
	github.com/munnerz/goautoneg v0.0.0-20191010083416-a7dc8b61c822 // indirect
	github.com/prometheus/client_model v0.6.2 // indirect
	github.com/prometheus/common v0.66.1 // indirect
	github.com/prometheus/procfs v0.16.1 // indirect
	go.yaml.in/yaml/v2 v2.4.2 // indirect
	golang.org/x/sync v0.17.0 // indirect
	golang.org/x/sys v0.35.0 // indirect
	golang.org/x/text v0.29.0 // indirect
	google.golang.org/protobuf v1.36.8 // indirect
)

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle

// P1 retention-worker: reuse the shared reality_registry client + DSN resolver.
// Promoted to contracts/ (D-REALITYREG-SHARED, row 086) — no longer a
// cross-import of the publisher service.
replace github.com/loreweave/foundation/contracts/realityreg => ../../contracts/realityreg
