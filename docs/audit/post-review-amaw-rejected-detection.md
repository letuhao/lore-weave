# Scope Guard Post-Review — amaw-rejected-detection

Verdict: **CLEAR**

Task: DEFERRED #002 — replace substring `"REJECTED" in evidence.upper()` in the
`cmd_complete` bridge with `_had_rejected_review(task_slug, phase)`, which reads
the structured `status` field from AUDIT_LOG.jsonl adversary review events.
Classified S, AMAW mode. Adversary r1: APPROVED_WITH_WARNINGS (0 BLOCK, 3 WARN).

## Step 0 — Captured-rules check
- `check_guardrails "ready-to-commit"` → `pass:true`, `rules_checked:3`, no matched rules.
- `search_lessons "AMAW bridge rejection detection" --type guardrail` → 3 hits
  (DB-migration, confirm-git-push, force-push-auth) — none gate this change
  (no git/migration path touched). Step 0 calls both succeeded.

## Checklist

1. **DEFERRED #002 acceptance — CLOSED.** The bridge condition (line 347) is now
   `phase in ("review-design","review-code") and _had_rejected_review(task_slug, phase)`.
   It no longer reads `evidence` to decide rejection. `_had_rejected_review`
   (lines 111-115) keys on `action == "review"` + `phase` + structured
   `status == "REJECTED"`. A `phase_complete` event whose free-text `evidence`
   contains "NOT REJECTED" cannot match — its `action` is `"phase_complete"`,
   not `"review"`. False-positive eliminated. AUDIT_LOG case D confirms
   ("phase_complete event with 'REJECTED' in free-text evidence → NOT matched").

2. **Adversary r1 WARNs — all dispositioned.**
   - WARN-1 (phase not matched): FIXED — helper signature is
     `_had_rejected_review(task_slug, phase)`, line 113 adds
     `ev.get("phase") == phase`. A design-phase REJECTED no longer mislabels a
     `review-code` lesson.
   - WARN-2 (trailing whitespace): FIXED — line 114 is
     `str(ev.get("status","")).strip().upper() == "REJECTED"`, symmetric with
     the line-level `.strip()` on 104.
   - WARN-3 (whole-log re-read + ordering dependency): DOCUMENTED/ACCEPTED in the
     docstring (lines 94-99) — bridge calls are rare (review-phase completion),
     log is per-repo small, ordering is guaranteed by AMAW orchestration.
   3/3 prior findings resolved.

3. **Bundle mirror — byte-identical.** `fc /b scripts\workflow-gate.py
   agentic-workflow\scripts\workflow-gate.py` → no differences.

4. **Logic trace — correct.** The `and` chain returns True only when all four
   conditions hold: `task` matches, `action == "review"`, `phase` matches,
   `status` (stripped/uppercased) `== "REJECTED"`. The original-bug event
   (`action:"phase_complete"`, "REJECTED" in free-text evidence) fails the
   `action == "review"` clause → correctly ignored. Approved-only tasks scan to
   EOF and return False. First match short-circuits via `return True`.

5. **No new regression from the phase param.** The stricter `phase` match is
   safe: the Adversary writes its review event with the same phase token the
   main agent passes to `complete` (`review-code` row in AUDIT_LOG carries
   `"phase":"review-code"`). A legitimate same-phase rejection is still caught;
   only a cross-phase rejection is (correctly) excluded — that was WARN-1's
   intended fix, not a missed rejection. No legitimate rejection is lost.

## Authority gates — none triggered
- No unresolved Adversary finding (3/3 dispositioned).
- DEFERRED #002 acceptance verified closed.
- Mirror byte-identical.
- check_guardrails passed.

Cleared for SESSION + COMMIT.
