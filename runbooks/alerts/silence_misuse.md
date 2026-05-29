# Runbook — Silence Misuse / Policy Violation

**Owner:** SRE on-call · **Severity:** SEV2 (escalates if protected alert silenced) · **Layer:** L7.J.9 (RAID cycle 34)

## When this fires

The `lw_alert_silence_policy_violation_total` counter increments OR an audit review surfaces a silence created outside `silence_admission_policy.yaml`. Common triggers:

- Wildcard silence (covering > 5 alertnames) — soft-warn fired
- Silence created during active SEV0/SEV1 incident — soft-warn fired
- Protected alert silenced by non-tech-lead actor — HARD violation; immediate page

## Background — why this matters

Silences are a tool, not a workaround. Misuse pattern:

1. Operator paged at 3am
2. Operator silences alert "just for tonight"
3. Forgets to remove silence
4. Real outage masked for days/weeks

Foundation V1 `silence_admission_policy.yaml` enforces:

- Every silence carries `actor`, `category`, `reason`, `created_at`, `expires_at`, `alert_matcher`, `origin`
- 5 categories with max durations: deploy (2h), maintenance (8h), known_issue (7d), incident_in_progress (24h), false_positive (48h)
- 4 protected alerts cannot be silenced without `tech_lead` role:
  - `LWMetaPostgresPrimaryDown`
  - `LWAuthHashMismatch`
  - `LWSLOBreachSessionAvailability`
  - `LWMultiTenantIsolationViolation`

## Quick triage (5 min)

1. From `alert-recorder` audit: `admin-cli alerts silences list --policy-violations --since 24h`
2. Note `actor` + `alert_matcher` + `category` + `created_at`
3. Check if the silenced alertname is in `protected_alerts` of `silence_admission_policy.yaml`
4. If YES + actor != tech_lead → IMMEDIATE escalation; revoke silence

## Investigation tree

```
Policy violation detected?
├── Wildcard (>5 alertnames)
│   ├── Look up actor's recent context (Slack #inc-* channels, deploy log)
│   └── action: Slack DM actor; ask for justification; tune if false-pos
├── Active-incident silence
│   ├── Cross-check against `incidents` table (L7)
│   └── action: confirm with IC; if legitimate, leave; if not, revoke
├── Protected alert (4 named)
│   ├── PAGE tech lead
│   ├── action: revoke silence; investigate why protected alert fired
│   └── postmortem if any platform-impact period during silence
└── Expired but not auto-cleaned
    └── action: bug in alert-recorder auto-expiry; file ticket
```

## Mitigation menu

1. **Revoke silence.** `admin-cli alerts silences delete --id <silence_id> --reason "policy violation"`
2. **Force-unsilence protected alert.** `admin-cli alerts silences force-clear --alertname <name>` (tech_lead only)
3. **Audit recent activity.** `admin-cli alerts silences audit --actor <user> --since 7d`
4. **Tune the alert.** If silence was created because the alert is noisy → schedule the rule tuning into next SLO review (`docs/sre/slo-reviews/`).

## Post-mitigation checklist

- [ ] Silence revoked + alert re-armed
- [ ] If protected alert was suppressed during an outage: postmortem MANDATORY
- [ ] `lw_alert_silence_policy_violation_total` counter does not increment again for 24h
- [ ] If pattern of misuse from same actor: discuss in next 1:1

## Cross-references

- `infra/alertmanager/silence_admission_policy.yaml` — policy source
- `services/alert-recorder/internal/store/store.go` — audit persistence (alert_silences)
- SR2 §12AE.8 — incidents tracker table
- Runbook `runbooks/slo/burn-rate-spike.md` — the canonical "do not silence" example

last_verified: 2026-05-29
verification_method: cycle-34-build
