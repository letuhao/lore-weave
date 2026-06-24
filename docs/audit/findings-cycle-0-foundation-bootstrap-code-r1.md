# Adversary findings -- cycle-0-foundation-bootstrap -- review-code round 1

**Verdict:** REJECTED → fixed → 40/40 smoke green
**Reviewer:** Adversary cold-start (general-purpose sub-agent)
**Reviewed:** C0 BUILD implementation post-39/39 smoke green; all 3 findings addressed in fix commit

> **Note:** Adversary sub-agent's Write tool was blocked by harness policy. This file
> persisted by parent (Raid Leader main session) from sub-agent's inline return content.

---

## Finding 1: BLOCK — C0 → C1 handoff destroyed by smoke cleanup

**File:** `scripts/raid/run-smoke-test.sh` lines 384-387 (pre-fix)
**Contract violated:** `CYCLE_0_PLAN.md` §3 B6 lock state machine

The smoke harness called `auto-dispatcher.py` (correct), then in the PASS branch did:
```bash
write_lock_raw "UNLOCKED"
rm -f "$RAID_DIR/READY_FOR_CYCLE_1.signal"
```

This **deleted the very handoff state the AUTO gate just produced**. After smoke
exit 0, system was in `lock=UNLOCKED + no signal` — which `accept_raid_invocation`
REFUSES with `error: lock=UNLOCKED expected READY_FOR_1`. The Semi-AUTO mechanism
was structurally broken.

**Fix applied (in run-smoke-test.sh):**
- Removed the lock/signal cleanup from PASS branch
- Kept only smoke-fixture teardown (`_smoke` dir)
- Added HANDOFF assertion: `lock=READY_FOR_1 + signal present` → PASS
- Smoke now reports 40 checks (was 39); HANDOFF is check #40

**Severity was:** BLOCK. After fix: handoff intact, smoke 40/40 PASS.

---

## Finding 2: BLOCK — P1-1B refusal probes accept ANY non-zero exit (false-green pattern)

**File:** `scripts/raid/run-smoke-test.sh` probes 1-4 (pre-fix)

Each probe did:
```bash
python3 .../orchestrator.py raid 1 >/dev/null 2>&1
if [ $? -ne 0 ]; then pass; else fail; fi
```

This treated argparse failure, ImportError, env break, OR any future regression as
"correctly refused". A regression where orchestrator wrongly accepted UNLOCKED+no-signal
but then subprocess failed would: (a) MUTATE lock to "001" (cycle in progress) before
the failing subprocess, then (b) exit non-zero, → probe says PASS while lock state was
corrupted.

**Fix applied (in run-smoke-test.sh):**
- Introduced `probe_refuse()` helper that captures stderr + asserts specific REFUSED
  substring in error message + asserts lock value UNCHANGED post-probe
- 4 probes refactored to use the helper with specific expected substrings:
  - Probe 1: "expected READY_FOR_1"
  - Probe 2: "lock=READY_FOR_2 expected READY_FOR_1"
  - Probe 3: "signal file missing"
  - Probe 4: "next_cycle=2 expected 1"

**Severity was:** BLOCK. After fix: probes assert reason + atomicity; all 4 PASS.

---

## Finding 3: WARN — auto-dispatcher.py "atomic transition" was actually 2 sequential writes; crash window produced out-of-table state

**File:** `scripts/raid/auto-dispatcher.py` `atomic_transition_to_ready` (pre-fix)

Pre-fix order:
```python
sig = emit_signal(cycle)       # signal first
write_lock_atomic(target)      # then lock
```

Crash window: kill between these two writes → `lock=00X + signal exists` —
CYCLE_0_PLAN.md §3 B6 crash-recovery table row 3 marks this state "impossible if
dispatcher is atomic". Plan and code disagreed; operator would have no recovery path.

**Fix applied:**
- Swapped order: write LOCK first, then signal
- Crash window now produces `lock=READY_FOR_<N> + signal missing` which IS in the
  table (row 4 → `recover-from-crash.sh --rewrite-signal <N>`)
- Added comment explaining the ordering rationale

**Severity was:** WARN. After fix: in-table crash state.

---

## Disposition

All 3 fixes applied + smoke re-run: 40/40 PASS (was 39 pre-fix; HANDOFF check added
as part of BLOCK 1 fix). Handoff state verified intact: `lock=READY_FOR_1 + signal
file present with valid YAML next_cycle=1 + smoke_evidence_sha=78f9290e`.

R2 code-review round to verify fixes (AMAW XL allows 2 code rounds).
