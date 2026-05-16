# Adversary Findings — amaw-atomic-save-state (round 1)

Reviewed change: `save_state()` in `workflow-gate.py` now writes a fixed-name
`.tmp` file then `Path.replace()`s it over `STATE_FILE`. Verdict:
**APPROVED_WITH_WARNINGS** — 3 WARN, 0 BLOCK.

## Finding 1 — WARN — Fixed `.tmp` name is not collision-safe under concurrency
`scripts/workflow-gate.py:122` — `tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")`
produces a single hard-coded path `.workflow-state.json.tmp` with no PID or
random suffix. The atomic-write idiom you cited (write-tmp-then-rename) only
guarantees atomicity for *one* writer; with a shared fixed name, two concurrent
`workflow-gate.py` processes both write the *same* `.tmp` and both `replace()`
it. The pre-commit hook path (`cmd_pre_commit`) and a developer running
`status`/`complete` in another shell can overlap. Question for the author: what
prevents two invocations from interleaving `tmp.write_text` (process A writes
half, process B truncates and writes its own, process A's `replace` then
publishes B's partial bytes)? The DESIGN audit entry claims "leftover .tmp
harmless (next write overwrites)" — but that reasoning assumes a single writer.
Why is single-writer a safe assumption for a state file the commit hook touches?

## Finding 2 — WARN — `cwd`-relative tmp path undermines the same-filesystem claim
`scripts/workflow-gate.py:26` — `STATE_FILE = Path(".workflow-state.json")` is
**cwd-relative**, so `with_name(...)` at line 122 yields a cwd-relative `.tmp`.
The inline comment (lines 120-121) asserts "Same-directory tmp guarantees
same-filesystem". That is only true if `STATE_FILE` and the tmp resolve to the
same *real* directory at call time. They do here only because both are relative
and resolved against the same cwd in the same call — but the comment frames it
as a structural guarantee. Contrast `MCP_QUERY` at line 32, which was
*deliberately* anchored to `__file__` precisely because "commit hooks may invoke
from worktrees, CI runners" with varying cwd. Question: if a future caller (or a
hook) `chdir`s between `load_state()` and `save_state()`, or runs from a
worktree where `.workflow-state.json` was created elsewhere, does the "atomic"
property still hold — or does `replace()` silently target a *different*
directory's file / raise `EXDEV`?

## Finding 3 — WARN — Killed process leaks `.tmp`; no fsync, no cleanup, no `.gitignore`
A crash/kill between `tmp.write_text` (line 123) and `tmp.replace` (line 124)
leaves `.workflow-state.json.tmp` on disk indefinitely. Nothing in the module
ever unlinks a stale tmp — `cmd_reset` (line 506-508) only `unlink()`s
`STATE_FILE`, not the tmp. Question for the author: (a) Is `.workflow-state.json.tmp`
in `.gitignore`? `.workflow-state.json` presumably is; a new sibling artifact
that the pre-commit hook itself can create is a candidate for accidental
commit. (b) `write_text` does not `fsync` the tmp nor the parent directory
before `replace`; on a power-loss (not just a process crash) the rename can be
durable while the tmp's *contents* are not yet flushed — the comment's "complete
new state, never partial" guarantee is weaker than stated. Is power-loss
durability in scope, or only process-level crash safety? If only the latter, the
comment should not claim more than it delivers.

Lessons consulted: 4
Step 0 query strings used: "atomic file write workflow state persistence" (type=guardrail); "workflow-gate save_state" (tags=adversary-rejection)
Guardrails relevant: (none — returned guardrails cover DB migration and git push, unrelated to file-write atomicity)
Prior REJECTED patterns: (none — only match was test fixture "rdy-rejected-test", not a comparable pattern)
