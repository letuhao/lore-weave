# Scope Guard Post-Review — amaw-precommit-no-side-effect

**Verdict: CLEAR** — DEFERRED #004 fully closed. Conservative final gate passes.

## Step 0 — Captured-rules check
- `check_guardrails "ready-to-commit"` → `pass: true`, 3 rules checked, no matched_rules. PASS.
- `search_lessons "pre-commit hook state file" --type guardrail` → 3 guardrails (git push confirm, force-push auth, DB-migration L+). None constrain this change. PASS.
- Both calls succeeded.

## Checklist

1. **DEFERRED #004 acceptance — COVERED.** `cmd_amaw_pre_commit` (workflow-gate.py:426) now has `if not STATE_FILE.exists(): sys.exit(0)` placed BEFORE `state = load_state()` at l.428. Since `load_state()` (l.152-155) auto-creates `.workflow-state.json` from `INITIAL_STATE` when absent, the early-exit guarantees an agent committing outside any tracked task never reaches `load_state()` and never leaves a stale state file. Exactly the #004 spec ("also early-exit if STATE_FILE absent before load_state()").

2. **Adversary r1 WARNs — dispositioned correctly.**
   - WARN-1 (corrupt/empty state file → `json.loads` traceback in `load_state` l.155, no try/except): filed as DEFERRED #008 (entry present, "Next ID: 009"). Severity LOW, target L4 hardening. Honestly scoped — affects all `load_state` callers.
   - WARN-2 (comment overclaimed "mirrors cmd_pre_commit" — cmd_pre_commit l.566 prints a visible WARNING, this guard exits silently): comment rewritten (l.418-421) to drop the "mirrors" claim and document the silent-exit rationale — cmd_pre_commit runs first in the `&&` chain and already surfaces the warning, so a second is noise.
   - WARN-3 (TOCTOU window between `exists()` at l.426 and `load_state()`'s re-check at l.153): comment l.423-425 explicitly states the single-threaded assumption and scopes a concurrent-`reset` race out for a local single-user dev tool.

3. **Bundle mirror byte-identical — YES.** `diff scripts/workflow-gate.py agentic-workflow/scripts/workflow-gate.py` → clean (BYTE-IDENTICAL-OK). `git diff` shows the identical 16-line addition (index d014a4f7→46519bcd) in both copies.

4. **Independent ruling on WARN-1 deferral — LEGITIMATE.** DEFERRED #004's spec is narrowly "absent state file → don't auto-create". A corrupt/empty-but-present file is a distinct failure mode: it is not the side-effect #004 names, the fix does not introduce or worsen it, and corruption handling belongs in `load_state` itself (or every call site) — not in this one guard. The pre-existing `json.loads` had no try/except before this change, so #004 is not leaving its own work half-done; it is leaving a pre-existing adjacent gap untouched, which is the correct scope discipline. DEFERRED #003's atomic `save_state` already removes the crash-mid-write path; only manual-edit / disk-corruption remain, which #008 captures. Not a cop-out.

5. **No new problem from the fix — CONFIRMED.** The guard fires ONLY when `STATE_FILE` does not exist = no task in flight = nothing to gate. When a real AMAW task is in flight, `.workflow-state.json` legitimately exists (written by `cmd_amaw_enable`/`cmd_phase` via `save_state`), so the guard does NOT fire and execution proceeds to `load_state()` → `amaw_enabled` check → `check_guardrails`. The guard cannot skip gating for a real in-flight task. Fail-open behaviour is correct and matches `cmd_pre_commit`'s own no-state exit-0 policy. VERIFY evidence (audit l.41) independently confirms: no-state → exit 0 + no file created; with-state + amaw_enabled → check_guardrails still runs (CLEAR, 3 rules).

## Artifacts
- `docs/audit/AUDIT_LOG.jsonl` — qc event appended
- `docs/audit/post-review-amaw-precommit-no-side-effect.md` — this file
