# SRE Runbook Index — auto-generated

> **Generated:** 2026-05-30  
> **Generator:** `scripts/runbook-index-generator.sh`  
> **Total runbooks:** 27  
> **Stubs (Q-L7B-1):** 27  
> **Overdue verification:** 27

## Alert → Runbook (3am fast lookup)

| Alert | Runbook(s) |
|---|---|
| `LWAdminBreakGlassRequested` | [`admin/break-glass.md`](admin/break-glass.md) |
| `LWAdminCommandFailureSpike` | [`admin/command-failure-investigation.md`](admin/command-failure-investigation.md) |
| `LWAuthBreakGlassRequested` | [`auth/break-glass-initiation.md`](auth/break-glass-initiation.md) |
| `LWAuthHashMismatch` | [`meta/write-audit-hash-mismatch.md`](meta/write-audit-hash-mismatch.md) |
| `LWAuthJwtExpiredSpike` | [`auth/jwt-expiration-spike.md`](auth/jwt-expiration-spike.md) |
| `LWAuthTokenFlowBroken` | [`auth/token-flow-broken.md`](auth/token-flow-broken.md) |
| `LWCanonInjectionDetected` | [`canon/injection-detected.md`](canon/injection-detected.md) |
| `LWCanonPropagationLatencyHigh` | [`canon/propagation-latency-high.md`](canon/propagation-latency-high.md) |
| `LWCapacityDeployBudgetBreach` | [`capacity/budget-breach-at-deploy.md`](capacity/budget-breach-at-deploy.md) |
| `LWCapacityShardNearFull` | [`capacity/shard-near-full.md`](capacity/shard-near-full.md) |
| `LWDeployCanaryBudgetBurn` | [`deploy/canary-abort.md`](deploy/canary-abort.md) |
| `LWDeployRollbackTriggered` | [`deploy/rollback-execution.md`](deploy/rollback-execution.md) |
| `LWLLMProviderCostAnomaly` | [`llm-provider/cost-anomaly.md`](llm-provider/cost-anomaly.md) |
| `LWLLMProviderOutagePrimary` | [`llm-provider/outage-primary.md`](llm-provider/outage-primary.md) |
| `LWLLMProviderRateLimitSpike` | [`llm-provider/rate-limit-degradation.md`](llm-provider/rate-limit-degradation.md) |
| `LWMetaPostgresPrimaryDown` | [`meta/failover-to-standby.md`](meta/failover-to-standby.md) |
| `LWMetaReplicaLagHigh` | [`meta/read-lag-investigation.md`](meta/read-lag-investigation.md) |
| `LWProjectionDriftDetected` | [`projection/drift-detected.md`](projection/drift-detected.md) |
| `LWProjectionRebuildRequired` | [`projection/rebuild-catastrophic.md`](projection/rebuild-catastrophic.md) |
| `LWPublisherDLQNonEmpty` | [`publisher/dead-letter-queue-review.md`](publisher/dead-letter-queue-review.md) |
| `LWPublisherLagSpike` | [`publisher/lag-spike.md`](publisher/lag-spike.md) |
| `LWRealityArchiveVerificationFailed` | [`reality/archive-verification-failed.md`](reality/archive-verification-failed.md) |
| `LWRealityLifecycleCorruption` | [`reality/lifecycle-corruption.md`](reality/lifecycle-corruption.md) |
| `LWRealityProvisioningStuck` | [`reality/provisioning-stuck.md`](reality/provisioning-stuck.md) |
| `LWWsAuthzRejectionSpike` | [`ws/refresh-failures.md`](ws/refresh-failures.md) |
| `LWWsConnectionSaturation` | [`ws/connection-saturation.md`](ws/connection-saturation.md) |
| `LWWsHandshakeFailureSpike` | [`ws/refresh-failures.md`](ws/refresh-failures.md) |
| `LWWsMassDisconnect` | [`ws/mass-disconnect.md`](ws/mass-disconnect.md) |

## Service → Runbooks

| Service | Runbook(s) |
|---|---|
| `api-gateway-bff` | [`admin/command-failure-investigation.md`](admin/command-failure-investigation.md), [`auth/token-flow-broken.md`](auth/token-flow-broken.md), [`deploy/canary-abort.md`](deploy/canary-abort.md), [`deploy/rollback-execution.md`](deploy/rollback-execution.md), [`ws/connection-saturation.md`](ws/connection-saturation.md), [`ws/mass-disconnect.md`](ws/mass-disconnect.md), [`ws/refresh-failures.md`](ws/refresh-failures.md) |
| `auth-service` | [`admin/break-glass.md`](admin/break-glass.md), [`auth/break-glass-initiation.md`](auth/break-glass-initiation.md), [`auth/jwt-expiration-spike.md`](auth/jwt-expiration-spike.md), [`auth/token-flow-broken.md`](auth/token-flow-broken.md), [`ws/refresh-failures.md`](ws/refresh-failures.md) |
| `chat-service` | [`llm-provider/outage-primary.md`](llm-provider/outage-primary.md), [`llm-provider/rate-limit-degradation.md`](llm-provider/rate-limit-degradation.md) |
| `meta-postgres` | [`admin/break-glass.md`](admin/break-glass.md), [`admin/command-failure-investigation.md`](admin/command-failure-investigation.md), [`capacity/shard-near-full.md`](capacity/shard-near-full.md), [`meta/failover-to-standby.md`](meta/failover-to-standby.md), [`meta/read-lag-investigation.md`](meta/read-lag-investigation.md), [`meta/write-audit-hash-mismatch.md`](meta/write-audit-hash-mismatch.md), [`reality/archive-verification-failed.md`](reality/archive-verification-failed.md), [`reality/lifecycle-corruption.md`](reality/lifecycle-corruption.md), [`reality/provisioning-stuck.md`](reality/provisioning-stuck.md) |
| `projection-runner` | [`projection/drift-detected.md`](projection/drift-detected.md), [`projection/rebuild-catastrophic.md`](projection/rebuild-catastrophic.md) |
| `publisher` | [`canon/propagation-latency-high.md`](canon/propagation-latency-high.md), [`publisher/dead-letter-queue-review.md`](publisher/dead-letter-queue-review.md), [`publisher/lag-spike.md`](publisher/lag-spike.md) |
| `translation-service` | [`llm-provider/outage-primary.md`](llm-provider/outage-primary.md) |
| `usage-billing-service` | [`capacity/budget-breach-at-deploy.md`](capacity/budget-breach-at-deploy.md), [`llm-provider/cost-anomaly.md`](llm-provider/cost-anomaly.md) |
| `world-service` | [`canon/injection-detected.md`](canon/injection-detected.md), [`canon/propagation-latency-high.md`](canon/propagation-latency-high.md), [`reality/lifecycle-corruption.md`](reality/lifecycle-corruption.md), [`reality/provisioning-stuck.md`](reality/provisioning-stuck.md) |

## Alphabetical

| Runbook | Owner | Last verified | Method |
|---|---|---|---|
| [`admin/break-glass.md`](admin/break-glass.md) | sre-team | 1970-01-01 | stub |
| [`admin/command-failure-investigation.md`](admin/command-failure-investigation.md) | sre-team | 1970-01-01 | stub |
| [`auth/break-glass-initiation.md`](auth/break-glass-initiation.md) | sre-team | 1970-01-01 | stub |
| [`auth/jwt-expiration-spike.md`](auth/jwt-expiration-spike.md) | sre-team | 1970-01-01 | stub |
| [`auth/token-flow-broken.md`](auth/token-flow-broken.md) | sre-team | 1970-01-01 | stub |
| [`canon/injection-detected.md`](canon/injection-detected.md) | sre-team | 1970-01-01 | stub |
| [`canon/propagation-latency-high.md`](canon/propagation-latency-high.md) | sre-team | 1970-01-01 | stub |
| [`capacity/budget-breach-at-deploy.md`](capacity/budget-breach-at-deploy.md) | sre-team | 1970-01-01 | stub |
| [`capacity/shard-near-full.md`](capacity/shard-near-full.md) | sre-team | 1970-01-01 | stub |
| [`deploy/canary-abort.md`](deploy/canary-abort.md) | sre-team | 1970-01-01 | stub |
| [`deploy/rollback-execution.md`](deploy/rollback-execution.md) | sre-team | 1970-01-01 | stub |
| [`llm-provider/cost-anomaly.md`](llm-provider/cost-anomaly.md) | sre-team | 1970-01-01 | stub |
| [`llm-provider/outage-primary.md`](llm-provider/outage-primary.md) | sre-team | 1970-01-01 | stub |
| [`llm-provider/rate-limit-degradation.md`](llm-provider/rate-limit-degradation.md) | sre-team | 1970-01-01 | stub |
| [`meta/failover-to-standby.md`](meta/failover-to-standby.md) | sre-team | 1970-01-01 | stub |
| [`meta/read-lag-investigation.md`](meta/read-lag-investigation.md) | sre-team | 1970-01-01 | stub |
| [`meta/write-audit-hash-mismatch.md`](meta/write-audit-hash-mismatch.md) | sre-team | 1970-01-01 | stub |
| [`projection/drift-detected.md`](projection/drift-detected.md) | sre-team | 1970-01-01 | stub |
| [`projection/rebuild-catastrophic.md`](projection/rebuild-catastrophic.md) | sre-team | 1970-01-01 | stub |
| [`publisher/dead-letter-queue-review.md`](publisher/dead-letter-queue-review.md) | sre-team | 1970-01-01 | stub |
| [`publisher/lag-spike.md`](publisher/lag-spike.md) | sre-team | 1970-01-01 | stub |
| [`reality/archive-verification-failed.md`](reality/archive-verification-failed.md) | sre-team | 1970-01-01 | stub |
| [`reality/lifecycle-corruption.md`](reality/lifecycle-corruption.md) | sre-team | 1970-01-01 | stub |
| [`reality/provisioning-stuck.md`](reality/provisioning-stuck.md) | sre-team | 1970-01-01 | stub |
| [`ws/connection-saturation.md`](ws/connection-saturation.md) | sre-team | 1970-01-01 | stub |
| [`ws/mass-disconnect.md`](ws/mass-disconnect.md) | sre-team | 1970-01-01 | stub |
| [`ws/refresh-failures.md`](ws/refresh-failures.md) | sre-team | 1970-01-01 | stub |

## Overdue verification

| Runbook | Due |
|---|---|
| [`admin/break-glass.md`](admin/break-glass.md) | 1970-04-01 |
| [`admin/command-failure-investigation.md`](admin/command-failure-investigation.md) | 1970-04-01 |
| [`auth/break-glass-initiation.md`](auth/break-glass-initiation.md) | 1970-04-01 |
| [`auth/jwt-expiration-spike.md`](auth/jwt-expiration-spike.md) | 1970-04-01 |
| [`auth/token-flow-broken.md`](auth/token-flow-broken.md) | 1970-04-01 |
| [`canon/injection-detected.md`](canon/injection-detected.md) | 1970-04-01 |
| [`canon/propagation-latency-high.md`](canon/propagation-latency-high.md) | 1970-04-01 |
| [`capacity/budget-breach-at-deploy.md`](capacity/budget-breach-at-deploy.md) | 1970-04-01 |
| [`capacity/shard-near-full.md`](capacity/shard-near-full.md) | 1970-04-01 |
| [`deploy/canary-abort.md`](deploy/canary-abort.md) | 1970-04-01 |
| [`deploy/rollback-execution.md`](deploy/rollback-execution.md) | 1970-04-01 |
| [`llm-provider/cost-anomaly.md`](llm-provider/cost-anomaly.md) | 1970-04-01 |
| [`llm-provider/outage-primary.md`](llm-provider/outage-primary.md) | 1970-04-01 |
| [`llm-provider/rate-limit-degradation.md`](llm-provider/rate-limit-degradation.md) | 1970-04-01 |
| [`meta/failover-to-standby.md`](meta/failover-to-standby.md) | 1970-04-01 |
| [`meta/read-lag-investigation.md`](meta/read-lag-investigation.md) | 1970-04-01 |
| [`meta/write-audit-hash-mismatch.md`](meta/write-audit-hash-mismatch.md) | 1970-04-01 |
| [`projection/drift-detected.md`](projection/drift-detected.md) | 1970-04-01 |
| [`projection/rebuild-catastrophic.md`](projection/rebuild-catastrophic.md) | 1970-04-01 |
| [`publisher/dead-letter-queue-review.md`](publisher/dead-letter-queue-review.md) | 1970-04-01 |
| [`publisher/lag-spike.md`](publisher/lag-spike.md) | 1970-04-01 |
| [`reality/archive-verification-failed.md`](reality/archive-verification-failed.md) | 1970-04-01 |
| [`reality/lifecycle-corruption.md`](reality/lifecycle-corruption.md) | 1970-04-01 |
| [`reality/provisioning-stuck.md`](reality/provisioning-stuck.md) | 1970-04-01 |
| [`ws/connection-saturation.md`](ws/connection-saturation.md) | 1970-04-01 |
| [`ws/mass-disconnect.md`](ws/mass-disconnect.md) | 1970-04-01 |
| [`ws/refresh-failures.md`](ws/refresh-failures.md) | 1970-04-01 |

## Stubs (Q-L7B-1 placeholders)

- [`admin/break-glass.md`](admin/break-glass.md)
- [`admin/command-failure-investigation.md`](admin/command-failure-investigation.md)
- [`auth/break-glass-initiation.md`](auth/break-glass-initiation.md)
- [`auth/jwt-expiration-spike.md`](auth/jwt-expiration-spike.md)
- [`auth/token-flow-broken.md`](auth/token-flow-broken.md)
- [`canon/injection-detected.md`](canon/injection-detected.md)
- [`canon/propagation-latency-high.md`](canon/propagation-latency-high.md)
- [`capacity/budget-breach-at-deploy.md`](capacity/budget-breach-at-deploy.md)
- [`capacity/shard-near-full.md`](capacity/shard-near-full.md)
- [`deploy/canary-abort.md`](deploy/canary-abort.md)
- [`deploy/rollback-execution.md`](deploy/rollback-execution.md)
- [`llm-provider/cost-anomaly.md`](llm-provider/cost-anomaly.md)
- [`llm-provider/outage-primary.md`](llm-provider/outage-primary.md)
- [`llm-provider/rate-limit-degradation.md`](llm-provider/rate-limit-degradation.md)
- [`meta/failover-to-standby.md`](meta/failover-to-standby.md)
- [`meta/read-lag-investigation.md`](meta/read-lag-investigation.md)
- [`meta/write-audit-hash-mismatch.md`](meta/write-audit-hash-mismatch.md)
- [`projection/drift-detected.md`](projection/drift-detected.md)
- [`projection/rebuild-catastrophic.md`](projection/rebuild-catastrophic.md)
- [`publisher/dead-letter-queue-review.md`](publisher/dead-letter-queue-review.md)
- [`publisher/lag-spike.md`](publisher/lag-spike.md)
- [`reality/archive-verification-failed.md`](reality/archive-verification-failed.md)
- [`reality/lifecycle-corruption.md`](reality/lifecycle-corruption.md)
- [`reality/provisioning-stuck.md`](reality/provisioning-stuck.md)
- [`ws/connection-saturation.md`](ws/connection-saturation.md)
- [`ws/mass-disconnect.md`](ws/mass-disconnect.md)
- [`ws/refresh-failures.md`](ws/refresh-failures.md)

---

_This file is regenerated by `scripts/runbook-index-generator.sh`._
_Do not edit by hand — your changes will be overwritten._
