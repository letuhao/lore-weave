# Runbook — Escalation to Founder

> **Layer:** L7.C.10 (RAID cycle 35) · **Spec:** SR2 §12AE.4
> **Audience:** SRE on-call OR tech-lead OR security on-call
> **Severity profile:** SEV0 / SEV1 only — never SEV2 or SEV3

## When to escalate to founder direct

This is the LAST RESORT escalation path. Use it when:

1. **SEV0 + 15 min unmitigated.** Per `infra/pagerduty/escalation_policy.yaml`
   the founder is layer 3 (15 min after layer 1 fires). PagerDuty already
   handles this automatically; this runbook documents the manual override.
2. **Personal-data breach suspected.** GDPR Art.33 72h timer is real — DPO
   + founder MUST be looped in early. The security escalation policy already
   pages DPO at layer 4; founder gets layer 3.
3. **War room created but IC unreachable.** If incident-bot declared SEV0/1
   and the assigned IC has not responded to war-room ping in 5 min, page
   founder direct via this runbook.
4. **Handoff failure cascade.** If `runbooks/oncall/handoff_missed.md` plus
   tech-lead unreachable, page founder.
5. **Auth-service is the incident.** If you cannot SSO into Grafana/Vault
   because auth-service is down, you cannot complete normal triage; founder
   has out-of-band access via the recovery procedure.

## What "founder direct" means

| Method | Latency | When to use |
|---|---|---|
| PagerDuty layer 3 (auto) | 15 min from layer 1 | normal SEV0/1 escalation |
| Slack `@founder` in `#incidents` | < 1 min if online | first attempt after PagerDuty layers 1+2 ack-no-mitigate |
| Phone direct (1Password `loreweave-sre/contacts/founder`) | varies | when Slack ack absent + > 5 min sev0 |
| Spouse/emergency contact | varies | unreachable > 30 min AND active SEV0 (last resort) |

The phone + emergency contact are in 1Password vault `loreweave-sre/contacts/`.
Access is restricted to the SRE rotation + tech-lead.

## Procedure

1. **Confirm SEV.** If SEV2 or SEV3, do not escalate — page tech-lead instead.
2. **Document the escalation** in the incident's war-room channel:
   `:phone: Escalating to founder direct at <time>. Reason: <one line>.`
3. **Page via PagerDuty manual incident** with title `FOUNDER-DIRECT: <reason>`
   targeting the `lw-sev0` service. This fires layer 3 immediately
   (bypassing layer 1 + 2 delays).
4. **Slack DM founder** with: `:phone: Founder-direct escalation — incident
   inc-NNNN — <one-line reason>. War room: <link>.`
5. **Phone** if no Slack ack within 5 min. The phone number rings for
   45 seconds then hits voicemail; LEAVE A MESSAGE with incident id + war
   room channel.
6. **Spouse / emergency contact** ONLY if 30 min elapsed AND active SEV0.
   Use the contact-script in `1Password loreweave-sre/contacts/emergency-script`
   — the message is pre-approved to avoid panicking a non-technical contact.

## Post-incident

Every founder-direct escalation MUST appear in the postmortem with:

- Why PagerDuty layer 3 was not enough (delay too long? founder phone off?
  PagerDuty itself misbehaving?)
- What lower-layer mitigation could have prevented it
- Action item: tighten layer timings OR fix the underlying gap that forced
  the escalation

If founder-direct escalations exceed 1 per quarter, tech-lead opens a
rotation hygiene review with PO.

## V1 solo-dev caveat

In V1 the founder IS the on-call. "Founder direct" therefore collapses to
"this same person, on their personal phone instead of PagerDuty". The
distinction still matters because:

- PagerDuty has a quiet-hours setting that suppresses non-SEV0 pages
- The phone bypasses that
- The phone also bypasses the PagerDuty app crash bug that hit Q2/2026

V1+30d when a second person joins, this runbook becomes the "page the
founder because the incoming on-call is unreachable" flow.

## Related

- `runbooks/oncall/handoff_missed.md`
- `infra/pagerduty/escalation_policy.yaml`
- `docs/governance/oncall-sla.md`
- LOCKED Q-L7C-1 + Q-L7C-2
