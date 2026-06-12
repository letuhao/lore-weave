#!/usr/bin/env python3
"""scripts/raid/generate-cycle-35-runbooks.py

One-shot generator that writes the 27 stub runbooks under
docs/sre/runbooks/ per SR03 §12AF.4 + Q-L7B-1.

Run once: python3 scripts/raid/generate-cycle-35-runbooks.py
Idempotent: re-running overwrites the stubs with the same content.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent.parent
RB_DIR = REPO / "docs" / "sre" / "runbooks"

# (rb_id, alerts, services, tldr)
RUNBOOKS = [
    # auth (3)
    ("auth/token-flow-broken", ["LWAuthTokenFlowBroken"], ["auth-service", "api-gateway-bff"],
     "Sev1 - JWT token issuance pipeline failure (all logins rejected)."),
    ("auth/jwt-expiration-spike", ["LWAuthJwtExpiredSpike"], ["auth-service"],
     "Spike in JWT-expired errors; root JWT or refresh-token may itself have expired."),
    ("auth/break-glass-initiation", ["LWAuthBreakGlassRequested"], ["auth-service"],
     "Initiate break-glass: dual-actor approval, mark incident, audit trail enforced (S12AA.L10)."),
    # ws (3)
    ("ws/refresh-failures", ["LWWsHandshakeFailureSpike", "LWWsAuthzRejectionSpike"], ["api-gateway-bff", "auth-service"],
     "WS ticket refresh fails: clock skew, slow client, frontend regression, or JWT expiry."),
    ("ws/connection-saturation", ["LWWsConnectionSaturation"], ["api-gateway-bff"],
     "WS replica connection count near pod limit - scale-out or cull idle sessions."),
    ("ws/mass-disconnect", ["LWWsMassDisconnect"], ["api-gateway-bff"],
     "Coordinated WS disconnect spike; network event, upstream auth flip, or rolling restart."),
    # meta (3)
    ("meta/failover-to-standby", ["LWMetaPostgresPrimaryDown"], ["meta-postgres"],
     "Promote standby; verify Patroni quorum + sync replica lag; legacy runbooks/meta/failover.md preserved."),
    ("meta/write-audit-hash-mismatch", ["LWAuthHashMismatch"], ["meta-postgres"],
     "Auto-SEV0 (S12X.L6): audit chain hash mismatch. STOP writes, page founder + DPO."),
    ("meta/read-lag-investigation", ["LWMetaReplicaLagHigh"], ["meta-postgres"],
     "Read replica lag > 1MiB; investigate WAL backpressure, vacuum, or replica disk."),
    # publisher (2)
    ("publisher/lag-spike", ["LWPublisherLagSpike"], ["publisher"],
     "Outbox-publisher consumer lag spike; check Redis stream depth and consumer health."),
    ("publisher/dead-letter-queue-review", ["LWPublisherDLQNonEmpty"], ["publisher"],
     "DLQ has entries - triage, classify (poison/transient), replay or quarantine."),
    # projection (2)
    ("projection/rebuild-catastrophic", ["LWProjectionRebuildRequired"], ["projection-runner"],
     "Projection corruption confirmed - coordinate read-only mode, rebuild from event log."),
    ("projection/drift-detected", ["LWProjectionDriftDetected"], ["projection-runner"],
     "Projection state diverges from event-log replay; tabletop drift class first."),
    # llm-provider (3)
    ("llm-provider/outage-primary", ["LWLLMProviderOutagePrimary"], ["chat-service", "translation-service"],
     "Primary LLM provider outage; failover to secondary via provider-registry."),
    ("llm-provider/rate-limit-degradation", ["LWLLMProviderRateLimitSpike"], ["chat-service"],
     "Sustained 429s from LLM provider; throttle/backoff or shift cohort to secondary."),
    ("llm-provider/cost-anomaly", ["LWLLMProviderCostAnomaly"], ["usage-billing-service"],
     "Spend rate exceeds budget envelope; identify caller, cap or throttle."),
    # canon (2)
    ("canon/injection-detected", ["LWCanonInjectionDetected"], ["world-service"],
     "Auto-SEV1 (S13): canon-injection signal; freeze contested canon, page security."),
    ("canon/propagation-latency-high", ["LWCanonPropagationLatencyHigh"], ["world-service", "publisher"],
     "Canon propagation past SLO; check outbox+projection chain."),
    # admin (2) — L7.B.12: break-glass + command-failure-investigation
    ("admin/break-glass", ["LWAdminBreakGlassRequested"], ["auth-service", "meta-postgres"],
     "Initiate break-glass admin flow: dual-actor approval, mark incident, audit trail enforced (S12AA.L10)."),
    ("admin/command-failure-investigation", ["LWAdminCommandFailureSpike"], ["api-gateway-bff", "meta-postgres"],
     "Admin command failure spike; isolate command class, check service ACL + RBAC, escalate to Tier1 dual-actor."),
    # reality (3) — L7.B.13: provisioning-stuck + archive-verification-failed + lifecycle-corruption
    ("reality/provisioning-stuck", ["LWRealityProvisioningStuck"], ["world-service", "meta-postgres"],
     "Reality provisioning step stuck > SLO; check provisioner queue + DB lock + LLM seed."),
    ("reality/archive-verification-failed", ["LWRealityArchiveVerificationFailed"], ["meta-postgres"],
     "Reality archive verification mismatch; STOP archival pipeline, page DPO + tech-lead."),
    ("reality/lifecycle-corruption", ["LWRealityLifecycleCorruption"], ["world-service", "meta-postgres"],
     "Reality lifecycle state machine corruption; freeze writes for affected realities, manual repair."),
    # deploy (2) — L7.B.14: canary-abort + rollback-execution
    ("deploy/canary-abort", ["LWDeployCanaryBudgetBurn"], ["api-gateway-bff"],
     "Canary cohort burn-rate breached; abort canary, restore to previous version, freeze rollout."),
    ("deploy/rollback-execution", ["LWDeployRollbackTriggered"], ["api-gateway-bff"],
     "Rollback procedure for a regressing deploy; verify DB migration safety (down-compat)."),
    # capacity (2) — L7.B.15: shard-near-full + budget-breach-at-deploy
    ("capacity/shard-near-full", ["LWCapacityShardNearFull"], ["meta-postgres"],
     "Shard storage/CPU/conn approaching saturation; activate burst capacity or migrate hot users."),
    ("capacity/budget-breach-at-deploy", ["LWCapacityDeployBudgetBreach"], ["usage-billing-service"],
     "Deploy would exceed monthly capacity budget; require waiver or downsize."),
]


TEMPLATE = """---
runbook_id: {rb_id}
version: 1
owner: sre-team
applies_to_alerts: [{alerts}]
applies_to_incidents: []
applies_to_services: [{services}]
last_verified: 1970-01-01
last_verified_by: unassigned
verification_method: stub
next_verification_due: 1970-04-01
severity_hints: [{sev_hints}]
dry_run_required_for_destructive: true
related_runbooks: []
external_access_needed: [{ext}]
born_from_incident_id: null
shipped_cycle: 35
locked_decisions_consumed: [Q-L7B-1]
---

# {title}

> **STUB - Q-L7B-1 V1 launch allowance.** This runbook is a placeholder.
> The next on-call SRE to be paged for the related alert(s) MUST upgrade
> this stub to a verified runbook before the next page. Set
> `verification_method: reading_review` and update `last_verified` to today.

## TL;DR (30 seconds)

{tldr}

## Symptoms

- Alert(s) firing: {alert_list}
- User-visible impact: TBD on first-incident upgrade
- Confirming metric/log query: TBD

## Likely Causes (ranked by frequency)

1. **TBD primary cause** - verify via TBD - fix: TBD
2. **TBD secondary cause** - verify via TBD - fix: TBD
3. **TBD edge case** - verify via TBD - fix: TBD

## Diagnostic Commands

```bash
# Placeholder - fill in on first-incident upgrade.
# Always include --dry-run first for destructive operations.
admin-cli {first_token} status --dry-run
```

## Mitigation Steps

### Quick mitigation (stop bleeding)

1. Confirm the alert is real (not flapping; check inhibition rules).
2. Apply the smallest reversible mitigation (silence is NOT a mitigation - see `runbooks/alerts/silence_misuse.md`).
3. Verify user-facing impact subsided.

### Full resolution

1. Run diagnostic commands above.
2. Identify the root cause class (use `generic/i-don-t-know-what-s-wrong.md` if unclear).
3. Apply targeted fix.
4. Verify against post-mitigation criteria.

## Rollback

If the mitigation worsens the situation, revert by:
1. Undo the most recent change.
2. Re-page the previous-on-call for context.
3. Escalate per Escalation table below.

## Escalation

| Condition | Escalate to | TTA |
|---|---|---|
| Mitigation fails after 30 min | tech-lead | 30 min |
| Multi-service blast radius | incident-bot SEV1 | 15 min |
| Data integrity suspected | founder + DPO | 5 min |

## Verification (post-mitigation)

1. Alert clears within 5 min of fix.
2. SLI ratio returns to baseline (see `dashboards/slo-burn-rate.json`).
3. No new user-facing reports for 15 min.

## Related

- `runbooks/alerts/silence_misuse.md` - silence policy boundaries
- `generic/escalation-chains.md` - fallback contacts
- `docs/governance/oncall-sla.md` - TTA targets per severity
- `docs/sre/runbooks/README.md` - library usage guide

## Upgrade checklist (for the SRE who runs this for real)

- [ ] Replace "TBD" lines with concrete diagnostic queries and fixes.
- [ ] Add expected output samples to each command.
- [ ] Verify with one other SRE (set `last_verified_by`).
- [ ] Change `verification_method: stub` -> `reading_review`.
- [ ] Bump `last_verified` to today; `next_verification_due` to today + 90d.
- [ ] If born from a real incident, set `born_from_incident_id`.
- [ ] Run `bash scripts/runbook-index-generator.sh` to refresh INDEX.md.
"""


def fmt_list(items):
    return ", ".join(items)


def sev_for(rb_id):
    if any(k in rb_id for k in ("write-audit-hash-mismatch", "injection-detected",
                                 "platform-budget-exhaustion", "break-glass")):
        return "sev0, sev1"
    if any(k in rb_id for k in ("failover", "outage", "rebuild-catastrophic", "abuse-cooldown")):
        return "sev1, sev0_if_blast_radius"
    return "sev2"


def ext_for(rb_id):
    if rb_id.startswith("meta/") or rb_id.startswith("reality/"):
        return "aws_cloudwatch_logs, grafana_meta_dashboard"
    if rb_id.startswith("ws/"):
        return "aws_cloudwatch_logs, grafana_ws_dashboard"
    if rb_id.startswith("auth/"):
        return "aws_cloudwatch_logs, grafana_auth_dashboard, vault_read_secret_db_prod"
    if rb_id.startswith("publisher/") or rb_id.startswith("projection/"):
        return "aws_cloudwatch_logs, grafana_pubsub_dashboard"
    if rb_id.startswith("llm-provider/"):
        return "pagerduty_admin, provider_registry_admin"
    if rb_id.startswith("canon/"):
        return "aws_cloudwatch_logs, grafana_canon_dashboard"
    if rb_id.startswith("deploy/"):
        return "aws_cloudwatch_logs, github_actions_admin"
    if rb_id.startswith("capacity/"):
        return "aws_cloudwatch_logs, grafana_capacity_dashboard"
    if rb_id.startswith("admin/"):
        return "aws_cloudwatch_logs, pagerduty_admin"
    return "aws_cloudwatch_logs, pagerduty_admin"


def main():
    if len(RUNBOOKS) != 27:
        print(f"FATAL: expected 27 runbooks, got {len(RUNBOOKS)}", file=sys.stderr)
        sys.exit(1)
    seen = set()
    count = 0
    for rb_id, alerts, services, tldr in RUNBOOKS:
        if rb_id in seen:
            print(f"FATAL: duplicate runbook id: {rb_id}", file=sys.stderr)
            sys.exit(1)
        seen.add(rb_id)
        subsystem, short = rb_id.split("/", 1)
        title = f"{subsystem.title()} - {short.replace('-', ' ').replace('_', ' ').title()}"
        alert_list = ", ".join(f"`{a}`" for a in alerts) if alerts else "(no direct alert - diagnostic runbook)"
        body = TEMPLATE.format(
            rb_id=rb_id,
            alerts=fmt_list(alerts),
            services=fmt_list(services),
            sev_hints=sev_for(rb_id),
            ext=ext_for(rb_id),
            title=title,
            tldr=tldr,
            alert_list=alert_list,
            first_token=subsystem,
        )
        out = RB_DIR / (rb_id + ".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        count += 1
    print(f"[generate-cycle-35-runbooks] wrote {count} runbooks under {RB_DIR}")


if __name__ == "__main__":
    main()
