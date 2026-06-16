# Capacity Progression — V1 → V3

> **L1.L.1** — Documented capacity progression + transition triggers per R04 §12D.9-10, I17/SR08 §12AK, S5-D5.

## Tiers

| Tier | Realities | Concurrent users | Shards | Replicas / service (typical) |
|---|---|---|---|---|
| **V0** | 1–10 | 1–10 | 1 docker-compose | 1 |
| **V1** | 10–100 | 100–500 | 1 docker-compose | 1–2 |
| **V1+30d** | 100–500 | 500–2K | 1–2 K8s | 2–4 |
| **V2** | 500–1K | 2K–10K | 2–4 K8s + autoscale | 2–8 |
| **V3** | 1K–10K | 10K–100K | 4+ K8s + multi-AZ | 4–32 |

## Transition triggers

A transition from V<n> → V<n+1> happens when ANY of the following triggers fires, sustained for at least 7 days:

### V1 → V1+30d
- Active reality count > 50
- p95 request latency > SLO threshold sustained
- Any single shard at > 80% capacity (per `scripts/capacity-thresholds.yaml`)

### V1+30d → V2
- Active reality count > 250
- Single-shard topology hitting `full_pct` (95%) more than once per week
- `lw_meta_routing_cache_miss_rate > 5%` (V2 cache topology change)

### V2 → V3
- Active reality count > 800
- Cross-AZ latency adds > 50ms (V3 multi-AZ becomes load-bearing)
- Backup window > 4h (V3 splits backup cluster)

## Per-tier infra deltas

| Component | V1 | V1+30d | V2 | V3 |
|---|---|---|---|---|
| Postgres meta | docker-compose 1+1+1 | EKS Patroni 1+1+1 | EKS Patroni 1+2+2 | EKS Patroni 1+2+2 (multi-AZ) |
| Postgres shards | 1 | 1 | 2-4 | 4+ multi-AZ |
| Redis (cache + control channel) | docker single | EKS Sentinel quorum=3 | per-AZ Sentinel | per-AZ Sentinel + cross-AZ replication |
| MinIO | docker single | EKS distributed | EKS distributed | multi-AZ |
| Prometheus | docker single | EKS HA pair | EKS HA pair + Thanos | Thanos + multi-region read |
| Backup tier | 7/14/30d MinIO | 7/14/30d MinIO + cross-region replica | + glacier deep-archive 2y | + multi-region glacier |

## Capacity-override flow (S5-D5 Tier 2)

When a transition trigger fires but the team hasn't yet rolled the new tier, SRE can grant a **24h capacity override** via:

```bash
admin-cli capacity-override --shard <host> --reason "<text>" --hours 24
```

This:

1. Writes `scaling_events.event_type='override'` with `override_expires_at = now() + 24h`.
2. Loosens the `full_pct` threshold for that shard for 24h.
3. Logs to `admin_action_audit` with command_version=v1 + actor.
4. Auto-expires — capacity-planner re-checks the override row at allocation time; rows past `override_expires_at` are inert.

**Override CANNOT be granted for > 24h.** A second override IS allowed (chained) but each requires a fresh reason. The DB CHECK constraint enforces the 24h cap.

## SLO budget link

Capacity decisions are driven by SLO budgets (cycle 34 `slo-budget-calculator`):
- Burn rate > 2x for 1h → consider scale-up
- Burn rate > 10x for 5m → page on-call AND auto-scale-up (V2+)
