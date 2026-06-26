# Plan — Plan-action Phase 2, slice 1: destructive ontology ops + enabled_ops toggle

**Branch:** `feat/composition-service` · **Size:** L (breadth-discounted XL) · **Date:** 2026-06-25
**Spec:** [2026-06-25-plan-action-kit.md](../specs/2026-06-25-plan-action-kit.md) §4 (G1 enabled_ops), §5 (error classes), §18 (additive→destructive boundary).

## Scope (this slice)

Three **destructive ontology ops** the planner can emit, gated by the per-op `enabled_ops`
confirm toggle that finally exercises the `enabledOps` skip already built into `mcp.Execute`:

- `delete_genre` — params `{genre_code}` → `cascadeDeleteBookGenre`
- `delete_kind` — params `{kind_code}` → `cascadeDeleteBookKind`
- `delete_attribute` — params `{kind_code, code}` → `softDeleteBookAttribute`

All `Destructive:true`, `Idempotent:true`, **tier 5** (run after every create/edit op).

**Out of this slice:** `merge_entities` + entity create/edit/rename → **slice 2** (they need entity
context added to the planner's ontology summary; merge isn't an ontology-vocabulary op). Recorded as
the next milestone, not built here.

## Idempotency contract (the subtlety)

The existing primitives return `found bool` = true only when a **live** row was deprecated;
`found=false` conflates *never-existed* with *already-deprecated*. The kit needs them distinguished:

- resolve code **ignoring `deprecated_at`**:
  - no row at all → `mcp.ErrNotFound` → `failed: target_gone` (re-proposable; matches `effectBookDelete`)
  - row exists, `deprecated_at IS NOT NULL` → `mcp.ErrAlreadyDone` → `skipped: already_done` (idempotent re-run)
  - live row → call cascade-delete primitive → `applied`

New resolvers (code→id, deprecation-aware): `resolveBookGenreForDelete`, `resolveBookKindForDelete`,
`resolveBookAttrForDelete` in `plan_ops.go` (or reuse a direct query). Return kit sentinels directly.

## Work items

### BE — kit (`sdks/go/loreweave_mcp`)
- No contract change needed (Destructive/enabledOps/sentinels already exist). Add a kit test asserting
  Execute runs a destructive op **only** when its id is in `enabledOps`, skips it (`not_confirmed`)
  otherwise — if not already covered.

### BE — glossary (`services/glossary-service/internal/api`)
1. `plan_ops.go` — register 3 OpSpecs (tier 5, Destructive); params structs; IdentityKey = the code(s);
   Validate = slug code(s) present; Handlers resolve-then-delete with the idempotency contract above.
2. `action_confirm.go` — `decodeConfirmToken` also decodes `enabled_ops []string`; return
   `(claims, enabledOps, ok)`. Update `confirmAction` + `previewAction` callers (preview ignores it).
3. `plan_confirm.go` — `effectExecutePlan(w, ctx, claims, enabledOps)`: validate each enabled id exists
   in the plan (unknown → 422 `bad_enabled_op`); build `map[string]bool`; pass to `Execute` (replaces
   hardcoded `nil`). `previewExecutePlan` sets `actionPreview.Destructive` if any op destructive; each
   row carries `op_id`; add delete cases to `previewPlanOp` with a cheap cascade-count note.
4. `action_propose_tools.go` — `previewRow` gains `OpID string` + `Destructive bool` (both omitempty).
5. `action_plan_tools.go` — add the 3 delete ops to `plannerSystemPrompt` vocab with guidance:
   emit a delete ONLY when the user explicitly asks to remove/delete; deletes are skipped unless the
   user enables them at confirm. (edit_attribute stays out of vocab — HIGH-1.)

### FE — chat (`frontend/src/features/chat`)
6. `ConfirmActionCard.tsx` — for each preview row with `destructive:true`, render an **opt-in checkbox**
   (default **unchecked**) keyed by `op_id`; track an `enabledOps` set; show "N destructive op(s) will be
   skipped unless enabled". Confirm is allowed with none checked (they just skip).
7. `actionsApi.ts` — `confirmAction(domain, token, accessToken, enabledOps?)` includes `enabled_ops` in
   the POST body when provided. Update the preview TS type (`op_id`, `destructive`).

## Tests (TDD)
- Go DB-free: validate (missing code rejected), enabled_ops validation (unknown id → 422), preview
  rows carry op_id+destructive, planner-prompt vocab parse. Kit: enabledOps skip/run.
- Go real-PG (or live-smoke): handler idempotency (delete live → applied; re-run → already_done;
  bogus code → target_gone) + cascade (kind delete deprecates its attributes).
- FE vitest: destructive row renders a checkbox; checked id lands in `enabled_ops`; unchecked → skipped.

## VERIFY
`go build`/`vet`/`test` glossary + kit green; FE `vitest` green + `tsc`; provider-gate OK.
**Live-smoke (destructive, ≥1 service):** plan with a `delete_kind` → preview shows destructive+cascade
→ confirm with `enabled_ops=[that op]` → kind `deprecated_at` set in real PG; confirm with `[]` → skipped.

## Risk boundary / checkpoint
One commit at the **BE complete** seam (ops + wiring + preview + planner, all Go green + smoked), then
the **FE toggle** as the second commit. Stage only the exact files (shared-tree hazard — never `git add -A`,
never touch `composition/*`).
