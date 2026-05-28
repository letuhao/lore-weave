# Pre-Flight Checklist — Before Foundation RAID Execution

> **Purpose:** Manual sign-off items the user (project owner) MUST verify BEFORE invoking
> Cycle 0. These are items RAID cannot automate (architectural decisions, environment
> setup, credential provisioning).
>
> **Created:** 2026-05-29 (v1.2 amendment to foundation CLARIFY)
> **Sign-off required:** YES (user must check each item before C0)

---

## §1. How to use this checklist

1. Read each item below
2. Verify your environment matches the assumption
3. Check the box (or note any deviation)
4. Once ALL items checked OR deviations explicitly accepted → invoke C0
5. After C0 + smoke test pass → orchestrator auto-dispatches C1-C37

If any item CANNOT be checked, the foundation is NOT ready — resolve before C0.

---

## §2. Environment + infrastructure pre-reqs

### 2.1 Docker installed + working

- [ ] Docker Desktop or Docker Engine installed (`docker --version` returns ≥ 20.x)
- [ ] Docker Compose v2 installed (`docker compose version` returns ≥ 2.x)
- [ ] At least 50 GB free disk space (worktrees + test infra + repo grows)
- [ ] At least 16 GB RAM (per-DPS docker stacks consume ~1-2 GB each, up to 11 DPS parallel
  in cycle 4 = 11-22 GB)

### 2.2 Local foundation-dev infra reachable

- [ ] `infra/foundation-dev/docker-compose.yml` will be created by C0 (B5)
- [ ] No port conflicts on ranges 10000-20000 (RAID uses these for per-DPS isolation)
  - Verify: `lsof -i :10000-20000` returns nothing critical
- [ ] No existing containers named `raid-c*-dps*` from prior failed runs
  - Clean: `docker ps -a --filter "name=raid-c" -q | xargs docker rm -f`

### 2.3 AWS staging account (for C38 acceptance)

- [ ] AWS account dedicated for foundation-staging exists (separate from existing prod)
- [ ] AWS CLI configured with credentials for staging account
- [ ] Terraform installed (≥ 1.5) for C38 IaC apply
- [ ] If you don't have staging AWS yet → defer C38 acceptance to V1+30d; foundation
  cycles 1-37 still ship to local foundation-dev only

---

## §3. Cost + budget acknowledgment

### 3.1 Anthropic API credentials + billing

- [ ] Anthropic API key with billing enabled
- [ ] Confirmed billing cap on API key ≥ $2000 USD (foundation $1500 hard cap + $500
  buffer for retries + smoke runs)
- [ ] Budget alert configured at $1000 + $1400 (B3 cost-tracker also enforces $1500)

### 3.2 Cost expectations sign-off

- [ ] I acknowledge foundation execution estimated $570-1140; hard cap $1500
- [ ] I acknowledge per-cycle cap $50; cost-tracker auto-halts if exceeded
- [ ] I acknowledge if hard cap hit, foundation halts at last completed cycle (state
  preserved; can resume manually after investigating)

---

## §4. Source-of-truth verification

### 4.1 OPEN_QUESTIONS_LOCKED.md sanity

- [ ] Re-read [OPEN_QUESTIONS_LOCKED.md](OPEN_QUESTIONS_LOCKED.md) §1-9 (73 LOCKED items)
- [ ] No surprise resolutions (verify Q-L1A-2 glossary DB, Q-L1A-1 hybrid, Q-L1A-3 full
  audit are what you expected)
- [ ] If any LOCKED resolution is now WRONG: STOP — re-run CLARIFY for affected items
  before C0; do NOT proceed and hope to re-litigate mid-execution

### 4.2 Layer plans sanity (skim each)

- [ ] L1 — [L1_db_physical_meta.md](L1_db_physical_meta.md): 12 sub-components OK
- [ ] L2 — [L2_event_sourcing.md](L2_event_sourcing.md): 12 sub-components OK
- [ ] L3 — [L3_snapshot_projection.md](L3_snapshot_projection.md): 11 sub-components OK
- [ ] L4 — [L4_sdk_kernel_api.md](L4_sdk_kernel_api.md): 17 sub-components OK
- [ ] L5 — [L5_inbound_canon.md](L5_inbound_canon.md): 10 sub-components OK
- [ ] L6 — [L6_ws_obs_llm_prespec.md](L6_ws_obs_llm_prespec.md): 12 sub-components OK
- [ ] L7 — [L7_ops_logs_monitor.md](L7_ops_logs_monitor.md): 12 sub-components OK

### 4.3 CYCLE_DECOMPOSITION.md verification

- [ ] [CYCLE_DECOMPOSITION.md](CYCLE_DECOMPOSITION.md): 38 cycles enumerated
- [ ] Cycle 0 deliverables = 36 items per RAID_WORKFLOW.md §13.9
- [ ] Per-cycle dependency order matches your mental model (read §3 dep graph)

### 4.4 I3 amendment understanding

- [ ] [I3_INVARIANT_AMENDMENT.md](I3_INVARIANT_AMENDMENT.md): you understand Rust will
  be added for kernel-derived services (world, travel, roleplay, embedding-worker)
- [ ] You're OK with 33 total services (12 existing + 7 original new + 14 surfaced)

---

## §5. Branch + repo state

### 5.1 Branch hygiene

- [ ] On branch `mmo-rpg/foundation-mega-task` (`git branch --show-current` returns this)
- [ ] No uncommitted changes (`git status` returns clean)
- [ ] Last commit is RAID v1.2 amendment (`git log --oneline -1` shows `5ed5cd1f` or
  later)

### 5.2 Main branch sync

- [ ] `main` branch tip is known and stable
- [ ] Rebase strategy decided: if main moves during foundation execution, will RAID
  rebase periodically or wait until C38 to merge? **Recommended: rebase at C18 + C28 +
  C38 (3 checkpoints) — orchestrator can be configured to do this**
- [ ] If you choose rebase: confirm comfortable with potential conflict resolution
  (escalation row may fire)

### 5.3 Remote push policy

- [ ] Will foundation branch be pushed to origin during execution OR only at C38?
  **Recommended: NEVER push during execution; only push at C38 with batch review** —
  reduces risk of partial state visible to other contributors
- [ ] If pushing during execution: confirm CI does NOT auto-deploy from this branch

---

## §6. Existing LoreWeave prod safety

### 6.1 Production isolation acknowledgment

- [ ] I acknowledge B5 enforces: foundation cycles do NOT touch `prod.loreweave.app`
  OR any existing prod DB/Redis/MinIO
- [ ] I acknowledge migration from existing prod → foundation prod is a SEPARATE
  sub-program after C38
- [ ] If foundation cycles accidentally hit existing prod: `prod-isolation-lint.sh`
  blocks the commit; ESCALATIONS row written

### 6.2 Existing service operations

- [ ] Existing LoreWeave novel-platform 12 services continue to run normally during
  foundation execution
- [ ] No team member will deploy breaking changes to existing services during the
  ~weeks of foundation execution (or accept that rebase at C18/C28/C38 handles drift)

---

## §7. Glossary-service coordination (Q-L1A-2 + Q-L5A-1)

### 7.1 Glossary outbox migration

- [ ] I understand Q-L5A-1: glossary-service outbox migration is a SEPARATE sub-program
  (not foundation)
- [ ] Foundation cycle 23 ships the contract + test fixture; actual glossary-service
  outbox implementation happens in a parallel novel-platform sub-program
- [ ] If glossary outbox migration is NOT ready by C24 (meta-worker canon consumer):
  C24 still completes (consumer code shipped), but L5 push flow won't activate end-to-end
  until glossary outbox lands
- [ ] Acceptance: C24 verify is unit/integration test against mock outbox; not
  end-to-end with glossary

### 7.2 Canon table location (Q-L1A-2)

- [ ] I understand canon_entries + canonization_audit + book_authorship + canon_change_log
  live in glossary DB, NOT meta DB
- [ ] Service map line 71 + line 19 amendment is part of Cycle 7 PR

---

## §8. Sub-program coordination

### 8.1 Out-of-foundation work pipeline

The following sub-programs are NOT foundation; coordinate scheduling:

- [ ] **Actor substrate** (EF/RES/PL/TDIL/AIT/PROG) — starts after C38
- [ ] **V1+30d Plan** (geography GEO_001..ROUTE_001 + travel TVL_001..005) — was blocked
  by foundation, can start after C38
- [ ] **Glossary outbox migration** (Q-L5A-1) — can start in parallel with foundation
  cycles 1-22
- [ ] **Existing prod → foundation prod migration** — separate sub-program after C38

### 8.2 Team handoffs

- [ ] Foundation execution is solo-Claude (no human contributors needed during cycles)
- [ ] Escalations require user (you) to review + decide; estimate: 2-5 escalations
  across 38 cycles based on complexity
- [ ] Expected user time commitment: 2-4 hours total across the foundation execution
  (escalation triage + C38 acceptance review)

---

## §9. Operational readiness

### 9.1 Monitoring during execution

- [ ] You will check `docs/raid/CYCLE_LOG.md` periodically (daily?)
- [ ] You will check `docs/raid/ESCALATIONS.md` for any halt (alerts if present)
- [ ] You will check `docs/raid/COST_LOG.jsonl` to track budget vs cap
- [ ] You will check `scripts/raid/health-dashboard.py` output for context health

### 9.2 Emergency stop

- [ ] You understand: ctrl-C during `auto-dispatcher.py` halts orchestrator
- [ ] You understand: `docs/raid/.session-cycle-lock` removal force-stops next cycle
- [ ] You understand: `git reset --hard <commit>` rolls back to specific cycle if needed
- [ ] You will NOT delete `docs/raid/IN_PROGRESS/` files mid-cycle (corrupts state)

---

## §10. Sign-off

- [ ] All items above checked OR deviations explicitly documented in a NOTES section
  below

```
NOTES (deviations from defaults):
(if any — paste here)
```

- [ ] **User signature:** ______________  **Date:** ______________
- [ ] **Confirmation:** I am ready to invoke Cycle 0 with the understanding that RAID
  v1.2 (with §12 + §13 protections) will autonomously execute cycles 1-37 after C0
  smoke green. Escalations will halt execution and notify me.

---

## §11. Invoking Cycle 0

Once all items signed off:

```
git checkout mmo-rpg/foundation-mega-task
git pull  # ensure latest commits
# do NOT push yet

# Cycle 0 runs in DEFAULT workflow (not RAID — bootstrap problem)
# Per CLAUDE.md /amaw is OK for L+ tasks; C0 is M-L
/amaw

# Then paste:
"""
Execute Cycle 0 of the foundation mega-task per docs/plans/2026-05-29-foundation-mega-task/CYCLE_DECOMPOSITION.md
§Cycle 0.

This is the BOOTSTRAP cycle - RAID infrastructure setup. After C0 ships and smoke test
passes, the auto-dispatcher will fire `/raid 1` automatically (per RAID_WORKFLOW.md
§13.7).

Ship all 36 deliverables listed in RAID_WORKFLOW.md §13.9:
- 5 v1.0 core
- 10 v1.1 §12 context protection scripts
- 21 v1.2 §13 production-readiness scripts + dirs + config

Verify with smoke test exercising all 10 P-protections + 6 B-protections on a no-op
helloworld cycle.

Hard exit criteria:
- All 38 cycle briefs auto-generated + validated by brief-structure-validator
- Smoke test exits 0
- Cost so far < $50

On smoke green: 60-second pause then auto-dispatch /raid 1.
On smoke fail: ESCALATIONS row + halt.
"""
```

Foundation RAID execution is now in your hands. Good luck.
