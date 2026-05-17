# Spec — tilemap-service Phase B: ObstaclePlacer + Biomes

> **Status:** CLARIFY+DESIGN · REVIEW(design) r1-r4 REJECTED, r5 APPROVED_WITH_WARNINGS — 3 WARN folded in 2026-05-17 · **Size:** XL · **Mode:** AMAW (`/amaw`)
> **Roadmap:** [`docs/plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md`](../plans/2026-05-17-tmp-005-006-007-modificator-roadmap.md) §4 Phase B
> **Source spec:** TMP_005 (Biome & Obstacles) — §2 schema, §4 ObstaclePlacer,
> §6 biome library, §9 resolved questions. Builds on Phase A (`would_seal_a_gap`,
> `TilemapObjectTemplate`, `TilemapBuildState`).

## §1 Context & goal

Phase A shipped the foundation; `place_tilemap` still produces no objects.
Phase B adds the **first real placer** — `ObstaclePlacer` (TMP_005 §4) — and the
**biome system** it selects from. After Phase B, a generated tilemap has
mountains, trees, rocks, etc. filling each zone's blocked area, every placement
honouring the "never seal a gap" invariant. This is the first phase that
**changes `place_tilemap` output** — the AC-9 golden snapshot is regenerated.

## §2 Scope

### In scope (V1+30d)

1. The TMP_005 §2 biome type family (`BiomeSet`, `BiomeObjectType`,
   `BiomeSelectionRules`, …).
2. A V1+30d engine biome library (TMP_005 §6) + the §2.3 engine-default
   selection rules.
3. The §4.1 biome-selection algorithm (filter → group → priority-ordered rules).
4. The `ObstaclePlacer` modificator — §4.2 area model, §4.3 strip-loose-appendages
   erosion, §4.4 largest-first fill.
5. §4.5 river source/sink discoverability — placed Mountain/Lake obstacles carry
   their `BiomeObjectType` so Phase E's RiverPlacer can find them.
6. Additive schema: `TilemapObjectKind::Obstacle`,
   `TilemapObjectPlacement.biome_object_type`, `ZoneSpec.biome_selection_rules`.

### Out of scope

| Item | Why |
|---|---|
| 15 % decoration variant (TMP_005 §3.2) | Cosmetic; needs a `terrain_layer` value-space extension; not load-bearing — deferred |
| Faction-scoped + alignment-scoped biome filtering (§2.4) | V1+30d zones have no faction/alignment; the schema fields exist but the V1 library leaves them empty (filter: empty ⇒ all pass) |
| Underground biomes / `BiomeLevel::Underground` | V3 — V1+30d is all `Surface` |
| Seasonal / LLM-generated biomes (§9 Q1/Q2) | V2+/V3 |
| `Forge:EditBiome` author overrides | V2+ |
| TreasurePlacer / ConnectionsPlacer / Road / River | Phases C–E |

## §3 Design decisions

**D1 — Biome type family (`types/biome.rs`).** New module:
`BiomeId(String)`; `BiomeObjectType` (9-variant closed enum — `Mountain`,
`Tree`, `Lake`, `Crater`, `Rock`, `Plant`, `Structure`, `Animal`, `Other`);
`BiomeLevel` (`Surface` / `Underground` / `Both`); `Alignment` (`Good` /
`Neutral` / `Evil`); `BiomeSet { biome_id, terrain_types: BTreeSet<TerrainKind>,
level: BiomeLevel, factions: BTreeSet<String>, alignments: BTreeSet<Alignment>,
object_type: BiomeObjectType, templates: Vec<TilemapObjectTemplate> }`;
`BiomeSelectionRules { use_engine_default: bool, rules: Vec<BiomeSelectionRule> }`;
`BiomeSelectionRule { object_type, count_min: u8, count_max: u8, xor_with:
Option<BiomeObjectType>, priority: BiomePriority }`; `BiomePriority` (`First` /
`Normal` / `Last`); `BiomeSelection` — the per-zone result, `BiomeId`s grouped by
`BiomeObjectType`. `BTreeSet` (not `HashSet`) for deterministic iteration
(TMP-A4).

**D2 — Engine biome library (`engine/biome_library.rs`).** `engine_biome_library()
-> Vec<BiomeSet>` — a V1+30d-locked, **representative** library covering the 8
surface terrains (`Grass`, `Forest`, `Mountain`, `Water`, `Sand`, `Snow`,
`Swamp`, `Rough`). Per the TMP_005 §6 table, each terrain gets the
`BiomeObjectType`s its default rules need (≥ `Mountain`, `Tree`, `Rock`,
`Plant`; `Lake`/`Crater`/`Structure`/`Animal`/`Other` where the §6 table lists
them — note §6's `Water` row has **no `Tree`**). Each `BiomeSet` ships **4–6**
`TilemapObjectTemplate`s — the compact end of TMP_005 §2.1's 4–10 range — with
rectangular all-blocking footprints sized per §2.1 (Mountain 4–9, Tree 2–6, Lake
4–9, Rock 1–3, Plant 1–2, Structure 1–4, Animal 1–2, Other 1). The library is a
faithful-but-compact realization of §6 — not 30 lavishly-detailed sets.
`engine_default_biome_selection_rules() -> Vec<BiomeSelectionRule>` ships the
§2.3 nine rules verbatim.

**D3 — Biome selection (§4.1).** Per zone: filter `engine_biome_library()` by
`terrain_types.contains(zone terrain)` **and** `level == Both || level ==
Surface` (V1+30d all-Surface); `factions`/`alignments` filters are no-ops in
V1+30d (the library leaves both empty ⇒ all pass — §2). Group survivors by
`object_type`. Apply the zone's `BiomeSelectionRules` (its
`biome_selection_rules` if `Some` and `!use_engine_default`, else the engine
defaults) in `priority` order (`First` → `Normal` → `Last`): per rule, pick
`random.range(count_min..=count_max)` biomes of `object_type`; honour `xor_with`
with **one decision per `{type, xor_with}` pair** — not a coin per rule. The
first rule of a mutually-`xor` pair makes the decision and records it; the
mirror rule reads the record instead of rolling again. The decision is **two
50/50 coins**: coin 1 decides feature-or-not (so the `xor` pair behaves as one
optional `First`-frame slot at ≈50 %, matching §4.1's per-optional-rule intent);
on "feature", coin 2 picks `this-type` vs `other-type`. Hence `P(neither) = 0.5`,
`P(this) = P(other) = 0.25` — never both. These are the **xor-decision**
probabilities (which type the pair resolves to), not the rate of a biome
appearing: the chosen type's rule then draws `count ∈ [count_min, count_max]`
independently, so with the §2.3 defaults (`Lake`/`Crater` `count 0–1`) the
*realized* rate of a water-feature biome appearing is ≈0.25 per type (`P(no
water feature) ≈ 0.75`). The two-coin model's job is to stop the
double-suppression over-delivery below — not to set the realized count. (TMP_005 §2.3 ships *both* `Lake xor
Crater` and `Crater xor Lake`; the §4.1 per-rule coin would suppress twice —
`P(neither) = 0.25` — over-delivering water features. The one-decision model
fixes that.) Deterministic — a per-`(zone, "obstacle_placer:biome_select")`
ChaCha8 sub-stream. **§9 TMP-BIOME-Q3 fallback:** if a needed `object_type` has zero
matching biomes, fall back to *all* library templates of that type; the result
is still produced.

**D4 — `ObstaclePlacer` modificator (`engine/modificators/obstacle_placer.rs`).**
A `Modificator` registered in `place_tilemap`'s pipeline. `dependencies()`
declares `terrain_painter`, `treasure_placer`, `road_placer`, `connections_placer`
— the latter three are unregistered in Phase B and D7-tolerated, so ObstaclePlacer
sorts last once they land (TMP_006 §7 pipeline order). TMP_003 §3.2 also lists
`DEPENDENCY(ObjectManager)`; that is **structurally satisfied without an edge** —
Phase A D3 made `ObjectManager` a *service module*, not a registered pass, so
there is no `object_manager` modificator to order against, and depending on the
placer names above already orders ObstaclePlacer after every
ObjectManager-placed object. Its `process` iterates zones; for each
non-`Forbidden` zone it runs D3 selection, then D5 erosion, then D6 fill.
`Forbidden` zones (all-`Obstacle`, no `free_paths`) are skipped — nothing to
fill. `Sea` zones are processed (TMP_005 §6 ships Water-terrain biomes).

**D5 — Strip-loose-appendages erosion (§4.3).** Iterative passes: within a pass,
scan the zone's `Open` tiles in flat-index order; mark a tile `Obstacle` when it
is 4-adjacent to a **wall** **and** blocking it does not seal a gap. A neighbour
counts as wall if it is **not a member of this zone's `assigned_tiles`** (off-map
*or* a tile of a neighbouring zone — this gives TMP_005 §4.3's "zone-boundary
fade", which a bare off-map check misses) **or** it is an `Obstacle` /
`Occupied` tile. The seal check is Phase A's
`would_seal_a_gap(single-tile blocking mask, zone passable mask)`, where
`passable` is `Walkable ∪ Open`. **Why the passable mask, not the `Walkable`
skeleton:** erosion only ever removes `Open` tiles, so it can never disconnect a
`Walkable` tile — a Walkable-only gate would be *vacuous* (it would permit
eroding a chokepoint that orphans an `Open` courtyard). The hazard erosion must
avoid is stranding an `Open` region, which is exactly `would_seal_a_gap` on
`Walkable ∪ Open`. The check is **not** a component-count delta (a count delta
misses split-while-eliminating; lesson 9ba274f5) and is evaluated
**sequentially** — each candidate is tested against the passable mask *as
updated by every earlier tile blocked in the same pass*, never a
batch-collect-then-apply (two tiles each individually safe can jointly sever a
2-wide corridor; TMP_005 §4.3's batch pseudocode and its "no harm" claim are
unsound here). **A loose appendage is absorbed tip-first across passes:** the
gate refuses an inner appendage tile while it still strands its outer
neighbour, but the outer (more border-ward) tile erodes first, and the next
pass — now seeing that new `Obstacle` — erodes the inner tile. Repeat passes
until one blocks nothing (fixed point). Deterministic — flat-index scan per
pass.

**D6 — Largest-first fill (§4.4) — a deliberate distinct placement path.**
Obstacle fill does **not** go through `ObjectManager::place_and_connect_object`:
that primitive is for treasure / connection objects, which need an *access path*
to `free_paths` and distance/centre *scoring*. An obstacle is a **wall** — it
needs neither, and an obstacle with no access path is correct (you do not walk
to a mountain). So ObstaclePlacer has its own fill loop. Algorithm: collect
every `TilemapObjectTemplate` from the zone's selected biomes; sort by footprint
`area()` descending (ties → a stable key: biome-id then template name). For each
template, scan the zone's `Obstacle`-state tiles in flat-index order; place at
the first anchor where the footprint fits **entirely within the zone's
`Obstacle` region** (`TilemapObjectTemplate::fits` against the `Obstacle` mask).
On placement: mark the footprint `Occupied`, push a `TilemapObjectPlacement {
kind: Obstacle, anchor, biome_object_type: Some(type), canon_ref: None }`.
**D6 makes no `would_seal_a_gap` call** — and that is correct, not an omission.
The footprint lies entirely on `Obstacle` tiles, which are already non-passable
(`TileState` is a partition — `Obstacle` ∉ `Walkable ∪ Open`); marking them
`Occupied` removes no passable tile and can disconnect nothing, so the check
would be provable dead code. ObstaclePlacer's one connectivity-critical step is
**D5 erosion** (`Open` → `Obstacle` genuinely removes passable tiles) — D5's
`would_seal_a_gap` gate is the live one. Remaining `Obstacle` tiles stay pure
`Obstacle` (engine renders generic impassable terrain). Deterministic —
flat-index scan, no RNG in the fill itself.

**D7 — Obstacle object schema (additive, TMP-A8).** `TilemapObjectKind` gains an
`Obstacle` variant. `TilemapObjectPlacement` gains
`biome_object_type: Option<BiomeObjectType>` (`#[serde(default)]`) — `Some` for
obstacle placements, `None` for all others. This lets Phase E's RiverPlacer
*find* the Mountain (river-source) and Lake (river-sink) obstacles by scanning
`object_placements` for `biome_object_type == Some(Mountain)` / `Some(Lake)` —
no separate registry. **Scope note:** the placement record carries the
obstacle's `anchor`, not its footprint extent; TMP_005 §4.5 passes a placed
object's *area* to RiverPlacer. Whether Phase E's V1+30d RiverPlacer needs the
full footprint or the `anchor` representative point suffices is a Phase-E
decision — if it needs the extent, adding a footprint/template reference to
`TilemapObjectPlacement` is an additive Phase-E change. Logged as a Deferred
item; Phase B's contract is only the `biome_object_type` tag.

**D8 — `ZoneSpec.biome_selection_rules`.** Additive `#[serde(default)]` field
`biome_selection_rules: Option<BiomeSelectionRules>` (deferred from Phase A D8).
`None` ⇒ engine defaults.

**D9 — Determinism; the golden is rebaselined to Phase B.** ObstaclePlacer
sub-seeds via `blake3(seed ‖ zone_id ‖ "obstacle_placer:…")` (`seed::sub_seed`).
Phase B **legitimately changes `place_tilemap` output** — `object_placements` is
no longer empty, so the Phase-A golden can no longer be reproduced. Phase B
**rebaselines** it (it does not delete it): `git mv
tests/golden/phase_a_baseline.json tests/golden/tilemap_baseline.json` (a
phase-neutral name), regenerate the content **once** from the reviewed Phase-B
engine, and keep a `golden_baseline_byte_identical` test asserting the engine
reproduces it. This is **not** the r1 tautology trap: the golden is a *frozen
committed artifact*. Within Phase B the test is trivially green (expected —
Phase B captured it); its value is for Phases C-E — a later phase that changes
obstacle output must **deliberately** rebaseline it (a reviewed commit), and a
phase that changes it *unintentionally* trips the test. The separate
within-build determinism gate is `ac4_same_seed_yields_byte_identical_tilemap`
(run the engine twice, assert byte-identical — never tautological, now also
exercising a non-empty `object_placements`). The `#[ignore]`d
`regenerate_golden_baseline` is kept as the deliberate-rebaseline tool.

## §4 Acceptance criteria

- **AC-1** — `engine_biome_library()` is non-empty; every `BiomeSet` has 4–10
  templates (TMP_005 §2.1; the V1+30d library uses the compact 4–6 end), a
  non-empty `terrain_types`, `level` ∈ {`Surface`, `Both`}. Coverage: every
  **land** terrain (`Grass`, `Forest`, `Mountain`, `Sand`, `Snow`, `Swamp`,
  `Rough`) has ≥1 `Mountain`, `Tree`, `Rock`, `Plant`, **and `Crater`** biome;
  `Water` has ≥1 `Mountain`, `Rock`, and `Plant` biome but **no `Tree`** and
  **no `Crater`** (TMP_005 §6's Water row lists those cells as "(none)" — a
  `Sea` zone's mandatory `Tree` rule and its `Crater` xor-half take the §9 Q3
  fallback). `Crater` must be stocked for every land terrain — though a
  less-common feature — because the §2.3 `Lake xor Crater` pair needs a real
  `Crater` biome: an unstocked `Crater` makes a "Crater" two-coin outcome dead,
  collapsing D3's ≈50 % water-feature slot to ≈25 %. Deterministic (same call ⇒
  equal `Vec`).
- **AC-2** — `engine_default_biome_selection_rules()` returns the §2.3 nine
  rules with the documented counts/priorities/xor.
- **AC-3** — biome selection filters correctly: a zone of terrain T selects only
  biomes whose `terrain_types` contains T; rule priority order is `First` →
  `Normal` → `Last`; counts land in `[count_min, count_max]`; deterministic for
  a fixed `(zone, seed)`. The `xor_with` pair: over many seeded zones all three
  of `this-only` / `other-only` / `neither` occur, both paired types are
  **never** selected together, and the **xor-decision** rates track D3's pinned
  two-coin model (`neither` ≈ 0.5, `this`/`other` ≈ 0.25 each — distinct from
  the buggy double-suppression's 0.25 `neither`), verified with `count` pinned
  to `1..=1` so the decision is observable. A separate check exercises the
  §2.3-default rules (`count 0–1`) and asserts the *realized* water-feature rate
  (`neither` ≈ 0.75) on the production library.
- **AC-4** — the §9 Q3 fallback: a zone whose terrain has no matching biome of a
  needed type still yields a `BiomeSelection` (all-templates-of-type fallback),
  no panic.
- **AC-5** — D5 erosion only ever turns `Open` → `Obstacle`; it terminates (a
  pass eventually blocks nothing). **Result invariant:** erosion never strands
  an `Open` region. Verified with the **split-OR-eliminate oracle, not a
  component count** — let `eroded` be every tile erosion turned `Open` →
  `Obstacle` across all passes; `would_seal_a_gap(eroded, pre_erosion_passable)`
  must be `false`. (A `connected_components` count delta is the wrong oracle: it
  misses split-while-eliminating — splitting one component while eliminating
  another leaves the count unchanged; lesson 9ba274f5.) A property test over
  random zones asserts this against an independent all-pairs reachability
  oracle, including (a) a 2-wide edge corridor that is the **sole** passable link
  between two regions — must erode to a 1-wide link, never sealed; (b) a 2-wide
  dead-end appendage — must erode away fully; and (c) a zone whose pre-erosion
  passable region is **multi-component** (two `Open` pockets split by a wall
  band) — `would_seal_a_gap(eroded, pre)` must stay `false`, the
  split-while-eliminating case a count oracle misses. An assertion on the
  `Walkable` skeleton alone would be vacuous — erosion never removes a `Walkable`
  tile.
- **AC-6** — D6 fill: every placed obstacle's footprint lies **entirely within**
  the zone's `Obstacle` region (no footprint tile overlaps `Open` / `Walkable` /
  `Occupied`); obstacles are placed largest-first (a placed object's footprint
  `area()` ≥ every later-placed object's); each placement is `kind: Obstacle`
  with `biome_object_type: Some(_)`. (D6 makes no `would_seal_a_gap` call by
  design — an all-`Obstacle` footprint cannot disconnect the passable region;
  the connectivity gate is D5 erosion / AC-5.)
- **AC-7** — placed obstacles are `TilemapObjectPlacement { kind: Obstacle,
  biome_object_type: Some(_) }`; a `Mountain`-object-type biome yields
  `Some(Mountain)`, a `Lake` biome `Some(Lake)`. A scan of `object_placements`
  for `Some(Mountain)` / `Some(Lake)` finds the river source/sink obstacles —
  the Phase-E discovery tag (D7).
- **AC-8** — additive schema round-trips: `TilemapObjectPlacement` with/without
  `biome_object_type`, `ZoneSpec` with/without `biome_selection_rules`; existing
  fixtures still deserialize.
- **AC-9** — `place_tilemap` is deterministic — same `(template, seed, grid)` ⇒
  byte-identical `TilemapView` including `object_placements`, verified by
  `ac4_same_seed_yields_byte_identical_tilemap` (run twice; struct-equal **and**
  serialize-equal). `object_placements` is **non-empty** for a fixture with
  fillable zone area. The golden is rebaselined to Phase B —
  `tests/golden/tilemap_baseline.json`, regenerated from the Phase-B engine,
  `golden_baseline_byte_identical` asserting reproduction (D9).
- **AC-10** — connectivity end-to-end: for a multi-zone fixture, after the
  `place_tilemap` modificator pipeline no zone's passable region (`Walkable ∪
  Open`) has been **split** — verified with the **split-OR-eliminate oracle**
  (`would_seal_a_gap`, or an independent all-pairs reachability flood-fill),
  **not** a `connected_components` count delta (which misses
  split-while-eliminating). The test drives the pipeline at the
  `TilemapBuildState` level: `place_tilemap`'s `TilemapView` return drops the
  build-internal `TileState`, so the post-pipeline passable region is
  observable only on the build state. Eroding an *already-isolated* `Open`
  pocket away entirely is permitted (it strands nothing — `would_seal_a_gap`
  agrees); the gate is that no passable component is split and no non-Forbidden
  zone is sealed whole. ObstaclePlacer's only passable-removing step is D5
  erosion (gated by AC-5); the `Walkable` skeleton is untouched by Phase B —
  and the *same correct oracle* is reused, live, by TreasurePlacer in Phase C.
- **AC-11** — `cargo test --workspace` green; `cargo clippy --workspace` clean.

## §5 Module design

```
src/
  types/biome.rs            NEW  BiomeSet · BiomeObjectType · BiomeLevel ·
                                 Alignment · BiomeSelectionRules · BiomeSelection
  types/object.rs           MOD  TilemapObjectKind +Obstacle ·
                                 TilemapObjectPlacement +biome_object_type
  types/template.rs         MOD  ZoneSpec +biome_selection_rules
  types/mod.rs              MOD  re-exports
  engine/biome_library.rs   NEW  engine_biome_library() ·
                                 engine_default_biome_selection_rules()
  engine/biome_select.rs    NEW  select_biomes(zone, terrain, rules, seed)
  engine/modificators/obstacle_placer.rs  NEW  ObstaclePlacer (erosion + fill)
  engine/modificators/mod.rs              MOD  re-export ObstaclePlacer
  engine/mod.rs             MOD  register ObstaclePlacer in place_tilemap
  tests/golden/phase_a_baseline.json      MOV  → tests/golden/tilemap_baseline.json, content rebaselined (D9)
  tests/determinism.rs      MOD  golden test → golden_baseline_byte_identical; regenerator kept (D9)
```

Property-style tests for erosion + fill (random zones, invariant assertions).
`cargo test --workspace` + `cargo clippy` are the VERIFY gate.
