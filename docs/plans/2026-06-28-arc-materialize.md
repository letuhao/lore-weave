# PLAN — D-W10-APPLY-PLANNER-MATERIALIZE (arc apply → committed outline)

**Size:** L/XL (backend, commit-path, cross-service). **Date:** 2026-06-28.

## Goal
The arc-template `apply` endpoint returns only the PURE preview plan (`ArcApplyPlan`). This
task adds **materialization**: turn the rescaled placements into a **committed
arc→chapter→scene outline** + a **`motif_application` ledger**, deterministically.

## Key finding — it's DETERMINISTIC (no LLM)
`engine/motif_select.scenes_from_motif` already turns a motif's **beats → ScenePlans with NO
LLM** (the bound-chapter path; "the motif IS the structure"). So materialize reuses the exact
deterministic primitives the A3 decompose-commit uses:
- `OutlineRepo.commit_decomposed_tree(...)` — atomic + idempotent + replace-aware tree writer
  (maps onto the book's EXISTING chapters; never mints book chapters).
- `MotifApplicationRepo.insert_many(...)` — the binding ledger (one row per bound scene).
- `scenes_from_motif` + `build_application_rows` — beats → scenes + ledger payloads.

The richer per-scene LLM prose is the EXISTING downstream generate path (unchanged) — not part
of materialize. (LLM "decompose planner" framing in the defer row resolves to this no-LLM path.)

## Beat → chapter distribution (the one real design choice)
A motif placement spans chapters `[s..e]`; the motif has beats `[b0..b(n-1)]`. Distribute **every
beat** across the span (NO beat lost, §12.6 spirit): beat `j` → chapter `s + floor(j*w/n)` (w =
e-s+1), grouped per chapter. Degenerate cases: `w=1` → all beats in that chapter (== decompose);
`n<=w` → ≤1 beat/chapter, some chapters empty for this motif (others may fill them).

## Motif resolution
Each placement carries `motif_code` (+ optional `motif_id`). Resolve to the full `Motif` (needs
beats):
- `motif_id` present → `MotifRepo.get_visible(user, motif_id)`.
- else → `MotifRepo.get_by_codes(user, codes)` (NEW additive method — tier-merged, caller's own
  shadows system by code).
- unresolved (no id + no visible code, or archived) → surfaced in `report.unresolved_placements`
  (NO silent drop); that placement contributes no scenes.

## Surface (additive, work-scoped — lives in plan.py with the decompose family)
`POST /v1/composition/works/{project_id}/arc/materialize`
Body: `{ arc_template_id, roster_bindings?, replace?, idempotency_key? }`.
Flow:
1. `_require_work` → book_id; `arc_template_repo.get_visible` (404 uniform).
2. `_book_chapter_ids` (ordered by sort_order); `target = len(chapters)`; 400 NO_CHAPTERS if 0,
   TOO_MANY_CHAPTERS if > plan_max_chapters.
3. `build_apply_plan(arc, ArcApplyArgs(target_chapters=target, roster_bindings))` — reuse the
   preview rescale.
4. resolve motifs; `_cast_roster` → cast_names for {role token} rendering.
5. `build_materialize_spec(plan, motifs, chapter_ids, cast_names)` (NEW pure engine) →
   `{ commit_chapters (spec), scene_application_rows (parallel, per scene), report }`.
6. `outline.commit_decomposed_tree(... replace, idempotency_key)` → ids.
7. `MotifApplicationRepo.insert_many` the ledger (positional with scene_ids; mirror decompose's
   non-atomic, FK-tolerant ledger pattern — documented).
8. return `{ arc_id, chapter_ids, scene_ids, motif_applications, unresolved_placements, replay }`.

Guards reused: IDOR (chapter ∈ book), EMPTY guard (no scenes anywhere → 400), AlreadyPlanned
(409 unless replace), idempotency replay.

## Files
- `engine/arc_materialize.py` (NEW, pure) + `tests/unit/test_arc_materialize.py`.
- `db/repositories/motif_repo.py` — `get_by_codes` (additive) + a repo test.
- `routers/plan.py` — the new endpoint + request model.
- `tests/unit/test_arc_materialize_route.py` — route dispatch/guards (fakes).

## Acceptance
- Deterministic spec: same arc+book → byte-identical commit spec (pure engine test).
- Every beat lands in some chapter within its span (no loss); multi-chapter motif distributes.
- Unresolved placements surfaced, never silently dropped.
- Ledger rows map 1:1 to bound scenes (positional), beat_key in annotations.
- Live smoke: author arc (real motif_ids) → materialize onto a test book → GET outline shows
  committed arc→chapter→scene + conformance/bindings read the ledger. Cleanup.
- replace=true re-materializes; idempotency_key replays.
```
