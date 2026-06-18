# PagerDuty Infrastructure — L7.C (RAID cycle 35)

> **LOCKED references:** Q-L7C-1 (PagerDuty V1) · Q-L7C-2 (internal SLA only)
> **Carry-forward:** cycle-34 `infra/alertmanager/channels.yaml` declares the 5
> PagerDuty service env-vars; this directory defines the matching rotations +
> escalation policies.

## What lives here

| File | Purpose |
|---|---|
| `main.tf` | Terraform skeleton for the 5 PagerDuty services + escalation policies + schedules |
| `rotation_schedule.yaml` | Solo-dev V1 / V1+30d 2-person / V2+ team — per SR2 §12AE.3 |
| `escalation_policy.yaml` | Primary -> secondary -> tech-lead -> founder (per SR2 §12AE.4) |
| `services.yaml` | The 5 PagerDuty services + their integration-key env-var names (matches cycle-34 channels.yaml) |
| `README.md` | This file |

## V1 reality (Q-L7C-1 + Q-L7C-2)

- **PagerDuty V1.** ~$25/user/month accepted — industry standard, broad
  integration set, terraform provider available. Alternatives (OpsGenie,
  Squadcast) explicitly considered + declined per Q-L7C-1.
- **Solo-dev V1.** All 5 services point at the same person (founder). The
  routing graph is in place so V1+30d expansion to a 2-person rotation is a
  YAML edit, not a refactor.
- **Internal SLA.** Targets live in `docs/governance/oncall-sla.md` — NOT in
  user-facing TOS (Q-L7C-2). Customer-facing SLA waits for V2+ paid tier.

## How the wiring works

Cycle 34 already laid down `infra/alertmanager/channels.yaml` declaring 5
PagerDuty services indexed by env-var name:

| Service name | Env-var | Use |
|---|---|---|
| sev0 | `PAGERDUTY_INTEGRATION_KEY_SEV0` | SLO breach — wake everyone |
| sev1 | `PAGERDUTY_INTEGRATION_KEY_SEV1` | Freeze >= 90% burn — primary + secondary |
| sre  | `PAGERDUTY_INTEGRATION_KEY_SRE`  | Default — meta + ws + service alerts |
| security | `PAGERDUTY_INTEGRATION_KEY_SECURITY` | auth + canon-injection + audit-hash |
| data | `PAGERDUTY_INTEGRATION_KEY_DATA` | meta-postgres + projection + outbox |

This cycle (35) adds the **rotation + escalation policy** that PagerDuty
applies to each service. The integration keys themselves are provisioned in
the PagerDuty UI on first apply and injected via env-var.

## Terraform apply procedure

```bash
cd infra/pagerduty
# V1 manual apply — once per environment.
terraform init
terraform plan -var-file=prod.tfvars
terraform apply -var-file=prod.tfvars
```

`terraform output` then emits the 5 integration keys. Store each in 1Password
under `loreweave-sre/pagerduty/<service>` and set the matching env-var on
alertmanager + slack-bot + incident-bot deployments.

## Rotation expansion plan

| Phase | Rotation | Owner of `escalation_policy.yaml` change |
|---|---|---|
| V1 | Solo-dev (founder for all 5 services) | founder |
| V1+30d | 2-person rotation (founder + first SRE hire) | tech-lead PR |
| V2+ | 4-person rotation + secondary tier + follow-the-sun | SRE manager PR |

The `rotation_schedule.yaml` file uses a `phase: v1 | v1plus30d | v2plus`
marker so the active phase is explicit. V1 file flips on the V1+30d hire date.

## Handoff procedure

Every rotation hand-off MUST write a handoff entry to
`docs/sre/oncall-handoffs/YYYY-MM-DD_outgoing-to-incoming.md` using the
`TEMPLATE.md` schema. Append-only is enforced by CI lint
`scripts/oncall-handoff-lint.sh` (V1+30d when handoffs start happening).

## References

- SR2 §12AE.3 — rotation table
- SR2 §12AE.4 — alert routing + fallback chain
- LOCKED Q-L7C-1 + Q-L7C-2
- `docs/governance/oncall-sla.md` — TTA + TTM + comms cadence
- `infra/alertmanager/channels.yaml` — env-var-indirected service keys
- `runbooks/oncall/handoff_missed.md` — what to do when a rotation hand-off is missed
- `runbooks/oncall/escalation_to_founder.md` — last-resort escalation flow
