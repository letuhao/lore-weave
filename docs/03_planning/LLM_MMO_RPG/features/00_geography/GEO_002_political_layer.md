# GEO_002 — Political Layer Generator (POL_001)

> **Conversational name:** "Political Layer" (POL). V1+30d generator that activates GEO_001's V1-schema-reserved political fields (provinces / states / culture_regions). Implements pipeline **stage 5** (political growth — priority-queue flood-fill from capital seeds with terrain cost) and **stage 8** (culture spread — flood-fill from cultural-hearth cells with terrain barriers). Hybrid seed source: canonical author declarations take priority; procedural fallback fills remainder. Activates 4 V1+ `GeographyDeltaKind` variants (MergeProvinces / SplitProvince / TransferProvinceToState / SetCultureRegion). Composes with future STRAT_001 V2+ as read-only strategy substrate.
>
> **Category:** GEO — Geography Foundation (V1+30d generator; activates GEO_001 schema-reserved fields)
> **Status:** **DRAFT 2026-05-14** (Phase 0 D1-D7 LOCKED with user approval option 1)
> **Catalog refs:** [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — extends `GEO-*` namespace with POL-* sub-prefix (`POL-*` axioms · `POL-D*` deferrals · `POL-Q*` open questions · `AC-POL-*` acceptance)
> **Builds on:** [`GEO_001`](GEO_001_world_geometry.md) §3.1 (political layer schema — Province / State / CultureRegion already declared; `political_seed` derived; `creative_seed.canonical_provinces` + `culture_hints` author-declared inputs) · §4.5 (GeographyDeltaKind closed enum — 5 V1 → 9 with V1+ activation) · §5 stage 5 + stage 8 (algorithm baseline declared) · §16 GEO-D2 + GEO-D8 (this feature is the activation path) · [`GEO_001b`](GEO_001b_authoring_flow.md) (CreativeSeed authoring; SpatialPreference V1+ enum already provides the LLM-friendly capital placement hints POL consumes via existing `position_normalized` field)
> **Resolves:** Strategy substrate political readiness (STRAT_001 V2+ blocker partially closed — province + state graph queryable) · LLM-context grounding state-tag enrichment (prompt-assembly `[GEOGRAPHIC_CONTEXT]` gains `state_name` + `culture_tag` per cell) · Admin canonization political tooling (4 V1+ DeltaKinds — Merge/Split/Transfer/SetCulture — for author state-history evolution post-bootstrap) · GEO_001 §16 deferrals GEO-D2 + GEO-D8 in single feature
> **Defers to:** future **STRAT_001 V2+** (province ownership-by-actor + armies + sieges + supply lines; consumes POL-activated `province.state_id` / `state.member_provinces` / `culture_regions.member_cells` as read-only inputs) · future **GEO_003 SET_001 V1+30d** (settlement generator stage 6; some POL paths need settlement candidates as capital procedural seeds — POL_001 V1+30d must either ship after SET_001 OR fall back to highest-population canonical settlement when none) · future **DIPL_001 V2+** (diplomacy axes between states; consumes State.culture_tag + State.ideology_ref) · **MAP_001 V1+** (visual layer; consumes Province centroids for state-border overlay rendering)

---

## §1 Why this exists

Three concrete gaps that POL_001 closes.

**Gap 1 — Strategy substrate political layer is empty V1.** GEO_001 V1 ships `world_geometry.provinces: Vec<Province>` + `world_geometry.states: Vec<State>` as schema-reserved Vec fields but populates them only when `creative_seed.canonical_provinces` declares author-pinned entries (full-canon worlds — "Tống triều with capital at Khai Phong"). The vast majority of V1+ worlds will be partially-canon: the author seeds a few canonical states + capitals, then expects the rest of the continent to be procedurally filled with consistent province boundaries + state-affiliations. Without POL_001, those worlds reject `geography.layer_activation_deferred_v1` on any runtime political write. POL_001 lifts this reject for the four populated entry-points (pipeline stage 5 / pipeline stage 8 / 4 V1+ DeltaKinds / canonical author declarations).

**Gap 2 — Culture spread is unbound to political geometry V1.** GEO_001 V1 lets the author declare `culture_hints` (≤16 hearth-position + naming_style + value_tags entries) but provides no mechanism to spread culture across cells. V1 prompt-assembly grounding sees `culture_regions=∅` for almost every cell — even when the author meant "Han Jiangnan dominates the southern third." POL_001 stage 8 culture-spread fills `culture_regions: Vec<CultureRegion>` deterministically from those hearths, with terrain-barrier falloff (mountains + oceans block spread; rivers partial; plains fast). Once populated, prompt-assembly `[GEOGRAPHIC_CONTEXT]` joins `cell_id → culture_regions(member_cells)` → `culture_tag` and feeds the LLM canon-faithful cultural context per cell instead of inventing it.

**Gap 3 — Author canonization tooling for political evolution is missing.** GEO_001's 5 V1 DeltaKinds cover settlement + biome + route edits but NONE of the political-evolution edits a long-running wuxia / strategy world needs:
- **MergeProvinces** — two provinces unify under one capital after a strategic event (e.g., Tống absorbs a vassal county post-coronation).
- **SplitProvince** — a province fragments after political crisis (e.g., civil war partitioning a state's heartland).
- **TransferProvinceToState** — a province defects from one state to another (e.g., border province switches allegiance after siege).
- **SetCultureRegion** — author re-tags a cell-set's CultureTag after canon-faithful retcon or narrative shift (e.g., Mongol-steppe culture displaces Han over a frontier region).

These are the 4 V1+ extensions GEO-D8 named explicitly. POL_001 V1+30d activates all 4 as a single closed-enum bump per R3 additive.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Capital seed** | `(cell_id, scope: SeedScope, source: SeedSource)` triple driving stage 5 flood-fill | SeedScope = State \| Province; SeedSource = Canonical (from `creative_seed.canonical_provinces` / `canonical_states`) \| Procedural (highest-burg-score cell V1+30d when SET_001 ships, OR highest-canonical-settlement-population_tier cell fallback V1+30d standalone). |
| **Influence radius** | `f32` accumulated cost from a capital seed during flood-fill | Province border = cell where competing capitals' costs equalize (Voronoi-of-costs partition). State border = cell where competing state-capitals' costs equalize at the outer flood. Per-stage independent. |
| **TerrainCost** | Per-cell cost multiplier feeding the priority queue | `f32` derived from `(BiomeKind, heightmap, river_flux, is_coast)`: Plain=1.0, Forest=1.5, Hill=2.0, Mountain=5.0, Marsh=3.0, Desert=2.5, Ocean=∞ (uncrossable for state spread), River=2.0, Coast=1.2, Jungle=2.5, Beach=1.1, Lake=∞, Tundra=2.5, Glacier=∞. Fixed by `generator_pipeline_version`; bumping requires V2+ upcaster. |
| **CultureBarrier** | Per-cell multiplier feeding stage 8 culture-spread flood-fill | Different curve than TerrainCost (cultures cross mountains slowly but cross rivers easily; oceans hard block but rivers don't). Independent enum to keep stage 5 and stage 8 algorithmically separable. |
| **Province** | GEO_001 §3.1 — `id + name + member_cells + capital_settlement_id + state_id + resources` | V1+30d POL_001 populates `member_cells` (flood-fill cluster) + `state_id` (parent state assignment) + `capital_settlement_id` (when SET_001 ships V1+30d; else None V1+30d standalone). |
| **State** | GEO_001 §3.1 — `id + name + capital_province_id + member_provinces + culture_tag + ideology_ref` | V1+30d POL_001 populates `member_provinces` (flood-fill cluster) + `capital_province_id` (canonical state capital → derived province at that capital's cell). `culture_tag` joined from dominant `culture_regions` overlap at the capital province's cells. `ideology_ref: Option<IdeologyId>` stays None V1+30d; IDF_005 Ideology Foundation activates V2+. |
| **CultureRegion** | GEO_001 §3.1 — `id + tag + member_cells + hearth_cell` | V1+30d POL_001 populates `member_cells` (stage 8 flood-fill from `creative_seed.culture_hints[i].hearth_position_normalized` → nearest land cell). |
| **PoliticalSeedMode** | Closed enum 3 V1+30d variants — Canonical / Procedural / Hybrid | Per POL-D2 default Hybrid. Canonical-only = author declares every state; Procedural-only = pure algorithmic (largest settlements seed); Hybrid (V1+30d default) = canonical takes priority + procedural fills remainder. |
| **StatelessProvince** | `Province { state_id: None, .. }` — frontier / disputed / no-man's-land | Per POL-D4. V1+30d procedural fallback produces provinces with `state_id=None` for cells beyond any state capital's influence radius (frontier zones). Wuxia jianghu = canonical pattern. `creative_seed.canonical_provinces[i].canonical_state_id: Option<StateId>` lets author also declare stateless canonical provinces. |
| **Provinces × States cardinality** | Strict 1-to-N when `state_id=Some`; orphan when `state_id=None` | Per POL-D4. Every state has ≥1 member province; province belongs to ≤1 state (None = stateless). |
| **Culture × State independence** | `CultureRegion.member_cells` overlay vs `State.culture_tag` summary | Per POL-D5. Independent overlays; cultures span state borders. `State.culture_tag` is the dominant-culture summary derived at materialization (mode of `CultureRegion.tag` over the state's cells); `culture_regions: Vec<CultureRegion>` is the full overlay. Conflict possible (state's capital region tagged with non-state-dominant culture) — by design (frontier dynamics; cultural enclaves). |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

POL_001 introduces **NO new EVT-T* category**. Reuses existing GEO_001 event-model with two activations + four DeltaKind closed-enum additions:

| POL event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Political layer materialized at bootstrap (stage 5 + stage 8 run; provinces/states/culture_regions populated) | **EVT-T3 Derived** | `aggregate_type=world_geometry` (field delta — provinces / states / culture_regions vectors grow from empty to populated; bumps `world_geometry.last_delta_event_id`) | Aggregate-Owner role (world-service post-stage-1-4 + GEO_001 §11 bootstrap order) | Causal-ref to triggering EVT-T4 GeographyBorn. POL_001 V1+30d adds stage 5 + stage 8 emission as an additional T3 layer-activation event per continent. Replay-deterministic per `political_seed`. |
| Forge admin runtime political edit (Merge / Split / Transfer / SetCultureRegion) | **EVT-T8 Administrative** | `Forge:EditGeographyDelta { continent_channel_id, delta_kind: MergeProvinces \| SplitProvince \| TransferProvinceToState \| SetCultureRegion, delta_payload, prev_delta_id }` | WA_003 Forge | Already-registered sub-shape in `_boundaries/02_extension_contracts.md` §4 (added 2026-05-13 fix cycle MED-1). POL_001 V1+30d extends `GeographyDeltaKind` closed enum from 5 V1 to 5 V1 + 4 V1+ active (R3 additive). All 4 are **Tier 1 ImpactClass=Destructive** per S5 (state-border edits affect strategy-game correctness; double-approval required). |
| LLM-derived political-evolution proposal (V2+) | **EVT-T6 Proposal** | `POL:NarrativePoliticalEdit` (V2+ reservation) | future LLM political-arc Generator | V2+: LLM proposes Merge/Split/Transfer based on observed strategic events (siege successes, dynastic deaths via TIT_001). Forge admin reviews + materializes via T8. V1+30d scope-out: T8 admin only. |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. The §4 EVT-T8 sub-shapes table's existing `Forge:EditGeographyDelta` row remains owned by GEO_001 (the schema-owning feature) — POL_001 V1+30d extends the variant set behind that sub-shape without adding a new sub-shape row.

EVT-T3 Derived sub-types row's existing `aggregate_type=world_geometry` registration absorbs POL_001's stage 5 + stage 8 layer-activation events without modification.

---

## §3 Schema activation

**No new aggregate.** POL_001 V1+30d populates GEO_001 §3.1 `world_geometry` aggregate's V1-schema-reserved fields:

- `provinces: Vec<Province>` — populated at stage 5 by flood-fill
- `states: Vec<State>` — populated at stage 5 from capital seeds
- `culture_regions: Vec<CultureRegion>` — populated at stage 8 from `creative_seed.culture_hints` hearths

Plus extends `GeographyDeltaKind` closed enum (R3 additive — same `schema_version` bump):

```rust
pub enum GeographyDeltaKind {                               // closed; admin canonization via Forge:EditGeographyDelta T8
    // ─── V1 (5 variants; GEO_001) ───
    AddNamedSettlement { cell_id: GeoCellId, name: LocalizedName, role: SettlementRole, population_tier: u8 },
    RenameRegion { cell_ids: Vec<GeoCellId>, new_name: LocalizedName, scope: RenameScope },
    SetBiomeOverride { cell_id: GeoCellId, biome_override: BiomeKind, reason: I18nBundle },
    AddRoute { from_cell: GeoCellId, to_cell: GeoCellId, kind: RouteKind, distance_units: u32, default_fiction_duration: FictionDuration },
    RemoveRoute { route_id: RouteId },

    // ─── V1+30d (4 variants; POL_001 — closed-enum bump per R3 additive) ───
    MergeProvinces { source_province_ids: Vec<ProvinceId>, into_capital_province_id: ProvinceId, new_name: Option<LocalizedName>, reason: I18nBundle },
    SplitProvince { source_province_id: ProvinceId, partition: Vec<ProvincePartition>, reason: I18nBundle },
    TransferProvinceToState { province_id: ProvinceId, new_state_id: Option<StateId>, reason: I18nBundle }, // None = transfer to stateless
    SetCultureRegion { cell_ids: Vec<GeoCellId>, new_culture_tag: CultureTag, reason: I18nBundle },
}

pub struct ProvincePartition {                              // SplitProvince payload — declares each new sub-province
    pub member_cells: Vec<GeoCellId>,                       // MUST partition source_province_id.member_cells exactly (no overlap, no gap)
    pub new_name: LocalizedName,
    pub new_capital_settlement_id: Option<SettlementId>,    // optional; if None, capital re-derives at apply time (largest settlement in member_cells)
    pub state_id: Option<StateId>,                          // V1+30d: copy from parent province by default unless explicitly overridden
}
```

**Why `Vec<ProvincePartition>` (not a tuple)** — split into N≥2 partitions is a natural admin pattern (civil war producing 3 successor states is one delta, not 2 separate splits). Partition count cap 8 (V1+30d) per `geography.partition_cap_exceeded` reject.

**`world_geometry.schema_version` stays at 1** (no aggregate field-shape change; Province / State / CultureRegion struct shapes unchanged from GEO_001). `GeographyDeltaKind` is a closed-enum bump per R3 additive (existing V1 readers reject unknown variants gracefully via `geography.delta_kind_v1plus_inactive` while POL_001 is V1+30d-deferred; V1+30d code lifts the gate).

**`creative_seed.schema_version` bumps 2 → 3 (HIGH-1 fix /review-impl 2026-05-14)** — POL_001 adds three additive fields (`political_seed_mode` + `canonical_states` + `procedural_density`); per I14 + GEO_001b precedent (which bumped 1→2 for the single additive field `spatial_preference`), every additive field-set in CreativeSeed bumps the version. **Reader semantics** (MED-11 fix /review-impl 2nd-pass — precision):
- The actual cross-version data path is governed by `world_geometry.generator_pipeline_version` pin (GEO_001 §3 MED-4) — pre-POL realities never run stage 5/8 regardless of CreativeSeed version they hold; their pipeline_version is pinned at GeographyBorn to a pre-POL value, and mid-life pipeline upgrades are FORBIDDEN. So "v2 vs v3 reader compat" matters only at fresh bootstrap (where the reader and writer are the same pipeline_version).
- For schema-version compat purposes V1+30d ships v3 readers ONLY (v2 readers from GEO_001b ship cohort have their own pipeline_version pin pre-POL; they never read v3 data at runtime). v3 readers see v3 data natively; default-tolerant on absent fields per R3 (`Hybrid` / empty Vec / `Medium`).
- Fork inheritance (AC-POL-15): child reality inherits parent's CreativeSeed snapshot at fork-point regardless of schema_version label, since CreativeSeed is data-snapshot frozen at GeographyBorn per GEO_001 §3 immutability rule. Schema_version travels with the snapshot.

**Capability addition (per `_boundaries/02_extension_contracts.md` §3 capability JWT):** `can_edit_political_geography` claim — required for the 4 new V1+30d DeltaKinds. Disjoint from existing `can_edit_geography` claim (which V1+30d POL_001 narrows to "settlement / biome / route edits only — political edits require the political claim"). Capability authorization migration plan documented §12.

---

## §4 Closed enums (POL_001 V1+30d)

### 4.1 PoliticalSeedMode (3 V1+30d; closed)

```rust
pub enum PoliticalSeedMode {                                // closed; per-CreativeSeed declaration
    Canonical,                                              // (HIGH-2 fix /review-impl 2026-05-14) NO procedural seeds; canonical provinces alone flood-fill across the entire continent (no influence-radius cap on canonical seeds); state assignment derives from each canonical_province.canonical_state_decl_index (Some → state's member_provinces; None → stateless province). Stage 5 procedural fallback (step 4) + procedural state clustering (step 5) BOTH skipped under this mode.
    Procedural,                                             // pure algorithmic; canonical_provinces / canonical_states IGNORED even if present in CreativeSeed (V1+30d fallback / dev mode for "just give me a generated world from seed"). All seeds procedural.
    Hybrid,                                                 // V1+30d DEFAULT — canonical seeds run first (priority); procedural fallback fills uncovered regions; procedural state-clustering forms additional states from orphan procedural provinces.
}
```

Per POL-D2 default Hybrid. Surfaced in `creative_seed.political_seed_mode: PoliticalSeedMode` (V1+30d additive — CreativeSeed `schema_version` bumps 2 → 3 per HIGH-1 fix above; POL_001 V1+30d additive at v3).

### 4.2 SeedSource (2 V1+30d; closed)

```rust
pub enum SeedSource {                                       // closed; per-capital-seed tag
    Canonical { decl_index: u32 },                          // points back to creative_seed.canonical_provinces[decl_index] OR canonical_states[decl_index] OR culture_hints[decl_index]
    Procedural { burg_score_rank: u32 },                    // V1+30d standalone: rank within settlement candidates by population_tier descending; V1+30d when SET_001 ships: burg_score from settlement-placement weighting
}
```

### 4.3 SeedScope (3 V1+30d; closed)

```rust
pub enum SeedScope {                                        // closed; per-capital-seed tag
    State,                                                  // seed produces State.id; longer-range flood-fill (state borders); influence_max ~ 0.3 of continent diameter V1+30d
    Province,                                               // seed produces Province.id; shorter-range flood-fill (province borders); influence_max ~ 0.08 of continent diameter V1+30d
    CultureHearth,                                          // seed produces CultureRegion.id; stage-8 flood-fill with CultureBarrier (not TerrainCost); independent range
}
```

### 4.4 RenameScope (additive — extends GEO_001 §4 RenameRegion payload)

GEO_001 already declared `RenameScope = Settlement | Province | Region | CulturalArea`. POL_001 V1+30d activates the **Province** and **CulturalArea** scopes (V1 GEO_001 only Settlement + Region were operative; Province + CulturalArea passed validator but errored on apply for empty Vec). No enum change.

---

## §5 Pipeline activation — stages 5 and 8

POL_001 V1+30d implements pipeline stages 5 (Political growth) and 8 (Culture spread), which GEO_001 §5 declared as V1+ activation slots. Stages 1-4 (Voronoi / heightmap / climate / biome+river) are V1 GEO_001 territory and unchanged.

### 5.1 Stage 5 — Political growth (priority-queue flood-fill)

```
Inputs:
  - cells, neighbors, biomes, heightmap, river_flux, is_coast (from stages 1-4)
  - political_seed: u64 (from GeographySeed)
  - creative_seed.canonical_provinces: Vec<CanonicalProvinceDecl>   (already in GEO_001b v2 schema)
  - creative_seed.canonical_states: Vec<CanonicalStateDecl>         (POL_001 V1+30d additive within v2)
  - creative_seed.political_seed_mode: PoliticalSeedMode             (POL_001 V1+30d additive within v2)

Outputs:
  - world_geometry.provinces: Vec<Province>
  - world_geometry.states: Vec<State>
  - province.member_cells, province.state_id, state.member_provinces, state.capital_province_id all populated

Algorithm (per POL-D3 hybrid; HIGH-2 + HIGH-3 fixes /review-impl 2026-05-14):
  1. Collect canonical StateSeeds from creative_seed.canonical_states[*] → (cell_id_at_canonical_provinces[capital_province_decl_index].seed_position, SeedScope::State, SeedSource::Canonical). If political_seed_mode == Procedural: skip step 1 (ignore canonical_states); proceed with empty canonical-state set.
  2. Collect canonical ProvinceSeeds from creative_seed.canonical_provinces[*] → (snap(seed_position_normalized) to nearest land cell, SeedScope::Province, SeedSource::Canonical). If political_seed_mode == Procedural: skip step 2 (ignore canonical_provinces); proceed with empty canonical-province set.
  3. Validate canonical seeds (per §8): no two seeds at same cell; canonical_state.capital_province_decl_index ∈ valid canonical_provinces range; canonical_province snap succeeded within radius 0.1.
  4. **Procedural fallback** — fires for Procedural AND Hybrid modes (Canonical skips entirely): add ProvinceSeeds at uncovered-region centroid cells via deterministic_rng(political_seed_substream(b"stage5_procedural_province")) until total ProvinceSeed count reaches procedural_province_target_count (= cells.len() / cells_per_procedural_province; default 200 cells/province V1+30d; tunable per creative_seed.procedural_density). For **Canonical** mode: SKIPPED; canonical ProvinceSeeds alone flood-fill the continent (step 6 covers all cells regardless of capital-distance — no influence-radius cap on canonical seeds in Canonical mode).
  5. **Procedural StateSeed clustering** (HIGH-3 fix — algorithm pinned for replay determinism per EVT-A9; HIGH-4 fix /review-impl 2nd-pass 2026-05-14 — sever stage-5/stage-8 cycle):
     - **Hybrid mode:** identify orphan provinces (those whose capital cell is beyond max_state_influence_radius = 0.3 × √(continent_area_normalized) from every canonical-state capital). Build undirected graph on orphan provinces where (p_a, p_b) are linked iff TerrainCost path between p_a.capital_cell and p_b.capital_cell ≤ max_state_radius. Compute connected components via deterministic union-find (orphan provinces processed in ascending ProvinceId order; ties broken by GeoCellId of capital cell). Each connected component → one procedural State (state.id allocated via deterministic_rng(political_seed_substream(b"stage5_procedural_state"), component_index)). **Procedural state naming V1+30d — NO stage-8 dependency** (HIGH-4): `state.name = format!("{}_State_{:06x}", component.capital_province.name.default_localized, state_id_short_hex)` where state_id_short_hex is the first 6 hex chars of state.id; deterministic and replay-safe without needing culture_tag. Culture-aware procedural state naming (using `creative_seed.naming_styles[dominant_culture_tag]` Markov chain) deferred to V2+ as new POL-D13. The connected-component centroid province (lowest ProvinceId in component) becomes the state's capital_province_id.
     - **Procedural mode:** same algorithm + naming scheme but applied to ALL provinces (no canonical states); produces a fully procedural state graph.
     - **Canonical mode:** SKIPPED; orphan provinces (those whose canonical_state_decl_index = None) stay state_id=None per author declaration. NO procedural state formation.
  6. **Province flood-fill** — multi-source Dijkstra (LOW-3 fix: clarified): single priority queue seeded with every ProvinceSeed at cost 0; pop minimum-cost frontier; relax neighbors with `cost + TerrainCost[neighbor_biome]`. Cell distance metric = sum of TerrainCost over path. Tiebreaker at cost-equal cells: lower GeoCellId wins (per §5 stage-1 cell_id deterministic-order invariant). In **Hybrid + Procedural** modes: every cell assigned to nearest ProvinceSeed by cost. In **Canonical mode:** same algorithm but only canonical ProvinceSeeds participate — all cells still get assigned (since canonical seeds alone flood across continent; no procedural seeds to compete).
  7. **State flood-fill** — assign each Province to a State:
     - **Canonical mode:** province.state_id = canonical_provinces[province.canonical_decl_index].canonical_state_decl_index (canonical author declaration; no algorithmic flood-fill needed since states are pre-declared).
     - **Hybrid + Procedural modes:** greedy assign each Province to nearest StateSeed by TerrainCost path (province.capital_cell → state.capital_province.capital_cell). Cap by max_state_influence_radius. Provinces beyond every state's reach → state_id=None (stateless / frontier).
  8. Materialize Province + State structs; populate member_cells (province) + member_provinces (state); state.capital_province_id derived per mode (canonical declaration in Canonical mode; seed-cell's province in Hybrid/Procedural modes); state.culture_tag derived in stage 8.

Determinism: same (political_seed, creative_seed snapshot, generator_pipeline_version) → bitwise-identical provinces + states (modulo HashMap normalization per SPIKE_04 GAP-S2.A canonical-JSON discipline; POL_001 V1+30d adopts the same CI gate).

Cost envelope (V1+30d target):
  10k cells continent → ~80ms wall-clock (single-threaded Rust; priority queue + flood-fill linear in cells); +30ms beyond stages 1-4 GEO_001 baseline.
  Adds ~200KB compressed to world_geometry aggregate (Vec<Province>×~50 provinces + Vec<State>×~6 states per 10k-cell continent at V1+30d default density).
  **Procedural state-clustering (HIGH-3 algorithm)** (MED-10 fix /review-impl 2nd-pass — cost-envelope clarification):
  worst-case is O(V²) TerrainCost path queries on V orphan provinces. Naive: V=100 orphans × ~10k-cell pathfinding per pair = ~1B operations (≈20s, unacceptable).
  V1+30d implementation MUST use the geometric-distance pre-filter optimization: compute Euclidean distance between orphan capital cells first; only invoke TerrainCost pathfinding for pairs within Euclidean radius ≤ max_state_radius × 1.5 (safe over-approximation since TerrainCost ≥ Euclidean). For typical wuxia/strategy worlds (V ≤ 50 orphans, spatially clustered) this collapses to ~V·5 path queries (~250 ops × ~10k cells = ~2.5M ops ≈ +50ms wall-clock), within the +30ms allowance with headroom.
  CI gate (V1+30d implementation phase): synthetic-orphan stress test with V=500 evenly-distributed orphans verifies <500ms total wall-clock; failure means pre-filter regressed.
```

### 5.2 Stage 8 — Culture spread (priority-queue flood-fill with terrain barriers)

```
Inputs:
  - cells, neighbors, biomes, heightmap, is_coast (from stages 1-4)
  - political_seed: u64 (shared with stage 5 per POL-Q3 → resolved POL-Q3 V1+30d: shared default; split V1+30d+ option)
  - creative_seed.culture_hints: Vec<CultureHint>                    (already in GEO_001 V1 schema)

Outputs:
  - world_geometry.culture_regions: Vec<CultureRegion>
  - state.culture_tag for each state (mode of CultureRegion.tag over state's cells; tie → CultureTag.as_canonical_str() byte-wise lexicographic order, lowest wins — MED-7 fix /review-impl 2nd-pass; CultureTag MUST implement as_canonical_str() -> &str returning a stable UTF-8 byte sequence; opaque V1 representation pinned via this method for replay-determinism)

Algorithm:
  1. Snap each culture_hint.hearth_position_normalized to nearest LAND cell (skip Ocean / Lake / Glacier);
     reject `geography.culture_hearth_unreachable_v1` if no land cell within radius 0.1 of declared hearth.
  2. Priority-queue flood-fill from each hearth. CultureBarrier metric:
     - Plain / Forest / Coast / Beach: 1.0
     - Hill / Marsh / Jungle / Tundra: 1.5
     - River: 1.2 (cultures cross rivers easily; lighter than TerrainCost)
     - Desert / Mountain: 3.0 (cultures spread slowly across)
     - Ocean / Lake / Glacier: ∞ (hard barrier; culture cannot cross)
  3. Tiebreaker at cost-equal: hearth declared earlier in creative_seed.culture_hints wins (deterministic via Vec order).
  4. cells unassigned-by-any-culture (e.g., isolated islands with no nearby hearth): tag = first hearth's CultureTag (default-culture-fallback V1+30d; tracked POL-D7 deferral).
  5. Materialize CultureRegion structs per unique CultureTag; member_cells = cells assigned to that tag; hearth_cell preserved from input.
  6. Compute state.culture_tag: for each state, mode of cell.culture_tag over state's member-province cells.

Determinism: same as stage 5; CI gate same canonical-JSON pattern.

Cost envelope: 10k cells × ≤16 hearths → ~40ms wall-clock; adds ~100KB to aggregate.
```

**Why shared `political_seed` for stages 5 + 8 (POL-Q3 resolution V1+30d default; MED-3 (1st pass) fix /review-impl 2026-05-14):** Azgaar's stack uses one RNG seed for both political growth and culture spread; the algorithmic kinship justifies shared seed. **Per-stage sub-streaming**: each stage derives its RNG via `political_seed_substream(tag) = blake3(political_seed || tag)` with stage-tagged constants (`b"stage5_procedural_province"`, `b"stage5_procedural_state"`) so cross-stage RNG-state pollution is prevented (stage 5 procedural fallback consuming N RNG draws does NOT shift other stages' RNG output). All RNG calls within a stage MUST go through its substream; mixing substreams across stages is a bug. **Stage 8 currently has no RNG consumer** (deterministic flood-fill + Vec-order tiebreaker + CultureTag.as_canonical_str lexicographic tiebreaker) so no `b"stage8_*"` substream is registered V1+30d (MED-12 fix /review-impl 2nd-pass — clarification; substream tag namespace `b"stage8_*"` is reserved for V2+ extensions that may need RNG, e.g., probabilistic culture-region naming variants). Independent re-roll deferred V1+30d+ (POL-D6 split).

**Why CultureBarrier ≠ TerrainCost:** Stage 5's terrain cost reflects "how hard is it for a state to project political power across this terrain" (mountains very hard, oceans uncrossable). Stage 8's culture barrier reflects "how easily do customs and language spread across this terrain" (rivers easier than mountains; oceans still hard but the curves diverge). Wuxia world example: Han Jiangnan culture spreads across the Yangtze River but stops at the Tibetan plateau — captured correctly only by the CultureBarrier curve, not TerrainCost.

---

## §6 CreativeSeed authoring extensions

POL_001 V1+30d bumps `creative_seed.schema_version` 2 → 3 per HIGH-1 fix (3 additive fields; mirrors GEO_001b's 1→2 precedent for additive evolution):

```rust
// Additive fields on CreativeSeed (v2 → v3 bump; HIGH-1 fix /review-impl 2026-05-14)
pub struct CreativeSeed {                                    // ... existing GEO_001 + GEO_001b fields elided ...
    pub schema_version: u32,                                 // V1 GEO_001 = 1; V1+ GEO_001b = 2; V1+30d GEO_002 = 3
    pub political_seed_mode: PoliticalSeedMode,             // V1+30d additive; (LOW-1 fix) reader default when absent: Hybrid (per R3 default-tolerant readers + I14 forward-compat)
    pub canonical_states: Vec<CanonicalStateDecl>,          // V1+30d additive; (LOW-1 fix) reader default when absent: empty Vec (legacy realities pre-POL ship carry None which deserializes to []); activated when political_seed_mode != Procedural
    pub procedural_density: ProceduralDensityHint,          // V1+30d additive; (LOW-1 fix) reader default when absent: Medium (cells_per_procedural_province = 200)
}

pub struct CanonicalStateDecl {                             // V1+30d additive
    pub name: LocalizedName,
    pub capital_province_decl_index: u32,                   // FK into canonical_provinces; reject state.capital_province_unknown if out of range
    pub culture_tag_hint: Option<CultureTag>,               // V1+30d optional; stage 8 culture_tag derivation overrides this if culture_regions disagree
    pub ideology_ref: Option<IdeologyId>,                   // V2+ when IDF_005 ships; V1+30d schema-reserved
    pub canon_ref: Option<BookCanonRef>,                    // book-grounded; canonical wuxia state like "Tống triều" → BookCanonRef("ThanDieuDaiHiep", "v1_chapter_3")
}

pub enum ProceduralDensityHint {                            // closed 3 V1+30d
    Coarse,                                                  // 400 cells/province; ~25 procedural provinces per 10k-cell continent
    Medium,                                                  // 200 cells/province; ~50 procedural provinces per 10k-cell continent (V1+30d default)
    Fine,                                                    // 100 cells/province; ~100 procedural provinces per 10k-cell continent
}
```

Existing `creative_seed.canonical_provinces: Vec<CanonicalProvinceDecl>` (declared in GEO_001 §6) gets its V1+30d activation here — CanonicalProvinceDecl shape was reserved in GEO_001 v2:

```rust
pub struct CanonicalProvinceDecl {                          // shape declared in GEO_001 §6; V1+30d POL_001 activates the runtime materialization path
    pub name: LocalizedName,
    pub capital_settlement_name: Option<LocalizedName>,     // FK by name into canonical_settlements; resolved post-stage-6 (when SET_001 ships V1+30d) OR nearest canonical settlement V1+30d standalone
    pub seed_position_normalized: (f32, f32),               // 0.0..=1.0 within continent viewport; capital seed lands here OR snaps to nearest land cell (POL-Q4 resolution V1+30d: snap within radius 0.1; reject geography.province_seed_unreachable_v1 if no land in radius)
    pub canonical_state_decl_index: Option<u32>,            // FK into canonical_states; None = stateless canonical province
    pub canon_ref: Option<BookCanonRef>,                    // book-grounded
}
```

**LLM-authoring contract (GEO_001b sibling-doc):** POL_001 V1+30d bumps the LLM authoring template to v2 (CreativeSeed schema v3 surface; mirrors how GEO_001b registered v1.tmpl for CreativeSeed schema v2). New template at `contracts/prompt/templates/world_authoring/v2.tmpl` adds prompt-sections covering political_seed_mode + canonical_states + procedural_density. The CreativeSeed v3 schemars-generated JSON Schema includes the 3 new fields so schema-constrained generation enforces them. V1+30d implementation phase REGISTERS the SpatialPreference 14-variant enum's `NearSettlement` variant (already in GEO_001b v2) as the LLM-friendly alternative to `seed_position_normalized: (f32, f32)` — capital placement via "NearSettlement(\"Khai Phong\")" instead of raw coordinates. Per GEO_001b §3, the v3-validator "at-least-one-Some between position_normalized and spatial_preference" check absorbs CanonicalProvinceDecl without change. Per §12Y.L2 governance, template version bump from v1 → v2 requires CI fixture update (the existing `template_version_deprecated` reservation in `authoring.*` namespace activates at POL ship to deprecate v1.tmpl).

---

## §7 Apply_delta total-function for 4 V1+30d DeltaKinds

Extends GEO_001 §7 `apply_delta` per-variant impl:

### 7.1 MergeProvinces

```rust
fn apply_merge_provinces(wg: &mut WorldGeometry, payload: &MergeProvincesPayload) -> () {
    // 1. Validate (ReferentialIntegrityGate at validator pipeline):
    //    - source_province_ids.len() >= 2
    //    - into_capital_province_id ∈ source_province_ids (the survivor)
    //    - all source provinces share the same state_id (cannot merge cross-state — use TransferProvinceToState first)
    //    - no source province is referenced by any State as capital_province_id except the into_capital_province_id
    //      (cannot merge a state's capital province INTO a non-capital province; would orphan the state's capital)
    // 2. Compute survivor's new member_cells = union of source provinces' member_cells (no overlap by construction —
    //    province membership is partition of cells).
    // 3. Update wg.provinces:
    //    - Survivor's member_cells extended; survivor's name = payload.new_name OR survivor's existing name
    //    - Other source provinces removed (Vec retain by id)
    // 4. Update wg.states[state_id].member_provinces: retain by id == into_capital_province_id (the others dropped)
    // 5. settlements + routes are NOT affected (they FK by cell_id and survive merge transparently)
}
```

**Validators (§8 pipeline):** `geography.merge_cross_state_forbidden` · `geography.merge_capital_orphan` · `geography.merge_source_count_invalid` (must be ≥2).

### 7.2 SplitProvince

```rust
fn apply_split_province(wg: &mut WorldGeometry, payload: &SplitProvincePayload) -> () {
    // 1. Validate:
    //    - source_province exists
    //    - partition.len() >= 2 (MED-3 fix /review-impl 2nd-pass — separate reject geography.split_partition_min_2;
    //      previously collapsed under partition_cap_exceeded which conflated two distinct user errors)
    //    - partition.len() <= 8 (geography.partition_cap_exceeded)
    //    - union(partition[i].member_cells) == source_province.member_cells (exact partition; no overlap, no gap)
    //    - if source is a state capital: exactly one partition declares state_id == source.state_id (the heir);
    //      others may have state_id == None OR a different state_id (TransferProvinceToState semantics composed)
    // 2. Remove source province from wg.provinces.
    // 3. Add new provinces (one per ProvincePartition); IDs allocated via deterministic_rng(political_seed, source_province_id, partition_index)
    //    so replay-deterministic.
    // 4. Update wg.states[source.state_id].member_provinces:
    //    - remove source_province_id
    //    - add heir partition's new id (the one with state_id == source.state_id)
    //    - the other partitions' state_id assignments update their respective states OR remain stateless (state_id=None)
    // 5. State's capital_province_id: if source was state capital, update to heir partition's new id.
}
```

**Validators:** `geography.split_partition_min_2` (MED-3) · `geography.partition_cap_exceeded` · `geography.partition_not_total` · `geography.split_capital_no_heir`.

### 7.3 TransferProvinceToState

```rust
fn apply_transfer_province_to_state(wg: &mut WorldGeometry, payload: &TransferProvincePayload) -> () {
    // 1. Validate:
    //    - province_id exists
    //    - new_state_id: Option<StateId> — None = transfer to stateless; Some(id) = target state must exist
    //    - province is NOT a state's capital_province (capitals cannot be transferred; would orphan state — must SplitProvince first)
    //    - province.state_id != new_state_id (MED-4 fix /review-impl 2nd-pass — transfer-to-self is a wasted admin
    //      action; reject geography.transfer_self_target. Distinct from "already there" idempotent retry because
    //      a fresh prev_delta_id pointer would be in flight, so this catches deliberate no-ops not retries.)
    // 2. Remove province from old state.member_provinces (if Some).
    // 3. Add province to new state.member_provinces (if Some).
    // 4. Update province.state_id = new_state_id.
}
```

**Validators:** `geography.transfer_capital_forbidden` · `geography.transfer_target_state_unknown` · `geography.transfer_self_target` (MED-4).

### 7.4 SetCultureRegion

```rust
fn apply_set_culture_region(wg: &mut WorldGeometry, payload: &SetCultureRegionPayload) -> () {
    // 1. Validate:
    //    - payload.cell_ids is non-empty (MED-1 fix /review-impl 2nd-pass — empty payload is a wasted admin action;
    //      reject geography.set_culture_region_empty BEFORE apply)
    //    - all cell_ids ∈ cells
    //    - new_culture_tag is a known CultureTag (in creative_seed.naming_styles OR an existing culture_regions tag)
    //      — author cannot invent CultureTags via delta; must register in CreativeSeed extension V1+ T6+T8 flow first
    // 2. For each cell_id in payload.cell_ids:
    //    - find existing CultureRegion containing cell_id; remove cell_id from its member_cells
    //    - find/create CultureRegion with tag == new_culture_tag; push cell_id to its member_cells
    //    - if a new CultureRegion is created (no existing tag matched), hearth_cell = MIN(payload.cell_ids by GeoCellId)
    //      (MED-2 fix /review-impl 2nd-pass — deterministic; replaces "first cell" Vec-order-dependent choice)
    // 3. Recompute affected state.culture_tag UNCONDITIONALLY: for any state whose member-province cells intersect
    //    payload.cell_ids, recompute mode-over-cells; write back (even if unchanged — keeps replay-deterministic;
    //    "if changed" guard would introduce mode-stability question not worth the optimization).
}
```

**Validators:** `geography.set_culture_region_empty` (MED-1) · `geography.culture_tag_unregistered` (POL-V14).

---

## §8 Validation pipeline (POL_001 V1+30d additive validators)

All extend GEO_001 §7 + 07_event_model EVT-V* pipeline. New validator slots register in `_boundaries/03_validator_pipeline_slots.md` (POL_001 V1+30d adds to existing GEO-V* slots, no new numbered slot needed — these are sub-validators within `Forge:EditGeographyDelta` ReferentialIntegrityGate step):

| Validator | Stage | Reject rule_id |
|---|---|---|
| **POL-V1** state-capital-province-membership | Stage 5 + delta apply | `geography.state_capital_not_in_province` (state.capital_province_id ∉ state.member_provinces) |
| **POL-V2** province-state-cross-reference | Stage 5 + delta apply | `geography.province_state_mismatch` (province.state_id == Some(s) but s.member_provinces ∌ province.id) |
| **POL-V3** state-capital-cycle | Stage 5 (post-flood-fill consistency check) | `geography.state_capital_cycle` (would only fire on author-corrupted canonical declarations; defensive) |
| **POL-V4** culture-hearth-on-land | Stage 8 setup | `geography.culture_hearth_unreachable_v1` (hearth_position_normalized snap fails — no land cell within radius 0.1) |
| **POL-V5** province-seed-on-land | Stage 5 setup | `geography.province_seed_unreachable_v1` (canonical_province.seed_position_normalized snap fails) |
| **POL-V6** partition-totality | SplitProvince delta apply | `geography.partition_not_total` (union of partitions != source province's member_cells) |
| **POL-V7** partition-cap | SplitProvince delta apply | `geography.partition_cap_exceeded` (>8 partitions; reasonable upper bound; V1+30d revisit if Roman-era reform-scale fragmentation needed) |
| **POL-V8** merge-source-count | MergeProvinces delta apply | `geography.merge_source_count_invalid` (<2 sources) |
| **POL-V9** merge-cross-state | MergeProvinces delta apply | `geography.merge_cross_state_forbidden` (sources span different states) |
| **POL-V10** merge-capital-orphan | MergeProvinces delta apply | `geography.merge_capital_orphan` (state's capital province would be removed) |
| **POL-V11** split-capital-no-heir | SplitProvince delta apply | `geography.split_capital_no_heir` (source was capital, no partition claims same state_id) |
| **POL-V12** transfer-capital-forbidden | TransferProvinceToState delta apply | `geography.transfer_capital_forbidden` (province is a state's capital) |
| **POL-V13** transfer-target-state-unknown | TransferProvinceToState delta apply | `geography.transfer_target_state_unknown` (Some(new_state_id) but state not in states[]) |
| **POL-V14** culture-tag-unregistered | SetCultureRegion delta apply | `geography.culture_tag_unregistered` (new_culture_tag ∉ creative_seed.naming_styles + ∉ existing culture_regions.tag) |
| **POL-V15** political-edit-capability | All 4 DeltaKinds — AuthorizationGate | `geography.political_edit_capability_required` (capability JWT missing `can_edit_political_geography`) |
| **POL-V16** set-culture-region-non-empty (MED-1) | SetCultureRegion delta apply | `geography.set_culture_region_empty` (payload.cell_ids.is_empty()) |
| **POL-V17** split-partition-min-2 (MED-3) | SplitProvince delta apply | `geography.split_partition_min_2` (partition.len() < 2 — distinct user-facing error from partition_cap_exceeded for >8) |
| **POL-V18** transfer-self-target (MED-4) | TransferProvinceToState delta apply | `geography.transfer_self_target` (province.state_id == new_state_id; defensive — fresh prev_delta_id means deliberate no-op not idempotent retry) |
| **POL-V19** canonical-mode-no-seeds (MED-8) | RealityBootstrapper / stage 5 setup | `geography.canonical_mode_no_seeds` (political_seed_mode == Canonical AND canonical_provinces.is_empty(); degenerate — zero canonical seeds in Canonical mode produces a world with zero provinces) |
| **POL-V20** canonical-state-province-mismatch (MED-9) | RealityBootstrapper / stage 5 setup | `geography.canonical_state_province_mismatch` (cross-reference asymmetry: canonical_states[s].capital_province_decl_index=p but canonical_provinces[p].canonical_state_decl_index != Some(s); author-corruption defensive validator at canonical-decl stage before flood-fill) |

ContentSafetyGate (§12X.L7 PII scrub regardless per D-S04-4 GEO_001 fix cycle approval): applied to `delta.reason` + `new_name` + `partition[*].new_name` + `culture_tag_hint` (LocalizedName + LocalizedString fields all run through the scrubber).

---

## §9 DP primitives + capability

POL_001 V1+30d introduces no new DP primitives. All writes flow through GEO_001's existing path:

- `dp.t2_write::<WorldGeometry>(channel_id, ...)` — extends existing GEO_001 T2 write
- `dp.subscribe_channel_events_durable::<WorldGeometryEvent>(channel_id, ...)` — consumed by MAP_001 V1+ (province centroid → border overlay)

Capability addition (extends `_boundaries/02_extension_contracts.md` §3 capability JWT):

- `can_edit_political_geography: bool` (claim) — required by EVT-T8 AuthorizationGate for the 4 V1+30d DeltaKinds
- Migration: existing `can_edit_geography` claim continues to authorize the 5 V1 DeltaKinds (settlement / biome / route); V1+30d capability holders MUST hold BOTH claims to perform the new political DeltaKinds (additive — no removal of V1 claim semantics).
- **Capability migration plan at POL ship** (MED-6 fix /review-impl 2nd-pass): auth-service runs a one-shot migration that auto-grants `can_edit_political_geography` to all currently-active `can_edit_geography` holders. Per PLT_001 §6.3 `forge.roles_version` bumps as part of the migration (auditable). Post-migration, future Forge admins receive both claims as a paired bundle at role-grant time (PLT_001 RBAC config V1+30d adds the pairing). No existing admin loses access at ship. Roll-out: cohort-style — staging realities migrate first; production realities migrate after 24h soak; failed migrations fall back to "neither claim active" (admin re-issuance required, surfaces UI banner).
- Tier 1 ImpactClass=Destructive per S5: all 4 require double-approval per ADMIN_ACTION_POLICY (parallel to SetBiomeOverride / RemoveRoute already-Tier-1 V1).

Subscribe path: POL_001 V1+30d emissions appear as `EVT-T3 Derived aggregate_type=world_geometry` events; existing GEO_001 subscribers automatically receive POL field updates (province / state / culture_region changes), no new subscribe contract needed.

---

## §10 Composition with foundation siblings

POL_001 V1+30d composes within GEO_001's existing composition contracts; no new sibling integration is added:

| Sibling | Composition with POL_001 |
|---|---|
| **GEO_001** | Schema parent; POL_001 V1+30d populates GEO_001 §3.1 schema-reserved fields. No GEO_001 schema change. |
| **GEO_001b** | LLM authoring contract; POL_001 V1+30d activates within GEO_001b v2 schema additively (political_seed_mode + canonical_states + procedural_density). No GEO_001b prompt-template change V1+30d. |
| **MAP_001** | V1+30d POL_001 stage 5 outputs (province centroid coordinates) feed MAP_001 V1+30d position auto-derivation per GEO-D5: `map_layout.position` for state-level channels derives from State.capital_province_id → cells[capital].center. MAP_001 light reopen at LOCK should add a "V1+ state-level position derivation row" alongside the GEO-D5 settlement row. |
| **PF_001** | V1+30d PF-D7 procedural place generation gains `culture_tag` context for PlaceType selection (Biome::Plain + Han-Jiangnan-culture → Inn naming style "tửu lâu" via creative_seed.naming_styles[han_jiangnan]). No PF_001 schema change. |
| **CSC_001** | V1+30d culture_tag feeds cell skeleton selection (Biome::Plain + Mongol-steppe-culture → yurt-style skeleton vs Han-style farmhouse). No CSC_001 schema change. |
| **EF_001** | No direct composition. Province/state membership doesn't affect entity binding. |
| **RES_001** | V2+ GEO-D10 resource generator consumes Province.member_cells × biomes × climate to populate per-province resource_inventory. POL_001 V1+30d populates Province; RES_001 V2+ consumes (no V1+30d dependency). |
| **PROG_001** | No direct composition V1+30d. V2+ cultivation-realm states (e.g., Wuxia "Spirit Sect" state) may carry per-state cultivation modifiers via State.ideology_ref → IDF_005 (V2+). |
| **TIT_001** | V1+30d: State.capital_province_id is the political-substrate basis on which TIT_001 titles like "Lord of \[Capital\]" CAN reference province name. No V1+30d schema integration; cross-ref documentation only. V2+ TIT_001 ideology_ref pairing surfaces. |
| **STRAT_001 V2+** | Primary read-only consumer. Reads Province graph (member_cells + neighbors-derived province adjacency) for province-ownership-by-actor + army-position-on-province; reads State.member_provinces for diplomatic-axis assignment; reads CultureRegion.member_cells for unrest-modifier computation. STRAT_001 spec lands V2+. |
| **DIPL_001 V2+** | V2+ consumer. Reads State.culture_tag + State.ideology_ref for diplomatic-axis defaults (cultural-affinity bonus / ideology-conflict penalty). |

---

## §11 RealityManifest extension

**No new RealityManifest field.** POL_001 V1+30d extends `creative_seed` (per §6) which is already inside `RealityManifest.continent_geometries[i].creative_seed` per GEO_001 §11. The CreativeSeed v2 schema (per GEO_001b) absorbs POL_001 fields additively per R3.

Bootstrap order remains GEO_001 §11:
1. DP create_channel (continent + cells)
2. RealityBootstrapper EVT-T4 GeographyBorn per continent
3. world-service materializes WorldGeometry — V1+30d this now runs stages 1-4 AND stages 5+8 (POL_001 active)
4. Apply initial `geography_deltas` (per CreativeSeed declaration; canonical states + provinces resolved)
5. Persist as T2/Channel-continent aggregate (now includes populated provinces + states + culture_regions)

V1+30d feature-flag: `services/world-service` config `political_layer_generator_enabled: bool` (default true V1+30d; false V1 backward-compat for realities bootstrapping pre-POL_001 ship). When false, stages 5+8 skipped, provinces/states/culture_regions stay empty (V1 behavior). Mid-life feature-flag flip on an existing reality: **FORBIDDEN** — per GEO_001 §3 `generator_pipeline_version` discipline. Flag affects only new realities at bootstrap.

---

## §12 Failure UX — extends `geography.*` namespace

POL_001 V1+30d adds **20 V1+30d rule_ids** under the existing `geography.*` namespace owned by GEO_001 (per POL-D7 — share namespace, no new prefix carving; /review-impl 2nd-pass added 5 MED-driven rule_ids on 2026-05-14). Total `geography.*` after POL_001 V1+30d ships: 33 V1+30d (13 V1 GEO_001 + 20 V1+30d POL_001).

Also LIFTS V1's `geography.layer_activation_deferred_v1` reject for the political layer specifically (V1+30d-gated): when `services/world-service` runs at POL_001 V1+30d ship time, political/state/culture_region writes via stage-5/stage-8/4-new-DeltaKind paths NO LONGER reject this rule_id. Other layer-activation paths (settlement V1+30d SET_001 / route V1+30d ROUTE_001 / resource V2+) keep the reject until their generator ships.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d) | English fallback |
|---|---|---|---|---|
| `geography.state_capital_not_in_province` | schema | Stage 5 / delta | "Thủ đô của quốc gia không thuộc tỉnh hợp lệ." | "State capital not in valid member province." |
| `geography.province_state_mismatch` | schema | Stage 5 / delta | "Tỉnh và quốc gia không nhất quán." | "Province-state reference inconsistent." |
| `geography.state_capital_cycle` | schema | Stage 5 consistency check | "Cấu trúc thủ đô-tỉnh-quốc gia có vòng lặp." | "State-capital-province cycle detected." |
| `geography.culture_hearth_unreachable_v1` | user | Stage 8 setup | "Không tìm thấy ô đất trong bán kính cho phép quanh điểm khởi nguồn văn hóa." | "No land cell within radius around culture hearth." |
| `geography.province_seed_unreachable_v1` | user | Stage 5 setup | "Không tìm thấy ô đất trong bán kính cho phép quanh thủ đô tỉnh đã khai báo." | "No land cell within radius around declared province seed." |
| `geography.partition_not_total` | schema | SplitProvince delta | "Các phần chia không phủ kín tỉnh gốc." | "Province partition is not total (cells missing or overlapping)." |
| `geography.partition_cap_exceeded` | user | SplitProvince delta | "Số phần chia vượt giới hạn (tối đa 8)." | "Partition count exceeds cap (max 8)." |
| `geography.merge_source_count_invalid` | user | MergeProvinces delta | "Phải có ít nhất 2 tỉnh để hợp nhất." | "Merge requires at least 2 source provinces." |
| `geography.merge_cross_state_forbidden` | user | MergeProvinces delta | "Không thể hợp nhất tỉnh thuộc các quốc gia khác nhau. Hãy chuyển quốc gia trước." | "Cannot merge provinces across states. Transfer state first." |
| `geography.merge_capital_orphan` | user | MergeProvinces delta | "Thao tác này sẽ làm mất thủ đô của quốc gia." | "This operation would orphan a state's capital." |
| `geography.split_capital_no_heir` | user | SplitProvince delta | "Phải chỉ định một phần kế thừa thủ đô quốc gia." | "Must designate an heir partition for the state capital." |
| `geography.transfer_capital_forbidden` | user | TransferProvinceToState delta | "Không thể chuyển quốc gia cho tỉnh đang là thủ đô. Hãy chia tỉnh trước." | "Cannot transfer a state's capital province. Split first." |
| `geography.transfer_target_state_unknown` | schema | TransferProvinceToState delta | "Quốc gia đích không tồn tại." | "Target state not found." |
| `geography.culture_tag_unregistered` | user | SetCultureRegion delta | "Văn hóa chưa được đăng ký trong cấu hình thế giới." | "Culture tag not registered in world configuration." |
| `geography.political_edit_capability_required` | user | All 4 DeltaKinds AuthorizationGate | "Bạn không có quyền chỉnh sửa địa lý chính trị." | "Missing political geography edit capability." |
| **`geography.set_culture_region_empty`** *(MED-1)* | user | SetCultureRegion delta | "Danh sách ô để đổi văn hóa không được trống." | "SetCultureRegion cell list cannot be empty." |
| **`geography.split_partition_min_2`** *(MED-3)* | user | SplitProvince delta | "Phải chia thành ít nhất 2 phần." | "SplitProvince requires at least 2 partitions." |
| **`geography.transfer_self_target`** *(MED-4)* | user | TransferProvinceToState delta | "Tỉnh đã thuộc quốc gia này; không cần chuyển." | "Province already belongs to target state; transfer is a no-op." |
| **`geography.canonical_mode_no_seeds`** *(MED-8)* | schema | RealityBootstrapper / stage 5 setup | "Chế độ Canonical yêu cầu khai báo ít nhất một tỉnh canonical." | "Canonical mode requires at least one canonical_provinces entry." |
| **`geography.canonical_state_province_mismatch`** *(MED-9)* | schema | RealityBootstrapper / stage 5 setup | "Tham chiếu chéo quốc gia-tỉnh canonical không nhất quán." | "Canonical state-province cross-reference inconsistent." |

V1+30d schema-level rejects (6): state_capital_not_in_province / province_state_mismatch / state_capital_cycle / partition_not_total / transfer_target_state_unknown / canonical_mode_no_seeds (MED-8) / canonical_state_province_mismatch (MED-9).
V1+30d user-facing rejects (14): the rest — including set_culture_region_empty (MED-1) / split_partition_min_2 (MED-3) / transfer_self_target (MED-4).

V2+ reservations (NEW): `geography.political_narrative_proposal_pending` (V2+ T6 NarrativePoliticalEdit Generator review).

---

## §13 Cross-service handoff

| Service | Role | V1+30d status |
|---|---|---|
| **world-service** | Authoritative owner — runs stages 5 + 8 at bootstrap; applies the 4 V1+30d DeltaKinds; persists aggregate | V1+30d |
| **glossary-service** | Stores CanonicalStateDecl names + CultureTag names + naming-style corpus refs (same pattern as canonical_provinces / canonical_settlements V1) | V1+30d |
| **chat-service** (S9 prompt-assembly) | Read-only consumer — `[GEOGRAPHIC_CONTEXT]` joins province name + state name + culture_tag per cell | V1+30d |
| **api-gateway-bff** | Routes Forge UI POSTs for 4 new V1+30d DeltaKinds → world-service; player map UI GETs continue to read populated provinces + states for state-border rendering | V1+30d Forge UI |
| **knowledge-service** | Reads State.culture_tag + Province.member_cells for political knowledge graph (planned V1+ knowledge-service activation per CLAUDE.md two-layer pattern) | Not V1+30d |
| **STRAT_001 service V2+** | Future consumer for province-ownership + army-position + siege-graph (separate service in V2+; consumes POL_001 V1+30d-locked schema as read-only) | V2+ |

No new service introduced. All V1+30d implementation fits inside `world-service` extension + read-only consumers.

---

## §14 Multiverse inheritance

POL_001 V1+30d inherits GEO_001 §9 fork-inheritance contract unchanged. Snapshot fork at event E:

- Parent's `political_layer` (provinces + states + culture_regions populated via stage 5/8 at parent bootstrap) copied bit-exactly into child.
- Parent's V1+30d POL DeltaKinds applied up to fork-point copied as part of `geography_deltas[..fork_point]`.
- Child appends new V1+30d POL DeltaKinds locally; parent's post-fork DeltaKinds do NOT cascade.
- L1/L2 cascade: if author edits `creative_seed.canonical_states[i]` at L2, both parent and child see new value UNLESS child has L3-scoped DeltaKind override (TransferProvinceToState / MergeProvinces / etc.) on the same province/state.

Determinism preserved: same `(political_seed, creative_seed_snapshot, generator_pipeline_version, fork_point_delta_count)` → bit-identical provinces + states + culture_regions across parent and child at fork point.

---

## §15 Sequences

### 15.1 Hybrid bootstrap — Yên Vũ Lâu wuxia setting (POL_001 V1+30d active)

```
RealityManifest.continent_geometries[0].creative_seed = {
  archetype: Wuxia, world_scale: Region (~2048 cells), hemisphere: Northern, coastline: Coastal,
  political_seed_mode: Hybrid,                                  // POL_001 V1+30d
  canonical_states: [
    { name: "Tống triều", capital_province_decl_index: 0, culture_tag_hint: Some(han_jiangnan), ... },
    { name: "Liêu", capital_province_decl_index: 1, culture_tag_hint: Some(qidan), ... },
  ],
  canonical_provinces: [
    { name: "Lương Châu", seed_position_normalized: (0.40, 0.50), canonical_state_decl_index: Some(0), ... },
    { name: "Yên Vân", seed_position_normalized: (0.75, 0.15), canonical_state_decl_index: Some(1), ... },
    // 4 more canonical provinces declared
  ],
  culture_hints: [ han_jiangnan@(0.30,0.40), qidan@(0.75,0.15) ],
  procedural_density: Medium,                                   // 200 cells/procedural province
  ...
}
  ↓ Stages 1-4 run (GEO_001 V1; ~50ms; biome/climate/heightmap populated; cells = 2048)
  ↓ Stage 5 (POL_001 V1+30d): Collect 6 canonical ProvinceSeeds + 2 canonical StateSeeds.
    Validate: no duplicate seeds; canonical_states[0].capital_province_decl_index=0 ∈ canonical_provinces; pass.
    Procedural fallback: 2048 cells / 200 cells/province = ~10 total provinces target; 6 canonical declared, so add
    ~4 procedural provinces at uncovered-region centroids via deterministic_rng(political_seed).
    Procedural states (per HIGH-3 fix — connected-component clustering on orphan provinces via TerrainCost
    path ≤ max_state_radius; geometric-distance pre-filter applied per MED-10): 1 connected component emerges from
    the 4 orphan procedural provinces clustered in the west → 1 new procedural State named "Tây Cương_State_a3f9c2"
    (per HIGH-4 fix — culture-agnostic naming `{centroid_province.name}_State_{6-hex-of-state-id}` where
    centroid_province.name is procedurally-derived from the western cluster's lowest-ProvinceId capital cell;
    culture-aware Markov-chain naming deferred V2+ per POL-D13).
    Province flood-fill: multi-source Dijkstra from 10 seeds; ~85ms wall-clock; all 2048 cells assigned.
    State flood-fill: greedy assign each province to nearest state-capital chain; 3 states total
    (Tống / Liêu / Tây Cương_State_a3f9c2); 1 province stays state_id=None (frontier "Tây Vực" region beyond all state reach).
  ↓ Stage 8 (POL_001 V1+30d): Snap 2 hearths to nearest land cells; flood-fill with CultureBarrier metric;
    ~40ms; 2 culture_regions emerge (han_jiangnan ~70% cells; qidan ~25% cells; 5% cells default-fallback
    han_jiangnan per POL-D7 fallback rule).
  ↓ state.culture_tag derived: Tống → han_jiangnan; Liêu → qidan; Tây Cương_State_a3f9c2 → han_jiangnan (dominant via mode-over-cells; CultureTag.as_canonical_str() tiebreaker per MED-7).
  ↓ WorldGeometry persisted: provinces=10, states=3, culture_regions=2, stateless_provinces=1.
  ↓ Prompt-assembly for cell:yen_vu_lau joins biomes[id]=Plain + climate=Subtropical +
    province_name="Lương Châu" + state_name="Tống triều" + culture_tag="han_jiangnan" →
    [GEOGRAPHIC_CONTEXT] = "thị trấn, văn hóa Hán-Giang Nam, tỉnh Lương Châu (Tống triều), đồng bằng cận nhiệt đới"
```

### 15.2 Forge MergeProvinces — Tống absorbs vassal county

```
Forge:EditGeographyDelta { delta_kind: MergeProvinces { source_province_ids: [p_luong_chau, p_jiang_nam_vassal],
                                                        into_capital_province_id: p_luong_chau,
                                                        new_name: Some("Lương Châu Đại Tỉnh"),
                                                        reason: "Hoàng đế ban chiếu hợp nhất...50+ char" },
                          prev_delta_id: <last_delta>, ... }
  ↓ EVT-T8 validator pipeline (POL_001 V1+30d):
    AuthorizationGate (has can_edit_political_geography claim) → SchemaGate → ReferentialIntegrityGate
    (POL-V8 source count ≥2; POL-V9 same state; POL-V10 capital not orphaned) → OrderingGate
    → ContentSafetyGate (reason scrubbed per D-S04-4) → all pass.
  ↓ EVT-T3 Derived: apply_merge_provinces(wg, payload):
    - survivor p_luong_chau.member_cells += p_jiang_nam_vassal.member_cells (now ~350 cells from 200+150)
    - survivor.name = "Lương Châu Đại Tỉnh"
    - wg.provinces drops p_jiang_nam_vassal entry
    - wg.states[Tống].member_provinces drops p_jiang_nam_vassal id, retains p_luong_chau
    - geography_deltas.push(delta_entry)
  ↓ Subsequent prompt-assembly for cells in old p_jiang_nam_vassal range now shows
    province_name="Lương Châu Đại Tỉnh"; nearest_settlement unchanged (settlements survive merge).
  ↓ STRAT_001 V2+ (when ships) sees province graph: p_luong_chau now larger; one fewer province for
    army-position calculation; state border line redrawn at MAP_001 V1+ visual layer.
```

### 15.3 Forge SetCultureRegion — Mongol displaces Han over frontier

```
Forge:EditGeographyDelta { delta_kind: SetCultureRegion { cell_ids: [c_500, c_501, c_502, ... 47 cells],
                                                          new_culture_tag: "mongol_steppe",  // already in naming_styles
                                                          reason: "Mông Cổ chiếm Hà Sáo...50+ char" },
                          prev_delta_id: <last>, ... }
  ↓ POL-V14 culture_tag_unregistered check: mongol_steppe ∈ creative_seed.naming_styles → pass.
    (If author hadn't pre-registered, reject — must add via V1+ T6 LLM extension + T8 admin first.)
  ↓ apply_set_culture_region(wg, payload):
    - for each cell_id: remove from existing CultureRegion's member_cells; add to mongol_steppe's
    - if no mongol_steppe CultureRegion existed yet (creative_seed declared but no hearth-flood-fill output),
      create one with member_cells = payload.cell_ids; hearth_cell = first cell (best-effort V1+30d)
    - recompute affected states' culture_tag: state "Tây Cương" loses ~15% han cells, drops to 60%/40% han/mongol
      → mode still han → state.culture_tag unchanged. State "Liêu" gains marginally → unchanged.
  ↓ Prompt-assembly for those 47 cells now grounds LLM with culture_tag=mongol_steppe even though state stays Tây Cương.
    Cultural enclave / frontier dynamics correctly modeled.
```

### 15.4 Forge SplitProvince — capital province fragments after civil war

```
Forge:EditGeographyDelta { delta_kind: SplitProvince {
    source_province_id: p_luong_chau,                          // Tống's capital province
    partition: [
      { member_cells: [c1..c180], new_name: "Lương Châu Bắc", state_id: Some(s_tong), ... },   // HEIR (keeps Tống state)
      { member_cells: [c181..c280], new_name: "Lương Châu Nam", state_id: Some(s_new_southern), ... },   // new breakaway
      { member_cells: [c281..c350], new_name: "Vô Chủ Địa", state_id: None, ... },             // stateless frontier
    ],
    reason: "Loạn nội chiến chia cắt thủ đô...50+ char" }, ... }
  ↓ POL-V6 partition-totality: union(180+100+70) = 350 = source.member_cells.len() → pass.
  ↓ POL-V7 partition-cap: 3 ≤ 8 → pass.
  ↓ POL-V11 split-capital-no-heir: heir partition has state_id == s_tong → pass.
    State s_new_southern existence pre-required (must be created in earlier delta or canonical declaration).
  ↓ apply_split_province:
    - drop p_luong_chau from wg.provinces
    - allocate 3 new ProvinceId via deterministic_rng(political_seed, p_luong_chau, partition_index)
    - push 3 new provinces to wg.provinces
    - wg.states[s_tong].capital_province_id = heir partition's new id (state survives with smaller capital province)
    - wg.states[s_tong].member_provinces: drop p_luong_chau, add heir id
    - wg.states[s_new_southern].member_provinces: add second partition id
    - third partition is stateless (state_id=None)
  ↓ STRAT_001 V2+ sees: Tống's capital province now smaller, lost member; new state s_new_southern emerges
    with first member province; frontier territory unassigned.
```

### 15.5 Cycle reject — author corruption in canonical_states

```
RealityManifest declares canonical_states[0] = { name: "X", capital_province_decl_index: 99 }
                       canonical_provinces.len() == 50  // index 99 out of range
  ↓ Stage 5 setup validator (before flood-fill):
    POL-V1 state-capital-province-membership check finds capital_province_decl_index=99 ∉ valid range →
    reject geography.state_capital_not_in_province at RealityBootstrapper.
  ↓ EVT-T4 GeographyBorn NOT emitted; reality bootstrap fails; author UI surfaces Vietnamese reject copy.
```

---

## §16 Acceptance criteria

21 V1+30d-testable acceptance scenarios (15 original + 6 added /review-impl 2nd-pass coverage: AC-POL-16..21 covering MED-1/3/4/8/9 rejects + LOW-2 island state). LOCK granted when ≥15 pass integration tests against POL reference module in `world-service` (extension of GEO_001's `geography-generator`).

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-POL-1** | Bootstrap continent with `political_seed_mode=Hybrid`, 2 canonical_states + 6 canonical_provinces + 2 culture_hints → provinces.len() in [10, 14] (canonical 6 + procedural fill), states.len() == 3 (2 canonical + 1 procedural cluster), culture_regions.len() == 2, all referenced state.capital_province_id ∈ valid province set. | — |
| **AC-POL-2** | Bootstrap with same `(political_seed, creative_seed, pipeline_version)` on second continent → byte-identical provinces + states + culture_regions (replay determinism per EVT-A9). | — |
| **AC-POL-3** | (HIGH-2 fix aligned) Bootstrap with `political_seed_mode=Canonical`, 2 canonical_states + 4 canonical_provinces (canonical seeds cover ~40% of cells initially) → provinces.len() == 4 (NO procedural fill per Canonical-mode skip), states.len() == 2. Province flood-fill (§5.1 step 6) runs with only canonical seeds — all 100% of land cells get assigned to one of the 4 canonical provinces by TerrainCost-nearest tiebreaker; no influence-radius cap on canonical seeds. Each province's state_id derives from canonical_provinces[i].canonical_state_decl_index (Some → state member; None → stateless). No procedural state clustering runs (§5.1 step 5 skipped). | — |
| **AC-POL-4** | Bootstrap with `canonical_states[0].capital_province_decl_index=99` (out of range; only 6 provinces declared) → reject at RealityBootstrapper. | `geography.state_capital_not_in_province` |
| **AC-POL-5** | Bootstrap with `culture_hint.hearth_position_normalized=(0.5, 0.5)` where cells[at (0.5,0.5)] is Ocean AND no land within radius 0.1 → reject at stage 8 setup. | `geography.culture_hearth_unreachable_v1` |
| **AC-POL-6** | Forge admin emits MergeProvinces with 2 source provinces from same state, valid capital survivor → delta appended; survivor's member_cells = union; state.member_provinces drops one entry. | — |
| **AC-POL-7** | Forge admin emits MergeProvinces with sources from different states → reject. | `geography.merge_cross_state_forbidden` |
| **AC-POL-8** | Forge admin emits MergeProvinces where survivor is NOT the state's capital province but one of the absorbed provinces IS → reject. | `geography.merge_capital_orphan` |
| **AC-POL-9** | Forge admin emits SplitProvince with partition that misses 5 cells → reject. | `geography.partition_not_total` |
| **AC-POL-10** | Forge admin emits SplitProvince with 10 partitions (>8 cap) → reject. | `geography.partition_cap_exceeded` |
| **AC-POL-11** | Forge admin emits SplitProvince where source is state's capital and no partition declares same state_id → reject. | `geography.split_capital_no_heir` |
| **AC-POL-12** | Forge admin emits TransferProvinceToState where province is a state's capital_province_id → reject. | `geography.transfer_capital_forbidden` |
| **AC-POL-13** | Forge admin emits SetCultureRegion with culture_tag NOT in creative_seed.naming_styles AND NOT in existing culture_regions.tag → reject. | `geography.culture_tag_unregistered` |
| **AC-POL-14** | Forge admin holds `can_edit_geography` but NOT `can_edit_political_geography` → emits MergeProvinces → reject at AuthorizationGate. | `geography.political_edit_capability_required` |
| **AC-POL-15** | Snapshot fork at event E where parent has stage-5/8 outputs + 2 V1+30d POL DeltaKinds applied → child world_geometry has identical provinces + states + culture_regions + 2 deltas; child appends MergeProvinces locally; parent appends SetCultureRegion; both diverge correctly with no cross-pollination. | — |
| **AC-POL-16** *(MED-1 coverage)* | Forge admin emits SetCultureRegion with empty `cell_ids` → reject. | `geography.set_culture_region_empty` |
| **AC-POL-17** *(MED-3 coverage)* | Forge admin emits SplitProvince with `partition.len() == 1` → reject with the dedicated min-2 rule (distinct from partition_cap_exceeded). | `geography.split_partition_min_2` |
| **AC-POL-18** *(MED-4 coverage)* | Forge admin emits TransferProvinceToState where `province.state_id == new_state_id` → reject. | `geography.transfer_self_target` |
| **AC-POL-19** *(MED-8 coverage)* | RealityBootstrapper with `political_seed_mode=Canonical` and `canonical_provinces.is_empty()` → reject at bootstrap (degenerate Canonical world). | `geography.canonical_mode_no_seeds` |
| **AC-POL-20** *(MED-9 coverage)* | RealityBootstrapper with `canonical_states[0].capital_province_decl_index=p` but `canonical_provinces[p].canonical_state_decl_index = None` (or = Some(s') for state s'≠0) → reject. | `geography.canonical_state_province_mismatch` |
| **AC-POL-21** *(LOW-2 coverage — island state)* | Bootstrap continent with one canonical_province on a water-isolated island (mainland-separated land cluster); island's only canonical state declared with capital at this island province → stage 5 succeeds: state's member_provinces contains only the island province; flood-fill from mainland canonical seeds does NOT cross Ocean=∞ to absorb island cells; island province retains its declared state_id. (Verifies island-state behavior is correct-by-construction under TerrainCost Ocean=∞.) | — |

---

## §17 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **POL-D1** | Per-province customization of TerrainCost weights (e.g., wuxia "qi-vein" cells trivialize Mountain cost for cultivation factions) | V2+ | Couples with PROG_001 cultivation-realm V2+; tracked alongside GEO-D7 MagicalAnomaly. |
| **POL-D2** | T6 LLM political-evolution proposal (NarrativePoliticalEdit Generator — LLM observes strategic events and proposes Merge/Split/Transfer) | V2+ | Parallel to GEO-D12 CreativeSeed extension; Forge admin reviews + materializes via T8. |
| **POL-D3** | Province adjacency graph derived from cell-neighbors (province A adjacent to province B if any cell in A neighbors any cell in B) | V1+30d+ | Useful for STRAT_001 V2+ supply-line + siege-modeling; not V1+30d-blocking (consumer derives from member_cells at read time). |
| **POL-D4** | State diplomatic axes (cultural-affinity / ideological-distance / historical-relations matrix) | V2+ DIPL_001 | Consumes State.culture_tag + State.ideology_ref. |
| **POL-D5** | Province-level resource_inventory generator | V2+ GEO-D10 | Coupled with GEO-D10. Province populated V1+30d enables the consumer; generator V2+. |
| **POL-D6** | Independent `culture_seed` separate from `political_seed` (currently shared per POL-Q3) | V1+30d+ | Re-rolling culture without re-rolling provinces; useful for authoring iteration; defer until author UX demands. |
| **POL-D7** | Default-culture-fallback for cells unassigned by any culture hearth | V1+30d | V1+30d default: first hearth's tag; could be smarter (climate-conditioned default; e.g., Polar cells default to "nomadic" culture). |
| **POL-D8** | Multi-state shared provinces (condominium / vassal-with-divided-allegiance) | V2+ | Currently strict 1-to-N per POL-D4; multi-allegiance is V2+ DIPL territory. |
| **POL-D9** | Capital relocation delta (`MoveStateCapital { state_id, new_capital_province_id }`) | V1+30d+ | Bookkeeping-only delta; deferred until V2+ DIPL or strategy-gameplay actually moves capitals. |
| **POL-D10** | Per-state population_tier propagation (state population = sum of member-province settlements' population_tier) | V2+ | Strategy-gameplay primitive; tracked alongside STRAT_001 V2+ entry. |
| **POL-D11** | Per-CultureRegion sub-cultures (e.g., "han_jiangnan" splits into "han_song_court" + "han_jianghu" within member_cells) | V2+ | Nested culture-region tree; needs author UX. |
| **POL-D12** | Province name-collision handling across canonical + procedural (procedural fallback naming Markov chain may produce same name as canonical) | V1+30d | V1+30d implementation: append numeric suffix; revisit if author UX complains. |
| **POL-D13** | Culture-aware procedural state naming (use `creative_seed.naming_styles[dominant_culture_tag]` Markov chain to name procedural states) | V2+ | Currently deferred per HIGH-4 fix (/review-impl 2nd-pass 2026-05-14) to sever stage-5/stage-8 circular dependency: stage-5 procedural state naming consuming stage-8 culture_tag created a cycle (stage 8 step 6 needs state.member_provinces from stage 5; stage 5 needs culture_tag from stage 8). V1+30d uses culture-agnostic naming (`{capital_province.name}_State_{hex}`); V2+ adds a post-stage-8 sub-pass that renames procedural states using the now-derived state.culture_tag. |
| **POL-D14** | CreateState / DestroyState V1+30d DeltaKinds — civil-war breakaway state creation + state extinction (MED-5 /review-impl 2nd-pass 2026-05-14) | V2+ | V1+30d civil-war breakaway scenarios go through `(SplitProvince → TransferProvinceToState)` chain referencing a pre-canonical-declared State only. Brand-new state creation mid-game has no path V1+30d; deferred to V2+ together with POL-D2 T6 NarrativePoliticalEdit Generator (LLM-proposed political evolution) since these often co-occur (LLM proposes "Republic of X emerges" → admin reviews + materializes via T8 CreateState delta). 2 new DeltaKinds at V2+ closed-enum bump per R3 additive: 9 V1+30d → 11 V2+ (CreateState + DestroyState). V2+ also adds the policy question: does DestroyState require all member_provinces to be Empty / TransferredAway / SetStateless first? Deferred-with-reasoning. |

---

## §18 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **POL-Q1** | Should procedural province count derive from continent area (cells.len) or from declared `procedural_density` enum? | V1+30d: enum-driven (Coarse/Medium/Fine maps to fixed cells/province ratio); revisit if authors complain about density granularity. |
| **POL-Q2** | When `canonical_provinces[i].canonical_state_decl_index = Some(s)` but the geometric flood-fill places the province inside a different state's reach (cost from state s farther than competing state) — which wins? | V1+30d: **canonical state declaration wins** (author intent); procedural flood-fill only assigns state for procedural provinces. Documented as POL-A4 invariant. |
| **POL-Q3** | Sub-seed split: shared `political_seed` for stages 5 + 8 OR separate `culture_seed`? | V1+30d: **shared** (matches Azgaar pattern; simpler authoring); split deferred POL-D6. |
| **POL-Q4** | Fallback when author's `canonical_provinces[i].seed_position_normalized` snaps to water with no land within radius 0.1? | V1+30d: **reject `geography.province_seed_unreachable_v1`**; author must move seed. Stricter than GEO_001's Settlement snap fallback because province affiliation is structural (not just naming). |
| **POL-Q5** | Storage representation: `Vec<Province>` monolithic OR per-province SQL table for spatial queries? | V1+30d: monolithic (~200KB / continent fine; matches GEO_001 pattern). V2+ STRAT_001 may force denormalization for province-graph SQL; revisit then. |

---

## §19 Cross-references

- [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — catalog extended with POL-* sub-prefix (entries POL-1..POL-N added 2026-05-14)
- [`_index.md`](_index.md) — folder index; GEO_002 row added 2026-05-14
- [`GEO_001`](GEO_001_world_geometry.md) — schema parent (§3 Province/State/CultureRegion + §4.5 GeographyDeltaKind + §5 stage 5/8 algorithm baseline + §16 GEO-D2/D8 deferrals activated here)
- [`GEO_001b`](GEO_001b_authoring_flow.md) — CreativeSeed authoring sibling; POL_001 additive within v2 schema (political_seed_mode + canonical_states + procedural_density)
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `world_geometry` annotation extended for POL_001 V1+30d activation (row added 2026-05-14)
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — `geography.*` namespace extended with 15 V1+30d POL rule_ids (§1.4); GeographyDeltaKind closed-enum bump 5 V1 → 9 with V1+30d active (§1); capability `can_edit_political_geography` added (§3)
- [`_boundaries/99_changelog.md`](../../_boundaries/99_changelog.md) — DRAFT 2026-05-14 entry top-anchored
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) — EVT-T3 / T8 sub-shapes unchanged (POL_001 reuses GEO_001 registrations)
- [`features/00_map/MAP_001_map_foundation.md`](../00_map/MAP_001_map_foundation.md) — V1+ position auto-derivation row gains "state-level via Province centroid" entry at MAP_001 LOCK (parallel to GEO-D5 settlement row)
- [`features/00_place/PF_001_place_foundation.md`](../00_place/PF_001_place_foundation.md) — PF-D7 procedural place generation gains culture_tag context input
- [`features/03_actor_substrate/TIT_001_title_foundation.md`](../03_actor_substrate/TIT_001_title_foundation.md) — V1+30d cross-ref: titles can reference State.capital_province name post-POL ship

---

## §20 Implementation readiness

**Design layer (this commit):** ✅ schema activation contract + 4 V1+30d DeltaKinds + stage 5 algorithm + stage 8 algorithm + 15 acceptance scenarios + 15 rule_ids + capability + composition with siblings + fork inheritance — all declared.

**Implementation phase (V1+30d):** 📦 stage 5 + stage 8 reference impl in `world-service` `geography-generator` Rust module · apply_delta total-function for 4 V1+30d DeltaKinds · capability `can_edit_political_geography` issuance flow in auth-service · CI gates: replay-determinism (seed → byte-identical provinces + states + culture_regions) + apply_delta total-function for 4 new variants + canonical-JSON normalization (per SPIKE_04 GAP-S2.A discipline inherited).

**Downstream consumer integration (V1+30d / V2+):** 📦 MAP_001 light reopen (state-level position derivation row per POL § coordination note) · PF_001 procedural place generation activating PF-D7 V1+30d consuming culture_tag · S9 prompt-assembly `[GEOGRAPHIC_CONTEXT]` join enriched with state_name + culture_tag (V1+30d S9 closure pass adds 2 placeholder fields).

**Status:** DRAFT 2026-05-14. CANDIDATE-LOCK upon §16 acceptance scenarios passing integration tests against the reference POL implementation in `world-service`. LOCK upon downstream consumers integrating successfully + STRAT_001 V2+ design entry consuming the locked POL schema as read-only inputs.
