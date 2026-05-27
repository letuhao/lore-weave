# Plan — `erode_zone` simple-point pre-filter

> **Spec:** [`docs/specs/2026-05-21-tilemap-erosion-simple-point.md`](../specs/2026-05-21-tilemap-erosion-simple-point.md)
> **Workflow:** default v2.2; `/review-impl` at POST-REVIEW (correctness-critical).

---

## Chunk 1 — `local_seal_verdict` helper + AC-1 oracle test

**Files:** MOD `services/tilemap-service/src/engine/modificators/obstacle_placer.rs`

1. Add `local_seal_verdict(tile, passable, passable_count, grid) -> Option<bool>`:
   - Read 8 neighbours via bounds-checked `passable.get`.
   - Count passable cardinals; union via passable diagonals; count groups.
   - `groups >= 2` → `None` (caller flood-fills).
   - `groups == 0` → `Some(passable_count == 1)`.
   - `groups == 1` → `Some(false)`.
2. **AC-1** `local_seal_verdict_matches_would_seal_a_gap_oracle` — random 9×9
   passable masks; for every passable tile `T`, assert the `Some`/`None`
   resolution equals `would_seal_a_gap({T}, passable)`. (For `None`, the test
   itself runs `would_seal_a_gap` — verifying we only return `None` when a
   flood fill is genuinely needed is implicit; the binding assertion is that
   when we return `Some(v)`, `v == would_seal_a_gap`.)

**Done when:** AC-1 passes — the per-tile verdict is bit-exact.

---

## Chunk 2 — wire the pre-filter into `erode_zone` + `erode_zone_naive` oracle

**Files:** MOD obstacle_placer.rs

1. Rename the current `erode_zone` body to `erode_zone_naive` under
   `#[cfg(test)]` (the unconditional-flood-fill oracle).
2. New `erode_zone`: maintain `passable_count` (init `passable.count_ones()`,
   decrement per erosion); replace the unconditional `would_seal_a_gap` with
   the `match local_seal_verdict(...) { Some(v) => v, None => <flood fill> }`.
3. **AC-2** `erode_zone_matches_naive_on_random_zones` — 200 random carved
   9×9 zones; run both `erode_zone` + `erode_zone_naive` on independent state
   copies; assert identical eroded mask + identical post `zone_passable`.

**Done when:** AC-2 passes; all existing erosion tests pass unchanged.

---

## Chunk 3 — AC-3 unit cases

**Files:** MOD obstacle_placer.rs

`simple_point_unit_cases` — one assertion per §4 branch:
- isolated single tile (passable=={T}) → verdict true (eliminates).
- isolated tile among others → verdict false.
- leaf stub (1 cardinal) → false.
- solid-interior boundary (groups==1, ≥2 cardinals) → false (and `None`? no —
  groups==1 returns `Some(false)`; assert it does NOT need the flood fill).
- 1-wide corridor middle (2 cardinals, no diagonal link) → `None` → flood-fill
  → true.
- T-junction (3 cardinals, ≥2 groups) → `None` → flood-fill.

**Done when:** AC-3 passes.

---

## Chunk 4 — VERIFY + AC-4 measure

1. `cargo test --workspace` green; `cargo clippy --workspace --all-targets` 0.
2. `cargo build --release`; `cargo run --release -- measure`.
3. Record `obstacle_placer` before/after; append to
   [`docs/measurements/2026-05-18-continent.md`](../measurements/2026-05-18-continent.md).

---

## Chunk 5 — REVIEW (code), QC, POST-REVIEW (`/review-impl`)

`/review-impl` mandatory — `erosion_never_seals_a_gap` is the most
safety-critical invariant; an unreachable region is a catastrophic UX bug.

---

## Chunk 6 — SESSION + COMMIT + RETRO

SESSION entry (before/after), DEFERRED (log residual if any), COMMIT
(explicit stage), RETRO (the simple-point lesson generalises the score-first
lesson — note if worth saving; ContextHub may be down this session).

---

## Risk register

| Risk | Mitigation |
|---|---|
| Simple-point test wrong for a corner/border tile | AC-1 tests every tile of random masks incl. borders; off-grid → false via bounds-checked get |
| `passable_count` drifts from actual passable | init from `count_ones()`, decrement only on actual erosion; AC-2 catches drift end-to-end |
| Conservative test accidentally returns false "safe" | §4 proof: groups≥2 always flood-fills; AC-1 is the bit-exact gate |
| Multi-component passable (Penrose hands non-4-connected zone) | `erosion_preserves_a_multi_component_passable_region` existing test + AC-2 random carved zones |
