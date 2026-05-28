# Cycle 00X: Hello-World Smoke Test (Cycle 0 AUTO gate exercise)

> Hand-written canonical brief for the C0 smoke test. Exercises all 24 P+B+Q
> checks + 5 lock-state probes + P5 dual-scenario per CYCLE_0_PLAN.md §4.
> NOT auto-generated; serves as known-good reference for brief-generator.

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** No-op cycle that creates `docs/raid/_smoke/HELLO_FROM_<TS>.md` and validates the orchestrator end-to-end.
- **Acceptance gate:** `scripts/raid/run-smoke-test.sh` exits 0 + AUDIT_LOG shows `event=smoke_complete result=PASS check_count=24`.
- **Top 3 LOCKED decisions consumed:** PRE_FLIGHT-D6 (Semi-AUTO), Q-RAID-v1.4-P5-DUAL, Q-RAID-v1.4-LOCK-FSM
- **DPS count:** 1 (sentinel)
- **Estimated wall time:** ~10 minutes

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: none (smoke is itself the C0 acceptance gate)
- Files expected to exist: all 46 C0 deliverables per CYCLE_0_PLAN.md §2

## Scope (IN)
- Exercise all 10 P-protections (P1-P10) per CYCLE_0_PLAN §4
- Exercise all 6 B-protections (B1-B6)
- Exercise all 8 Q-protections (Q1-Q9 minus Q9 dual-use bundle)
- Lock state machine 5 paired-state probes (P1 1B)
- P5 dual-scenario (5A CONSISTENT + 5B INCONSISTENT-HALT)
- Brief structure validation across this brief + 37 generated briefs

## Scope (OUT — explicitly)
- Real cycle work (this is no-op; only orchestrator infrastructure validation)
- Anything in `infra/existing-prod/`
- Any actual sub-agent spawn that costs Anthropic quota beyond probes

## Acceptance criteria (CI gates — exit code 0 = pass)
- All 24 checks emit `[PASS] <check-name>` to stdout
- Final line: `[PASS] all 24 smoke checks (P:10 B:6 Q:8)`
- AUDIT_LOG row: `event=smoke_complete result=PASS check_count=24`
- `quota-summary.py` reports smoke burn < 100K tokens equivalent

## DPS parallelism plan
- DPS 1 (sentinel): creates `docs/raid/_smoke/HELLO_FROM_<TS>.md` with content "RAID smoke test"
- No real parallel work; smoke uses cycle=999 sentinel for B2 port allocation
- Return budget: 1500 tokens summary (verifies P4)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- Did all 24 checks ACTUALLY run (not skipped via env var)?
- Did P5 5B INCONSISTENT branch fire (HALT exit + ESCALATIONS row + recovery_halted audit)?
- Did lock-state probes 2-4 use `test/force-lock-state.sh` to pre-position state?
- Q2 model tiering: are the 3 dry-run probes (DPS=sonnet, scope_guard=haiku, raid_leader=opus) the actual models the production path would use?

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- 24 PASS markers in stdout
- No FAIL markers
- AUDIT_LOG has all expected event rows
- ESCALATIONS.md has the P5 5B inconsistent row (REQUIRED — proves HALT branch tested)
- `.session-cycle-lock` returned to UNLOCKED after smoke

## Cross-references (for deep-read IF Raid Leader needs FOCUS mode)
- Plan: [CYCLE_0_PLAN.md](../../plans/2026-05-29-foundation-mega-task/CYCLE_0_PLAN.md) §4
- Workflow spec: [RAID_WORKFLOW.md](../RAID_WORKFLOW.md) §13.7 v1.4
- Adversary findings: [findings-cycle-0-foundation-bootstrap-r{1,2,3}.md](../../audit/)
- LOCKED: D6 (PRE_FLIGHT_CHECKLIST §10 NOTES)

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **PRE_FLIGHT-D6:** auto-dispatch is Semi-AUTO; user opens fresh session for /raid 1
- 🔴 **P5 dual-scenario:** 5B INCONSISTENT MUST fire HALT path — verify ESCALATIONS row appended
- 🔴 **Lock probes 1B:** probes 2-4 use `test/force-lock-state.sh` (R3 D-CYCLE-0-LOCK-PROBE-SETUP)
- 🔴 **Drift enforcer (R3 D-CYCLE-0-DRIFT-ENFORCER):** startup-verifier Step 6 + brief-generator both refuse on header mismatch
- 🔴 **PID file contract (R3 D-CYCLE-0-PID-FILE-CONTRACT):** orchestrator writes/deletes `.raid-session.pid`
- 🔴 **Fresh session reminder:** C0 itself uses default+AMAW workflow; /raid 1 must be invoked from a FRESH Claude Code session per P1.
