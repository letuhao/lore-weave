# Weekly SLO Review — <yyyy-mm-dd>

> **Cadence:** weekly (SR1 §12AD.6 Layer 5)
> **Owner:** SRE lead · **Required attendees:** SRE, tech lead, PM
> **Outcome:** freeze/unfreeze decisions; feature-vs-reliability prioritization

Copy this file to `docs/sre/slo-reviews/<yyyy-mm-dd>_weekly.md` and fill in.

## 1. Current burn rates (per SLI × tier)

Read from `dashboards/slo-burn-rate.json` for the **past 7 days** and the **past 30 days**.

| SLI | Tier | 7d burn | 30d burn | Status |
|---|---|---|---|---|
| sli_session_availability | free | _ | _ | _ |
| sli_session_availability | paid | _ | _ | _ |
| sli_session_availability | premium | _ | _ | _ |
| sli_turn_completion | free | _ | _ | _ |
| sli_turn_completion | paid | _ | _ | _ |
| sli_turn_completion | premium | _ | _ | _ |
| sli_event_delivery | free | _ | _ | _ |
| sli_event_delivery | paid | _ | _ | _ |
| sli_event_delivery | premium | _ | _ | _ |
| sli_realtime_freshness | free | _ | _ | _ |
| sli_realtime_freshness | paid | _ | _ | _ |
| sli_realtime_freshness | premium | _ | _ | _ |
| sli_auth_success | (flat) | _ | _ | _ |
| sli_admin_action_success | platform | _ | _ | _ |
| sli_cross_reality_propagation | platform | _ | _ | _ |

Status legend: `normal` | `warn` (50–75%) | `review` (75–90%) | `freeze` (≥90%) | `breach` (≥100%)

## 2. Active freezes

| Frozen since | Affected SLI | Reason | Owner | Target unfreeze |
|---|---|---|---|---|

## 3. Active overrides (PRs merged with `approve-reliability-override`)

| PR | SLI affected | Override approver | Why approved | Tracking ticket |
|---|---|---|---|---|

## 4. Multi-tenant isolation incidents

Per SR1 §12AD.5. Any `LWMultiTenantIsolationViolation` alert this week?

| Date | reality_id | Resource | Action taken | Cross-reality impact |
|---|---|---|---|---|

## 5. Runbook updates

| Runbook | Reason | Updated by |
|---|---|---|

## 6. Freeze/unfreeze decisions

- [ ] Freeze X SLI: rationale, expected duration
- [ ] Unfreeze Y SLI: criteria met (burn < 50% for 24h continuous), tech-lead approval

## 7. Action items

| Item | Owner | Due |
|---|---|---|

## 8. Notes / context

(Free-form: any context that shapes next week's priorities, postmortem items still open, looming launches, etc.)

---

References:

- SR1 §12AD — full SLO + error budget contract
- `contracts/slo/sli_definitions.yaml` — 7 SLI registry
- `contracts/slo/slo_targets.yaml` — per-tier targets
- `dashboards/slo-burn-rate.json` — review dashboard
- `runbooks/slo/burn-rate-spike.md` — SRE response runbook
