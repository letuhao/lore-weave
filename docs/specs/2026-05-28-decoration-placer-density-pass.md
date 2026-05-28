# DecorationPlacer — visual density pass for zone-map quality (ADR)

> **Branch:** `mmo-rpg/zone-map-quality-spec` (CLARIFY/DESIGN only — no code yet)
> **Builds on:** V2 data model [`2026-05-26-data-model-v2-registry-footprint.md`](2026-05-26-data-model-v2-registry-footprint.md) (`primitive: Decoration` already defined in `ObjectPrimitive` enum; `min_spacing` already a registry field).
> **Status:** ACCEPTED 2026-05-28 — PO locked Q1–Q3 same session
> **Sizing estimate:** M implementation across 4 chunks (~1-2 sessions)

## 1. Driver — concrete UX observation

PO 2026-05-28: "demo bạn gửi cho tôi thì bản đồ trống trơn, thiếu 1 đống tính năng" (the demo I sent had an empty map, missing tons of features). VCMI HoMM3 comparison confirms the gap: our `tilemap-service` ships 5/18 of VCMI's RMG modificators, ~9 object kinds vs HoMM3's 40+. The walkable interior of every zone today is **visually empty** — paths and a handful of treasure/mine/obstacle anchors against an unbroken terrain tile field.

Driver validated against `feedback_validate_adr_driver_before_drafting`:
- ✅ Concrete user flow: re-render the existing demo, count objects, measure visual density
- ✅ Stable surface: `services/tilemap-service` is on main, V2 registry stable, modificator pattern well-established
- ✅ No moving target: existing placers are not being refactored

## 2. Goals & non-goals

**Goal:** Add a single new modificator (`decoration_placer.rs`) that fills the walkable OPEN region of each zone with cosmetic `primitive: Decoration` objects at a biome-driven density target. Walkability is preserved; pathfinding unaffected; existing determinism golden remains byte-identical for templates that don't opt in.

**Non-goals (separate quality-push themes; do not bundle):**
- ❌ Value-band treasure refactor (HoMM3 `CTreasureInfo { min, max, density }` model) — separate ADR.
- ❌ Per-resource type splits (gold/wood/ore/gems/crystal/mercury/sulfur) — separate ADR.
- ❌ `TerrainPainter`-style biome-driven road/river styling — separate ADR (frontend-heavy).
- ❌ Monster guards on high-value treasure — separate ADR.
- ❌ Towns / heroes / artifacts / scrolls / seer huts — separate ADR per category.
- ❌ V3 placement engine refactor — that branch (`mmo-rpg/zone-map-v3-spec`) is paused; this is independent quality work.

This ADR is deliberately **narrow**: one new placer, one new template field, one new registry section. Nothing else moves.

## 3. Why "density first" — VCMI mechanism diagnosed

VCMI's visual richness comes from two places:
1. **`ObstaclePlacer::process()`** — iteratively blocks tiles adjacent to already-blocked tiles (so long as it doesn't seal a passage), then `createObstacles()` populates the blocked region with biome-filtered obstacle objects. Result: 50-70% of non-path interior fills with thematic obstacles (trees, rocks, bushes).
2. **`ObstacleSetFilter`** — picks obstacle templates matching `(terrainType, mapLevel, factionId, alignment)`. Result: snow zones use snow obstacles, lava zones use lava obstacles.

Our `obstacle_placer.rs` already runs but it only fills the OBSTACLE region (areas already marked non-passable; rivers/mountains). The OPEN region (walkable interior minus paths) is untouched.

The fix is NOT to refactor our `obstacle_placer` (risk of breaking river/path invariants). The fix is to **add a parallel placer** that fills the OPEN region with walkable decorations (`primitive: Decoration`, `walkability_pattern: all_walkable`). This is structurally additive — no existing region is mutated, no determinism golden is touched for templates that don't opt in.

## 4. Architecture

### 4.1 New module — `services/tilemap-service/src/engine/modificators/decoration_placer.rs`

```rust
//! TMP-Q1 §3 — DecorationPlacer. Fills the walkable OPEN region of each
//! zone with cosmetic `primitive: Decoration` objects to address the
//! "visually empty" map gap diagnosed in the quality push ADR.
//!
//! Pure additive: walkability_pattern: all_walkable means pathfinding
//! is unaffected. Opt-in via `TilemapTemplate.decoration_density`;
//! `None` = no decorations placed = byte-identical to V2 golden.

pub struct DecorationPlacer;

impl Modificator for DecorationPlacer {
    fn process(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        let Some(density) = ctx.template.decoration_density else {
            return Ok(()); // V2 backward-compat: opt-in only
        };

        for zone_idx in 0..ctx.state.zones().len() {
            let open = ctx.state.zone_area_open(zone_idx);
            let free = subtract_other_placers(open, ctx); // see §4.2
            let target_count = density.target_for(zone_idx, &free, ctx);
            let pool = ctx.registry.decorations_for_biome(zone.terrain_type);
            place_decorations(zone_idx, &free, target_count, &pool, ctx);
        }
        Ok(())
    }
}
```

### 4.2 Pipeline position — runs LAST

DecorationPlacer is the final modificator. Subtracts from the OPEN region:
- treasure_placer placements (pile + guard anchors)
- road_placer waypoints
- river_placer waypoints + crossings
- obstacle_placer (already fills OBSTACLE region, so no overlap — but defensive)
- mine/town anchors
- zone center
- child cell anchors (CSC_001 drill-down references)

Result: a "remaining free walkable" mask. Decorations land only here.

### 4.3 Per-tile placement (per Q3 (c) per-tag min_spacing)

Algorithm:
1. RNG: per-zone-derived ChaCha8Rng (`seed = blake3(template.seed || b"decoration" || zone_id)[..8]`) — deterministic, independent across zones (so adding/removing a zone doesn't shift placement in unrelated zones).
2. Iterate `target_count` placements:
   - Roll a decoration tag from the biome's pool, weighted by `density_weight`.
   - Roll a candidate tile from the remaining-free mask.
   - Check the tag's `min_spacing` (Chebyshev distance): is there an already-placed decoration with the same tag within `min_spacing` tiles? If yes, reject this candidate, retry up to N times.
   - On accept: place the decoration; update the tag's per-tag placed-anchors set.
3. After exhausting retries on a tag (e.g. dense map can't fit more), fall back to lower-min_spacing tags from the biome pool. Continue until target_count reached or biome pool exhausted.

**Per-tag spacing semantics (Q3 (c)):** min_spacing is **per-tag, not cross-tag**. A `flower_patch` (min_spacing=0) can sit next to a `broken_cart` (min_spacing=8), but two broken_carts cannot be within 8 tiles of each other. Cross-tag spacing would over-constrain placement and cause target_count under-shoot on small zones.

**Default min_spacing values per tag** (proposed, registry-tunable):
- Clustered (min_spacing=0): mushroom_cluster, flower_patch, fern, tall_grass, bone_pile
- Close (min_spacing=2): small_rock, weed, fungus_patch
- Spread (min_spacing=4): bush, dead_tree, log_pile
- Rare (min_spacing=8): broken_cart, signpost, ruins_stone, crystal_shard

Per-decoration biome filter: registry-declared `biomes: Vec<String>` on each `lw:decoration.*` tag. Zone's `terrain_type` must be in the decoration's `biomes` list.

## 5. Density model

New `TilemapTemplate` field (additive):

```rust
pub struct TilemapTemplate {
    // ... existing fields
    pub decoration_density: Option<DecorationDensity>, // None = V2 behavior
}

pub struct DecorationDensity {
    pub min_per_zone: u32,    // floor for any zone
    pub max_per_zone: u32,    // ceiling
    pub fraction_of_free: f32, // 0.0..=1.0 fraction of remaining-free mask
}

impl DecorationDensity {
    /// target = clamp(round(fraction * free.count()), min, max)
    pub fn target_for(&self, free: &TileMask) -> u32 { /* … */ }
}
```

**Default DecorationDensity per channel tier** (proposed; PO-tunable in D2):

| Tier | min | max | fraction | Rationale |
|---|---|---|---|---|
| Town (64²) | 20 | 40 | 0.10 | Small zone, decoration shouldn't dominate |
| District (128²) | 50 | 90 | 0.08 | Medium zone, more room |
| Country (192²) | 100 | 200 | 0.06 | Large, but density slightly diluted to avoid clutter |
| Continent (256²) | 200 | 500 | 0.04 | Largest, lowest fraction; raw count peaks |

Per-tier defaults live in `services/tilemap-service/src/types/template.rs` constants; templates override per zone if needed.

## 6. Registry additions (per Q2 (b) — ~30 tags across all 10 V2 biomes)

New `default.toml` section (additive — does not touch existing 28 entries). PO locked Q2=(b): ~30 decoration tags spanning **all 10 V2 terrain biomes** (`lw:grass`, `lw:forest`, `lw:water`, `lw:road`, `lw:hill`, `lw:mountain`, `lw:swamp`, `lw:desert`, `lw:snow`, `lw:subterranean`).

**Distribution: ~3 tags per biome, with cross-biome shared tags counted once.** Total target: 28-32 tags.

Per-biome tag inventory (proposed; tunable in chunk B):

| Biome | Decoration tags (min_spacing class) |
|---|---|
| `lw:grass` (plain) | flower_patch (cluster), tall_grass (cluster), small_rock (close), signpost (rare) |
| `lw:forest` | mushroom_cluster (cluster), fern (cluster), dead_tree (spread), log_pile (spread) |
| `lw:hill` | small_rock (close), weathered_rock (spread), bush (spread), broken_cart (rare) |
| `lw:mountain` | weathered_rock (spread), boulder (spread), bones (cluster), abandoned_pickaxe (rare) |
| `lw:swamp` | fungus_patch (close), bog_pool (spread), dead_tree (spread), bone_pile (cluster) |
| `lw:desert` | weathered_rock (spread), cactus (spread), bleached_bones (cluster), oasis_rocks (rare) |
| `lw:snow` | snowdrift (cluster), pine_branch (close), frozen_log (spread), ice_shard (close) |
| `lw:water` | reed_patch (cluster — only walkable shallows; placed only on coast-adjacent water tiles) |
| `lw:subterranean` | crystal_shard (close), fungus_patch (close), bone_pile (cluster), ruins_stone (rare) |
| `lw:road` | wheel_rut (close) — only on tiles adjacent to road waypoints |

Cross-biome shared tags: `small_rock`, `weathered_rock`, `bone_pile`, `mushroom_cluster`, `dead_tree` — declared once with multi-biome `biomes` list, weighted differently per biome via `density_weight`.

Example TOML entries:

```toml
[[object_kinds]]
id = "lw:decoration.small_rock"
primitive = "decoration"
label = "Small Rock"
footprint = { width = 1, height = 1 }
walkability_pattern = "all_walkable"
biomes = ["lw:grass", "lw:hill", "lw:mountain", "lw:desert"]
density_weight = 1.0
min_spacing = 2
properties = {}

[[object_kinds]]
id = "lw:decoration.flower_patch"
primitive = "decoration"
biomes = ["lw:grass"]
density_weight = 1.5
min_spacing = 0

[[object_kinds]]
id = "lw:decoration.broken_cart"
primitive = "decoration"
biomes = ["lw:grass", "lw:road"]
density_weight = 0.3
min_spacing = 8

[[object_kinds]]
id = "lw:decoration.cactus"
primitive = "decoration"
biomes = ["lw:desert"]
density_weight = 0.8
min_spacing = 4

[[object_kinds]]
id = "lw:decoration.crystal_shard"
primitive = "decoration"
biomes = ["lw:subterranean", "lw:mountain"]
density_weight = 0.5
min_spacing = 6

# ... 23-27 more entries
```

New `Registry` index (`registry.rs`):

```rust
pub struct Registry {
    // ... existing
    pub decoration_by_biome: BTreeMap<String, Vec<DecorationRef>>,
}
pub struct DecorationRef {
    pub kind_id: String,
    pub density_weight: f32,
    pub min_spacing: u32, // Chebyshev distance; pulled from ObjectKindDef.min_spacing
}
```

`decoration_by_biome` is computed at registry-load: scan all `ObjectKindDef`s with `primitive: Decoration`, bucket by each entry in their `biomes` list. Validation: every decoration tag MUST declare ≥1 biome; tags in unknown biomes fail registry-load.

Xianxia sample registry adds parallel entries (~30 `xianxia:decoration.*` tags spanning the same 10 biome IDs) in chunk B. Chunks A and C work against default registry only; xianxia parallel is part of B's scope.

## 7. Determinism preservation

The V2 golden test asserts:
```rust
let view = place_tilemap_with_registry(default_template, seed=1, default_registry);
assert_eq!(view.canonical_bytes_hash(), V2_GOLDEN_HASH); // byte-identical
```

V3 must keep this green. Strategy:
- Default `TilemapTemplate.decoration_density = None`. DecorationPlacer early-returns. View output unchanged.
- A NEW test asserts: `decoration_density = None` ⇒ output equals V2 golden hash exactly (regression lock).
- A NEW V3 golden asserts: `decoration_density = Some(DEFAULT_TOWN)` ⇒ output is hash-pinned to a NEW V3 reference (permanent regression for the density path).

No existing V2 test is rebaselined.

## 8. Locked decisions (PO approval 2026-05-28)

| # | Decision | PO lock | Implication |
|---|---|---|---|
| **Q1** | Per-tier density defaults | **(a)** §5 table values (VCMI-tuned) | Town 20-40 @ 0.10 / District 50-90 @ 0.08 / Country 100-200 @ 0.06 / Continent 200-500 @ 0.04 |
| **Q2** | Decoration tag count | **(b)** ~30 tags across all 10 V2 biomes | Chunk B grows to ~30 tags spanning `lw:grass`, `lw:forest`, `lw:water`, `lw:road`, `lw:hill`, `lw:mountain`, `lw:swamp`, `lw:desert`, `lw:snow`, `lw:subterranean`. Distribution per §6 table |
| **Q3** | min_spacing for decorations | **(c)** Per-tag min_spacing from registry | Each `lw:decoration.*` tag declares its own `min_spacing: u32` (Chebyshev). Per-tag, not cross-tag (see §4.3). Default classes: cluster (0), close (2), spread (4), rare (8). Algorithm: retry-on-reject with fallback to lower-min_spacing tags when target_count under-shoots |

PO chose higher-rigor options on Q2 and Q3 over my pragmatic defaults — pattern consistent with [[po-prefers-rigor-on-v3-decisions]] memory. Recorded for future quality-push ADRs.

## 9. Chunks (4 PRs)

| Chunk | Scope | Tests | PR size | Risk |
|---|---|---|---|---|
| **A** | `decoration_placer.rs` skeleton + `DecorationDensity` struct + `TilemapTemplate.decoration_density: Option<...>` field. Placer early-returns when `None`. | 1 unit test (compile + early-return); V2 golden unchanged (existing tests pass). | XS | LOW |
| **B** | Default registry decoration tags (~15 entries) + `Registry.decoration_by_biome` index + load-time validation (every decoration tag must list ≥1 biome). | Registry-load tests; drift test (xianxia sample doesn't break). | S | LOW |
| **C** | Placer logic — subtract other-placer anchors, density computation, uniform random placement, biome filter, deterministic per-zone RNG seed. | 4 unit tests: density bounds, walkability preserved, biome filter correct, determinism (same seed → same placements). | M | MED — load-bearing |
| **D** | Demo template opts in (`decoration_density: Some(TOWN_DEFAULT)`), frontend `L4 object overlay` renders `primitive: Decoration` sprites. Browser smoke at `/play` shows visible density jump. | Browser smoke test counts canvas-rendered decorations; cross-browser e2e passes. | S | LOW |

Total: 4 PRs, ~1-2 sessions of work. Each PR is independently reviewable.

## 10. Test strategy

### 10.1 V2 backward-compat (load-bearing)
- `decoration_density_none_preserves_v2_golden` — explicit hash check on V2 default template.
- All existing 433 tilemap-service tests stay green.

### 10.2 New V3 quality-path determinism
- `decoration_v3_default_town_pinned_hash` — composed-path snapshot for `(default_template + decoration_density=TOWN_DEFAULT, seed=1)`. New permanent regression.

### 10.3 Density invariants
- For each tier × 5 seeds: assert `min ≤ count ≤ max`.
- Assert `count ≤ fraction_of_free * free.count()` (approximately; some slack for min floor).

### 10.4 Walkability preservation
- For each placement: assert `walkability_pattern == all_walkable`.
- Pathfinding test: A* path from zone center → opposite corner stays valid after decorations placed.

### 10.5 Biome filtering
- For each decoration placement: assert `decoration.biomes.contains(zone.terrain_type)`.

### 10.6 Browser smoke (chunk D)
- Render demo at `/play`, count canvas objects in a Town-tier zone, assert ≥ 20.
- Visual side-by-side screenshot vs pre-decoration commit (manual gate, not CI).

## 11. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| V2 golden breaks during chunk A (template field addition) | LOW | Field is `Option<...>` with `#[serde(default)]`; `None` is the implicit default; serde round-trip unchanged |
| Browser smoke reveals chosen density too low/high | MED | Q1's default is heuristic; chunk D tests on actual demo; tunable in `template.rs` constants without re-shipping placer |
| Registry decoration tags clash with future V3 placement engine tags | LOW | V3 placement engine ADR (parked) reserved namespace `lw:obstacle.*`, `lw:object.*`; decorations use new namespace `lw:decoration.*` — disjoint |
| Frontend sprite pack missing decoration sprites | MED | Chunk D includes sprite generation step; can ship as placeholder colored squares (chunk D1) and replace with proper sprites later |
| DecorationPlacer slow on Continent tier (256² × 500 decorations × biome filter) | LOW | Placement is O(target_count × log(pool_size)); 500 × log(20) ≈ 2200 ops; negligible vs existing placer cost |
| Determinism breaks if registry sort order changes | LOW | `decoration_by_biome` uses `BTreeMap` (sorted) + decoration tag lookup uses sorted Vec; RNG seed is per-zone, decoupled from registry order |

## 12. Acceptance criteria

| ID | Criterion |
|---|---|
| AC-DECO-1 | `decoration_placer.rs` exists; `TilemapTemplate.decoration_density: Option<DecorationDensity>` field exists; `DecorationPlacer::process` early-returns when `None` |
| AC-DECO-2 | `decoration_density_none_preserves_v2_golden` test passes — explicit hash match on V2 default template (byte-identical, no rebaseline) |
| AC-DECO-3 | Default registry has ≥15 decoration tags across ≥5 land biomes; xianxia sample registry continues to load without error |
| AC-DECO-4 | For each tier in `{Town, District, Country, Continent}` × 5 seeds: placed decoration count ∈ `[min_per_zone, max_per_zone]` and count ≤ `1.5 × fraction_of_free × free.count()` (slack accommodates min floor) |
| AC-DECO-5 | Every placed decoration has `walkability_pattern: all_walkable`; A* pathfinding from zone center to opposite corner remains valid after placement |
| AC-DECO-6 | Every placed decoration's `kind.biomes` contains the zone's `terrain_type` (biome filter correctness) |
| AC-DECO-7 | `decoration_v3_default_town_pinned_hash` test passes — composed path output for `(default_template + TOWN_DEFAULT density, seed=1)` matches a hash-pinned 32-byte literal (new permanent regression) |
| AC-DECO-8 | Browser smoke at `/play` with demo template shows ≥ 20 distinct decoration sprites in the Town tier zone (chunk D) |
| AC-DECO-9 | All 433 existing tilemap-service tests + 49 frontend-game vitest tests stay green across all 4 chunks; no test rebaselined |
| AC-DECO-10 (Q3) | **Per-tag min_spacing enforcement**: for each placed decoration `d` with `min_spacing = s`, NO other placement with the same `kind_id` exists within Chebyshev distance `s` of `d`. Cross-tag pairs are exempt (a `flower_patch` adjacent to a `broken_cart` is legal) |
| AC-DECO-11 (Q3) | **Density target under-shoot fallback**: if a tag's retries exhaust before target_count, placer falls back to lower-min_spacing tags from the biome pool. Test: a zone with only one tag at min_spacing=20 (impossibly large) → placer fills with fallback cluster-tags until target_count or pool exhausted. Document under-shoot rate ≤ 10% across all tier × seed pairs |
| AC-DECO-12 (Q2) | Default registry declares ≥28 decoration tags spanning all 10 V2 terrain biomes; every biome has ≥2 decoration tags; validation passes (every tag's `biomes` list refers to known terrain primitives) |

## 13. Out of scope (explicit)

- Value-band treasure refactor — separate ADR.
- Per-resource type splits (gold/wood/ore/gems/crystal/mercury/sulfur) — separate ADR.
- TerrainPainter-style biome-driven terrain styling — separate ADR.
- Monster guards on treasure — separate ADR.
- Towns / heroes / artifacts / scrolls / seer huts — separate ADRs per category.
- V3 placement engine refactor — separate paused branch.
- world-gen ↔ zone-map integration — separate PARKED ADR.

## 14. Next steps (PO lock complete 2026-05-28)

1. ✅ PO locked Q1–Q3 same session — see §8.
2. Write `docs/plans/2026-05-28-decoration-placer-build.md` chunking the 4 PRs in detail (files touched, ACs per chunk, test deltas, /amaw triggers).
3. Start chunk **A (skeleton)** on a fresh implementation branch `mmo-rpg/zone-map-decoration-placer` off main.
4. After A merges: chunk **B** (~30 decoration tags + Registry index + per-tag min_spacing validation).
5. After B merges: chunk **C** (placer logic — the load-bearing piece; recommend `/amaw` for adversarial review on the deterministic seed derivation + per-tag spacing fallback algorithm).
6. After C merges: chunk **D** (demo opt-in + frontend overlay + browser smoke).
7. Browser smoke verdict gates whether we proceed to next quality-push theme or tune density.

**Stop condition:** if after chunk D the demo looks visually full and PO confirms "no longer empty," stop. Other quality-push themes (value bands, resources, theming, monster guards, etc.) are deferred until needed.
