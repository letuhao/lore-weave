# Runbook: Degraded-mode recovery

**Owning chunk:** L1.J.7 / SR06-D5 / C03 §12O.8
**RTO target:** Limited→Full within 30s of primary recovery (RTO derived from L1.E meta failover RTO).

## When this fires

Alerts that page on:

- `LimitedModeSustained` — any service has been in `ServiceMode=Limited` for > 60s
- `FallbackBufferFillRate` — `lw_meta_fallback_buffer_size` rate of growth > 100/s sustained 30s
- `FallbackBufferDropOnFull` — `lw_meta_fallback_buffer_dropped_on_full_total` increased (writes lost)

## Architecture refresher

- **`contracts/meta/fallback.go::FallbackBuffer`** — per-process in-memory write buffer; hard cap 10K (`DefaultBufferCap`); FIFO drain.
- **`contracts/lifecycle/service_mode.go::ServiceMode`** — 5-state enum: Full → Limited → Essentials → ReadOnly → Offline.
- **`contracts/lifecycle/mode_propagation.go`** — Redis pubsub on `lw:dependency:control` (shared with cache Redis per Q-L1J-1).

### Shared-Redis-channel risk (Q-L1J-1 documented risk)

The control channel `lw:dependency:control` lives on the SAME Redis cluster as the cache (cycle 5 `infra/redis/redis.conf`). If Redis itself dies:

1. Subscribers stop receiving mode shifts.
2. Each service falls back to local health-check polling (every service runs a `/meta/health` poll at 10s interval).
3. Mode propagation degrades from ~1s to ~10s.
4. The cache also dies (same Redis), so services should ALREADY be in Limited on cache miss.

If you see `RedisUnreachable` alert AND `LimitedModeSustained` simultaneously: this is the documented compound failure. Follow:

1. Recover Redis (see `runbooks/redis/recovery.md` — pending L7 cycle 33).
2. After Redis is back, run `chaos-engine run mode_propagation_probe` to force each service to publish its current mode.

## Recovery procedure

### Step 1: Confirm scope

```bash
# Which services are in Limited?
curl -s prometheus:9090/api/v1/query?query=lw_service_mode==1 | jq '.data.result[].metric.service'
```

### Step 2: Confirm root cause is meta (vs cache vs network)

```bash
# Is meta primary responsive?
psql "$LW_META_PRIMARY_URL" -c "SELECT 1" || echo "meta primary DOWN"

# Is cache up?
redis-cli -h $LW_REDIS_HOST PING
```

If meta is the problem: jump to Step 3. If cache is the problem: this runbook is wrong — go to `runbooks/redis/recovery.md`.

### Step 3: Restore meta primary

Follow `runbooks/meta/failover.md` to confirm Patroni has elected a new leader (it should auto-failover within 30s of primary death). If Patroni failed to failover, follow `runbooks/meta/pitr_restore.md`.

### Step 4: Confirm mode propagation

```bash
# Force a mode probe — every subscriber should reply with mode_shift carrying its current mode.
chaos-engine run mode_propagation_probe   # ships cycle 22
```

Each service should publish a `mode_shift` message carrying its OWN current mode. Watch for any service still announcing `to_mode=limited` 5s after primary is healthy — that service may have a stuck health-check + needs manual restart.

### Step 5: Verify buffer flush

```bash
# Per-service flush metric should tick up
curl -s prometheus:9090/api/v1/query?query=increase(lw_meta_fallback_buffer_flush_succeeded_total[1m])
```

Expected: every service that buffered writes during the outage now reports a positive `flush_succeeded` count. CAS-conflict entries are NOT counted as success; they are counted in `flush_conflicts_total` and are NOT re-buffered (intentional — the conflict resolves toward the winning writer).

### Step 6: Validate degraded-write integrity

If `DroppedOnFull > 0` during the outage, customer writes were LOST:

1. Identify affected requests by request_id in `meta_write_audit` (compare buffered intent IDs vs successful audit row IDs).
2. Surface a per-customer status to comms (statuspage).
3. Open an INCIDENT (`incidents` table, SEV1 if > 1000 lost writes, SEV2 otherwise).

## Common pitfalls

- **Watch the canary-mode bypass.** Services may be deployed with `FallbackBuffer.cap=0` (canary fail-fast); they NEVER buffer. Those services surfaced 500s during the outage and that's expected.
- **`AcceptsFreshAckRequired() == false` in any mode except Full.** Admin commands that need fresh ack (R9 close confirmations) MUST be deferred during Limited+. If admin-cli is happily accepting a close confirmation while a service is in Limited, that's a contracts/admin-cli bug.
- **Mode shift races on flap.** If meta is flapping (up/down 3+ times in 60s), debounce shifts at 5s in each service's mode subscriber. The flap itself is a separate incident.

## Chaos drill validation

`chaos/drills/meta_outage.yaml` is the canonical drill — it exercises this entire path automatically. Drill failure pages SRE.
