# Cycle 0 Bootstrap — Fresh Session Invocation

> **Purpose:** Hand-off doc for user to start Cycle 0 in a FRESH Claude Code session.
> **Created:** 2026-05-29 by CLARIFY session (after 6 commits of CLARIFY + RAID v1.3 amendments)
> **Why fresh session:** Per RAID_WORKFLOW.md §12.1 / P1, even Cycle 0 (which runs default
> workflow, not RAID) benefits from fresh context. CLARIFY session was ~200K+ tokens.

---

## Step 1: Verify environment

```bash
cd d:/Works/source/lore-weave-game-foundation
git checkout mmo-rpg/foundation-mega-task
git pull --rebase origin mmo-rpg/foundation-mega-task  # ensure latest
git log --oneline -10  # confirm 6 CLARIFY commits + 1 skeleton commit present
```

Expected latest commits:
```
<latest-sha> docs(raid): Cycle 0 pre-stage skeleton + handoff
d1adbc17 docs(foundation): RAID v1.3 — §14 quota-aware execution
92bc4088 docs(foundation): RAID v1.2 amendment — §13 production-readiness BLOCKERs
5ed5cd1f docs(foundation): RAID v1.1 amendment — §12 context management protections
34787c4c docs(foundation): CLARIFY COMPLETE — L7 added + 4 final artifacts + 73 Qs LOCKED
12d2b484 docs(foundation): CLARIFY L2-L6 deep-dive — all 6 layers enumerated
3e7d2425 docs(foundation): CLARIFY L1 deep-dive — DB physical + meta registry
```

## Step 2: Sign off PRE_FLIGHT_CHECKLIST.md

Read [docs/plans/2026-05-29-foundation-mega-task/PRE_FLIGHT_CHECKLIST.md](../plans/2026-05-29-foundation-mega-task/PRE_FLIGHT_CHECKLIST.md)
and check each item §2-§9. Note any deviations in §10 NOTES section.

**Critical items to verify before C0:**
- §2.1 Docker installed
- §2.2 Ports 10000-20000 available
- §3.1 Max 20x subscription confirmed
- §3.2 Wall-clock 2-3 weeks acknowledged
- §5.1 On branch `mmo-rpg/foundation-mega-task`, clean tree
- §6.1 Existing prod isolation acknowledged

## Step 3: Open fresh Claude Code session

**Important:** EXIT this session first. Open a new Claude Code instance OR clear current.

## Step 4: Invoke `/amaw` (Cycle 0 uses default+AMAW workflow, NOT RAID)

Per CLAUDE.md, Cycle 0 is size L → /amaw is appropriate. Cycle 0 is the bootstrap; it
delivers the RAID orchestrator itself, so it cannot use RAID.

```
/amaw
```

## Step 5: Paste the following prompt

```
Execute Cycle 0 of the foundation mega-task per
docs/plans/2026-05-29-foundation-mega-task/CYCLE_DECOMPOSITION.md §"Cycle 0".

CONTEXT — what I'm working on:
- Branch: mmo-rpg/foundation-mega-task (already checked out, clean)
- Foundation mega-task: build 7-layer foundation infrastructure for LLM MMO RPG engine
- This is the BOOTSTRAP cycle — ship RAID v1.3 infrastructure scripts so cycles 1-37
  can execute autonomously via /raid <N>

REQUIRED READING (in this order):
1. docs/plans/2026-05-29-foundation-mega-task/RAID_WORKFLOW.md (all sections §1-§14)
2. docs/plans/2026-05-29-foundation-mega-task/CYCLE_DECOMPOSITION.md §"Cycle 0"
3. docs/plans/2026-05-29-foundation-mega-task/OPEN_QUESTIONS_LOCKED.md (73 LOCKED items)
4. docs/raid/BEGIN_CYCLE_0.md (this file — for orientation)
5. Skeleton files already pre-staged: docs/raid/{CYCLE_LOG.md, ESCALATIONS.md,
   AUDIT_LOG.jsonl, QUOTA_LOG.jsonl, RESET_SCHEDULE.md, .session-cycle-lock,
   IN_PROGRESS/README.md}

DELIVERABLES (43 items per RAID_WORKFLOW.md §13.9 + §14.10):

Core v1.0 (5):
- scripts/raid/orchestrator.py — main RAID dispatcher
- scripts/raid/verify-cycle-template.sh — template for per-cycle verify scripts
- scripts/raid/escalation-writer.py — appends ESCALATIONS.md rows
- docs/raid/{AUDIT_LOG.jsonl, CYCLE_LOG.md, ESCALATIONS.md, cycle_briefs/} — DONE (pre-staged)
- Copy of RAID_WORKFLOW.md to docs/raid/

§12 v1.1 context protections (10):
- scripts/raid/startup-verifier.sh (P2)
- scripts/raid/in-progress-state-writer.py (P3)
- scripts/raid/compaction-detector.py (P5)
- scripts/raid/post-commit-verifier-prompt.md (P9)
- scripts/raid/health-dashboard.py (P10)
- scripts/raid/files-from-cycle.sh (P7)
- docs/raid/IN_PROGRESS/ + _archive/ dirs — DONE (pre-staged)
- docs/raid/.session-cycle-lock — DONE (pre-staged)
- docs/raid/cycle_briefs/TEMPLATE.md (P6 canonical brief)

§13 v1.2 production-readiness (21):
- scripts/raid/worktrees-{create,cleanup,check}.sh (B1)
- scripts/raid/test-infra-{up,down}-dps.sh (B2)
- scripts/raid/test-infra-template.docker-compose.yml (B2)
- scripts/raid/cost-tracker.py (B3, dual-use)
- scripts/raid/cost-summary.py (B3, dual-use)
- scripts/raid/brief-generator.py (B4)
- scripts/raid/brief-structure-validator.sh (B4)
- scripts/raid/regenerate-briefs.sh (B4)
- scripts/raid/prod-isolation-lint.sh (B5)
- .gitleaks.toml (B6)
- scripts/raid/secret-scan-{dps,cycle,final}.sh (B6)
- scripts/raid/run-smoke-test.sh (AUTO gate)
- scripts/raid/auto-dispatcher.py (AUTO gate)
- docs/raid/cycle_briefs/00X_helloworld_smoke.md (AUTO gate)
- infra/foundation-dev/docker-compose.yml (B5)
- infra/foundation-staging/terraform/ skeleton (B5)
- ../foundation-worktrees/ + _archive/ + _quarantine/ dirs (B1, B6)

§14 v1.3 quota-aware (7):
- contracts/raid/quota-profile.yaml (Q3, currently: max-20x)
- scripts/raid/quota-check.sh (Q4)
- scripts/raid/sub-agent-spawn.py (Q2 model tiering)
- scripts/raid/quota-summary.py (Q7)
- scripts/raid/session-counter.py (Q8)
- docs/raid/QUOTA_LOG.jsonl — DONE (pre-staged)
- docs/raid/RESET_SCHEDULE.md — DONE (pre-staged)

PLUS: brief-generator.py must auto-generate all 37 cycle briefs into
docs/raid/cycle_briefs/<NN>_<short>.md following §4 template + 4000 token cap.

EXIT CRITERIA:
1. All 43 deliverables present
2. All 37 cycle briefs generated + validated by brief-structure-validator
3. Smoke test cycle 00X_helloworld passes end-to-end:
   - Exercises ALL 10 P-protections + 6 B-protections + Q-protections
   - Uses Sonnet/Haiku sub-agents per §14.2 model tiering
   - Completes within ~$5 worth of tokens (or ~50K Raid Leader tokens)
4. Auto-dispatcher with 60-second pause window functional
5. .session-cycle-lock sentinel writes correctly
6. SESSION_PATCH.md updated with C0 completion
7. Single commit with all 43 deliverables + smoke test evidence

AFTER C0 GREEN:
The auto-dispatcher will pause 60 seconds then fire /raid 1 automatically.
User has 60 seconds to ctrl-C if anything looks wrong.

HARD RULES:
- This is Cycle 0 ONLY. Do not start Cycle 1.
- Cost cap for C0: ~$5 (subscription user — token estimate ~50-100K Raid Leader + ~150-300K
  sub-agent tokens equivalent ≈ 5-10% of 5h window)
- If smoke fails: write ESCALATIONS row, do NOT auto-dispatch C1, halt.

Begin with /amaw workflow Phase 1 (CLARIFY) reading the required-reading list above.
```

## Step 6: Monitor C0 execution

User observes:
- Token usage via Claude Code status bar
- File creation via `git status` periodically
- Any escalation messages

Expected wall-clock for C0: **3-5 hours** (writing 43 scripts + validating + smoke test).

## Step 7: After C0 smoke green

Auto-dispatcher fires `/raid 1` in 60 seconds. If you want to investigate something first:
- Press ctrl-C within the 60s window
- Investigate
- Manually invoke `/raid 1` later

Otherwise: foundation execution begins automatically.

---

## What's already done by CLARIFY session (saved you time)

Pre-staged skeleton files (committed in this branch, ready for C0 to reference/extend):

| File | Purpose |
|---|---|
| `docs/raid/CYCLE_LOG.md` | Status board with all 39 cycles PENDING |
| `docs/raid/ESCALATIONS.md` | Empty, schema documented |
| `docs/raid/AUDIT_LOG.jsonl` | One init line |
| `docs/raid/QUOTA_LOG.jsonl` | One init line, max-20x plan noted |
| `docs/raid/RESET_SCHEDULE.md` | Quota reset window docs |
| `docs/raid/.session-cycle-lock` | UNLOCKED sentinel |
| `docs/raid/IN_PROGRESS/README.md` | Schema docs |
| `docs/raid/cycle_briefs/` | Empty dir (briefs auto-gen in C0) |
| `scripts/raid/` | Empty dir |
| `contracts/raid/` | Empty dir |
| `docs/raid/BEGIN_CYCLE_0.md` | This file |

**Good luck. 🚀**
