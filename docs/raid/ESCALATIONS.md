# RAID Escalations

> **Schema:** See [RAID_WORKFLOW.md §5](../plans/2026-05-29-foundation-mega-task/RAID_WORKFLOW.md#§5-escalation-flow)
> **Types:** `error` (real escalation — needs human fix) · `quota_block` (recoverable, wait for reset window — RAID v1.3 §14.5)
> **Append-only.** Newest at top.

---

## ✅ RESOLUTION BANNER (post-RAID review, 2026-05-30) — PRR-10 reconciliation

**All entries below are RESOLVED. There is ZERO real unresolved work in this file.**

- **23 × `p5_recovery_inconsistent`** entries (cycles **10, 11, 13–19, 21–28, 30–35**) were
  **spurious post-completion false-positives** caused by the **PRR-10 recovery ordering bug**:
  `recovery-protocol-runner.sh` treated a MISSING live `IN_PROGRESS/cycle-<N>-state.md` as a
  crash, but that file is legitimately MOVED to `IN_PROGRESS/_archive/cycle-<NNN>-state.md` on
  normal COMMIT. Every one of these cycles **completed, archived its state file, is marked DONE
  in `docs/raid/CYCLE_LOG.md`, and has a feature commit**. The bug is now **FIXED** (the runner
  checks the archive + CYCLE_LOG DONE status before declaring INCONSISTENT, exiting 0 without
  escalating). Verified: re-running the runner for a DONE cycle now reports CONSISTENT and writes
  no escalation.
- **Cycle 0 `spec_drift`** (CYCLE_DECOMPOSITION v1.4 != RAID_WORKFLOW v1.5) — **RESOLVED**: the
  bootstrap version drift was reconciled when the v1.5/v1.6 workflow was adopted; cycle 0 and all
  38 cycles subsequently completed.

The historical entries are **retained (not deleted)** for the audit trail and annotated inline as
resolved / false-positive. **No human action is required for any entry below.**

---

## Cycle 0 — SPEC DRIFT — 2026-05-28T21:35:53Z — ✅ RESOLVED (version drift reconciled; all 38 cycles completed)

### Type
`spec_drift`

### Phase
clarify

### Reason / details
CYCLE_DECOMPOSITION header version v1.4 != RAID_WORKFLOW v1.5



### Suggested human action
Re-run scripts/raid/regenerate-briefs.sh; sync CYCLE_DECOMPOSITION header version with RAID_WORKFLOW.md frontmatter; re-attempt cycle

---

## Cycle 10 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T07:10:29Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

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

## Cycle 11 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T07:37:31Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 11; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 13 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T08:11:05Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 13; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 14 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T08:30:20Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 14; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 15 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T08:52:27Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 15; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 16 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T09:11:00Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 16; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 17 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T09:35:41Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 17; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 18 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T10:05:27Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 18; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 19 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T10:25:48Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 19; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 21 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T11:20:51Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 21; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 22 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T11:47:26Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 22; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 23 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T12:09:19Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 23; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 24 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T12:31:32Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 24; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 25 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T12:58:38Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 25; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 26 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T13:26:52Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 26; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 27 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T14:02:41Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 27; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 28 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T14:25:37Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 28; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 30 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T15:06:04Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 30; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 31 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T15:34:46Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 31; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 32 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T16:07:22Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 32; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 33 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T16:37:30Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 33; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 34 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T17:18:38Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 34; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---

## Cycle 35 — P5 RECOVERY INCONSISTENT (halted) — 2026-05-29T17:39:41Z — ✅ RESOLVED (FALSE-POSITIVE; PRR-10 recovery ordering bug — cycle completed + archived + DONE)

### Type
`p5_recovery_inconsistent`

### Phase
recovery

### Reason / details
(no reason provided)

### Mismatch
IN_PROGRESS state file missing for cycle 35; cannot reconstruct phase

### Suggested human action
Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking

---
