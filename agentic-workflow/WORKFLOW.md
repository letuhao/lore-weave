# Agent Workflow v2

> A structured development workflow for AI coding agents. Combines the best of [Superpowers](https://github.com/obra/superpowers) (execution discipline, TDD, verification gates) with session persistence, role-based review, and enforcement mechanisms.
>
> **How to use:** Paste this into your `CLAUDE.md` or agent instructions. Customize paths marked with `[CUSTOMIZE]`.

---

## Task Workflow (12 phases)

Every task follows this workflow. The agent plays all roles sequentially.

**ENFORCEMENT: This workflow uses a state machine (`.workflow-state.json`). You MUST call the phase transition protocol before moving between phases. Hooks will block commits if verification evidence is missing.**

```
Phase          | Role              | What Happens
---------------|-------------------|----------------------------------------------
1. CLARIFY     | Architect + PO    | Brainstorm, ask questions, define scope
2. DESIGN      | Lead              | API contract / component API / data flow
3. REVIEW      | PO + Lead         | Review design spec before coding
4. PLAN        | Lead + Developer  | Decompose into bite-sized tasks (2-5 min)
5. BUILD       | Developer         | Write code (TDD: red -> green -> refactor)
6. VERIFY      | Developer         | Evidence-based verification gate
7. REVIEW      | Lead              | Code review (spec compliance + quality)
8. QC          | QA / PO           | Test against acceptance criteria
9. POST-REVIEW | Human + Developer | Human-interactive review (context reset)
10. SESSION    | Developer         | Update session notes + task status
11. COMMIT     | Developer         | Git commit (+ push if approved)
12. RETRO      | All               | Record decision/workaround if learned
```

**Status tracking:** `[ ]` not started · `[C]` clarify · `[D]` design · `[P]` plan · `[B]` build · `[V]` verify · `[R]` review · `[Q]` QC · `[PR]` post-review · `[S]` session · `[x]` done

**Task types:** `[FE]` frontend · `[BE]` backend · `[FS]` full-stack

---

## Task Size Classification (MANDATORY — do this BEFORE any work)

Agents misjudge task size. They call things "small" to skip phases. This protocol removes subjectivity.

**Before starting any task, count 3 things:**

| Metric | How to count |
|--------|-------------|
| **Files touched** | How many files will be created or modified? |
| **Logic changes** | How many functions/methods/handlers will change behavior? (not formatting) |
| **Side effects** | Does it change: API contract, DB schema, config, external behavior, types used by other files? |

**Classification (objective, not negotiable):**

| Size | Files | Logic | Side effects | Allowed skips |
|------|-------|-------|--------------|---------------|
| **XS** | 1 | 0-1 | None | CLARIFY + PLAN |
| **S** | 1-2 | 2-3 | None | PLAN only |
| **M** | 3-5 | 4+ | Maybe | None |
| **L** | 6+ | Any | Yes | None. Write plan file. |
| **XL** | 10+ | Any | Yes | None. Write spec + plan. Subagent recommended. |

**State it explicitly before work begins:**
```
Task: Fix pagination off-by-one
Size: XS (1 file, 1 logic change, 0 side effects)
Skipping: CLARIFY, PLAN -> straight to BUILD
```

**Using the enforcement script:**
```bash
./scripts/workflow-gate.sh size XS 1 1 0    # Classify task
./scripts/workflow-gate.sh phase build       # XS allows skipping to BUILD
```

**Anti-gaming rules:**
- The script validates counts vs claimed size — **cannot undersize**
- If you haven't read the code yet, **you don't know the size** — don't classify
- If during BUILD you discover it's larger — **STOP, reclassify, resume correct phase**

**NOT XS (agents commonly misjudge these):**
- "Simple" CSS fix -> often touches multiple components = S or M
- "Quick" API rename -> changes contract, affects callers = M+
- "Small" bug fix -> if root cause unclear = M+ (debugging protocol)
- "Just add a field" -> migration + API + UI + types = L

### Anti-Skip Rules (MANDATORY)

**Common skip patterns — ALL are violations:**

| Skip pattern | Why agents do it | Why it's forbidden |
|---|---|---|
| Skip CLARIFY, jump to BUILD | "The task seems obvious" | Unexamined assumptions cause rework |
| Skip PLAN, jump to BUILD | "It's a small change" | Small changes grow; no plan = no checkpoint |
| Skip VERIFY after BUILD | "Tests passed earlier" | Stale results are not evidence |
| Skip REVIEW after VERIFY | "I wrote it, I know it's correct" | Author blindness is real |
| Skip POST-REVIEW | "I already reviewed in phase 7" | Phase 7 review has author blindness — you wrote this code moments ago. POST-REVIEW forces context reset via human interaction, then fresh re-read from disk. **NEVER skippable.** |
| Skip SESSION before COMMIT | "I'll update later" | You won't. Context is lost |
| Combine multiple phases | "CLARIFY+DESIGN+PLAN in one go" | Phases exist to create pause points |

**If you catch yourself about to skip — STOP, announce the skip attempt, ask the user.**
User can authorize skips explicitly — agent must never self-authorize.

**Phase transition protocol:**
1. State task size classification before starting (XS/S/M/L/XL with counts)
2. Before starting any phase, run `./scripts/workflow-gate.sh phase <name>`
3. Before leaving any phase, run `./scripts/workflow-gate.sh complete <name> "<evidence>"`
4. If during work you discover the task is larger than classified — STOP, reclassify, announce to user
5. User can authorize additional skips explicitly — but the agent must never self-authorize

---

## Role Perspectives

| Role | Thinks about... |
|------|-----------------|
| **Architect** | System boundaries, dependencies, scoping, impact analysis |
| **PO (Product Owner)** | User value, acceptance criteria, design sign-off, final QC |
| **Lead** | Technical design, plan quality, code review (patterns, security, a11y) |
| **Developer** | Correctness, TDD, efficiency, verification, session tracking |
| **QA** | What can break — edge cases, regression, acceptance criteria |

When playing each role, shift perspective accordingly. Don't just check boxes — think from that role's viewpoint.

---

## Phase Details

### Phase 1: CLARIFY (Brainstorming Protocol)

Don't jump into code — clarify first.

1. **Explore context** — read relevant files, docs, git history
2. **Ask ONE question at a time** — multiple choice preferred, never overwhelm
3. **Propose 2-3 approaches** with trade-offs after enough context
4. **Present design in sections** — scale to complexity (few sentences to 300 words per section)
5. **Write spec file** to `docs/specs/YYYY-MM-DD-<topic>.md` for non-trivial tasks
6. **Self-review spec** — check for placeholders, contradictions, ambiguity, scope creep
7. **User approval gate** — do NOT proceed without user sign-off

> **Skip conditions:** Only for tasks classified **XS** (1 file, 0-1 logic, 0 side effects). If you haven't counted yet, you can't skip.

### Phase 2: DESIGN

- Define API contracts, component APIs, data flow diagrams
- Identify breaking changes and migration needs
- Consider error states, edge cases, backwards compatibility

### Phase 3: REVIEW (Design Review)

- PO: Does this meet acceptance criteria? Is scope right?
- Lead: Is the design sound? Any architectural concerns?
- Gate: Do NOT proceed to Phase 4 without sign-off

### Phase 4: PLAN (Task Decomposition)

Break work into executable chunks before coding.

- Decompose into **bite-sized tasks (2-5 minutes each)**
- Each task specifies: **exact file paths, code intent, verification command**
- **No placeholders allowed** — no "TBD", "TODO", "add error handling here"
- For large tasks (>5 files), write plan to `docs/plans/YYYY-MM-DD-<feature>.md`
- Self-review: spec coverage, placeholder scan, type/signature consistency

**Execution mode** (for large plans):
| Mode | When | How |
|------|------|-----|
| **Inline** (default) | Most tasks | Execute sequentially with checkpoints |
| **Subagent dispatch** | Multi-file, independent tasks | Fresh agent per task + 2-stage review |

Subagent 2-stage review:
1. **Spec compliance** — does it match the design?
2. **Code quality** — patterns, security, performance
3. Never skip either stage; never proceed with unfixed issues

> **Skip conditions:** Only for tasks classified **XS** or **S**. If S, CLARIFY is still required.

### Phase 5: BUILD (TDD Discipline)

For each task in the plan:

```
1. RED    — Write a failing test (must fail for the right reason)
2. GREEN  — Write minimal code to pass (no more than needed)
3. REFACTOR — Clean up while tests stay green
4. COMMIT — Small, atomic commit
```

> **When TDD doesn't apply:** UI layout, config changes, docs, migrations — just build and verify.

### Phase 6: VERIFY (Evidence Gate)

**Evidence before claims, always.**

5-step gate before ANY completion claim:

| Step | Action |
|------|--------|
| 1. Identify | What command proves the claim? (test, build, lint, curl...) |
| 2. Run | Execute it fresh — not from memory or cache |
| 3. Read | Complete output including exit codes |
| 4. Confirm | Does output actually match the claim? |
| 5. Claim | Only now state the result, with evidence |

**Red flags — stop immediately if you catch yourself:**
- Using "should work", "probably passes", "seems fine"
- Feeling satisfied before running verification
- About to commit/push without fresh test run
- Trusting prior output without re-running

**Applies before:** success claims, commits, PRs, task handoffs, session notes.

### Phase 7: REVIEW (2-Stage Code Review)

| Stage | Focus |
|-------|-------|
| **1. Spec compliance** | Does code implement what was designed? Missing requirements? Scope creep? |
| **2. Code quality** | Patterns, security, a11y, performance, maintainability |

Both stages must pass. If issues found: fix -> re-verify (Phase 6) -> re-review.

### Phase 8: QC

- QA perspective: test against acceptance criteria
- Edge cases, error states, regression checks
- If QC fails: loop back to Phase 5 BUILD

### Phase 9: POST-REVIEW (Human-Interactive Context Reset)

**Why this phase exists:** AI agents suffer from author blindness — they can't objectively review code they just wrote because the reasoning is still in context. A forced human interaction breaks the agent's thought chain, effectively resetting its perspective. When the agent resumes after the human responds, it re-reads code from scratch rather than relying on what it *thinks* it wrote.

**This phase is NEVER skippable, regardless of task size.**

**Step 1 — Present summary to human (MANDATORY STOP):**
- List all files created/modified with one-line descriptions
- Summarize what was built and key design decisions
- Report verification evidence (build, tests, type-check)
- **STOP and WAIT for human response.** Do NOT proceed until the human replies.

**Step 2 — After human responds, adversarial review:**
- **Re-read ALL changed files from disk** — do NOT rely on memory or prior context
- Review with an adversarial mindset: actively try to break the code
- Check these categories:

| Category | What to look for |
|----------|-----------------|
| **Logic** | Off-by-one, null handling, missing edge cases, wrong operator |
| **Data flow** | Can fields be null when code assumes non-null? Are transformations reversible when they should be? |
| **API contract** | Request/response mismatch, missing validation, wrong HTTP status codes |
| **State** | Cache staleness, race conditions, stale closures |
| **Integration** | Does the new code break existing callers? Are mocks in tests updated? |
| **Security** | Input validation at boundaries, injection, auth bypass |

**Step 3 — Report findings:**
- If issues found: list them with severity, then fix → loop back to Phase 6 VERIFY
- If no issues found: state explicitly "Post-review: 0 issues found" with evidence of what was checked
- Complete with: `./scripts/workflow-gate.sh complete post-review "<N issues found, M fixed>"`

### Phase 10: SESSION

<!-- [CUSTOMIZE] Change the path below to your project's session tracking file -->

Update session notes after EVERY sprint completes. Don't batch.

What to include:
- Sprint number and one-line outcome
- New/modified files, migrations, commits
- Review issues found and how fixed
- Live test results (real stack, not mocked)
- What's next

### Phase 11: COMMIT

- Write clear commit message (what + why)
- `git commit` — small and atomic preferred
- Push only with user approval or pre-authorized rules

### Phase 12: RETRO

- If a non-obvious decision was made -> record it (decision log, ADR, lesson, etc.)
- If a workaround was needed -> record it with context so it can be revisited
- If nothing notable -> skip this phase

---

## Debugging Protocol

Activated whenever a bug is encountered during any phase.

**Rule: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

```
Phase      | What Happens
-----------|----------------------------------------------
1. INVEST  | Read errors fully, reproduce, trace data flow backward
2. PATTERN | Find working examples, compare every difference
3. HYPOTHE | State hypothesis, test one variable at a time
4. FIX     | Write failing test -> implement single fix -> verify
```

**Hard stop:** If 3+ fix attempts fail -> stop. Question the architecture. Discuss with user before continuing.

**Anti-patterns (never do these):**
- Propose fix before tracing data flow
- Attempt multiple fixes simultaneously
- Skip test creation for the bug
- Make assumptions without verification

---

## Git Workflow

| Task size | Strategy |
|-----------|----------|
| **Small** (1-3 files) | Work on current branch |
| **Large** (>5 files, >1 hour) | `git worktree` — isolated branch, clean baseline |

**Worktree protocol:**
1. Create worktree on new branch
2. Verify tests pass before starting (clean baseline)
3. On completion: present merge/PR/discard options to user
4. Clean up worktree after merge

---

## Test Workflow (for QC/E2E tasks)

Lighter workflow for writing tests (not features).

```
Phase     | What Happens
----------|----------------------------------------------
1. SETUP  | Install deps, shared utilities, verify infra
2. WRITE  | Write tests (one sprint at a time)
3. RUN    | Execute against live stack
4. FIX    | Triage: test bug vs real bug vs infra issue
5. REPORT | Results, session notes, commit
```

Repeat 2-5 per sprint.

**Status:** `[ ]` not started · `[S]` setup · `[W]` writing · `[R]` running · `[F]` fixing · `[x]` done

**Failure triage:**
| Type | Example | Action |
|------|---------|--------|
| **Test bug** | Wrong selector, bad assertion | Fix the test |
| **Real bug** | Endpoint 500, wrong data | Fix product code, re-run |
| **Infra issue** | Docker not ready, service down | Mark `skip`, don't fail suite |

---

## Quick Reference Card

```
CLARIFY -> DESIGN -> REVIEW -> PLAN -> BUILD -> VERIFY -> REVIEW -> QC -> POST-REVIEW -> SESSION -> COMMIT -> RETRO
   C          D         R        P       B        V         R       Q        PR             S         x         x

Size classification: count files + logic + side_effects BEFORE starting
Skip CLARIFY+PLAN: only XS (1 file, 0-1 logic, 0 side effects)
Skip PLAN only: XS or S (1-2 files, 0 side effects)
POST-REVIEW: NEVER skippable — present to human, wait, re-read code fresh, adversarial review
Skip TDD for: UI layout, config, docs, migrations
Hard stop debugging after: 3 failed fix attempts
Verify gate: run command -> read output -> then claim
```

---

## Credits

- **Session persistence, role perspectives** — [free-context-hub](https://github.com/) workflow (2024-2026)
- **Brainstorming, TDD, verification gate, debugging, subagent dispatch** — [Superpowers](https://github.com/obra/superpowers) by Jesse Vincent / Prime Radiant

---

*Workflow v2.1 — last updated 2026-04-16*
