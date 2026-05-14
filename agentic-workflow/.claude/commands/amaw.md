---
description: Enable AMAW (Autonomous Multi-Agent Workflow) mode for the current task. Spawns cold-start sub-agents at REVIEW + POST-REVIEW phases instead of using main-session self-review.
---

# /amaw — Enable AMAW mode for this task

By default, this project uses the v2.2 human-in-loop workflow (see `WORKFLOW.md`). Invoke `/amaw` to enable the AMAW extension (see `AMAW.md`) for the current task only.

## When to invoke /amaw

| Use case | Why AMAW pays off |
|---|---|
| Data migration (vector dim, schema change) | Cache coherence, side effects easy to miss |
| New service boundary / multi-system contract | Edge cases compound across components |
| Security-critical path (auth, tenant isolation, destructive ops) | Author blindness is a real risk |
| Bulk operation affecting >1 project | Cross-project side effects hard to enumerate |

Don't invoke for: single-file bugs, doc updates, small refactors. Token cost (~$1-5/task) only pays off at L+ size.

## What changes when /amaw is active

1. **Phase 3 REVIEW (design):** spawn Adversary cold-start sub-agent instead of self-review. Re-spawn until APPROVED.
2. **Phase 7 REVIEW (code):** same — Adversary cold-start, fresh per round.
3. **Phase 8 QC + Phase 9 POST-REVIEW:** spawn Scope Guard for conservative final gate.
4. **Phase 10 SESSION:** optionally spawn Scribe to write `docs/sessions/SESSION_PATCH.md` or `docs/03_planning/<TRACK>/SESSION_HANDOFF.md` (depending on whether the task is main-project or a design track).
5. **AUDIT_LOG.jsonl** at `docs/audit/AUDIT_LOG.jsonl` is the single source of truth for phase transitions + agent verdicts. Append-only.
6. **Phase 12 RETRO:** call ContextHub `add_lesson` with `project_id = "mmo-rpg-zone-map-design-non-human-in-loop"` for any non-obvious decision/workaround discovered during the task.

See `docs/amaw-workflow.md` (installed from `AMAW.md`) for full prompt templates, the "Repo integration" section, and operational details.

## Process when /amaw is invoked

1. **Acknowledge:** "AMAW mode enabled for this task. Default v2.2 workflow remains for future tasks."
2. **Append `amaw_enabled` event to AUDIT_LOG.jsonl** with current task slug + timestamp.
3. **At each REVIEW phase:** use the Adversary prompt template from `AMAW.md`. Spawn via Agent tool with `subagent_type: general-purpose` (or whichever the host supports). The sub-agent must:
   - Read ONLY the files listed in the prompt — never the chat history
   - Find EXACTLY 3 problems (BLOCK or WARN). Never say what is good.
   - Append verdict event to AUDIT_LOG.jsonl + detailed findings to `docs/audit/findings-<task>-r<N>.md`
4. **On REJECTED:** fix the findings, re-spawn the Adversary, increment round number. No self-authorized skips.
5. **At POST-REVIEW:** spawn Scope Guard. CLEAR → proceed. BLOCKED → fix → re-run.
6. **At SESSION:** ensure AUDIT_LOG has all phase events + the `sprint_complete` event at end.

## Calibration

Don't run AMAW at maximum intensity blindly. Calibrate by size:

| Size | Rounds |
|---|---|
| **S** | 1 Adversary code review only (skip design review). |
| **M** | 1 design + 1 code review + Scope Guard. Stop at first APPROVED_WITH_WARNINGS. |
| **L** | Up to 3 design + 2 code review rounds + Scope Guard. |
| **XL** | Full AMAW + subagent dispatch for parallel sub-tasks. |

**Run `tsc --noEmit` (or equivalent static checker) before each Adversary code-review round.** Phase 14 case study: round 3 of design review caught only a typo-level BLOCK (missing fs import) that the type-checker would have caught for free.

## Stop condition

APPROVED_WITH_WARNINGS after round 2 is acceptable. Document "pragmatic stop" + residual risk in AUDIT_LOG. Don't chase APPROVED across endless rounds.

## What this command does NOT do

- Does NOT change the default workflow for future tasks
- Does NOT modify CLAUDE.md or settings.json
- Does NOT skip any v2.2 phases (CLARIFY, PLAN, BUILD, VERIFY, SESSION, COMMIT, RETRO all still run)
- Is per-task only — explicitly invoke `/amaw` again for the next task if needed

## After completion

When the task closes, just commit normally. The AUDIT_LOG.jsonl and DEFERRED.md updates carry forward as durable history. The next task starts in default v2.2 mode unless `/amaw` is invoked again.
