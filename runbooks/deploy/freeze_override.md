# Runbook — Deploy Freeze Override (Break-Glass)

> **Layer:** L7.K.13 (RAID cycle 38) · **Spec:** SR05 §12AH.3
> **Audience:** SRE on-call + tech lead (break-glass requires dual control)
> **Severity profile:** used DURING an active SEV0/SEV1 or security incident

## When you need this

A deploy you must ship is blocked by `deploy-freeze-check.sh` because an active
freeze covers it. The four freeze types (§12AH.3):

| Freeze type | Trigger | Override authority |
|---|---|---|
| `slo_burn` | any SLI burn ≥90% over 7d (SR1-D3) | tech lead + post-deploy review |
| `scheduled` | `admin ops deploy-freeze` set a window | founder approval |
| `incident` | active SEV0/SEV1 involving the service | IC + tech lead |
| `security` | active attack / supply-chain suspicion | security on-call + tech lead |

**`emergency`-class deploys are already exempt from the `slo_burn` freeze** —
you do NOT need break-glass for that case. Break-glass is for the other three
freeze types, or an `slo_burn` freeze blocking a non-emergency change you have
decided must ship anyway.

## The break-glass workflow (§12AH.3)

Break-glass is the ONLY sanctioned bypass. It requires ALL of:

1. The PR carries the **`break-glass-deploy`** label.
2. A **tech-lead CODEOWNERS approval** (a different person from the deployer —
   no self-approval).
3. An **`incident_id` OR `security_finding_id`** (emergency justification).
4. A **mandatory post-deploy review within 24h** (the obligation is recorded).

Run the admin command to record the override to `deploy_audit`:

```
admin deploy break-glass \
  --deploy_id <deploy_audit id> \
  --freeze_type <slo_burn|scheduled|incident|security> \
  --tech_lead_approver <tech-lead user_ref> \
  --incident_id <INC-…>            # or --security_finding_id <SEC-…> \
  --reason "<why this must ship despite the freeze>" \
  --dry-run                         # tier-1: dry-run first, then re-run to apply
```

This is a **tier-1 destructive** command: dry-run + double-approval are both
required (the double-approval IS the tech-lead control §12AH.3 demands). The
command writes an `OverrideRecord` to `deploy_audit` with the post-deploy
review due time (now + 24h).

Once recorded + the label is on the PR, `deploy-freeze-check.sh` lets the merge
through and logs which freeze was overridden.

## Steps

1. Confirm the freeze is real and you genuinely need to bypass it. Read
   `deploy-freeze-check.sh` output — it names the active freeze(s).
2. Get the tech-lead approval (CODEOWNERS review on the PR).
3. Add the `break-glass-deploy` label to the PR.
4. Record the override via `admin deploy break-glass` (dry-run, then apply).
5. Merge + deploy. The canary protocol still applies if the class is `major`
   (break-glass bypasses the FREEZE, not the canary safety — see
   `runbooks/deploy/canary_abort.md`).
6. **Schedule the 24h post-deploy review** — this is not optional. Use the SR05
   §12AH.10 emergency post-deploy review template.

## Do NOT

- Do not edit `deploy-freeze-check.sh` or remove the freeze signal to get a merge
  through — that defeats the audit trail and is itself an incident.
- Do not self-approve (the command rejects `tech_lead_approver == actor`).
- Do not skip the post-deploy review — a break-glass without a review is a
  governance violation surfaced in the weekly SR2 review.

## Related

- `runbooks/deploy/canary_abort.md` — canary safety still applies after override
- `runbooks/slo/burn-rate-spike.md` — if the freeze is an `slo_burn` freeze
- `services/admin-cli/commands/deploy/break_glass.go` · `scripts/deploy-freeze-check.sh`
