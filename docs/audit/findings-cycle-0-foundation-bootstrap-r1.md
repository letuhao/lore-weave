# Adversary findings -- cycle-0-foundation-bootstrap -- round 1

**Verdict:** REJECTED
**Reviewer:** Adversary cold-start (general-purpose sub-agent)
**Reviewed:** CYCLE_0_PLAN.md against RAID_WORKFLOW Sections 13 + 14, CYCLE_DECOMPOSITION C0, PRE_FLIGHT NOTES

---

## Finding 1: BLOCK -- Smoke test Section 4 omits ALL Q-protections (Q1-Q9), making Section 14 quota-aware execution unverified before auto-dispatch fires Cycle 1

**Where:** CYCLE_0_PLAN.md Section 4 "VERIFY plan -- smoke test exit criteria" enumerates checks for P1-P10 (10 P-protections) and B1-B6 (6 B-protections) totaling "All 16 checks emit [PASS]". The deliverable inventory (Section 2 v1.3 row) ships 7 Q-protection items (Q2 sub-agent-spawn, Q3 quota-profile, Q4 quota-check, Q7 quota-summary + QUOTA_LOG.jsonl, Q8 session-counter, Q5-Q6 RESET_SCHEDULE), but the smoke test does NOT exercise a single Q-protection.

**What the spec says:** RAID_WORKFLOW.md Section 14.10 explicitly adds 7 Q-deliverables to Cycle 0; Section 14 declares them MANDATORY for subscription (Max 20x) users; PRE_FLIGHT Section 3.2 captures user sign-off (5 distinct quota acknowledgments). Section 14.4 Q4 mandates a pre-cycle quota check returning PROCEED/RISKY/WAIT; Section 14.2 Q2 mandates sub-agent model tier enforcement (Opus/Sonnet/Haiku); Section 14.7 Q7 mandates QUOTA_LOG.jsonl rows per phase event. None of these are verified by smoke.

**Why this is the canonical false-green pattern (lesson 5 "xor-paired choice silently suppresses"):** Cycle 1 (L1.E Meta HA, 4 DPS) immediately depends on Q-protections: it spawns 4 sub-agents which Section 14.2 requires to be Sonnet-tiered (not Opus). If sub-agent-spawn.py is silently broken (e.g., model param drops through), C1 spawns 4 Opus sub-agents and burns the 5h window in one cycle -- exactly the failure Section 14 was written to prevent. Smoke is the LAST GATE before /raid 1 fires, yet it gives a green light without testing the gate logic. Same pattern as lesson 5 ("xor rate unit test masked this bug by using a hand-built library") -- smoke uses pass criteria that do not actually exercise the protection being tested.

**Recommended fix (must precede BUILD):**
1. Add Section 4 entries Q1-Q9: smoke MUST (a) invoke quota-check.sh and assert output schema (PROCEED|RISKY|WAIT) + log row written to QUOTA_LOG.jsonl; (b) spawn smoke DPS via sub-agent-spawn.py with role=DPS and assert the launched model is sonnet-4-6 (not Opus); (c) assert session-counter.py increments by 1; (d) assert quota-summary.py reads the new QUOTA_LOG row.
2. Update smoke pass-count from 16 to ~25 checks (or fold Q checks into the existing matrix).
3. Update Section 13.7 smoke cycle acceptance criteria enumeration to match (Section 13.7 was written for v1.2 -- predates Section 14 -- so the plan inherited the gap from the spec; this finding is partially a spec-coverage hole that the plan should close rather than propagate).

**Severity:** BLOCK. Auto-dispatch firing /raid 1 after a smoke that did not exercise Q-protections is exactly the "broken C0 but C1 fires anyway" anti-pattern Section 13.8 AUTO row claims to prevent.

---

## Finding 2: BLOCK -- Plan Section 4 #5 explicitly downgrades P5 compaction-recovery test from "force a summarization" (spec requirement) to "assert detector script runs without error" -- guarantees false-green

**Where:** CYCLE_0_PLAN.md Section 4 row 5 reads: "P5 compaction recovery: smoke does NOT actually trigger compaction (too unreliable); instead, asserts the detector script's heuristic runs without error."

**What the spec says:** RAID_WORKFLOW.md Section 13.7 explicit acceptance criteria for the smoke cycle: "All 10 P-protections exercised: fresh session, startup routine, IN_PROGRESS file written + read, sub-agent return within budget, **compaction simulation (force a summarization)**, cycle brief structure validated, ..." (emphasis added). The spec uses the phrase "compaction simulation (force a summarization)" -- a deliberate verb, not a passive "runs without error". Section 12.5 P5 specifies an 8-step recovery protocol triggered by a compaction event; testing without triggering the event tests nothing about the protocol.

**Why this is a guaranteed false-green:** "Runs without error" passes if compaction-detector.py is a no-op def detect(): return False. The detector is the ONLY signal that triggers steps 1-8 of P5 recovery. If detector is broken (always returns False), the entire P5 recovery flow is dead code that no test ever exercises until cycle 17 (DP-kernel macros, the most token-heavy cycle per Section 14.2 explicit Opus call-out) compacts mid-build, the detector misses it, IN_PROGRESS state diverges from actual git state, and Phase 9 post-commit verifier may DRIFT_DETECTED -- burning a full cycles quota for nothing.

This matches prior adversary-rejection lesson 1: "connectivity invariant from a loose source-spec needs two corrections -- the region AND the algorithm". The plan adopted the loose interpretation ("runs without error") rather than the tight spec interpretation ("force a summarization") -- and as in lesson 1, the loose version is *inert*.

**Recommended fix:**
1. Smoke MUST inject a synthetic compaction event (write a fake tool-result-disappearance signal to a test-mode hook in compaction-detector.py), then assert the detector returns True AND that the recovery protocol's 8 steps execute (P3 re-read, brief re-read, git log cross-check, etc.) -- at minimum verify a compaction_detected row hits AUDIT_LOG.jsonl.
2. If "force a summarization" is genuinely impossible to simulate in a smoke harness (defensible), then explicitly DEFER P5 verification in PRE_FLIGHT NOTES as D6 and ship a contract test that exercises the recovery code path with mocked input -- do NOT ship "runs without error" as the verification.

**Severity:** BLOCK. Per CLAUDE.md "Defer must mean tracked, not forgotten" and "if you find yourself saying skip if time is tight, thats a yellow flag" -- this is the textbook deferral-by-stealth the projects own rules prohibit.

---

## Finding 3: BLOCK -- auto-dispatcher.py "60s pause then /raid 1" mechanism is unspecified and structurally cannot satisfy P1 fresh-session invariant from within the C0 Claude session

**Where:** CYCLE_0_PLAN.md Section 3 Batch B6 lists scripts/raid/auto-dispatcher.py (AUTO) -- 60s pause then /raid 1. RAID_WORKFLOW Section 13.7 shows bash scripts/raid/auto-dispatcher.py --start-cycle 1 invoked from inside run-smoke-test.sh, which is invoked from the C0 main Claude session. Plan Section 4 last bullet: "On failure: ESCALATIONS row written + run-smoke-test.sh exits non-zero + auto-dispatcher does NOT fire."

**What the spec says:** RAID_WORKFLOW.md Section 12.1 P1 is the FIRST and most critical context protection:
> "Each cycle MUST be a SEPARATE /raid <N> invocation in a fresh main session. The Raid Leader main context starts at near-zero at every cycle boundary."
> "Anti-pattern: Running multiple cycles in one session (just keep going after this one). Always exit and re-/raid for the next cycle."

Section 13.7 enforcement: scripts/raid/orchestrator.py rejects /raid <N> if the same session already executed a different cycle (sentinel check via .session-cycle-lock).

**Why the plan is structurally broken:** A Python subprocess invoked by Bash invoked by a Claude tool call CANNOT spawn a fresh Claude Code session. It can:
- (a) shell out to claude CLI in a new process -- but Claude Code is typically not invocable as claude /raid 1 and the plan does not specify this mechanism;
- (b) write a sentinel "next cycle = 1" file and exit, leaving the user to invoke /raid 1 manually -- but then the "60s pause" is meaningless and the AUTO label in Section 13.7 is misleading;
- (c) call into the parent Claudes tool harness -- not a supported pattern.

The plan also has a paired lifecycle hole: Section 4 #1 says ".session-cycle-lock shows 00X after smoke start; reset to UNLOCKED after smoke success" -- but does NOT specify who re-locks it to 01 for Cycle 1, when, or how that lock acquisition coordinates with the supposedly-fresh /raid 1 session. This is precisely the paired-protection suppression pattern of lesson 5 (unlocking without specifying the matching re-lock = silent suppression of P1 enforcement at the transition).

Without a specified mechanism, BUILD will either (a) implement option (b) and silently violate Section 13.7s AUTO promise, (b) implement a sleep-and-exec workaround that defeats P1s fresh-context guarantee, or (c) discover at smoke time that auto-dispatch is impossible and ship without it (failing PRE_FLIGHT Section 11s "auto-dispatcher will fire /raid 1 automatically" promise).

**Recommended fix (must precede BUILD):**
1. The plan MUST specify the concrete dispatch mechanism -- likely (b) with explicit user-instruction output ("smoke green; please run /raid 1 in a fresh Claude Code session"), and update Section 13.7 + PRE_FLIGHT Section 11 to reflect that AUTO is actually "semi-AUTO + user step". User opted "AUTO continue" in PRE_FLIGHT Section 3, so this is a contract change requiring user re-sign.
2. The plan MUST specify the .session-cycle-lock state-transition contract for the C0->C1 handoff: who writes 01, when, and what happens if user invokes /raid 1 from same session.
3. Smoke Section 4 #1 MUST add a paired check: after smoke success -> unlock -> next-cycle sentinel = 01 -> verify subsequent /raid 1 invocation acquires the lock atomically.

**Severity:** BLOCK. This is the keystone of RAIDs autonomy story; an undefined dispatcher renders Section 13.7s AUTO gate and 38-cycle autonomous execution promise unimplementable.

---

Captured rules: read pre-loaded (5 prior adversary-rejection lessons + 1 guardrail check pass)
Guardrails relevant: none triggered on "spawn 43 files + smoke test + auto-dispatch"