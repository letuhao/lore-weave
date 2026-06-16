# Runbook — Customer Comms Under Pressure

> **Layer:** L7.D.16 (RAID cycle 37) · **Spec:** SR2 problem 7 + §12AE.2
> **Audience:** IC · SRE on-call
> **Severity profile:** SEV0 / SEV1 (user-visible)

## Why this runbook exists

Under incident pressure, ad-hoc copy is dangerous: wrong tone, premature
root-cause claims ("it was a bad deploy" before you know), legal exposure,
and broken-promise ETAs. SR2 problem 7. The fix: **always use a pre-approved
template.** Never freehand a public statement during a live incident.

## The templates

Pre-approved templates live in `infra/comms/templates/` (Q-L7-2). Each is
i18n EN + VI (V1 minimum, L7.L.4):

| Template id | Use when | Channel |
|---|---|---|
| `incident_investigating` | First public notice; cause unknown | status page |
| `incident_identified` | Cause known, fix in progress | status page |
| `incident_resolved` | Service restored | status page |
| `gdpr_breach_notice` | Personal-data breach → DPO (NOT public) | email |

`incident-bot`'s `comms_template` package loads + renders these. It refuses to
emit if a required placeholder (e.g. `{{incident_id}}`) is missing, so you
cannot accidentally publish an unfinished statement.

## Rules under pressure

1. **Template first.** If no template fits, the IC drafts and a SECOND person
   (tech-lead) approves before it goes public. Two-person rule.
2. **No root-cause speculation** in the first notice. "We are investigating"
   is always safe; "caused by X" must be confirmed.
3. **No ETAs you can't keep.** Commit only to the next-update cadence
   (the `incident_investigating` template promises an update in 30 min).
4. **Match the comms obligation.** Only user-visible SEV0/SEV1 get a public
   post (the matrix decides — `RequiresStatusPage`). An internal SEV0 does
   not get a public banner.
5. **Localize.** Status-page subscribers include VI users; the templates
   already carry VI. Render the locale, don't machine-translate live.

## Cadence

- SEV0: public update at least every **30 min**.
- SEV1: public update at least every **60 min**.
- On resolution: post `incident_resolved` promptly; promise the postmortem.

## Related

- `runbooks/statuspage/manual_update.md`
- `runbooks/incident/declaration.md`

---

> **last_verified:** 1970-01-01
> **verification_method:** stub
