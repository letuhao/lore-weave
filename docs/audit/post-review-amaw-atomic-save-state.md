# Post-Review (Scope Guard) — amaw-atomic-save-state

**Verdict: CLEAR**
Date: 2026-05-15T17:31:18 · Agent: scope-guard (AMAW cold-start) · Phase: post-review
Task: DEFERRED #003 — make `save_state()` atomic (write-tmp-then-rename).
Classified S, reclassified M mid-build.

## Step 0 — Captured-rules check

- `check_guardrails "ready-to-commit"` → `{"pass": true, "rules_checked": 3}` — no block.
- `search_lessons "atomic file write workflow state" --type guardrail` → 3 matches, all
  unrelated (DB migration, git push, force-push). None gate file-write atomicity.
- Both `scripts/mcp-query.py` calls succeeded (tooling reliable for this run).

No captured rule blocks the commit.

## Checklist

### 1. Adversary's 3 findings — all resolved

**Finding 1 (PID-unique tmp) — RESOLVED.**
`workflow-gate.py:135` — `tmp = STATE_FILE.with_name(f"{STATE_FILE.name}.{os.getpid()}.tmp")`.
The `.{pid}.` infix gives each process a distinct tmp path, so two concurrent
`workflow-gate.py` invocations cannot interleave bytes into a shared `.tmp`.
Comment lines 127-129 document the rationale. `import os` present at line 21.

**Finding 2 (comment accuracy re same-dir guarantee) — RESOLVED.**
Comment lines 123-125 now state the guarantee structurally: "The tmp is derived
from STATE_FILE via with_name(), so the two always share a parent directory —
hence the same filesystem." `with_name()` only swaps the final path component,
so tmp and STATE_FILE provably share a parent regardless of cwd. The old
cwd-coincidence framing the Adversary objected to is gone.

**Finding 3 (stale-tmp cleanup + .gitignore + power-loss honesty) — RESOLVED.**
- Cleanup: `finally` block lines 139-143 unlinks the process's own tmp if
  `replace()` never ran. `cmd_reset` lines 528-534 sweeps stale
  `.workflow-state.json.*.tmp` via glob (orphans from killed processes).
- `.gitignore` line 237 — `.workflow-state.json.*.tmp`.
- Power-loss honesty: comment lines 131-134 explicitly scope OUT power-loss
  durability (no fsync) and state process-crash safety is the design target —
  no longer over-claiming.

### 2. Acceptance — crash-safety achieved

`save_state` (lines 116-143): serializes to a same-dir PID-unique tmp via
`tmp.write_text`, then `tmp.replace(STATE_FILE)` — an atomic rename
(os.replace/MoveFileEx). A process crash between write and replace leaves
STATE_FILE holding the complete prior state; only the tmp can be partial.
`finally` block cleans a leftover tmp on failed write or Windows-locked-dest
PermissionError. Same-dir tmp satisfies the same-filesystem precondition
(no EXDEV). Verified by AUDIT_LOG verify entries (V1-V4, two rounds).
All 4 DEFERRED #003 acceptance facets covered: atomic rename, same-dir tmp,
old-state-preserved-on-crash, no leftover tmp.

### 3. Bundle mirror — byte-identical

`diff` reports no difference. `sha256sum` both copies =
`b45f16325e9ce616cc67dd534c9168243633bf624c62f0f8dd1827ec28ce51c5`.

### 4. .gitignore + install.sh — both cover tmp pattern

- `.gitignore:237` — `.workflow-state.json.*.tmp`.
- `install.sh:111` (append branch) and `install.sh:121` (create branch) both
  emit `.workflow-state.json.*.tmp`; line 115 message mentions "(+ .tmp)".

### 5. New problems introduced by the fixes — none

- `os.getpid()` — stdlib, deterministic, no failure mode.
- `cmd_reset` glob `f"{STATE_FILE.name}.*.tmp"` — narrowly scoped to the tmp
  naming pattern; will not match `.workflow-state.json` itself (requires a
  middle segment + `.tmp` suffix). `parent` falls back to `Path(".")` when
  `STATE_FILE.parent` is empty — correct for the cwd-relative default.
- `finally` unlink uses `missing_ok=True` — safe if `replace()` already
  consumed the tmp. Only ever unlinks this process's own PID-named tmp,
  never another live process's.

## Summary

All 5 checklist items pass. 3/3 Adversary findings resolved. 4/4 acceptance
criteria covered, 0 uncovered. No spec drift. No new defects. check_guardrails
clean. **CLEAR for SESSION + COMMIT.**
