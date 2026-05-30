# RAID — Recursive Autonomous Implementation Drive Workflow Spec

> **Version:** RAID v1.6 (amended 2026-05-29 — v1.6 §16 task-portability via `.raid/active-task.yaml`; supersedes v1.5 hardcoded paths)
> **Prior versions:** v1.5 (§15 Coordinator dispatch — still active), v1.4 (§13.7 Semi-AUTO — superseded), v1.3 (§14 quota), v1.2 (§13 production-readiness), v1.1 (§12 context), v1.0
> **Status:** SPEC — v1.6 amendment adds branch/task portability; v1.5 Coordinator pattern unchanged
> **Parallel to:** AMAW v3.0 (Autonomous Multi-Agent Workflow) and v2.2 (human-in-loop)
> **Replaces AMAW:** NO — RAID is a SEPARATE workflow for autonomous multi-cycle execution. With v1.5 §15 Coordinator pattern, RAID's autonomy promise is restored: user invokes `/raid` ONCE; main session becomes the Coordinator and dispatches each cycle as Agent-tool sub-agent (cold-start = P1 fresh-session spirit satisfied without separate Claude Code sessions).
>
> **v1.1 amendment rationale:** initial v1.0 spec did not explicitly protect against
> context-window bloat, compaction-induced state loss, or lost-in-the-middle
> degradation over a 38-cycle execution. v1.1 adds §12 (Context Management
> Protections) covering 10 mitigations derived from Anthropic's published guidance
> on long-running agent harnesses and effective context engineering, plus 2025-2026
> research on lost-in-the-middle. See §12 for the full protection contract.
>
> **v1.2 amendment rationale:** v1.1 protected the agent loop but missed 6 production-
> readiness BLOCKERs: git worktree lifecycle, per-DPS isolated test infra, cost
> kill-switch, brief auto-generation + validation, foundation-vs-existing-prod
> isolation, and secret-scan in DPS workflow. v1.2 adds §13 (Production-Readiness
> Protections) covering B1-B6 + a smoke-test auto-gate from C0 to C1 (user opted for
> AUTO continue, not human checkpoint). See §13 for the full BLOCKER fix contract +
> [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md) for manual sign-off items.
>
> **v1.3 amendment rationale:** v1.2 §13.3 framed cost as $-budget assuming API
> pay-as-you-go. Project owner runs Claude on **subscription (Max 20x $200/mo)** with
> quota-based blocking (~900 messages / 5h window + monthly + weekly caps + 50
> sessions/month) — NOT dollar billing. §14 supersedes B3 with **B3-Q (Quota-Aware
> Execution)**: pre-cycle quota check, sub-agent model tiering (Opus reserved for
> Raid Leader; Sonnet/Haiku for DPS+Adversary+Scope-Guard+Auditor — Anthropic
> guidance: lighter models reduce hourly consumption ~40%), DPS count cap reduced
> (default 2-4 instead of 4-11), and graceful pause-on-quota-block via P3
> IN_PROGRESS state. User opted "run until quota out then resume after reset" — no
> auto-resume; user manually re-invokes `/raid <N>` after Anthropic's reset window
> (5h / weekly). See §14 for the full quota contract.

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

These are out of foundation scope; RAID v1.1 is the locked spec for foundation mega-task execution.

---

## §12. Context Management Protections (v1.1 ADDED 2026-05-29)

> **Why this section exists:** RAID executes 38 cycles over many hours/days. The Raid
> Leader main session, sub-agent results, cycle briefs, audit logs, and git diffs all
> compete for finite context window. Without explicit protections, the workflow degrades:
> Raid Leader forgets cycle 5's decision by cycle 25 (lost-in-middle), sub-agent results
> pollute orchestrator context (context bloat), compaction summarizes away critical state,
> and recovery from crash mid-cycle is ad-hoc.
>
> This section locks 10 protections (P1-P10) derived from Anthropic's effective-harnesses
> guidance + 2025-2026 lost-in-the-middle research. Every RAID cycle MUST honor these.

### §12.1 — P1: Fresh-session-per-cycle invariant

**Rule:** Each cycle MUST be a SEPARATE `/raid <N>` invocation in a fresh main session.
The Raid Leader main context starts at near-zero at every cycle boundary.

**Rationale:** Anthropic's "Long-Running Agent Harness" pattern uses initializer +
worker phases where "each new session begins with no memory of what came before." This
is a feature, not a bug — it bounds the per-cycle context cost regardless of how many
cycles have run.

**Enforcement:**
- `scripts/raid/orchestrator.py` rejects `/raid <N>` invocation if the same session
  already executed a different cycle (sentinel check via `docs/raid/.session-cycle-lock`)
- Cross-cycle reference is ONLY via files (CYCLE_LOG.md, AUDIT_LOG.jsonl,
  OPEN_QUESTIONS_LOCKED.md, IN_PROGRESS state files), NEVER via conversation memory

**Anti-pattern:** Running multiple cycles in one session ("just keep going after this
one"). Always exit and re-`/raid` for the next cycle.

---

### §12.2 — P2: Session startup routine (5-step "wake up" before any work)

**Rule:** Every `/raid <N>` invocation MUST execute these 5 steps in order BEFORE any
DESIGN/BUILD work. Skipping = ESCALATIONS row + abort.

```
Step 1: Read docs/raid/CYCLE_LOG.md tail (last 5 entries)
        → understand which cycles are DONE, which is current
Step 2: Read docs/raid/cycle_briefs/<NN>_*.md (the brief for THIS cycle)
        → get scope, acceptance, DPS plan, REMINDERS block
Step 3: Read docs/raid/IN_PROGRESS/cycle-<N>-state.md IF EXISTS
        → resume from prior checkpoint if crashed mid-cycle (see P5)
Step 4: Run `scripts/raid/startup-verifier.sh <N>`
        → verifies: git is on right branch, working tree clean OR
          matches IN_PROGRESS state, dependency cycles all DONE,
          no orphan ESCALATIONS rows blocking
Step 5: Read OPEN_QUESTIONS_LOCKED.md sections relevant to current cycle
        → load LOCKED decisions for this cycle's layer + cross-cutting
```

**Output:** Raid Leader has minimal-but-sufficient state to begin Phase 1 (CLARIFY).

**Why:** Anthropic's long-running harness spec mandates "session startup routines:
reading logs, verifying git history, and running basic end-to-end tests before new work
begins" — this is exactly that.

---

### §12.3 — P3: In-progress state file (claude-progress.txt analog)

**Rule:** Raid Leader writes `docs/raid/IN_PROGRESS/cycle-<N>-state.md` at every phase
transition. File contains:

```yaml
---
cycle: <N>
title: <from brief>
current_phase: <one of: CLARIFY|DESIGN|REVIEW1|PLAN|BUILD|VERIFY|REVIEW2|QC|POST_REVIEW|SESSION|COMMIT|RETRO>
phase_started_at: <ISO>
last_checkpoint_at: <ISO>
retry_count: <0..3>
dps_status:
  - dps_id: 1
    worktree: ../cycle-<N>-dps-1
    branch: cycle-<N>-dps-1-<slice>
    status: pending|in_progress|complete|failed
    started_at: <ISO>
    completed_at: <ISO or null>
  - ... (per DPS)
adversary_findings: <count or null if phase not yet>
scope_guard_result: <CLEAR|BLOCKED|null>
verify_script_exit: <0..255 or null>
notes: <free-text, < 500 chars>
---

# Cycle <N> in-progress state

<short narrative of where we are, what's next, any anomalies>
```

**Update points (mandatory):**
- After Step 5 of startup routine (initial state written)
- At every phase transition (Phase 1→2, 2→3, …, 11→12)
- After every DPS completion notification
- After every retry attempt
- Before any sub-agent spawn (so spawn is recoverable)

**On successful COMMIT (Phase 11):** Move file to `docs/raid/IN_PROGRESS/_archive/cycle-<N>-state.md`
(append-only audit; don't delete).

**On compaction event:** If the main session detects compaction (token count drop
between consecutive tool results), Raid Leader IMMEDIATELY:
1. Re-reads its IN_PROGRESS state file (regains state)
2. Re-reads the cycle brief (regains plan)
3. Cross-references against git log + AUDIT_LOG.jsonl (verifies no work lost)
4. Continues from documented phase

**Rationale:** Anthropic's `claude-progress.txt` pattern. Files are the source of truth;
context window is ephemeral.

---

### §12.4 — P4: Sub-agent return budget (1000-2000 tokens condensed summaries)

**Rule:** Sub-agents (DPS, Tank, Healer, Adversary, Scope Guard, Auditor) MUST return
condensed summaries, NEVER full diffs/logs/dumps.

**Per-role return contracts:**

| Role | Max return size | Content |
|---|---|---|
| DPS | 1500 tokens | `{branch_name, commit_sha, test_results: pass/fail counts, files_modified: [paths only], known_issues: []}` |
| Tank | 1000 tokens | `{rebase_result: ok|conflict|fail, conflicts_resolved: count, integration_test: pass|fail, branches_merged: [names]}` |
| Healer | 1200 tokens | `{tests_fixed: [test names], root_causes: [<50 chars each], remaining_failures: count, files_touched: [paths]}` |
| Adversary | 2000 tokens | `{findings: [{severity, file:line, category, one_line_description}]}` (max 30 findings) |
| Scope Guard | 500 tokens | `{result: CLEAR|BLOCKED, reason: <200 chars>, items_missing: [...] or items_out_of_scope: [...]}` |
| Auditor | 800 tokens | `{audit_log_appended: ok, cycle_log_appended: ok, retro_note: <500 chars>}` |

**Enforcement:** Sub-agent prompts include hard instruction:
> "Return only the structured summary specified. Do NOT include code diffs, test output,
> or commentary. If Raid Leader needs more, it will query git/files directly."

**Why:** Anthropic guidance: "specialized sub-agents tackle focused tasks and return
condensed summaries (typically 1,000-2,000 tokens)" — keeps Raid Leader context lean.

**Verification path:** If Raid Leader needs full info from a sub-agent, it queries via
Bash (`git diff`, `cat tests/output.log`, etc.) — NOT by asking the sub-agent for more.

---

### §12.5 — P5: Compaction recovery protocol

**Rule:** If Anthropic's server-side compaction fires mid-cycle, Raid Leader MUST:

1. Detect compaction (heuristic: prior tool results referenced by ID disappear OR token
   count between consecutive turns drops > 30%)
2. Pause new tool calls
3. Re-read IN_PROGRESS state file (P3)
4. Re-read cycle brief (full)
5. Re-read OPEN_QUESTIONS_LOCKED.md sections relevant to cycle
6. Cross-reference against:
   - `git log --since=<phase_started_at>` (verify no work lost)
   - `docs/raid/AUDIT_LOG.jsonl` tail (verify last logged phase)
   - DPS worktrees (verify branch states match IN_PROGRESS dps_status)
7. If state CONSISTENT: continue from documented phase
8. If state INCONSISTENT (worktree dirty unexpectedly, branch SHA mismatch, audit log
   shows different phase): **HALT + write ESCALATIONS.md row** (corrupted recovery is
   worse than halt)

**Why:** Compaction loses high-fidelity state. Recovery via files is safe; recovery via
inferred memory is dangerous.

---

### §12.6 — P6: Cycle brief structure (lost-in-middle aware)

**Rule:** Every cycle brief MUST follow this structure to minimize lost-in-middle:

```markdown
# Cycle <N>: <Title>

## 🎯 TL;DR (30 seconds — TOP critical info)
- Scope: <one paragraph>
- Acceptance: <bullet of CI gates>
- Top 3 LOCKED decisions consumed: Q-XXX-N, Q-YYY-N, Q-ZZZ-N
- DPS count: <N>
- Estimated cycle wall time: <hours>

## Dependencies (must show DONE in CYCLE_LOG.md)
- <list>

## Scope (IN)
<bullets>

## Scope (OUT — explicitly)
<bullets>

## Acceptance criteria (CI gates)
<bullets>

## DPS parallelism plan
<per-DPS slice + worktree>

## Adversary review focus
<bullets>

## Scope Guard CLEAR criteria
<bullets>

## Cross-references
<links to layer plans + kernel chunks>

## LOCKED decisions consumed (full list)
<all Q-IDs)>

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED decision 1:** <Q-ID resolution one-liner>
- 🔴 **Top LOCKED decision 2:** <Q-ID resolution one-liner>
- 🔴 **Top LOCKED decision 3:** <Q-ID resolution one-liner>
- 🔴 **Acceptance MUST include:** <key gate>
- 🔴 **Do NOT touch:** <out-of-scope items most likely to drift>
```

**Why:** Lost-in-the-middle research (Liu et al. 2023; Chroma 2025): info at start and
end of context receives stronger attention. By placing critical info BOTH at top (TL;DR)
AND at bottom (REMINDERS), we reduce reliance on middle retrieval.

**Hard rule:** Cycle brief size ≤ 4000 tokens. If a cycle's brief exceeds this, the
cycle MUST be split into 2 cycles (CYCLE_DECOMPOSITION.md amendment required).

---

### §12.7 — P7: Cross-cycle reference via CYCLE_LOG row only (DACS pattern)

**Rule:** When current cycle references a prior cycle's outcome, Raid Leader reads the
ONE CYCLE_LOG.md row for that cycle (~200 tokens). It does NOT re-read the prior cycle
brief OR prior cycle's IN_PROGRESS state.

**Allowed lookups:**
- CYCLE_LOG.md row (≤200 tokens summary per cycle)
- AUDIT_LOG.jsonl entries by cycle filter (machine-readable, slim)
- Git log + diff for specific files (targeted query, not bulk)

**Forbidden:**
- Reloading prior cycle's full brief (waste of context)
- Reloading prior cycle's IN_PROGRESS file
- Asking a sub-agent to summarize a prior cycle (overhead, drift risk)

**Why:** DACS (Dynamic Attentional Context Scoping) research: orchestrator operates in
"REGISTRY mode" with ≤200 tokens per agent/cycle status, only escalating to "FOCUS mode"
when absolutely necessary. RAID applies this cross-cycle.

**Concrete example:** Cycle 25 (L5.G reality seeder) needs to know how L1.C provisioner
(Cycle 5) registers Prometheus scrape targets. Raid Leader reads CYCLE_LOG row for Cycle
5 (sees: "L1.C ships provisioner with scrape-config-generator.sh hook"), then queries
`scripts/raid/files-from-cycle.sh 5` to get the file list, then `cat` the specific
provisioner code. NOT re-reading the entire L1C_to_L_infrastructure.md file.

---

### §12.8 — P8: Token budgets per phase + cycle ceiling

**Rule:** Per-phase soft budgets (token-count of Raid Leader's main context across the
phase). Exceeding triggers a warning in AUDIT_LOG; sustained exceeding triggers halt.

| Phase | Soft budget (Raid Leader main) | Notes |
|---|---|---|
| 1. CLARIFY | 5K | Just reads brief + startup routine output |
| 2. DESIGN | 8K | Applies brief, maps DPS assignments |
| 3. REVIEW1 | 3K | Self-check |
| 4. PLAN | 10K | DPS prompts written |
| 5. BUILD | 15K | Notifications from N DPS (each returns ≤1.5K) |
| 6. VERIFY | 8K | Tank + Healer summaries + verify script output |
| 7. REVIEW2 | 5K | Adversary findings list |
| 8. QC | 3K | Scope Guard |
| 9. POST-REVIEW | 3K | Second Scope Guard |
| 10. SESSION | 4K | Auditor writes log |
| 11. COMMIT | 5K | Commit message + status update |
| 12. RETRO | 3K | Auditor reflects |
| **Per-cycle ceiling (hard)** | **150K** | If exceeded → halt + ESCALATIONS |

**Cumulative Raid Leader per cycle target: ~70K-100K** (≈ 10-15% of 1M context budget,
matches Anthropic's thin-orchestrator guidance).

**Enforcement:** Auditor sub-agent (Phase 10) records `raid_leader_token_count` in
AUDIT_LOG.jsonl per phase. If cumulative > 150K → next cycle reads the warning and may
reduce DPS count or split into 2 cycles.

---

### §12.9 — P9: Auditor cross-check (anti-hallucination)

**Rule:** After Raid Leader writes the COMMIT (Phase 11), the Auditor sub-agent (Phase
10 ran before; runs again as a post-COMMIT verifier) is spawned ONE MORE TIME with a
verification prompt:

> "You are the post-commit verifier. Read the latest git commit (HEAD), the
> CYCLE_LOG.md tail entry, and the AUDIT_LOG.jsonl entries for cycle <N>. Check:
> 1. Commit SHA matches what CYCLE_LOG claims
> 2. CYCLE_LOG status=DONE matches AUDIT_LOG final phase=commit event
> 3. File count in commit matches IN_PROGRESS state's expected files
> 4. No phantom phases (every claimed phase in AUDIT_LOG has timestamp + sub-agent return)
> Return: VERIFIED or DRIFT_DETECTED with specific mismatch."

**On VERIFIED:** Cycle officially closes. Archive IN_PROGRESS state file.

**On DRIFT_DETECTED:** This is RAID's last line of defense against lost-in-middle
Raid Leader hallucination. ROLLBACK the commit (`git reset --soft HEAD~1`), write
ESCALATIONS.md row, halt cycle.

**Why:** Self-verification by an independent (cold-start) reader catches Raid Leader's
fabricated successes (e.g., "I claim DPS-3 succeeded but actually it errored and I
missed it after compaction").

---

### §12.10 — P10: Heartbeat metric + per-cycle health gauge

**Rule:** AUDIT_LOG.jsonl every per-phase event includes:

```jsonl
{
  "ts": "<ISO>",
  "cycle": <N>,
  "phase": "<name>",
  "event": "<event_type>",
  "raid_leader_token_count": <int>,  // estimated from API metadata
  "wall_time_in_phase_sec": <int>,
  "sub_agent_invocations_so_far": <int>,
  "memory_pressure": "<low|medium|high>"  // derived from token budget %
}
```

**Cycle 0 (RAID infra) ships `scripts/raid/health-dashboard.py`** that reads AUDIT_LOG
and emits a per-cycle health summary:

```
Cycle 17 — L4.A+B DP-kernel core + Macros — DONE
├─ Wall time: 4h 12min
├─ Sub-agent invocations: 11 (2 DPS, 1 Tank, 1 Healer, 1 Adversary, 2 Scope Guard, 1 Auditor, 1 post-commit verifier, 2 retries)
├─ Raid Leader peak tokens: 87,432 / 150K ceiling (58% — healthy)
├─ Compaction events detected: 0
├─ Memory pressure: low (peaked at medium during BUILD phase)
└─ Drift events: 0
```

**Pre-flight check for next cycle:** orchestrator reads prior cycle's health summary.
If prior cycle's peak tokens > 80% of ceiling OR > 1 compaction event detected →
warning logged + recommendation to reduce DPS count for next cycle.

**Why:** Without observability, context degradation is silent. Heartbeat + health gauge
makes the problem visible BEFORE it causes a cycle abort.

---

### §12.11 — Summary protection contract

| ID | Protection | Anti-pattern it prevents |
|---|---|---|
| P1 | Fresh-session-per-cycle | Raid Leader memory bloat across 38 cycles |
| P2 | 5-step startup routine | Beginning a cycle without proper state load |
| P3 | IN_PROGRESS state file | Crash recovery requires guessing state |
| P4 | Sub-agent return budget (1-2K tokens) | Sub-agent results polluting orchestrator context |
| P5 | Compaction recovery protocol | Hallucinated state after server-side compaction |
| P6 | Cycle brief TL;DR + REMINDERS structure | Lost-in-middle for critical LOCKED decisions |
| P7 | Cross-cycle ref via CYCLE_LOG only | Reloading prior briefs wastes context |
| P8 | Per-phase + cycle token budgets | Silent context bloat across phases |
| P9 | Auditor post-commit verification | Raid Leader hallucinating cycle success |
| P10 | Heartbeat + health dashboard | Context degradation invisible until cycle abort |

**Hard rule:** All 10 protections are MANDATORY for RAID execution. Cycle 0 (RAID infra)
delivers the supporting scripts for P2, P3, P5, P9, P10. Briefs are pre-written
following P6's structure. P1, P4, P7, P8 are agent-discipline rules enforced by
orchestrator and prompt templates.

---

### §12.12 — Cycle 0 additional deliverables (for §12 protections)

These are NEW deliverables added to Cycle 0 by this v1.1 amendment (in addition to those
in CYCLE_DECOMPOSITION.md §"Cycle 0"):

- `scripts/raid/startup-verifier.sh` — implements P2 5-step routine
- `scripts/raid/in-progress-state-writer.py` — implements P3 state file writer
- `scripts/raid/compaction-detector.py` — implements P5 detection heuristic
- `scripts/raid/post-commit-verifier-prompt.md` — implements P9 verifier prompt
- `scripts/raid/health-dashboard.py` — implements P10 health gauge
- `docs/raid/IN_PROGRESS/` directory — empty, with README explaining schema
- `docs/raid/IN_PROGRESS/_archive/` directory — empty, for archived completed-cycle states
- `docs/raid/.session-cycle-lock` — sentinel file for P1 enforcement
- `docs/raid/cycle_briefs/TEMPLATE.md` — canonical brief template per P6 structure
- `scripts/raid/files-from-cycle.sh` — helper for P7 cross-cycle file lookup

Cycle 0 also amends each of the 37 pre-written cycle briefs to follow P6 structure
(TL;DR top, REMINDERS bottom). The token budget per brief: 4000 token soft cap; cycles
that exceed must be split.

---

## §13. Production-Readiness Protections (v1.2 ADDED 2026-05-29)

> **Why this section exists:** v1.1 §12 protected the AGENT LOOP against context
> degradation, but missed REAL-WORLD operational hazards. Over 38 cycles + ~$1K cost +
> hundreds of git worktrees + DPS sub-agents touching test infra, several BLOCKER-class
> failure modes were unaddressed. v1.2 §13 closes them.

### §13.1 — B1: Git worktree lifecycle discipline

**Rule:** Every worktree spawned by Phase 5 (BUILD) MUST be cleaned up by Phase 11
(COMMIT). Stale worktrees from prior cycles MUST be detected and refused at Phase 1
startup.

**Worktree naming convention:**
- Pattern: `../foundation-worktrees/cycle-<N>-dps-<I>` (sibling to main repo)
- Branch pattern: `mmo-rpg/foundation-mega-task/cycle-<N>-dps-<I>-<slice-name>`

**Lifecycle per cycle:**

```
Phase 4 (PLAN):
  - Raid Leader calls: scripts/raid/worktrees-create.sh <N> <DPS_COUNT>
  - Creates N worktrees at known paths

Phase 5 (BUILD):
  - DPS agents work in their worktrees, commit to their branches

Phase 6 (VERIFY) — Tank:
  - Tank rebases all DPS branches onto cycle base branch
  - On success: each DPS branch merged + worktree marked for cleanup

Phase 11 (COMMIT) — Raid Leader:
  - Calls: scripts/raid/worktrees-cleanup.sh <N>
  - For each DPS worktree:
    - If branch successfully merged AND working tree clean:
      → git worktree remove <path> + delete branch
    - If working tree DIRTY (unexpected — Tank's rebase should have left it clean):
      → ARCHIVE to ../foundation-worktrees/_archive/cycle-<N>-dps-<I>-<timestamp>
      → write WARNING to AUDIT_LOG (forensic later)
```

**Pre-cycle startup check (extends P2 startup routine):**

```bash
# scripts/raid/worktrees-check.sh — runs as step 4.5 of P2 startup routine
existing=$(git worktree list --porcelain | grep "foundation-worktrees" | grep -v "_archive")
if [ -n "$existing" ]; then
  echo "STALE WORKTREES from prior cycles:"
  echo "$existing"
  echo "Refusing to start cycle. Manually investigate or run worktrees-cleanup.sh"
  exit 1
fi
```

**Why:** Without discipline, 38 cycles × 5-15 DPS = 200-500 stale worktrees → disk fills
+ confused git state + risk of accidentally merging wrong branch.

---

### §13.2 — B2: Per-DPS isolated test infrastructure

**Rule:** Each DPS sub-agent MUST have its own isolated test stack (Postgres + Redis +
MinIO). No shared test infra → no cross-DPS data races → no flaky tests.

**Port allocation strategy:**

```
Postgres port = 10000 + cycle_num * 100 + dps_id
Redis port    = 12000 + cycle_num * 100 + dps_id
MinIO port    = 14000 + cycle_num * 100 + dps_id (MinIO API)
MinIO console = 15000 + cycle_num * 100 + dps_id

Examples:
- Cycle 17, DPS 1: Postgres=11701, Redis=13701, MinIO=15701/16701
- Cycle 17, DPS 2: Postgres=11702, Redis=13702, MinIO=15702/16702
- Cycle 26, DPS 1: Postgres=12601, Redis=14601, MinIO=16601/17601

Deterministic — multiple cycles can't collide.
```

**Lifecycle scripts (delivered by Cycle 0):**

- `scripts/raid/test-infra-up-dps.sh <N> <DPS_ID>` — `docker compose -p raid-c<N>-dps<I> up -d`
  using a templated docker-compose with port overrides
- `scripts/raid/test-infra-down-dps.sh <N> <DPS_ID>` — `docker compose -p raid-c<N>-dps<I> down -v`
  (volumes wiped — no state between DPS runs)
- `scripts/raid/test-infra-template.docker-compose.yml` — base template

**DPS prompt augmentation (added to brief DPS plan):**

```
Before BUILD: bash scripts/raid/test-infra-up-dps.sh <N> <DPS_ID>
After BUILD (success or failure): bash scripts/raid/test-infra-down-dps.sh <N> <DPS_ID>
Use POSTGRES_URL=postgres://test:test@localhost:<port>/test in tests.
```

**Why:** Per-DPS isolation = parallel DPS work doesn't corrupt each other's test DB. No
flaky tests from race conditions on shared port 5432.

---

### §13.3 — B3: Cost kill-switch + per-cycle budget

**Rule:** Hard cost caps enforced at orchestrator level. Per-cycle: $50 USD. Per-
foundation: $1500 USD (≈50% over $1140 estimate, allows headroom for retries).

**Tracking:**

- AUDIT_LOG.jsonl every phase event includes `estimated_cost_usd` (from Anthropic API
  response metadata: `usage.input_tokens` × $15/M + `usage.output_tokens` × $75/M for
  Opus 4.7)
- `scripts/raid/cost-tracker.py` reads AUDIT_LOG, sums per cycle + cumulative
- Pre-flight check per cycle: if cumulative cost > $1400 → ABORT cycle + ESCALATIONS
  (last-100-buffer rule — don't blow past the cap silently)
- Per-cycle check at every phase boundary: if cycle cost > $40 → WARNING in AUDIT_LOG;
  if > $50 → ABORT cycle + ESCALATIONS

**Escalation row template:**

```
## Cycle <N> — COST EXCEEDED — ESCALATED <date>

### Cost details
- Cycle cost so far: $<X.XX>
- Cumulative foundation cost: $<Y.YY>
- Cap exceeded: per-cycle | per-foundation
- Last 5 phase events (cost breakdown):
  - PHASE | ESTIMATED COST | RUNNING TOTAL
  - ...

### Suggested action
- [ ] Investigate which phase consumed unexpected tokens (look for retry loops)
- [ ] Check for compaction recovery loop (P5 may have triggered repeatedly)
- [ ] Manually approve to continue with explicit `--accept-cost-overrun=$<Z.ZZ>` flag
- [ ] Pause foundation; revise estimate; replan cycles 38..N
```

**Cost dashboard (delivered by Cycle 0):**

- `docs/raid/COST_LOG.jsonl` (append-only, machine-readable)
- `scripts/raid/cost-summary.py` outputs:

```
Foundation cost so far: $872 / $1500 cap (58% used)
Per-cycle averages: $24.50 (target $30; under budget)
Most expensive cycle: Cycle 17 (DP-kernel macros) at $87 (RETRIED 2x)
Cheapest cycle: Cycle 4 (audit tables) at $11
Projected remaining: $200-400 for cycles 33-38
Recommendation: ON TRACK
```

**Why:** Without hard caps, a runaway cycle (e.g., DP-kernel macros looping on compile
errors) could burn $200+ before detection. Per-cycle $50 cap is generous but bounded.

---

### §13.4 — B4: Brief auto-generation + schema validator

**Rule:** The 37 cycle briefs are NOT hand-written. They are AUTO-GENERATED by Cycle 0
from the CLARIFY artifacts (layer plans + OPEN_QUESTIONS_LOCKED + CYCLE_DECOMPOSITION),
then validated against the §4 schema.

**Generator pipeline:**

```
scripts/raid/brief-generator.py <cycle_num>
  ↓
Reads:
  - docs/plans/2026-05-29-foundation-mega-task/CYCLE_DECOMPOSITION.md §2 (cycle row)
  - docs/plans/2026-05-29-foundation-mega-task/L<X>_*.md (parent layer plan)
  - docs/plans/2026-05-29-foundation-mega-task/OPEN_QUESTIONS_LOCKED.md (relevant Qs)
  ↓
Generates:
  docs/raid/cycle_briefs/<NN>_<short>.md following §4 template:
  - TL;DR (top)
  - Dependencies
  - Scope IN / OUT
  - Acceptance criteria
  - DPS parallelism plan (extracted from CYCLE_DECOMPOSITION §2 "DPS parallel" column)
  - Adversary review focus (from layer plan §X)
  - Scope Guard CLEAR criteria
  - Cross-references
  - LOCKED decisions (auto-pulled from OPEN_QUESTIONS_LOCKED for this layer)
  - 🔴 REMINDERS (top 3 most critical LOCKEDs + most likely scope drift)
```

**Schema validator (CI lint):**

```
scripts/raid/brief-structure-validator.sh <brief_path>
  ↓
Checks:
  - All 10 required sections present (TL;DR, Deps, Scope IN, Scope OUT,
    Acceptance, DPS plan, Adversary, Scope Guard, Cross-refs, REMINDERS)
  - TL;DR section ≤ 300 tokens
  - REMINDERS section has ≥ 3 🔴 lines AND ≤ 600 tokens
  - Total brief ≤ 4000 tokens
  - All Q-IDs referenced exist in OPEN_QUESTIONS_LOCKED.md
  - All file paths referenced exist OR are explicitly future-created
  - Markdown links valid
  ↓
Exit 0 = valid; non-zero = lint fail with specific reason
```

**Re-generation on LOCKED changes:**

- If OPEN_QUESTIONS_LOCKED.md changes (re-litigation), `scripts/raid/regenerate-briefs.sh`
  detects affected cycles + re-generates their briefs
- Pre-cycle check: brief's `last_generated_from_LOCKED_sha` matches current LOCKED file sha

**Why:** Hand-written briefs are themselves vulnerable to lost-in-middle from CLARIFY.
Auto-generation guarantees structure compliance + traceability to LOCKED decisions.

---

### §13.5 — B5: Foundation-vs-existing-prod isolation

**Rule:** Foundation infrastructure (Patroni Postgres HA, Redis Sentinel, MinIO,
pgbouncer) is built and tested in DEDICATED dev/staging environments that are SEPARATE
from the existing LoreWeave novel-platform prod. Foundation cycles MUST NOT touch
existing prod services or DBs.

**Environment topology:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ EXISTING LoreWeave novel-platform prod (untouched)                      │
│  - Postgres: single instance, no Patroni                                │
│  - Redis: single instance, no Sentinel                                  │
│  - 12 existing services running                                         │
│  - URL: prod.loreweave.app                                              │
└─────────────────────────────────────────────────────────────────────────┘

                              ╳ ISOLATION ╳

┌─────────────────────────────────────────────────────────────────────────┐
│ FOUNDATION dev (built by RAID cycles)                                   │
│  - infra/foundation-dev/docker-compose.yml                              │
│  - Local Patroni + etcd + Redis Sentinel + MinIO                        │
│  - All foundation cycle tests target this env                           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ FOUNDATION staging (built by RAID cycles, deployed at C38 acceptance)   │
│  - infra/foundation-staging/terraform/                                  │
│  - AWS staging account (NEW account, separate from prod)                │
│  - E2E smoke test runs here at C38                                      │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ FOUNDATION prod (NOT built by RAID — separate V1+30d sub-program)       │
│  - infra/foundation-prod/terraform/                                     │
│  - Migration from existing prod → foundation prod is OUT of foundation  │
│  - Foundation runs in parallel as "shadow" until migration sub-program  │
└─────────────────────────────────────────────────────────────────────────┘
```

**RAID cycle scope:**

- Cycles 1-37 build foundation in `infra/foundation-dev/` + `infra/foundation-staging/`
- Existing prod is read-only from foundation perspective (`prod.loreweave.app` may be
  referenced for design but never written to)
- Foundation service scaffolds compile + run in foundation-dev; they do NOT replace
  existing services in prod

**C38 acceptance smoke runs in foundation-staging, NOT existing prod.**

**Post-foundation sub-program (out of this CLARIFY):** Migration program designs the
cutover from existing prod (single Postgres + Redis) → foundation prod (Patroni +
Sentinel + MinIO). That program owns its own risk assessment.

**CI lint to enforce isolation:**

- `scripts/raid/prod-isolation-lint.sh` — blocks any DPS commit that references
  `prod.loreweave.app` hostname OR existing prod IPs OR prod connection strings
- Blocks any commit touching `infra/existing-prod/` or `infra/loreweave-novel-platform/`
- Foundation cycles only touch `infra/foundation-*/`

**Why:** Without isolation, a buggy DPS could attempt schema migration on existing prod
DB → catastrophic outage of existing services. Hard isolation = no risk.

---

### §13.6 — B6: Secret scan in DPS workflow

**Rule:** Every DPS branch is scanned by gitleaks BEFORE Tank rebase. Any secret found
→ DPS slice ABORTS, branch quarantined, ESCALATIONS row written.

**Setup (delivered by Cycle 0):**

- `.gitleaks.toml` at repo root — config tuned for LoreWeave (whitelist test fixtures,
  flag real-looking AWS/GCP/Anthropic/Postgres URLs)
- `scripts/raid/secret-scan-dps.sh <N> <DPS_ID>` — runs gitleaks on DPS branch + worktree
- Pre-commit hook installed in DPS worktrees: refuses commit if gitleaks detects secret

**Workflow integration:**

```
Phase 5 (BUILD) end — DPS finishes its work:
  DPS sub-agent prompt augmented:
  > "Before returning summary, run: bash scripts/raid/secret-scan-dps.sh <N> <DPS_ID>
  > If exit non-zero, abort + return {status: 'aborted_secret_detected', details}"

Phase 6 (VERIFY) — Tank rebase:
  Before rebase, Tank runs scan again across ALL DPS branches:
  > bash scripts/raid/secret-scan-cycle.sh <N>
  > If any leak detected → halt rebase + ESCALATIONS row + quarantine all DPS branches

Phase 11 (COMMIT) — final scan:
  Before final commit:
  > bash scripts/raid/secret-scan-final.sh <N>
  > Last defense; aborts commit if leak somehow survived
```

**Quarantine on leak:**

- Affected branch renamed to `quarantine/cycle-<N>-dps-<I>-LEAK-<timestamp>`
- Worktree moved to `../foundation-worktrees/_quarantine/`
- ESCALATIONS row includes: file path, line, secret pattern matched (REDACTED), DPS ID
- Cycle halts; human investigates + manually rotates the leaked credential if real

**False-positive handling:**

- `.gitleaks.toml` allowlist for test fixtures using placeholder secrets
  (`<REDACTED-FAKE-SECRET>`, `test-only-not-a-real-token`)
- Project secrets convention: real secrets ONLY in env vars (per CLAUDE.md "no
  hardcoded secrets"); never in test fixtures
- Allowlist additions require code review (CODEOWNERS check)

**Why:** DPS agents have full repo write access. A single accidental secret commit =
credential rotation + possible breach disclosure. Pre-Tank scan = caught at branch level
before merge.

---

### §13.7 — C0→C1 Semi-AUTO gate via smoke test (REVISED v1.4 — was AUTO)

> **v1.4 amendment (2026-05-29, Cycle 0 build phase):** Original "AUTO continue" was
> structurally impossible — a Claude Code session cannot spawn a fresh Claude Code
> session from inside its tool harness, violating P1 fresh-session invariant. Adversary
> R1 surfaced this BLOCK during C0 design review. User re-confirmed "Semi-AUTO: signal
> emit + user starts /raid <N>" (see PRE_FLIGHT D6). The pause + dispatch mechanism
> remains; only the final step changes from "auto-spawn" to "emit ready-signal +
> instruct user".

**Rule:** Cycle 0 (RAID infra) does NOT require human review before C1 fires. Instead,
C0 ends with a comprehensive smoke test that exercises ALL §12 (P1-P10) + §13 (B1-B6)
+ §14 (Q1-Q9) protections on a NO-OP cycle. If smoke passes → orchestrator emits
ready-signal + user opens fresh session + invokes `/raid 1`. If smoke fails → halt +
ESCALATIONS.

**Smoke test cycle: `cycle_test_helloworld`**

Located at `docs/raid/cycle_briefs/00X_helloworld_smoke.md` — a deliberately tiny cycle:

```
Scope IN:
  - Create file `docs/raid/_smoke/HELLO_FROM_<TIMESTAMP>.md` with content "RAID smoke test"
  - Single DPS, single file commit
  - Auto-cleanup after verify

Acceptance criteria:
  - All 10 P-protections exercised: fresh session, startup routine, IN_PROGRESS file
    written + read, sub-agent return within budget, compaction simulation (force a
    summarization), cycle brief structure validated, cross-cycle ref tested, token
    budget tracked, post-commit verifier run, health dashboard updated
  - All 6 B-protections exercised: worktree created + cleaned up, isolated Postgres
    spun up + torn down, cost tracked + under $1, brief auto-generated + validated,
    no real prod reference, gitleaks scan green
  - All 38 cycle briefs validated by brief-structure-validator
  - Health dashboard reports peak < 50K tokens
```

**Semi-AUTO dispatch logic (v1.4 — REVISED):**

```
End of C0:
  bash scripts/raid/run-smoke-test.sh
  smoke_exit=$?

  if [ $smoke_exit -eq 0 ]; then
    echo "[C0] Smoke green — emitting ready-signal for cycle 1 in 60 seconds"
    python scripts/raid/auto-dispatcher.py --next-cycle 1
    # auto-dispatcher.py runs the 60s countdown + signal-emit (NOT a session spawn)
  else
    echo "[C0] SMOKE FAILED — exit $smoke_exit"
    # ESCALATIONS row already written by smoke script
    exit $smoke_exit
  fi
```

**The 60-second pause + user-step is the C0→C1 boundary** in RAID v1.4 (was "AUTO" in v1.2;
revised after Adversary R1). User watching the output has a window to ctrl-C if
something looks wrong; otherwise reads the ready-signal instruction block and opens a
fresh Claude Code session manually.

**auto-dispatcher.py behavior (v1.4):**

- Reads CYCLE_LOG.md to find next PENDING cycle whose deps are all DONE
- Acquires lock transition: `UNLOCKED` (or `00X`) → `READY_FOR_<N>` (paired state)
- Writes `docs/raid/READY_FOR_CYCLE_<N>.signal` with metadata (next cycle, ready_at, deps, smoke evidence SHA)
- Prints 60-second countdown with `Ctrl-C to halt` banner (short sleep increments)
- After countdown without interrupt: emits user instruction block:
  ```
  ═══════════════════════════════════════════════════════════
  C0 SMOKE GREEN — READY FOR CYCLE <N>
  ═══════════════════════════════════════════════════════════
  1. Close this Claude Code session (P1 fresh-session invariant)
  2. Open a NEW Claude Code session in the same repo
  3. Run:  /raid <N>
  4. Orchestrator detects READY_FOR_CYCLE_<N>.signal +
     acquires lock transition READY_FOR_<N> → <N>
  ═══════════════════════════════════════════════════════════
  ```
- Exit 0 (signal file is the durable handoff; user is the dispatcher's continuation)

**Why not actual session spawn?** Two structural blockers:
1. Claude Code CLI is not designed to be invoked as `claude /raid 1` from a Python
   subprocess from a Bash tool call from a Claude session — even if technically wired,
   the parent session's tool harness would lose handle on the child.
2. P1 fresh-session invariant requires the new `/raid <N>` to begin with NEAR-ZERO
   main-session context. A parent-spawned child would inherit the parent's authentication
   + working dir but the orchestration handle would remain in the parent, which has
   already burned its context on C0 — defeating P1.

**Cycles still run strictly sequential** (NOT parallel — per PRE_FLIGHT decision;
parallel cycles defer to RAID v2.0).

**Continues until all 38 cycles DONE OR escalation row written.** If escalation:
dispatcher halts, user is the notification channel (no Slack/email integration in v1.4;
deferred to V1+30d).

**Smoke test failure modes (each blocks C1):**

| Smoke failure | Likely cause | Remediation |
|---|---|---|
| P1 fresh-session check fails | session-cycle-lock sentinel buggy | Fix orchestrator before C0 retry |
| P3 IN_PROGRESS write fails | path permissions / disk full | Ops fix |
| P4 sub-agent return exceeds budget | smoke sub-agent prompt allows verbosity | Tighten prompt |
| B1 worktree cleanup fails | `git worktree remove` race | Investigate + retry |
| B2 docker-compose port conflict | port allocation bug | Fix allocator |
| B3 cost > $1 for smoke | Anthropic API metering off | Investigate |
| B4 brief validator fails on smoke brief | template generator bug | Fix generator + regenerate all briefs |
| B6 gitleaks false positive on test fixture | allowlist incomplete | Update `.gitleaks.toml` |

---

### §13.8 — Summary BLOCKER fix contract

| ID | BLOCKER | Fix delivered by Cycle 0 | Anti-pattern prevented |
|---|---|---|---|
| B1 | Git worktree lifecycle | `worktrees-create.sh`, `worktrees-cleanup.sh`, `worktrees-check.sh`, archive dir | 200-500 stale worktrees over 38 cycles |
| B2 | Per-DPS isolated test infra | `test-infra-up-dps.sh`, `test-infra-down-dps.sh`, port allocator | Cross-DPS test data races, flaky tests |
| B3 | Cost kill-switch | `cost-tracker.py`, `cost-summary.py`, COST_LOG.jsonl, $50/cycle + $1500/foundation caps | Runaway cycle burns $200+ silently |
| B4 | Brief auto-gen + validator | `brief-generator.py`, `brief-structure-validator.sh`, `regenerate-briefs.sh` | Hand-written briefs with lost-in-middle |
| B5 | Foundation-vs-prod isolation | dev/staging/prod env split, `prod-isolation-lint.sh` | Buggy DPS migrates existing prod DB → outage |
| B6 | Secret scan | `.gitleaks.toml`, `secret-scan-dps.sh`, `secret-scan-cycle.sh`, `secret-scan-final.sh`, quarantine flow | Credential commit → rotation + breach |
| AUTO | C0→C1 auto-gate | `run-smoke-test.sh`, `auto-dispatcher.py`, 60s pause window | C0 broken but C1 fires anyway |

**Hard rule:** All 6 BLOCKERs + the AUTO gate are MANDATORY for Cycle 0 success.
Failing any = C0 INCOMPLETE = no RAID execution.

---

### §13.9 — Cycle 0 amended deliverables (full list across v1.0, v1.1, v1.2)

**v1.0 core (5 items):**
- `scripts/raid/orchestrator.py`
- `scripts/raid/verify-cycle-template.sh`
- `scripts/raid/escalation-writer.py`
- `docs/raid/{AUDIT_LOG.jsonl, CYCLE_LOG.md, ESCALATIONS.md, cycle_briefs/}`
- Copy of RAID_WORKFLOW.md

**v1.1 §12 context protections (10 items):**
- `scripts/raid/startup-verifier.sh` (P2)
- `scripts/raid/in-progress-state-writer.py` (P3)
- `scripts/raid/compaction-detector.py` (P5)
- `scripts/raid/post-commit-verifier-prompt.md` (P9)
- `scripts/raid/health-dashboard.py` (P10)
- `scripts/raid/files-from-cycle.sh` (P7)
- `docs/raid/IN_PROGRESS/` + `_archive/` dirs
- `docs/raid/.session-cycle-lock`
- `docs/raid/cycle_briefs/TEMPLATE.md`

**v1.2 §13 production-readiness (12 items):**
- `scripts/raid/worktrees-create.sh` (B1)
- `scripts/raid/worktrees-cleanup.sh` (B1)
- `scripts/raid/worktrees-check.sh` (B1)
- `scripts/raid/test-infra-up-dps.sh` (B2)
- `scripts/raid/test-infra-down-dps.sh` (B2)
- `scripts/raid/test-infra-template.docker-compose.yml` (B2)
- `scripts/raid/cost-tracker.py` (B3 — dual-use per §14.9)
- `scripts/raid/cost-summary.py` (B3 — dual-use per §14.9)
- ~~`docs/raid/COST_LOG.jsonl` (B3)~~ — **SUPERSEDED** by `docs/raid/QUOTA_LOG.jsonl` per §14.9; do NOT create COST_LOG.jsonl (subscription users)
- `scripts/raid/brief-generator.py` (B4)
- `scripts/raid/brief-structure-validator.sh` (B4)
- `scripts/raid/regenerate-briefs.sh` (B4)
- `scripts/raid/prod-isolation-lint.sh` (B5)
- `.gitleaks.toml` (B6)
- `scripts/raid/secret-scan-dps.sh` (B6)
- `scripts/raid/secret-scan-cycle.sh` (B6)
- `scripts/raid/secret-scan-final.sh` (B6)
- `scripts/raid/run-smoke-test.sh` (AUTO)
- `scripts/raid/auto-dispatcher.py` (AUTO)
- `docs/raid/cycle_briefs/00X_helloworld_smoke.md` (AUTO)
- `infra/foundation-dev/docker-compose.yml` (B5)
- `infra/foundation-staging/terraform/` skeleton (B5)
- `../foundation-worktrees/` + `_archive/` + `_quarantine/` dirs (B1, B6)

**Total Cycle 0: 36 deliverables.** Cycle 0 is now size **L** (was M v1.1; was S/M v1.0).
This is the largest single non-RAID cycle but required for safe autonomous execution.

---

## §14. Quota-Aware Execution (v1.3 ADDED 2026-05-29 — supersedes §13.3 B3)

> **Why this section exists:** v1.2 §13.3 B3 assumed pay-as-you-go API billing. Project
> owner runs Claude on subscription (**Max 20x at $200/mo**). Anthropic protects
> subscription users via QUOTA blocking — not dollar billing. Tokens drained from
> conversation history + tool definitions + file references + sub-agent contexts all
> count against the same 5-hour rolling quota. Sub-agents are particularly expensive
> (~7× standard usage per Anthropic guidance — each maintains its own context window).
>
> §14 supersedes the B3 cost-kill-switch logic in §13.3 with quota-aware execution.
> All other v1.2 §13 protections (B1, B2, B4, B5, B6) remain in force unchanged.

### §14.1 — Q1: Subscription plan context (Max 20x)

**Locked plan:** Anthropic Max 20x ($200/month) — per PRE_FLIGHT_CHECKLIST §3.

**Known limits (Anthropic published, May 2026):**
- ~900 messages per 5-hour rolling window (estimate; varies by message length + files)
- Weekly cap (separate from 5h)
- 50 sessions/month soft guideline (each session ≈ 5h window)
- Cross-surface aggregation: claude.ai + Claude Code + Desktop all share quota

**Quota signal:** Anthropic returns `"Claude usage limit reached"` message or HTTP 429
when window hit. Tool calls are blocked until reset.

**Reset windows:**
- 5h: rolling from first message of session
- Weekly: rolling from first message of week
- Monthly session cap: rolling from first session of month

---

### §14.2 — Q2: Sub-agent model tiering (CRITICAL quota reduction)

**Per Anthropic guidance:** "Letting Sonnet conduct the orchestra while Haiku handles
repetitive lookups and research cuts hourly consumption by up to 40%."

**RAID v1.3 role → model assignment:**

| Role | Model | Reason |
|---|---|---|
| **Raid Leader** (main session) | **Opus 4.7** (current model) | Orchestration requires deep reasoning + tool selection |
| **DPS** (per worktree, parallel) | **Sonnet 4.6** for std slices; Opus 4.7 only for DP-kernel (C17), macros (C17), per-reality DB migrations (C9, C13) — complex slices | Build work doable in Sonnet for most slices |
| **Tank** (rebase + integration) | **Sonnet 4.6** | Mostly mechanical merge work |
| **Healer** (test repair) | **Sonnet 4.6** | Test fixes seldom need deep reasoning |
| **Adversary** (cold-start review) | **Sonnet 4.6** | Adequate for code review per Anthropic guidance |
| **Scope Guard** (brief vs diff) | **Haiku 4.5** | Simple comparison task; Haiku sufficient |
| **Auditor** (write logs) | **Haiku 4.5** | Pure write task; minimal reasoning |
| **Post-commit verifier** (P9) | **Haiku 4.5** | Cross-check facts, no synthesis |

**Estimated quota multiplier reduction:** 7× sub-agent overhead → ~3× when most are
Sonnet/Haiku. **Net cycle quota: ~400-500K tokens** (was projected ~1M-1.5M with all-Opus).

**Per Max 20x window (≈ 2M tokens equivalent):** 4-5 cycles per 5h window.

**Implementation:**
- DPS prompts include `model: "sonnet-4-6"` or `model: "opus-4-7"` directive
- Agent tool calls explicitly pass `model` parameter
- `scripts/raid/sub-agent-spawn.py` enforces tier assignment per role

---

### §14.3 — Q3: DPS count cap (reduce parallelism for quota)

**v1.0 default DPS counts** in CYCLE_DECOMPOSITION.md §2 ranged 1-11 per cycle. v1.3
caps for Max 20x:

| Cycle complexity | DPS count cap (Max 20x) | Was (v1.0) |
|---|---|---|
| Simple (1-2 components) | 1-2 | 1-2 (unchanged) |
| Medium (3-5 components) | **2-3** | 3-4 |
| Complex (6-8 components) | **3-4** | 5-7 |
| Mega (9+ components — e.g., C7, C36) | **4-5** | 8-11 |

**Wall-clock tradeoff:** less parallelism → cycles take longer (1.5-2× wall-clock per
cycle). Quota savings: each DPS = full context spawn = significant tokens. Reducing 8
DPS → 4 DPS = ~50% sub-agent quota saving per cycle.

**Mega-cycle splitting:** if reducing DPS makes a cycle exceed 6h wall-clock, the cycle
is SPLIT into 2 cycles. Cycle 36 (L7.A admin-cli with ~30 commands) and Cycle 7 (L1
remainder) are candidates for splitting; brief-generator (B4) detects and proposes.

**Configurable:** `contracts/raid/quota-profile.yaml`:

```yaml
plan: max-20x
dps_count_cap_per_complexity:
  simple: 2
  medium: 3
  complex: 4
  mega: 5
mega_split_wall_clock_threshold_hours: 6
preferred_models:
  default_sub_agent: sonnet-4-6
  light_sub_agent: haiku-4-5
  heavy_sub_agent: opus-4-7
```

Future profiles (`pro.yaml`, `max-5x.yaml`, `api-payg.yaml`) for other users.

---

### §14.4 — Q4: Pre-cycle quota check

**Rule:** Before invoking `/raid <N>`, the orchestrator (or user manually) runs a
pre-flight check:

```bash
scripts/raid/quota-check.sh
  → reads docs/raid/QUOTA_LOG.jsonl (estimated burn since session start)
  → computes: estimated_remaining_5h_quota / typical_cycle_quota_burn
  → output:
    - cycles_runnable_in_window: <int>
    - estimated_remaining_pct: <%>
    - recommendation: PROCEED | WAIT-FOR-RESET | RISKY
```

**Decision matrix:**
- Remaining ≥ 1.5× typical cycle: PROCEED
- 0.5-1.5× typical cycle: RISKY (warn — cycle may halt mid-execution)
- < 0.5× typical cycle: WAIT-FOR-RESET (5h wait recommended)

**User-initiated mode:** User runs `/raid <N>` and the prompt template's startup routine
(P2) includes:

```
Step 0 (NEW v1.3): Check QUOTA_LOG.jsonl
  - If estimated remaining < 0.5× cycle burn: print warning, ask user to confirm
    "Quota likely insufficient for full cycle. Continue anyway? [Y/n]"
  - If user proceeds: log explicit acceptance to AUDIT_LOG
```

---

### §14.5 — Q5: Quota-block detection + graceful pause

**Rule:** If Anthropic returns "usage limit reached" / 429 mid-cycle, Raid Leader MUST:

1. **Catch the error** (orchestrator wraps tool calls with retry-on-rate-limit handler)
2. **Save IN_PROGRESS state** (P3 already does this — quota block uses same mechanism)
3. **Log to ESCALATIONS.md** with `type=quota_block` (not a true escalation — recoverable):

```markdown
## Cycle <N> — QUOTA BLOCK <date>

### Status
- Phase reached: <name>
- Phase progress: <description>
- Last successful tool call: <ISO>
- Block detected at: <ISO>

### Estimated reset
- 5h window resets at: <ISO + 5h from session start>
- Weekly window resets at: <ISO of week start + 7d>

### Recovery action
- User manually re-invokes `/raid <N>` after reset window
- Orchestrator reads IN_PROGRESS state, resumes from documented phase
- No work lost (all DPS branches preserved in worktrees per B1)
```

4. **Exit gracefully** (do NOT loop on retries — that burns tokens trying to recover)

**This is NOT an ESCALATION in the v1.0 sense** (no fix needed — just wait + resume).
Auditor distinguishes `type=quota_block` rows from `type=error` rows in cost dashboard.

---

### §14.6 — Q6: Block-recovery protocol (resume after reset)

**Rule:** After Anthropic's reset window passes, user manually runs `/raid <N>` again.
The startup routine (P2) detects an in-progress cycle and resumes:

```
P2 Step 3 (already exists): Read docs/raid/IN_PROGRESS/cycle-<N>-state.md IF EXISTS
  → if exists with current_phase != COMMIT:
    → Resume mode activated
    → Reload completed DPS states from worktrees
    → Continue from documented current_phase
    → Skip phases already complete (idempotent operation)
```

**Idempotency requirement:** every phase action MUST be safe to run twice. Critical:
- BUILD phase: skip DPS that already shows `complete` status in IN_PROGRESS
- VERIFY phase: don't re-run verify if last result was PASS
- COMMIT phase: detect if commit already exists (sha match) and skip

**Worktree state preservation:** B1 worktree-cleanup is SKIPPED on quota-block exit —
worktrees persist until cycle completes. Only completed cycles trigger cleanup.

---

### §14.7 — Q7: Quota observability (QUOTA_LOG.jsonl)

**Rule:** Auditor records estimated quota burn per phase event in QUOTA_LOG.jsonl:

```jsonl
{"ts":"<ISO>","cycle":17,"phase":"build","event":"dps_complete","dps_id":1,"model":"sonnet-4-6","estimated_tokens":45000}
{"ts":"<ISO>","cycle":17,"phase":"build","event":"dps_complete","dps_id":2,"model":"opus-4-7","estimated_tokens":92000}
{"ts":"<ISO>","cycle":17,"phase":"verify","event":"verify_script","model":"main-opus-4-7","estimated_tokens":12000}
{"ts":"<ISO>","cycle":17,"phase":"review","event":"adversary","model":"sonnet-4-6","estimated_tokens":28000}
{"ts":"<ISO>","cycle":17,"phase":"qc","event":"scope_guard","model":"haiku-4-5","estimated_tokens":4000}
```

**Dashboard (`scripts/raid/quota-summary.py`):**

```
Foundation quota burn so far: ~14.3M tokens
Sessions used this month: 3 / 50 (Max 20x cap)
Cycles per window average: 4.2
Most expensive cycle: C17 (DP-kernel macros) — 680K tokens
Cheapest cycle: C4 (audit tables) — 220K tokens
Current 5h window estimated remaining: ~600K tokens (3 cycles runnable)
Weekly window resets in: 2 days 14h
Recommendation: PROCEED
```

**Estimation accuracy:** Anthropic doesn't expose exact subscription quota state via
API. Estimates use:
- Input/output token counts from API response metadata (where exposed)
- Conservative multiplier per model (Opus 1×, Sonnet 0.4×, Haiku 0.1× equivalent quota
  burn per Anthropic Max 20x informal guidance)
- Phase-based heuristic (PLAN heavy on Raid Leader; BUILD heavy on sub-agents; etc.)

Cycle 0 calibrates the heuristic against actual Max 20x experience during the smoke
test cycle.

---

### §14.8 — Q8: 50-session/month awareness

**Rule:** Max 20x has a 50-session/month soft guideline. Each "session" ≈ 5h window of
activity. Foundation needs ~8-10 sessions total at projected pace (4-5 cycles/window ×
8-10 windows = 38 cycles).

**Risk:** If user uses subscription for OTHER work concurrently (claude.ai, other CC
projects), session count rises faster.

**Mitigation:**
- PRE_FLIGHT_CHECKLIST §3.2 user acknowledges "foundation will use 8-10 sessions/month"
- `scripts/raid/session-counter.py` tracks new-session-spawn events from CYCLE_LOG
- Warning at 40 sessions used; halt at 48 sessions (2-session safety buffer)

---

### §14.9 — Q9: Replaces B3 cost-kill-switch

**v1.2 B3 deprecated (but scripts retained for API users):**

- `scripts/raid/cost-tracker.py` — KEPT (works for both subscription token estimate + API $ cost)
- `scripts/raid/cost-summary.py` — KEPT (same)
- `COST_LOG.jsonl` — RENAMED to `QUOTA_LOG.jsonl` per §14.7
- Per-cycle $50 cap → **REMOVED for subscription users**; estimated cycle burn warning
  at 300K tokens (not abort, just warn user)
- Per-foundation $1500 cap → **REMOVED for subscription users**; session-count cap
  (§14.8) is the relevant boundary

**Subscription users (Max 20x): no hard $-cap; user controls via plan choice.**
**API users (future, separate profile): existing B3 caps still apply.**

---

### §14.10 — Q10: Cycle 0 amended deliverables (v1.3 additions)

**Adds to §13.9 list:**

- `contracts/raid/quota-profile.yaml` (Q3) — current: `max-20x` profile
- `scripts/raid/quota-check.sh` (Q4) — pre-cycle quota check
- `scripts/raid/sub-agent-spawn.py` (Q2) — enforces model tiering per role
- `scripts/raid/quota-summary.py` (Q7) — quota dashboard
- `scripts/raid/session-counter.py` (Q8) — 50-session tracking
- `docs/raid/QUOTA_LOG.jsonl` (Q7) — replaces COST_LOG.jsonl
- `docs/raid/RESET_SCHEDULE.md` (Q5-Q6) — tracks known reset windows for documentation

**Renamed:**
- `scripts/raid/cost-tracker.py` → still exists, dual-purpose ($ cost + quota tokens)
- `scripts/raid/cost-summary.py` → still exists, dual-purpose

**Total Cycle 0 deliverables: 43** (was 36 in v1.2). Still size L; ~20% larger.

---

### §14.11 — Wall-clock expectations (Max 20x)

**Per Anthropic Max 20x:**
- 5h window: ~2M tokens equivalent
- Per cycle with §14.2 model tiering: ~400-500K tokens
- **4-5 cycles per 5h window**
- 38 cycles / 4.5 per window = **8.5 windows ≈ 42.5 hours of execution time**
- With realistic user availability (8h/day): **~5-6 calendar days at sustained pace**
- With weekly cap pauses: **~2-3 calendar weeks** (more realistic)
- 50-session cap: foundation uses ~8-10 sessions → 16-20% of monthly budget

**User commitment estimate:**
- ~3-5 "active sessions" per week (5h each — but user is mostly idle during cycle work)
- Watching CYCLE_LOG + ESCALATIONS periodically: 30-60 min/day
- Active intervention on escalations: 1-2h total across 38 cycles
- C38 acceptance review: 2-4h at end

---

### §14.12 — Sources

- [Anthropic Claude Code rate limits and quotas (Aug 2026)](https://www.truefoundry.com/blog/claude-code-limits-explained)
- [Claude Max plan limits guide](https://intuitionlabs.ai/articles/claude-max-plan-pricing-usage-limits)
- [Sub-agent 7× consumption finding](https://www.morphllm.com/claude-rate-limits)
- [40% reduction via Sonnet-conductor + Haiku-researcher pattern](https://www.truefoundry.com/blog/claude-code-limits-explained)
- [Anthropic effective harnesses (model tier guidance)](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Claude usage limits help center](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work)

---

## §15. Agent-tool Coordinator dispatch (v1.5 ADDED 2026-05-29 — supersedes §13.7 v1.4 Semi-AUTO)

> **Why this section exists:** v1.4 §13.7 amended the auto-dispatcher to a "Semi-AUTO"
> ready-signal emitter because the Cycle 0 build assumed Claude tool harness could not
> spawn a fresh Claude session (Adversary R1 BLOCK 3 finding). That assumption was
> half-right: Claude Code CLI cannot be invoked from inside a Bash subprocess in a way
> that respects P1 fresh-session, BUT the **Agent tool** spawns sub-agents with
> cold-start context (no inherited conversation), which IS the P1 invariant's actual
> goal — preventing main-session Raid Leader bloat over 38 cycles.
>
> v1.5 §15 fixes the under-design: replace Semi-AUTO + manual `/raid <N>` per cycle
> with a Coordinator pattern that runs the entire foundation in ONE main session via
> Agent-tool sub-agent dispatch. User invokes `/raid` ONCE.

### §15.1 — Coordinator pattern

When user invokes `/raid` (no cycle number), Claude main session enters Coordinator
mode (defined by `.claude/commands/raid.md` slash command). The Coordinator:

```
LOOP:
  1. Read docs/raid/CYCLE_LOG.md to find next PENDING cycle whose deps are all DONE
  2. If none -> all cycles done -> exit (report success)
  3. Read the cycle brief docs/raid/cycle_briefs/<NN>_*.md
  4. Construct cycle-runner prompt (template at scripts/raid/cycle-runner-prompt.md)
  5. Invoke Agent tool with:
       subagent_type: general-purpose
       prompt: cycle-runner-prompt + cycle-specific scope
       model: <per §14.2 tier — usually opus-4-7 for cycle leader>
  6. Sub-agent runs full 12-phase cycle in COLD-START context (P1 satisfied)
  7. Sub-agent returns <=1500 token condensed summary (P4 satisfied)
  8. Coordinator validates summary + updates CYCLE_LOG row + AUDIT_LOG
  9. Goto LOOP
```

**Key invariants preserved from prior versions:**
- **P1 fresh-session-per-cycle:** Agent-tool sub-agent cold-start = NEAR-ZERO context (no inherited conversation). Equivalent to a fresh Claude Code session in the only way that matters (preventing Raid Leader bloat).
- **P4 sub-agent return budget:** Coordinator enforces <=1500 token return; rejects oversized returns.
- **P2 startup routine:** sub-agent executes startup-verifier.sh as Step 1.
- **P5 compaction recovery:** sub-agent runs recovery-protocol-runner.sh if IN_PROGRESS state exists.
- **P3 IN_PROGRESS:** sub-agent writes its own IN_PROGRESS state; Coordinator can monitor.
- All §13 B-protections (worktrees, test-infra, prod-isolation, secret-scan, briefs) execute inside sub-agent.
- All §14 Q-protections (quota-check, model tiering, session-counter) honored by Coordinator before each dispatch.

### §15.2 — Coordinator main-session token budget

Per-cycle Coordinator overhead:
- Read CYCLE_LOG row (~200 tokens)
- Read cycle brief (~4000 tokens)
- Construct prompt + invoke Agent (~5000 tokens prompt context — Agent call cost is in sub-agent)
- Receive <=1500 token summary
- Update CYCLE_LOG + AUDIT_LOG (~500 tokens)

**Coordinator main-session cumulative per cycle: ~11K tokens.** Over 38 cycles: ~420K tokens.
Well within 1M context budget. If quota window hits cap mid-foundation, Coordinator
pauses gracefully (Anthropic 429); user waits for reset window; re-invokes `/raid`;
Coordinator resumes from CYCLE_LOG state.

### §15.3 — Sub-agent per-cycle context cost

Each cycle sub-agent has its OWN fresh context window:
- Prompt + brief + repo context: ~10-20K tokens
- BUILD work + tool calls: ~50-200K tokens depending on cycle size
- DPS sub-spawns if cycle requires: nested Agent calls (one level deep)
- Return summary: <=1500 tokens to Coordinator

Per §14.2 model tiering, sub-agent uses Sonnet/Haiku where appropriate. Cycle leader
sub-agent typically Opus 4.7 (orchestration); DPS nested sub-agents Sonnet 4.6.

### §15.4 — What v1.5 deprecates from v1.4

| v1.4 Component | v1.5 disposition |
|---|---|
| `auto-dispatcher.py` (Semi-AUTO ready-signal emitter) | DEPRECATED — kept for backwards compat; v1.5 Coordinator does not call it |
| `READY_FOR_CYCLE_<N>.signal` files | DEPRECATED — no longer written by Coordinator |
| `.session-cycle-lock` paired states (UNLOCKED <-> 00X <-> READY_FOR_N <-> N) | SIMPLIFIED — only tracks "Coordinator session active" with cycle N (no READY_FOR_N intermediate) |
| `orchestrator.py raid <N>` per-cycle entry point | DEPRECATED — fallback only for manual single-cycle re-run; primary flow is Coordinator |
| 5 paired-state probes in smoke (P1-1B) | DEPRECATED — no lock state machine to probe |
| User opens fresh Claude Code session per cycle | NOT REQUIRED — single main session for all 38 cycles |
| User runs `/raid <N>` 37 times | NOT REQUIRED — user runs `/raid` ONCE |

**v1.4 mechanism remains available as fallback** for cycles that genuinely need
manual single-cycle invocation (e.g., debugging a specific cycle in isolation).

### §15.5 — What v1.5 ADDS

| New deliverable | Purpose |
|---|---|
| `.claude/commands/raid.md` | Slash command — paste-and-go Coordinator prompt for user invocation |
| `scripts/raid/cycle-runner-prompt.md` | Cold-start sub-agent prompt template Coordinator interpolates per cycle |
| `scripts/raid/coordinator-helper.py` | Small utility: Coordinator next-pending-cycle query against CYCLE_LOG.md |
| RAID_WORKFLOW.md §15 (this section) | The spec |

### §15.6 — Escalation handling in v1.5

If cycle sub-agent returns escalation (e.g., 3-retry exhausted, design gap surfaced,
secret leak detected):
1. Sub-agent writes ESCALATIONS.md row before returning
2. Returns summary with `result: ESCALATED, type: <error-type>`
3. Coordinator detects ESCALATED status -> halts loop -> prints escalation summary to user
4. Coordinator exits gracefully (no further cycles dispatched)
5. User investigates + resolves + re-invokes `/raid` to resume

Quota-block (§14.5 Q5/Q6) is NOT an escalation — Coordinator pauses gracefully on
Anthropic 429; user re-invokes `/raid` after reset window; Coordinator resumes.

### §15.7 — Migration from v1.4 (what to do with existing C0 artifacts)

C0 v1.4 already shipped 46 deliverables (commit 203ff879). v1.5 does NOT require
re-shipping those — most are still valid:

**Still valid (no change):** orchestrator.py (raid command kept for fallback);
startup-verifier.sh; recovery-protocol-runner.sh; recover-from-crash.sh; in-progress-state-writer.py;
escalation-writer.py; compaction-detector.py; files-from-cycle.sh; sub-agent-spawn.py;
quota-check.sh + _quota_helper.py; quota-summary.py; session-counter.py; cost-tracker.py +
cost-summary.py; brief-generator.py; brief-structure-validator.sh; regenerate-briefs.sh;
worktrees-{create,cleanup,check}.sh; test-infra-{up,down,template}; prod-isolation-lint.sh;
.gitleaks.toml; secret-scan-{dps,cycle,final}.sh; health-dashboard.py; verify-cycle-template.sh;
post-commit-verifier-prompt.md; force-lock-state.sh (testing helper); all 38 cycle briefs;
infra/foundation-{dev,staging}/; contracts/raid/quota-profile.yaml; docs/raid/RAID_WORKFLOW.md.

**Deprecated but kept (for backwards compat):** auto-dispatcher.py;
READY_FOR_CYCLE_1.signal (already in repo — Coordinator ignores it).

**To add in v1.5 amendment commit:**
- `.claude/commands/raid.md`
- `scripts/raid/cycle-runner-prompt.md`
- `scripts/raid/coordinator-helper.py`
- This §15 amendment (already done)
- Update CYCLE_0_PLAN.md §8 (Adversary code-R2 entry — what v1.5 fixes)
- Update SESSION_PATCH.md (v1.5 amendment entry)

**Smoke test:** v1.4 smoke (40/40 PASS, commit 203ff879) remains valid — the 5
paired-state probes still exercise orchestrator refusal logic (kept for fallback).
v1.5 adds NEW lighter-weight smoke: spawn 1 dummy "cycle 999 helloworld" via Agent
tool, verify cold-start sub-agent receives correct prompt + returns valid summary +
Coordinator updates state. This proves the dispatch mechanism actually works
end-to-end.

### §15.8 — Sources

- Anthropic Claude Code Agent tool documentation (sub-agent cold-start pattern)
- Workflow tool documentation (pipeline/parallel orchestration — RAID v1.5 borrows the orchestrator-coordinator pattern but uses direct Agent calls for simpler resume semantics)
- AMAW v3.0 sub-agent dispatch pattern (review-only) — RAID v1.5 extends to per-cycle execution

---

## §16. Task portability via `.raid/active-task.yaml` (v1.6 ADDED 2026-05-29 — supersedes hardcoded paths)

### §16.1 — Problem v1.6 solves

v1.5 hardcoded `docs/plans/2026-05-29-foundation-mega-task/` in 5 script files + 2 prompt templates. Consequences:
- Cannot run RAID on a different branch without forking + editing all scripts
- Cannot run two RAID tasks in the same repo on different branches
- Adversary R1 BLOCK 3 (resolved in v1.5) noted the broader problem of "RAID infrastructure tied to a single task instance"

### §16.2 — Solution: per-branch task config

- **File:** `.raid/active-task.yaml` (committed per branch — like CI config, not user-local)
- **Schema:** declares task_id, task_slug, plan_dir, workflow_doc, decomposition_doc, locked_qs_doc, pre_flight_doc, brief_dir, cycle_log, audit_log, escalations_log, in_progress_dir, quota_log, cycle_count, first_cycle, last_cycle, bootstrap_cycle, quota_profile
- **Loader:** `scripts/raid/task_config.py` (Python, pyyaml stdlib-adjacent dep already used by `in-progress-state-writer.py`). Subcommands: `dump`, `get <key>`, `path <key>`, `abspath <key>`, `validate`, `keys`
- **Importable:** `from task_config import load_config; cfg = load_config()` — used by `brief-generator.py` and any future Python RAID script
- **Bash invocation:** `python scripts/raid/task_config.py get <key>` — used by `startup-verifier.sh`, `recovery-protocol-runner.sh`

### §16.3 — Refactored consumers

| Script | Before (hardcoded) | After (config-driven) |
|---|---|---|
| `brief-generator.py` | `PLANS_DIR = REPO_ROOT/"docs"/"plans"/"2026-05-29-foundation-mega-task"` | `from task_config import load_config; PLANS_DIR = REPO_ROOT / load_config()["plan_dir"]` |
| `startup-verifier.sh` | `PLANS_DIR="$REPO_ROOT/docs/plans/2026-05-29-foundation-mega-task"` | `PLANS_DIR="$REPO_ROOT/$(python "$TASK_CONFIG" get plan_dir)"` |
| `recovery-protocol-runner.sh` | Same as above | Same fix |
| `cycle-runner-prompt.md` | Literal path string in required-reading list | `<LOCKED_QS_DOC>` `<WORKFLOW_DOC>` placeholders interpolated by Coordinator from `task_config.py dump` |
| `.claude/commands/raid.md` | Literal reference to `docs/plans/2026-05-29-foundation-mega-task/RAID_WORKFLOW.md` | Reference to `.raid/active-task.yaml::workflow_doc`; Coordinator Step 2 runs `task_config.py dump` first |

### §16.4 — Coordinator startup contract (updated for v1.6)

When `/raid` is invoked, the Coordinator MUST run these steps BEFORE entering the dispatch LOOP:

1. **Acknowledge** "RAID v1.6 Coordinator mode active..."
2. **Load:** `python scripts/raid/task_config.py dump` → keep JSON in working memory
3. **Validate:** `python scripts/raid/task_config.py validate` → exits non-zero if any declared path missing (catches branch-mismatch). If fails, halt and ask user to fix `.raid/active-task.yaml`.
4. **Verify prereqs:** lock state UNLOCKED, ≥1 PENDING cycle exists in `<cycle_log>`, no stale worktrees
5. Then enter LOOP per §15

### §16.5 — Portability semantics

| Scenario | Behavior |
|---|---|
| Same branch, same task | Identical to v1.5 — config just declares what was hardcoded |
| Same branch, different task (e.g. v2.0 foundation rev) | Edit `.raid/active-task.yaml` to point to new plan_dir/workflow_doc; commit; `/raid` picks up new task |
| Different branch, different task | Each branch commits its own `.raid/active-task.yaml`; switching branches switches task context automatically |
| Branch with no `.raid/active-task.yaml` | `task_config.py` exits 3 with clear message; `/raid` refuses to start |
| `.raid/active-task.yaml` references missing files (branch mismatch) | `task_config.py validate` exits 5; Coordinator halts with diff of missing paths |

### §16.6 — What v1.6 does NOT do (deferred to v1.7+)

- **Multi-task concurrent execution in same repo:** v1.6 assumes ONE active task per repo at any time. Running 2 RAID tasks in parallel (e.g. foundation + a parallel L8-server work) would need lock/worktree namespacing per task — defer until needed
- **Docs refactor:** CYCLE_DECOMPOSITION, BEGIN_CYCLE_0, SESSION_PATCH retain hardcoded `2026-05-29-foundation-mega-task` references — those are task-specific by nature; not paths a different task would inherit
- **Schema validation:** v1.6 loader checks declared paths exist; does NOT enforce schema (e.g. cycle_count is int, plan_dir is dir). Add `cerberus` or `pydantic` validation if config typos start causing problems
- **Auto-detect fallback:** if `.raid/active-task.yaml` missing, v1.6 fails loud rather than auto-detecting the newest `docs/plans/*-foundation-mega-task` dir. Loud-fail is intentional for now — auto-detect can mask config drift

### §16.7 — Sources

- 12-Factor App: Config (https://12factor.net/config) — config separate from code
- POSIX environment-variable + config-file pattern (cron, systemd unit files)
- Anthropic Agent SDK file-tool conventions — read-config-first as Step 0

---

## §17. Post-RAID Comprehensive Review (v1.7 ADDED 2026-05-30 — mandatory end-of-run gate)

After ALL build cycles are DONE (Coordinator `next-cycle` → `idle`), the Coordinator MUST run the **Post-RAID Comprehensive Review** BEFORE reporting "ready to PR" or opening a PR to `main`. This is a permanent anti-drift / anti-tech-debt gate: per-cycle review (the 12-phase, cold-start sub-agent) structurally cannot see cross-cycle drift, "contract-complete but skeleton" gaps, escalation-log noise, missing CI, or invariant-enforcement that silently went NOTE-only.

**Canonical spec:** [`docs/raid/POST_RAID_REVIEW_PROTOCOL.md`](../../raid/POST_RAID_REVIEW_PROTOCOL.md) (task-agnostic; portable across RAID tasks).

**Summary:**
- **3 multi-agent + adversarially-verified passes:** Acceptance audit (escalation reconciliation · artifact completeness · git integrity) · Decisions audit (locked-decision drift/debt) · Dimension review (architecture/invariant drift · contract conformance · security/GDPR · test-quality/live-smoke) + an integrated build.
- **Output:** `<plan_dir>/POST_RAID_REVIEW_FINDINGS.md` — `PRR-NN` findings + Fix Log + **Triage disposition** + a machine-readable `POST-RAID-REVIEW: CLEAR|BLOCKED` verdict line. Every deferral → a `docs/deferred/DEFERRED.md` row (defer = tracked, never forgotten).
- **Gate:** `scripts/raid/post-raid-review-gate.sh` PASSES only when the findings doc exists, has a Triage disposition, and is stamped CLEAR. The Coordinator runs it before PR; BLOCKED halts the loop.
- **CLEAR ≠ production-complete** — it means reviewed + nothing silently lost; HIGH deferred rows remain the explicit before-prod gate.
- **Origin:** the foundation mega-task review (2026-05-30) surfaced **45 findings** (a forgeable admin auth, dead-at-runtime PII masking, an exit-0 worker fleet, a 64% projection-coverage gap, 24 spurious escalations, …) that no per-cycle review caught — see `docs/plans/2026-05-29-foundation-mega-task/POST_RAID_REVIEW_FINDINGS.md`.
