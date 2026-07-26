# S3 deep-dive — auditing the "honest engineering calls"

**Date:** 2026-07-25 · prompted by: *"deep dive this before continue"* — a challenge to the
"leave separate" verdicts, in case they were rationalized laziness rather than real judgment.

## What was audited

Every S3 decision to NOT merge, re-verified against code (not memory):

1. **authoring_run tier-split — CONFIRMED sound.** Verified all 5 W ops
   (create/start/resume/gate/revert_all) mint a confirm-token (`gate_or_confirm`/
   `mint_confirm_token`) and all 4 A ops (pause/close/accept_unit/reject_unit) call `svc.<op>()`
   immediately. The tier boundary is genuinely behavioral; merging W+A would break gating.

2. **arc-engine / motif adopt+mine / conformance / reference / work — CONFIRMED separate.**
   Mixed tier+scope, distinct transforms, or true singletons (reference has only find+update;
   work has only create+get+switch — no CRUD pair).

3. **derivative family — my verdict was RIGHT but my REASON was wrong, and there was a real bug behind it.**

## Two real findings (the value of the push)

### Finding A — a shipped correctness bug: `motif_edit` op=patch lost null-clear

`motif_patch` builds its SQL SET clause from `model_dump(exclude_unset=True)`, so an **explicit
null clears the column** (`emotion_target=null` → `SET emotion_target = NULL`). But `motif_edit`
forwarded patch fields with `_present` (drop-None), which collapses absent-vs-null — so through
the unified tool you could **not clear a nullable field the legacy tool can**. A flat op superset
can't distinguish the two by value; you must route the caller's own `model_fields_set`.

**Fix:** new `_passed(args, *names)` forwards fields by `model_fields_set` (preserving explicit
None). Applied to `motif_edit` op=patch. The other 6 merged update handlers use the
`if value is not None` pattern (None = unchanged, never clears) — audited, `_present` stays
correct for them. Test + mutation (reverting to `_present` reds the null-clear test).
**LIVE-VERIFIED:** motif `emotion_target='dread'` → `motif_edit op=patch emotion_target=null` →
column NULL.

### Finding B — a family the prefix-based survey MISSED: derivative CRUD

My family survey grouped by name-prefix (`arc_*`, `motif_*`), so it never bucketed
`archive_derivative` + `divergence_spec_update` together — yet both are A/book, both keyed by the
derivative's own `project_id`, both reject the canonical Work: **soft-DELETE + UPDATE on the same
entity.** I had dismissed them as "unrelated semantics" (wrong) and later thought null-clear made
them unmergeable (also wrong — `_passed` solves it).

**Action:** merged into `composition_derivative_edit(op=archive|update_spec)` [A/book], using
`_passed` so the documented `pov_anchor=null` clear survives. `create_derivative` stays separate
(W/confirm-gated); `switch_active_work` stays separate (a per-user active-work PREF keyed by
`book_id` over any Work, not derivative-CRUD). Live: both ops reach their handlers (the
`NOT_A_DERIVATIVE` domain rejection on a canonical Work proves dispatch + arg-forwarding);
validation clean; legacy hidden.

## Method correction (so it doesn't recur)

- **Survey CRUD families by the ENTITY an op mutates, not by name-prefix** — same-entity ops with
  divergent names (`archive_derivative` vs `divergence_spec_update`) hide from a prefix scan.
- **op-dispatch + a PATCH handler that uses `exclude_unset`/`model_fields_set` ⇒ forward by
  `model_fields_set` (`_passed`), never drop-None** — else explicit-null clears are silently lost.

## Net

- 1 real correctness bug found + fixed (motif null-clear), live-verified.
- 1 genuinely-missed family recovered (derivative_edit).
- 3 "leave separate" verdicts re-confirmed with correct reasons.
- Composition default discovery: **96 → 50** (9 families, 48 legacy write tools → 13 unified).

---

## Round 2 — real bugs found by continuing the deep-dive (2026-07-25)

Prompted by *"have we fixed real bugs?"* → *"deep dive and fix them"*. Audited the composition
write handlers for correctness (gating, OCC, integrity invariants, contract-vs-behavior). Most
were solidly defended (scene_link validates both endpoints are scenes in the gated project;
switch_active_work validates the target belongs to the book; OCC enforced). **Three real bugs
found in one cluster — Undo affordances that silently vanished + an advertised-but-unreachable
reversibility:**

### Bug 1+2 — bare-STRING `undo_hint` silently dropped (no Undo button)

`chat-service tool_undo_hint()` returns `hint if isinstance(hint, dict) else None`. Two Tier-A
composition tools returned a **string** `undo_hint`, so the consumer dropped it → the FE activity
strip showed **no Undo** for these reversible actions:
- `composition_archive_derivative`: `"restore by PATCH status=active"` — a string, AND naming an
  operation no tool exposed.
- `composition_switch_active_work`: `"…project_id=null → back to canonical"` — a string, AND only
  ever offering canonical (not the true prior).

Cross-service sweep: **isolated to composition** — book/glossary/provider-registry all emit the
structured `{tool,args}` map. Fixed both to structured `_undo(...)`. Live-verified: both now
return dicts; `switch_active_work`'s undo restores the **actual prior** active Work (added
`get_user_preference` to capture it first) — proven live (switch→WORK then→canonical yields an
undo pointing back at WORK).

### Bug 3 — `archive_derivative` advertised a reversibility NO path delivered

The archive claimed "REVERSIBLE" but **no tool or REST route un-archived a derivative** (nothing
set a Work's `status` back to `active`). Fixed by adding `op=restore` to
`composition_derivative_edit` (the un-archive that makes the claim real) over the SAME
`WorksRepo.update` the archive uses — EDIT-gated, derivative-only, OCC, with a structured
re-archive undo. Live: `op=restore` is wired + reaches the guarded handler (NOT_A_DERIVATIVE on a
canonical Work). Also corrected the false "restore by switching it active" claim in the
`derivative_edit`/`archive_derivative` descriptions (switching active sets a pref, never changes
status).

**Net round 2: 3 real bugs fixed** (2 silently-dropped Undo affordances + 1 unreachable
reversibility), 6 tests (incl. the pre-existing test that had PINNED the buggy string hint),
live-verified. Method note: contract-vs-behavior ("the description promises X; does the code do
X, and can the consumer even read the result?") is the lens that keeps yielding real defects.
