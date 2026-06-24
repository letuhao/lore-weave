# On-Call SLA — Internal V1

> **Status:** internal docs · **Audience:** SRE + tech lead + founder
> **Q-L7C-2 LOCKED:** V1 internal-only; user-facing TOS V2+ paid-tier launch
> **Layer:** L7.J governance reference (RAID cycle 34)

## Why this is INTERNAL only

Per Q-L7C-2: solo-dev V1 weekend SLA cannot match enterprise expectations.
Promising one externally creates legal liability the project can't honor.
This doc captures the OPERATIONAL targets we hold ourselves to; once paid
tier launches (V2+), a customer-facing TOS will reference these targets
with appropriate hedges + credits policy.

## Severity → Time-to-Acknowledge (TTA)

These targets drive the PagerDuty escalation timers per `infra/alertmanager/channels.yaml::pagerduty`. V1 solo-dev mode collapses primary/secondary onto the same person, so the relevant number is "I will look at my phone within X."

| Severity | Business hours TTA | Off-hours TTA | Weekend TTA |
|---|---|---|---|
| SEV0 (SLO breach, security incident) | 5 min | 15 min | 30 min |
| SEV1 (feature freeze, partial outage) | 15 min | 30 min | 2 h |
| SEV2 (degraded; auto-mitigated) | 1 h | 4 h | next business day |
| SEV3 (advisory) | next business day | next business day | next business day |

**Note:** these are TTA, not Time-to-Resolve. Resolution time depends on root cause; SLA shape is V2+ territory.

## Severity → Time-to-Mitigate (TTM)

| Severity | Target TTM |
|---|---|
| SEV0 | 30 min |
| SEV1 | 2 h |
| SEV2 | 8 h |
| SEV3 | best-effort |

## Severity → Communication cadence

Per SR2 §12AE.7. Internal Slack `#inc-<id>` channel update cadence:

| Severity | Update frequency |
|---|---|
| SEV0 | every 30 min until resolved |
| SEV1 | every 60 min until mitigated |
| SEV2 | ad-hoc, with mitigation + resolution announcements |
| SEV3 | resolution-only |

## Postmortem timeline

Per SR2 §12AE postmortem state:

- **SEV0:** postmortem MANDATORY; published within 7 calendar days; PO+tech-lead review
- **SEV1:** postmortem MANDATORY; published within 14 days
- **SEV2:** postmortem only if L8 trigger met (e.g., regression of known issue)
- **SEV3:** no postmortem

Postmortems live in `docs/sre/postmortems/<yyyy-mm-dd>_<incident-id>.md`.

## Solo-dev weekend reality

V1 ships with a single on-call person (the founder). Weekend pages are
real but rare. Mitigation strategies:

1. **Auto-mitigation first.** L1.J degraded mode, circuit breakers, rate
   limits — most outages should self-heal without a human page.
2. **Alert hygiene.** Every alert must have a runbook (`scripts/alert-rule-validator.sh`)
   so the on-call doesn't reverse-engineer the issue at 3am.
3. **Inhibition rules.** `infra/alertmanager/inhibition_rules.yaml` ensures
   SEV0 doesn't spawn 50 downstream pages.
4. **Silence policy.** `infra/alertmanager/silence_admission_policy.yaml`
   makes "I'll silence this and look in the morning" a tracked, audited
   action — not a silent forever-bypass.

If the founder is unreachable (vacation, etc.) the escalation falls back
to PagerDuty's manager-on-duty + the published phone number. V1+1mo
will add a backup person to the rotation.

## V2+ (paid tier) — customer-facing SLA candidates

Once the paid tier launches with > 100 active subscribers, these
**candidate** numbers will be published in TOS:

| Tier | Uptime target | Credits if missed |
|---|---|---|
| Paid | 99.5% monthly | 10% off next month |
| Premium | 99.9% monthly | 25% off next month |

These will reference SLI `sli_session_availability` + `sli_turn_completion`
from `contracts/slo/sli_definitions.yaml`. Credits processed automatically
via the usage-billing-service.

## References

- SR1 §12AD — SLO + error budget
- SR2 §12AE — incident on-call
- `infra/alertmanager/channels.yaml` — PagerDuty service map
- `infra/alertmanager/silence_admission_policy.yaml` — silence policy
- `runbooks/alerts/silence_misuse.md` — what to do on policy violation
- LOCKED Q-L7C-2

last_verified: 2026-05-29
verification_method: cycle-34-build (Q-L7B-1 stub class — V1 ships internal doc; V2+ external TOS)
