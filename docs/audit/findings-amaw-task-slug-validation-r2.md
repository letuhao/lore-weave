# Adversary Review — amaw-task-slug-validation (round 2)

Verdict: **APPROVED_WITH_WARNINGS** (0 BLOCK, 3 WARN)
Round-1 findings resolved: 3/3

Reviewed `scripts/workflow-gate.py` (+ bundle mirror — `diff` confirms byte-identical).

## Round-1 verification

- **R1 BLOCK (cmd_pragmatic_stop)** — RESOLVED. Line 437:
  `task_slug, reason = _normalize_slug(args[0]), args[1]`. The slug is normalized
  before reaching `_log_audit` (l.447) and `tags=["amaw","pragmatic-stop",task_slug]` (l.457).
- **R1 WARN-2 (cmd_complete read side)** — RESOLVED. Lines 280-281:
  `raw_task = state.get("task"); task_slug = _normalize_slug(raw_task) if raw_task else "unnamed-task"`.
  Read-side defensive re-normalize before the two `_bridge_to_contexthub` tag lists.
- **R1 WARN-3 (unnamed-task collision / sentinel disagreement)** — ADDRESSED by
  documentation. Docstring l.328-333 codifies the two-layer split: `unnamed-task`
  = value layer (tag-safe), `(unnamed)` = display layer (parens make it a
  non-collidable non-slug). The literal collision still exists but is now a
  conscious, documented design choice — acceptable to close the WARN.

## Current findings (round 2)

### Finding 1 — WARN
`cmd_amaw_enable` normalizes only on the `if args:` write path (l.348-352). The
"already enabled" early-return at l.342-344 and the no-arg case still surface
`state.get("task")` raw. If a prior writer or hand-edited `.workflow-state.json`
seeded an un-normalized `task`, `cmd_amaw_enable` will *print* it raw — and more
importantly never rewrite it. Only `cmd_complete` re-normalizes. **Should
`cmd_amaw_enable` re-normalize `state["task"]` in-place (even with no arg) so the
stored value is canonical, rather than relying on every reader to defensively
fix it?** Right now the state file can permanently hold a dirty slug.

### Finding 2 — WARN
`_normalize_slug` is typed `raw: str` and calls `raw.lower()` (l.335) with no
guard. `cmd_complete` protects it with `if raw_task else` (l.281), but a
hand-edited state file with `"task": 123` or `"task": null`-becomes-truthy-list
would raise `AttributeError` deep inside the bridge path. `cmd_pragmatic_stop`
passes `args[0]` (always a str from argv — safe). **Should `_normalize_slug`
coerce non-str input (`str(raw)`) or the call sites validate type, so a
malformed state file degrades gracefully instead of crashing `complete`?**

### Finding 3 — WARN
Empty-`args[0]` divergence between the two entry points. `cmd_pragmatic_stop`
with an empty-string slug arg (`pragmatic-stop "" reason`) passes `len(args)>=2`,
so `_normalize_slug("")` returns `unnamed-task` and the event is logged silently
under the fallback. `cmd_amaw_enable ""` hits `if args:` truthy-false (empty
string is falsy) so `task` is left unset → `(unnamed)`. **Should an explicitly
empty slug arg be rejected with a usage error in both verbs, rather than one
silently bridging a real `pragmatic_stop` event under `unnamed-task` and the
other silently dropping the arg?** Same input, two behaviours.

## Notes on what was checked and cleared
- Bundle mirror byte-identical (`diff` exit 0). Not flagged.
- `_normalize_slug` idempotency, regex run-collapse, `strip("-")` fallback: all
  hold. Not flagged.
- `cmd_complete` ordering — `_normalize_slug` defined at l.315, called at l.281
  (module-level def, runtime call) — no forward-reference issue. Not flagged.
- Normalization NOTE print (l.350-351) only fires on actual change. Correct.

---
Lessons consulted: 4 (1 adversary-rejection, 3 generic guardrails)
Step 0 query strings used: "workflow-gate task slug normalization" (type=guardrail); "cmd_amaw_enable slug" (tags=adversary-rejection)
Guardrails relevant: none — only generic git-push / migration guardrails returned, none about slug/tag handling
Prior REJECTED patterns: r1 of THIS task (1 BLOCK cmd_pragmatic_stop, 2 WARN) — all 3 resolved; rdy-rejected-test review-design (contract holes) — unrelated domain
