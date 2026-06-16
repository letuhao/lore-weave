---
runbook_id: canon/injection-detected
version: 1
owner: sre-team
applies_to_alerts: [LWCanonInjectionDetected]
applies_to_incidents: []
applies_to_services: [world-service]
last_verified: 1970-01-01
last_verified_by: unassigned
verification_method: stub
next_verification_due: 1970-04-01
severity_hints: [sev0, sev1]
dry_run_required_for_destructive: true
related_runbooks: []
external_access_needed: [aws_cloudwatch_logs, grafana_canon_dashboard]
born_from_incident_id: null
shipped_cycle: 35
locked_decisions_consumed: [Q-L7B-1]
---

# Canon - Injection Detected

> **STUB - Q-L7B-1 V1 launch allowance.** This runbook is a placeholder.
> The next on-call SRE to be paged for the related alert(s) MUST upgrade
> this stub to a verified runbook before the next page. Set
> `verification_method: reading_review` and update `last_verified` to today.

## TL;DR (30 seconds)

Auto-SEV1 (S13): canon-injection signal; freeze contested canon, page security.

## Symptoms

- Alert(s) firing: `LWCanonInjectionDetected`
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
admin-cli canon status --dry-run
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
