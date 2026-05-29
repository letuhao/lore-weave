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

go 1.22

require (
	github.com/google/uuid v1.6.0
	github.com/loreweave/foundation/contracts/lifecycle v0.0.0
)

replace github.com/loreweave/foundation/contracts/lifecycle => ../../contracts/lifecycle
