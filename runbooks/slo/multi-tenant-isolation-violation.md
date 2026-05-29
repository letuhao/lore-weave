# Runbook — Multi-Tenant Isolation Violation (Noisy Neighbor)

**Owner:** SRE on-call · **Severity:** SEV2 (escalates if cross-reality SLI impact confirmed) · **Layer:** L7.I.8 / L7.I.12 (RAID cycle 34)

## When this fires

`LWMultiTenantIsolationViolation` alert from `infra/prometheus/alerts/slo-burn.yaml`.

Fires when:

```
lw_reality_resource_usage_ratio{resource=<resource>} > 0.10
AND
stddev_over_time(...[1h]) > 3 × stddev_over_time(...[24h])
```

Translation: a single reality is using > 10% of a shared resource (Postgres conn pool, Redis memory, LLM spend outside premium) AND the usage shows a 3σ anomaly vs its 24h baseline.

Per SR1 §12AD.5 this is NOT auto-PAGE — could be legitimate popular reality. Route is Slack `#alerts` for SRE investigation.

## Quick triage (5 min)

1. From the alert, note `reality_id` and `resource`.
2. Open `per-reality-health` dashboard, filter by `reality_id`.
3. Cross-check the platform SLI for *another* reality. If SLI ≠ baseline → cross-reality impact CONFIRMED, escalate to SEV1.
4. If no other reality is affected → likely organic spike (popular content launch); document + monitor.

## Investigation tree

```
Resource usage spike?
├── pgbouncer conn pool (§12D.4)
│   ├── check pgbouncer logs for connection reject
│   ├── check per-reality conn limit cfg
│   └── action: temporarily raise per-reality limit; long-term: investigate query bursts
├── Redis stream MAXLEN (§12F.6)
│   ├── check XLEN of affected streams
│   ├── compare vs MAXLEN trim threshold
│   └── action: review stream usage; consider per-reality consumer groups
├── LLM budget (§12V.3)
│   ├── check provider-registry tokens used
│   ├── check per-session cost cap config
│   └── action: throttle non-premium tier in affected reality
└── per-user queue (§12W)
    ├── check user job-queue depth
    └── action: enforce per-user queue cap; identify abuser
```

## Mitigation menu

1. **Throttle the offending reality.** `admin-cli reality throttle <reality_id> --resource <resource> --duration 1h`
2. **Increase shared resource cap.** Short-term: bump the per-reality limit. Long-term: requires capacity planning.
3. **Cross-reality protection.** If other realities are degrading, force-isolate via per-reality circuit breaker (cycle 19 L4.F).
4. **Cost cap.** For LLM-spend cases, lower the per-session cap for affected tier.

## Confirmation that mitigation worked

- [ ] `lw_reality_resource_usage_ratio{reality_id=<id>}` drops below 10% within 15 min
- [ ] Cross-reality SLIs (sli_session_availability, sli_turn_completion, sli_event_delivery) return to baseline
- [ ] 3σ stddev anomaly clears for ≥ 1h

## Cross-references

- SR1 §12AD.5 — Multi-tenant isolation SLO
- L1.J — circuit-breaker patterns (cycle 7)
- L4.F — resilience contract (cycle 19)
- SR2 §12AE.4 — alert routing table

last_verified: 2026-05-29
verification_method: cycle-34-build
