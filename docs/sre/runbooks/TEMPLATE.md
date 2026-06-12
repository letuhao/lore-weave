---
runbook_id: <subsystem>/<short-name>
version: 1
owner: sre-team
applies_to_alerts: []
applies_to_incidents: []
applies_to_services: []
last_verified: 1970-01-01
last_verified_by: unassigned
verification_method: stub
next_verification_due: 1970-04-01
severity_hints: [sev2]
dry_run_required_for_destructive: true
related_runbooks: []
external_access_needed: []
born_from_incident_id: null
shipped_cycle: 35
locked_decisions_consumed: [Q-L7B-1]
---

# <Subsystem> — <Short Name>

## TL;DR (30 seconds)

[One paragraph: what's happening + first immediate action. Read this in the elevator.]

## Symptoms

- [Alert that fired]
- [User-visible impact]
- [Dashboard indicators / metric to confirm]

## Likely Causes (ranked by frequency)

1. **[Most common cause]** — verify via `[metric/log query]` — fix: `[short]`
2. **[Second most common]** — verify via `[metric/log query]` — fix: `[short]`
3. **[Edge case]** — verify via `[metric/log query]` — fix: `[short]`

## Diagnostic Commands

```bash
# Copy-paste ready. Always --dry-run first for destructive operations.
admin-cli <subsystem> status --dry-run
```

Expected output:
```
[paste expected output sample]
```

## Mitigation Steps

### Quick mitigation (stop bleeding — SEV1 or higher)

1. [Immediate action]
2. [Confirm user-facing impact subsided]

### Full resolution

1. [Diagnostic step]
2. [Fix step]
3. [Verification step]

## Rollback

[How to revert if mitigation worsens. Required even for read-only mitigations:
"we paged the wrong team and the right team is now in conflict — un-page" is
a valid rollback.]

## Escalation

| Condition | Escalate to | TTA |
|---|---|---|
| Mitigation fails after 30 min | tech-lead | 30 min |
| Multi-service impact | incident-bot SEV1 | 15 min |
| Data integrity suspected | founder + DPO | 5 min |

## Verification (post-mitigation)

1. [Metric returns to baseline]
2. [No user-facing reports]
3. [Update incident timeline if SEV0/SEV1]

## Related

- [Related runbook link]
- [Postmortem link if `born_from_incident_id` is set]
- [Spec/design doc reference]
