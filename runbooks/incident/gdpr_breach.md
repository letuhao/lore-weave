# Runbook — GDPR Art.33 Personal Data Breach (72h flow)

> **Layer:** L7.D.15 (RAID cycle 37) · **Spec:** §12X · GDPR Art.33
> **Audience:** SRE on-call · IC · DPO · founder
> **Severity profile:** SEV0 (personal-data-breach class)

## The 72-hour clock is real

GDPR Article 33 requires notifying the supervisory authority **within 72
hours** of becoming aware of a personal data breach. The clock anchors at
**detection time**, not declaration time. Missing it is a regulatory
violation, not just an SLA miss.

## Trigger

A personal-data breach is a SEV0 with the `personal_data_breach` trigger
(`contracts/incidents/severity_matrix.yaml`, `gdpr_breach_check: true`).
Examples: unauthorized access to user PII, a leaked credential exposing user
data, a misconfigured store serving another tenant's data.

## What incident-bot does (gdpr_breach_flow)

On a SEV0 personal-data breach, `gdpr_breach_flow` (L7.D.7):

1. Records the breach timeline: `detected_at` → `deadline = detected_at + 72h`.
2. Sends the DPO notice using the `gdpr_breach_notice` template
   (`infra/comms/templates/`, EN + VI).
3. Raises an **approaching-deadline** alert when < 12h remain.
4. Flags **deadline missed** if 72h elapse without notification.

## IC checklist

1. **Anchor the clock.** Confirm `detected_at` is the true awareness time.
   If unsure, use the earliest plausible time (conservative).
2. **Loop in the DPO and founder immediately** — do not batch this with the
   technical fix. Use `runbooks/oncall/escalation_to_founder.md`.
3. **Scope the data.** What categories (email, IP, payment, content)? How
   many subjects (approximate is fine for the initial notice)?
4. **Do NOT make premature claims** in any customer comms. Use only the
   pre-approved `gdpr_breach_notice` template until legal reviews.
5. **Notify the supervisory authority within 72h.** The DPO leads this; SRE
   provides the technical timeline.
6. **Record everything** in the incident timeline — it becomes the Art.33
   documentation.

## Credentials

DPO contact + supervisory-authority portal details live in the SRE 1Password
vault `loreweave-sre/contacts/dpo`. The DPO notifier uses an env-var-sourced
channel; no addresses are committed.

## Related

- `runbooks/incident/declaration.md`
- `runbooks/incident/comms_under_pressure.md`

---

> **last_verified:** 1970-01-01
> **verification_method:** stub
