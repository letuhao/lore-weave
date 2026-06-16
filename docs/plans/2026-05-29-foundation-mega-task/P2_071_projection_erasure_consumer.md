# P2/071 — projection-erasure consumer (D-PROJECTION-ERASURE)

**Status:** DESIGN (build-ready; recommended for a dedicated session — XL, follows the long 101+113+112 arc)
**Size:** XL — 2 production adapters + meta-worker dispatch wiring + audit + cross-service live-smoke.
**Unblocked by 113:** `user.erased` now emits → `meta-outbox-relay` xreality bridge → `xreality.user.erased` carries top-level `user_id`/`erased_at`. The consumer (`meta-worker/user_erased_writer`) has the orchestration but is registered as a **skeleton no-op** (`dispatch.go:207`) with **no production adapters**.

## What exists vs what 071 builds
- **Exists:** `user_erased_writer.Writer` (`New(Config{Lookup, PerRealityDB, AuditSink, …})`, `HandleUserErased` → `RealitiesForUser` → `ScrubUserRefs` per reality, NACK-on-error per Q-L5H-1 inverted = over-scrub safe / under-scrub leaks); `decodePayload` (reads top-level `user_id`/`erased_at`/`event_id`); meta-worker's per-reality pool infra (`realityreg`, used by the canon path); the `xreality.user.erased` XREADGROUP consume loop pattern.
- **071 builds:**
  1. **`PgUserRealityLookup`** (meta) — `RealitiesForUser(userID)` = `SELECT DISTINCT reality_id FROM player_character_index WHERE user_ref_id=$1`. (Q-L5H-1: prefer over-inclusion.)
  2. **`PgPerRealityScrubber`** (per-reality) — `ScrubUserRefs(ScrubIntent{RealityID, UserID, …})` = idempotent `UPDATE pc_projection SET name='[erased]', status='deleted' WHERE user_id=$1 AND status <> 'deleted'`. **`pc_projection` is the ONLY per-reality projection referencing `user_id`** (verified against `0006_projections`).
  3. **Wire `HandleUserErased`** into `meta-worker/cmd/meta-worker/main.go` (register for `xreality.user.erased`, replacing the `dispatch.go` skeleton) + build the per-reality scrubber from the existing reality pools.
  4. **Audit** each scrub (Q-L1A-3 = no sampling) — a `service_to_service_audit` / dedicated erasure-audit row per reality scrub (the scrub is a per-reality projection UPDATE, NOT a meta-table MetaWrite, so it's outside meta-write-discipline).
  5. **Live-smoke:** seed a `pc_projection` row + `player_character_index` row → publish `xreality.user.erased` → meta-worker consumes → assert `pc_projection.name='[erased]'`/`status='deleted'` + idempotent re-delivery.

## KEY SCOPE DECISION (for sign-off) — what counts as user PII to scrub
1. **Per-reality `pc_projection`** (the projection-erasure target, D-PROJECTION-ERASURE proper): `name` → `'[erased]'` (NOT NULL, so a sentinel not NULL) + `status` → `'deleted'`. Open: also clear `stats` JSONB? (likely game stats, not PII — default: leave.)
2. **Meta `player_character_index.pc_name`** — a SECOND PII copy lives in the meta cross-reality index. Scrubbing it is arguably part of erasure but is a META write (→ via `MetaWrite`, emits `pc.index.status.changed`). **Decision:** fold into 071, or split to the erasure orchestrator (076/admin-cli), or a separate row. Recommendation: fold (the erasure isn't complete while pc_name lingers in the index).
3. **NPC session memory / embeddings** referencing the user's content — out of scope for V1 (no direct user_id column; content-level erasure is a separate, harder problem).

## Gate
Removes the F4 projection-coverage allowlist entry for `xreality.user.erased` so the gate enforces it. Human-in-loop + /review-impl (it's an erasure path). No new migration. Build recommended in a fresh session (this one already shipped 101 ×3 + 113 ×2 + 112).
