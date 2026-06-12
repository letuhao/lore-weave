# Runbook: Meta Postgres Failover

> **Artifact:** L1.E.9 (RAID cycle 1, L1.E Meta HA Infrastructure)
> **Owning chunk:** C03 §12O.3
> **Audience:** SRE on-call
> **Severity profile:** P0 (meta DB primary unreachable)
> **RTO target:** 30 seconds

## When to invoke

Use FAILOVER when the meta Postgres **primary is unreachable** AND the sync
replica is healthy. Patroni normally promotes automatically on primary death;
this runbook covers:

1. **Manual switchover** (zero-downtime maintenance — e.g., primary AMI patch)
2. **Failover diagnosis** when Patroni's automatic promotion seems stuck

Do NOT use this runbook when:
- Both primary and sync replica are down → use `pitr_restore.md` (read-only
  service via async replica may still be possible)
- Logical corruption (bad data on primary AND replica) → use `pitr_restore.md`
- Primary is just slow → check `pg_stat_activity` first; failover should not
  be the first response to a slow primary

## Prerequisites

- SRE on-call has Bastion access to a Patroni-aware node (`patronictl` installed)
- `etcd` cluster is healthy (quorum 2/3 reachable — see `etcd-cluster.tf`)
- Sync replica lag < 1 MiB (`maximum_lag_on_failover` in `patroni.yml`)

## Procedure

### Step 0 — Sanity check (~10s)

```bash
patronictl -c /etc/patroni/patroni.yml list
```

Expected output:

```
+ Cluster: lw-meta-pg (...) +-----------+----+-----------+
| Member          | Host      | Role    | State     | TL | Lag in MB |
+-----------------+-----------+---------+-----------+----+-----------+
| primary         | 10.0.1.10 | Leader  | running   |  3 |           |
| sync_replica_a  | 10.0.1.11 | Replica | streaming |  3 |         0 |
| async_replica_0 | 10.0.1.12 | Replica | streaming |  3 |         2 |
+-----------------+-----------+---------+-----------+----+-----------+
```

**If sync_replica_a lag > 1 MiB:** STOP. Wait for lag to drop or accept data
loss risk. Patroni's `maximum_lag_on_failover` will block automatic failover.

**If etcd unhealthy:** STOP. Recover etcd first (`etcdctl endpoint health`).
Patroni cannot promote without a quorate DCS.

### Step 1 — Switchover (planned maintenance, ~30s)

```bash
patronictl -c /etc/patroni/patroni.yml switchover \
  --master primary --candidate sync_replica_a \
  --scheduled now
```

Patroni:
1. Checkpoints primary
2. Promotes `sync_replica_a` to leader
3. Demotes old primary to replica (will sync from new leader)
4. Updates etcd leader lock

**Target wall clock: < 30s.** If > 60s, investigate `patronictl history` and
the Patroni log for the slow step.

### Step 2 — Failover (primary actually down, ~30s auto + verification)

If Patroni auto-promotion fired:

```bash
# Verify the new leader
patronictl -c /etc/patroni/patroni.yml list

# Verify writes flow through new leader
psql -h <new-leader-host> -c "INSERT INTO _lw_meta_health (ts) VALUES (now()) RETURNING id;"
```

If Patroni did NOT auto-promote (e.g., manual `synchronous_mode_strict` block):

```bash
# Force promote sync_replica_a
patronictl -c /etc/patroni/patroni.yml failover --candidate sync_replica_a
```

Forced failover bypasses `maximum_lag_on_failover` — only use when you accept
the data-loss risk implied by current lag.

### Step 3 — Service mode (L1.J)

During the failover window meta is BRIEFLY unwritable. Services should:

- Buffer writes in `contracts/meta/fallback.go` (L1.B.3, ships cycle 2)
- Emit `ServiceMode=Limited` to `lw:dependency:control` Redis channel (L1.J)
- Flush buffer when meta returns + ack the recovery (L1.J.6 acceptance test)

If services are NOT yet integrated with L1.J (early L1 cycles), expect 30s of
meta-write errors. Frontend/API gateway should return 503 retryable.

### Step 4 — Post-failover validation (~5 min)

```bash
# All replicas should follow the new leader
patronictl -c /etc/patroni/patroni.yml list
# All members State=running; lag stabilizes within 60s

# Verify WAL archive resumed from new leader
ls -lt /var/lib/postgresql/archive_status | head    # on new leader
# Should show recent WAL segments as .done (shipped to lw-meta-wal-archive)

# Verify sync replication on new leader
psql -c "SELECT application_name, sync_state FROM pg_stat_replication;"
# Should show sync_replica_a (now the original primary, demoted) as 'sync'
```

### Step 5 — Patch old primary + return to service

After patching the original primary's underlying issue:

```bash
# On old primary host
systemctl start patroni                       # rejoins as replica
patronictl -c /etc/patroni/patroni.yml list   # confirm "running" "streaming"
```

If you want to swap roles back (return original primary to leader):

```bash
patronictl -c /etc/patroni/patroni.yml switchover \
  --master sync_replica_a --candidate primary --scheduled now
```

## Failure modes + escalation

| Symptom | Likely cause | Action |
|---|---|---|
| `patronictl list` hangs | etcd unhealthy | Recover etcd; consult etcd runbook |
| Promotion takes > 60s | Replica lag during promote | Check WAL replay rate; bigger volume IOPS |
| New leader rejects writes | `synchronous_standby_names` no quorum | Promote another replica or accept temporary degraded mode |
| Split-brain (2 leaders) | etcd lost quorum mid-failover | STOP all meta writes; consult ENG immediately |

## RPO / RTO

| Metric | Target | Notes |
|---|---|---|
| RTO (planned switchover) | 30s | Per L1.E acceptance |
| RTO (automatic failover) | 30s | Bounded by `loop_wait + ttl` in patroni.yml |
| RPO (sync replica) | 0s | `synchronous_commit=on` invariant |
| RPO (failover with lag) | ≤ 1 MiB of WAL | `maximum_lag_on_failover` enforces |

## Cross-references

- Patroni config: `infra/patroni/patroni.yml`
- etcd cluster: `infra/etcd/etcd-cluster.tf`
- Postgres base config: `infra/postgres/postgresql.conf`
- PITR (for data corruption, not failover): `runbooks/meta/pitr_restore.md`
- Chaos drill: `chaos/drills/meta_failover.yaml`
- Integration test: `tests/integration/meta_failover_test.go`
- LOCKED Qs: Q-L1E-1 (cross-region V3+), Q-L1E-2 (etcd self-hosted)
