# RAID — Recursive Autonomous Implementation Drive Workflow Spec

> **Version:** RAID v1.0
> **Status:** SPEC — locked 2026-05-29 by foundation mega-task CLARIFY
> **Parallel to:** AMAW v3.0 (Autonomous Multi-Agent Workflow) and v2.2 (human-in-loop)
> **Replaces AMAW:** NO — RAID is a SEPARATE workflow for tasks where 100% autonomous execution is required (no human checkpoint per cycle)

---

## §1. When to invoke RAID

RAID is invoked via `/raid` at task start. Use RAID ONLY when:

- ✅ Task is a **mega-task** decomposed into many (5+) cycles with **strict dependencies** (e.g., foundation build)
- ✅ Plan is **comprehensively written** with locked acceptance criteria + lockfile of decisions (this CLARIFY's OPEN_QUESTIONS_LOCKED.md is the prototype)
- ✅ Cycle artifacts are **purely automatable** (CI exit code = pass/fail; no human read of test output required)
- ✅ Human is OK with **batch review at the end** (not per-cycle stop)

Do NOT invoke RAID when:

- ❌ Single task ≤ L size (use AMAW or default workflow)
- ❌ Open design questions remain (resolve first via CLARIFY)
- ❌ Acceptance criteria involve human judgment (UX, prose quality, design taste)
- ❌ Cycle touches sensitive production state with no rollback path

**Default for the LoreWeave repo:** v2.2 (human-in-loop). Opt-in to AMAW (`/amaw`) for L+ tasks that need adversarial review. Opt-in to RAID (`/raid`) ONLY when a multi-cycle mega-plan exists.

---

## §2. RAID role contract

| Role | Cold-start? | Spawn pattern | Owns |
|---|---|---|---|
| **Raid Leader** | NO (main session) | n/a | Orchestration, dispatch DPS, gather output, write CYCLE_LOG row |
| **Tank** | YES per cycle | Sub-agent (general-purpose, isolation:worktree) | Architecture guard, kernel invariant defense, integration rebase of DPS branches |
| **DPS (1..N)** | YES per cycle, parallel worktrees | Sub-agents (general-purpose, isolation:worktree, run_in_background:true) | Build one slice of cycle in own worktree per the brief's DPS plan |
| **Healer** | YES per cycle | Sub-agent (general-purpose, isolation:worktree) | Test repair + regression chaser AFTER Tank rebase |
| **Adversary** | YES per cycle | Sub-agent (general-purpose, NO worktree — reviews diff only) | Cold-start code review (carry-over from AMAW v3.0) |
| **Scope Guard** | YES per cycle | Sub-agent (general-purpose, NO worktree — reviews diff vs brief) | Brief-vs-diff comparison (carry-over from AMAW v3.0; auto POST-REVIEW) |
| **Auditor** | YES per cycle | Sub-agent (general-purpose, reads logs) | Writes AUDIT_LOG.jsonl row + CYCLE_LOG.md entry |

**Cold-start = sub-agent invoked with no context except the brief + diff.** Prevents author-blindness rubber-stamping.

---

## §3. Twelve phases mapped (RAID variant)

```
1. CLARIFY → 2. DESIGN → 3. REVIEW → 4. PLAN → 5. BUILD → 6. VERIFY →
7. REVIEW → 8. QC → 9. POST-REVIEW → 10. SESSION → 11. COMMIT → 12. RETRO
```

Each cycle runs all 12 phases. Roles per phase:

| Phase | Default v2.2 | AMAW v3.0 | **RAID v1.0** |
|---|---|---|---|
| 1. CLARIFY | Architect + PO | Main + Scribe | **Raid Leader reads cycle brief; NO new clarify** (CLARIFY was done at foundation level) |
| 2. DESIGN | Lead | Main | **Raid Leader applies brief's design choices** (no new design — brief is authoritative) |
| 3. REVIEW (design) | PO + Lead self-review | Adversary cold-start | **Raid Leader self-check vs brief** (design is locked; mismatch = STOP + escalation row) |
| 4. PLAN | Lead + Developer | Main + Scribe | **Raid Leader writes per-DPS task assignments** + spawns worktrees |
| 5. BUILD | Developer (TDD) | Main | **DPS sub-agents in parallel worktrees**; each runs full TDD per its slice |
| 6. VERIFY | Developer (evidence gate) | Main | **DPS runs verify-slice; Tank rebases; Healer fixes regressions; Raid Leader runs `verify-cycle-<N>.sh`** |
| 7. REVIEW (code) | Lead self-review | Adversary cold-start | **Adversary sub-agent cold-start** — reads cycle brief + full diff + verify evidence |
| 8. QC | QA / PO | Scope Guard | **Scope Guard sub-agent** — same as AMAW; checks for scope drift |
| 9. POST-REVIEW | Human checkpoint — WAIT | Scope Guard | **AUTO Scope Guard comparison** — emits CLEAR or BLOCKED; NO human wait |
| 10. SESSION | Developer | Scribe | **Auditor sub-agent** writes AUDIT_LOG.jsonl + CYCLE_LOG.md row |
| 11. COMMIT | Developer | Main | **Raid Leader** commits with template message + amends CYCLE_LOG status=DONE in same commit |
| 12. RETRO | All — add_lesson | Audit Logger | **Auditor sub-agent** writes RETRO row to AUDIT_LOG.jsonl |

**Key RAID differences from AMAW:**
1. **Phase 1 (CLARIFY) is a no-op** — CLARIFY was done at foundation level (this folder)
2. **Phase 3 (design REVIEW) is self-check only** — design is locked in cycle brief
3. **Phase 5 (BUILD) spawns DPS sub-agents in parallel worktrees**
4. **Phase 6 (VERIFY) is purely CI-gate** — `scripts/raid/verify-cycle-<N>.sh` exit 0 = pass
5. **Phase 9 (POST-REVIEW) is AUTO** — Scope Guard sub-agent, no human wait
6. **Phase 11 (COMMIT) updates CYCLE_LOG in same commit** (proves cycle done atomically)

---

## §4. Phase-by-phase detail

### Phase 1 — CLARIFY (no-op in RAID)

**Action:** Raid Leader reads `docs/raid/cycle_briefs/<NN>_<short>.md`. Confirms scope matches brief. If brief is missing or malformed → STOP + ESCALATIONS.md row + abort cycle.

**No new clarification with user.** Foundation CLARIFY is the lockfile.

**Output:** Cycle brief loaded into Raid Leader context.

---

### Phase 2 — DESIGN (apply brief, no new design)

**Action:** Raid Leader applies the brief's enumerated artifacts list. Cross-references parent layer plan (L1-L7 files) and cited kernel chunks for full spec.

**If brief enumerates a deliverable Raid Leader doesn't know how to build:** STOP + ESCALATIONS.md row (this is a CLARIFY-time miss).

**Output:** Per-DPS task assignments (file lists) for Phase 4.

---

### Phase 3 — REVIEW (design self-check)

**Action:** Raid Leader compares planned DPS task assignments against:
- Brief's `Scope (IN)` — must cover all listed artifacts
- Brief's `Scope (OUT)` — must NOT touch out-of-scope items
- LOCKED decisions consumed — list must be enumerable

**Output:** GO or STOP+escalation.

---

### Phase 4 — PLAN (DPS dispatch plan)

**Action:** Raid Leader:
1. Creates a git worktree per DPS slice (`git worktree add ../cycle-<N>-dps-<I>`)
2. Writes a self-contained prompt for each DPS containing:
   - DPS's slice scope (file list)
   - Acceptance for that slice (TDD test list)
   - Cross-DPS dependencies (which other DPS's files this DPS reads but doesn't write)
   - LOCKED decisions relevant to slice
3. Spawns N DPS agents in parallel (Agent tool with `run_in_background:true, isolation:"worktree"`)

**Output:** N background DPS agents running.

---

### Phase 5 — BUILD (DPS sub-agents in parallel worktrees)

**Action:** Each DPS independently:
1. Reads its prompt
2. TDD: writes acceptance tests FIRST
3. Implements slice until tests pass
4. Runs slice-local verification (cargo test / go test / etc.)
5. Commits to its worktree branch
6. Returns control with the worktree path

**Raid Leader receives completion notifications** (no polling — runtime auto-notifies).

**On DPS failure:** Raid Leader logs failure + retries that specific DPS (counts toward cycle's 3-retry budget).

**Output:** N worktrees with committed branches.

---

### Phase 6 — VERIFY (Tank rebase + Healer + cycle-wide gate)

**Step 1: Tank rebase (cold-start sub-agent).**
- Spawns Tank sub-agent with prompt: "Rebase these N worktree branches onto main, in dependency order. Resolve conflicts conservatively. Run integration test after rebase."
- Tank merges branches sequentially, resolving conflicts.
- On conflict Tank can't resolve → STOP + ESCALATIONS.md.

**Step 2: Healer regression chase (cold-start sub-agent).**
- Spawns Healer sub-agent: "Run full test suite. For each failure, fix root cause. Do not modify tests to pass — only modify implementation."
- Healer iterates until tests green OR 3 attempts fail.

**Step 3: Cycle-wide verify script.**
- Raid Leader runs `scripts/raid/verify-cycle-<N>.sh`.
- Exit 0 = VERIFY PASS.
- Non-zero = VERIFY FAIL → goto retry path.

**Retry path on VERIFY fail:**
- Retry counter ++
- If counter ≤ 3: re-spawn DPS slice that caused failure (identifiable from CI output)
- If counter > 3: write ESCALATIONS.md row + ABORT cycle

**Output (success):** All tests green; verify-cycle-<N>.sh exit 0.

---

### Phase 7 — REVIEW (Adversary cold-start)

**Action:** Spawn Adversary sub-agent (NO worktree — reads diff via `git diff main...HEAD`).

**Prompt to Adversary:** "You are an adversarial reviewer. The cycle brief and full diff are below. Find issues: bugs, missing requirements, scope creep, security flaws, performance regressions. Return FINDINGS list with severity (blocker / major / minor / note)."

**Raid Leader processes findings:**
- 0 blockers + 0 majors → continue to Phase 8
- ≥1 blocker → STOP + retry cycle with fix (counts toward 3-retry budget)
- Only minors/notes → continue (note in CYCLE_LOG for future)

**Output:** Findings list + GO/STOP decision.

---

### Phase 8 — QC (Scope Guard pre-check)

**Action:** Spawn Scope Guard sub-agent (NO worktree — reads brief + diff).

**Prompt:** "Compare diff against cycle brief. Return CLEAR or BLOCKED. CLEAR criteria: all IN-scope items built + no OUT-scope items touched + acceptance criteria met. BLOCKED: any of these fails — return specific reason."

**On BLOCKED:** STOP + retry cycle (counts toward 3-retry budget).

---

### Phase 9 — POST-REVIEW (AUTO Scope Guard)

**Action:** Spawn second Scope Guard sub-agent for AUTO check (no human wait).

**Prompt:** "You are the final pre-commit reviewer. Read the cycle brief, full diff, verify-cycle-<N>.sh output, Adversary findings list, prior Scope Guard QC result. Emit CLEAR (proceed to commit) or BLOCKED (write ESCALATIONS.md and abort)."

**Behavior:**
- CLEAR → proceed to SESSION
- BLOCKED → ESCALATIONS.md row + abort cycle

**This is the RAID-defining phase.** AMAW v3.0 stops here for human review; RAID auto-comparisons against the brief.

---

### Phase 10 — SESSION (Auditor writes audit log)

**Action:** Spawn Auditor sub-agent.

**Prompt:** "Write a JSONL row to docs/raid/AUDIT_LOG.jsonl with fields: cycle, started_at, completed_at, dps_count, retry_count, adversary_findings_count, scope_guard_blocks, escalations_written. Then append a row to docs/raid/CYCLE_LOG.md with cycle number, title, status=DONE, completed_at, key decisions, file list."

**Output:** AUDIT_LOG.jsonl + CYCLE_LOG.md updated.

---

### Phase 11 — COMMIT (Raid Leader)

**Action:** Raid Leader stages all changed files + the SESSION updates. Commits with template message (see CYCLE_DECOMPOSITION.md §6). The CYCLE_LOG.md update is in the SAME COMMIT as the code change (atomic proof of completion).

**Output:** Single commit. Branch advanced by one.

---

### Phase 12 — RETRO (Auditor)

**Action:** Auditor sub-agent reflects on cycle:
- What went smoothly?
- What surprised? (drift from CLARIFY assumptions)
- What should next cycle avoid?

Writes a one-line RETRO entry to AUDIT_LOG.jsonl with `phase=retro`.

**No `add_lesson` to ContextHub** (RAID doesn't use ContextHub — too automated for that loop). Future improvement: ContextHub integration.

---

## §5. Escalation flow

When a cycle aborts (3-retry exhaustion, Scope Guard BLOCKED, Adversary blocker uncorrectable):

```
1. Raid Leader writes ESCALATIONS.md row:

   ## Cycle <N> — <Title> — ESCALATED <date>
   
   ### Failure mode
   <one paragraph: which phase failed, what fixes were tried>
   
   ### 3 retry attempts (if applicable)
   - Attempt 1: <fix tried> → <why failed (last 10 lines of error output)>
   - Attempt 2: <fix tried> → <why failed>
   - Attempt 3: <fix tried> → <why failed>
   
   ### Suggested escalation type
   - [ ] Kernel design gap (CLARIFY missed something)
   - [ ] External dependency (waiting on novel-platform team / vendor)
   - [ ] Unclear spec (brief was ambiguous)
   - [ ] Other: <describe>
   
   ### Suggested human action
   <what user should do to unblock>
   
   ### Pending dependencies
   <which cycles can still proceed without this; which are blocked>

2. Update CYCLE_LOG.md row: status=ESCALATED, completed_at=now()
3. Workflow HALTS. RAID does not advance to next cycle.
4. Human picks up from ESCALATIONS.md row.
```

---

## §6. Audit trail schemas

### `docs/raid/AUDIT_LOG.jsonl` (append-only JSONL)

```jsonl
{"ts":"2026-05-29T12:34:56Z","cycle":1,"phase":"clarify","event":"start","brief":"docs/raid/cycle_briefs/01_l1e_meta_ha.md"}
{"ts":"...","cycle":1,"phase":"plan","event":"dps_spawn","count":4,"worktrees":["../cycle-1-dps-1",...]}
{"ts":"...","cycle":1,"phase":"build","event":"dps_complete","dps_id":1,"branch":"cycle-1-dps-1"}
{"ts":"...","cycle":1,"phase":"verify","event":"verify_script_exit","exit_code":0}
{"ts":"...","cycle":1,"phase":"review","event":"adversary_findings","blockers":0,"majors":0,"minors":2,"notes":1}
{"ts":"...","cycle":1,"phase":"post_review","event":"scope_guard","result":"CLEAR"}
{"ts":"...","cycle":1,"phase":"commit","event":"commit","sha":"abc123","files_count":24}
{"ts":"...","cycle":1,"phase":"retro","event":"retro","note":"DPS-3 took 3x longer than DPS-1; consider splitting at L1.E sync replica setup"}
```

### `docs/raid/CYCLE_LOG.md` (human-readable, append-only)

```markdown
## Cycle 1 — L1.E Meta HA Infrastructure — DONE 2026-MM-DD

**Brief:** docs/raid/cycle_briefs/01_l1e_meta_ha.md
**Duration:** 4h 23min (DPS parallel)
**DPS:** 4 (primary, sync, async, Patroni)
**Retries:** 0
**Adversary findings:** 0 blockers, 0 majors, 2 minors, 1 note
**Scope Guard:** CLEAR
**verify-cycle-1.sh:** exit 0

### Key decisions consumed
- Q-L1E-1: cross-region DR deferred V3+
- Q-L1E-2: etcd self-hosted

### Notable
- DPS-3 (async replica) took 3x longer due to AWS API rate limit; throttled retries handled it. Recommendation: stagger DPS launches for IaC-heavy slices.

### Files touched
<list of 27 files>
```

### `docs/raid/ESCALATIONS.md` (append-only — only on aborts)

See §5 schema above.

---

## §7. Bootstrap (Cycle 0 — RAID infrastructure)

Cycle 0 ships the workflow infrastructure. It runs in **DEFAULT WORKFLOW** (NOT RAID — chicken-and-egg). After Cycle 0 ships, all subsequent cycles use RAID.

**Cycle 0 deliverables:**
- `scripts/raid/orchestrator.py` — main RAID dispatcher
- `scripts/raid/verify-cycle-template.sh` — template for per-cycle verify scripts
- `scripts/raid/escalation-writer.py` — appends ESCALATIONS.md row
- `scripts/raid/audit-logger.py` — appends AUDIT_LOG.jsonl
- `docs/raid/RAID_WORKFLOW.md` — copy of this file (or symlink)
- `docs/raid/AUDIT_LOG.jsonl` — empty file
- `docs/raid/CYCLE_LOG.md` — skeleton
- `docs/raid/ESCALATIONS.md` — skeleton
- `docs/raid/cycle_briefs/` directory — 37 pre-written cycle briefs (one .md per cycle)

**Smoke test for Cycle 0:** orchestrator runs a no-op cycle (`hello-world` cycle brief) end-to-end through all 12 phases. Verifies AUDIT_LOG appends, CYCLE_LOG appends, ESCALATIONS not triggered, commit happens.

---

## §8. Cost model

Estimated tokens per cycle (RAID):

| Role | Tokens per cycle | Notes |
|---|---|---|
| Raid Leader (main) | ~50K | Orchestration overhead |
| Tank (cold-start) | ~30K | Reads diff + rebases |
| DPS × N | ~80K × N | Each DPS reads its brief + implements |
| Healer | ~20K | Test fixing |
| Adversary | ~40K | Reads diff + brief; outputs findings |
| Scope Guard × 2 | ~20K × 2 | Brief comparison |
| Auditor | ~5K | Writes audit log |

For a 4-DPS cycle: ~50 + 30 + 320 + 20 + 40 + 40 + 5 = **~505K tokens / cycle**.

At Opus 4.7 pricing (~$15/M input, $75/M output, rough estimate): **~$15-30 per cycle**.

**Full foundation (38 cycles):** ~$570-1140 total. Significant cost. Recommend running RAID only when manual cost would be ~$5K+ (e.g., 5+ weeks of dev time for the foundation build).

---

## §9. Failure modes + mitigations

| Failure | Mitigation |
|---|---|
| Sub-agent goes off-script | Cold-start prompts are self-contained + scope-bounded; runtime kills if exceeds budget |
| DPS worktrees diverge irreconcilably | Tank rebases conservatively; conflict → ESCALATIONS |
| CI flakiness causes false fails | 3-retry budget tolerates; persistent flake → ESCALATIONS |
| Cycle brief is wrong | Phase 3 design review catches; STOP + ESCALATIONS |
| External dep (e.g., novel-platform glossary-service) blocks | Cycle marks dep needed; ESCALATIONS with "external dep waiting" |
| Adversary rubber-stamps (0 findings on broken code) | Cold-start helps; Scope Guard double-checks; verify-cycle script is the ultimate gate |
| Cost runaway | Per-cycle token budget cap (hard limit at orchestrator); cycle abort if exceeded |
| Race conditions across DPS worktrees | DPS prompts declare cross-DPS dependencies; Tank rebase tests for races |

---

## §10. RAID vs AMAW summary

| Aspect | AMAW v3.0 | RAID v1.0 |
|---|---|---|
| Sub-agent usage | At REVIEW + POST-REVIEW only | Throughout (Tank, Healer, DPS, Adversary, Scope Guard, Auditor) |
| Human checkpoint at POST-REVIEW | YES (HARD STOP, WAIT) | NO (auto Scope Guard) |
| Cycle-internal parallelism | Single-track | N DPS in worktrees |
| Cost per task | $1-5 | $15-30/cycle × N cycles |
| Use case | Single L+ task with adversarial review | Multi-cycle mega-task (5+ cycles) with locked plan |
| Escalation | Human review at POST-REVIEW | ESCALATIONS.md row + halt |
| Trigger | `/amaw` | `/raid` |

---

## §11. Future improvements (post-foundation)

- ContextHub `add_lesson` integration in Phase 12 RETRO
- Adaptive retry budget per cycle complexity
- Cross-cycle pattern detection (which DPS slices recur — auto-extract as helper)
- Cost dashboards per cycle
- ML-assisted Adversary (specialized model for code review)
- DPS specialization (Rust DPS vs Go DPS vs IaC DPS)

These are out of foundation scope; RAID v1.0 is the locked spec for foundation mega-task execution.
