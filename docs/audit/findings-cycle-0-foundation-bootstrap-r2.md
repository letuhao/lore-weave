# Adversary findings -- cycle-0-foundation-bootstrap -- round 2

**Verdict:** REJECTED
**Reviewer:** Adversary cold-start (general-purpose sub-agent)
**Reviewed:** REVISED CYCLE_0_PLAN.md (R2) against R1 findings + RAID_WORKFLOW.md v1.4 + CYCLE_DECOMPOSITION.md + PRE_FLIGHT_CHECKLIST.md D6 + pre-staged raid/ skeleton
**R1 BLOCKERs status:** B1 partially fixed; B2 paper-thin patch (recovery PROTOCOL still not exercised); B3 new holes introduced

> **Note:** Adversary sub-agent's Write tool was blocked by harness policy. This file
> persisted by parent (Raid Leader main session) from sub-agent's inline return content
> per AMAW audit trail requirement.

---

## Finding 1: BLOCK — P5 smoke assertion (d) conflates P2 5-step startup with P5 8-step recovery PROTOCOL; the "recovery protocol logs 8-step execution" line is a paper-thin patch on R1 BLOCK 2

**Where:** `CYCLE_0_PLAN.md` §4 P-protections row 5 (P5 REAL SIMULATION). Plan invokes `compaction-detector.py --test-mode --inject-event` then `startup-verifier.sh 00X --resume-mode`, asserting (a)-(d) including (d) "recovery protocol logs 8-step execution to AUDIT_LOG".

**What the spec actually says (RAID_WORKFLOW v1.4 §12.5 P5 vs §12.2 P2):**
- §12.2 P2 = **5-step session startup routine** implemented by `scripts/raid/startup-verifier.sh`.
- §12.5 P5 = **8-step compaction recovery protocol** the Raid Leader executes when compaction detected; step 8 = "IF INCONSISTENT: HALT + ESCALATIONS" (the safety-critical branch).

**Why this is false-green by another name:**

1. **No executor for the 8 steps.** Smoke has no Raid Leader. `startup-verifier.sh` is the P2 5-step routine, not the P5 8-step protocol. Deliverable inventory §2 contains **no** `recovery-protocol-runner.sh` or equivalent. `compaction-detector.py` performs detection only.
2. **The HALT branch (step 8) is never exercised.** Smoke writes a CONSISTENT synthetic IN_PROGRESS matching git state; the INCONSISTENT path (worktree dirty / branch SHA mismatch / audit shows different phase) is never injected. This is the single branch that prevents corrupted Raid Leaders from committing fabricated work. R1 lesson 1 ("loose-spec invariant needs two corrections") applies: detector AND HALT branch both need verification; verifying only the happy detector path is *inert*.
3. **"logs 8-step execution"** is the textbook stealth-deferral CLAUDE.md prohibits. A no-op `for s in 1..8; do echo "step $s" >> AUDIT_LOG; done` passes assertion (d) while implementing zero recovery logic.

**Recommended fix:**
- Ship `scripts/raid/recovery-protocol-runner.sh` as a NEW deliverable implementing §12.5 P5 steps 3-8.
- Smoke MUST run TWO P5 scenarios: happy (consistent → continue) AND halt (intentionally mismatched IN_PROGRESS vs git → INCONSISTENT → HALT + ESCALATIONS row with `type=p5_recovery_inconsistent`).
- Replace assertion (d)'s "8-step execution logs" with two specific assertions tied to the consistent + inconsistent code paths.

**Severity:** BLOCK. R1 demanded a real exercise of the recovery code path; R2 ships a more elaborate version that exercises detection only and writes log rows naming steps without running them.

---

## Finding 2: BLOCK — Lock state machine in §3 B6 is self-contradictory AND introduces a new paired-state suppression hole

**Where:** `CYCLE_0_PLAN.md` §3 Batch B6 auto-dispatcher redesign block.

**Contradiction #1 (step 2 vs contract block):**
- Step 2: "Acquires `.session-cycle-lock` transition: `00X` → `READY_FOR_<N>` (paired state — neither UNLOCKED nor `<N>`)"
- Contract block: `UNLOCKED ← (smoke complete) ← 00X ← (smoke start) ← UNLOCKED` then `UNLOCKED → (auto-dispatcher signal) → READY_FOR_<N> → ...`

Per the contract, smoke completion returns the lock to UNLOCKED, then auto-dispatcher does `UNLOCKED → READY_FOR_<N>`. So actual transition is `UNLOCKED → READY_FOR_<N>`, contradicting step 2's `00X → READY_FOR_<N>`. Implementer must guess; either guess produces false-fails/false-blocks.

**Contradiction #2 (paired-state suppression — lesson 5):**

`READY_FOR_<N>` was introduced to pair "deps satisfied + signal emitted" with "/raid <N> entry". Plan covers one direction:
- §3 B6 last bullet: "`orchestrator.py /raid <N>` REFUSES if lock is `<M>` (M ≠ N)"

NO RULE specifies what happens when **lock=UNLOCKED + no signal file**. Sequence:
1. Smoke completes → lock=UNLOCKED
2. Auto-dispatcher crashes mid-run (after lock reset, before signal write) → state: UNLOCKED + no signal + no dep check ever ran
3. User runs `/raid 1`
4. Orchestrator sees UNLOCKED (not `<M> ≠ N`), accepts `/raid 1`, **silently bypassing the auto-dispatcher's deps-satisfied check**

Other unspecified states (all are lesson 5 paired-state holes):
- Smoke succeeds + auto-dispatcher mid-write crash → partial/0-byte signal file → behavior undefined
- User invokes `/raid 1` BEFORE READY_FOR_1.signal emitted → not refused
- `orchestrator.py /raid M` invoked while lock=`READY_FOR_<N>` where M ≠ N → spec refuses only on numeric `<M> ≠ N`, unclear on `READY_FOR_<N>` ≠ M
- User re-runs smoke when lock=00X (prior crash) → `UNLOCKED → 00X` precondition fails, no recovery path

**Recommended fix:**
1. Resolve contradiction: atomic transition `00X → READY_FOR_<N>` inside auto-dispatcher.py (one writer; no UNLOCKED window).
2. `orchestrator.py /raid <N>` MUST refuse unless `(lock == READY_FOR_<N>) AND (READY_FOR_CYCLE_<N>.signal exists with valid YAML schema)`.
3. Specify crash-recovery rules per lock state (00X / READY_FOR_<N> + missing signal / etc.).
4. Smoke adds a paired-state test: `/raid 1` with lock=UNLOCKED + no signal exits non-zero with specific error code.

**Severity:** BLOCK. Self-contradictory spec at the keystone gate + unenforced refusal rule = auto-dispatcher's dep-check is bypassable, defeating the entire reason `READY_FOR_<N>` was introduced.

---

## Finding 3: WARN — Spec/plan drift: CYCLE_DECOMPOSITION.md §Cycle 0 stale (Size M, ~25 deliverables vs canonical 43); RAID_WORKFLOW §13.9 still references renamed COST_LOG.jsonl; brief-generator (B4) will produce wrong briefs

**Where:**
1. `CYCLE_DECOMPOSITION.md` lines 26-67 (§Cycle 0): heading "amended v1.1", Size M, deliverables list only v1.0 core + v1.1 §12 + v1.3 §14 (~25 items). **Completely omits** all v1.2 §13 items: worktree scripts (B1), test-infra scripts (B2), brief-generator+validator+regenerator (B4), prod-isolation-lint (B5), gitleaks config + 3 secret-scan scripts (B6), AUTO `run-smoke-test.sh` + `auto-dispatcher.py` + `00X_helloworld_smoke.md`, infra/foundation-dev + infra/foundation-staging skeletons, `../foundation-worktrees/` dir tree.
2. `CYCLE_0_PLAN.md` §1 cites **43 deliverables**; RAID_WORKFLOW §14.10: "**Total Cycle 0 deliverables: 43**". Numeric drift: decomposition ~25 vs plan/spec 43.
3. `RAID_WORKFLOW.md` §13.9: lists `docs/raid/COST_LOG.jsonl (B3)`. §14.9: "`COST_LOG.jsonl` — RENAMED to `QUOTA_LOG.jsonl`". Plan §2 row #42 lists QUOTA_LOG.jsonl pre-staged; COST_LOG.jsonl appears nowhere in plan.
4. `CYCLE_DECOMPOSITION.md` line 336: "POST-REVIEW is AUTO" — ambiguous post-D6 (per-cycle Phase 9 is AUTO; C0→C1 boundary is Semi-AUTO per v1.4 §13.7).

**Why this matters:**
- `brief-generator.py` (B4) reads `CYCLE_DECOMPOSITION.md §2` per RAID_WORKFLOW §13.4. Stale Cycle 0 row → stale generator authority → ALL 37 auto-generated briefs may inherit drift.
- B2 implementers may create empty `COST_LOG.jsonl` per §13.9 list, then discover §14.9 contradiction → wasted work + ambiguous on-disk state.
- Auditor smoke P6 (brief-structure-validator passes on all 38 briefs) passes structure even with wrong content; drift surfaces only at C1.

**Recommended fix (as first action of B5 batch, before brief-generator runs):**
1. Update `CYCLE_DECOMPOSITION.md §Cycle 0`: heading "amended v1.3", Size **L** (or XL per plan §1), append v1.2 §13 deliverables + Semi-AUTO trio + verify alignment with plan §2 rows #37-43.
2. Amend `RAID_WORKFLOW.md §13.9`: strike `COST_LOG.jsonl (B3)`, add "(superseded by §14.7 QUOTA_LOG.jsonl)".
3. Fix `CYCLE_DECOMPOSITION.md` line 336 to distinguish per-cycle Phase 9 (AUTO) from C0→C1 boundary (Semi-AUTO per v1.4 §13.7).
4. Add `last_synced_with_RAID_WORKFLOW_version` header field to CYCLE_DECOMPOSITION.md so drift is detectable by brief-generator + checkable by startup-verifier.

**Severity:** WARN — does not break C0 build itself (plan §2 is correct at 43) but will silently produce wrong cycle briefs at C1+ via brief-generator and leaves stale COST_LOG.jsonl references B2 implementers may act on.

---

Captured rules: read pre-loaded (5 lessons + 1 guardrail check pass)
R1 fix quality summary:
- **R1 BLOCK 1 (Q-protections):** partial — 8 Q checks added; Q2 uses `--dry-run` string-match (probe, not real spawn); Q5/Q6 uses env-var injection (acceptable synthetic). Net: structurally addresses R1 BLOCK 1.
- **R1 BLOCK 2 (P5):** paper-thin patch — assertion (d) has no executor; HALT branch never exercised; same false-green dressed up. See Finding 1.
- **R1 BLOCK 3 (auto-dispatcher):** new holes — lock state machine self-contradictory; paired-state suppression of `/raid <N>` refusal. See Finding 2.
