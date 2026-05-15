# Adversary Review — amaw-rejected-detection (review-code, round 1)

Verdict: APPROVED_WITH_WARNINGS — 3 findings, 0 BLOCK, 3 WARN.

The change correctly replaces the substring false-positive with a structured
`status` read. The #002 defect (matching "NOT REJECTED") is genuinely closed,
verified by AUDIT_LOG case D. Three concerns remain worth fixing.

## WARN-1 — Helper ignores `phase`; cross-phase mislabel
`_had_rejected_review` (workflow-gate.py:100-103) matches on `task`,
`action == "review"`, `status == "REJECTED"` — but NOT on `phase`. The bridge
at line 335 fires for `phase in ("review-design","review-code")` and titles the
lesson `f"Adversary REJECTED: {task_slug} {phase}"` (line 338).

Scenario: Adversary REJECTS in `review-design`, later APPROVES in
`review-code`. When the main agent completes `review-code`, the helper still
returns True (the design-phase REJECTED row matches), so a lesson titled
"Adversary REJECTED: <task> review-code" is filed — but review-code was never
rejected. The title misattributes the rejection to the wrong phase.
Question: shouldn't the helper take the phase and match
`ev.get("phase") == phase`, so the lesson title reflects where the rejection
actually occurred? The docstring even says "ANY adversary review event" — that
is the bug, not the intent.

## WARN-2 — `status` exact-match brittle to trailing whitespace
Line 102 does `str(ev.get("status","")).upper() == "REJECTED"`. `.upper()`
covers lowercase, but an Adversary writing the AUDIT_LOG line by Bash heredoc
(the documented sub-agent path, DEFERRED #006) can easily emit `"REJECTED "`
or `" REJECTED"` — a stray space silently fails the match and the rejection
lesson is lost. The failure is silent: no rejection bridged, no warning.
Question: should this be `.strip().upper() == "REJECTED"` to be symmetric with
the `.strip()` already applied to the *line* on line 93? The instructions to
the Adversary template (own JSON line) are not machine-validated, so defensive
normalization of the value is cheap insurance.

## WARN-3 — Whole-log re-read on every bridge call; unbounded growth
`_had_rejected_review` reads the ENTIRE AUDIT_LOG.jsonl
(`read_text().splitlines()`, line 92) on every `review-design`/`review-code`
completion. AUDIT_LOG is append-only and committed — it grows without bound
across every AMAW task forever. Today it is 29 lines; in a year it could be
thousands. Each bridge call re-parses all of it.
Not a correctness bug and JSON-per-line is cheap, but: question — is there any
intent to scope the scan (e.g. break early, or only the current task's recent
rows)? At minimum the early `return True` on first match helps; worst case is
"approved-only" tasks which must scan to EOF. Acceptable for a local dev tool,
flagged so the unbounded-growth assumption is a conscious decision, not an
oversight. Pairs with an ordering note: the helper's correctness depends on the
Adversary's review event being flushed to AUDIT_LOG *before* the main agent
runs `cmd_complete review-code` — true in the AMAW orchestration (main waits on
sub-agent) but not enforced by code; if a future caller reorders this, the
helper silently returns False.

## Footer
- Lessons consulted: c0aef658 (DB migration L+), b2d376de (confirm git push),
  b21930d8 (force-push auth), e52f469a (Adversary REJECTED amaw-task-slug-
  validation — prior adversary-rejection lesson, unrelated to this change as
  noted), f333a0e5 (Adversary REJECTED rdy-rejected-test).
- Step 0 queries: "AMAW bridge rejection detection audit log" (type=guardrail);
  "cmd_complete bridge REJECTED" (tags=adversary-rejection).
- Guardrails relevant: none of the 3 returned guardrails (migration, git push,
  force-push) gate this change — it touches no git/migration paths.
- Prior REJECTED patterns: e52f469a shows the recurring AMAW miss type —
  "fix applied to one entry point, second path left unhandled." Checked here:
  the bridge is the only caller of the substring match; no second un-migrated
  call site. WARN-1 (phase scope) is the analogous "incomplete fix" risk.
