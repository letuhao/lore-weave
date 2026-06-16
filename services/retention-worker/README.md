# retention-worker (L2.K)

Per-reality cron worker that **enforces R1-L3 retention rules** across the
ephemeral / append-only tables of each per-reality DB. SEPARATE binary
from archive-worker (Q-L2K-1).

## Scope

| Table              | Action                                                    | Driver                       |
|--------------------|-----------------------------------------------------------|------------------------------|
| `events_outbox`    | DELETE published rows older than 24h (addresses D-OUTBOX-PRUNE) | `pkg/outbox_pruner`          |
| `event_audit`      | Per-class retention (30d non-flagged / 90d flagged)       | wraps `scripts/event-audit-retention-cron.sh` |
| `aggregate_snapshots` | placeholder (no-op V1; L3 lands cycle 12+)             | `pkg/snapshot_pruner`        |

## NOT in scope

- **`events`** — managed by archive-worker (DETACH partition → archive → DROP).
  A retention-worker DELETE on `events` would race the archive-worker. The
  ACL matrix entry MUST NOT grant the `events` table any permission.
- **`events_outbox` dead-letter rows** — handled per
  `runbooks/publisher/lag.md` triage workflow (SRE review). The pruner
  filters `dead_lettered_at IS NULL`.

## Cadence

Hourly. Compare with archive-worker's daily cadence:

- Retention is fast (DELETEs of ephemeral rows; bounded by LIMIT 10000).
- A delayed retention run is a soft signal — outbox grows; the next run
  catches up.
- A delayed archive run is harder — `events` partitions stay attached
  longer, growing DB size; daily cadence is more conservative.

## Heartbeats

Reuses cycle-2's `publisher_heartbeats` table, namespaced by
`publisher_id = "retention-worker-<replica>"`. Same single-observability-surface
decision as archive-worker.
