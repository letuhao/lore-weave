# IN_PROGRESS — Per-Cycle State Files

> **Purpose:** Per RAID_WORKFLOW.md §12.3 / P3, Raid Leader writes
> `cycle-<N>-state.md` here at every phase transition. Files enable
> crash recovery + compaction recovery + quota-block recovery.

## Schema

```yaml
---
cycle: <N>
title: <from brief>
current_phase: CLARIFY | DESIGN | REVIEW1 | PLAN | BUILD | VERIFY | REVIEW2 | QC | POST_REVIEW | SESSION | COMMIT | RETRO
phase_started_at: <ISO 8601>
last_checkpoint_at: <ISO 8601>
retry_count: 0..3
quota_block_count: 0..N
dps_status:
  - dps_id: 1
    worktree: ../foundation-worktrees/cycle-<N>-dps-1
    branch: mmo-rpg/foundation-mega-task/cycle-<N>-dps-1-<slice>
    status: pending | in_progress | complete | failed | aborted_secret_detected
    model: opus-4-7 | sonnet-4-6 | haiku-4-5
    started_at: <ISO>
    completed_at: <ISO or null>
adversary_findings_count: <int or null>
scope_guard_result: CLEAR | BLOCKED | null
verify_script_exit: <int or null>
notes: <free-text, < 500 chars>
---

# Cycle <N> in-progress state

<short narrative of where we are, what's next, any anomalies>
```

## Lifecycle

- **Created:** at Phase 1 (CLARIFY) by Raid Leader
- **Updated:** at every phase transition + every DPS completion + every retry
- **Read on resume:** by P2 startup routine step 3 (RAID_WORKFLOW.md §12.2)
- **Archived on COMMIT success:** moved to `_archive/cycle-<N>-state.md`
- **Archived on quota_block:** stays in `IN_PROGRESS/` for resume
- **Archived on ABORTED:** moved to `_archive/` with `_FAILED` suffix; ESCALATIONS row links here

## Do NOT

- Manually edit while a cycle is running (corrupts state)
- Delete files mid-cycle (orchestrator will fail to recover)
- Commit IN_PROGRESS files directly to git (use `.gitignore` if needed — they are state, not source)
