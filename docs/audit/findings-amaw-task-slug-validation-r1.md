# Adversary Review — amaw-task-slug-validation (round 1)

Verdict: **REJECTED** (1 BLOCK, 2 WARN)

DEFERRED #001 fix: `_normalize_slug()` slugifies the task slug in `cmd_amaw_enable`.
Reviewed `scripts/workflow-gate.py` (+ byte-identical bundle mirror, sha256 confirmed).

## Finding 1 — BLOCK

`cmd_pragmatic_stop` (lines 415-441) takes `task_slug = args[0]` straight from
the CLI and feeds it unnormalized into `tags=["amaw", "pragmatic-stop", task_slug]`
at line 439 — and into `_log_audit` at line 432. The fix's own docstring (lines
315-319) says normalization is "the single chokepoint that keeps every downstream
consumer safe", yet `pragmatic-stop` is a second, independent path that writes the
slug into a comma-joined tag list via `_bridge_to_contexthub`. **Should `_normalize_slug`
not also be applied to `cmd_pragmatic_stop`'s `args[0]`?** DEFERRED #001 says "comma
in slug splits into multiple tags downstream" — that defect is still fully live on
the `pragmatic-stop` path. The fix as scoped does not actually close the deferral;
it closes one of two entry points. This is a missing-requirement gap, not a nitpick.

## Finding 2 — WARN

`cmd_complete` (lines 275-307) bridges with `tags=["amaw", "sprint", task_slug]`
(line 299) and `["amaw", "adversary-rejection", task_slug]` (line 306), reading
`task_slug` from `state["task"]`. That state value can be written by paths *other*
than `cmd_amaw_enable` — e.g. a future verb, a hand-edited `.workflow-state.json`,
or a slug seeded before AMAW was enabled (the `if args:` branch at line 334 only
runs when a slug arg is supplied; enabling AMAW with no arg leaves whatever `task`
was already in state untouched and unnormalized). **Should the read side in
`cmd_complete` defensively re-normalize `state["task"]` before tagging, rather than
trusting that every writer normalized?** Normalization is idempotent
(`_normalize_slug(_normalize_slug(x)) == _normalize_slug(x)`), so a read-side call
is cheap insurance and removes the "every writer must remember" coupling.

## Finding 3 — WARN

The `"unnamed-task"` fallback (line 322) can **collide with a real task**: a user
who runs `amaw-enable "Unnamed Task"` or `amaw-enable "---"` produces the literal
slug `unnamed-task`, indistinguishable in `AUDIT_LOG.jsonl` and ContextHub tags
from the empty-input fallback. Worse, it diverges from the *other* unnamed sentinel
in the same file — `cmd_complete` line 276 and `cmd_amaw_enable` line 340 use
`"(unnamed)"` (parens) when `task` is falsy. So an empty slug becomes `unnamed-task`
when set via the arg path but `(unnamed)` when never set — two different sentinels
for the same concept. **Should the fallback be a non-slug-collidable sentinel
(e.g. keep `state["task"]` empty and let the existing `"(unnamed)"` display logic
handle it) so audit entries can be told apart and the two code paths agree?**

## Notes on what was checked and cleared

- Regex `[^a-z0-9]+` on already-lowercased input: correct, greedy run-collapse,
  no catastrophic backtracking. Unicode (`café`, full-width digits) → stripped to
  ASCII-safe; acceptable, not flagged.
- Leading-digit / all-dash / very-long input: handled by `strip("-")` + fallback;
  no crash. Not flagged.
- Idempotency: holds. Not flagged.

Lessons consulted: 4
Step 0 query strings used: "workflow-gate task slug normalization" (type=guardrail); "cmd_amaw_enable slug" (tags=adversary-rejection)
Guardrails relevant: (none — only generic git-push / migration guardrails returned, none about slug/tag handling)
Prior REJECTED patterns: rdy-rejected-test review-design (contract holes, 2 BLOCK) — unrelated domain; no slug-specific precedent
