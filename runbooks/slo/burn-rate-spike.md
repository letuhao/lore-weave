# Runbook — SLO Burn Rate Spike

**Owner:** SRE on-call · **Severity (default):** SEV2 (escalates per ladder) · **Layer:** L7.I (RAID cycle 34)

## When this fires

The `LWSLOBurnWarn*` / `LWSLOBurnPage*` / `LWSLOBurnFreeze*` / `LWSLOBreach*` alert
family from `infra/prometheus/alerts/slo-burn.yaml`. Each alert carries:

- `sli_ref` — which SLI is burning (one of 7; see `contracts/slo/sli_definitions.yaml`)
- `tier` — free / paid / premium / platform
- `severity` — warn (Slack) or page (PagerDuty)
- `sev` — 0 (breach), 1 (freeze), unset otherwise

## Quick triage (5 min)

1. Open dashboard `slo-burn-rate` — confirm the 1h ratio is BELOW the historic baseline.
2. Check the corresponding raw metric (numerator/denominator). Pure absence of denominator events ≠ a real burn — verify the service is actually serving traffic.
3. Check `lw_obs_stack_up` — if observability infra is degraded, the 1h ratio may be artifactual.
4. Confirm at least one PR landed in the last 1h — burn that lines up with a deploy is the most common pattern.

## Per-SLI hot paths

| SLI | First-look service | Common cause |
|---|---|---|
| `sli_session_availability` | auth-service, game-server | DB conn pool exhaust; auth-service crash loop |
| `sli_turn_completion` | chat-service, world-service | LLM provider rate limit; long projection lag |
| `sli_event_delivery` | game-server (WS), publisher | WS replica saturation; outbox stuck |
| `sli_realtime_freshness` | publisher, projection-runner | Outbox lag, projection-runner restart |
| `sli_auth_success` | auth-service, provider-registry | Token signing key rotation problem; secret rotation lag |
| `sli_admin_action_success` | admin-cli, meta-worker | meta-postgres saturation; meta-worker queue stuck |
| `sli_cross_reality_propagation` | world-service, canon-service | Cross-reality fan-out stalled; canon write contention |

## Mitigation menu (act fastest first)

1. **Rollback latest deploy.** Use `scripts/deploy-canary-abort.sh` (cycle 35+) if available; else `kubectl rollout undo` per the affected service.
2. **Throttle ingress.** If turn completion is burning, lower the chat-service rate limit per `contracts/api/chat-service.yaml::rate_limit_global`.
3. **Provider failover.** For turn completion driven by LLM provider failures, route to fallback provider via `provider-registry-service` admin command.
4. **Force-mitigate.** Declare incident: `admin-cli incident declare --sli {{sli_ref}} --tier {{tier}}`. IC takes over comms.

## Burn-rate ladder responses

Burn-rate tier policy maps to PR labels (`scripts/feature-freeze-enforcer.sh`):

| Burn | Action |
|---|---|
| < 50% | Normal; no label required |
| 50–75% | Slack warning; feature PRs review at standup |
| 75–90% | PagerDuty page; PR `reliability-review-required` label mandatory |
| ≥ 90% | PagerDuty SEV1; **feature freeze**; PR `approve-reliability-override` + tech-lead approval |
| ≥ 100% | PagerDuty SEV0; **SLO breach**; postmortem MANDATORY; freeze stays until budget recovers + 24h |

## Post-mitigation checklist

- [ ] Mitigation timestamp recorded in `incidents` table (L7) via `admin-cli incident mitigate`
- [ ] Slack `#inc-<id>` channel: announce mitigation, link to dashboard
- [ ] If SEV0 or SEV1: schedule postmortem in `docs/sre/postmortems/`
- [ ] Burn rate confirmed < 50% for 24h continuous before lifting freeze
- [ ] Append SLO review entry to `docs/sre/slo-reviews/<yyyy-mm-dd>_burn-recovery.md`

## Escalation

- TTA primary 15 min → SRE secondary
- TTA secondary 15 min → tech lead
- Tech lead 30 min → founder phone (PagerDuty manager fallback per SR2 §12AE.4)

## V1 solo-dev note

V1 solo-dev mode collapses primary/secondary/tech-lead onto one person.
Same runbook; just don't skip the documented mitigation timestamp — your
future self (or first hire) reads this trail during the postmortem.

## References

- `contracts/slo/sli_definitions.yaml` — 7 SLI registry
- `contracts/slo/slo_targets.yaml` — per-tier targets + burn-rate response policy
- `infra/prometheus/alerts/slo-burn.yaml` — alert ladder source
- `infra/alertmanager/main.yaml` — routing (cycle 34 L7.J)
- `dashboards/slo-burn-rate.json` — primary burn-rate dashboard
- SR1 §12AD.4 — burn-rate 4-tier policy

last_verified: 2026-05-29
verification_method: cycle-34-build (Q-L7B-1 stub class — V1 ships full runbook here, V2+ ops review)
