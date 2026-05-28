# V3 world-gen ↔ zone-map Architectural Boundary (ADR)

> **Branch:** `mmo-rpg/zone-map-v3-spec` (CLARIFY/DESIGN only — no code yet; second V3 ADR)
> **Builds on:** V2 data model [`2026-05-26-data-model-v2-registry-footprint.md`](2026-05-26-data-model-v2-registry-footprint.md) (primitive + registry + footprint), V3 placement engine [`2026-05-28-v3-registry-driven-placement.md`](2026-05-28-v3-registry-driven-placement.md) (primitive-based dispatch).
> **Status:** PROPOSED 2026-05-28 — pending PO scope approval (4 open decisions)
> **Sizing estimate:** L implementation across 1 new shared crate + adapter modules in both services + integration tests

## 1. Why this ADR exists

Two Rust crates currently coexist in the workspace but **share no types and have no defined data contract**:

| Side | Crate / service | Output |
|---|---|---|
| Continental | `crates/world-gen` (main, merged 2026-05-27) | `WorldMap`: Voronoi cells in `[0,1]²` + biome/climate/hydrology/settlements/routes/cultures with `content_hash` for determinism |
| Tile-level | `services/tilemap-service` (PR #6 → main 2026-05-27) | `TilemapView`: per-zone tile grid `(u16, u16)` with terrain_layer + object_placements + zones, also deterministic by seed |

Both use the word "biome" for **different concepts**:

- `world_gen::BiomeKind` = 14 closed variants (Ocean, Lake, River, Coast, Beach, Plain, Forest, Jungle, Marsh, Mountain, Hill, Desert, Tundra, Glacier). **Geographic classification** of a continental cell.
- `tilemap_service::types::biome::BiomeId(String)` = open string identifier. **Asset-pack grouping** (`grassland_pines`, `grassland_oaks`, …). Drives obstacle template selection.

The same name covers different abstractions: world-gen's `BiomeKind::Plain` could correspond to *many* tilemap `BiomeId`s in the same per-book registry. Without a defined boundary, downstream consumers cannot:

- Drill from continental view → zone view deterministically.
- Carry world-gen-derived state (biome, climate, settlement-presence) into tilemap-service generation parameters.
- Compose determinism: a "world with seed=X" should produce the SAME zone tiles when drilled into cell C, every time.

V3 cannot proceed coherently without resolving this. The placement-engine ADR (just landed) reserves `Habitable` primitive for settlement drill-down — that handler must know what world-gen settlements look like. The xianxia-sample registry's `xianxia:qi-meadow` tag implies world-gen biome `Plain` (or `Marsh`?) — without a mapping table, "what world-gen biome does this per-book registry assume" is undefined.

## 2. Goals & non-goals

**Goals:**
1. Define the **data contract** for world-gen → tilemap-service: what gets handed over, in what type, with what determinism guarantee.
2. Establish **where shared types live** (shared crate vs duplication vs cross-references).
3. Compose **determinism** across the boundary — `world_map.content_hash` becomes part of the input to tilemap generation, so a zone's tiles are deterministically derived from (world_seed, cell_id, zone_template, tilemap_seed).
4. Locate the **adapter module** (which crate owns the conversion logic).

**Non-goals (deferred to sibling sub-ADRs):**
- Per-book world-gen-biome → tilemap-biome mapping table content (per-book registry concern; this ADR defines the table SHAPE).
- Coordinate transform algorithm details (this ADR defines the contract; algorithm is implementation).
- Settlement → `Habitable` placement automation (sub-ADR; depends on CSC_001 interior scenes).
- Route → road-segment generation (sub-ADR; touches existing `road_placer`).
- River-flux → river-segment generation (sub-ADR; touches existing `river_placer`).
- Climate-driven property overrides (sub-ADR; touches V3 placement-engine property handlers).

## 3. Decision — federated services with a shared types crate

### 3.1 Architectural pattern

```
                       ┌──────────────────────┐         ┌─────────────────────────┐
WorldArchetype  ──►   │  crates/world-gen    │  ──►   │  crates/loreweave_world │
seed (u64)            │  generate() → WorldMap│         │  - shared vocabulary    │
   (deterministic     └──────────────────────┘         │  - CellRef (cell_id +   │
    per seed +                  │                       │    world_hash)         │
    CreativeSeed)               ▼                       │  - WorldGenBiome /     │
                       ┌──────────────────────┐         │    Climate / SettleRole │
                       │  adapter (in world-  │ ◄────► │  - DrilldownInput type  │
                       │  gen)                 │         └─────────────────────────┘
                       │  WorldMap × cell_id →│                      │
                       │  DrilldownInput      │                      ▼
                       │ (deterministic per   │         ┌─────────────────────────┐
                       │  cell)               │         │  services/tilemap-svc   │
                       └──────────────────────┘   ───► │  template_for(drilldown)│
                                  │                      │  → TilemapTemplate      │
                                  └────────────────────►│  → place_tilemap_with_  │
                                                          │    drilldown(...)       │
                                                          │  → TilemapView          │
                                                          └─────────────────────────┘
```

**Pattern:** federated services share a small **vocabulary crate**, not types directly. World-gen and tilemap-service each own their internal types; the shared crate carries only the cross-boundary vocabulary + the handoff payload (`DrilldownInput`).

### 3.2 The shared crate — `crates/loreweave_world/`

Contains exactly the cross-boundary vocabulary + handoff types. NOT a god-crate:

```rust
// crates/loreweave_world/src/lib.rs

/// Typed wrapper around world-gen's `WorldMap.content_hash`. Prevents
/// accidental confusion with unrelated 32-byte hashes (tilemap goldens,
/// blake3 outputs from other code paths).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct WorldContentHash(pub [u8; 32]);

/// Stable reference to a world-gen cell with provenance.
///
/// `world_hash` is `WorldMap.content_hash` (wrapped). When folded into
/// the tilemap-service seed (§3.4), the same (cell_id, world_hash,
/// tilemap_seed) always produces the same `TilemapView`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CellRef {
    pub cell_id: u32,
    pub world_hash: WorldContentHash,
}

/// `f32` constrained to `0.0..=1.0` (finite). The `TryFrom<f32>` rejects
/// non-finite + out-of-range values at the boundary; downstream consumers
/// never see NaN / Inf / >1.0.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Serialize, Deserialize)]
pub struct NormalizedF32(f32);

impl NormalizedF32 {
    pub fn new(v: f32) -> Result<Self, ConversionError> {
        if !v.is_finite() || !(0.0..=1.0).contains(&v) {
            return Err(ConversionError::OutOfRange);
        }
        Ok(Self(v))
    }
    pub fn get(self) -> f32 { self.0 }
}

// Vocabulary enums move to this crate per B4=(c). world-gen re-exports
// them so its public API stays stable.
pub mod biome { /* WorldGenBiome enum (14 variants) */ }
pub mod climate { /* WorldGenClimate enum */ }
pub mod settlement { /* WorldGenSettlementRole enum */ }
pub mod route { /* WorldGenRouteKind enum */ }

pub use crate::biome::WorldGenBiome;
pub use crate::climate::WorldGenClimate;
pub use crate::settlement::WorldGenSettlementRole;
pub use crate::route::WorldGenRouteKind;

/// The cell-drill-down handoff payload. Produced by world-gen's adapter
/// module, consumed by tilemap-service.
///
/// **Field discipline:** every field listed below has a named consumer
/// in §5 (a sub-ADR) or in §3.4 (determinism composition). Adding a
/// field without naming its consumer is a scope-creep violation;
/// reviewers reject.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DrilldownInput {
    /// Provenance + determinism composition input (§3.4).
    pub cell_ref: CellRef,

    /// Consumer: sub-ADR 3a (per-book biome mapping).
    pub biome: WorldGenBiome,

    /// Consumer: sub-ADR 3f (climate property overrides).
    pub climate: WorldGenClimate,

    /// Consumer: sub-ADR 3e (river-flux → river-segment generation).
    pub river_flux_normalized: NormalizedF32,

    /// Consumer: sub-ADR 3c (settlement → Habitable). `None` for
    /// settlement-free cells.
    pub settlement: Option<DrilldownSettlement>,

    /// Consumer: sub-ADR 3d (route → road generation). Empty for cells
    /// with no incoming routes.
    pub incoming_routes: Vec<DrilldownRoute>,
}

impl DrilldownInput {
    /// V2 backward-compat: returns `None` everywhere; the `place_tilemap_with`
    /// non-drilldown entry point bypasses composition entirely (§3.4).
    /// This constructor exists so test fixtures + non-drilldown call sites
    /// can pass `Option::None` without constructing a fake payload.
    pub fn none() -> Option<Self> { None }

    /// Test-fixture builder. Defaults: biome=Plain, climate=Temperate,
    /// river_flux=0.0, no settlement, no routes. Override fields with
    /// the `.with_*` methods. Lives behind `cfg(any(test, feature = "test-support"))`.
    #[cfg(any(test, feature = "test-support"))]
    pub fn for_testing(cell_ref: CellRef) -> Self { /* … */ }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DrilldownSettlement {
    pub role: WorldGenSettlementRole,
    pub population_tier: u8,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DrilldownRoute {
    pub kind: WorldGenRouteKind,
    /// Direction the route enters the cell from (one of the cell's
    /// world-gen neighbors).
    pub from_neighbor: CellRef,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConversionError {
    OutOfRange,
}
```

**Crate dependencies + workspace discipline:**
- `crates/loreweave_world` depends on `serde` only — version pinned via root `Cargo.toml` `[workspace.dependencies]` so both services see the same serde major.minor (prevents derive-output drift).
- `crates/world-gen` depends on `crates/loreweave_world` for shared vocabulary + emits `DrilldownInput` via its adapter module.
- `services/tilemap-service` depends on `crates/loreweave_world` to read `DrilldownInput`.
- Neither service depends on the other directly. Enforcement: compile-fail check (§7.1) using `trybuild` dev-dep on `crates/loreweave_world`.

**Fields explicitly dropped from initial design (no V3 consumer):** `elevation_normalized`, `is_coast`, `neighbors`. Re-add only when a sub-ADR names them as a consumer. Wire-format-additive — re-adding later does not break readers, since deserialization tolerates missing-field-with-default via serde.

### 3.3 The adapter — `crates/world-gen/src/drilldown.rs`

```rust
// crates/world-gen/src/drilldown.rs

use loreweave_world::{
    CellRef, DrilldownInput, DrilldownRoute, DrilldownSettlement,
    WorldGenBiome, WorldGenClimate, WorldGenRouteKind, WorldGenSettlementRole,
};
use crate::WorldMap;

impl WorldMap {
    /// Build the drilldown payload for one cell. Pure function;
    /// deterministic given the same `WorldMap` + cell_id. Returns
    /// `None` if `cell_id` is out of range.
    pub fn drilldown(&self, cell_id: u32) -> Option<DrilldownInput> {
        // 1. Wrap content_hash in CellRef { cell_id, WorldContentHash }
        // 2. Map self.biome[cell_id]    → WorldGenBiome (re-exported, no conversion)
        // 3. Map self.climate[cell_id]  → WorldGenClimate (re-exported)
        // 4. Compute NormalizedF32 from self.river_flux[cell_id] / max_flux
        //    (TryFrom rejects non-finite — caller sees None on world-gen bug,
        //    but this branch is unreachable per world-gen's existing finite-f32
        //    debug_assert)
        // 5. Gather settlement (Option<DrilldownSettlement>) from self.settlements
        //    matching .cell == cell_id (≤ 1 per cell per world-gen invariant)
        // 6. Gather incoming_routes (Vec<DrilldownRoute>) by scanning
        //    self.routes for entries where cell_id ∈ route.path
    }
}
```

The adapter lives in `world-gen` (not `tilemap-service`) because:
1. World-gen owns the source data and the cell-id namespace.
2. World-gen's content_hash IS the determinism root; the adapter is the only code that legitimately reads it for provenance.
3. tilemap-service shouldn't import world-gen (one-way dependency).

### 3.4 Determinism composition — two distinct entry points

The V2 invariant: `place_tilemap_with_registry(template, seed=S, registry=R)` produces a `TilemapView` deterministic in `(template, S, R)`. This invariant is preserved by V3 placement engine (per its ADR §4.1) and MUST stay preserved by this ADR.

V3 adds a **second**, drilldown-aware entry point that uses a **composed** seed. The two entry points are deliberately separate functions; the V2 path is untouched.

```rust
// V2 entry — unchanged. Used by all V2 call sites + tests.
pub fn place_tilemap_with_registry(
    template: &TilemapTemplate,
    seed: u64,
    registry: &Registry,
) -> TilemapView { /* V2 logic; V3 placement engine refactor lands here */ }

// V3+ entry — composes seed against world-gen provenance.
pub fn place_tilemap_with_drilldown(
    template: &TilemapTemplate,
    seed: u64,
    registry: &Registry,
    drilldown: &DrilldownInput,
) -> TilemapView {
    // Domain-separated composition. The tag prevents collision with
    // any other use of blake3 in the codebase.
    let mut h = blake3::Hasher::new();
    h.update(b"loreweave:v3:drilldown-seed-v1\0");
    h.update(&drilldown.cell_ref.world_hash.0);
    h.update(template.template_id.as_bytes());
    h.update(&drilldown.cell_ref.cell_id.to_le_bytes());
    h.update(&seed.to_le_bytes());
    let composed_seed = u64::from_le_bytes(h.finalize().as_bytes()[..8].try_into().unwrap());
    place_tilemap_with_registry(template, composed_seed, registry)
}
```

**The contract:**

| Entry point | Inputs | Determinism guarantee |
|---|---|---|
| `place_tilemap_with_registry(t, s, r)` | template, seed, registry | V2 golden — Eq-equivalent `(t, s, r)` ⇒ Eq-equivalent `TilemapView`. UNCHANGED across V3. |
| `place_tilemap_with_drilldown(t, s, r, d)` | + drilldown | V3 golden — Eq-equivalent `(t, s, r, d)` ⇒ Eq-equivalent `TilemapView`. |

**Why two functions, not one with `Option<DrilldownInput>`:**
- An `Option<DrilldownInput>` parameter with `None` ⇒ skip composition would work, but adds a runtime branch on every call. Separate functions make the V2 path obviously untouched at the type level.
- Test discoverability: a V2 determinism golden test calls `place_tilemap_with_registry` directly; the function signature in the test makes it visually obvious composition is not in play.
- Refactor safety: a future bug that accidentally routes a V2 call through composition would require *changing the function name*, not flipping a defaulted argument.

**Non-drilldown V3 call sites** (e.g. test fixtures, sub-ADR 3a end-to-end test fixtures that don't have a real WorldMap) use `place_tilemap_with_registry` directly. The `DrilldownInput::none()` constructor returns `Option::None` and the V2 entry is the natural fit — no fake `[0u8; 32]` payload is constructed.

**CI enforcement:**
- AC-V3-BOUNDARY-4 pins V2 golden byte-equality for `place_tilemap_with_registry` on the default registry — exact same test as V2 today (V3 just adds the second entry point next to it).
- AC-V3-BOUNDARY-5 proves `place_tilemap_with_drilldown` composes on cell_id (two distinct cell_ids ⇒ different `TilemapView`).
- AC-V3-BOUNDARY-9 (new — see §9) pins a fixed `(template, seed=2026, registry=default, drilldown=fixture)` to a hash-pinned `TilemapView` for the V3 composed path.

### 3.5 Template selection — explicitly deferred to sub-ADR 3g (NEW)

The diagram in §3.1 shows the arrow `tilemap-svc: template_for(drilldown) → TilemapTemplate`. The mapping from `(WorldGenBiome, WorldGenClimate, …)` to a `TilemapTemplate` is a **per-book registry concern** — different books pick different templates for the same biome (`Plain + Temperate` could be `lw:meadow_v1` in default registry, `xianxia:qi_meadow_v1` in xianxia registry).

This boundary ADR defines only the contract `(DrilldownInput) → (template_id, …)`; the *content* of that mapping is **sub-ADR 3g — Template selection from drilldown** (added to §5). This ADR's end-to-end test (§6.5) uses a hand-fixtured `TilemapTemplate` so it can run before sub-ADR 3g ships.

## 4. Open decisions (PO lock required before BUILD)

| # | Decision | Options | Default proposal (per [[po-prefers-rigor-on-v3-decisions]]) |
|---|---|---|---|
| **B1** | Where does the adapter live — `crates/world-gen` (one-way producer), `services/tilemap-service` (one-way consumer), or a third location? | (a) `world-gen` produces `DrilldownInput`; (b) `tilemap-service` ingests `WorldMap`; (c) third crate `crates/loreweave_world_adapter` | **(a)** — one-way data flow, no circular deps, adapter co-located with source data + content_hash |
| **B2** | Shared types crate name + scope | (a) `crates/loreweave_world` (cross-boundary vocab + DrilldownInput); (b) collapse into `loreweave_world` super-crate that re-exports both services' types; (c) per-service mirror types with `serde`-equivalent shapes | **(a)** — narrow crate, just vocabulary + handoff payload; both services own their internal types |
| **B3** | Determinism composition — how does world-gen's content_hash flow into tilemap-service's seeding? | (a) Two separate entry points — V2 `place_tilemap_with_registry` untouched + V3 `place_tilemap_with_drilldown` composes via domain-separated `blake3(b"loreweave:v3:drilldown-seed-v1\0" \|\| world_hash \|\| template_id \|\| cell_id \|\| seed)`; (b) single function with `Option<DrilldownInput>` runtime branch; (c) no composition — tilemap-service ignores world_hash | **(a)** — V2 golden preserved by leaving V2 entry untouched at the type level; composed path is a separate function with its own snapshot pin (AC-10) |
| **B4** | Should `loreweave_world` re-export world-gen's enums (BiomeKind etc.) or define mirror enums? | (a) mirror enums in `loreweave_world` with explicit From/Into bridges to/from `world_gen`'s; (b) re-export world-gen's enums verbatim (tighter coupling); (c) world-gen re-exports `loreweave_world`'s enums (move definitions to shared crate) | **(c)** — move the enums to `loreweave_world` so world-gen is a *consumer* of the shared vocabulary too; eliminates the mirror-enum drift risk. Higher refactor cost for world-gen but cleanest long-term ownership |

## 5. Sub-ADRs deferred from this boundary spec

This boundary ADR establishes the contract. Each integration touchpoint gets its own sub-ADR. The **Blocked by** column tracks cross-spec dependencies so sub-ADRs can be parallelized safely.

| Sub-ADR | Scope | Blocked by |
|---|---|---|
| **3a — Per-book biome mapping** | The `WorldGenBiome → Vec<TilemapBiomeId>` mapping table in each per-book registry. **Amends the V2 registry format** ([`docs/specs/2026-05-26-data-model-v2-registry-footprint.md`](2026-05-26-data-model-v2-registry-footprint.md)) with a new `[world_gen_biomes]` TOML section. Defaults registry (`lw:`) maps all 14 world-gen biomes to default tilemap biome sets. Xianxia sample maps `Plain → [qi-meadow_pines, qi-meadow_oaks, …]`. | This ADR Phase 2 (DrilldownInput exists) |
| **3b — Coordinate transform** | Continental `[0,1]²` ↔ tile `(u16, u16)`. Voronoi cell polygon → tile grid extent. Edge handling (cell boundaries → zone boundaries). | This ADR Phase 2 |
| **3c — Settlement → Habitable** | `DrilldownInput.settlement` → tilemap-service `Habitable` placement (currently inert per V3 placement-engine ADR D2). Depends on CSC_001 interior scenes. | V3 placement-engine ADR D2 deferral (CSC_001 spec) + this ADR Phase 3 |
| **3d — Route → road generation** | `DrilldownInput.incoming_routes` → tilemap-service `road_placer` directives. Touches existing road_placer (geometric placer, untouched by V3 placement-engine refactor). | This ADR Phase 3 |
| **3e — River flux → river generation** | `DrilldownInput.river_flux_normalized` → tilemap-service `river_placer` directives. Touches existing river_placer. | This ADR Phase 3 |
| **3f — Climate property overrides** | `DrilldownInput.climate` overrides default property values on per-zone object placements (e.g. cold climate → reduce `growth_capacity` for plants; arid climate → reduce `river_flux`). | **V3 placement-engine ADR chunk 3.4a (schema infra)** + this ADR Phase 3. ⚠ Hard block: 3f cannot ship until schema-typed properties exist. |
| **3g — Template selection from drilldown (NEW)** | Per-book mapping `(WorldGenBiome, WorldGenClimate, settlement-presence, …) → TilemapTemplate`. Lives in the per-book registry alongside the 3a biome-mapping. Provides the `template_for(drilldown) → TilemapTemplate` logic the diagram in §3.1 shows. | This ADR Phase 3 + sub-ADR 3a (registry format already amended) |

**Cross-spec dependencies tracked here (LOW-4):**
- 3f → V3 placement-engine ADR chunk 3.4a (schema infrastructure). V3 placement-engine ADR §10 to be amended to list 3f as a downstream consumer.
- 3a + 3g → V2 registry format amendment (new TOML sections). V2 ADR §2.2 to be amended with a "V3 extensions" appendix when 3a / 3g land.

Sub-ADRs 3a / 3b / 3d / 3e can ship in any order once this ADR's Phase 3 lands. 3c blocks on CSC_001. 3f blocks on V3 placement-engine chunk 3.4a. 3g blocks on 3a (shared registry section).

## 6. Migration path (assumes B4=(c) per §4 recommendation)

If PO chooses B4=(a) (mirror enums), this whole section is rewritten as part of the counter-proposal — phases would re-shape around `From`/`Into` bridge code instead of enum moves. The plan below commits to (c) end-to-end.

### 6.1 Phase 0 — shared crate scaffold

Create `crates/loreweave_world/` with:
- `lib.rs` exporting nothing yet (just module declarations).
- `Cargo.toml` listing it as workspace member; `serde` pinned via workspace-level `[workspace.dependencies]`.
- One placeholder test (`workspace_member_compiles`).

No service consumes it yet. Sanity check that the workspace structure works.

### 6.2 Phase 1 — vocabulary migration (B4=(c))

Move world-gen's enums (`BiomeKind` → `WorldGenBiome`, `ClimateZone` → `WorldGenClimate`, `SettlementRole` → `WorldGenSettlementRole`, `RouteKind` → `WorldGenRouteKind`) into `loreweave_world`. World-gen re-exports them under their original names so its public API stays stable.

**The hash-stability gate:** every enum's `tag(self) -> u8` byte assignment is preserved exactly (same variants in same order). Pre-migration snapshot pins `generate(seed=2026, CreativeSeed::default()).content_hash` as a 32-byte literal; post-migration snapshot must match. If it doesn't, the migration is reverted — no rebaselining.

This Phase MUST keep all 18 world-gen tests + the new content-hash pin (AC-V3-BOUNDARY-8) green.

### 6.3 Phase 2 — `DrilldownInput` type + adapter

Add the payload types (CellRef, WorldContentHash, NormalizedF32, DrilldownInput, DrilldownSettlement, DrilldownRoute, ConversionError) to `loreweave_world`. Add `WorldMap::drilldown(cell_id) -> Option<DrilldownInput>` in `crates/world-gen/src/drilldown.rs`. Tests:
- Round-trip serde for all payload types.
- `drilldown(invalid_cell_id)` returns `None`.
- `drilldown(water_cell_id)` returns `Some(DrilldownInput { biome: Ocean | Lake, ... })` with `settlement = None` and empty `incoming_routes`.
- Determinism: same `(WorldMap, cell_id)` → same `DrilldownInput` (Eq-equivalent).
- `NormalizedF32::new(NaN)` / `new(1.5)` / `new(-0.1)` returns `Err(OutOfRange)`.

### 6.4 Phase 3 — `place_tilemap_with_drilldown` ingestion path

Add to `services/tilemap-service/src/lib.rs`:
- **Keep** `place_tilemap_with_registry(template, seed, registry) -> TilemapView` UNCHANGED. V2 golden is preserved by leaving this function untouched.
- **Add** new public function `place_tilemap_with_drilldown(template, seed, registry, drilldown) -> TilemapView` which composes the seed via the domain-separated `blake3(b"loreweave:v3:drilldown-seed-v1\0" || world_hash || template_id || cell_id || seed)` and then calls `place_tilemap_with_registry` with the composed seed.

**No `Option<DrilldownInput>` parameter on the V2 function** — see §3.4 "Why two functions, not one."

Tests:
- `place_tilemap_with_registry(default_template, seed=1, default_registry)` matches the existing V2 byte-identical golden (literally the same test — V3 doesn't touch the V2 function).
- `place_tilemap_with_drilldown(t, 1, r, drilldown_A)` ≠ `place_tilemap_with_drilldown(t, 1, r, drilldown_B)` for distinct cell_ids (proves composition is active).
- `place_tilemap_with_drilldown(t, 1, r, drilldown_A)` runs twice ⇒ Eq-equivalent (proves determinism).

### 6.5 Phase 4 — wire up one sub-ADR end-to-end as proof of contract

Pick sub-ADR 3a (per-book biome mapping) — smallest scope, no algorithmic risk. Sub-ADR 3a includes the V2 registry-format amendment (`[world_gen_biomes]` TOML section); without that amendment this end-to-end test can't run. Order is therefore: 3a's registry-format amendment + mapping content ships first, then this Phase 4 integration test.

Integration test: drills `WorldMap(seed=1).drilldown(cell=42)` → `tilemap-service.place_tilemap_with_drilldown(hand_fixtured_template, 1, registry, drilldown)` → asserts the per-zone biome IDs match the registry's `[world_gen_biomes]` mapping for `WorldGenBiome::Plain`.

(The hand-fixtured template here is intentional — sub-ADR 3g `template_for(drilldown)` hasn't shipped yet, so the test bypasses it.)

Validates the entire contract end-to-end before scaling to other sub-ADRs.

## 7. Test strategy

### 7.1 Shared-crate type discipline
- All payload types: serde round-trip tests (CellRef, WorldContentHash, NormalizedF32, DrilldownInput, DrilldownSettlement, DrilldownRoute).
- `CellRef` hash + equality test (derived Hash + Eq must work so `HashMap<CellRef, …>` is usable).
- `NormalizedF32::new` rejects NaN, Inf, negative, > 1.0; accepts 0.0, 1.0, finite-in-range.
- **Compile-fail tests via `trybuild` dev-dep on `crates/loreweave_world`:** a `tests/ui/no_service_import.rs` source asserts `use world_gen::*;` from a fixture target fails to compile. `trybuild` is added explicitly to `crates/loreweave_world/Cargo.toml` `[dev-dependencies]`. (Without an explicit harness, "workspace dep graph enforced" is just a verbal claim.)

### 7.2 Determinism propagation
- `WorldMap::drilldown(cell_id)` is deterministic for fixed `(WorldMap, cell_id)`.
- **V2 golden preservation (the load-bearing invariant):** `place_tilemap_with_registry(default_template, seed=1, default_registry)` byte-identical match to existing V2 golden. This is literally the existing V2 test, untouched — V3 added the second `place_tilemap_with_drilldown` entry next to it.
- `place_tilemap_with_drilldown(t, s, r, drilldown_A) ≠ place_tilemap_with_drilldown(t, s, r, drilldown_B)` for distinct cell_ids (proves composition is active, not no-op).
- `place_tilemap_with_drilldown(...)` run twice on the same inputs ⇒ Eq-equivalent (proves V3 path determinism).
- **V3 composed-path snapshot (new):** `place_tilemap_with_drilldown(default_template, seed=2026, default_registry, fixture_drilldown_2026)` pinned to a hash-pinned `TilemapView` (`blake3` over canonical bytes). Locks the composed-path output forever (MED-4 permanent regression).

### 7.3 Adapter coverage
- For each of the 14 `WorldGenBiome` variants: a unit test asserts `drilldown(cell-with-this-biome)` returns the variant correctly.
- For each `WorldGenSettlementRole`: unit test.
- Water cells (`is_water` biomes): drilldown returns settlement=None, routes empty.

### 7.4 world-gen content_hash regression (permanent)
- New permanent test `world_gen_content_hash_pinned_2026_05_28` in `crates/world-gen/tests/`. Asserts `generate(seed=2026, CreativeSeed::default()).content_hash == [pinned 32-byte literal]`. Any future change to `loreweave_world` enum tags, world-gen hash logic, or world-gen field set must update the literal intentionally (the test fails otherwise — flagging the drift, not silently accepting it).
- This is MED-4's permanent-pin requirement. AC-V3-BOUNDARY-8 covers the migration-time check; this test covers the post-migration forever.

### 7.5 Sub-ADR proof (end-to-end)
- Per §6.5: one full drill `WorldMap → DrilldownInput → TilemapView` covering biome mapping (sub-ADR 3a). Establishes the integration test pattern subsequent sub-ADRs can replicate.

### 7.6 Test fixtures via `DrilldownInput::for_testing`
- Behind `cfg(any(test, feature = "test-support"))`. Default: biome=Plain, climate=Temperate, river_flux=NormalizedF32::new(0.0).unwrap(), settlement=None, routes=empty.
- `.with_biome(b)`, `.with_climate(c)`, `.with_river_flux(f)`, `.with_settlement(s)`, `.with_route(r)` builder methods.
- Used by sub-ADR integration tests when constructing a `DrilldownInput` without a real `WorldMap`.

## 8. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Moving enums into shared crate (B4=c) breaks world-gen's 18 existing tests | MED | Re-export from `world_gen` to keep its public API stable; only INTERNAL paths change. Run full world-gen test suite at every step of migration |
| world-gen's `content_hash` silently changes during enum migration (tag bytes drift) | LOW-MED | Pre-migration snapshot AC-V3-BOUNDARY-8 + permanent post-migration pin §7.4 (`world_gen_content_hash_pinned_2026_05_28`). Migration-time AND forever |
| tilemap-service's V2 determinism golden breaks when V3 entry point is added | LOW (after HIGH-1 fix) | V2 entry `place_tilemap_with_registry` is left structurally untouched; V3 adds the second `place_tilemap_with_drilldown` next to it (separate function, separate test surface) |
| V3 composed-path output silently changes (e.g. composition formula edit) | MED | Permanent `place_tilemap_with_drilldown` snapshot pin (§7.2) over `(default_template, seed=2026, default_registry, fixture_drilldown_2026)` |
| Sub-ADR drift — sub-ADRs land in inconsistent order and break the contract | LOW | Blocked-by column in §5 makes the dep graph explicit. Each sub-ADR PR includes the integration test from §6.5 extended for its scope; contract changes require updating this ADR first |
| Shared crate becomes a god-crate over time | MED | The crate scope is documented in §3.2: vocabulary + handoff payload only. The "field discipline" doc-comment on `DrilldownInput` flags reviewers explicitly. Custom clippy lint TBD if pattern recurs |
| Per-book registry adds biomes/settlement-roles not in world-gen's closed enums | LOW (today) | Closed enum (14 biomes, 6 settlement roles). If a book genuinely needs a new world-gen biome variant (e.g. "Astral Plane" for sci-fi), that's a world-gen ADR — not a per-book registry concern |
| `trybuild` compile-fail harness drifts (changes to deps make the negative test pass-by-accident) | LOW | `trybuild` snapshots both the expected error output and the rejection; run on CI like any other test |

## 9. Acceptance criteria

| ID | Criterion |
|---|---|
| AC-V3-BOUNDARY-1 | `crates/loreweave_world` exists as a workspace member with exactly: `CellRef`, `WorldContentHash`, `NormalizedF32`, `ConversionError`, `DrilldownInput`, `DrilldownSettlement`, `DrilldownRoute`, + 4 vocabulary enums (`WorldGenBiome`, `WorldGenClimate`, `WorldGenSettlementRole`, `WorldGenRouteKind`). `DrilldownInput` field set per §3.2 — no `elevation_normalized`, no `is_coast`, no `neighbors` (re-add only when a sub-ADR names them as a consumer) |
| AC-V3-BOUNDARY-2 | `world-gen` and `tilemap-service` both depend on `loreweave_world`; neither depends on the other directly. Enforcement: `trybuild` compile-fail test on `crates/loreweave_world` proves a fixture that `use world_gen::*;` from a tilemap-service-like target fails to compile (§7.1) |
| AC-V3-BOUNDARY-3 | `WorldMap::drilldown(cell_id) -> Option<DrilldownInput>` exists in `crates/world-gen/src/drilldown.rs`; covered by §7.3 unit tests for all 14 biomes + 6 settlement roles + water cells. Settlement-free cells return `settlement: None`; route-less cells return `incoming_routes: vec![]` |
| AC-V3-BOUNDARY-4 | **V2 entry point unchanged**: `place_tilemap_with_registry(default_template, seed=1, default_registry)` produces a Eq-equivalent `TilemapView` to the existing pre-V3 golden — bit-for-bit, no rebaseline. This is V2's literal test, untouched (V3 only ADDED the drilldown function next to it) |
| AC-V3-BOUNDARY-5 | `place_tilemap_with_drilldown(t, s, r, drilldown_A)` ≠ `place_tilemap_with_drilldown(t, s, r, drilldown_B)` for two distinct `cell_id`s on the same `WorldMap` (proves composition is active, not no-op) |
| AC-V3-BOUNDARY-6 | world-gen's existing 18 tests + tilemap-service's 433 tests stay green across all migration phases. No test rebaselined; no `expect_test::update_snapshots`-style refresh allowed |
| AC-V3-BOUNDARY-7 | End-to-end test from §6.5 passes once sub-ADR 3a's V2-registry amendment ships: `WorldMap(seed=1).drilldown(cell=42)` → `place_tilemap_with_drilldown(hand_fixtured_template, …, drilldown)` → asserts per-zone biome IDs match the registry's `[world_gen_biomes]` mapping for `WorldGenBiome::Plain`. **Gated on sub-ADR 3a registry-format amendment.** |
| AC-V3-BOUNDARY-8 | world-gen's `content_hash` for `generate(seed=2026, CreativeSeed::default())` is byte-identical pre-migration vs post-migration (enum-move did not drift) — **migration-time check** |
| AC-V3-BOUNDARY-9 (NEW) | Permanent `world_gen_content_hash_pinned_2026_05_28` test asserts `generate(seed=2026, CreativeSeed::default()).content_hash == [pinned 32-byte literal]`. Locks the hash forever; any later change to `loreweave_world` enum tags or world-gen hash logic must update the literal intentionally |
| AC-V3-BOUNDARY-10 (NEW) | Permanent `place_tilemap_with_drilldown` snapshot test pins the composed-path output `TilemapView` over `(default_template, seed=2026, default_registry, fixture_drilldown_2026)` to a hash-pinned reference. Any change to the composition formula or downstream path fails until the pin is updated intentionally |
| AC-V3-BOUNDARY-11 (NEW) | `NormalizedF32::new(NaN | Inf | -0.1 | 1.5)` returns `Err(OutOfRange)`; `new(0.0 | 0.5 | 1.0)` returns `Ok`. Locks the bounds-enforcement at the type boundary |

## 10. Out of scope (explicit)

- Per-book biome mapping table CONTENT (default registry mapping, xianxia registry mapping, etc.) — sub-ADR 3a.
- Per-book TEMPLATE selection logic (`template_for(drilldown)`) — sub-ADR 3g.
- Coordinate transform algorithm (continental `[0,1]²` ↔ tile `(u16, u16)`) — sub-ADR 3b.
- Settlement drill-down to interior scenes (CSC_001 dep) — sub-ADR 3c.
- Route → road / River → river-segment integration — sub-ADRs 3d, 3e.
- Climate property overrides — sub-ADR 3f (blocked by V3 placement-engine chunk 3.4a).
- Re-adding `DrilldownInput` fields dropped from initial design (`elevation_normalized`, `is_coast`, `neighbors`) — only when a future sub-ADR names a consumer.
- New world-gen primitives or biomes (e.g. "Astral Plane") — separate world-gen ADR if a book actually needs one.
- HTTP-layer per-channel registry selection (separate sibling V3 ADR; mostly independent of this boundary).
- Footprint-honoring frontend rendering (separate sibling V3 ADR; frontend-only).
- Asset pipeline thaw (DEFERRED #037; separate sibling V3 ADR).

## 11. Next steps after PO lock

1. PO approves B1–B4 (or counter-proposes).
2. Write `docs/plans/2026-05-28-v3-world-gen-boundary-build.md` chunking the 4-phase migration.
3. Start Phase 0 (shared crate scaffold) on a fresh implementation branch `mmo-rpg/zone-map-v3-world-boundary` off main.
4. /amaw recommended for Phase 1 (vocabulary migration — touches world-gen's hash-stable enums) and Phase 3 (tilemap-service seed composition — touches the V2/V3 determinism golden).
