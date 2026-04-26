# Boundary Folder Lock

> Single-writer mutex for the `_boundaries/` folder. Only ONE agent may write to this folder at a time.

---

## Current owner

- **Owner:** None
- **Claimed at:** —
- **Expected work:** —
- **Expires at:** —
- _Last released:_ 2026-04-26 by main session (RES_001 downstream HIGH-priority impacts Phase 2 — single `[boundaries-lock-claim+release]` commit). 6 HIGH priority downstream items resolved: PL_006 Hungry V1 promotion with magnitude 1/4/7 semantics + WA_006 §6.5 MortalityCauseKind catalog + PL_005 §9.1 harvest sub-intent + trade flow + EF_001 §3.1 cell_owner + inventory_cap + EntityRef + PCS_001 brief §4.4f + §S8 xuyên không body-substitution + 07_event_model 4 EVT-T5 + 2 EVT-T3 RES_001 sub-types registered. 11 MEDIUM/LOW priority items deferred to subsequent commits. Drift watchpoints unchanged at 8 active. See [99_changelog.md](99_changelog.md) for full details. Foundation tier 5/5 complete. Files modified: `_LOCK.md` (claim+release) + `01_feature_ownership_matrix.md` (2 NEW aggregate rows `vital_pool` + `resource_inventory` + RealityManifest extension row updated + RejectReason namespace updated + i18n I18nBundle cross-cutting type row + EVT-T3/T5/T8 sub-type ownership rows + RES-* stable-ID prefix) + `02_extension_contracts.md` §1 (RejectReason `user_message: I18nBundle` envelope extension + I18nBundle type definition) + §1.4 (`resource.*` namespace 12 V1 rule_ids) + §2 (9 OPTIONAL V1 RealityManifest extensions) + `99_changelog.md` (entry). Files created: `features/00_resource/{_index.md, 00_CONCEPT_NOTES.md, 01_REFERENCE_GAMES_SURVEY.md, RES_001_resource_foundation.md}` + `catalog/cat_00_RES_resource.md`. **i18n NEW cross-cutting pattern introduced**: English `snake_case` stable IDs + `I18nBundle` user-facing strings (engine standard going forward; RES_001 first adopter; existing-features audit deferred). 17 downstream impact items tracked in RES_001 §17.2 for follow-up commits (HIGH: PL_006/WA_006/PL_005/EF_001/PCS_001/07_event_model). Q1-Q12 ALL LOCKED via 2-batch deep-dive discussion (Q1-Q5 batch 1; Q6-Q12 batch 2 with 3 NEW big changes — Q9c body-substitution / Q12b buy-sell spread / Q12c NPC finite liquidity). See [99_changelog.md](99_changelog.md) for full details.

---

## How to claim

1. Verify the lock is unowned (Owner: **None**) OR the current claim's `Expires at` is in the past.
2. Replace the "Current owner" section above with your claim:
   - **Owner:** `<short identifier>` — e.g., "main session 2026-04-25", "event-model agent (07_event_model design)", "pcs-agent", "ops engineer"
   - **Claimed at:** `<ISO 8601 timestamp>`
   - **Expected work:** `<one-line summary>`
   - **Expires at:** `<claim TTL — default 4 hours; renewable by re-stamping>`
3. Commit with message starting `[boundaries-lock-claim]` so the lock-claim is auditable in git history.
4. Edit boundary files freely while the lock is yours.
5. On finish: release the lock by:
   - Reverting "Current owner" back to **None**
   - Adding a row to [`99_changelog.md`](99_changelog.md) summarizing what changed
   - Commit with message starting `[boundaries-lock-release]`

---

## Expiry / forced takeover

If a claim's `Expires at` is in the past:
- Any agent MAY take over by replacing the claim with their own
- The new claimant MUST add a row to [`99_changelog.md`](99_changelog.md) noting the previous owner's expiry + their own claim
- This protects against orphaned locks (agent crashes, work abandoned)

The 4-hour default TTL is intentionally short: prefers re-claiming over orphaning. Renewable by re-stamping while still active.

---

## Why single-writer

`_boundaries/` is the META layer that governs how all other features fit together. Concurrent edits create:
- Race conditions on the ownership matrix (two features both claim the same aggregate)
- Conflicting extension-contract rules
- Validator slot reorderings that disagree

A serialized writer eliminates the conflict class entirely. Other folders (features/, 02_storage/, 06_data_plane/, 07_event_model/) have their own ownership rules and are not affected by this lock.

The lock applies ONLY to `_boundaries/`. Agents may freely edit OTHER folders without touching this lock.

---

## Reading is unrestricted

Any agent at any time may READ `_boundaries/*` to check ownership / boundaries before designing. Only WRITES require the lock.
