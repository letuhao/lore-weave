# Scope Guard — POST-REVIEW: amaw-task-slug-validation

**Verdict: CLEAR**

DEFERRED #001 — `_normalize_slug()` slugifies user-supplied task slugs so
commas/spaces cannot fragment the downstream comma-joined tag list.
Classified S, AMAW mode. Adversary: r1 REJECTED → fixes → r2 APPROVED_WITH_WARNINGS.

## Step 0 — Captured-rules check

- `check_guardrails "ready-to-commit" --format json` → `{"pass": true, "rules_checked": 3}` — exit 0. No block.
- `search_lessons "task slug normalization" --type guardrail` → 3 matches, all generic (DB migration, git push, force-push). None slug/tag-specific. No block.

Both Step 0 calls succeeded. No guardrail blocks this commit.

## Checklist

### 1. DEFERRED #001 acceptance — comma-fragmentation closed at ALL entry points?

YES. The slug becomes a tag in `_bridge_to_contexthub`'s `",".join(tags)` at both
write paths and the read path:

- `cmd_amaw_enable` (write side) — l.352 `normalized = _normalize_slug(args[0])`,
  l.355 `state["task"] = normalized`.
- `cmd_pragmatic_stop` (independent arg) — l.440 `task_slug, reason = _normalize_slug(args[0]), args[1]`;
  feeds `_log_audit` (l.448-454) and `tags=["amaw","pragmatic-stop",task_slug]` (l.460).
- `cmd_complete` (read side) — l.280-281 `raw_task = state.get("task"); task_slug = _normalize_slug(raw_task) if raw_task else "unnamed-task"`;
  feeds `tags=["amaw","sprint",task_slug]` (l.304) and `["amaw","adversary-rejection",task_slug]` (l.311).

All three slug→tag flows are normalized. AC covered: 2/2 (cmd_amaw_enable, cmd_pragmatic_stop). AC uncovered: 0.

### 2. Adversary r1 — all 3 findings resolved?

3/3 resolved.
- r1 BLOCK (cmd_pragmatic_stop unnormalized slug) → RESOLVED at l.440.
- r1 WARN-2 (cmd_complete read side) → RESOLVED at l.280-281 (defensive re-normalize).
- r1 WARN-3 (unnamed-task sentinel collision) → ADDRESSED by docstring l.328-333
  codifying the two-layer split (`unnamed-task` value layer / `(unnamed)` display layer).
  Literal collision is now a conscious documented design choice — acceptable.

### 3. Adversary r2 — disposition of 3 WARNs

- r2 WARN-1 (cmd_amaw_enable no-arg/already-enabled leaves raw state["task"]) →
  DEFERRED.md entry #007 exists, L4 hardening, LOW severity. Conscious deferral with
  mitigation noted (cmd_complete re-normalizes the OUTPUT tag list; only the
  state-file display value can be stale). Properly tracked.
- r2 WARN-2 (no non-str guard) → FIXED in code: l.338 `str(raw).lower()`.
- r2 WARN-3 (empty-arg divergence) → declared false finding by author.
  INDEPENDENT RULING: author is CORRECT. `cmd_amaw_enable` receives `args=[""]`
  (a one-element list). `bool([""])` is `True`, so `if args:` ENTERS the branch,
  `_normalize_slug("")` runs → `"unnamed-task"`. `cmd_pragmatic_stop ""` also
  yields `_normalize_slug("")` → `"unnamed-task"`. Verified by executing both
  paths: identical result. The Adversary r2 conflated `bool([""])` (truthy list)
  with `bool("")` (falsy string). No divergence. WARN-3 is genuinely a false finding.

### 4. Bundle mirror byte-identical?

YES. sha256 of both `scripts/workflow-gate.py` and
`agentic-workflow/scripts/workflow-gate.py` = `3e2c9d4a2ae30d18782b675d619f65c86d5265f78ca546ca9a13971fe59fe855`.

### 5. Any NEW problem introduced by the fixes?

None.
- `str(raw)` guard — keeps `_normalize_slug` total; cannot raise on non-str input.
  No regression for str input (`str("x") == "x"`).
- cmd_complete defensive re-normalize — `_normalize_slug` is idempotent, so
  re-normalizing an already-clean slug is a no-op. The `if raw_task else` guard
  preserves the prior `"unnamed-task"` fallback for empty/missing task. Note: prior
  code used `"(unnamed)"` fallback here; new code uses `"unnamed-task"` — this is an
  improvement (tag-safe value, consistent with the value-layer design), not a regression.
- cmd_pragmatic_stop change — normalization happens before the `amaw_enabled` gate;
  harmless (a non-AMAW invocation exits before any tag is built). `args[0]` is always
  a str from argv, so the str() guard is never exercised here. No new failure mode.

## Verdict

CLEAR. DEFERRED #001 fully closed at both entry points + read side. All 6 Adversary
findings (r1 3 + r2 3) resolved or consciously deferred (#007). Bundle mirror
byte-identical. check_guardrails pass. No new problems. spec_drift: false.
