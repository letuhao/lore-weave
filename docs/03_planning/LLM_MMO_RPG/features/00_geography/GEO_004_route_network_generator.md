# GEO_004 — Route Network Generator (ROUTE_001)

> **Conversational name:** "Route Network Generator" (ROUTE). V1+30d sibling of GEO_002 POL_001 + GEO_003 SET_001 that activates GEO_001's V1-schema-reserved route layer. Implements pipeline **stage 7** with 4 sub-stages (7a Road Dijkstra over TerrainCost between settlements with population_tier ≥ 2 / 7b Trail connections for smaller settlements / 7c SeaLane derivation between coastal Cities / 7d MountainPass via graph edge-betweenness; RiverNavigation inline auto-derived). Populates `world_geometry.routes: Vec<Route>`. Activates 1 V1+30d `GeographyDeltaKind` variant (ReclassifyRoute). Composes with future TVL_001 V1+ (route consumed for travel-speed + cost modeling) and V2+ STRAT_001 (supply-line + invasion-path modeling). Completes the V1+30d geography activation triangle (POL + SET + ROUTE).
>
> **Category:** GEO — Geography Foundation (V1+30d generator; activates GEO_001 schema-reserved route layer; sibling of POL_001 + SET_001 at same stage horizon; final feature in the V1+30d activation triangle)
> **Status:** **DRAFT 2026-05-14** (Phase 0 ROUTE-D1..D7 LOCKED with user approval `approve all`)
> **Catalog refs:** [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — extends `GEO-*` namespace with ROUTE-* sub-prefix (`ROUTE-*` axioms · `ROUTE-D*` deferrals · `ROUTE-Q*` open questions · `AC-ROUTE-*` acceptance)
> **Builds on:** [`GEO_001`](GEO_001_world_geometry.md) §3.1 (Route struct schema already declared with `id + kind + from_cell + to_cell + distance_units + default_fiction_duration + is_bidirectional` fields) · §4.4 RouteKind 5-variant closed enum (Road / Trail / RiverNavigation / SeaLane / MountainPass) · §4.5 GeographyDeltaKind closed enum — AddRoute V1 + RemoveRoute V1 already exist; ROUTE_001 V1+30d adds 1 more · §5 stage 7 algorithm baseline declared · §16 GEO-D4 (this feature is the activation path) · [`GEO_002 POL_001`](GEO_002_political_layer.md) (sibling V1+30d; ROUTE consumes Province graph for province-boundary-aware route classification; ROUTE consumes State.capital_settlement_id for capital-connection prioritization) · [`GEO_003 SET_001`](GEO_003_settlement_generator.md) (critical sibling V1+30d; ROUTE stage 7 runs AFTER SET stage 6 — needs settlement coordinates as Dijkstra source/sink pairs)
> **Resolves:** Route-graph empty V1+30d-blocker (Routes remained empty V1 except canonical-declared; ROUTE_001 fills graph procedurally with classified RouteKinds) · LLM-context grounding route-name gap (prompt-assembly `[GEOGRAPHIC_CONTEXT]` gains `nearest_route_kind + route_origin/destination` per cell once ROUTE ships) · TVL_001 V1+ travel-mechanics dependency (TVL_001 needs route graph for inter-settlement travel-speed + cost; without ROUTE_001 V1+30d, TVL_001 has nothing to traverse) · Admin canonization runtime route-classification tooling (ReclassifyRoute V1+30d — upgrade Trail → Road after canon road-construction event; mirrors SET PromoteSettlement role-upgrade pattern) · GEO_001 §16 deferral GEO-D4 closed
> **Defers to:** future **TVL_001 V1+** (primary consumer — travel mechanics consume Route graph for inter-settlement movement modeling; route.kind → travel-speed modifier; route.distance_units + route.default_fiction_duration → time-cost) · future **STRAT_001 V2+** (consumes Route graph for supply-line + invasion-path + siege-encirclement modeling) · future **CSC_001** V1+30d cell skeleton selection at route-anchor cells (Road cell → Highway skeleton; SeaLane cell → Wharf skeleton — orthogonal; ROUTE owns the route-graph schema, CSC owns the cell-interior composition)

---

## §1 Why this exists

Three concrete gaps that ROUTE_001 closes.

**Gap 1 — Route graph is empty V1, leaving TVL_001 V1+ blocked.** GEO_001 V1 ships `world_geometry.routes: Vec<Route>` as schema-reserved Vec but populates it only from `creative_seed.canonical_routes` (V1+30d additive — author-pinned). The vast majority of V1+ worlds will be partially-canon: author seeds a few canonical roads (e.g., "Silk Road segments", "Imperial Highway"), then expects the rest of the continent to be procedurally networked with consistent settlement-pair connections. Without ROUTE_001, those worlds reject `geography.layer_activation_deferred_v1` on any runtime route write. TVL_001 V1+ (travel mechanics) has nothing to consume — it cannot model inter-settlement movement without a route graph. ROUTE_001 V1+30d unblocks TVL_001 by filling the graph procedurally.

**Gap 2 — LLM-context grounding has no route-context layer.** When prompt-assembly per S9 §12Y `[ACTOR_CONTEXT]` describes "Lý Minh travels from Khai Phong to Tương Dương", the LLM grounds on biome + climate + (post-POL) culture_tag + state_name + (post-SET) nearest_settlement. But the canonical reference for HUMAN-readable journey-identity is the **route taken** — "via the Imperial Highway Road" reads more concretely than "across Subtropical Plain". V1 has routes only when author pinned canonical_routes; runtime journeys lacking pinned routes get empty grounding. ROUTE_001 stage 7 populates routes deterministically; prompt-assembly joins `(from_cell, to_cell) → nearest_route(by Dijkstra distance)` and feeds the LLM canon-faithful route-name + RouteKind per inter-cell journey.

**Gap 3 — Admin canonization route-classification tooling is missing.** GEO_001 V1 ships `AddRoute` + `RemoveRoute` DeltaKinds (admin can add/remove) but NO classification-change primitive. Long-running wuxia worlds need:
- **ReclassifyRoute** — change `route.kind` after narrative event (e.g., Trail upgraded to Road after Imperial road-construction decree; Road downgraded to Trail after canonical war damage).

ROUTE_001 V1+30d adds this as the symmetric closing primitive. Total V1+30d active GeographyDeltaKind after ROUTE ships: **13** (5 V1 + 4 V1+30d POL + 3 V1+30d SET + 1 V1+30d ROUTE).

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Route** | GEO_001 §3.1 `Route { id, kind, from_cell, to_cell, distance_units, default_fiction_duration, is_bidirectional }` | V1+30d ROUTE_001 populates `kind` + `from_cell` + `to_cell` + `distance_units` (derived from Dijkstra path-cost over TerrainCost) + `default_fiction_duration` (derived from distance_units × per-RouteKind speed-modifier; OnFoot baseline matches MAP_001 §8 pattern) + `is_bidirectional` (= true V1+30d for all kinds; V1+30d+ one-way routes deferred). |
| **TerrainCost** | Same metric as POL_001 §2 (re-used) | Per-cell `f32` derived from `(BiomeKind, heightmap, river_flux, is_coast)`: Plain=1.0, Forest=1.5, Hill=2.0, Mountain=5.0, Marsh=3.0, Desert=2.5, Ocean=∞ (uncrossable for Road), River=2.0, Coast=1.2, Jungle=2.5, Beach=1.1, Lake=∞, Tundra=2.5, Glacier=∞. Fixed by `generator_pipeline_version`; shared with POL_001 stage 5 (no duplication). |
| **NavalCost** | NEW per-water-cell `f32` (V1+30d) for stage 7c SeaLane derivation | Ocean=1.0 (open sea passable); Lake=∞ (lakes are not navigable inter-settlement V1+30d; V2+ if lake-shipping needed); River=2.0 (RiverNavigation passable when river_flux > navigable_threshold per GEO_001 §3 + §4.4 baseline); Coast=1.0 (coastal cells passable as embark/disembark points); Land cells = ∞ for SeaLane. |
| **Route seed source** | `RouteSeedSource` 2-variant enum — Canonical / Procedural | Canonical = from `creative_seed.canonical_routes[i]` (V1+30d additive field — author-pinned `(from_cell, to_cell, kind)`). Procedural = Dijkstra-derived during stages 7a-7d. Mirrors POL/SET SeedSource pattern. |
| **RouteSeedMode** | Closed enum 3 V1+30d variants — Canonical / Procedural / Hybrid | Per ROUTE-D2 default Hybrid. Mirrors POL_001 PoliticalSeedMode + SET_001 SettlementSeedMode 3-variant pattern. Canonical = only canonical_routes placed (no procedural fill); Procedural = ignore canonical_routes entirely; Hybrid (default) = canonical first + procedural fills remaining settlement-pair connectivity. |
| **SettlementPair threshold** | population_tier ≥ 2 for Road; population_tier ≥ 0 for Trail (per ROUTE-D4) | Road class connects only Towns + Cities + Fortresses + Capitals (tier ≥ 2). Trail class connects Hamlets + Villages (tier 0-1) to their nearest larger settlement. Avoids O(N²) Road explosion (25 settlements × all-pairs would yield 300 Roads — too dense). |
| **Stage 7 sub-stages** | 4 sub-stages 7a-7d (per ROUTE-D3) | 7a: Road Dijkstra between settlement-pairs with both endpoints population_tier ≥ 2; cost = sum of TerrainCost over path. 7b: Trail connections — each settlement with population_tier 0-1 gets a Trail to its nearest larger-settlement (population_tier ≥ 2) via TerrainCost. 7c: SeaLane derivation — for each coastal-City pair within Euclidean range, BFS over water cells (NavalCost) finds shortest sea-path; emit SeaLane Route. 7d: MountainPass detection — graph edge-betweenness centrality on the cell-adjacency graph (weighted by inverse TerrainCost); top-N highest-betweenness mountain-cell edges become MountainPass Routes. RiverNavigation: inline auto-derived during 7a-7b — when a procedural Trail/Road path overlaps cells with `river_flux > navigable_threshold` for ≥ 3 consecutive cells, the segment converts to RiverNavigation. |
| **RouteSubstage** | Closed enum 4 V1+30d variants (informational; not serialized) | `Stage7a_Road`, `Stage7b_Trail`, `Stage7c_SeaLane`, `Stage7d_MountainPass` — audit/debug tag for which sub-stage produced each procedural route. Stored on `Route.seed_source.substage` field (additive Option<RouteSubstage>). |
| **One-route-per-pair invariant** | **Cell-pair `(from_cell, to_cell)` hosts ≤ 1 Route V1+30d (any kind)** — HIGH-2 fix /review-impl 2026-05-14 reconciled with Route struct schema (Route keys on GeoCellId pairs, not settlement IDs); RiverNavigation + MountainPass routes have NON-settlement endpoints so settlement-pair phrasing was wrong | Prevents double-routing (e.g., a Trail AND a Road between same cell pair). If stage 7a emits Road and stage 7b ATTEMPTS Trail for same (from_cell, to_cell), the Trail is suppressed. Covers all 5 RouteKind variants uniformly (Road/Trail at settlement-cell endpoints; RiverNavigation at river-segment-endpoint cells; SeaLane at coastal-cell endpoints; MountainPass at adjacent mountain-cell endpoints). V2+ multi-route-per-pair (Road + SeaLane between coastal cities at same cell pair) deferred ROUTE-D8. |
| **Bidirectional V1+30d** | All routes V1+30d are `is_bidirectional = true` | One-way routes (e.g., one-way scenic mountain road) deferred V1+30d+ as ROUTE-D9. |
| **River_flux navigable_threshold** | Reused from GEO_001 §3 + §6 — `river_threshold: f32` default 1000.0 | Stage 7 RiverNavigation auto-detect threshold; configurable per `creative_seed.river_threshold` (already V1 field). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

ROUTE_001 introduces **NO new EVT-T* category**. Reuses existing GEO_001 + POL_001 + SET_001 event-model with one activation + one DeltaKind closed-enum addition:

| ROUTE event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Route layer materialized at bootstrap (stage 7 runs; routes populated) | **EVT-T3 Derived** | `aggregate_type=world_geometry` (field delta — routes Vec grows from empty/canonical-only to fully populated; bumps `world_geometry.last_delta_event_id`) | Aggregate-Owner role (world-service post-SET-stage-6) | Causal-ref to triggering EVT-T4 GeographyBorn. ROUTE_001 V1+30d adds stage 7 emission as a T3 layer-activation event per continent (separate from POL's stage 5+8 and SET's stage 6 emissions). Replay-deterministic per `settlement_seed` (substream `b"stage7_route"` — no dedicated route_seed sub-seed per ROUTE-Q1; deterministic algorithm without RNG, substream tag reserved for V1+30d+ probabilistic extensions). |
| Forge admin runtime route reclassification | **EVT-T8 Administrative** | `Forge:EditGeographyDelta { continent_channel_id, delta_kind: ReclassifyRoute, delta_payload, prev_delta_id }` | WA_003 Forge | Already-registered sub-shape. ROUTE_001 V1+30d extends `GeographyDeltaKind` closed enum from 12 (5 V1 + 4 V1+30d POL + 3 V1+30d SET) → 13 V1+30d (R3 additive). ReclassifyRoute is **Tier 2 ImpactClass=Griefing** per S5 (reversible — admin can reclassify back; matches AddRoute V1 + SET RelocateSettlement/PromoteSettlement V1+30d precedent). Existing V1 AddRoute remains Tier 2 Griefing; RemoveRoute V1 remains Tier 1 ImpactClass=Destructive (per GEO_001 §7). |
| LLM-derived route-evolution proposal (V2+) | **EVT-T6 Proposal** | `ROUTE:NarrativeRouteEdit` (V2+ reservation) | future LLM route-arc Generator | V2+: LLM proposes Add/Remove/Reclassify based on narrative events (canonical road construction → AddRoute; war damage → ReclassifyRoute Road→Trail; trade collapse → RemoveRoute). Forge admin reviews + materializes via T8. V1+30d scope-out: T8 admin only. |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. The §4 EVT-T8 sub-shapes table's existing `Forge:EditGeographyDelta` row remains owned by GEO_001 — ROUTE_001 V1+30d extends the variant set behind that sub-shape without adding a new sub-shape row, mirroring POL_001 + SET_001 discipline.

EVT-T3 Derived sub-types row's existing `aggregate_type=world_geometry` registration absorbs ROUTE_001's stage 7 layer-activation events without modification.

---

## §3 Schema activation

**No new aggregate.** ROUTE_001 V1+30d populates GEO_001 §3.1 `world_geometry.routes: Vec<Route>` field.

Extends `GeographyDeltaKind` closed enum (R3 additive — no aggregate schema_version bump for world_geometry itself; Route struct shape unchanged from GEO_001 V1; CreativeSeed schema_version DOES bump 4 → 5 for new `route_seed_mode + canonical_routes` fields):

```rust
pub enum GeographyDeltaKind {                               // closed; admin canonization via Forge:EditGeographyDelta T8
    // ─── V1 (5 variants; GEO_001) ───
    AddNamedSettlement { cell_id: GeoCellId, name: LocalizedName, role: SettlementRole, population_tier: u8 },
    RenameRegion { cell_ids: Vec<GeoCellId>, new_name: LocalizedName, scope: RenameScope },
    SetBiomeOverride { cell_id: GeoCellId, biome_override: BiomeKind, reason: I18nBundle },
    AddRoute { from_cell: GeoCellId, to_cell: GeoCellId, kind: RouteKind, distance_units: u32, default_fiction_duration: FictionDuration },
    RemoveRoute { route_id: RouteId },

    // ─── V1+30d POL_001 (4 variants; GEO_002) ───
    MergeProvinces { source_province_ids: Vec<ProvinceId>, into_capital_province_id: ProvinceId, new_name: Option<LocalizedName>, reason: I18nBundle },
    SplitProvince { source_province_id: ProvinceId, partition: Vec<ProvincePartition>, reason: I18nBundle },
    TransferProvinceToState { province_id: ProvinceId, new_state_id: Option<StateId>, reason: I18nBundle },
    SetCultureRegion { cell_ids: Vec<GeoCellId>, new_culture_tag: CultureTag, reason: I18nBundle },

    // ─── V1+30d SET_001 (3 variants; GEO_003) ───
    RelocateSettlement { settlement_id: SettlementId, new_cell_id: GeoCellId, reason: I18nBundle },
    PromoteSettlement { settlement_id: SettlementId, new_role: Option<SettlementRole>, new_population_tier: Option<u8>, reason: I18nBundle },
    RemoveSettlement { settlement_id: SettlementId, reason: I18nBundle },

    // ─── V1+30d ROUTE_001 (1 variant; this commit — closed-enum bump per R3 additive; total 13 V1+30d active) ───
    ReclassifyRoute { route_id: RouteId, new_kind: RouteKind, reason: I18nBundle },
}
```

**Why `ReclassifyRoute` (single new V1+30d DeltaKind, not 2-3 more):** symmetric admin tooling — Add (V1) + Remove (V1) + Reclassify (V1+30d) covers the natural lifecycle of route canonization. Distance/duration tuning is rare and tracked V2+ (ROUTE-D5 attribute-tuning deferral). Merge/Split routes is uncommon admin pattern (V2+ ROUTE-D7). The 1-variant addition matches ROUTE-D6.

**`world_geometry.schema_version` bumps 2 → 3** (HIGH-1 fix /review-impl 2026-05-14 — Route struct field declaration made explicit; MED-3 cleanup of prior self-contradictory prose): ROUTE_001 adds `Route.seed_source: Option<RouteSeedSource>` field — additive struct field on a `world_geometry` sub-struct mirrors SET-001 HIGH-3 precedent (Settlement.seed_source 1→2 bump). Per I14 + R3 default-tolerant readers, every additive struct field bumps aggregate schema_version. Reader semantics: v3 readers see `Route.seed_source` natively; v2 readers (pre-ROUTE cohort) governed by `generator_pipeline_version` pin per POL MED-11 — they never read v3 data at runtime. Legacy Route rows pre-ROUTE-ship: `seed_source = None` (R3 default-tolerant absent-field).

**Route struct extension (V1+30d additive — HIGH-1 fix /review-impl 2026-05-14):**

```rust
// Extends GEO_001 §3.1 Route struct (V1) with V1+30d additive field; world_geometry.schema_version bump 2 → 3
pub struct Route {                                          // ... GEO_001 V1 fields elided (id / kind / from_cell / to_cell / distance_units / default_fiction_duration / is_bidirectional) ...
    pub seed_source: Option<RouteSeedSource>,               // V1+30d ROUTE_001 additive — Canonical { decl_index } | Procedural { substage, dijkstra_rank }; None for legacy V1 canonical-only Routes pre-ROUTE-ship (R3 default-tolerant readers); mirrors SET-001 Settlement.seed_source field-addition precedent
}
```

**`creative_seed.schema_version` bumps 4 → 5** — ROUTE_001 adds 2 additive fields (`route_seed_mode` + `canonical_routes`); per I14 + GEO_001b 1→2 + POL_001 2→3 + SET_001 3→4 precedent, every additive field-set in CreativeSeed bumps the version. **LLM authoring template version bump v3.tmpl → v4.tmpl** with CreativeSeed v5 schemars-generated JSON Schema. Per §12Y.L2 governance: template version bump requires CI fixture update.

**Capability addition (per `_boundaries/02_extension_contracts.md` §3 capability JWT):** `can_edit_route_geography` claim — required for the V1+30d ReclassifyRoute DeltaKind + the existing V1 `AddRoute` + `RemoveRoute` (which currently require only `can_edit_geography`; ROUTE ship migrates AddRoute/RemoveRoute to ALSO require `can_edit_route_geography` per migration plan §9 mirroring POL_001 MED-6 + SET_001). Disjoint from `can_edit_political_geography` (POL claim) + `can_edit_settlement_geography` (SET claim). Migration plan: auto-grant to all `can_edit_geography` holders at ROUTE ship; PLT_001 §6.3 quad-pair (`can_edit_geography + can_edit_political + can_edit_settlement + can_edit_route`) at role-grant time.

---

## §4 Closed enums (ROUTE_001 V1+30d)

### 4.1 RouteSeedMode (3 V1+30d; closed)

```rust
pub enum RouteSeedMode {                                    // closed; per-CreativeSeed declaration; mirrors POL/SET SeedMode pattern
    Canonical,                                              // NO procedural seeds; canonical_routes alone placed. Settlements without canonical-route coverage have NO routes — TVL_001 V1+ will return "no path" between them.
    Procedural,                                             // pure algorithmic; canonical_routes IGNORED even if present (V1+30d fallback / dev mode "give me a generated road network from seed"). All routes procedural via stages 7a-7d.
    Hybrid,                                                 // V1+30d DEFAULT — canonical routes placed first (priority); procedural Dijkstra fills remaining settlement-pair connectivity per ROUTE-D4 threshold (Road for tier ≥ 2; Trail for tier 0-1).
}
```

Per ROUTE-D2 default Hybrid. Surfaced in `creative_seed.route_seed_mode: RouteSeedMode` (V1+30d additive — CreativeSeed `schema_version` bumps 4 → 5 per §3 above).

### 4.2 RouteSeedSource (2 V1+30d; closed)

```rust
pub enum RouteSeedSource {                                  // closed; per-route provenance tag
    Canonical { decl_index: u32 },                          // points back to creative_seed.canonical_routes[decl_index]
    Procedural { substage: RouteSubstage, dijkstra_rank: u32 }, // sub-stage that produced this route + rank within sub-stage (e.g., 5th Road emitted by stage 7a)
}
```

### 4.3 RouteSubstage (4 V1+30d; closed — audit/debug tag)

```rust
pub enum RouteSubstage {                                    // closed; audit-only; written to Route.seed_source for replay-debug clarity
    Stage7a_Road,                                           // multi-source Dijkstra Road network between settlements with population_tier ≥ 2
    Stage7b_Trail,                                          // Trail connections from population_tier 0-1 settlements to nearest larger
    Stage7c_SeaLane,                                        // SeaLane derivation between coastal Cities via NavalCost BFS
    Stage7d_MountainPass,                                   // MountainPass detection via graph edge-betweenness on mountain-cell edges
    // RiverNavigation produced inline within Stage7a/7b — not a separate substage; tagged via post-pass cell scan
}
```

### 4.4 RouteKind (no enum change — already declared in GEO_001 §4.4)

GEO_001 already declared `RouteKind = Road | Trail | RiverNavigation | SeaLane | MountainPass`. ROUTE_001 V1+30d activates ALL 5 variants via multi-pass stage 7 algorithm. No enum change.

### 4.5 CanonicalRouteDecl (V1+30d additive; in CreativeSeed v5)

```rust
pub struct CanonicalRouteDecl {                             // V1+30d additive on CreativeSeed; author-pinned routes
    pub from_position: SpatialPreference,                   // GEO_001b v2 SpatialPreference — usually NearSettlement(LocalizedName) for canonical routes
    pub to_position: SpatialPreference,
    pub kind: RouteKind,
    pub distance_units_override: Option<u32>,               // if None, derived from Dijkstra-path; if Some, author override (e.g., canonical Silk Road = 1000 leagues regardless of cell-path)
    pub default_fiction_duration_override: Option<FictionDuration>,
    pub canon_ref: Option<BookCanonRef>,                    // book-grounded; canonical wuxia "Imperial Highway" → BookCanonRef("ThanDieuDaiHiep", "v1_chapter_5")
}
```

---

## §5 Pipeline activation — stage 7

ROUTE_001 V1+30d implements pipeline stage 7 (Route network generation), which GEO_001 §5 declared as V1+ activation slot. Stages 1-4 (geometry / climate / biome+river) are V1 GEO_001 territory; stage 5 (political growth) + stage 8 (culture spread) are V1+30d POL_001; stage 6 (settlement placement) is V1+30d SET_001; stage 7 is THIS commit. Final pipeline order: 1-4 GEO_001 → 5 POL → 6 SET → **7 ROUTE** → 8 POL.

### 5.1 Stage ordering precondition

Stage 7 MUST run AFTER stages 1-4 (geometry / climate / biome) AND stage 5 (POL provinces + state.capital_settlement_id) AND stage 6 (SET settlements). Reasons:
- Stage 7a Road Dijkstra needs settlements (from SET stage 6) for source/sink pairs.
- Stage 7b Trail connections need population_tier (from SET stage 6) to filter pair eligibility.
- Stage 7c SeaLane needs Settlement.role == City + is_coast (from SET + GEO_001) for coastal-City detection.
- Stage 7d MountainPass needs the full cell-adjacency graph weighted by TerrainCost (from POL stage 5 + GEO_001 stages 1-4).

If SET_001 V1+30d is NOT activated (settlements stay empty): ROUTE stage 7 produces NO routes (empty Vec). Reverse (SET on, ROUTE off) is the V1+30d-pre-ROUTE state — routes stay empty per GEO_001 schema-reserved discipline.

### 5.2 Stage 7 algorithm — Multi-pass route network generation

```
Inputs:
  - cells, neighbors, biomes, heightmap, river_flux, is_coast (from stages 1-4)
  - climate_zones (from stage 3)
  - provinces, states, state.capital_province_id (from POL stage 5)
  - settlements, Province.capital_settlement_id (from SET stage 6)
  - settlement_seed: u64 (from GeographySeed; ROUTE substream tag b"stage7_route" per ROUTE-Q1 — no dedicated route_seed sub-seed V1+30d; deterministic algorithm without RNG, substream reserved for V1+30d+ probabilistic extensions)
  - creative_seed.canonical_routes: Vec<CanonicalRouteDecl>          (ROUTE_001 V1+30d additive within v5)
  - creative_seed.route_seed_mode: RouteSeedMode                      (ROUTE_001 V1+30d additive within v5)
  - creative_seed.river_threshold: f32                                (already V1 GEO_001 — default 1000.0)

Outputs:
  - world_geometry.routes: Vec<Route>
  - route.kind, route.from_cell, route.to_cell, route.distance_units, route.default_fiction_duration all populated

Algorithm (per ROUTE-D2 hybrid + ROUTE-D3 multi-pass + ROUTE-D4 population_tier threshold):

  ─── Phase 1: Canonical route placement (priority) ──────────────────────
  1. If route_seed_mode == Procedural: skip phase 1 (ignore canonical_routes); proceed with empty canonical-route set.
  2. For each CanonicalRouteDecl in creative_seed.canonical_routes (Vec order — author intent preserved):
     a. Resolve from_position SpatialPreference → from_cell (e.g., NearSettlement("Khai Phong") → cells[khai_phong.cell_id]).
     b. Resolve to_position → to_cell similarly.
     c. Validate (per §8): from_cell ≠ to_cell (ROUTE-V1); both cells ∈ cells (ROUTE-V2); RouteKind valid (closed enum check); for SeaLane: both cells coastal OR water (NavalCost < ∞).
     d. Compute distance_units: if decl.distance_units_override is Some, use it; else compute via Dijkstra/BFS path-sum over TerrainCost (Road/Trail) or NavalCost (SeaLane) or river-cell-count (RiverNavigation).
     e. Compute default_fiction_duration: if decl.default_fiction_duration_override is Some, use it; else derive from distance_units × per-RouteKind speed-modifier (Road = 1 league/hour OnFoot baseline; Trail = 0.6 league/hour; SeaLane = 4 leagues/hour by sail; RiverNavigation = 3 leagues/hour by boat; MountainPass = 0.3 league/hour climbing).
     f. Materialize Route { id: blake3-derive (continent_channel_id || settlement_seed || "stage7_canonical" || decl_index_be_bytes), kind: decl.kind, from_cell, to_cell, distance_units, default_fiction_duration, is_bidirectional: true V1+30d, seed_source: Some(Canonical { decl_index }) }.

  ─── Phase 2: Procedural Road network — Stage 7a (priority-queue Dijkstra) ───
  3. If route_seed_mode == Canonical: skip phase 2 entirely (no procedural fill).
  4. Identify Road-eligible settlement set R = { s ∈ settlements : s.population_tier ≥ 2 } per ROUTE-D4.
  5. For each pair (s_i, s_j) in R × R with i < j (avoid duplicate pairs; is_bidirectional handles reverse):
     a. Check pair-uniqueness: if a Route already exists with (from_settlement, to_settlement) == (s_i, s_j) OR (s_j, s_i) (canonical may have pre-placed) → skip pair.
     b. Run multi-source Dijkstra from s_i.cell_id to s_j.cell_id over cell-adjacency graph weighted by TerrainCost. Tiebreaker: lowest GeoCellId for intermediate cells per stage-1 invariant.
     c. If shortest-path cost is ∞ (no land-route exists — e.g., s_i and s_j on disconnected continents): SKIP this pair; do NOT emit Road. (V2+ inter-continent Road via SeaLane bridge deferred ROUTE-D11.)
     d. Compute distance_units = path-cost (TerrainCost sum); compute default_fiction_duration = distance_units × Road-OnFoot-speed-modifier (1 league/hour V1+30d).
     e. Materialize Route { id: blake3-derive (continent_channel_id || settlement_seed || "stage7a_road" || pair_index_be_bytes), kind: Road, from_cell: s_i.cell_id, to_cell: s_j.cell_id, distance_units, default_fiction_duration, is_bidirectional: true, seed_source: Some(Procedural { substage: Stage7a_Road, dijkstra_rank: pair_index }) }.

  ─── Phase 3: Procedural Trail connections — Stage 7b ────────────────────
  6. If route_seed_mode == Canonical: skip phase 3.
  7. Identify Trail-eligible settlement set T = { s ∈ settlements : s.population_tier ∈ [0, 1] } per ROUTE-D4.
  8. For each s in T (Vec order — deterministic):
     a. Find nearest larger settlement s_nearest where s_nearest.population_tier ≥ 2, by TerrainCost path-distance (ties broken by lowest GeoCellId of larger settlement).
     b. If no s_nearest reachable (TerrainCost path = ∞): SKIP; Hamlet/Village remains route-isolated (V1+30d acceptable — V2+ could add SeaLane-bridge or skip-settlement-network).
     c. Check pair-uniqueness vs existing canonical + Phase-2-Road set.
     d. Materialize Route { kind: Trail, from_cell: s.cell_id, to_cell: s_nearest.cell_id, ... seed_source: Some(Procedural { substage: Stage7b_Trail, dijkstra_rank: trail_index }) }.

  ─── Phase 4: SeaLane derivation — Stage 7c ─────────────────────────────
  9. If route_seed_mode == Canonical: skip phase 4.
  10. Identify coastal-City set C = { s ∈ settlements : s.role == City AND is_coast[s.cell_id] }.
  11. For each pair (c_i, c_j) in C × C with i < j AND Euclidean distance(c_i.cell_id, c_j.cell_id) ≤ max_sealane_range (0.5 of continent diameter V1+30d):
       a. Run BFS over water-cell adjacency (cells where biome ∈ {Ocean, Coast} per NavalCost) from c_i's coastal cell to c_j's coastal cell.
       b. If reachable (BFS finds path): materialize Route { kind: SeaLane, from_cell: c_i.cell_id, to_cell: c_j.cell_id, distance_units = path-length, default_fiction_duration = distance_units / 4 leagues-per-hour-by-sail, seed_source: Some(Procedural { substage: Stage7c_SeaLane, dijkstra_rank: sealane_index }) }.
       c. If unreachable (inland lake-bound City, no water-path to other coast): SKIP.

  ─── Phase 5: MountainPass detection — Stage 7d (HIGH-3 fix /review-impl 2026-05-14 — settlement-pair-betweenness over full TerrainCost graph) ─────────────────────────
  12. If route_seed_mode == Canonical: skip phase 5.
  13. **HIGH-3 fix: vertex set is SETTLEMENTS (from SET stage 6 output), not Mountain/Hill cells.** A "mountain pass" is a mountain/hill cell-pair edge that LIES ON shortest paths between settlements on opposite sides of a mountain range — NOT an interior route within mountain terrain. Build full-cell-adjacency graph G_full: vertices = ALL cells (1024-16384 per continent); edges = neighbor adjacency weighted by TerrainCost (mountain=5.0 / hill=2.0 / plain=1.0 / etc.; Ocean=∞ uncrossable).
  14. Compute settlement-pair-restricted edge-betweenness centrality: for each settlement-pair (s_i, s_j) where both s_i, s_j ∈ settlements (from SET stage 6 output), run shortest-path Dijkstra over G_full and accumulate +1 betweenness score for every edge on that path. Use Brandes' algorithm restricted to settlement-vertices as sources (~O(S · E) where S = settlement count, E = total edges; for 25 settlements × 30k edges ≈ 750k ops, ≈ 10ms wall-clock). This correctly identifies mountain/hill edges that bottleneck inter-settlement travel through mountain corridors — the canonical "pass" semantic.
  15. Filter to mountain/hill edges only: `eligible_edges = { (cell_a, cell_b) edge in G_full : biomes[cell_a] ∈ {Mountain, Hill} OR biomes[cell_b] ∈ {Mountain, Hill} }`. Sort by descending settlement-pair-betweenness; select top-N edges where N = `min(mountain_pass_target, num_chokepoints_above_threshold)` (V1+30d default: mountain_pass_target = 5 per continent; threshold = top 10% betweenness within eligible_edges).
  16. For each selected edge (cell_a, cell_b): materialize Route { kind: MountainPass, from_cell: cell_a, to_cell: cell_b, distance_units = 1 (single-edge pass), default_fiction_duration = 1 league × MountainPass-speed-modifier (0.3 league/hour climbing → ~3.3h), seed_source: Some(Procedural { substage: Stage7d_MountainPass, dijkstra_rank: pass_index }) }.

  ─── Phase 6: RiverNavigation auto-derivation (inline within 7a-7b) ─────
  17. Post-pass: for each procedural Road/Trail emitted in phases 2-3, scan its Dijkstra-path cell sequence:
       a. Find consecutive ≥ 3-cell segments where `river_flux[cell] > river_threshold` (navigable river).
       b. For each such segment, EMIT a parallel RiverNavigation Route over the segment (alternative routing for water-bound travel).
       c. Original Road/Trail Route preserved (admin/player can choose land OR river travel via TVL_001 V1+ traversal logic).
       d. RiverNavigation Route tagged seed_source: Some(Procedural { substage: Stage7a_Road, dijkstra_rank }) reusing parent's rank+source — informational link.

Determinism: same (settlement_seed, creative_seed snapshot, generator_pipeline_version, [POL stage 5 output, SET stage 6 output]) → bitwise-identical routes (modulo HashMap normalization per SPIKE_04 GAP-S2.A canonical-JSON discipline). All sub-stages are deterministic — Dijkstra with GeoCellId tiebreaker, BFS deterministic, Brandes' edge-betweenness deterministic. No RNG calls V1+30d.

Cost envelope (V1+30d target):
  10k cells continent, 25 settlements, 5 Road-eligible (tier ≥ 2) → ~60ms wall-clock for stage 7 (single-threaded Rust). +60ms beyond stages 1-6 baseline (combined stages 1-7 ≈ 170ms).
  Adds ~80KB compressed to world_geometry aggregate (MED-2 fix /review-impl 2026-05-14 — original 30KB estimate undercounted RiverNavigation inline auto-emit; revised estimate: ~15 procedural Road/Trail Routes from stages 7a-7b + ~5 MountainPass Routes from stage 7d + ~5 SeaLane Routes from stage 7c + **~15 RiverNavigation Routes auto-emitted inline within stages 7a-7b** (river-crossing land routes typically generate 2-3 RiverNav segments each over the Trường Giang / Hoàng Hà class river systems in wuxia-archetype continents) = ~40 procedural Routes per 10k-cell continent at V1+30d default Medium density × ~2KB per Route struct serialized).
  CI gate: synthetic-dense-canonical stress test with 50 canonical_routes + 100 settlements verifies <500ms wall-clock + pair-uniqueness invariant + one-route-per-pair invariant (ROUTE-V8 enforces) + route-density-cap (1000 per continent V1+30d default via `geography.route_density_cap_exceeded` reject) NOT breached at ~40 routes/continent expected. **RiverNavigation count contributes ~38% of total** Routes; if archetype/world has minimal rivers (Arid / Desert continents), expect fewer Routes (~25 total).
```

**Why share `settlement_seed` substream tag pattern with POL/SET** (mirror of POL MED-3 + SET MED-3 substream discipline): stage 7's RNG (when probabilistic V1+30d+ extensions land) via `settlement_seed_substream(tag) = blake3(settlement_seed || tag)` with `b"stage7_route"` constant. V1+30d has no RNG consumer — Dijkstra + BFS + Brandes' are all deterministic. Substream tag reserved.

**Per ROUTE-Q1 — no dedicated `route_seed` sub-seed V1+30d**: GeographySeed sub-seed struct unchanged from GEO_001 V1 (master/voronoi/climate/erosion/political/settlement). Adding `route_seed: u64` would force GeographySeed struct shape change → world_geometry.schema_version bump (already at 3 post-ROUTE-001 HIGH-3-mirror-bump). Reusing settlement_seed substream tag avoids the additional bump. V1+30d+ can introduce `route_seed` via R3 additive evolution if procedural-route variation requires independent re-roll.

---

## §6 CreativeSeed authoring extension

ROUTE_001 V1+30d bumps `creative_seed.schema_version` 4 → 5 (2 additive fields; mirrors GEO_001b 1→2 + POL_001 2→3 + SET_001 3→4 precedent):

```rust
// Additive fields on CreativeSeed (v4 → v5 bump; ROUTE_001 V1+30d)
pub struct CreativeSeed {                                    // ... existing GEO_001 + GEO_001b + POL_001 + SET_001 fields elided ...
    pub schema_version: u32,                                 // V1 GEO_001 = 1; GEO_001b = 2; POL_001 = 3; SET_001 = 4; ROUTE_001 = 5
    pub route_seed_mode: RouteSeedMode,                     // V1+30d additive; reader default when absent: Hybrid (per R3 default-tolerant readers + I14 forward-compat)
    pub canonical_routes: Vec<CanonicalRouteDecl>,          // V1+30d additive; reader default when absent: empty Vec (legacy realities pre-ROUTE ship carry None which deserializes to []); activated when route_seed_mode != Procedural
}
```

**LLM-authoring contract:** ROUTE_001 V1+30d bumps LLM authoring template v3.tmpl → v4.tmpl (mirrors POL_001 v1→v2 + SET_001 v2→v3 precedent). New prompt-sections cover `route_seed_mode + canonical_routes` (with CanonicalRouteDecl shape including `SpatialPreference` for from/to positions — leveraging GEO_001b v2 14-variant enum for LLM-friendly route endpoint authoring). CreativeSeed v5 schemars-generated JSON Schema includes the 2 new fields so schema-constrained generation enforces them. Per §12Y.L2 governance, template version bump v3 → v4 requires CI fixture update; existing `authoring.template_version_deprecated` reservation activates at ROUTE ship to deprecate v3.tmpl.

---

## §7 Apply_delta total-function for 1 V1+30d DeltaKind + extensions to existing V1

Extends GEO_001 §7 + GEO_002 §7 + GEO_003 §7 `apply_delta` per-variant impl:

### 7.1 ReclassifyRoute

```rust
fn apply_reclassify_route(wg: &mut WorldGeometry, payload: &ReclassifyRoutePayload) -> () {
    // 1. Validate (ReferentialIntegrityGate at validator pipeline):
    //    - route_id exists in wg.routes (ROUTE-V3 route_not_found)
    //    - new_kind ∈ RouteKind closed enum (schema-level — handled by JSON deserializer)
    //    - new_kind != current_route.kind (ROUTE-V4 reclassify_no_change — wasted admin action; mirrors SET-V8 promote_settlement_no_change pattern)
    //    - if new_kind == SeaLane: both from_cell + to_cell MUST be coastal OR water cells (ROUTE-V5 sealane_inland_invalid — cannot reclassify a land Trail to SeaLane)
    //    - if new_kind == RiverNavigation: at least 3 consecutive cells along route path MUST have river_flux > river_threshold (ROUTE-V6 river_navigation_no_river — cannot reclassify to RiverNavigation if no navigable river exists)
    //    - if new_kind == MountainPass: from_cell + to_cell MUST be adjacent (single-edge); both cells biome ∈ {Mountain, Hill} (ROUTE-V7 mountain_pass_invalid_terrain)
    // 2. Update wg.routes[route_id].kind = new_kind.
    // 3. Update wg.routes[route_id].default_fiction_duration based on new_kind speed-modifier × existing distance_units (admin may compose ReclassifyRoute + V2+ UpdateRouteAttributes if duration override needed; V1+30d auto-recomputes per kind).
    // 4. Route.seed_source UNCHANGED (preserves audit trail of original placement).
}
```

**Validators:** `geography.route_not_found` (ROUTE-V3) · `geography.reclassify_no_change` (ROUTE-V4) · `geography.sealane_inland_invalid` (ROUTE-V5) · `geography.river_navigation_no_river` (ROUTE-V6) · `geography.mountain_pass_invalid_terrain` (ROUTE-V7).

### 7.2 Extensions to existing V1 AddRoute (capability migration)

V1 AddRoute V1 GEO_001 — apply_delta logic unchanged. ROUTE_001 V1+30d ADDS to its validator pipeline:
- AuthorizationGate now requires BOTH `can_edit_geography` AND `can_edit_route_geography` (per §9 capability migration).
- ROUTE-V8 pair-uniqueness: reject `geography.route_pair_collision` if a Route already exists with same canonical-order pair `(min(from_cell, to_cell), max(from_cell, to_cell))` regardless of kind (HIGH-1 fix /review-impl 2026-05-14 — pair canonicalization required since is_bidirectional=true V1+30d means (A, B) and (B, A) are logically the SAME pair; without canonicalization, ROUTE-V8 missed reverse-pair duplicates from AddRoute deltas + canonical-canonical declarations). Mirrors SET-V2 cell-uniqueness invariant. Defensive — V1 didn't have this check; admin could pre-ROUTE add 2 Routes per pair; ROUTE_001 V1+30d enforces one-route-per-pair WITH canonical-order normalization.
- ROUTE-V9 RouteKind-specific terrain check: same as ROUTE-V5/V6/V7 for ReclassifyRoute — e.g., AddRoute with kind=SeaLane MUST have coastal/water cells.

**MED-1 fix /review-impl 2026-05-14 — pre-ROUTE-ship pair-duplicate migration policy:** ROUTE-V8 is a NEW invariant V1+30d that pre-ROUTE-ship realities may violate (V1 admin could legally emit 2 AddRoute deltas with same (from_cell, to_cell) pair — the V1 schema didn't forbid it). At ROUTE ship, world-service runs a one-shot migration scan per reality:
1. For each reality, scan `world_geometry.routes` for canonical-order pair duplicates.
2. If duplicates found: KEEP newest (highest delta_id per Route.seed_source or insertion order); drop older duplicates via synthetic RemoveRoute deltas emitted by the migration job (audit-graded — appears in `geography_deltas` as RemoveRoute with `reason = "[ROUTE_001 V1+30d migration: pair-uniqueness invariant enforcement] dropped duplicate of route {newest_id} at canonical pair ({min_cell}, {max_cell})"`).
3. Migration is idempotent — re-running scans for duplicates again and finds none. Cohort rollout per §9 (staging 24h soak → production).
4. Realities with ZERO pre-ROUTE pair-duplicates: migration no-op (no synthetic deltas emitted).

### 7.3 Extensions to existing V1 RemoveRoute (capability migration)

V1 RemoveRoute V1 GEO_001 — apply_delta logic unchanged. ROUTE_001 V1+30d ADDS:
- AuthorizationGate now requires BOTH `can_edit_geography` AND `can_edit_route_geography`.
- ROUTE-V10 cascade-check: if removing a Route would orphan a settlement (e.g., the only route connecting a Hamlet to network), emit warning to ops dashboard (informational; doesn't reject — admin may intentionally isolate a settlement). V2+ could add `geography.route_orphan_settlement` reject if author UX demands.

---

## §8 Validation pipeline (ROUTE_001 V1+30d additive validators)

All extend GEO_001 §7 + GEO_002 §8 + GEO_003 §8 + 07_event_model EVT-V* pipeline. New validator slots register as sub-validators within `Forge:EditGeographyDelta` ReferentialIntegrityGate step:

| Validator | Stage | Reject rule_id |
|---|---|---|
| **ROUTE-V1** canonical-route-from-to-distinct | Stage 7 phase 1 + AddRoute delta | `geography.route_from_to_identical` (from_cell == to_cell — degenerate self-loop) |
| **ROUTE-V2** canonical-route-cells-valid | Stage 7 phase 1 + AddRoute delta | `geography.route_cell_unknown` (from_cell ∉ cells OR to_cell ∉ cells) |
| **ROUTE-V3** route-not-found | All 3 V1+30d DeltaKinds touching route_id | `geography.route_not_found` (route_id ∉ wg.routes; covers ReclassifyRoute + RemoveRoute) |
| **ROUTE-V4** reclassify-no-change | ReclassifyRoute delta | `geography.reclassify_no_change` (new_kind == current route.kind — wasted admin action) |
| **ROUTE-V5** sealane-inland-invalid | ReclassifyRoute + AddRoute delta (kind=SeaLane) | `geography.sealane_inland_invalid` (SeaLane requires coastal OR water cells at both endpoints) |
| **ROUTE-V6** river-navigation-no-river | ReclassifyRoute + AddRoute delta (kind=RiverNavigation) | `geography.river_navigation_no_river` (RiverNavigation requires ≥ 3 consecutive cells with river_flux > river_threshold along path) |
| **ROUTE-V7** mountain-pass-invalid-terrain | ReclassifyRoute + AddRoute delta (kind=MountainPass) | `geography.mountain_pass_invalid_terrain` (MountainPass requires adjacent Mountain/Hill cells) |
| **ROUTE-V8** route-pair-collision | AddRoute delta + Phase 1 canonical + stage 7 phase 2-5 procedural + Phase 6 RiverNavigation inline | `geography.route_pair_collision` (Route already exists for canonical-order pair `(min(from_cell, to_cell), max(from_cell, to_cell))` regardless of kind; HIGH-1 fix /review-impl 2026-05-14 — canonical-order pair normalization required since is_bidirectional=true V1+30d makes (A, B) ≡ (B, A); validator applies at EVERY emission path uniformly) |
| **ROUTE-V9** route-disconnected-graph | Stage 7 phase 2 Dijkstra | (informational — no reject; pairs with no land-path skip Road emission per §5.2 step 5c; ops dashboard records under-connect metric) |
| **ROUTE-V10** route-cascade-orphan | RemoveRoute delta | (informational — warning only; admin may intentionally isolate settlement; V2+ may add `geography.route_orphan_settlement` reject if author UX demands) |
| **ROUTE-V11** route-edit-capability | All route-touching DeltaKinds — AuthorizationGate | `geography.route_edit_capability_required` (capability JWT missing `can_edit_route_geography`) |
| **ROUTE-V12** sealane-range-exceeded | Stage 7 phase 4 + AddRoute SeaLane | `geography.sealane_range_exceeded` (Euclidean distance > max_sealane_range = 0.5 of continent diameter V1+30d; prevents unrealistic open-ocean routes) |
| **ROUTE-V13** route-density-cap | Stage 7 procedural | `geography.route_density_cap_exceeded` (total route count > 1000 per continent V1+30d; defensive against pathological canonical_routes flood) |
| **ROUTE-V14** route-seed-mode-valid | RealityBootstrapper / stage 7 setup | `geography.route_seed_mode_invalid` (schema-level — closed-enum tampering at JSON deserialization; defensive) |

ContentSafetyGate (§12X.L7 PII scrub regardless per D-S04-4 GEO_001 fix cycle approval): applied to `delta.reason` on ReclassifyRoute + AddRoute + RemoveRoute LocalizedName/I18nBundle fields.

---

## §9 DP primitives + capability

ROUTE_001 V1+30d introduces no new DP primitives. All writes flow through GEO_001's existing path:

- `dp.t2_write::<WorldGeometry>(channel_id, ...)` — extends existing GEO_001 + POL_001 + SET_001 T2 write
- `dp.subscribe_channel_events_durable::<WorldGeometryEvent>(channel_id, ...)` — consumed by MAP_001 V1+ (route geometry → map overlay rendering) + TVL_001 V1+ (route graph → travel pathfinder cache)

**Capability addition** (extends `_boundaries/02_extension_contracts.md` §3 capability JWT):

- `can_edit_route_geography: bool` (claim) — required by EVT-T8 AuthorizationGate for ReclassifyRoute (V1+30d new) + AddRoute (V1 existing; ROUTE-ship migration) + RemoveRoute (V1 existing; ROUTE-ship migration).
- Disjoint from `can_edit_political_geography` (POL_001) + `can_edit_settlement_geography` (SET_001). Admin tools that edit BOTH political + settlement + routes need all 3 claims (V1+30d post-ROUTE-ship: 4-claim bundle including legacy `can_edit_geography` for biome/region edits).
- **Capability migration plan at ROUTE ship** (mirrors POL_001 MED-6 + SET_001): auth-service one-shot migration auto-grants `can_edit_route_geography` to all currently-active `can_edit_geography` holders. `forge.roles_version` bumps per PLT_001 §6.3. Post-migration, future Forge admins receive `can_edit_geography + can_edit_political_geography + can_edit_settlement_geography + can_edit_route_geography` as a quad-paired bundle at role-grant time (PLT_001 RBAC config V1+30d adds the 4-pairing). Roll-out: staging realities migrate first; production realities migrate after 24h soak.
- **ImpactClass per variant** (per S5 discipline):
  - `ReclassifyRoute` → **Tier 2 ImpactClass=Griefing** (reversible — admin can reclassify back; matches SET PromoteSettlement V1+30d + AddRoute V1 precedent).
  - `AddRoute` (existing V1) → **Tier 2 ImpactClass=Griefing** per GEO_001 §7 (unchanged).
  - `RemoveRoute` (existing V1) → **Tier 1 ImpactClass=Destructive** per GEO_001 §7 (unchanged — irrecoverable route deletion; double-approval required).

Subscribe path: ROUTE_001 V1+30d emissions appear as `EVT-T3 Derived aggregate_type=world_geometry` events; existing GEO_001 + POL_001 + SET_001 subscribers automatically receive ROUTE field updates (route changes), no new subscribe contract needed.

---

## §10 Composition with foundation siblings

ROUTE_001 V1+30d composes within existing GEO_001 + POL_001 + SET_001 composition contracts; one critical new coordination point with SET_001:

| Sibling | Composition with ROUTE_001 |
|---|---|
| **GEO_001** | Schema parent; ROUTE_001 V1+30d populates GEO_001 §3.1 schema-reserved `routes: Vec<Route>` field. No GEO_001 schema change. |
| **GEO_001b** | LLM authoring contract; ROUTE_001 V1+30d activates within CreativeSeed v5 additively (route_seed_mode + canonical_routes). LLM authoring template v3.tmpl → v4.tmpl bump. CanonicalRouteDecl leverages GEO_001b v2 SpatialPreference enum for LLM-friendly route endpoint authoring. |
| **GEO_002 POL_001** | Sibling V1+30d; **soft coordination**: ROUTE stage 7 reads POL stage 5 output (province graph + state.capital_settlement_id) for canonical-route prioritization — canonical routes connecting state capitals are V1+30d-implicit "Imperial Highway" pattern. Cross-province Roads are tagged for V2+ STRAT_001 supply-line modeling. No POL_001 schema change. |
| **GEO_003 SET_001** | **Critical sibling V1+30d coordination**: ROUTE stage 7 runs AFTER SET stage 6 — needs settlements for Dijkstra source/sink pairs. Stage 7a Road operates on R = { s : s.population_tier ≥ 2 }; Stage 7b Trail operates on T = { s : s.population_tier ∈ [0, 1] }; Stage 7c SeaLane operates on coastal-City subset. **Capability bundle** (auth-service): quad-pair (`can_edit_geography + can_edit_political_geography + can_edit_settlement_geography + can_edit_route_geography`) at role-grant time post-ROUTE ship. ROUTE.from_cell / to_cell index into cells, NOT directly into settlements — but the algorithmic source/sink pairs ARE settlement-derived. SET-001 changes (RelocateSettlement / RemoveSettlement) may invalidate routes whose endpoint cells were settlements: V1+30d acceptable (route remains valid as a cell-pair connection even if no settlement at endpoint); V2+ admin pattern: emit RemoveSettlement → cascade RemoveRoute via admin UI bundling (tracked SET-D10 BundleDeltas). |
| **MAP_001** | V1+30d ROUTE_001 stage 7 outputs (route geometry) feed MAP_001 V1+ visual overlay rendering — map UI draws Roads (solid lines), Trails (dashed), SeaLanes (dotted blue), MountainPass (red triangle markers). No MAP_001 schema change; visual layer reads ROUTE-populated data. |
| **PF_001** | V1+30d cross-ref: PF-D7 procedural place generation may consume route-cell context for PlaceType bias (Road-passing cell → Caravanserai / Toll PlaceType bias; SeaLane cell → Harbor PlaceType bias). No PF_001 schema change V1+30d; tracked as future composition deferral. |
| **CSC_001** | V1+30d cross-ref: route-anchor cells get richer skeleton selection — Road cell → Highway skeleton; SeaLane cell → Wharf skeleton (extends CSC_001 V1+30d biome+role-driven skeleton catalog with route-driven variants). |
| **EF_001** | No direct composition. Routes are cell-pair edges; entities live in cells (not on edges). |
| **RES_001** | V2+ Trade-good flow modeling — Roads + SeaLanes determine inter-settlement resource flow rates. SET_001 V2+ + RES_001 V2+ + ROUTE_001 V2+ compose into the trade-economy substrate. V1+30d schema only (no consumption). |
| **PROG_001** | No direct composition V1+30d. |
| **TIT_001** | V1+30d cross-ref: titles like "Lord of the Northern Trade Route" CAN reference Route geometry once ROUTE ships. No V1+30d schema integration; documentation cross-ref only. V2+ TIT_001 route-binding via TitleBinding::Standalone surfaces. |
| **TVL_001 V1+** | **Primary consumer**. Reads Route graph for inter-settlement movement modeling: route.kind → travel-speed modifier; route.distance_units + route.default_fiction_duration → time-cost; route.is_bidirectional → reverse-traversal allowed. ROUTE_001 V1+30d is the dependency unblocker for TVL_001 V1+ launch. |
| **STRAT_001 V2+** | Consumer. Reads Route graph for supply-line + invasion-path + siege-encirclement modeling. STRAT_001 spec lands V2+. |
| **future GEO_005 V2+** | V2+ resource distribution generator may consume Route graph for trade-flow modulation (Road-connected provinces share resource-prices; isolated provinces have price-divergence). |

---

## §11 RealityManifest extension

**No new RealityManifest field.** ROUTE_001 V1+30d extends `creative_seed` (per §6 — adds `route_seed_mode + canonical_routes`) which is already inside `RealityManifest.continent_geometries[i].creative_seed` per GEO_001 §11. The CreativeSeed v5 schema absorbs ROUTE_001's fields additively per R3.

Bootstrap order extends GEO_001 §11 + POL_001 §11 + SET_001 §11:
1. DP create_channel (continent + cells)
2. RealityBootstrapper EVT-T4 GeographyBorn per continent
3. world-service materializes WorldGeometry:
   - V1 stages 1-4 (geometry / climate / biome+river)
   - V1+30d POL stage 5 (political growth + state.capital_province_id assignment)
   - V1+30d SET stage 6 (settlement placement + Province.capital_settlement_id linkage)
   - **V1+30d ROUTE stage 7 (route network multi-pass 7a-7d — THIS commit's activation)**
   - V1+30d POL stage 8 (culture spread)
4. Apply initial `geography_deltas` (per CreativeSeed declaration + Forge-pre-bootstrap canonical deltas)
5. Persist as T2/Channel-continent aggregate (now includes populated routes alongside POL + SET layers)

V1+30d feature-flag: `services/world-service` config `route_network_generator_enabled: bool` (default true V1+30d; false V1 backward-compat for realities bootstrapping pre-ROUTE_001 ship). Mid-life feature-flag flip on existing reality: **FORBIDDEN** — per GEO_001 §3 `generator_pipeline_version` discipline.

---

## §12 Failure UX — extends `geography.*` namespace

ROUTE_001 V1+30d adds **10 V1+30d rule_ids** under the existing `geography.*` namespace owned by GEO_001 (per ROUTE-D7 — share namespace, no new prefix carving). Total `geography.*` after ROUTE_001 V1+30d ships: **58 V1+30d** (13 V1 GEO_001 + 20 V1+30d POL_001 + 15 V1+30d SET_001 + 10 V1+30d ROUTE_001).

Also LIFTS V1's `geography.layer_activation_deferred_v1` reject for the route layer specifically: when `services/world-service` runs at ROUTE ship time, route runtime writes via stage-7 / 1-new-DeltaKind / existing AddRoute+RemoveRoute paths NO LONGER reject this rule_id. **V1+30d activation triangle complete** — political / settlement / route layers all activated; only V2+ resource layer remains deferred.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d) | English fallback |
|---|---|---|---|---|
| `geography.route_from_to_identical` | schema | Stage 7 phase 1 + AddRoute | "Tuyến đường không thể có cùng điểm đầu và cuối." | "Route from_cell and to_cell cannot be identical (self-loop)." |
| `geography.route_cell_unknown` | schema | Stage 7 phase 1 + AddRoute | "Ô không tồn tại trong địa lý." | "Route from_cell or to_cell not in cells set." |
| `geography.route_not_found` | schema | ReclassifyRoute + RemoveRoute | "Không tìm thấy tuyến đường được nêu." | "Route ID not found." |
| `geography.reclassify_no_change` | user | ReclassifyRoute delta | "Phải thay đổi loại tuyến đường khác với hiện tại." | "ReclassifyRoute requires new_kind different from current." |
| `geography.sealane_inland_invalid` | user | ReclassifyRoute + AddRoute (kind=SeaLane) | "Hải đạo yêu cầu cả hai điểm phải ở ven biển hoặc trên biển." | "SeaLane requires coastal or water cells at both endpoints." |
| `geography.river_navigation_no_river` | user | ReclassifyRoute + AddRoute (kind=RiverNavigation) | "Đường sông yêu cầu ít nhất 3 ô liên tiếp có lưu lượng đủ lớn." | "RiverNavigation requires ≥3 consecutive cells with river_flux above threshold." |
| `geography.mountain_pass_invalid_terrain` | user | ReclassifyRoute + AddRoute (kind=MountainPass) | "Đèo núi yêu cầu hai ô kề nhau thuộc Núi hoặc Đồi." | "MountainPass requires adjacent Mountain/Hill cells." |
| `geography.route_pair_collision` | user | AddRoute delta + stage 7 procedural | "Hai điểm này đã có tuyến đường khác." | "Route already exists for this cell pair (V1+30d one-route-per-pair invariant)." |
| `geography.sealane_range_exceeded` | user | Stage 7 phase 4 + AddRoute SeaLane | "Hải đạo vượt phạm vi cho phép (0.5 đường kính lục địa)." | "SeaLane exceeds max range (0.5 of continent diameter)." |
| `geography.route_density_cap_exceeded` | schema | Stage 7 procedural | "Tổng số tuyến đường vượt giới hạn (1000 mỗi lục địa)." | "Total route count exceeds cap (max 1000 per continent)." |
| `geography.route_edit_capability_required` | user | All route DeltaKinds AuthorizationGate | "Bạn không có quyền chỉnh sửa tuyến đường." | "Missing route geography edit capability." |
| `geography.route_seed_mode_invalid` | schema | RealityBootstrapper / stage 7 setup | "Cấu hình chế độ phát sinh tuyến đường không hợp lệ." | "Route seed mode invalid (closed-enum tampering at deserialization)." |

V1+30d schema-level rejects (5): route_from_to_identical / route_cell_unknown / route_not_found / route_density_cap_exceeded / route_seed_mode_invalid.
V1+30d user-facing rejects (7): the rest.

V2+ reservations (NEW): `geography.route_narrative_proposal_pending` (V2+ T6 NarrativeRouteEdit Generator review); `geography.route_orphan_settlement` (V2+ defensive — RemoveRoute that would isolate settlement per ROUTE-V10 future activation).

---

## §13 Cross-service handoff

| Service | Role | V1+30d status |
|---|---|---|
| **world-service** | Authoritative owner — runs stage 7 at bootstrap; applies ReclassifyRoute + V1 AddRoute/RemoveRoute with V1+30d migration; persists aggregate | V1+30d |
| **glossary-service** | Stores CanonicalRouteDecl names + canon_ref backlinks (same pattern as canonical_settlements + canonical_provinces + canonical_states) | V1+30d |
| **chat-service** (S9 prompt-assembly) | Read-only consumer — `[GEOGRAPHIC_CONTEXT]` joins nearest_route_kind + route_origin/destination per cell (in addition to POL_001's province/state/culture_tag + SET_001's nearest_settlement) | V1+30d |
| **api-gateway-bff** | Routes Forge UI POSTs for V1+30d ReclassifyRoute + V1 AddRoute/RemoveRoute → world-service; player map UI GETs populated routes for visual overlay | V1+30d Forge UI |
| **auth-service** | Capability migration: one-shot grant `can_edit_route_geography` to all current `can_edit_geography` holders at ROUTE ship; quad-pair claim bundle at role-grant time | V1+30d migration |
| **knowledge-service** | Reads Route graph for inter-entity travel-history knowledge graph (planned V1+ knowledge-service activation) | Not V1+30d |
| **TVL_001 service V1+** | **Primary consumer** — Route graph feeds travel-speed + cost calculations for inter-settlement movement. TVL_001 V1+ depends on ROUTE_001 V1+30d shipping. | V1+ |
| **STRAT_001 service V2+** | Future consumer for supply-line + invasion-path modeling | V2+ |

No new service introduced. All V1+30d implementation fits inside `world-service` extension + auth-service migration job + read-only consumers.

---

## §14 Multiverse inheritance

ROUTE_001 V1+30d inherits GEO_001 §9 fork-inheritance contract unchanged. Snapshot fork at event E:

- Parent's `route_layer` (routes populated via stage 7 at parent bootstrap) copied bit-exactly into child.
- Parent's V1+30d ROUTE DeltaKinds (ReclassifyRoute) + V1 AddRoute/RemoveRoute applied up to fork-point copied as part of `geography_deltas[..fork_point]`.
- Child appends new V1+30d ROUTE DeltaKinds locally; parent's post-fork DeltaKinds do NOT cascade.
- L1/L2 cascade: if author edits `creative_seed.canonical_routes[i]` at L2, both parent and child see new value UNLESS child has L3-scoped DeltaKind override on the same route.

Determinism preserved: same `(settlement_seed, creative_seed_snapshot, generator_pipeline_version, POL stage 5 outputs, SET stage 6 outputs, fork_point_delta_count)` → bit-identical routes across parent and child at fork point.

---

## §15 Sequences

### 15.1 Hybrid bootstrap — Yên Vũ Lâu wuxia setting (V1+30d activation triangle complete: POL + SET + ROUTE all active)

```
RealityManifest.continent_geometries[0].creative_seed = {
  archetype: Wuxia, world_scale: Region (~2048 cells), hemisphere: Northern, coastline: Coastal,
  political_seed_mode: Hybrid,
  canonical_states: [Tống, Liêu],
  canonical_provinces: [{ name: "Lương Châu", ...}, { name: "Yên Vân", ...}, ...6 entries],
  canonical_settlements: [{ name: "Tương Dương", role: Capital, ...}, { name: "Khai Phong", ...}, { name: "Yên Vũ Lâu", ...}, ...7 entries],
  canonical_routes: [
    { from_position: NearSettlement("Khai Phong"), to_position: NearSettlement("Tương Dương"), kind: Road, canon_ref: Some(...) },  // canonical Imperial Highway
    { from_position: NearSettlement("Tương Dương"), to_position: NearSettlement("Yên Vũ Lâu"), kind: Road, canon_ref: Some(...) },  // canonical wuxia trade road
  ],
  culture_hints: [han_jiangnan@(0.30,0.40), qidan@(0.75,0.15)],
  settlement_seed_mode: Hybrid, settlement_density_hint: Medium,
  route_seed_mode: Hybrid,                                       // ROUTE_001 V1+30d
  schema_version: 5,                                             // CreativeSeed v5 per ROUTE-001 bump
  ...
}
  ↓ Stages 1-4 run (GEO_001 V1; ~50ms)
  ↓ Stage 5 (POL V1+30d): provinces=10, states=3 (Tống / Liêu / Tây Cương_State_a3f9c2); ~85ms
  ↓ Stage 6 (SET V1+30d): settlements=10 (3 canonical Capital/City/Town + 7 procedural); Province.capital_settlement_id populated; ~30ms
  ↓ Stage 7 (ROUTE V1+30d):
    Phase 1 canonical placement: 2 canonical_routes resolved — "Khai Phong-Tương Dương" Road snaps to Khai Phong.cell ↔ Tương Dương.cell;
      Dijkstra over TerrainCost yields path-cost = 24 (passes through Plain cells); distance_units = 24, default_fiction_duration = 24h OnFoot.
      "Tương Dương-Yên Vũ Lâu" Road similarly placed (distance_units = 8, ~8h OnFoot). 2 canonical Roads emitted; ~10ms.
    Phase 2 procedural Road (Stage 7a): Road-eligible settlements R = { Tương Dương (tier 5), Khai Phong (tier 5), Yên Vũ Lâu (tier 3), 2 procedural Cities (tier 4) } = 5 settlements. Pair-count = 5C2 = 10 pairs; 2 already canonical → 8 procedural pairs.
      Dijkstra over each pair; ~30ms wall-clock; 8 procedural Roads emitted (some pairs may overlap canonical paths — pair-uniqueness check passes since (from_cell, to_cell) tuples are distinct).
    Phase 3 procedural Trail (Stage 7b): Trail-eligible settlements T = { 5 procedural Hamlets/Villages (tier 0-1) }. For each, find nearest larger settlement by TerrainCost; emit Trail. 5 Trails emitted; ~5ms.
    Phase 4 SeaLane (Stage 7c): Coastal-City set C = { Tương Dương (coastal), 1 procedural coastal-City }. 1 pair; BFS over water cells; SeaLane emitted between them via coastal cells; ~5ms.
    Phase 5 MountainPass (Stage 7d): Brandes' edge-betweenness on Mountain/Hill cell-edge graph (~150 mountain cells in this continent → ~200 edges). Top 5 betweenness edges → 5 MountainPass routes; ~8ms.
    Phase 6 RiverNavigation inline: 2 Road paths pass through ≥3-consecutive-cell river segments (Trường Giang); 2 parallel RiverNavigation routes auto-emitted alongside their Roads; ~2ms.
    Total stage 7: ~60ms. Routes emitted: 2 canonical + 8 procedural Road + 5 Trail + 1 SeaLane + 5 MountainPass + 2 RiverNavigation = 23 Routes.
  ↓ Stage 8 (POL culture spread V1+30d): culture_regions populated; state.culture_tag derived; ~40ms.
  ↓ WorldGeometry persisted: provinces=10, states=3, settlements=10, routes=23, culture_regions=2.
  ↓ Prompt-assembly for cell:yen_vu_lau journey-context joins nearest_route="Tương Dương-Yên Vũ Lâu Road" + route_kind=Road + state_name="Tống triều" + nearest_settlement="Yên Vũ Lâu" + culture_tag="han_jiangnan" → [GEOGRAPHIC_CONTEXT] = "trên đường lớn Tương Dương-Yên Vũ Lâu (Road), thị trấn Yên Vũ Lâu, văn hóa Hán-Giang Nam, tỉnh Lương Châu (Tống triều)"
    LLM grounded with concrete route name + kind — closes the LLM-context route-grounding gap §1 Gap 2 named.
```

### 15.2 Forge ReclassifyRoute — Trail upgraded to Road after Imperial decree

```
Forge:EditGeographyDelta { delta_kind: ReclassifyRoute {
    route_id: tieu_thon_trail_id,                              // currently Trail kind connecting Hamlet to Town
    new_kind: SettlementRole::Road,
    reason: "Hoàng đế ban chiếu xây đường lớn nối Tống triều phương nam...50+ char" },
    prev_delta_id: <last>, ... }
  ↓ EVT-T8 validator pipeline (ROUTE_001 V1+30d):
    AuthorizationGate (has can_edit_route_geography claim per ROUTE-V11) → SchemaGate → ReferentialIntegrityGate
    (ROUTE-V3 route_id exists → pass;
     ROUTE-V4 new_kind != current Trail → pass;
     ROUTE-V5 sealane check — new_kind is Road not SeaLane → skip;
     ROUTE-V6 river check — new_kind is Road not RiverNavigation → skip;
     ROUTE-V7 mountain check — new_kind is Road not MountainPass → skip)
    → OrderingGate → ContentSafetyGate (reason scrubbed per D-S04-4) → all pass.
  ↓ EVT-T3 Derived: apply_reclassify_route(wg, payload):
    - wg.routes[tieu_thon_trail_id].kind = Road
    - wg.routes[tieu_thon_trail_id].default_fiction_duration recomputed: distance_units × Road-speed (1 league/hour) instead of × Trail-speed (0.6 league/hour) → new duration shorter
    - Route.seed_source UNCHANGED (audit preserved: still Procedural { Stage7b_Trail, rank=3 } even though now reclassified Road)
    - geography_deltas.push(delta_entry)
  ↓ TVL_001 V1+ (when ships) sees route.kind change; travel-speed calculations use new Road modifier.
  ↓ Prompt-assembly cells along this route now show route_kind=Road instead of Trail.
```

### 15.3 Forge AddRoute reject — capability missing

```
Forge admin holds can_edit_geography only (not can_edit_route_geography post-ROUTE-ship).
Forge:EditGeographyDelta { delta_kind: AddRoute { from_cell: 500, to_cell: 800, kind: Road, ... }, ... }
  ↓ EVT-T8 validator pipeline (post-ROUTE-ship migration):
    AuthorizationGate (ROUTE-V11): admin lacks can_edit_route_geography → reject geography.route_edit_capability_required.
  ↓ UI surfaces Vietnamese reject copy: "Bạn không có quyền chỉnh sửa tuyến đường."
  ↓ Admin must request capability grant from PLT_001 RBAC (auth-service one-shot migration already auto-granted to all
    can_edit_geography holders at ROUTE ship — this admin is a NEW grantee post-ROUTE-ship who didn't receive the
    initial migration. Re-issuance flow per PLT_001 §6.3.)
```

### 15.4 Snapshot fork — child inherits route layer + appends locally

```
Parent reality R_alpha at event E has WorldGeometry with 23 routes (per §15.1 bootstrap).
Player creates fork at event E → child reality R_beta.
  ↓ DP SnapshotForker emits GeographyForkInherited per continent (EVT-T4 System per GEO_001 §2.5 MED-2 fix).
  ↓ Child R_beta WorldGeometry: seed/creative_seed identical to parent (immutable per GEO_001 §3); routes copied
    bit-exactly (23 routes); geography_deltas copied up to fork-point.
  ↓ R_beta admin emits ReclassifyRoute (Trail→Road on tieu_thon route); R_alpha emits independent ReclassifyRoute (different route).
  ↓ Both diverge: R_beta.routes[tieu_thon].kind=Road; R_alpha.routes[tieu_thon].kind=Trail (unchanged).
    No cross-pollination. Save state stable across both forks.
```

---

## §16 Acceptance criteria

15 V1+30d-testable acceptance scenarios. LOCK granted when ≥10 pass integration tests against POL+SET+ROUTE reference module in `world-service`.

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-ROUTE-1** | Bootstrap continent with 2 canonical_routes (Imperial Highway segments) + `route_seed_mode=Hybrid`, post POL + SET stages → routes.len() in [15, 30] (2 canonical + ~13 procedural across Road/Trail/SeaLane/MountainPass/RiverNavigation); every Road route has both endpoints settlement.population_tier ≥ 2; every Trail has at least one endpoint settlement.population_tier ∈ [0, 1]; pair-uniqueness invariant holds. | — |
| **AC-ROUTE-2** | Bootstrap with same `(settlement_seed, creative_seed, pipeline_version, POL stage 5 outputs, SET stage 6 outputs)` on second continent → byte-identical routes (replay determinism per EVT-A9). | — |
| **AC-ROUTE-3** | Bootstrap with `route_seed_mode=Canonical`, 5 canonical_routes → routes.len() == 5 (no procedural fill); Hamlets without canonical-route coverage have no Trail connection (V1+30d acceptable). | — |
| **AC-ROUTE-4** | Bootstrap with `route_seed_mode=Procedural`, canonical_routes declared but ignored → routes generated entirely by stages 7a-7d; canonical declarations unused. | — |
| **AC-ROUTE-5** | Forge admin emits ReclassifyRoute with new_kind == current route.kind → reject. | `geography.reclassify_no_change` |
| **AC-ROUTE-6** | Forge admin emits ReclassifyRoute (target Trail, new_kind=SeaLane) on an inland route (both cells land, not coastal) → reject. | `geography.sealane_inland_invalid` |
| **AC-ROUTE-7** | Forge admin emits ReclassifyRoute (target Road, new_kind=RiverNavigation) where route path has < 3 consecutive cells with river_flux > threshold → reject. | `geography.river_navigation_no_river` |
| **AC-ROUTE-8** | Forge admin emits ReclassifyRoute (target Trail, new_kind=MountainPass) on a non-adjacent route (path > 1 cell) → reject. | `geography.mountain_pass_invalid_terrain` |
| **AC-ROUTE-9** | Forge admin emits AddRoute with from_cell == to_cell → reject. | `geography.route_from_to_identical` |
| **AC-ROUTE-10** | Forge admin emits AddRoute with from_cell ∉ cells (out of bounds) → reject. | `geography.route_cell_unknown` |
| **AC-ROUTE-11** | Forge admin emits AddRoute for a pair where a Route already exists (any kind), tested via BOTH same-order `(from=A, to=B)` AND reverse-order `(from=B, to=A)` per HIGH-1 fix — both cases reject. | `geography.route_pair_collision` |
| **AC-ROUTE-12** | Forge admin holds `can_edit_geography` but NOT `can_edit_route_geography` → emits ReclassifyRoute → reject at AuthorizationGate. | `geography.route_edit_capability_required` |
| **AC-ROUTE-13** | Forge admin emits AddRoute with kind=SeaLane and Euclidean distance > 0.5 of continent diameter → reject. | `geography.sealane_range_exceeded` |
| **AC-ROUTE-14** | Stage 7 procedural runs on a continent with 100+ canonical_routes pre-placed + Dense density → procedural caps at 1000 total routes per continent. | `geography.route_density_cap_exceeded` |
| **AC-ROUTE-15** | Snapshot fork at event E where parent has stage-7 outputs + 2 V1+30d ROUTE DeltaKinds applied → child world_geometry has identical routes + 2 deltas; child appends ReclassifyRoute locally; parent appends AddRoute; both diverge correctly with no cross-pollination. | — |

---

## §17 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **ROUTE-D1** | Sub-cell route geometry (route waypoints, segment shapes, sub-cell road curvature) | V2+ | V1+30d focus is on the route *graph* (cell-pair edges); sub-cell geometry is rendering concern owned by MAP_001 V2+ visual layer. |
| **ROUTE-D2** | V2+ T6 LLM route-evolution proposal (`ROUTE:NarrativeRouteEdit` Generator — LLM observes narrative events and proposes Add/Remove/Reclassify) | V2+ | Parallel to POL-D2 + SET-D2 + GEO-D12; LLM proposes route changes based on narrative; Forge admin reviews via T8. |
| **ROUTE-D3** | One-way routes (`is_bidirectional = false` activation) | V1+30d+ | V1+30d all routes bidirectional. V1+30d+ for scenic one-way mountain passes, fast-flowing one-way rivers. |
| **ROUTE-D4** | V2+ route-graph derived adjacency (compute "neighbor settlements" from route graph for TVL_001 V1+ queries) | V1+30d+ | Useful for TVL_001 V1+ pathfinding; not V1+30d-blocking (consumer derives at read time). |
| **ROUTE-D5** | V2+ UpdateRouteAttributes admin DeltaKind (distance_units / default_fiction_duration tuning) | V2+ | Rare admin pattern; deferred until canonical canon-event surfaces (e.g., "Tống canonized the Silk Road as exactly 1500 leagues per canonical text"). |
| **ROUTE-D6** | V2+ MergeRoutes admin DeltaKind (combine 2 adjacent routes into a single long-route entity) | V2+ | Rare admin pattern. |
| **ROUTE-D7** | V2+ SplitRoute admin DeltaKind (split a route at an intermediate cell into 2 sub-routes) | V2+ | Rare admin pattern. |
| **ROUTE-D8** | V2+ multi-route-per-pair (Road + SeaLane both connecting same coastal Cities) | V2+ | V1+30d strict one-route-per-pair. V2+ for realistic dual-network coastal trade modeling. |
| **ROUTE-D9** | V2+ route-quality tiers (Royal Road / Provincial Road / Local Road as Road sub-classifications) | V2+ | Wuxia worlds may want road hierarchy; V1+30d uses single Road kind. R3 additive enum bump when needed. |
| **ROUTE-D10** | V1+30d+ probabilistic route-variation (RNG-driven variation in procedural route paths for replay diversity) | V1+30d+ | Currently fully deterministic; substream tag `b"stage7_route"` reserved. |
| **ROUTE-D11** | V2+ inter-continent Road via SeaLane bridge (multi-continent worlds — coastal-Capital pairs across continents get implicit SeaLane Road) | V2+ | Coupled with GEO-D11 multi-continent. |
| **ROUTE-D12** | V2+ route-resource flow modeling (Trade-good capacity per route) | V2+ | Coupled with RES_001 V2+ trade-economy substrate. |
| **ROUTE-D13** | V2+ route-orphan-settlement detection (reject RemoveRoute if it isolates a settlement) — ROUTE-V10 future activation | V2+ | Currently informational warning only. |

---

## §18 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **ROUTE-Q1** | Should ROUTE_001 introduce a dedicated `route_seed: u64` sub-seed in GeographySeed, or share `settlement_seed` via substream? | V1+30d: share `settlement_seed` via substream tag `b"stage7_route"`. Reason: stage 7 algorithm is fully deterministic V1+30d (Dijkstra + BFS + Brandes' — no RNG); substream tag is reserved for V1+30d+ probabilistic extensions. Adding `route_seed` would force GeographySeed struct shape change → world_geometry.schema_version bump (already bumped 1→2 by SET_001; ROUTE_001 V1+30d schema bumps 2→3 only for the additive Settlement.seed_source-parallel Route.seed_source field — adding `route_seed` would compound the bump). Defer dedicated route_seed to V1+30d+ ROUTE-D10. |
| **ROUTE-Q2** | Edge-betweenness algorithm scaling: 10k cells × ~150 mountain cells × Brandes' O(VE) = ~22.5k operations per continent. Adequate for V1+30d 10k cells; concern at V3 16k cells with high mountain ratio? | V1+30d: Brandes' is fine (~50ms worst-case). V2+ may need approximation algorithms (random-sampling betweenness) if continents grow to 50k+ cells. |
| **ROUTE-Q3** | RiverNavigation auto-emit: should the parallel RiverNavigation Route REPLACE the underlying Road segment, or coexist? | V1+30d: coexist (TVL_001 V1+ traversal logic picks land OR river based on actor preferences + canon flavor). Replacement strategy V2+ if author UX surfaces complaints. |
| **ROUTE-Q4** | mountain_pass_target = 5 V1+30d default — tunable per continent or per archetype? | V1+30d: fixed 5. V2+ adds `creative_seed.mountain_pass_density: usize` if author UX needs control. |
| **ROUTE-Q5** | Storage representation: monolithic `Vec<Route>` matches GEO_001 + POL_001 + SET_001 pattern. OR per-route SQL table for spatial queries? | V1+30d: monolithic (~30KB / continent fine). V2+ STRAT_001 may force denormalization for route-graph SQL; revisit then. |

---

## §19 Cross-references

- [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — catalog extended with ROUTE-* sub-prefix
- [`_index.md`](_index.md) — folder index; GEO_004 row added 2026-05-14
- [`GEO_001`](GEO_001_world_geometry.md) — schema parent (§3.1 Route + §4.4 RouteKind + §4.5 GeographyDeltaKind AddRoute/RemoveRoute V1 + §5 stage 7 algorithm baseline + §16 GEO-D4 deferral activated here)
- [`GEO_001b`](GEO_001b_authoring_flow.md) — CreativeSeed authoring sibling; ROUTE_001 additive within v5 schema (route_seed_mode + canonical_routes); template v3.tmpl → v4.tmpl bump; SpatialPreference 14-variant enum reused for CanonicalRouteDecl
- [`GEO_002 POL_001`](GEO_002_political_layer.md) — sibling V1+30d; soft coordination (canonical-route prioritization between state capitals via Province graph)
- [`GEO_003 SET_001`](GEO_003_settlement_generator.md) — critical sibling V1+30d; stage 6 (SET) runs before stage 7 (ROUTE); ROUTE consumes Settlement graph for Dijkstra source/sink pairs
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `world_geometry` annotation extended for ROUTE_001 V1+30d activation
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — `geography.*` namespace extended with 10 V1+30d ROUTE rule_ids (§1.4); GeographyDeltaKind closed-enum bump 12 V1+30d → 13 with V1+30d active (§1); capability `can_edit_route_geography` added (§3)
- [`_boundaries/99_changelog.md`](../../_boundaries/99_changelog.md) — DRAFT 2026-05-14 entry top-anchored
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) — EVT-T3 / T8 sub-shapes unchanged (ROUTE_001 reuses GEO_001 + POL_001 + SET_001 registrations)
- [`features/00_map/MAP_001_map_foundation.md`](../00_map/MAP_001_map_foundation.md) — visual overlay layer reads ROUTE-populated data for line rendering (Road solid / Trail dashed / SeaLane dotted / MountainPass triangle markers)
- [`features/00_place/PF_001_place_foundation.md`](../00_place/PF_001_place_foundation.md) — V1+30d cross-ref: PF-D7 procedural place generation V1+30d may consume route-cell context (Caravanserai / Toll / Harbor PlaceType bias); no V1+30d schema integration
- [`features/03_actor_substrate/TIT_001_title_foundation.md`](../03_actor_substrate/TIT_001_title_foundation.md) — V1+30d cross-ref: titles can reference Route geometry post-ROUTE ship
- *future* TVL_001 — primary consumer; depends on ROUTE_001 V1+30d shipping for inter-settlement travel modeling

---

## §20 Implementation readiness

**Design layer (this commit):** ✅ schema activation contract + 1 V1+30d DeltaKind (ReclassifyRoute) + extensions to existing V1 AddRoute/RemoveRoute (capability migration) + stage 7 multi-pass algorithm (7a-7d + RiverNavigation inline) + 15 acceptance scenarios + 12 rule_ids (10 V1+30d + 2 V2+ reservations) + capability + composition with siblings (SET coordination critical for Dijkstra endpoints; POL soft coordination for canonical-route prioritization) + fork inheritance + CreativeSeed v4 → v5 schema bump + world_geometry v2 → v3 schema bump — all declared.

**Implementation phase (V1+30d):** 📦 stage 7 reference impl in `world-service` `geography-generator` Rust module (extends GEO_001 + POL_001 + SET_001 generator) · apply_delta total-function for ReclassifyRoute V1+30d + capability gates on AddRoute V1 + RemoveRoute V1 · capability `can_edit_route_geography` issuance + migration job in auth-service (mirrors POL_001 MED-6 + SET_001 precedent) · CI gates: replay-determinism (settlement_seed + POL + SET outputs → byte-identical routes) + apply_delta total-function for ReclassifyRoute + canonical-JSON normalization (inherited from SPIKE_04) + pair-uniqueness invariant + Dijkstra-tiebreaker determinism + Brandes' edge-betweenness determinism.

**Downstream consumer integration (V1+30d / V1+):** 📦 MAP_001 visual overlay rendering (Roads/Trails/SeaLanes/MountainPass) · TVL_001 V1+ travel mechanics (primary consumer) · S9 prompt-assembly `[GEOGRAPHIC_CONTEXT]` extends with `nearest_route_kind + route_origin/destination` fields (V1+30d S9 closure pass adds 2 placeholder fields) · PF_001 V1+30d cross-ref for route-cell PlaceType bias · CSC_001 V1+30d cross-ref for route-anchor skeleton selection.

**Status:** DRAFT. CANDIDATE-LOCK upon §16 acceptance scenarios passing integration tests against the reference ROUTE implementation in `world-service`. LOCK upon downstream consumers (TVL_001 V1+ primary) integrating successfully + V1+30d activation triangle (POL + SET + ROUTE) fully shipped + auth-service quad-pair migration completed.

**V1+30d activation triangle complete after this commit + V1+30d implementation phase**: 4 of GEO_001's 5 V1+ schema-reserved layers activated (political / culture / settlement / route); only V2+ resource layer (GEO-D10) remains. Strategy substrate readiness for future STRAT_001 V2+ now complete at design layer — every layer STRAT_001 will consume has its schema locked + activation generator designed.
