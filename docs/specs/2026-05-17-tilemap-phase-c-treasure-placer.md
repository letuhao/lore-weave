# Spec — tilemap-service Phase C: TreasurePlacer

> **Status:** CLARIFY+DESIGN · REVIEW(design) r1-r2 REJECTED → revised · human-in-loop review 2026-05-17 pulled in `inherit_treasure_from` (D9) + persisted placement `value` (D10) · **Size:** XL · **Mode:** AMAW (`/amaw`)
> **Roadmap:** [`docs/plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md`](../plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md) §4 Phase C
> **Source spec:** TMP_006 (Treasure & Objects) — §2 schema, §3 TreasurePlacer,
> §8.5 resolved questions. Builds on Phase A (`place_and_connect_object`,
> `choose_guard`, `OptimizeType`, `TreasureTierSpec`, `nearest_object_distance`)
> and Phase B (the registered modificator pipeline).

## §1 Context & goal

Phase B shipped the first placer — `ObstaclePlacer`. Phase C adds the second:
**`TreasurePlacer`** (TMP_006 §3) — the tiered value-density treasure-pile
generator. After Phase C, a generated tilemap has treasure piles scaled to each
zone's author `treasure_tiers`, high-value piles guarded by a monster lair, every
placement honouring the "never seal a gap" invariant via the Phase-A
`place_and_connect_object`. This is the **second phase to change `place_tilemap`
output** — the AC-9 golden is rebaselined.

The Phase-A `ObjectManager` (`place_and_connect_object`, `choose_guard`) is the
placement engine; Phase C is the *policy* that drives it: build an object value
pool, compose piles per tier, decide guards, call the placer.

## §2 Scope

### In scope (V1+30d)

1. A V1+30d engine **treasure-object value pool** (TMP_006 §3.1) — a small set of
   value-bearing objects with `value` + `rarity` weight, the distribution piles
   are composed from.
2. **Pile composition** (TMP_006 §3.3) — sample objects weighted by rarity,
   value-capped, until the running sum lands in a tier's `[min, max]`;
   emergency-bounded.
3. The **`TreasurePlacer` modificator** (TMP_006 §3.3) — per zone, per tier
   (high-`max` first), compose `target_count` piles and place each.
4. **Pile placement** via the Phase-A `place_and_connect_object` (TMP_006 §3.4 /
   §5.2) — `OptimizeType::BothDistanceAndCenter`, `min_distance` scaled by pile
   value.
5. **Guards** (TMP_006 §3.5) — a pile whose value ≥ `min_guard_value` (engine
   default 2000) gets a `MonsterLair` placed on a footprint-adjacent `Open` tile;
   guard strength = `value / 10` (`choose_guard`, Phase A).
6. `min_distance(value)` value-scaling (TMP_006 §3.4).
7. Determinism (TMP-TR-Q5) — a per-`(zone, "treasure_placer")` ChaCha8 sub-stream.
8. `TreasurePlacer` registered in the `place_tilemap` pipeline, ordered before
   `ObstaclePlacer` (TMP_006 §7).
9. **`ZoneSpec.inherit_treasure_from`** (TMP_006 §3.2 / TMP-TR-Q3) — a zone may
   inherit another zone's `treasure_tiers` (D9). Pulled into Phase C at the
   2026-05-17 human-in-loop review: TMP-TR-Q3 resolved it V1+30d and the A–E
   roadmap has no later home, so deferring it would be silent drift.
10. **Persisted placement `value`** (D10) — `TilemapObjectPlacement` gains an
    additive `value: Option<u32>` carrying the treasure pile's gold value / the
    guard strength, so V2 loot / combat need not re-generate to recover
    generation-time data (the `biome_object_type` precedent).

### Out of scope

| Item | Why |
|---|---|
| Dwellings, Seer Huts, Prisons, Pandora Boxes (TMP_006 §3.1 sources 2/3/4/5) | V2 — the V1+30d pool is "generic chest + scattered gold + cache" only |
| TownPlacer / MinePlacer / Monolith placement (§7 steps 1-3) | V2 / separate placers — Phase C is TreasurePlacer only |
| ConnectionsPlacer connection-guards (§7 step 4) | Phase D |
| RoadPlacer / RiverPlacer (§7 steps 6-7) | Phase E |
| Grail-equivalent special placement (§6) | No V1+30d Grail |
| Zone-config object **filtering** — `banned_object_categories`, `banned_objects`, `required_objects` (§3.2) | A separate object-pool-filtering layer needing its own `ZoneSpec` fields + a filter pass; no §8.5 question makes it V1+30d-mandatory. Tracked as **DEFERRED #023**, target a TMP_004 authoring task (Track 2) — not silent drift. (`inherit_treasure_from`, also §3.2, **is in scope** — D9 — per TMP-TR-Q3.) |
| TMP-TR-Q4 explicit "reduce density 50 % + emit `tilemap.density_reduced` INFO" | The INFO event needs the Phase-2+ progress-event channel (cf. DEFERRED #015/#017). V1+30d: density is a soft target — the bounded loop places what fits; see D6 |
| V2 combat (guard kill → `Occupied`→`Walkable`, §8.5 Q2/Q6) | V2 |
| Landmark / Decoration placement | Not tier-driven; a separate (out-of-scope) mechanism |
| §4.3 connectivity pre-filter optimisation | Already DEFERRED #020 (perf) |

## §3 Design decisions

**D1 — Treasure-object value pool (`engine/treasure_pool.rs`).** New module
mirroring `biome_library.rs`. `TreasureObject { id: &'static str, value: u32,
rarity: u16 }` — a value-bearing object the pile composer draws from; `rarity` is
the weighted-pick weight (higher = picked more often). `engine_treasure_pool() ->
Vec<TreasureObject>` ships a fixed V1+30d set with a deliberate **value spread**
so a pile can be composed across the §2.3-style tier ranges (e.g. scattered gold
≈250, decorative cache ≈750, treasure chest ≈2000, rich hoard ≈5000, …) — sized
so the smallest object is cheaper than a typical tier `min` step and the set
spans low → high. Deterministic — a fixed-order `Vec`, same call ⇒ equal `Vec`.
The pool carries `value` + `rarity` only — **not** a footprint: a V1+30d pile is
placed as a single 1×1 `Treasure` object (D4); the pool is a value/rarity
*distribution*, the multi-object composite is build-internal (TMP-TR-Q1's
"composite pile" is the value sum, not a multi-footprint placement).

**D2 — Pile composition (`compose_pile`).** Per TMP_006 §3.3 inner loop:
`compose_pile(pool, tier, rng) -> Option<TreasurePile>` where `TreasurePile {
value: u32, object_count: u32 }` (build-internal — no placement record yet).
**A tier with `max == 0` is TMP_006 §2's "filler / empty" tier (`{0,0,1}`) —
`compose_pile` returns `None` immediately:** it composes no pile, the caller's
emergency counter absorbs it, so a filler tier is a no-op that places nothing
(its intended effect — never a phantom `Some(value: 0, object_count: 0)`).
Otherwise (`max > 0`) the loop runs **while `(running_sum < tier.min` or
`object_count == 0)` and `attempts < MAX_COMPOSE_ATTEMPTS` (100, TMP_006 §3.3's
explicit attempt cap)** — a non-filler tier always composes ≥ 1 object, even a
`min == 0` tier — calling `sample_weighted_by_rarity(pool, value_cap = tier.max
- running_sum)`, adding the object's `value` and bumping `object_count` **and
`attempts`**; the sampler returns `None` (breaking the loop) when no pool object
fits under `value_cap`. (The attempt cap is belt-and-suspenders — every pool
object has `value > 0`, so `running_sum` strictly increases each iteration and
the loop self-terminates regardless — but D2 keeps §3.3's cap verbatim rather
than silently diverge.) Return `Some(pile)` iff
`object_count ≥ 1` **and** `running_sum ∈ [tier.min, tier.max]`, else `None` (a
failed composition). `value_cap = max - running_sum` makes `running_sum ≤ max`
hold by construction, so a `None` return means the sampler ran dry before
reaching `min`. `sample_weighted_by_rarity` walks the pool in fixed order
accumulating `rarity` weights against one `rng.gen_range` roll over the eligible
(`value ≤ value_cap`) subset — deterministic.

**D3 — `min_distance(value)` (§3.4).** `min_distance(value) = (value as f32 /
100.0).sqrt() + 5.0` — low-value piles may cluster, high-value piles spread.
Pure function.

**D4 — `TreasurePlacer` modificator (`engine/modificators/treasure_placer.rs`).**
A `Modificator`. `name()` = `"treasure_placer"`. `dependencies()` =
`["terrain_painter", "connections_placer"]` — terrain must be painted before
`choose_guard` reads the zone terrain; `connections_placer` is unregistered in
Phase C (D7-tolerated) and orders connection-guards (§7 step 4) before treasures
(step 5) once Phase D lands. `ObstaclePlacer` already declares `treasure_placer`
in its own `dependencies()`, so registering `TreasurePlacer` orders Obstacle fill
(§7 step 8) **after** treasures automatically. `process` iterates zones; a
`Forbidden` zone (all-`Obstacle`, no `Open` area) is skipped; a zone whose
**effective tiers** (D9 — its own `treasure_tiers`, or, when
`inherit_treasure_from` is set, the inherited zone's) are empty contributes
nothing. For each processed zone: sort its
tiers by the **total key `(max desc, min desc, density desc)`** — high-`max`
first (§3.3); the `min`/`density` sub-keys pin a deterministic order for
equal-`max` tiers, so the result never depends on sort stability (TMP-A4) — and
for each tier compose + place `target_count` piles. A pile is placed as a single 1×1 blocking
`Treasure` object via `place_and_connect_object(state, zone_idx,
&treasure_pile_template(), TilemapObjectKind::Treasure, Some(pile.value),
&search_area, min_distance(pile.value), OptimizeType::BothDistanceAndCenter)` where
`search_area = state.zone_area_open(zone_idx)` recomputed fresh before each call
(so already-placed piles/guards are excluded — they are `Occupied`, not `Open`).

**D5 — Guards (§3.5).** After a pile is placed, if `pile.value ≥
MIN_GUARD_VALUE` (engine default 2000) place a guard. The zone terrain comes
from `state.zone_terrain[zone_idx]`, typed `Option<TerrainKind>`. `TreasurePlacer`
declares `terrain_painter` in `dependencies()`, so the registry runs
TerrainPainter first and the value is `Some`; D5 resolves it with
`.expect("TerrainPainter runs before TreasurePlacer (dependency edge)")` — the
**same dependency-guaranteed unwrap `ObstaclePlacer::process` already uses**. A
`None` here is a pipeline-wiring bug, not runtime data, so a panic is the correct
surfacing — never a silent default terrain. Then `choose_guard(terrain,
pile.value / 10)` picks the flavour, and `place_and_connect_object(state,
zone_idx, &guard_template(), TilemapObjectKind::MonsterLair,
Some(guard.strength), &guard_search_area, 0.0, OptimizeType::Center)` places it,
where `guard_search_area` is a **grid-dimensioned** `TileMask` —
`state.zone_area_open(zone_idx)` intersected with the 4-neighbourhood of the
just-placed pile's `footprint`, so it stays grid-sized (matching
`place_and_connect_object`'s `debug_assert_eq!` on `search_area` dimensions)
while restricting candidates to the pile's `Open` neighbours (the guard sits
beside the pile it guards; `min_distance` 0 — the guard *is* meant to be next to
the pile). If `place_and_connect_object` returns `NoSpace` (no non-sealing
adjacent tile), the guard is **skipped** and the pile is unguarded (TMP_006 §5.3
— an unguarded pile is valid). The guard goes through `place_and_connect_object`,
so it cannot itself seal a gap. `MonsterTemplate` (from `choose_guard`) carries
the terrain flavour tag; the placement record is `kind: MonsterLair` with
`value: Some(guard.strength)` (D10) — the monster *flavour* and the combat
payload stay V2.

**D6 — Density target + the §3.3 emergency bound (§3.3 / §4.4 / TMP-TR-Q4).**
Per tier: `target_count = (tier.density as f32 *
zone.assigned_tiles.count_ones() as f32 / 1000.0) as u32`. `density` is "piles
per zone-tile-thousand" (TMP_006 §2); the `as u32` truncation means a zone with
`density × tiles < 1000` truncates to `target_count == 0` for that tier —
**intended** (a sub-thousand-tile-weight zone holds no piles of that tier; the
author raises `density` for treasure in a small zone). The pile loop follows
TMP_006 §3.3: a separate `emergency` counter is incremented **only on a pile
failure** — the iteration's `compose_pile` → `None` (the pool cannot compose
`[min, max]`) **or** the **pile's** `place_and_connect_object` → `NoSpace` (no
non-sealing tile for the pile). A **guard** `place_and_connect_object` →
`NoSpace` is **not** a loop failure: the pile has already placed (`placed`
incremented) and an unguarded pile is valid (D5 / TMP_006 §5.3), so a guard skip
never touches `emergency`. The counter never increments on a successful pile
placement. The loop is `while placed < target_count &&
emergency < target_count`. So a clean zone reaches `placed == target_count`
(successes never consume budget — §3.3); only *failures* are capped, at
`target_count`, after which the loop stops (TMP_006 §4.4 — placement failures
are normal). A failure places nothing — the realized count is a **soft** target.
(Rejected at design-review r1: a *single* counter incremented on every iteration
caps total iterations at `target_count`, so one early failure permanently loses
a pile slot — that contradicts §3.3, where successes never touch the counter.)
The explicit TMP-TR-Q4 "reduce density 50 % + emit a `tilemap.density_reduced`
INFO event" is **out of scope** — the INFO event needs the Phase-2+
progress-event channel; the bounded-loop soft target is the V1+30d behaviour and
is connectivity- and determinism-safe.

**D7 — Determinism; golden rebaselined (TMP-TR-Q5 / TMP-A4).** `TreasurePlacer`
sub-seeds per zone via `seed::sub_seed(seed, "treasure_placer:{zone_id}")` → a
`ChaCha8Rng`; all composition-sampling RNG draws from that per-zone stream, so
*composition* is order-independent. **Placement is not:**
`place_and_connect_object` scores anchors against the **map-wide**
`nearest_object_distance` oracle, which every prior placement in any zone
mutates — so the anchor chosen in one zone depends on what earlier zones placed.
`place_tilemap` is nonetheless deterministic because (a) composition RNG is
per-zone sub-seeded **and** (b) the pipeline processes `state.zones` in a fixed
order, single-threaded; the TMP-A4 axiom holds on that basis, **not** on
placement being order-free. Consequence for the TMP-TR-Q5 / §4.2 future
parallel mode: per-zone parallel placement is **blocked** until
`nearest_object_distance` is made placement-order-insensitive — else the placer
races on the shared oracle and breaks determinism. Phase C **legitimately
changes `place_tilemap` output** — `object_placements` gains `Treasure` +
`MonsterLair` records — so the golden is **rebaselined**: regenerate
`tests/golden/tilemap_baseline.json` once from the reviewed Phase-C engine
(`regenerate_golden_baseline`, the existing `#[ignore]`d tool), keep
`golden_baseline_byte_identical` as the cross-phase drift gate. `ac4_same_seed`
remains the within-build determinism gate (engine run twice, byte-identical).

**D8 — Pipeline registration.** `place_tilemap` registers `TreasurePlacer`
**before** `ObstaclePlacer` (TMP_006 §7: treasures step 5, obstacles step 8).
`TerrainPainter` → `TreasurePlacer` → `ObstaclePlacer`. The `ModificatorRegistry`
Kahn topo-sort already enforces this once both name + dependency edges are
present.

**D9 — `inherit_treasure_from` (additive `ZoneSpec` field; TMP_006 §3.2 /
TMP-TR-Q3).** `ZoneSpec` gains `inherit_treasure_from: Option<ZoneId>` (additive,
`#[serde(default)]` — like `treasure_tiers`). Resolution, computed once per zone
before its tier loop: **one level, non-transitive** — a zone `X` with
`inherit_treasure_from: Some(Y)` takes zone `Y`'s literal `treasure_tiers` as its
**effective tiers**, and `X`'s own `treasure_tiers` is ignored ("inherit" means
"use that zone's"). If `Y` itself declares `inherit_treasure_from`, that is
**not** chased — non-transitive, which also makes an inheritance cycle
structurally impossible. If `Y` is not a zone of the template, `X`'s effective
tiers are **empty** (no treasure): a dangling `inherit_treasure_from` is an
author error that surfaces deterministically as a treasure-less zone — never a
panic, never an aborted `place_tilemap`. **REPLACE, not UNION-with-override.** D9 takes `Y`'s `treasure_tiers` wholesale,
not TMP-TR-Q3's UNION-with-override: that "more-specific zone-level wins" model
is meaningful for the *keyed* `banned_objects` / `required_objects` (a per-key
override), but `treasure_tiers` is an **unkeyed `Vec`** with no per-entry key,
so "inherit" can only mean "use the source's list". A zone declaring **both**
`inherit_treasure_from` and a non-empty own `treasure_tiers` gets the inherited
list — its own tiers are **inert** (a benign authoring contradiction, resolved
deterministically, never an abort). The keyed UNION-with-override is reconciled
when the §3.2 filtering layer lands (DEFERRED #023 records this divergence). A
zone with neither field has no treasure. "Effective tiers" in D4/D6 is this
resolved list.

**D10 — Persisted placement `value` (additive, TMP-A8; human-in-loop review
2026-05-17).** `TilemapObjectPlacement` gains `value: Option<u32>`
(`#[serde(default, skip_serializing_if = "Option::is_none")]` — the
`biome_object_type` pattern). The composed pile gold-value and the guard
strength are **generation-time data**: `compose_pile` / `choose_guard` compute
them, the placer consumes them for spacing/guard decisions, and without
persistence they are discarded — recoverable later only by a full deterministic
re-generation. Phase B set the precedent (`biome_object_type` persisted so Phase
E discovers river sources without re-generating); the treasure `value` / guard
`strength` are the identical pattern, and V2 loot / economy / combat need them.
`value` is the **kind-specific magnitude** — for `kind: Treasure` the pile's
summed gold value, for `kind: MonsterLair` the guard strength, `None` for every
other kind. To thread it into the record `place_and_connect_object` creates,
that Phase-A function gains a `value: Option<u32>` parameter (placed next to
`kind`). Adding the field touches **two distinct site sets**: (i) **callers** of
`place_and_connect_object` get the new param arg — `TreasurePlacer` (new) and
Phase A's `object_manager.rs` tests (mechanical `None`); (ii) **struct-literal**
constructions of `TilemapObjectPlacement` get the new field — the
`place_and_connect_object` body, the `object.rs` test module, **and
`ObstaclePlacer::fill_zone`**, which builds the literal directly (Phase B D6 —
obstacle fill deliberately bypasses `place_and_connect_object`). `TilemapObjectPlacement`
derives no `Default`, so every literal must name `value`; each non-treasure site
gets a mechanical `value: None`, and §5 lists `obstacle_placer.rs` MOD.
No V1+30d consumer reads `value` (loot is V2) — this is deliberate cheap
preservation of generation-time data for the known V2 consumer.

## §4 Acceptance criteria

- **AC-1** — `engine_treasure_pool()` is non-empty, deterministic (same call ⇒
  equal `Vec`); every `TreasureObject` has `value > 0` and `rarity > 0`; the set
  has a real value spread (`min value < max value`), and its cheapest object is
  cheaper than its dearest by a wide margin (so piles can be composed across
  tiers).
- **AC-2** — `compose_pile`: for a non-filler tier (`max > 0`) whose `[min, max]`
  the pool *can* reach, it returns `Some(pile)` with `pile.value ∈ [min, max]`
  and `object_count ≥ 1`; for an unreachable tier (`min` above the total pool
  value, or `max` below the cheapest object) it returns `None` without looping
  unboundedly; for TMP_006 §2's **filler tier (`max == 0`, e.g. `{0,0,1}`)** it
  returns `None` — never a phantom `Some(value: 0, object_count: 0)`. It is
  deterministic for a fixed `(tier, seed)`. `sample_weighted_by_rarity` never
  returns an object whose `value` exceeds the passed cap.
- **AC-3** — `min_distance(value)` is monotonic non-decreasing in `value` and
  `min_distance(0) ≥ 5.0`.
- **AC-4** — guard policy: a pile with `value ≥ 2000` triggers a guard placement
  attempt; a pile with `value < 2000` never does. Guard strength = `value / 10`.
- **AC-5** — `TreasurePlacer` places `Treasure` objects, driven by the §3.3
  loop. Verified at the `TilemapBuildState` level with **hand-built zones of
  pinned tile count** (so `target_count` is exactly known, not `place_zones`'
  variable geometry): (a) a zone whose tier yields `target_count ≥ 2` with an
  ample `Open` area places **exactly** `target_count` `Treasure` objects when no
  composition/placement failure occurs (`emergency` stays 0 → `placed ==
  target_count`) — the clean-zone baseline; D6's corrected bound diverges from
  the rejected per-iteration counter **only on the failure path**, pinned
  separately by (e), not here; (b) a zone with two tiers — **both** with
  `target_count ≥ 1` and a pool-reachable `[min, max]` (so neither is vacuously
  empty) — is consumed high-`max`-first: the higher-`max` tier's piles appear in
  `object_placements` before the lower tier's; (c) a zone with
  `density × tiles < 1000` gets
  `target_count == 0` → **zero** `Treasure` objects (the documented truncation
  boundary); (d) every placed `Treasure` carries `value == Some(v)` (D10), `v`
  the composed pile value, within the tier's `[min, max]`; (e) **failure-path
  coverage — the D6 gate:** a fixture with a tier whose `[min, max]` the pool
  reaches for *some* compositions but not others (the §3.3 loop deterministically
  hits ≥ 1 `compose_pile → None`), `target_count ≥ 3`, and an `Open` area ample
  for `target_count` piles, still places **exactly** `target_count` `Treasure`
  objects. The test independently confirms the failure path ran — it replays
  `compose_pile` over the same tier + sub-seed and asserts ≥ 1 `None` (a
  pure-function check) — so the scenario genuinely exercises the corrected
  emergency bound; the rejected r1 per-iteration counter caps *total* iterations
  at `target_count` and would fall short by the failure count.
- **AC-6** — guards, verified on hand-built pinned-size zones whose **geometry
  guarantees guardability** — a wide all-`Open` zone with the `free_paths`
  skeleton confined to one edge, so a centre-biased pile always has ≥ 1
  non-sealing `Open` tile 4-adjacent to it: (a) a zone with a tier whose
  `min ≥ 2000` (every composed pile ≥ the guard threshold) and `target_count ≥ 1`
  places **exactly as many** `MonsterLair` objects as `Treasure` piles, each
  `MonsterLair` on a tile `neighbors4`-adjacent to a `Treasure` footprint; (b) a
  zone whose only tier has `max < 2000` (no pile can reach the threshold) places
  **zero** `MonsterLair`. Guard strength passed to `choose_guard` is
  `pile.value / 10`, and each placed `MonsterLair` carries `value ==
  Some(strength)` (D10).
- **AC-7** — connectivity end-to-end: after the `TerrainPainter` →
  `TreasurePlacer` → `ObstaclePlacer` pipeline no non-`Forbidden` zone's
  passable region (`Walkable ∪ Open`) has been split — verified at the
  `TilemapBuildState` level with an independent flood-fill (the Phase-B AC-10
  split-OR-eliminate oracle). The fixture is **hand-built** — not `place_zones`'
  per-seed-varying geometry: multi-zone, pinned tile counts, non-`Forbidden`
  zones carrying a `min ≥ 2000` tier with a **wide `[min, max]`** — `max` well
  above the pool's total object value, so `compose_pile` reliably succeeds for
  *every* seed (not the AC-5(e) sometimes-fails shape) — and a `density` giving
  `target_count ≥ 2` (headroom: a stray failure still leaves ≥ 1 guarded pile),
  on the AC-6 guard-placeable geometry (a wide `Open` zone, `free_paths` along
  one edge). So
  the pipeline **deterministically** emits `Treasure` + `MonsterLair`
  placements, and the `object_placements` ≥ 1 `Treasure` **and** ≥ 1
  `MonsterLair` no-op-detector assertions are robust — never a false-RED on
  varying geometry. Run over several seeds (the RNG varies; the geometry is
  pinned). `place_and_connect_object` rejects any gap-sealing anchor, so
  connectivity holds by construction; this test is the regression gate.
- **AC-8** — `place_tilemap` is deterministic — same `(template, seed, grid)` ⇒
  byte-identical `TilemapView` incl. the new `Treasure`/`MonsterLair` placements
  (`ac4_same_seed`, run twice). `object_placements` is non-empty.
- **AC-9** — the golden is rebaselined to Phase C (`tests/golden/tilemap_baseline.json`,
  regenerated from the Phase-C engine); `golden_baseline_byte_identical`
  reproduces it.
- **AC-10** — `inherit_treasure_from` (D9), verified on hand-built pinned-size
  fixtures: (a) a zone `X` declaring `inherit_treasure_from: Some(Y)` **and** a
  non-empty own `treasure_tiers` whose pool-reachable `[min,max]` is **disjoint**
  from `Y`'s — every placed `Treasure` in `X` carries `value` in `Y`'s range and
  **none** in `X`'s own range (this pins REPLACE; a prefer-own or union resolver
  lands piles in `X`'s range and fails); (b) **non-transitivity** — a three-zone
  chain where `X` declares `inherit_treasure_from: Some(Y)`, `Y` declares
  `inherit_treasure_from: Some(Z)`, and `Y` carries a non-empty own
  `treasure_tiers` pool-reachable and **disjoint** from `Z`'s: every placed
  `Treasure` in `X` carries `value` in `Y`'s **own** range and **none** in
  `Z`'s (a transitive-chase resolver lands `X`'s piles in `Z`'s range and
  fails); **plus** an authoring cycle `X → Y → X` — `place_tilemap` terminates
  with a deterministic result and **no panic / no hang** (the cycle-safety D9
  derives from non-transitivity); (c) a dangling `inherit_treasure_from` (no
  such zone in the template) yields **zero** treasure and **no panic**.
- **AC-11** — additive schema round-trips (TMP-A8): `ZoneSpec` with and without
  `inherit_treasure_from`; `TilemapObjectPlacement` with and without `value`;
  pre-Phase-C JSON for both still deserializes (the new fields default).
- **AC-12** — `cargo test --workspace` green; `cargo clippy --workspace
  --all-targets` clean.

## §5 Module design

```
src/
  types/object.rs                            MOD  TilemapObjectPlacement +value (D10)
  types/template.rs                          MOD  ZoneSpec +inherit_treasure_from (D9)
  engine/object_manager.rs                   MOD  place_and_connect_object +value param (D10)
  engine/treasure_pool.rs                    NEW  TreasureObject · engine_treasure_pool()
  engine/treasure_select.rs                  NEW  compose_pile · sample_weighted_by_rarity ·
                                                  min_distance · TreasurePile
  engine/modificators/treasure_placer.rs     NEW  TreasurePlacer — effective-tier resolution
                                                  (D9) + per-tier compose/place/guard +
                                                  treasure_pile_template() / guard_template()
  engine/modificators/obstacle_placer.rs     MOD  +value: None in the fill_zone
                                                  TilemapObjectPlacement literal (D10)
  engine/modificators/mod.rs                 MOD  re-export TreasurePlacer
  engine/mod.rs                              MOD  register TreasurePlacer before ObstaclePlacer
  tests/golden/tilemap_baseline.json         MOD  rebaselined (D7)
  tests/determinism.rs                       MOD  golden regenerated; AC coverage
```

`compose_pile` / `sample_weighted_by_rarity` / `min_distance` are pure +
unit-testable; `TreasurePlacer::process` is integration-tested via a
build-state-level harness. `cargo test --workspace` + `cargo clippy
--all-targets` are the VERIFY gate.
