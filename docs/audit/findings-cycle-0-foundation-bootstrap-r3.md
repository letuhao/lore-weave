# Adversary findings -- cycle-0-foundation-bootstrap -- round 3

**Verdict:** APPROVED_WITH_WARNINGS
**Reviewer:** Adversary cold-start (general-purpose sub-agent, AMAW XL pragmatic-stop round)
**Reviewed:** REVISED CYCLE_0_PLAN.md (R3) against R2 findings + RAID_WORKFLOW.md v1.4 + CYCLE_DECOMPOSITION.md (R3-updated §Cycle 0) + PRE_FLIGHT_CHECKLIST.md D6 + pre-staged docs/raid/ skeleton

**R2 fix quality:**
- R2 BLOCK 1 (P5 8-step executor): **FIXED** — recovery-protocol-runner.sh added with 6 concrete checks (re-read IN_PROGRESS, brief, LOCKED, git log cross-ref, AUDIT_LOG tail, DPS worktree verify); §4 P5 5A+5B truly exercises both CONSISTENT and INCONSISTENT branches with distinct exit codes/log rows. Substantive, not paper-thin.
- R2 BLOCK 2 (lock state machine): **PARTIAL** — contradictions resolved (atomic 00X→READY_FOR_<N>, refusal rule with 5 cases, 8-state crash-recovery table). Probe setup mechanism for 1B unspecified (Finding 1). Design clean; testability hole.
- R2 WARN 3 (spec/plan drift): **PARTIAL** — header added, COST_LOG.jsonl SUPERSEDED, Phase 9 vs C0→C1 disambiguated. Enforcement logic for the new `last_synced_with_RAID_WORKFLOW_version` header not propagated to brief-generator.py/startup-verifier.sh descriptions in CYCLE_0_PLAN §3 (Finding 2).
- New issue exposed by R3 toolkit additions: recover-from-crash.sh "checks pid file" but no orchestrator-pid file mechanism is specified anywhere (Finding 3).

> **Note:** Adversary sub-agent's Write tool was blocked by harness policy. This file
> persisted by parent (Raid Leader main session) from sub-agent's inline return content
> per AMAW audit trail requirement.

---

## Finding 1: WARN — §4 P1 1B paired-state probes (probes 2-4) require setting the lock into states the production code path cannot reach without intervention; no test-mode lock-writer is specified in deliverables, leaving probes unimplementable as written

**Where:** `CYCLE_0_PLAN.md` §4 P1 "1B — Refusal at boundary states (NEW R3)" — 5 probes listed. Probe 1 (lock=UNLOCKED + no signal) is trivially reachable (clean state). Probes 2-4 require pre-states that the production code path explicitly forbids creating:
- Probe 2: `lock=READY_FOR_2 + signal exists` — would require auto-dispatcher.py to have been run for cycle 2, but smoke is dispatching cycle 1.
- Probe 3: `lock=READY_FOR_1 + signal absent` — would require auto-dispatcher.py to crash between its two writes (the very crash row 4 of the recovery table describes).
- Probe 4: `lock=READY_FOR_1 + signal.next_cycle=2` (corrupted) — would require malformed signal generation that the dispatcher itself never produces.

**Why R3's BLOCK 2 fix is downstream-incomplete:** The lock state machine + refusal rule R3 (orchestrator.accept_raid_invocation) is well-specified, and the crash-recovery table correctly enumerates 8 observed states. But to TEST the refusal rule at smoke time, the smoke harness must FORCE the lock + signal file into each of probes 2-4's states. The plan never specifies a test-mode flag, a test-only force-lock-state helper, or explicit direct file manipulation in run-smoke-test.sh. Without an explicit mechanism, BUILD will either (a) implement direct file writes ad-hoc without contract; (b) ship probes as no-ops with "lock state forced for test" comment (silent suppression — lesson 5 recurrence); or (c) downgrade to comment-asserted passes at smoke time (R2 BLOCK 2 recurrence one layer up).

**Recommended fix (track in §9 residual risk; address in B1 build):**
1. Add `scripts/raid/test/force-lock-state.sh <state> [signal-yaml-path]` test-only helper — writes lock+signal to exact state, prints WARNING line, audit-logs `event=test_lock_forced`.
2. Update §4 P1 1B preamble: "Probes 2-4 use `test/force-lock-state.sh` to pre-position lock+signal; probe 5 uses the normal dispatcher flow."
3. orchestrator.py rejection logic MUST NOT special-case test-mode — refusal is production logic; only SETUP is test-only.

**Severity:** WARN — design correct; gap is build-phase testability mechanism. Tracker: `D-CYCLE-0-LOCK-PROBE-SETUP`.

---

## Finding 2: WARN — Drift-detection header text propagated to CYCLE_DECOMPOSITION but enforcement logic NOT propagated to brief-generator.py / startup-verifier.sh deliverable descriptions; declarative without enforcer = TODO masquerading as a fix

**Where:** `CYCLE_DECOMPOSITION.md` line 28-29 promises: "brief-generator.py + startup-verifier.sh assert this header matches RAID_WORKFLOW.md frontmatter; mismatch → halt + ESCALATIONS row." But:
- `CYCLE_0_PLAN.md` §3 B1 startup-verifier.sh description: "P2 5-step routine" — no header check.
- `CYCLE_0_PLAN.md` §3 B5 brief-generator.py description: "parses CYCLE_DECOMPOSITION §2 + cites layer plans + extracts LOCKED Q-IDs" — no header check.
- §4 has no smoke assertion that detects a header mismatch (e.g., bump RAID_WORKFLOW to fake v1.5, expect halt).

**Why R3's WARN 3 fix is downstream-incomplete:** R3 addressed the OBSERVATION (header missing) by adding text, but not the MECHANISM that makes the header load-bearing. At BUILD time an implementer reads CYCLE_0_PLAN §3 B1/B5 and ships without the check. Drift returns silently the next RAID_WORKFLOW amendment. Same paper-thin pattern as R2 BLOCK 1 P5 fix at smaller scope — assertion in spec but not executor. Compounding: brief-generator is the source of all 37 auto-generated briefs; silent ignore means every brief sails through against stale CYCLE_DECOMPOSITION; smoke P6 only checks structure not version sync; drift invisible until C1+.

**Recommended fix (track in §9 residual risk; address in B1 + B5 build):**
1. Update §3 B1 startup-verifier.sh: "P2 5-step routine + Step 6: drift check — parses `last_synced_with_RAID_WORKFLOW_version` from CYCLE_DECOMPOSITION + RAID_WORKFLOW frontmatter; mismatch → exit non-zero + ESCALATIONS row `type=spec_drift`."
2. Update §3 B5 brief-generator.py: "Refuses to run if CYCLE_DECOMPOSITION header version != RAID_WORKFLOW frontmatter version."
3. Add §4 smoke assertion: temporarily bump CYCLE_DECOMPOSITION header to fake v1.5, assert startup-verifier exits non-zero with `type=spec_drift`, restore, re-run, assert exit 0.

**Severity:** WARN — orthogonal to keystone gates; same anti-pattern as R2 BLOCK 1 one layer up. Tracker: `D-CYCLE-0-DRIFT-ENFORCER`.

---

## Finding 3: WARN — recover-from-crash.sh claims it "refuses while a /raid session is active (checks pid file)" but no orchestrator-session pid file mechanism is specified anywhere in the design

**Where:** `CYCLE_0_PLAN.md` §3 B1 `scripts/raid/recover-from-crash.sh` description (added R3): "Refuses to run while a `/raid <N>` session is active (checks pid file)."

**What is unspecified:**
- The `dispatcher_pid` in signal YAML (§3 B6 step 4) is auto-dispatcher.py's PID, not an active orchestrator.py /raid session's PID. After dispatcher exits, dispatcher_pid is stale.
- No orchestrator.py-writes-its-pid-on-entry contract appears in §3 B1 orchestrator.py description.
- No standard pid file path (e.g., `docs/raid/.raid-session.pid`) is defined.
- Crash-recovery table row 7 ("lock=<N> + cycle commit absent → /raid <N> again triggers P5 recovery-protocol-runner") implies orchestrator knows from lock alone — but recover-from-crash.sh refusal requires distinguishing "stale lock=<N>" from "active /raid <N> in another terminal" which a lock value alone cannot do.

**Why this matters:** R3 correctly introduced recover-from-crash.sh to close the crash-recovery hole. But the refusal contract was written without specifying how the script DETECTS an active session. Without the pid file mechanism: operator running `--reset-lock` during an active /raid <N> in a parallel terminal corrupts that session mid-execution (the very thing the refusal check exists to prevent). Implementation will either (a) skip refusal entirely (silent suppression); (b) use a fragile pgrep heuristic; or (c) require manual confirmation breaking automation.

**Recommended fix (track in §9 residual risk; address in B1 build):**
1. Add to §3 B1 orchestrator.py description: "On entry (after lock-acquisition transition `READY_FOR_<N> → <N>`), writes own PID to `docs/raid/.raid-session.pid` (atomic tempfile+rename). On commit completion (lock-reset transition), deletes pid file."
2. Update §3 B1 recover-from-crash.sh: "Refusal check reads `docs/raid/.raid-session.pid` if exists; if PID alive (`kill -0 PID` == 0), REFUSE with `error: /raid session PID <pid> active in another terminal`. If PID file exists but process dead → stale; audit-log `event=stale_pid_cleaned` and proceed."
3. Add crash-recovery table row 9: `pid file exists + process alive | session running normally | recover-from-crash.sh refuses operator command`. Row 10: `pid file exists + process dead | crashed mid-cycle | recover-from-crash.sh cleans stale pid + proceeds as row 7`.
4. Optional smoke probe 6 in §4 P1 1B: operator `recover-from-crash.sh --reset-lock` invoked while smoke's simulated session is "active" → assert REFUSE.

**Severity:** WARN — refusal claim exists in spec; mechanism does not. Same anti-pattern as Finding 2 at the operator-toolkit layer. Tracker: `D-CYCLE-0-PID-FILE-CONTRACT`.

---

Captured rules: read pre-loaded (5 lessons + 1 guardrail check pass).

**Summary verdict rationale:** R3 substantively addressed R2 BLOCK 1 (P5 executor real, both 5A/5B branches truly run with concrete assertions, stealth-defer gone); R3 substantively addressed R2 BLOCK 2 design (atomic transition, refusal rule codified, 8-state crash table, paired-state probes specified); R3 substantively addressed R2 WARN 3 surface (header, COST_LOG SUPERSEDED, Phase 9 disambiguation). The 3 remaining issues are all **downstream-incomplete propagations** — design contracts right but build-phase deliverable descriptions don't include implementation hooks that make those contracts load-bearing. None are design contradictions; none re-open R2 BLOCK 2 paired-state suppression; all three are tractable as BUILD-phase tickets without redesign. Per AMAW XL calibration: 3 design rounds exhausted; APPROVED_WITH_WARNINGS = pragmatic stop. BUILD may begin; issues tracked in §9 residual-risk register.
