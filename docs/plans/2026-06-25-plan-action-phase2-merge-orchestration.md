# Design + Plan — Plan-action Phase 2 slice 2: planner orchestrates merge (batch dedup)

**Branch:** `feat/composition-service` · **Size:** L · **Date:** 2026-06-25
**Spec:** [2026-06-25-plan-action-kit.md](../specs/2026-06-25-plan-action-kit.md) (companion P2 — "orchestrate existing actions").

## Why this shape (the design decision)

The scout established that glossary **entities are UUID-identified and their names are non-unique EAV
values** — so a planner cannot safely address an existing entity by name (slice-1's "don't ship vocab
the planner can't drive" lesson). But **merge has a context source that already carries UUIDs**: the
`merge_candidates` table (detected duplicate clusters, written by knowledge-service coref detection).

So the planner does NOT invent entity references — it **selects from detected candidates**. Its only
cognitive task is "which of these detected duplicate-groups should be merged", emitting the cluster's
**`candidate_id`** (one stable PK per cluster). The handler resolves everything else at execute time.

### Addressing: `candidate_id`, resolved at execute time
- The planner copies **one UUID per merge** (`candidate_id`), shown in its context — not a member-UUID
  it transcribes, not an ambiguous name. A mis-copied id → `target_gone` (fail-safe).
- The handler loads the candidate's **current** `member_entity_ids` at execute time → no staleness (the
  plan token stays valid even if members shift between propose and confirm).
- Winner resolution (deterministic, no planner UUID needed): `winner_id` if supplied **and** a member →
  else the candidate's `suggested_winner_entity_id` (the detector's hint) → else `ErrBadParams`.

### One op per candidate (not a batch param)
`merge_candidate` (singular) — `{candidate_id, winner_id?}`. The planner emits one per cluster, so each
gets its **own enable toggle** in the confirm card (per-candidate veto, slice-1 model). `MaxPlanOps=50`
caps the batch; `ValidatePlan` dedupes by `candidate_id`.

## Work items

### BE — glossary op (`plan_ops.go`)
- Register `merge_candidate` OpSpec: **tier 5, Destructive:true, Idempotent:true**. IdentityKey =
  `candidate_id`. Validate = `candidate_id` is a UUID (and `winner_id` a UUID when present).
- `loadCandidateForMerge(ctx, bookID, candidateID) (members []uuid.UUID, suggested *uuid.UUID, status string, found bool, err error)`.
- Handler: load candidate (book-scoped) → not found = `ErrNotFound` (target_gone); status≠`proposed` =
  `ErrAlreadyDone` (already merged/dismissed); resolve winner (above) → losers = members∖winner (empty =
  `ErrBadParams`) → `mergeEntitiesCore(bookID, winner, loserStrs, userID)`; `errMergeBadWinner` →
  `ErrNotFound`. Detail = `{winner, results}`. `mergeEntitiesCore` already journals + `markCandidatesMerged`.

### BE — preview (`plan_confirm.go`)
- `previewPlanOp` `merge_candidate` case: load the candidate → row shows winner name (kept) + loser
  names (merged away) + "reversible (journaled)". `op_id`+`destructive` stamped generically (slice 1).
  Unknown/dismissed candidate → "already resolved — will be skipped".

### BE — planner context + vocab (`action_plan_tools.go`)
- `ontologyStateSummary` appends a **"Pending merge candidates"** block when `loadMergeCandidates(book,
  "proposed")` is non-empty (cap ~25 by score): per candidate — `candidate_id`, kind, members
  (`name` + entity-id + link count), suggested winner, score, rationale.
- Planner vocab: add `merge_candidate {candidate_id, winner_id?}`. Guidance: emit ONLY when the user asks
  to dedup/merge duplicates; reference a `candidate_id` from the block; copy `winner_id` only to override
  the suggested winner. DESTRUCTIVE → the user confirms each.

### Reuse (no logic reimplemented)
`loadMergeCandidates` (context), `mergeEntitiesCore` (executor + journal + mark-merged),
`entityNameAndAliases` (preview names). The op is a thin selector→resolver→core wrapper.

## Tests
- DB-free: validate (bad candidate_id rejected; winner_id optional), parse a `merge_candidate` plan,
  registry guard (now 8 ops; merge_candidate destructive), enabled_ops default-skip for it.
- Real-PG: seed 2 same-kind entities + a `proposed` merge_candidate → `merge_candidate` op (enabled) →
  applied, loser soft-deleted + candidate flips `merged`; re-run → `already_done`; bogus id → `target_gone`.

## VERIFY
`go build`/`vet`/tests green; provider-gate OK. Real-PG merge round-trip. FE unchanged (the slice-1
toggle already renders any destructive plan op — confirm the merge_candidate preview rows render).

## Risk boundary
One commit at the slice complete (op + context + vocab + tests). Stage only my files (shared-tree hazard).
`D-PLAN-EXEC-LIVE-SMOKE` (chat-UI) still covers the browser leg; this slice adds the merge path to it.
