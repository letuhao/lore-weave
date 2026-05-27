# Spec — `place_and_connect_object`: score-first, validate-on-demand (DEFERRED #029)

> **Status:** CLARIFY → DESIGN.
> **Track:** `LLM_MMO_RPG` (tilemap-service).
> **Size:** L (default v2.2 human-in-loop; `/review-impl` at POST-REVIEW —
> correctness-critical: must hold the golden test byte-exact).
> **Follows:** 2026-05-20 PM per-modificator timing — `treasure_placer` is
> 973 s of the 993 s continent total (98 %), and the per-placement cost is
> `~O(zone_tiles²)` exactly as the captured lesson predicted.

---

## 1. Problem

[`services/tilemap-service/src/engine/object_manager.rs:102-202`](services/tilemap-service/src/engine/object_manager.rs#L102-L202)
runs **two flood-fill-sized passes per candidate** inside the hot loop:

```rust
for anchor in search_area.iter_set() {                  // O(N) candidates
    if !template.fits(...) { continue; }                // O(1)
    let footprint = ...;                                // O(footprint_size)
    let blocking = ...;                                 // O(footprint_size)

    // (2a) connectivity — flood fill: O(N)
    if would_seal_a_gap(&blocking, &zone_passable) { continue; }
    // (2b) spacing — O(1) lookup
    if state.nearest_object_distance[...] < min_distance { continue; }
    // (2c) access — BFS: O(N)
    let access_path = match find_access_path(...) { ... };

    // (3) score — O(1)
    let score = score_anchor(...);
    if better { best = Some(...) }
}
```

Where `N = zone_tiles`. Total per-placement cost is **O(N²)**: every surviving
candidate pays an O(N) `would_seal_a_gap` (which double-flood-fills the
zone's passable region per call) **plus** an O(N) `find_access_path` BFS.

**Measured continent cost (256², 12 zones, 456 placements, 2026-05-20):**
`treasure_placer = 973.376 s — 98.0 %` of the 993 s pipeline. Every other
placer is sub-20 s.

## 2. Goal

Drop `treasure_placer` to **under 10 s** at 256² (≥ 100× speedup) by
restructuring the per-placement loop. Continent total should fall from ~993 s
to well under 30 s, with the next dominant cost surfacing in
`obstacle_placer`'s 17.9 s (likely no longer the bottleneck after this fix).

### Non-goals

- **Do not** change the placement output. The golden test
  ([`tests/determinism.rs`](services/tilemap-service/tests/determinism.rs)
  `golden_baseline_byte_identical`) must pass with **no rebaseline**.
- **Do not** touch `would_seal_a_gap` or `find_access_path` internals — they
  are correct, the fix is in *how often* they are called.
- **Do not** rewrite the `nearest_object_distance` oracle refresh
  ([object_manager.rs:189-199](services/tilemap-service/src/engine/object_manager.rs#L189-L199))
  in this task — O(map_tiles) per placement = ~30M ops total at 256², a
  second-class concern. Open a separate deferred item if it surfaces as a
  bottleneck after this fix.
- **Do not** address DEFERRED #020 (the §4.3 connectivity pre-filter — skip
  candidates adjacent to ≤1 free region) in this task. It is *complementary*
  and would compound, but a separate cycle.

## 3. Approach — score-first, validate-on-demand

### 3.1 Restructure

```rust
// (A) collect — cheap filters + score, NO flood fills.
let mut survivors: Vec<ScoredCandidate> = Vec::new();
for anchor in search_area.iter_set() {
    if !template.fits(anchor, search_area) { continue; }
    let blocking = template.blocking_footprint_at(anchor, grid).expect(...);
    let footprint = template.footprint_at(anchor, grid).expect(...);

    // Cheap filter — O(1) oracle lookup.
    let flat = anchor.flat_index(width);
    if state.nearest_object_distance[flat] < min_distance { continue; }

    let dist = state.nearest_object_distance[flat];
    let score = score_anchor(optimize, first_placement, anchor, zone_center, dist);
    survivors.push(ScoredCandidate { anchor, flat, footprint, blocking, score });
}

// (B) sort — descending score; ties → ascending flat index. STABLE sort.
survivors.sort_by(|a, b| match b.score.total_cmp(&a.score) {
    Ordering::Equal => a.flat.cmp(&b.flat),
    other => other,
});

// (C) validate-on-demand — walk in best-first order, return the first that
// passes the expensive checks. Identical winner to the current algorithm
// (proof in §4).
for c in survivors {
    if would_seal_a_gap(&c.blocking, &zone_passable) { continue; }
    let access_path = match find_access_path(&zone_passable, &c.footprint, &free_paths, grid) {
        Some(p) => p,
        None => continue,
    };
    // Winner — commit and return.
    return commit(state, c.anchor, c.footprint, c.blocking, access_path, ...);
}
Err(PlacementError::NoSpace)
```

### 3.2 Why this is faster

- **Old**: O(N) candidates × O(N) per validation = O(N²)
- **New**: O(N) score + O(N log N) sort + O(K × N) validation, where K is the
  number of candidates examined until the first valid one. **In typical maps
  K = 1–5** (most candidates pass `would_seal_a_gap` + `find_access_path`).

For N = 5000 (continent-zone median):
- Old: 5000 × 5000 = 25M per-candidate ops per placement.
- New: 5000 (score) + ~60 000 (sort) + K × 5000 (validation, K small).
- Speedup: **~400×** at the per-placement level for typical K=1.

For 456 placements: 973 s → **~2–3 s** target.

### 3.3 Worst-case behaviour

If every candidate fails the expensive checks (an adversarial zone — e.g. a
zone where every blocking footprint would seal a gap), the new algorithm
degrades to O(N) × O(N) = O(N²) — same as the old algorithm. No regression
in the worst case; better in every realistic case.

## 4. Determinism contract — bit-exact equivalence proof

The current algorithm returns `argmax over { valid candidates } of
(score, -flat_index)` — the candidate with the highest score; ties resolved
to the lowest flat index ([object_manager.rs:165-169](services/tilemap-service/src/engine/object_manager.rs#L165-L169)).

The new algorithm sorts survivors by `(score desc, flat asc)`, then returns
the first survivor that passes the expensive validation. Define:

- `S` = set of candidates passing cheap filters (same for both algorithms).
- `V ⊆ S` = subset of `S` that also passes the expensive validation
  (`would_seal_a_gap` ∧ `find_access_path` returns Some). Same set for both.
- The current algorithm returns `argmax_{v ∈ V} (score(v), -flat(v))`.
- The new algorithm sorts `S` by `(score desc, flat asc)` and returns the
  first element of that sorted sequence that is in `V`.

**Claim:** these are the same element.

**Proof:** the first element of `S` sorted by `(score desc, flat asc)` that
is in `V` is, by definition, the element of `V` with the highest score; if
multiple elements of `V` share the top score, it is the one with the
lowest flat index. This is exactly `argmax_{v ∈ V} (score(v), -flat(v))`. □

**Empty `V`**: both algorithms return `Err(NoSpace)`. ✓

**The cheap-filter set `S` is the same** for both algorithms because the
cheap filters (`template.fits`, `nearest_object_distance`) are
side-effect-free and depend only on `(anchor, template, state)` — which the
inner loop does not mutate.

**No side effects between candidates**: the loop body does not mutate
`state` until the commit phase. Both algorithms hit the commit phase
exactly once (or none, for `NoSpace`), with the same `(anchor, footprint,
blocking, access_path)`. Therefore `state` post-commit is bit-identical
including the `nearest_object_distance` oracle refresh.

## 5. Test strategy

### 5.1 Existing tests that must stay green (no rebaseline)

- All 13 `object_manager::tests::*` (the unit tests in object_manager.rs)
- All `TreasurePlacer` tests in
  [`engine/modificators/treasure_placer.rs`](services/tilemap-service/src/engine/modificators/treasure_placer.rs)
- The golden test `golden_baseline_byte_identical` — **the load-bearing
  end-to-end gate.**
- `ac4_same_seed_yields_byte_identical_tilemap`

### 5.2 New tests — bit-exact equivalence at fixture scale

Same pattern as the 2026-05-20 perf fix — keep the old algorithm under
`#[cfg(test)]` as `place_and_connect_object_naive`, and add an oracle test:

- **AC-1** `place_and_connect_matches_naive_on_diverse_zones` — for a panel of
  small zone fixtures (varied size, varied free_paths layout, varied
  `min_distance`), place a sequence of 3–5 objects via both algorithms,
  assert the resulting `(state, placement_result)` pairs are equal after
  each placement.
- **AC-2** `worst_case_zone_with_no_valid_anchor_returns_no_space` — a
  hand-crafted fixture where every candidate fails `would_seal_a_gap` (e.g.
  a thin corridor); both naive and refactored return `NoSpace`.
- **AC-3** `sort_tie_break_prefers_lower_flat_index_after_score_tie` — two
  candidates with score-tied positions in different bucket regions; assert
  the refactored algorithm picks the lower flat index, matching the
  current `< b.flat` rule.

### 5.3 Perf gate (AC-4 — informational, not a CI gate)

Re-run `tilemap-service measure` after the fix. Target: `treasure_placer`
< 10 s at 256². Record before/after in the SESSION entry.

## 6. Acceptance criteria

- **AC-1** `place_and_connect_matches_naive_on_diverse_zones` passes.
- **AC-2** `worst_case_zone_with_no_valid_anchor_returns_no_space` passes.
- **AC-3** `sort_tie_break_prefers_lower_flat_index_after_score_tie` passes.
- **AC-4** `tilemap-service measure` shows `treasure_placer` < 10 s at 256²
  (informational; the algorithmic argument is the gate; AC-4 is the
  evidence). Recorded in the SESSION entry.
- **AC-5** `cargo test --workspace` green; `cargo clippy --workspace
  --all-targets` 0 warnings.
- **AC-6** the golden test (`golden_baseline_byte_identical`) and AC-4
  (`ac4_same_seed_yields_byte_identical_tilemap`) pass with **no
  rebaseline** — the §4 determinism contract is the hard gate.
- **AC-7** DEFERRED #029 moves to "Recently cleared".

## 7. Files touched (estimate)

| Path | Change |
|---|---|
| `services/tilemap-service/src/engine/object_manager.rs` | refactor `place_and_connect_object` to score-first/validate-on-demand; keep `_naive` under `#[cfg(test)]` as the oracle; add `ScoredCandidate` struct |
| `docs/specs/2026-05-21-tilemap-place-and-connect-perf.md` | THIS FILE |
| `docs/plans/2026-05-21-tilemap-place-and-connect-perf.md` | PLAN doc (next phase) |
| `docs/deferred/DEFERRED.md` | clear #029 to "Recently cleared" |
| `docs/measurements/2026-05-18-continent.md` | append the post-fix measurement |
| `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` | new session entry |

6 files. **L.**

## 8. Open questions for PO — RESOLVED

- **Q1** ✅ **Yes — fold in.** AC-4 stands: re-run `measure`, record
  before/after in the SESSION.
- **Q2** ✅ **Keep `find_access_path` local.** Score-first restructure is the
  primary win; per-candidate access-path stays as-is. If it surfaces as the
  next bottleneck after this fix, it gets its own deferred item + cycle.
