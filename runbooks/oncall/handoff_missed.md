# Runbook — On-Call Handoff Missed

> **Layer:** L7.C.9 (RAID cycle 35) · **Spec:** SR2 §12AE.3
> **Audience:** outgoing on-call (page recipient); tech-lead on layer-2 escalation
> **Severity profile:** SEV2 by default; promotes to SEV1 if mid-incident

## What "handoff missed" means

The rotation hand-off is scheduled (e.g., Monday 09:00 local). PagerDuty
fires a courtesy notice 15 min before. The incoming on-call MUST write an
acknowledgement line into the new handoff file in `docs/sre/oncall-handoffs/`
within 15 min of shift start.

"Missed" = no acknowledgement within 15 min AND no Slack message in
`#oncall` from the incoming person.

## Why this is dangerous

If the incoming on-call is unreachable AND a page fires, PagerDuty's
escalation chain still works (layer 2 -> tech-lead -> founder), BUT the
outgoing on-call may have stopped looking at their phone. Gap = unmitigated
SEV until escalation chain works through layers.

## Mitigation (outgoing on-call action)

1. **Stay on shift.** Do not silence your PagerDuty notifications. You are
   still de-facto primary until the incoming on-call acknowledges.
2. **Ping the incoming person.** Slack DM, then phone (in 1Password under
   `loreweave-sre/contacts/<name>`).
3. **Page tech-lead via Slack `#oncall` channel.** Use the message template:
   `:rotating_light: Handoff missed — <incoming> unreachable at <time>. I am
   staying on as primary until ack or tech-lead activates secondary.`
4. **Write the handoff file YOURSELF.** Even without the incoming on-call's
   ack, post your shift summary so future-you (or the eventual incoming)
   has the context. Mark the acknowledgement line `MISSED — incoming did
   not ack`.

## Mitigation (tech-lead action, after Slack ping)

1. Confirm the incoming person is OK (medical, network, vacation slip).
2. If unreachable for > 30 min from scheduled handoff:
   - Activate the secondary in `escalation_policy.yaml`'s layer-2.
   - PagerDuty override: temporarily re-assign incoming's schedule layer to
     the secondary via PagerDuty UI (manual; V1+30d when secondary exists).
3. Open Slack DM with the missing on-call asking for ETA. If no reply in 1h,
   page founder (`runbooks/oncall/escalation_to_founder.md`).

## Post-incident

- Add an action item: "Why was handoff missed? (vacation slip, phone died,
  PagerDuty notification disabled, calendar drift, etc.)"
- If recurring (> 1x quarter), escalate to PO for rotation hygiene review.
- Update the handoff file with the actual ack time (post-facto) and a
  `MISSED — recovered by <name> at <time>` line.

## Related

- `runbooks/oncall/escalation_to_founder.md` — last-resort escalation
- `docs/sre/oncall-handoffs/TEMPLATE.md` — handoff schema
- `infra/pagerduty/escalation_policy.yaml` — fallback chain
- `docs/governance/oncall-sla.md` — TTA targets

## V1 solo-dev note

In V1 there are no handoffs (solo-dev rotation). This runbook is in place
so it's there when V1+30d hires a second person.
