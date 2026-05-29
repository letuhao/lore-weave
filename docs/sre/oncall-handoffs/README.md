# On-call Handoffs — Append-Only Log

> **Layer:** L7.C.4 (RAID cycle 35) · **Spec:** SR2 §12AE.3 handoff protocol

This directory is the append-only handoff log between rotation shifts. Every
rotation hand-off MUST write an entry here using `TEMPLATE.md`.

## Why append-only

Handoffs are evidence in postmortems. Editing or deleting them after the fact
hides what the outgoing on-call communicated. The CI lint
`scripts/oncall-handoff-lint.sh` (V1+30d when handoffs start) enforces:

- File names match `YYYY-MM-DD_outgoing-to-incoming.md`
- No file may be deleted (`git log --diff-filter=D --name-only` post-PR check)
- Edits to existing handoff files require a justification line in the PR
  description matching `Handoff edit reason: <reason>`

## V1 solo-dev reality

In V1 there is no rotation, so handoff files are not produced. The directory
exists so the schema + lint are in place when V1+30d adds the second person.
First handoff lands on `YYYY-MM-DD_founder-to-sre-hire-1.md` on the first
hand-off date.

## Schema

See [`TEMPLATE.md`](TEMPLATE.md). Required sections:
1. **Open incidents** — any SEV that's still IN_PROGRESS
2. **SLI burn status** — which SLIs are currently warming
3. **Expected blips** — scheduled deploys, maintenance, drills
4. **Anomalies seen this shift** — anything weird the next-on-call should know
5. **Action items handed off** — what the incoming on-call should do

## References

- SR2 §12AE.3 — rotation + handoff protocol
- `infra/pagerduty/rotation_schedule.yaml` — schedule that drives handoffs
- `docs/governance/oncall-sla.md` — TTA + TTM targets
- LOCKED Q-L7C-1 + Q-L7C-2
