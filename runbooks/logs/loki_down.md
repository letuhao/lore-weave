# Runbook — Loki Down

> **Trigger:** Grafana datasource `loki-primary` returns 5xx; `up{job="loki"}` = 0 in Prometheus for ≥ 5 minutes; SRE pager.
> **Severity:** SEV2 (operator visibility — degrades incident response, does NOT degrade user-facing flow).
> **Last verified:** 2026-05-29 (cycle 33 ship).
> **Verification method:** stub (full DR drill ships V1+30d per Q-L7B-1 V1 stub policy).

## Quick triage (≤ 2 min)

1. **Is the container running?**
   ```bash
   docker compose -f infra/docker-compose.observability.yml ps loki
   ```
   If "Exited" → step 2; if "Up" → step 3.

2. **Container exited — last 100 log lines:**
   ```bash
   docker compose -f infra/docker-compose.observability.yml logs --tail=100 loki
   ```
   Common causes:
     * `failed to acquire lock on /loki/chunks/` — stale lock file. Remove `/loki/chunks/.lock`. Restart.
     * `out of disk` — Loki chunks volume full. Check `df -h` on host; if dev, prune `docker volume rm` of old chunks. If prod, escalate to capacity backlog (D-LOKI-S3-TERRAFORM ).
     * `schema config error` — someone changed `loki-distributed.yaml schema_config`. Revert + redeploy.

3. **Container Up but unhealthy — check internal health:**
   ```bash
   docker compose -f infra/docker-compose.observability.yml exec loki wget -qO- http://localhost:3100/ready
   ```
   * `ready` → Loki is fine, problem is downstream (Grafana proxy? Vector push failing?). Go to step 4.
   * `Ingester not ready` → Loki is starting; wait 60s, recheck. If still not ready after 5 min, restart.
   * Connection refused → process dead despite "Up". Restart container.

4. **Downstream check — Vector push pipeline:**
   ```bash
   docker compose -f infra/docker-compose.observability.yml exec vector \
     curl -s http://localhost:9598/metrics | grep -E 'vector_(events_in|events_out|component_errors)'
   ```
   * `vector_component_errors_total{component_type="loki"} > 0` rising → Loki is rejecting pushes (rate limit? schema mismatch?). Check Loki logs.
   * Errors zero, events flowing → Vector→Loki is fine. Grafana datasource problem; check `grafana` container logs.

## Mitigation paths

| Scenario | Mitigation | Rollback condition |
|---|---|---|
| Disk full, dev/staging | `docker volume rm foundation-mega-task_loki-chunks` (loses all log history) | n/a — dev only |
| Disk full, prod | Trigger S3 archival sweep early via `infra/loki/compactor` manual run | n/a |
| Lock file stale after crash | Remove `/loki/chunks/.lock`, restart container | If Loki refuses to start after lock removal → restore from `/loki/chunks-backup-*` snapshot |
| Schema drift | `git checkout HEAD -- infra/loki/loki-distributed.yaml`, redeploy | Revert succeeds → done; if config file is downstream of an in-flight migration, escalate to platform on-call |
| Loki OOM | Increase container memory limit in docker-compose.observability.yml; investigate cardinality (Vector `service` label drift?) | Memory headroom restored → done |

## Service mode impact

Loki down ≠ degraded mode (L1.J ModeLimited). Logging is OPERATOR-visible
infrastructure, not USER-facing. Services continue normal operation; the
cycle-32 logger writes locally to `/var/log/lw/<service>.log` (file source
for Vector) which Vector queues + replays on Loki recovery.

If logs are visibly missing from Grafana for > 30 min:
  * Confirm Vector buffer (`vector_buffer_*` metrics) is not full
  * If buffer full → Vector will start dropping (back-pressure to source).
    This is a SEV1 (silent log loss).

## Recovery verification

```bash
# Push a synthetic log line via Vector
docker compose -f infra/docker-compose.observability.yml exec vector \
  sh -c 'echo "{\"message\":\"runbook-loki-down recovery test\",\"service\":\"runbook-canary\"}" >> /var/log/lw/canary.log'

# Wait 10s, then query Loki
sleep 10
docker compose -f infra/docker-compose.observability.yml exec loki \
  wget -qO- 'http://localhost:3100/loki/api/v1/query?query={service="runbook-canary"}'
```

Expected: JSON response containing the synthetic message.

## Escalation

* > 30 min outage → SEV1
* > 2 hour outage + active incident in progress (no log visibility for incident response) → SEV0
* Confirmed silent log loss → SEV0 (compliance: PII handling visibility)

## Linked items

* `Q-L7F-1` — Loki self-hosted V1 (no managed fallback)
* `D-LOKI-S3-TERRAFORM` — production S3 plant
* `D-DEGRADED-LIVE-SMOKE` — cleared cycle 33
* Cycle 33 `infra/loki/loki-distributed.yaml` — config
* Cycle 32 `contracts/logging/logger.go` — source-side logging lib

## Audit footer

| Field | Value |
|---|---|
| Last verified | 2026-05-29 (cycle 33 commit) |
| Verification method | stub (full DR drill ships V1+30d per Q-L7B-1) |
| Owner | platform / SRE |
