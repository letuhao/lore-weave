# Adversary Review r1 — amaw-precommit-no-side-effect

**Verdict: APPROVED_WITH_WARNINGS** — 3 WARN, 0 BLOCK. The guard fixes DEFERRED #004 as specified; three follow-up concerns worth fixing, none blocking.

## Finding 1 — WARN: does the early-exit also cover a *corrupt* state file, or only an *absent* one?

`cmd_amaw_pre_commit` line 417 guards `not STATE_FILE.exists()`. But `load_state()` (line 152-155) ends with `json.loads(STATE_FILE.read_text(...))` — no try/except. If `.workflow-state.json` exists but is **empty or malformed** (truncated write that escaped the atomic-rename guarantee, manual edit, merge-conflict markers), line 419 `state = load_state()` raises `json.JSONDecodeError` and the hook dies with a traceback. Because the chain is `pre-commit && amaw-pre-commit`, a non-zero exit from the traceback **blocks the commit** with an opaque Python stack — strictly worse UX than the stale-file bug #004 set out to fix. The DEFERRED #004 spec scopes only "absent", so this is not a regression of the fix — but it is an adjacent failure mode the fix walks right past. Should `load_state()` (or this call site) treat an unparseable file as "no usable state → exit 0", consistent with the fix's own fail-open intent? (file: `scripts/workflow-gate.py:155`, `:417-419`)

## Finding 2 — WARN: silent exit vs. `cmd_pre_commit`'s announced WARNING — is the asymmetry intentional?

The comment claims the guard "Mirrors cmd_pre_commit's own no-state early-exit." It does not mirror it. `cmd_pre_commit` line 556-558 prints `"WARNING: No workflow state found. Proceeding without enforcement."` before `sys.exit(0)`. The new guard at line 417-418 exits **0 silently**. For an AMAW-enabled task, a missing state file mid-task is a real signal (state lost / wrong cwd / worktree mismatch) — and AMAW mode is exactly when guardrail checking matters most. Silent exit means an agent that *should* be gated sails through with zero output. At minimum the guard should print a one-line note to stderr so the absence is observable. Is silent-exit a deliberate choice, or an oversight that the "mirrors" comment masks? (file: `scripts/workflow-gate.py:417-418` vs `:556-558`)

## Finding 3 — WARN: TOCTOU window between `STATE_FILE.exists()` and `load_state()`'s second `exists()` check

Line 417 checks `STATE_FILE.exists()`; line 419 → `load_state()` re-checks `exists()` at line 153. Between the two, a concurrent `workflow-gate.py size`/`phase` invocation (or `reset`) could create or delete the file. Concretely: file absent at 417 → guard does NOT fire only if file appears... actually the inverse — file present at 417, deleted by a concurrent `reset` before 419 → `load_state()` re-creates it from INITIAL_STATE, reintroducing the exact stale-file side effect #004 targets. The window is tiny and the scenario (concurrent reset during a commit hook) is unlikely for a local dev tool, so this is a nitpick — but the fix's correctness rests on an assumption of single-threaded invocation that is nowhere stated. Worth a one-line comment acknowledging the fix is not concurrency-safe, mirroring how `save_state` explicitly documents its crash-safety scope. (file: `scripts/workflow-gate.py:417` / `:153`)

## Hook-chain semantics check
`.claude/settings.json:18` — `pre-commit && amaw-pre-commit`. `cmd_pre_commit` exits 0 when no state (line 558), so `&&` **does** proceed to `amaw-pre-commit` on a no-state commit. This is precisely the path #004 describes; the guard is correctly placed to intercept it. No issue with the `&&` itself.

## Bundle mirror
`agentic-workflow/scripts/workflow-gate.py` is byte-identical to `scripts/workflow-gate.py` (`diff` clean). OK.

---
**Lessons consulted:** b2d376de (Confirm before git push), c0aef658 (DB migration L+), b21930d8 (Force-push auth), e52f469a (Adversary REJECTED: amaw-task-slug-validation), f333a0e5 (Adversary REJECTED: rdy-rejected-test).
**Step 0 queries:** "workflow-gate pre-commit hook state file" (--type guardrail); "cmd_amaw_pre_commit load_state" (--tags adversary-rejection).
**Guardrails relevant:** none of the 3 returned guardrails (git push / migration / force-push) constrain this change.
**Prior REJECTED patterns:** e52f469a (amaw-task-slug-validation) — adversary r1 rejected on unnamed-task / state-edge handling; the corrupt-state gap in Finding 1 is the same family of edge-case-omission and is the reason this is APPROVED_WITH_WARNINGS rather than clean APPROVED.
