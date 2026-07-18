# S-12 deferred-cleanup — close the discoverability badge + parity gaps

> **Origin:** the S-12 audit ([`../plans/2026-07-18-S12-workflows-gui-RUN-STATE.md`](../plans/2026-07-18-S12-workflows-gui-RUN-STATE.md))
> deferred 3 items. This spec clears all three. **Services:** agent-registry-service (Go) + FE.
> Size: **M** (4 small slices, each BUILD → review-impl → QC). **✅ ALL SLICES BUILT 2026-07-18.**

## Why now
The S-12 audit closed the propose→approve loop's *in-conversation* signal (the agent names + can
open the Workflow Proposals panel). The remaining gap is the **persistent** signal — when a user
returns to the studio later, nothing tells them proposals are waiting. The count already exists
(`proposals_pending` sums skill + workflow proposals — verified); it's just never surfaced in the
studio. And the studio has a **clean, precedented mechanism** for exactly this: frame-level status-bar
items (`StudioStatusContributions` — `NotificationsStatusItem`/`UsageCostStatusItem`) that stay live
while their panel is closed. So the badge is a mirror, not a structural build.

## Slices

### Slice A · BE — split the proposal count (D-S12-STUDIO-PROPOSAL-BADGE, half 1)
`getUsage` returns `proposals_pending` (a SUM of skill + workflow). Add the two components so the
badge can route a click to the right panel:
- `skill_proposals_pending`, `workflow_proposals_pending` (keep `proposals_pending` = sum, back-compat).
- `countProposalsIfExists` already runs the two queries separately — split its return, don't re-query.
- FE `UsageCounters` type gains the two fields (optional, back-compat).
*DoD:* a unit test asserts `/usage` returns both components + their sum; existing usage tests green.

### Slice B · FE — the studio pending-approvals badge (D-S12-STUDIO-PROPOSAL-BADGE, half 2)
A frame-level `ProposalsStatusItem` mirroring `NotificationsStatusItem`:
- polls `extensionsApi.usage` (seed on mount) → total pending = skill + workflow.
- renders an inbox icon + count badge (hidden when 0); tooltip "N pending approval(s)".
- **click routes deterministically:** `workflow_proposals_pending > 0` → open `workflow-proposals`,
  else → open `proposals` (skills). Covers BOTH proposal types with one badge, no drift.
- registered in `StudioStatusContributions` (module-level def, stable identity).
- i18n: `studio` ns `status.proposals*` keys.
*DoD:* the item renders the count; click opens the right panel per the split counts; unit test.

### Slice C · BE — workflow revisions read route (D-S12-WORKFLOW-REVISIONS)
`snapshotWorkflowRevision` writes `workflow_revisions` on approve-update but nothing reads them.
Add `GET /v1/workflows/{workflow_id}/revisions` → `listWorkflowRevisions`, mirroring
`listSkillRevisions` (visibility = System ∪ own ∪ book-with-view). **BE-only** — skills' revisions
route also has no FE consumer, so parity is the route, not a panel. *DoD:* a route test (own → rows;
not-visible → 404); no FE (matches skills).

### Slice D · FE — i18n the mode-binding UI (D-S12-BINDINGS-I18N)
`BindingSettings` (now a settings tab) hardcodes English ("Loading…", mode headings, the veto
toggle labels, empty state). Wrap them in `useTranslation` (`extensions` ns, `bindings.*` keys) +
fill 17 locales. `WorkflowRack` (the /extensions read-only rack) similarly, if its strings are
user-visible. *DoD:* no hardcoded visible English in BindingSettings; i18n gate full parity.

## Adherence
- Badge reuses the registered-status-item mechanism (no new chrome). Count split is additive
  (back-compat). Revisions mirror the skills route (visibility helper reused). i18n via
  `i18n_translate.py` (ML-7), en-first.
- Tenancy: the counts are owner-scoped (`WHERE owner_user_id`); the revisions route reuses the
  workflow visibility gate (System ∪ own ∪ book-with-view).

## Out of scope
- A notification-on-propose (agent-registry → notification-service emit) — a bigger cross-service
  change; the badge (poll) + the in-conversation signal (audit) cover discovery without it.
- A workflow revisions FE panel (skills has none either; add when a real need appears).
