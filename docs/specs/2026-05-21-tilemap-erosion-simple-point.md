# Spec — `erode_zone`: simple-point pre-filter (obstacle_placer perf)

> **Status:** CLARIFY → DESIGN.
> **Track:** `LLM_MMO_RPG` (tilemap-service).
> **Size:** L (default v2.2 human-in-loop; `/review-impl` at POST-REVIEW —
> correctness-critical: golden byte-exact + `erosion_never_seals_a_gap` is the
> single most safety-critical invariant in the engine).
> **Follows:** 2026-05-21 TreasurePlacer fix. `obstacle_placer` is now the
> dominant placer at **16.96 s = 79 %** of the 21.5 s continent total.

---

## 1. Problem

[`erode_zone`](services/tilemap-service/src/engine/modificators/obstacle_placer.rs#L100-L135)
peels wall-adjacent `Open` tiles to `Obstacle`, each gated by a per-tile
`would_seal_a_gap` flood fill:

```rust
loop {
    for tile in zone_assigned.iter_set() {           // O(N) per pass
        if state.tile_state_at(tile) != Open { continue; }
        if !is_wall_adjacent(...) { continue; }       // O(1)
        blocking.set(tile);
        let seals = would_seal_a_gap(&blocking, &passable);  // O(N) double flood fill!
        blocking.clear(tile);
        if seals { continue; }
        // erode: Open → Obstacle, passable.clear(tile)
    }
    if !blocked_any { break; }
}
```

`would_seal_a_gap` does **two** `label_components` flood fills (passable
before + after) plus a `HashMap` label-mapping pass — O(N) with a high
constant. It is called once per wall-adjacent Open tile, across O(√N)
erosion passes. Total: **O(passes × N × N)**.

**Measured (256² continent, 2026-05-21):** `obstacle_placer = 16.961 s`,
79 % of the 21.541 s total — now the leading cost after the TreasurePlacer fix.

## 2. Key insight — the blocking footprint is always a single tile

`erode_zone` always calls `would_seal_a_gap` with `blocking = {tile}` — one
tile. For a single-tile removal, whether it seals a gap has a purely **local**
characterisation (the *simple-point* test from digital topology):

> Removing a single tile `T` from a 4-connected passable region can **split**
> the region **iff** `T`'s passable cardinal (4-)neighbours form **≥ 2 groups**
> under the relation "linked via a passable diagonal on the 8-ring". It can
> **eliminate** the region iff `T` is the only passable tile.

So:
- **0 passable cardinal neighbours**: `T` is isolated. Removing it drops a
  singleton component — seals **iff** `T` is the whole region.
- **1 passable cardinal neighbour** (a leaf): removing it can never split;
  the region survives ⇒ never seals.
- **≥ 2 passable cardinal neighbours in ONE local group** (a *simple point* —
  e.g. any boundary tile of a solid region): they stay connected via the
  passable ring around `T`, so removal never splits ⇒ never seals.
- **≥ 2 passable cardinal neighbours in ≥ 2 local groups**: removal **might**
  split (the groups could reconnect via a long global path, or not) ⇒ the
  global `would_seal_a_gap` flood fill is still required.

**The local test is a sound conservative pre-filter:** "provably safe" cases
skip the flood fill; "maybe" cases fall through to the unchanged
`would_seal_a_gap`. Output is bit-identical.

### Why this is the right win

During solid-region erosion (the common case), **every** boundary tile is a
simple point — its interior neighbours are all locally linked through passable
diagonals — so the flood fill is skipped. Only genuine 1-wide pinch points
(corridor tiles, where two neighbours are NOT diagonally linked) trigger the
flood fill, and there are few. Cost drops from O(passes × N × floodfill) to
O(passes × N × O(1)) + O(few × floodfill).

## 3. Goal

Drop `obstacle_placer` from ~17 s to **under 3 s** at 256², bringing the
continent total under ~7 s. Output **byte-identical** — the golden test
(`golden_baseline_byte_identical`) and `erosion_never_seals_a_gap` must pass
with no rebaseline.

### Non-goals

- **Do not** modify `would_seal_a_gap` — it is the correctness oracle for the
  "maybe" cases and the property tests.
- **Do not** touch `fill_zone` — at sub-second it is not the bottleneck.
- **Do not** change erosion *semantics* — the eroded set must be identical.

## 4. Determinism / correctness contract — bit-exact equivalence

Define `local_verdict(T, passable, passable_count)`:

```
groups = count of local groups of T's passable cardinal neighbours
         (linked via passable diagonals on the 8-ring)
if groups >= 2:  return would_seal_a_gap({T}, passable)   // unchanged path
if groups == 0:  return passable_count == 1               // elimination only
else (groups==1): return false                            // leaf/simple, safe
```

**Claim:** `local_verdict(T, passable, |passable|) == would_seal_a_gap({T}, passable)`
for every single tile `T ∈ passable`.

**Proof** (the three cheap branches; the `groups ≥ 2` branch is identity):

- **`groups == 0`** (no passable cardinal neighbour): `T` is its own component
  in `passable`. `blocked_after = passable − {T}`. If `|passable| == 1`,
  `blocked_after` is empty ⇒ `would_seal_a_gap` returns `!passable.is_empty()`
  = `true`. Else `blocked_after` non-empty and no *other* component touches `T`
  ⇒ no split ⇒ `false`. So the verdict is `passable_count == 1`. ✓
- **`groups == 1`** (≥ 1 passable cardinal neighbour, all in one local group):
  `T` has ≥ 1 neighbour ⇒ `|passable| ≥ 2` ⇒ `blocked_after` non-empty (no
  elimination). The neighbours stay mutually connected via the passable ring
  around `T` (a path not through `T`), so `T`'s component does not split.
  ⇒ `false`. ✓
- **`groups ≥ 2`**: delegate to the unchanged `would_seal_a_gap`. ✓ (identity)

Because the per-tile verdict is identical and `erode_zone`'s control flow is
otherwise unchanged, the eroded set — hence every downstream `Obstacle` /
`Occupied` state — is byte-identical. The golden test is the end-to-end gate.

**Soundness of the conservative direction** (no false "safe"): a `groups == 1`
verdict relies on the passable ring path existing; that path is *in* the
8-neighbourhood and does not pass through `T`, so it survives `T`'s removal.
A `groups ≥ 2` verdict never claims safe — it always flood-fills. So we can
never erode a tile the original would have refused. ∎

## 5. Approach

Add a private `local_seal_verdict(tile, passable, passable_count, grid) ->
Option<bool>` helper:
- Returns `Some(false)` for `groups ∈ {1}` (and `groups == 0 && count > 1`).
- Returns `Some(true)` for `groups == 0 && count == 1`.
- Returns `None` for `groups ≥ 2` — caller runs `would_seal_a_gap`.

In `erode_zone`, maintain a running `passable_count` (init
`passable.count_ones()`, decrement on each erosion) and replace the
unconditional flood fill:

```rust
let seals = match local_seal_verdict(tile, &passable, passable_count, grid) {
    Some(v) => v,
    None => {
        blocking.set(tile);
        let s = would_seal_a_gap(&blocking, &passable);
        blocking.clear(tile);
        s
    }
};
```

The local-groups computation: read the 8 neighbours via bounds-checked
`passable.get` (off-grid → false), count passable cardinals, then union the
cardinals pairwise where the connecting diagonal is passable (N–E via NE,
E–S via SE, S–W via SW, W–N via NW), and count groups.

## 6. Test strategy

### 6.1 Existing tests that must stay green (no rebaseline)

- All `obstacle_placer::tests::*` — especially `erosion_never_seals_a_gap`
  (200 random zones), `erosion_keeps_a_two_wide_sole_corridor_passable`,
  `erosion_fully_consumes_a_two_wide_dead_end_appendage`,
  `erosion_preserves_a_multi_component_passable_region`.
- The golden test `golden_baseline_byte_identical`.
- `connectivity::tests::*` (would_seal_a_gap unchanged).

### 6.2 New tests

- **AC-1** `local_seal_verdict_matches_would_seal_a_gap_oracle` — for a corpus
  of random 9×9 passable masks, for **every** passable tile `T`, assert
  `local_verdict(T) == would_seal_a_gap({T}, passable)`. This is the
  per-tile bit-exact gate (the core of §4).
- **AC-2** `erode_zone_matches_naive_on_random_zones` — keep `erode_zone_naive`
  (the unconditional-flood-fill version) under `#[cfg(test)]`; run both on
  200 random carved zones; assert identical eroded masks + identical
  post-state.
- **AC-3** `simple_point_unit_cases` — hand fixtures for each branch:
  isolated-single-tile (seal by elimination), leaf stub (safe),
  solid-interior boundary (safe, groups==1), 1-wide corridor bridge
  (groups==2, must flood-fill → seal), T-junction (groups≥2).

### 6.3 Perf gate (AC-4 — informational)

Re-run `tilemap-service measure`. Target: `obstacle_placer < 3 s` at 256².
Record before/after in the SESSION entry.

## 7. Acceptance criteria

- **AC-1** `local_seal_verdict_matches_would_seal_a_gap_oracle` passes for
  every tile of a random-mask corpus.
- **AC-2** `erode_zone_matches_naive_on_random_zones` passes (200 zones).
- **AC-3** `simple_point_unit_cases` passes (each branch).
- **AC-4** `obstacle_placer < 3 s` at 256² (informational; the §4 proof + AC-1
  are the hard gate). Recorded in the SESSION.
- **AC-5** `cargo test --workspace` green; `cargo clippy` 0 warnings.
- **AC-6** golden + `erosion_never_seals_a_gap` pass — **no rebaseline**.
- **AC-7** no new deferred items needed (this clears the obstacle bottleneck);
  if a residual surfaces, log it.

## 8. Files touched (estimate)

| Path | Change |
|---|---|
| `services/tilemap-service/src/engine/modificators/obstacle_placer.rs` | `local_seal_verdict` helper + `erode_zone` pre-filter + `passable_count` tracking; `erode_zone_naive` + AC-1/2/3 under `#[cfg(test)]` |
| `docs/specs/2026-05-21-tilemap-erosion-simple-point.md` | THIS FILE |
| `docs/plans/2026-05-21-tilemap-erosion-simple-point.md` | PLAN |
| `docs/measurements/2026-05-18-continent.md` | post-fix measurement |
| `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` | session entry |
| `docs/deferred/DEFERRED.md` | (only if a residual is logged) |

## 9. Open question for PO

- **Q1** (recommended: **yes**) — re-run `measure` and record before/after
  (AC-4)? ~5 min now (continent is fast post-TreasurePlacer-fix). Yes per the
  measurement-first discipline.
