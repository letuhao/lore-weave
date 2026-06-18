# Runbook — Incident Declaration

> **Layer:** L7.D.14 (RAID cycle 37) · **Spec:** SR2 §12AE.2
> **Audience:** SRE on-call · any engineer who spots a SEV0/SEV1
> **Severity profile:** all (SEV0–SEV3)

## When to declare an incident

Declare an incident the moment ANY of these is true. Do NOT wait to confirm
root cause — declaration is cheap, a missed incident is not.

- A SEV0/SEV1 auto-classify trigger fired (see
  `contracts/incidents/severity_matrix.yaml`): data integrity loss, audit
  hash mismatch, personal data breach, total outage, canon injection,
  core-surface partial outage, security exposure.
- An SLO burn-rate page fired (see `infra/alertmanager/`).
- A customer-reported outage you can reproduce.

## How declaration works (incident-bot)

`incident-bot` (L7.D.1) is the entry point. On an inbound Alertmanager webhook
or a manual `/incident declare` it:

1. **Classifies severity** via `severity_classifier` against the severity
   matrix. An unknown alert defaults to **SEV2** (never silently SEV3).
2. **Creates the war room** (`#incident-<id>`) and invites IC + fixer + teams
   (`war_room`). Target: channel live in **< 30s**.
3. **Assigns the IC** — distinct from the fixer (SR2 §12AE.2; see
   `ic_role`). If no IC is named, the war-room card shows `(unassigned)` and
   the first responder claims it.
4. **Evaluates the comms obligation** (`statuspage`). For user-visible
   SEV0/SEV1 it emits `IncidentDeclaredV1`, which `statuspage-updater`
   (L7.L.3) turns into a public status-page entry + auto-banner.
5. **Triggers GDPR flow** if the severity row has `gdpr_breach_check: true`
   (SEV0) AND the trigger is `personal_data_breach` — see
   `runbooks/incident/gdpr_breach.md`.

## Manual checklist (if automation is degraded)

1. Pick a severity from the matrix. When in doubt, round UP.
2. Create `#incident-<id>` in Slack manually; pin a card with severity, IC,
   fixer, trigger, user-visible Y/N.
3. Assign an IC who is NOT the fixer.
4. If user-visible SEV0/SEV1: post the `incident_investigating` template
   (`infra/comms/templates/`) to the status page — see
   `runbooks/statuspage/manual_update.md`.
5. Start a timeline doc; you will need it for the postmortem.

## On resolution

Close the incident. `postmortem-bot` (L7.D.9) auto-creates
`docs/sre/postmortems/<id>.md` for SEV0/SEV1. Fill it in within 48h.

## Related

- `runbooks/incident/gdpr_breach.md`
- `runbooks/incident/comms_under_pressure.md`
- `runbooks/oncall/escalation_to_founder.md`

---

> **last_verified:** 1970-01-01
> **verification_method:** stub
