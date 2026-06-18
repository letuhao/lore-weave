# On-call Handoff — YYYY-MM-DD — <outgoing> to <incoming>

> **Shift:** YYYY-MM-DD HH:MM <tz> to YYYY-MM-DD HH:MM <tz>
> **Outgoing on-call:** <name>
> **Incoming on-call:** <name>
> **Layer:** L7.C.5 (RAID cycle 35) · **Spec:** SR2 §12AE.3

## 1. Open incidents

| ID | Severity | Status | Owner | War room | ETA |
|---|---|---|---|---|---|
| inc-NNNN | SEV1 | mitigated | <name> | `#inc-NNNN` | TBD |

_If none: write "None."_

## 2. SLI burn status (last 24h)

| SLI | Tier | 1h burn | 6h burn | Notes |
|---|---|---|---|---|
| sli_session_availability | free | 0.01 | 0.05 | normal |
| sli_turn_completion | paid | 0.30 | 0.20 | warming after deploy 1234 |

_Pull from dashboard `slo-burn-rate` — only list SLIs above 0.10 (warming threshold)._

## 3. Expected blips during incoming shift

- Scheduled deploy: ENG-1234 lands ~14:00 UTC; expect canary cohort burn spike for ~10min.
- Maintenance: meta-postgres replica resize 02:00 UTC; failover drill at 03:00.
- Drill: chaos-engineering Q3 ws-disconnect drill at 16:00 UTC.

_Reference: dev calendar + deploy queue + chaos schedule._

## 4. Anomalies seen this shift

- Anomaly description, timestamp, what was investigated, conclusion.
- Anything the incoming on-call should re-check if it recurs.

_If none: write "None."_

## 5. Action items handed off

- [ ] Action description, why, where to find context.
- [ ] Follow up with frontend-game about ticket-redeem regression (slack thread `<link>`).

## 6. Operational handoff signatures

- Outgoing signed off at: YYYY-MM-DD HH:MM <tz>
- Incoming acknowledged at: YYYY-MM-DD HH:MM <tz>

_Append-only — once committed, do not edit. See `runbooks/oncall/handoff_missed.md` if the incoming on-call did not acknowledge within 15 min of shift start._
