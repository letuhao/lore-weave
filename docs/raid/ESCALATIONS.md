# RAID Escalations

> **Schema:** See [RAID_WORKFLOW.md §5](../plans/2026-05-29-foundation-mega-task/RAID_WORKFLOW.md#§5-escalation-flow)
> **Types:** `error` (real escalation — needs human fix) · `quota_block` (recoverable, wait for reset window — RAID v1.3 §14.5)
> **Append-only.** Newest at top.

---

(empty — no escalations yet)

## Cycle 0 — SPEC DRIFT — 2026-05-28T21:35:53Z

### Type
`spec_drift`

### Phase
clarify

### Reason / details
CYCLE_DECOMPOSITION header version v1.4 != RAID_WORKFLOW v1.5



### Suggested human action
Re-run scripts/raid/regenerate-briefs.sh; sync CYCLE_DECOMPOSITION header version with RAID_WORKFLOW.md frontmatter; re-attempt cycle

---

## Cycle 10 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T07:10:29Z

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 10; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---
