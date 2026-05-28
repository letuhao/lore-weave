---
description: Enable RAID v1.5 Coordinator mode — main session dispatches each pending cycle as Agent-tool sub-agent (cold-start = P1 fresh-session spirit) and runs the entire foundation in ONE invocation.
---

# /raid — RAID v1.5 Coordinator mode

By default the LoreWeave repo uses v2.2 human-in-loop workflow. Invoke `/raid` to enter
**Coordinator mode** for the foundation mega-task: main session auto-dispatches each
pending cycle as a cold-start Agent-tool sub-agent until all cycles are DONE OR an
escalation halts the loop.

This supersedes RAID v1.4 §13.7 Semi-AUTO (which required manual `/raid <N>` per cycle).
See `docs/plans/2026-05-29-foundation-mega-task/RAID_WORKFLOW.md` §15 for the spec.

## When to invoke /raid

- Only on the `mmo-rpg/foundation-mega-task` branch (or another RAID-eligible branch)
- After C0 has been committed (its 46 deliverables are prerequisites)
- After PRE_FLIGHT_CHECKLIST.md is signed off
- When `docs/raid/CYCLE_LOG.md` has at least one PENDING cycle whose dependencies are all DONE

## What happens when /raid is active (Coordinator pseudo-flow)

```
You (main session) are now the RAID COORDINATOR.

LOOP until all cycles DONE or escalation halts:
  1. Run: python scripts/raid/coordinator-helper.py next-cycle
     -> emits {cycle: N, brief_path: <path>, deps_satisfied: true} or {idle: true}
  2. If idle -> emit final report -> exit
  3. Read the brief at the emitted path
  4. Read scripts/raid/cycle-runner-prompt.md as the sub-agent prompt template
  5. Interpolate {cycle, brief_path, brief_summary, locked_qids} into template
  6. Run: bash scripts/raid/quota-check.sh <N> (PROCEED -> continue; RISKY -> warn + continue; WAIT -> pause-for-quota-reset escalation)
  7. Spawn Agent tool with:
       subagent_type: general-purpose
       prompt: interpolated cycle-runner template
       model: claude-opus-4-7 (cycle leader; sub-agent itself uses §14.2 tier for nested DPS)
  8. Receive <=1500-token structured summary from sub-agent:
       {result: DONE|ESCALATED|QUOTA_BLOCK, commit_sha, files_count, ...}
  9. Append AUDIT_LOG row + update CYCLE_LOG row (status, commit_sha, completed_at)
  10. If result == ESCALATED: emit escalation summary; HALT loop; ask user to investigate
  11. If result == QUOTA_BLOCK: pause; print "Wait for reset window then re-invoke /raid"; exit gracefully
  12. Otherwise: continue LOOP at step 1

Maintain Coordinator main-session token budget per RAID_WORKFLOW.md §15.2
(<=11K tokens/cycle Coordinator overhead; <=420K total over 38 cycles).
```

## Process when /raid is invoked

1. **Acknowledge:** "RAID v1.5 Coordinator mode active. Will dispatch pending cycles via Agent-tool sub-agents until all DONE or escalation."
2. **Verify prerequisites:** check `docs/raid/.session-cycle-lock` is `UNLOCKED` or empty; check at least one PENDING cycle exists in CYCLE_LOG.md; check no stale worktrees (`scripts/raid/worktrees-check.sh`).
3. **Enter LOOP** (per pseudo-flow above).
4. **Status reporting:** between cycle dispatches, briefly state "Cycle <N> DONE (sha <abbrev>, <count> files). Next: cycle <M>." Don't dump full sub-agent summaries — they're already in CYCLE_LOG.
5. **On escalation:** halt; print cycle, type, reason, suggested action.
6. **On all-done:** print foundation completion summary (38/38 cycles DONE, total wall clock, total quota burn estimate from QUOTA_LOG).

## What the sub-agent (cycle runner) does

See `scripts/raid/cycle-runner-prompt.md` for the canonical template. Summary:
- Cold-start: reads ONLY listed files (CYCLE_LOG row, brief, OPEN_QUESTIONS_LOCKED relevant sections, parent layer plan)
- Executes RAID 12-phase workflow per `docs/raid/RAID_WORKFLOW.md` §3
- May spawn nested Agent calls for DPS/Tank/Healer/Adversary/Scope Guard/Auditor (one level deep allowed)
- Writes IN_PROGRESS state file at each phase transition (P3)
- Runs scripts/raid/{startup-verifier, worktrees-create, test-infra-up-dps, secret-scan, prod-isolation-lint, verify-cycle-N, brief-structure-validator}.sh as needed
- Commits with template message (CYCLE_DECOMPOSITION.md §6 format) atomically with CYCLE_LOG update
- Returns <=1500-token structured summary to Coordinator

## What /raid does NOT do

- Does NOT execute Cycle 0 (C0 bootstrap uses default+AMAW workflow per CLAUDE.md)
- Does NOT skip phases (12-phase workflow enforced per sub-agent's workflow-gate calls)
- Does NOT bypass smoke test / verify gates (sub-agent runs verify-cycle-N.sh)
- Does NOT push to origin during cycles (per PRE_FLIGHT D3 — user pushes between cycles if desired)
- Does NOT change CLAUDE.md, prod env, or anything in `infra/existing-prod/` (B5 enforced)

## Resume semantics

If Coordinator is interrupted (quota hit, user Ctrl-C, machine restart):
- All durable state lives in `docs/raid/CYCLE_LOG.md` + `docs/audit/AUDIT_LOG.jsonl` + `docs/raid/IN_PROGRESS/cycle-<N>-state.md`
- Re-invoking `/raid` reads CYCLE_LOG, picks up the next PENDING cycle with satisfied deps
- If a cycle was mid-execution (IN_PROGRESS state exists), Coordinator hands resume responsibility to the cycle sub-agent — sub-agent runs P5 recovery-protocol-runner.sh to validate state before continuing

## Single-cycle fallback (v1.4 backwards compat)

If you want to run JUST ONE cycle manually (e.g., debugging cycle 17 in isolation):
- Do NOT invoke `/raid` (that runs the full Coordinator loop)
- Instead use the v1.4 entry: `bash scripts/raid/auto-dispatcher.py --next-cycle <N> --from-clean` then in a fresh session run the per-cycle prompt template from CYCLE_DECOMPOSITION.md §5
- This is the v1.4 Semi-AUTO mechanism; kept for backwards compat per §15.4

## After completion

Coordinator emits final report. User can:
- Inspect `docs/raid/CYCLE_LOG.md` for per-cycle outcomes
- Inspect `docs/raid/ESCALATIONS.md` (should be empty if no halts)
- Run `python scripts/raid/health-dashboard.py --all` for per-cycle health summaries
- Run `python scripts/raid/quota-summary.py` for foundation-wide quota burn
- If all 38 cycles DONE: open PR `mmo-rpg/foundation-mega-task -> main` per CYCLE_DECOMPOSITION.md §8 acceptance criteria
