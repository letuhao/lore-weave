# Boundary Folder Lock

> Single-writer mutex for the `_boundaries/` folder. Only ONE agent may write to this folder at a time.

---

## Current owner

- **Owner:** None
- **Claimed at:** —
- **Expected work:** —
- **Expires at:** —
- _Last released:_ 2026-04-26 by main session (MAP_001 Phase 3 review cleanup S1+S2+S3 + 3 new V1 rule_ids + lazy-cell map_layout fix S2.6) at end of single-atomic commit. See [99_changelog.md](99_changelog.md) for details.

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
