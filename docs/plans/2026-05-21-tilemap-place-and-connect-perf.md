# Plan — `place_and_connect_object`: score-first, validate-on-demand

> **Spec:** [`docs/specs/2026-05-21-tilemap-place-and-connect-perf.md`](../specs/2026-05-21-tilemap-place-and-connect-perf.md)
> **Workflow:** default v2.2 human-in-loop; `/review-impl` at POST-REVIEW
> (correctness-critical: golden test is the hard gate, the §4 determinism
> proof is the soft gate).

---

## Chunk 1 — extract `place_and_connect_object_naive` as the oracle

**Files:**
- MOD `services/tilemap-service/src/engine/object_manager.rs`

**Build steps:**
1. Rename the current `place_and_connect_object` body to
   `place_and_connect_object_naive` under `#[cfg(test)]`. Keep it 100 %
   identical to today's implementation — this is the bit-exact oracle for
   AC-1.
2. Add a stub new `place_and_connect_object` (initially still O(N²) — just
   the same body, not yet refactored) so the crate compiles. We'll refactor
   it in Chunk 2.

**Done when:** crate compiles; all existing tests still pass; the naive is
reachable from tests via `#[cfg(test)] fn place_and_connect_object_naive(...)`.

---

## Chunk 2 — refactor to score-first/validate-on-demand

**Files:**
- MOD `services/tilemap-service/src/engine/object_manager.rs`

**Build steps:**
1. Replace the new `place_and_connect_object` body with the score-first
   algorithm per spec §3.1:
   - Phase A: collect survivors of cheap filters with score (no flood fill).
   - Phase B: stable sort `(score desc, flat asc)`.
   - Phase C: walk in best-first order; first to pass `would_seal_a_gap` +
     `find_access_path` wins; commit + return.
2. Pull the `commit` step into a private helper to avoid duplicating
   `Occupied` painting + oracle refresh between the new function and the
   naive.

**Done when:** all 13 existing `object_manager::tests::*` pass unchanged.

---

## Chunk 3 — bit-exact equivalence tests (AC-1, AC-2, AC-3)

**Files:**
- MOD `services/tilemap-service/src/engine/object_manager.rs` (tests section)

**Build steps:**
1. **AC-1** `place_and_connect_matches_naive_on_diverse_zones` — drive
   *both* algorithms on a panel of small fixtures (5×5 / 8×8 / 12×8 zones,
   varied `free_paths` layouts, varied `min_distance`), place 3–5 objects
   each, assert state equality after each placement. Uses fresh state per
   variant so the oracle replays the same call sequence.
2. **AC-2** `worst_case_zone_with_no_valid_anchor_returns_no_space` — a thin
   corridor where every blocking footprint seals a gap; both algorithms
   return `Err(NoSpace)`.
3. **AC-3** `sort_tie_break_prefers_lower_flat_index_after_score_tie` —
   already covered by `equal_score_anchors_break_to_the_lowest_flat_index`
   but add a fixture where the lower-flat winner is NOT the first in
   `search_area.iter_set()`-order to make the explicit `flat asc` tie-break
   visible (the current test doesn't distinguish iteration order from sort
   order because the `search_area` only has two tiles).

**Done when:** all three new tests pass; oracle confirms bit-exact equivalence.

---

## Chunk 4 — VERIFY + AC-4 continent measurement

**Build steps:**
1. `cargo test --workspace` green.
2. `cargo clippy --workspace --all-targets` 0 warnings.
3. `cargo build --release --package tilemap-service`.
4. `cargo run --release --package tilemap-service -- measure` — record
   `treasure_placer` wall time. **Target: < 10 s.**
5. Append the new measurement to
   [`docs/measurements/2026-05-18-continent.md`](../measurements/2026-05-18-continent.md)
   under a new "2026-05-21 update — TreasurePlacer fix" section.

---

## Chunk 5 — REVIEW (code), QC, POST-REVIEW (`/review-impl`)

`/review-impl` is mandatory at POST-REVIEW per the spec — this rewrite is
correctness-critical. Findings folded inline if LOW/MED; HIGH loops back to
VERIFY.

---

## Chunk 6 — SESSION + DEFERRED + COMMIT + RETRO

1. SESSION_HANDOFF entry above the 2026-05-20 PM entry: before/after
   numbers, deferred cleared (#029).
2. DEFERRED.md: move #029 to "Recently cleared".
3. COMMIT: stage explicitly, no `git add -A`. Message names the
   speedup + cleared deferred.
4. RETRO: if anything non-obvious about the determinism contract is worth
   keeping (e.g. the "score-first ↔ argmax-over-V" lemma generalises), save
   a lesson to ContextHub.

---

## Risk register (for BUILD)

| Risk | Mitigation |
|---|---|
| Score-then-sort changes tie-break semantics in a corner case | §4 proof + AC-1 oracle test (multi-zone, multi-placement, multi-fixture) + golden test |
| Worst-case zone where every candidate fails validation → still O(N²) | Documented in spec §3.3 as acceptable (no regression vs current behaviour) |
| Sort stability matters? | Use `total_cmp` for `f32` scores; tie-break by `flat` is explicit, not implied by sort stability |
| `commit` extraction introduces a bug | Existing 13 tests + new AC-1 cover commit-side state; oracle test is the safety net |
