# Runbook — publisher lag

**Scope:** the L2.D outbox publisher service. V1 single replica per shard
host (Q-L2D-1); ships a no-op leader-election skeleton (Q-L2-5).

**SLO thresholds (R06 §12F.3):**

| Threshold | Action |
|---|---|
| `outbox_lag > 10s` | WARN — Slack `#data-platform` notification |
| `outbox_lag > 60s` | PAGE — primary on-call SRE |
| `outbox_lag > 300s` | DEGRADED — page secondary + post status page banner |

`outbox_lag_seconds` = `now() - min(enqueued_at) WHERE published=FALSE AND
dead_lettered_at IS NULL`. Emitted as `lw_outbox_lag_seconds` (gauge per
shard_host).

## Triage steps

1. **Identify shard.** Open the Grafana dashboard "Publisher lag" and pick
   the shard whose `lw_outbox_lag_seconds` is over threshold.
2. **Check publisher liveness.** Query meta:
   ```sql
   SELECT publisher_id, status, last_heartbeat_at
     FROM publisher_heartbeats
    WHERE shard_host = '<shard>'
    ORDER BY last_heartbeat_at DESC;
   ```
   - If `last_heartbeat_at` > 30s ago → publisher pod is stuck or crashed.
     Run `kubectl -n lw-foundation logs deploy/publisher --since=5m` and
     look for panics. Restart the pod (`kubectl rollout restart
     deploy/publisher`) if the loop is wedged.
   - If `status = 'dead'` → meta-worker already marked the publisher dead.
     V1: investigate why the pod stopped heartbeating (OOM? deadlock?).
     V2+: leader election should have failed over; if not, page the
     RedisLeader path owner.
3. **Check Redis Streams reachability.** From inside the cluster:
   ```sh
   kubectl exec -it deploy/publisher -- redis-cli -h "$LW_REDIS_ADDR" XINFO STREAM "lw.events.<reality_id>"
   ```
   If Redis is unreachable, follow the redis-sentinel runbook.
4. **Check Postgres pool exhaustion.** `pgbouncer_pool_waiting_clients` on
   the publisher's pool. If > 0 and rising → bump pool size or investigate
   downstream slow query.

## Dead-letter triage

When `lw_outbox_dead_lettered_total` increments, an outbox row exhausted
`max_attempts` (default 10). Triage steps:

1. **List the dead-lettered rows for a shard:**
   ```sql
   SELECT event_id, reality_id, attempts, last_error, last_attempt_at,
          dead_lettered_at
     FROM events_outbox
    WHERE dead_lettered_at IS NOT NULL
    ORDER BY dead_lettered_at DESC
    LIMIT 50;
   ```
2. **Classify:**
   - **Schema violation on the Redis side** (e.g. message too large) →
     fix payload at the source service, then admin-cli `re-enqueue
     <event_id>` (cycle 36).
   - **Persistent Redis outage** → un-dead-letter once Redis recovers
     (admin-cli; sets `dead_lettered_at = NULL, attempts = 0`).
   - **Genuinely poisoned event** (corrupt payload) → DO NOT re-enqueue.
     Log to incident, escalate to platform team.

## Degraded mode propagation

If the publisher's heartbeat writer fails 3 times consecutively, the
publisher self-flips to `ServiceMode = Limited` (L1.J) and PAUSES the
poll loop until the heartbeat recovers. This is intentional — running
the poll loop without a heartbeat means meta-worker can't tell us apart
from a dead publisher, and V2+ failover would split-brain. Triage same
as step 2 above: investigate why meta writes are failing.

## V2+ multi-replica activation

When realities > 1000 (Q-L2D-1):
1. Bump `replicas` in this manifest.
2. Swap `leader_election.NewNoOp()` → `leader_election.NewRedisLeader(...)`
   in `cmd/publisher/main.go`.
3. Bump capacity budget in `contracts/capacity/budgets.yaml`.
4. Re-run the failover integration test (`tests/integration/publisher_failover_test.go`).
