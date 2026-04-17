---
description: On-demand adversarial implementation review. Invoke when POST-REVIEW needs a deeper look or after COMMIT when something feels off.
---

# /review-impl — Adversarial implementation review

Perform a deep adversarial review of the most recent implementation work. This is the **separate mental mode** that POST-REVIEW deliberately does NOT do (see `CLAUDE.md` Phase 9 note).

## Scope

Review whatever the user is currently focused on. If `$ARGUMENTS` names a task (e.g. `K17.9`), scope to that task's files. Otherwise scope to the changes in the latest commit (`git show --stat HEAD`).

## How this differs from the REVIEW-CODE phase (Phase 7)

| Phase 7 REVIEW-CODE | `/review-impl` |
|---|---|
| "Does the code implement the design? Are the patterns clean?" | "What does the test coverage **miss**? What could break that nothing currently guards against?" |
| Focus on the code as written | Focus on the *surface area the code leaves exposed* |
| 2-stage: spec compliance + code quality | 1-stage: coverage gaps + drift risk + adjacent correctness |

## Mental mode — required before starting

Before reading any file, list in your head:
1. **Every field on every input model** — which ones does the implementation actually persist/act on, and which are silently dropped?
2. **Every normalization step upstream** — does any of them make a downstream defense moot? (e.g., `_normalize_predicate` munching whitespace before a whitespace-sensitive sanitizer runs)
3. **Every invariant the implementation claims** — idempotence, ordering, dedup keys — and whether a future change could break them without a test catching it
4. **Every boundary between this code and its callers/callees** — what contract is assumed, and what happens if that contract drifts?

## Process

1. **Read the task's plan row** (e.g. from `KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md`) to recover the acceptance criteria in their original form.
2. **Re-read all changed files from disk** — `git show HEAD` for the latest commit, or files matching the task.
3. **Read all callers and callees one hop out** — the implementation is at a boundary; the boundary partners can hide bugs.
4. **For each input-model field:** is it persisted, transformed, or dropped? If dropped, is that intentional?
5. **For each defensive operation** (sanitize, validate, dedup): does an upstream step make it moot? Is there a test that would catch if it became moot?
6. **For each test added:** does it prove the invariant, or does it merely exercise the happy path?

## Output format

Return findings as a numbered list, **ordered by severity**: HIGH (production bug), MED (real risk but not exploitable today), LOW (coverage/drift/documentation), COSMETIC (test-quality smell).

For each finding:
- One-line title with severity tag
- `file:line` reference
- What's actually wrong (1–3 sentences)
- Suggested fix or "accept and document"

**If you find nothing, say why convincingly** — list the specific coverage checks you made and what you verified they pass. Do NOT output "0 issues found" without that evidence; that's the rubber-stamp we're trying to avoid.

## When to suggest follow-up work vs. fix now

- HIGH → fix now, loop back to VERIFY
- MED → the user decides: fix-now or deferred item in SESSION_PATCH
- LOW + COSMETIC → default to deferred item unless batching with HIGH/MED fixes

Never silently accept a HIGH finding.
