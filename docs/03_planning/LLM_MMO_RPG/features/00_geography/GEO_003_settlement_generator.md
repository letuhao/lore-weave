# GEO_003 — Settlement Generator (SET_001)

> **Conversational name:** "Settlement Generator" (SET). V1+30d sibling of GEO_002 POL_001 that activates GEO_001's V1-schema-reserved settlement layer (`world_geometry.settlements: Vec<Settlement>`). Implements pipeline **stage 6** (Settlement placement — burg-score weighted Poisson-disk placement; SettlementRole assignment via political-first-then-terrain hybrid; population_tier hybrid derivation). Coordinates with POL_001 V1+30d: stage 6 runs AFTER stage 5 so state.capital_province cells can receive Capital role. Hybrid seed source per SET-D2: canonical author declarations take priority; procedural Poisson-disk fills remainder. Activates 3 V1+30d `GeographyDeltaKind` variants (RelocateSettlement / PromoteSettlement / RemoveSettlement). Composes with future TVL_001 V1+ (settlement-to-settlement travel) + future STRAT_001 V2+ (settlement-as-strategic-target).
>
> **Category:** GEO — Geography Foundation (V1+30d generator; activates GEO_001 schema-reserved settlement layer)
> **Status:** **DRAFT 2026-05-14** (Phase 0 D1-D7 LOCKED with user approval option 1)
> **Catalog refs:** [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — extends `GEO-*` namespace with SET-* sub-prefix (`SET-*` axioms · `SET-D*` deferrals · `SET-Q*` open questions · `AC-SET-*` acceptance)
> **Builds on:** [`GEO_001`](GEO_001_world_geometry.md) §3.1 (Settlement struct schema + `settlements: Vec<Settlement>` already declared; `settlement_seed` derived; `creative_seed.canonical_settlements: Vec<CanonicalSettlementDecl>` author-declared inputs V1) · §4.3 SettlementRole 6-variant closed enum (Hamlet / Village / Town / City / Capital / Fortress) · §4.5 GeographyDeltaKind closed enum — AddNamedSettlement V1 already exists; SET_001 V1+30d adds 3 more · §5 stage 6 algorithm baseline declared · §16 GEO-D3 (this feature is the activation path) · [`GEO_001b`](GEO_001b_authoring_flow.md) (CreativeSeed authoring; CanonicalSettlementDecl already V1) · [`GEO_002 POL_001`](GEO_002_political_layer.md) (sibling V1+30d feature; SET_001 stage 6 runs AFTER POL_001 stage 5 so Capital role can reference state.capital_province; populates Province.capital_settlement_id linkage)
> **Resolves:** Settlement-graph empty V1+30d-blocker (Settlements remained empty V1 except canonical-declared; SET_001 fills graph procedurally) · LLM-context grounding settlement-name gap (prompt-assembly `[GEOGRAPHIC_CONTEXT]` gains `nearest_settlement_name + settlement_role` per cell once SET ships; POL_001 V1+30d already documented this slot) · Admin canonization runtime settlement tooling (3 V1+30d DeltaKinds — Relocate / Promote / Remove — for narrative settlement evolution post-bootstrap; `RemoveSettlement` closes V1 gap where AddNamedSettlement existed but no removal path) · GEO_001 §16 deferral GEO-D3 closed · POL_001 Province.capital_settlement_id linkage population (POL_001 V1+30d ships with field declared but None V1+30d standalone; SET_001 V1+30d populates)
> **Defers to:** future **TVL_001 V1+** (settlement-to-settlement travel mechanics; consumes Settlement.cell_id + SettlementRole + population_tier for movement modeling) · future **GEO_004 ROUTE_001 V1+30d** (route network generator; consumes Settlement graph for Dijkstra source/sink pairs — SET ships first to provide settlements; ROUTE ships second to network them) · future **STRAT_001 V2+** (consumes Settlement graph for army-position-on-settlement + siege-target modeling) · future **DIPL_001 V2+** (consumes settlement-Population for state-power calculations) · future **CSC_001** V1+30d settlement sub-cell interior (skeleton selection per role + culture_tag — orthogonal; SET owns the settlement-graph schema, CSC owns the interior composition)

---

## §1 Why this exists

Three concrete gaps that SET_001 closes.

**Gap 1 — Settlement-graph empty V1+30d-blocker.** GEO_001 V1 ships `world_geometry.settlements: Vec<Settlement>` as schema-reserved Vec but populates it only from `creative_seed.canonical_settlements` (author-pinned wuxia worlds where every settlement is declared). The vast majority of V1+ worlds will be partially-canon: the author seeds 3-50 canonical settlements ("Tương Dương", "Khai Phong", "Yên Vũ Lâu"), then expects the rest of the continent to be procedurally seeded with consistent burg placement + role assignment. Without SET_001, those worlds reject `geography.layer_activation_deferred_v1` on any runtime settlement write. SET_001 lifts this reject for the four populated entry-points (pipeline stage 6 / 3 V1+30d DeltaKinds / AddNamedSettlement V1 admin path / canonical author declarations).

**Gap 2 — POL_001 Province.capital_settlement_id linkage stays None V1+30d.** GEO_002 POL_001 V1+30d ships with `Province.capital_settlement_id: Option<SettlementId>` declared but None V1+30d standalone — POL_001 produces province + state graphs but cannot wire state capitals to actual settlements without the Settlement graph existing. SET_001 V1+30d closes this loop: stage 6 placement runs AFTER stage 5; settlements landing in `state.capital_province.member_cells` get Capital role + their SettlementId populates `Province.capital_settlement_id` for the state's capital province. Strategy substrate readiness becomes complete (Province + State + Settlement triangle all populated).

**Gap 3 — Admin canonization tooling for runtime settlement evolution is asymmetric.** GEO_001 ships `AddNamedSettlement` V1 (admin can add) but NO removal or relocation primitive. Long-running wuxia worlds need:
- **RelocateSettlement** — settlement moves to a new cell after narrative event (e.g., flood destroys village; rebuilt 3 cells downstream).
- **PromoteSettlement** — settlement gains role + population_tier after expansion (e.g., Hamlet grows to Village after agricultural reform; Town becomes Capital after political event).
- **RemoveSettlement** — settlement extinct after canonical event (e.g., destroyed in war; abandoned during plague).

These 3 are the asymmetric closing-set the V1 schema implied but never specified. SET_001 V1+30d adds all 3 as closed-enum bump per R3 additive.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Settlement** | GEO_001 §3.1 `Settlement { id, name, cell_id, role, population_tier, canon_ref, channel_id }` | V1+30d SET_001 populates `cell_id` (placement) + `role` (Capital / City / Town / Village / Hamlet / Fortress) + `population_tier` (0..6). `channel_id: Option<ChannelId>` stays None V1+30d (town-tier channel activation deferred V1+30d+ per SET-D8). |
| **BurgScore** | Per-cell `f32` derived from `(BiomeKind, heightmap, river_flux, is_coast, neighbor_water_proximity)` | The placement priority metric. Components: population_potential (Plain=1.0, Hill=0.8, Forest=0.7, Marsh=0.3, Mountain=0.2, Desert=0.1, Tundra=0.2, others 0) × water_proximity_bonus (×1.5 if is_coast OR river_flux > threshold) × climate_friendliness (Temperate/Mediterranean/Subtropical=1.0; Boreal/Tropical=0.8; Arid/Polar=0.4; Highland=0.6). Ocean / Lake / Glacier = 0.0 (uninhabitable). Fixed by `generator_pipeline_version`; bumping requires V2+ upcaster. Per SET-Q1 V1+30d defaults; tuning slot reserved for V1+30d+ if author UX demands. |
| **PoissonDiskMinSeparation** | `f32` per-stage parameter | Settlements MUST be ≥ this Euclidean distance apart (normalized [0,1] continent coordinates). Derived from `SettlementDensityHint`: Sparse=0.08, Medium=0.05, Dense=0.03. Prevents settlement clumping. |
| **SettlementDensityHint** | Closed enum 3 V1+30d variants — Sparse / Medium / Dense | Per SET-D5 default Medium. Surfaced in `creative_seed.settlement_density_hint: SettlementDensityHint` (V1+30d additive — `creative_seed.schema_version` bumps 3 → 4 mirroring POL_001's HIGH-1 fix discipline). |
| **CellsPerSettlementTarget** | `usize` derived from SettlementDensityHint | Target settlement count = `cells.len() / CellsPerSettlementTarget`. Sparse=800 cells/settlement (~12 settlements per 10k-cell continent — rural civilization), Medium=400 (~25 settlements — V1+30d default), Dense=200 (~50 settlements — urban civilization). Canonical settlements count toward this target (their slots displace procedural). |
| **SettlementSeedSource** | Closed enum 2 V1+30d variants — Canonical / Procedural | Per SET-D2 hybrid pattern. Canonical = from `creative_seed.canonical_settlements[i]` (author-pinned name + position + role + population_tier). Procedural = Poisson-disk weighted sample over remaining-uncovered land cells. |
| **SettlementSeedMode** | Closed enum 3 V1+30d variants — Canonical / Procedural / Hybrid | Per SET-D2 default Hybrid. Mirrors POL_001's PoliticalSeedMode 3-variant pattern. Canonical = only canonical_settlements placed (no procedural fill); Procedural = ignore canonical_settlements entirely; Hybrid (default) = canonical first + procedural fills to target count. |
| **SettlementRole assignment** | Hybrid political-first-then-terrain (SET-D4) | Step 1 — political-first: settlements landing in `state.capital_province.member_cells` (POL_001 stage 5 output) → Capital role (exactly 1 per state; if multiple settlements in capital province, lowest GeoCellId wins per stage-1 cell_id deterministic-order invariant). Step 2 — terrain heuristic for non-Capital: mountain-pass cells → Fortress; coast-and-high-river-flux cells with population_tier ≥ 3 → port City; remainder → role by population_tier mapping (tier 0..1 → Hamlet, tier 1..2 → Village, tier 2..3 → Town, tier 3..6 → City). |
| **Population_tier derivation** | Hybrid canonical-or-burg-score-mapped (SET-D3) | Canonical settlements: use author-declared `CanonicalSettlementDecl.population_tier` as-is. Procedural: `tier = clamp(floor(burg_score / max_burg_score_on_continent × 6), 0, 6)`. Mountain Fortress / port City may override via terrain bonus +1 (capped 6). |
| **Settlement.cell_id uniqueness** | One settlement per cell V1+30d | Two settlements at same cell V1+30d reject (geometric clumping is the Poisson-disk discipline's whole point). Canonical settlements snap to declared cell (or nearest unoccupied land per GEO-Q2 radius 5 fallback). V2+ multi-settlement-per-cell deferred (SET-D9) for urban-cluster modeling. |

---

## §2.5 Event-model mapping (per 07_event_model Option C taxonomy)

SET_001 introduces **NO new EVT-T* category**. Reuses existing GEO_001 + POL_001 event-model with one activation + three DeltaKind closed-enum additions:

| SET event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| Settlement layer materialized at bootstrap (stage 6 runs; settlements populated; Province.capital_settlement_id linked) | **EVT-T3 Derived** | `aggregate_type=world_geometry` (field delta — settlements Vec grows from empty/canonical-only to populated; provinces[i].capital_settlement_id linked; bumps `world_geometry.last_delta_event_id`) | Aggregate-Owner role (world-service post-stage-5 + GEO_001 §11 bootstrap order) | Causal-ref to triggering EVT-T4 GeographyBorn. SET_001 V1+30d adds stage 6 emission as a T3 layer-activation event per continent (separate from POL_001's stage 5+8 emissions — independent T3 events per stage for replay-debug clarity). Replay-deterministic per `settlement_seed`. |
| Forge admin runtime settlement edit (Relocate / Promote / Remove) | **EVT-T8 Administrative** | `Forge:EditGeographyDelta { continent_channel_id, delta_kind: RelocateSettlement \| PromoteSettlement \| RemoveSettlement, delta_payload, prev_delta_id }` | WA_003 Forge | Already-registered sub-shape (added 2026-05-13 GEO_001 fix cycle MED-1). SET_001 V1+30d extends `GeographyDeltaKind` closed enum from 9 (5 V1 + 4 V1+30d POL) → 12 V1+30d (+3 SET) per R3 additive. RemoveSettlement is Tier 1 ImpactClass=Destructive per S5 (matches RemoveRoute V1 GEO_001 + 4 POL V1+30d DeltaKinds); RelocateSettlement + PromoteSettlement are Tier 2 ImpactClass=Griefing (matches AddNamedSettlement V1 GEO_001) — reversible canonical edits. Per-DeltaKind tier discipline documented §9. |
| LLM-derived settlement-evolution proposal (V2+) | **EVT-T6 Proposal** | `SET:NarrativeSettlementEdit` (V2+ reservation) | future LLM settlement-arc Generator | V2+: LLM proposes Promote/Relocate/Remove based on observed economic + narrative events (population_tier deltas from RES_001 production rates, NPC migration patterns from NPC_001). Forge admin reviews + materializes via T8. V1+30d scope-out: T8 admin only. |

No new EVT-T* row in `_boundaries/01_feature_ownership_matrix.md`. The §4 EVT-T8 sub-shapes table's existing `Forge:EditGeographyDelta` row remains owned by GEO_001 (the schema-owning feature) — SET_001 V1+30d extends the variant set behind that sub-shape without adding a new sub-shape row, mirroring POL_001 V1+30d's discipline.

---

## §3 Schema activation

**No new aggregate.** SET_001 V1+30d populates GEO_001 §3.1 `world_geometry.settlements: Vec<Settlement>` + `provinces[i].capital_settlement_id: Option<SettlementId>` (POL_001-declared, V1+30d empty until SET ships).

Extends `GeographyDeltaKind` closed enum (R3 additive — no schema_version bump for world_geometry aggregate itself; CreativeSeed schema_version DOES bump 3 → 4 for new SettlementDensityHint field):

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

    // ─── V1+30d SET_001 (3 variants; this commit — closed-enum bump per R3 additive; total 12 V1+30d active) ───
    RelocateSettlement { settlement_id: SettlementId, new_cell_id: GeoCellId, reason: I18nBundle },
    PromoteSettlement { settlement_id: SettlementId, new_role: Option<SettlementRole>, new_population_tier: Option<u8>, reason: I18nBundle },
    RemoveSettlement { settlement_id: SettlementId, reason: I18nBundle },
}
```

**Why `Option<SettlementRole>` + `Option<u8>` on PromoteSettlement (NOT separate Promote-Role / Promote-PopulationTier kinds):** matches the natural admin pattern (promote often combines role + tier change; "Tống makes Lương Châu the new capital and elevates it to population_tier 5" is one canonical event, not two). Validator requires at-least-one-Some (else PromoteSettlement is a no-op).

**`world_geometry.schema_version` bumps 1 → 2 (HIGH-3 fix /review-impl 2026-05-14)** — SET_001 adds `seed_source: Option<SettlementSeedSource>` field to the Settlement struct (per §4.3). Per I14 + GEO_001 MED-5 fix precedent (`schema_version` field added per I14 additive evolution discipline) + R3 default-tolerant readers, every additive struct-field change to a `world_geometry` sub-struct bumps the aggregate schema_version. **Reader semantics**: v2 readers see Settlement.seed_source natively; v1 readers (pre-SET cohort) have their own `generator_pipeline_version` pin pre-SET — they never read v2 data at runtime per the cross-version data path documented in POL_001 §3 (MED-11 precision). The bump is operative ONLY at fresh bootstrap (where reader + writer share `generator_pipeline_version` post-SET-ship). Migration path: legacy Settlement rows pre-SET carry `seed_source = None` (R3 default-tolerant read absent field → None). `GeographyDeltaKind` is a closed-enum bump per R3 additive (separate concern; closed-enum bumps don't affect aggregate schema_version per GEO_001 §3 + GEO_002 §3 precedent).

**`creative_seed.schema_version` bumps 3 → 4 (SET_001 ship)** — SET_001 adds one additive field (`settlement_density_hint`); per I14 + GEO_001b + POL_001 precedent (every additive field-set in CreativeSeed bumps the version), v4 is the natural next. Reader semantics: v4 readers see v4 data natively; v3 readers (pre-SET cohort) have their own `generator_pipeline_version` pin pre-SET — they never read v4 data at runtime per the cross-version data path documented in POL_001 §3 (MED-11 precision). Default-tolerant per R3: absent `settlement_density_hint` → reader assumes Medium.

**Capability addition (per `_boundaries/02_extension_contracts.md` §3 capability JWT):** `can_edit_settlement_geography` claim — required for the 3 new V1+30d DeltaKinds AuthorizationGate. Disjoint from existing `can_edit_geography` (which V1+30d narrows to SetBiomeOverride / AddRoute / RemoveRoute / RenameRegion + V1 AddNamedSettlement) and from POL_001's `can_edit_political_geography` (which authorizes the 4 V1+30d political DeltaKinds). Migration plan documented §9 mirroring POL_001 MED-6 precedent.

---

## §4 Closed enums (SET_001 V1+30d)

### 4.1 SettlementSeedMode (3 V1+30d; closed)

```rust
pub enum SettlementSeedMode {                               // closed; per-CreativeSeed declaration
    Canonical,                                              // NO procedural seeds; canonical_settlements alone (no fill-to-target). Settlements.len() = canonical_settlements.len() post-bootstrap.
    Procedural,                                             // pure algorithmic; canonical_settlements IGNORED even if present (V1+30d fallback / dev mode for "just give me a generated world from seed"). All settlements procedural.
    Hybrid,                                                 // V1+30d DEFAULT — canonical seeds placed first (priority); procedural Poisson-disk fills to target count.
}
```

Per SET-D2 default Hybrid. Surfaced in `creative_seed.settlement_seed_mode: SettlementSeedMode` (V1+30d additive within v4 — additive per R3 default-tolerant readers; absent → reader assumes Hybrid).

### 4.2 SettlementDensityHint (3 V1+30d; closed)

```rust
pub enum SettlementDensityHint {                            // closed; cells-per-settlement ratio + Poisson-disk min-separation
    Sparse,                                                 // 800 cells/settlement; PoissonDiskMinSeparation 0.08; ~12 settlements per 10k-cell continent (rural civilization)
    Medium,                                                 // 400 cells/settlement; PoissonDiskMinSeparation 0.05; ~25 settlements per 10k-cell continent (V1+30d DEFAULT)
    Dense,                                                  // 200 cells/settlement; PoissonDiskMinSeparation 0.03; ~50 settlements per 10k-cell continent (urban civilization)
}
```

Per SET-D5 default Medium. Surfaced in `creative_seed.settlement_density_hint: SettlementDensityHint`.

### 4.3 SettlementSeedSource (2 V1+30d; closed)

```rust
pub enum SettlementSeedSource {                             // closed; per-settlement provenance tag
    Canonical { decl_index: u32 },                          // points back to creative_seed.canonical_settlements[decl_index]
    Procedural { burg_score_rank: u32 },                    // rank within procedural Poisson-disk sample by burg_score descending
}
```

Stored as `Settlement.seed_source` field (additive Option<SettlementSeedSource> on the Settlement struct V1+30d additive — V1 GEO_001 readers tolerate absent field per R3; field is None for V1 canonical-only settlements pre-SET-ship).

### 4.4 BurgScoreComponent (informational; not a serialized enum)

Documented decomposition of burg_score for replay-debug clarity. Not a runtime-visible enum:

| Component | Formula | Notes |
|---|---|---|
| population_potential | Plain=1.0 / Hill=0.8 / Forest=0.7 / Marsh=0.3 / Mountain=0.2 / Desert=0.1 / Tundra=0.2 / Coast=0.9 / Beach=0.7 / Jungle=0.4 / River=0.8 / Ocean=Lake=Glacier=0.0 | Per-BiomeKind baseline |
| water_proximity_bonus | ×1.5 if is_coast OR river_flux > 1000 else ×1.0 | Coastal + riverside cities favored |
| climate_friendliness | Temperate/Mediterranean/Subtropical=1.0 / Boreal/Tropical=0.8 / Arid/Polar=0.4 / Highland=0.6 | Per-ClimateZone modifier |
| chokepoint_bonus | ×1.3 if cell is between high-altitude neighbors (mountain pass) | Strategic terrain heuristic for stage-6 Fortress role candidates |

Final burg_score = `population_potential × water_proximity_bonus × climate_friendliness × chokepoint_bonus`. Fixed by `generator_pipeline_version`; bumping requires V2+ upcaster.

---

## §5 Pipeline activation — stage 6

SET_001 V1+30d implements pipeline stage 6 (Settlement placement), which GEO_001 §5 declared as V1+ activation slot. Stages 1-4 (Voronoi / heightmap / climate / biome+river) are V1 GEO_001 territory; stages 5 + 8 (political growth + culture spread) are V1+30d POL_001 territory; stage 6 sits between (post-POL stage 5; pre-POL stage 8 acceptable since stage 8 doesn't reference settlements — POL_001's culture-spread is cell-level not settlement-level).

### 5.1 Stage 6 — Settlement placement (burg-score weighted Poisson-disk)

```
Inputs:
  - cells, neighbors, biomes, heightmap, river_flux, is_coast (from stages 1-4)
  - provinces, states (from stage 5 POL_001 V1+30d; specifically state.capital_province_id + state.member_provinces)
  - settlement_seed: u64 (from GeographySeed)
  - creative_seed.canonical_settlements: Vec<CanonicalSettlementDecl>            (already in GEO_001 V1 schema)
  - creative_seed.settlement_seed_mode: SettlementSeedMode                        (SET_001 V1+30d additive within v4; default Hybrid)
  - creative_seed.settlement_density_hint: SettlementDensityHint                  (SET_001 V1+30d additive within v4; default Medium)

Outputs:
  - world_geometry.settlements: Vec<Settlement>
  - settlement.cell_id, settlement.role, settlement.population_tier all populated
  - provinces[i].capital_settlement_id populated for state-capital provinces

Algorithm (per SET-D2 hybrid + SET-D4 political-first-then-terrain role assignment + SET-D3 hybrid population_tier):

  STEP A — burg_score precomputation (deterministic per generator_pipeline_version):
  A1. For each land cell c (biome ∉ {Ocean, Lake, Glacier}):
        c.burg_score = population_potential[biome] × water_proximity_bonus(is_coast[c], river_flux[c])
                      × climate_friendliness[climate_zones[c]] × chokepoint_bonus(neighbors[c], heightmap)
  A2. Water + Glacier cells: burg_score = 0.0 (uninhabitable; excluded from Poisson-disk sample).
  A3. max_burg_score = MAX(burg_score) over all land cells (used for population_tier mapping in STEP D).

  STEP B — canonical placement (priority):
  B1. If settlement_seed_mode == Procedural: skip step B entirely (ignore canonical_settlements).
  B2. For each CanonicalSettlementDecl in creative_seed.canonical_settlements (Vec order — author intent preserved):
        snap_cell = nearest land cell to position_normalized within radius 0.1 (per GEO-Q2 fallback);
        reject `geography.canonical_settlement_unreachable_v1` if no land cell within radius;
        reject `geography.canonical_settlement_cell_collision` if snap_cell already occupied by an earlier canonical;
        emit Settlement { id: blake3-derive (LOW-3 fix /review-impl — canonical inputs: continent_channel_id || settlement_seed || "stage6_canonical" || decl_index_be_bytes; truncated to SettlementId opaque newtype per SPIKE_04 GAP-S3.E discipline),
                          name: decl.name, cell_id: snap_cell, role: decl.role, population_tier: decl.population_tier,
                          canon_ref: decl.canon_ref, channel_id: None,
                          seed_source: Some(Canonical { decl_index }) };

  STEP C — procedural placement (Poisson-disk weighted sample):
  C1. If settlement_seed_mode == Canonical: skip step C (no procedural fill; settlements.len() = canonical_settlements.len()).
  C2. target_count = cells.len() / cells_per_settlement_target[settlement_density_hint];
        remaining_target = max(0, target_count - canonical_count).
  C3. Weighted Poisson-disk sampler iterates over land cells in deterministic order (ascending GeoCellId — stage-1 invariant):
        - candidate cell c accepted iff:
          (a) c.burg_score > 0.05 (min-threshold; rejects degenerate placements in low-quality cells)
          (b) c.cell_id NOT already occupied by another settlement (MED-1 fix /review-impl — explicit cell-uniqueness check; Euclidean min-separation alone implicit per Voronoi geometry but explicit check rules out edge cases)
          (c) min-distance to any already-placed Settlement ≥ PoissonDiskMinSeparation[settlement_density_hint]
          (d) acceptance probability = c.burg_score / max_burg_score (deterministic_rng draws from settlement_seed_substream(b"stage6_procedural") per candidate)
        - stop when remaining_target settlements accepted OR all land cells exhausted (whichever first; if exhausted, V1+30d records under-fill metric for ops dashboard, doesn't reject)
  C4. emit Settlement { id: blake3-derive (LOW-3 fix /review-impl — explicitly blake3 per SPIKE_04 GAP-S3.E discipline; canonical inputs: continent_channel_id || settlement_seed || "stage6_procedural" || procedural_index_be_bytes; truncated to SettlementId opaque newtype),
                        name: V1+30d culture-agnostic synthesis (HIGH-1 fix /review-impl 2026-05-14 — culture_regions NOT populated at stage 6 time since POL stage 8 runs AFTER stage 6;
                              V1+30d: name = format!("{}_{:06x}", biomes[cell_id].as_str(), settlement_id_short_hex);
                              V2+ culture-aware Markov-chain naming via creative_seed.naming_styles[cell.dominant_culture_tag] deferred per new SET-D13),
                        cell_id: accepted_cell, role: <assigned in STEP D>, population_tier: <derived in STEP D>,
                        canon_ref: None, channel_id: None,
                        seed_source: Some(Procedural { burg_score_rank: rank_among_procedural }) };

  STEP D — role assignment (hybrid political-first-then-terrain per SET-D4; HIGH-2 + HIGH-4 fixes /review-impl 2026-05-14):
  D0. CANONICAL OVERRIDE (processed FIRST per HIGH-2 fix — canonical role declarations take priority over algorithmic assignment):
        For each canonical settlement: role = decl.role (author intent preserved); marked as canonical-pinned (not subject to D1/D2 reassignment).
  D1. POLITICAL FIRST (operates only on settlements NOT canonical-pinned per D0; HIGH-2 fix):
        For each state s in POL_001 stage 5 output:
          capital_province = states[s].capital_province;
          // If any canonical settlement in capital_province already has decl.role == Capital: that's the state's Capital.
          // SET-V16 canonical_capital_collision (MED-2 fix /review-impl) catches ≥2 canonicals declaring Capital in same province.
          // If no canonical Capital in capital_province: assign Capital to lowest-GeoCellId NON-canonical-pinned settlement
          // in capital_province.member_cells (deterministic tiebreaker per stage-1 invariant).
          // If no non-canonical-pinned settlement exists in capital_province: SET_001 emits a forced procedural placement
          // at the lowest-GeoCellId LAND cell in capital_province.member_cells (NOT the geometric centroid, since centroid
          // could fall in water for concave provinces or already-occupied; MED-5 fix), bypassing burg_score min-threshold
          // (MED-3 fix — forced placement guarantees state's capital_settlement_id always Some), marked as
          // Procedural with synthetic rank=u32::MAX.
          capital_settlement.role = Capital;
          provinces[capital_province].capital_settlement_id = Some(capital_settlement.id);
  D2. TERRAIN HEURISTIC (operates only on settlements NOT canonical-pinned AND NOT assigned Capital by D1):
        - if cell is mountain-pass-cell (`cell.heightmap < 30000 AND ≥2 neighbors have heightmap > 50000` per HIGH-4 fix — low corridor between high regions, NOT high cell with low neighbor which describes cliff/slope) → role = Fortress
        - else if is_coast[cell] AND river_flux[cell] > 1000 AND population_tier ≥ 3 → role = City (port-City special-case)
        - else fallback to STEP E population_tier mapping
  D3. (HIGH-2 fix: rule moved to D0 above and reframed as canonical-FIRST processing precedence rather than override-after.)

  STEP E — population_tier derivation (hybrid per SET-D3):
  E1. CANONICAL: use decl.population_tier as-is.
  E2. PROCEDURAL: tier = clamp(floor(cell.burg_score / max_burg_score × 6), 0, 6).
        Special-case: mountain-pass Fortress: tier += 1 (capped 6) — strategic-terrain bonus.
        Special-case: port City (D2 match): tier already ≥ 3 by D2 precondition; no further bonus.
  E3. ROLE MAPPING for non-special-cased settlements (after step D fallback):
        tier 0..1 → Hamlet / tier 1..2 → Village / tier 2..3 → Town / tier 3..6 → City.
        Already Capital / Fortress / port City keep their D-assigned role; only fallback procedural settlements use this mapping.

Determinism: same (settlement_seed, creative_seed snapshot, generator_pipeline_version, POL stage 5 outputs) → bitwise-identical settlements + capital_settlement_id linkages (modulo HashMap normalization per SPIKE_04 GAP-S2.A canonical-JSON discipline; SET_001 V1+30d adopts the same CI gate).

Cost envelope (V1+30d target):
  10k cells continent → ~30ms wall-clock (single-threaded Rust; Poisson-disk linear in cells × accepted-count). +30ms beyond stages 1-5 GEO_001 + POL_001 baseline (combined stages 1-6 ≈ 110ms).
  Adds ~50KB compressed to world_geometry aggregate (Vec<Settlement>×~25 settlements per 10k-cell continent at V1+30d default Medium density).
  Total post-SET continent generation (LOW-2 fix /review-impl 2026-05-14 — per-stage marginal costs, not cumulative): stages 1-4 (50ms GEO_001 baseline) + stage 5 (+30ms POL_001 marginal — 80ms cumulative with HIGH-3 clustering) + stage 6 (+30ms SET_001 marginal — 110ms cumulative) + stage 8 (+40ms POL_001 culture spread marginal — 150ms cumulative for full pipeline at 10k cells / Medium density). Within V3 scale anchor budget per DP-S8 (200ms upper budget; 150ms total leaves ~25% headroom for V1+30d+ stages 7 ROUTE generation).
```

**Why settlement_seed sub-streaming** (mirrors POL_001's per-stage substream discipline): SET_001 stage 6 derives RNG via `settlement_seed_substream(tag) = blake3(settlement_seed || tag)` with stage-tagged constants (`b"stage6_canonical"`, `b"stage6_procedural"`). Cross-stage RNG-state pollution prevented; stage 6 canonical placement consuming N RNG draws does NOT shift stage 6 procedural placement's RNG output. Reserved future tags: `b"stage6_role_tiebreaker"` for V1+30d+ if role assignment gains a probabilistic component.

---

## §6 CreativeSeed authoring extensions

SET_001 V1+30d bumps `creative_seed.schema_version` 3 → 4 (1 additive field; mirrors GEO_001b 1→2 + POL_001 2→3 precedent):

```rust
// Additive fields on CreativeSeed (v3 → v4 bump; SET_001 V1+30d 2026-05-14)
pub struct CreativeSeed {                                    // ... existing GEO_001 + GEO_001b + POL_001 fields elided ...
    pub schema_version: u32,                                 // V1 GEO_001=1; V1+ GEO_001b=2; V1+30d GEO_002 POL_001=3; V1+30d GEO_003 SET_001=4
    pub settlement_seed_mode: SettlementSeedMode,           // V1+30d additive; default-tolerant Hybrid when absent (R3 + I14)
    pub settlement_density_hint: SettlementDensityHint,     // V1+30d additive; default-tolerant Medium when absent (R3 + I14)
}
```

Existing `creative_seed.canonical_settlements: Vec<CanonicalSettlementDecl>` (declared in GEO_001 §6 V1; shape unchanged) gets its V1+30d activation here — `CanonicalSettlementDecl` shape from GEO_001:

```rust
pub struct CanonicalSettlementDecl {                        // shape declared in GEO_001 §6 V1 — UNCHANGED by SET_001
    pub name: LocalizedName,
    pub position_normalized: (f32, f32),                    // 0.0..=1.0; snap to nearest land cell within radius 0.1 (GEO-Q2 fallback); SET-V1 reject if no land in radius
    pub role: SettlementRole,
    pub population_tier: u8,
    pub canon_ref: Option<BookCanonRef>,
}
```

**LLM-authoring contract (GEO_001b sibling-doc):** SET_001 V1+30d bumps the LLM authoring template to v3 (CreativeSeed schema v4 surface; mirrors how POL_001 bumped v1.tmpl → v2.tmpl for CreativeSeed v3). New template at `contracts/prompt/templates/world_authoring/v3.tmpl` adds prompt-sections covering `settlement_seed_mode + settlement_density_hint`. The CreativeSeed v4 schemars-generated JSON Schema includes the 2 new fields so schema-constrained generation enforces them. Per §12Y.L2 governance, template version bump from v2 → v3 requires CI fixture update (the existing `template_version_deprecated` reservation in `authoring.*` namespace activates at SET ship to deprecate v2.tmpl alongside v1.tmpl). SpatialPreference 14-variant enum (GEO_001b) continues to support LLM-friendly canonical settlement placement via `NearSettlement` / `NearBiome` / `Coastal` etc. — no GEO_001b change.

---

## §7 Apply_delta total-function for 3 V1+30d DeltaKinds

Extends GEO_001 §7 + POL_001 §7 `apply_delta` per-variant impl:

### 7.1 RelocateSettlement

```rust
fn apply_relocate_settlement(wg: &mut WorldGeometry, payload: &RelocateSettlementPayload) -> () {
    // 1. Validate (ReferentialIntegrityGate at validator pipeline):
    //    - settlement_id exists
    //    - new_cell_id ∈ cells
    //    - wg.biomes[new_cell_id] ∉ {Ocean, Lake, Glacier} (uninhabitable; reject geography.settlement_target_uninhabitable)
    //    - no other settlement at new_cell_id (one-settlement-per-cell V1+30d invariant; reject geography.settlement_cell_collision)
    //    - if settlement.role == Capital: new_cell_id MUST be in settlement's state.capital_province.member_cells
    //      (Capital settlement cannot relocate outside its state's capital province; would orphan state's capital
    //      linkage. Use TransferProvinceToState + PromoteSettlement first if intent is "move capital to new province".
    //      Reject geography.capital_relocate_outside_capital_province.)
    // 2. Update wg.settlements[settlement_id].cell_id = new_cell_id.
    // 3. If settlement was a province capital (provinces[p].capital_settlement_id == Some(this)): no change to
    //    Province.capital_settlement_id (settlement identity preserved; only cell moved).
}
```

**Validators:** `geography.settlement_target_uninhabitable` · `geography.settlement_cell_collision` · `geography.capital_relocate_outside_capital_province` · `geography.settlement_not_found`.

### 7.2 PromoteSettlement

```rust
fn apply_promote_settlement(wg: &mut WorldGeometry, payload: &PromoteSettlementPayload) -> () {
    // 1. Validate:
    //    - settlement_id exists
    //    - at least one of (new_role, new_population_tier) is Some (else this is a no-op admin action;
    //      reject geography.promote_settlement_no_change)
    //    - if new_role == Some(Capital): the settlement's current cell_id MUST be in some state's
    //      state.capital_province.member_cells AND that state's capital_province.capital_settlement_id
    //      MUST currently be None OR equal settlement_id (cannot have 2 Capitals in same province).
    //      Reject geography.capital_role_invalid_context.
    //    - if new_population_tier is Some: 0 ≤ tier ≤ 6 (reject geography.population_tier_out_of_range)
    //    - if old_role == Capital AND new_role == Some(non-Capital): demoting a state capital.
    //      V1+30d HARD-REJECT geography.capital_demote_without_successor (MED-4 fix /review-impl 2026-05-14:
    //      capital-swap via PromoteSettlement is GENUINELY IMPOSSIBLE V1+30d, not "order matters"). The 2-delta
    //      workaround FAILS at the FIRST delta because SET-V9 capital_role_invalid_context rejects assigning
    //      Capital to a settlement when the province ALREADY has a Capital. Both possible orderings deadlock.
    //      Tracked SET-D11 V2+: Forge:SwapStateCapital atomic primitive bypasses both rejects by validating
    //      the pair-of-changes as a single transaction. V1+30d admins who must rewrite state capitals: either
    //      (a) re-issue from canonical_settlements at L2 + reality bootstrap, OR (b) compose POL_001 SplitProvince
    //      + TransferProvinceToState to detach the old capital's cell into a stateless province, freeing the
    //      Capital slot on the parent state. §15.4 documents this V1+30d limitation explicitly.
    // 2. Update wg.settlements[settlement_id]:
    //    - if new_role.is_some(): settlement.role = new_role.unwrap()
    //    - if new_population_tier.is_some(): settlement.population_tier = new_population_tier.unwrap()
    // 3. If new_role == Capital: provinces[settlement.cell.province].capital_settlement_id = Some(settlement_id)
    //    (links the province to its new capital settlement).
    // 4. If old_role was Capital AND new_role is non-Capital: provinces[settlement.cell.province].capital_settlement_id
    //    re-assignment is the admin's responsibility (see step 1's capital_demote_without_successor reject).
}
```

**Validators:** `geography.promote_settlement_no_change` · `geography.capital_role_invalid_context` · `geography.population_tier_out_of_range` · `geography.capital_demote_without_successor`.

### 7.3 RemoveSettlement

```rust
fn apply_remove_settlement(wg: &mut WorldGeometry, payload: &RemoveSettlementPayload) -> () {
    // 1. Validate:
    //    - settlement_id exists
    //    - settlement.role != Capital (cannot remove a state capital; orphans Province.capital_settlement_id.
    //      Use PromoteSettlement + RemoveSettlement combo if intent is "destroy old capital after new one
    //      is established"; UI bundling guidance same as 7.2.)
    //      Reject geography.cannot_remove_capital_settlement.
    //    - settlement.channel_id == None (cannot remove a settlement that has an active town-tier channel —
    //      orphans the channel. V1+30d Settlement.channel_id is always None per SET-D8 deferral; check is
    //      defensive for V1+30d+ when channel_id activation lands.)
    //      Reject geography.cannot_remove_settlement_with_channel.
    // 2. Remove settlement from wg.settlements (Vec retain by id).
    // 3. If settlement was referenced as Province.capital_settlement_id: already prevented by validator above.
    // 4. Settlements + routes that referenced this settlement_id via cell adjacency: NO action needed (settlements
    //    and routes FK by cell_id, not by settlement_id — they survive removal transparently). The removed
    //    settlement's cell is now uninhabited but otherwise unchanged.
}
```

**Validators:** `geography.cannot_remove_capital_settlement` · `geography.cannot_remove_settlement_with_channel`.

---

## §8 Validation pipeline (SET_001 V1+30d additive validators)

Extends GEO_001 §7 + POL_001 §8 + 07_event_model EVT-V* pipeline. New validator slots register in `_boundaries/03_validator_pipeline_slots.md` as sub-validators within `Forge:EditGeographyDelta` ReferentialIntegrityGate step (no new numbered slot needed):

| Validator | Stage | Reject rule_id |
|---|---|---|
| **SET-V1** canonical-settlement-reachable | Stage 6 step B2 | `geography.canonical_settlement_unreachable_v1` (snap to nearest land within radius 0.1 fails) |
| **SET-V2** canonical-settlement-cell-collision | Stage 6 step B2 | `geography.canonical_settlement_cell_collision` (earlier canonical already occupied snap_cell) |
| **SET-V3** procedural-burg-score-min-threshold | Stage 6 step C3 | (informational — no reject; under-fill recorded for ops dashboard if accepted_count < target_count) |
| **SET-V4** settlement-target-uninhabitable | RelocateSettlement delta apply | `geography.settlement_target_uninhabitable` (target cell biome ∈ {Ocean, Lake, Glacier}) |
| **SET-V5** settlement-cell-collision | RelocateSettlement delta apply | `geography.settlement_cell_collision` (target cell already has another settlement; V1+30d one-per-cell invariant) |
| **SET-V6** capital-relocate-outside-capital-province | RelocateSettlement delta apply | `geography.capital_relocate_outside_capital_province` (Capital cannot relocate outside its state's capital_province; compose TransferProvinceToState + PromoteSettlement instead) |
| **SET-V7** settlement-not-found | All 3 V1+30d DeltaKinds | `geography.settlement_not_found` (settlement_id ∉ wg.settlements) |
| **SET-V8** promote-no-change | PromoteSettlement delta apply | `geography.promote_settlement_no_change` (new_role AND new_population_tier both None) |
| **SET-V9** capital-role-invalid-context | PromoteSettlement delta apply | `geography.capital_role_invalid_context` (assigning Capital but cell not in any state's capital_province OR another settlement already holds Capital in same province) |
| **SET-V10** population-tier-out-of-range | PromoteSettlement delta apply | `geography.population_tier_out_of_range` (new_population_tier ∉ [0, 6]) |
| **SET-V11** capital-demote-without-successor | PromoteSettlement delta apply | `geography.capital_demote_without_successor` (old_role==Capital AND new_role==Some(non-Capital) AND this is sole Capital in province — must promote successor first) |
| **SET-V12** cannot-remove-capital-settlement | RemoveSettlement delta apply | `geography.cannot_remove_capital_settlement` (settlement.role == Capital) |
| **SET-V13** cannot-remove-settlement-with-channel | RemoveSettlement delta apply | `geography.cannot_remove_settlement_with_channel` (settlement.channel_id != None; V1+30d defensive, since channel_id activation deferred V1+30d+) |
| **SET-V14** settlement-edit-capability | All 3 V1+30d DeltaKinds — AuthorizationGate | `geography.settlement_edit_capability_required` (capability JWT missing `can_edit_settlement_geography`) |
| **SET-V15** settlement-density-hint-valid | RealityBootstrapper / stage 6 setup | `geography.settlement_density_hint_invalid` (schema-level — closed-enum tampering at JSON deserialization; defensive) |
| **SET-V16** multi-canonical-capital-collision (MED-2 /review-impl) | RealityBootstrapper / stage 6 step B2 | `geography.canonical_capital_collision` (≥2 canonical_settlements with role=Capital declared in same state's capital_province cells — author-corruption defensive at bootstrap; mirrors POL-V20 canonical cross-reference asymmetry check) |
| **SET-V16** canonical-capital-collision (MED-2 fix /review-impl) | Stage 6 STEP B2 + STEP D0/D1 capital assignment | `geography.canonical_capital_collision` (≥2 canonical_settlements declare role=Capital in same state's capital_province at bootstrap — author corruption; resolves SET-Q3 RESOLVE-DEFER as V1+30d active reject) |

ContentSafetyGate (§12X.L7 PII scrub regardless per D-S04-4 GEO_001 fix cycle approval): applied to `delta.reason` + `new_name` if RelocateSettlement gains rename-on-relocate V1+30d+ extension (currently V1+30d RelocateSettlement does NOT rename — only relocates; renaming requires RenameRegion delta separately).

---

## §9 DP primitives + capability

SET_001 V1+30d introduces no new DP primitives. All writes flow through GEO_001's existing path:

- `dp.t2_write::<WorldGeometry>(channel_id, ...)` — extends existing GEO_001 + POL_001 T2 write
- `dp.subscribe_channel_events_durable::<WorldGeometryEvent>(channel_id, ...)` — consumed by MAP_001 V1+ (settlement centroid → map_layout.position auto-derivation per GEO-D5)

Capability addition (extends `_boundaries/02_extension_contracts.md` §3 capability JWT):

- `can_edit_settlement_geography: bool` (claim) — required by EVT-T8 AuthorizationGate for the 3 V1+30d DeltaKinds (RelocateSettlement / PromoteSettlement / RemoveSettlement)
- **Tier discipline per S5** (mirrors POL_001 but with mixed tiers — settlements smaller-scale than provinces+states):
  - `RemoveSettlement`: **Tier 1 ImpactClass=Destructive** (deletion is irrecoverable; double-approval per ADMIN_ACTION_POLICY; matches RemoveRoute V1 + 4 POL V1+30d precedent)
  - `RelocateSettlement`: **Tier 2 ImpactClass=Griefing** (reversible — admin can relocate back; single-approval acceptable)
  - `PromoteSettlement`: **Tier 2 ImpactClass=Griefing** (reversible — admin can demote back; single-approval acceptable)
  - `AddNamedSettlement` (existing V1): **Tier 2 ImpactClass=Griefing** per GEO_001 §7 (unchanged)
- **Capability migration plan at SET ship** (mirrors POL_001 MED-6 precedent): auth-service runs a one-shot migration that auto-grants `can_edit_settlement_geography` to all currently-active `can_edit_geography` holders. **LOW-1 clarification /review-impl**: `AddNamedSettlement` (existing V1 GEO_001) stays under `can_edit_geography` unchanged (NOT migrated to require the new claim) — this preserves V1 admin workflow compatibility. The 3 NEW V1+30d DeltaKinds (Relocate/Promote/Remove) carve under `can_edit_settlement_geography`. `can_edit_geography` post-SET-ship continues to authorize: SetBiomeOverride / AddRoute / RemoveRoute / RenameRegion / AddNamedSettlement. Per PLT_001 §6.3 `forge.roles_version` bumps as part of the migration (auditable). Post-migration, future Forge admins receive all three claims (`can_edit_geography` + `can_edit_political_geography` + `can_edit_settlement_geography`) as a paired bundle at role-grant time (PLT_001 RBAC config V1+30d adds the bundling). No existing admin loses access at ship. Cohort-style rollout: staging realities migrate first; production realities migrate after 24h soak; failed migrations fall back to "neither claim active" (admin re-issuance required, surfaces UI banner).

Subscribe path: SET_001 V1+30d emissions appear as `EVT-T3 Derived aggregate_type=world_geometry` events; existing GEO_001 + POL_001 subscribers automatically receive SET field updates (settlement changes), no new subscribe contract needed.

---

## §10 Composition with foundation siblings

SET_001 V1+30d composes within GEO_001's existing composition contracts; **POL_001 stage 5 → SET_001 stage 6 → POL_001 stage 8** order is the new V1+30d coordination point:

| Sibling | Composition with SET_001 |
|---|---|
| **GEO_001** | Schema parent; SET_001 V1+30d populates GEO_001 §3.1 `world_geometry.settlements` Vec. No GEO_001 schema change. |
| **GEO_001b** | LLM authoring contract; SET_001 V1+30d additive within CreativeSeed v4 schema (settlement_seed_mode + settlement_density_hint). LLM authoring template v2.tmpl → v3.tmpl. |
| **GEO_002 POL_001** | Sibling V1+30d feature; **coordination point**: SET_001 stage 6 runs AFTER POL_001 stage 5 (state.capital_province available); BEFORE POL_001 stage 8 (culture spread doesn't reference settlements V1+30d, so order is independent). SET_001 populates `Province.capital_settlement_id` per state's capital_province (closes POL_001's V1+30d-standalone None field). SET_001 step D1 reads `state.capital_province.member_cells` to assign Capital role to the lowest-GeoCellId settlement in that province. POL_001's apply_delta for SplitProvince + TransferProvinceToState may invalidate Province.capital_settlement_id linkage (admin pattern: emit SplitProvince first, then re-assign via PromoteSettlement to new Capital + RelocateSettlement of old Capital). |
| **MAP_001** | V1+30d SET_001 stage 6 outputs (settlement cell centroid coordinates) feed MAP_001 V1+30d position auto-derivation per GEO-D5: `map_layout.position` for town-tier channels derives from Settlement.cell_id → cells[cell].center. Currently MAP_001 V1+30d position derivation row tracks GEO-D5 (settlement-based); SET_001 ship is the ACTIVATION moment for that row. MAP_001 light reopen at LOCK should note "ACTIVATED" status on GEO-D5 row. |
| **PF_001** | V1+30d PF-D7 procedural place generation gains `SettlementRole + population_tier` context for PlaceType selection (Capital settlement + Han-Jiangnan culture → palace + temple + market PlaceTypes; Hamlet + Forest biome → single-cottage PlaceType). No PF_001 schema change. |
| **CSC_001** | V1+30d settlement cells get richer skeleton selection: Capital → palace_complex skeleton; Fortress → fortified_keep skeleton; port City → harbor skeleton; Town → market_square skeleton; etc. (extends CSC_001 V1+30d biome-driven skeleton catalog with role-driven variants). |
| **EF_001** | No direct composition. Settlements live in cells; entities live in cells; entity_binding doesn't traverse settlement graph. |
| **RES_001** | V2+ GEO-D10 resource generator + SET_001 settlements compose: per-settlement population_tier modulates resource production rates (City × Plain biome → larger grain production than Hamlet × Plain biome). Tracked V2+ via RES-D19 NPCAutoCollect lazy migration consuming Settlement.population_tier. V1+30d schema only (no consumption). |
| **PROG_001** | No direct composition V1+30d. V2+ cultivation-realm settlements (e.g., Wuxia "Sect Headquarters" at Fortress role with Highland biome) may carry per-cell cultivation modifiers. |
| **TIT_001** | V1+30d: TIT_001 titles like "Lord of \[Settlement\]" CAN reference Settlement.name once SET ships. No V1+30d schema integration; cross-ref documentation only. V2+ TIT_001 settlement-binding via TitleBinding::Standalone surfaces. |
| **TVL_001 V1+** | Future consumer. Reads Settlement.cell_id + role + population_tier for travel-speed modifiers (City-to-City road faster than Hamlet-to-Hamlet trail). |
| **GEO_004 ROUTE_001 V1+30d** | Future sibling V1+30d. ROUTE_001 stage 7 runs AFTER SET_001 stage 6 (Dijkstra source/sink pairs are settlement positions). SET ships first; ROUTE ships second. |
| **STRAT_001 V2+** | Primary read-only consumer. Reads Settlement graph for army-position-on-settlement + siege-target + supply-line endpoint modeling. STRAT_001 spec lands V2+. |

---

## §11 RealityManifest extension

**No new RealityManifest field.** SET_001 V1+30d extends `creative_seed` (per §6) which is already inside `RealityManifest.continent_geometries[i].creative_seed` per GEO_001 §11. The CreativeSeed v4 schema absorbs SET_001 fields additively per R3.

Bootstrap order extends GEO_001 §11 + POL_001 §11:
1. DP create_channel (continent + cells)
2. RealityBootstrapper EVT-T4 GeographyBorn per continent
3. world-service materializes WorldGeometry — V1+30d runs stages 1-4 (GEO_001) + stage 5 (POL_001 political growth) + **stage 6 (SET_001 settlement placement — this commit)** + stage 8 (POL_001 culture spread)
4. Apply initial `geography_deltas` (per CreativeSeed declaration; canonical states + provinces + settlements resolved)
5. Persist as T2/Channel-continent aggregate (now includes populated provinces + states + settlements + culture_regions; Province.capital_settlement_id linked)

V1+30d feature-flag: `services/world-service` config `settlement_layer_generator_enabled: bool` (default true V1+30d; false V1 backward-compat for realities bootstrapping pre-SET-ship — settlements stay empty/canonical-only V1 behavior). Mid-life feature-flag flip on an existing reality: **FORBIDDEN** — per GEO_001 §3 `generator_pipeline_version` discipline. Flag affects only new realities at bootstrap.

---

## §12 Failure UX — extends `geography.*` namespace

SET_001 V1+30d adds **15 V1+30d rule_ids** under the existing `geography.*` namespace owned by GEO_001 (per SET-D7 — share namespace mirroring POL-D7 precedent, no new prefix carving; /review-impl 2026-05-14 added MED-2 `canonical_capital_collision`). Total `geography.*` after SET_001 V1+30d ships: 48 V1+30d (13 V1 GEO_001 + 20 V1+30d POL_001 + 15 V1+30d SET_001).

Also LIFTS V1's `geography.layer_activation_deferred_v1` reject for the settlement layer specifically (V1+30d-gated): when `services/world-service` runs at SET_001 V1+30d ship time, settlement runtime writes via stage-6 / 3-new-DeltaKind paths NO LONGER reject this rule_id. Other layer-activation paths (route V1+30d ROUTE_001 / resource V2+) keep the reject until their generator ships.

| Rule ID | Severity | Where raised | Vietnamese user copy (V1+30d) | English fallback |
|---|---|---|---|---|
| `geography.canonical_settlement_unreachable_v1` | user | Stage 6 step B2 | "Không tìm thấy ô đất trong bán kính cho phép quanh thị trấn canonical đã khai báo." | "No land cell within radius around declared canonical settlement." |
| `geography.canonical_settlement_cell_collision` | user | Stage 6 step B2 | "Ô đã có thị trấn canonical khác chiếm trước." | "Cell already occupied by an earlier canonical settlement." |
| `geography.settlement_target_uninhabitable` | user | RelocateSettlement delta | "Ô đích không thể có thị trấn (đại dương / hồ / băng)." | "Target cell is uninhabitable (Ocean / Lake / Glacier)." |
| `geography.settlement_cell_collision` | user | RelocateSettlement delta | "Ô đích đã có một thị trấn khác." | "Target cell already has another settlement (V1+30d one-per-cell invariant)." |
| `geography.capital_relocate_outside_capital_province` | user | RelocateSettlement delta | "Thủ đô không thể chuyển ra ngoài tỉnh thủ đô. Hãy chuyển tỉnh trước." | "Capital cannot relocate outside its state's capital province." |
| `geography.settlement_not_found` | schema | All 3 V1+30d DeltaKinds | "Không tìm thấy thị trấn được nêu." | "Settlement not found." |
| `geography.promote_settlement_no_change` | user | PromoteSettlement delta | "Phải thay đổi ít nhất một thuộc tính (vai trò hoặc dân số)." | "PromoteSettlement requires at least one change (role or population_tier)." |
| `geography.capital_role_invalid_context` | user | PromoteSettlement delta | "Không thể gán vai trò Thủ đô — ô không thuộc tỉnh thủ đô của quốc gia, hoặc tỉnh đã có thủ đô khác." | "Cannot assign Capital role — cell not in state's capital_province OR another Capital already exists." |
| `geography.population_tier_out_of_range` | user | PromoteSettlement delta | "Cấp độ dân số phải nằm trong khoảng 0-6." | "Population tier must be in range 0-6." |
| `geography.capital_demote_without_successor` | user | PromoteSettlement delta | "Phải bổ nhiệm thủ đô mới trước khi giáng cấp thủ đô hiện tại." | "Must designate successor Capital before demoting current Capital." |
| `geography.cannot_remove_capital_settlement` | user | RemoveSettlement delta | "Không thể xóa thị trấn đang là thủ đô quốc gia. Hãy bổ nhiệm thủ đô mới trước." | "Cannot remove a state capital settlement. Promote a successor first." |
| `geography.cannot_remove_settlement_with_channel` | user | RemoveSettlement delta | "Không thể xóa thị trấn đang có kênh hoạt động." | "Cannot remove a settlement with an active town-tier channel." |
| `geography.settlement_edit_capability_required` | user | All 3 V1+30d DeltaKinds AuthorizationGate | "Bạn không có quyền chỉnh sửa thị trấn." | "Missing settlement geography edit capability." |
| `geography.settlement_density_hint_invalid` | schema | RealityBootstrapper / stage 6 setup | "Cấu hình mật độ thị trấn không hợp lệ." | "Settlement density hint invalid (closed-enum tampering at deserialization)." |
| **`geography.canonical_capital_collision`** *(MED-2)* | schema | RealityBootstrapper / stage 6 setup | "Đã khai báo nhiều hơn một thủ đô canonical trong cùng tỉnh thủ đô của quốc gia." | "Multiple canonical settlements declared with role=Capital in same state's capital province." |

V1+30d schema-level rejects (4): settlement_not_found / settlement_density_hint_invalid / canonical_capital_collision (MED-2 /review-impl) / (informational under-fill metric).
V1+30d user-facing rejects (11): the rest.

V2+ reservations (NEW): `geography.settlement_narrative_proposal_pending` (V2+ T6 NarrativeSettlementEdit Generator review per SET-D7); `geography.multi_settlement_per_cell_pending` (V2+ relaxation of one-per-cell invariant per SET-D9).

---

## §13 Cross-service handoff

| Service | Role | V1+30d status |
|---|---|---|
| **world-service** | Authoritative owner — runs stage 6 at bootstrap; applies the 3 V1+30d DeltaKinds; persists aggregate | V1+30d |
| **glossary-service** | Stores CanonicalSettlementDecl names + canon_ref backlinks (same pattern as canonical_provinces V1+30d POL + canonical_states V1+30d POL) | V1+30d |
| **chat-service** (S9 prompt-assembly) | Read-only consumer — `[GEOGRAPHIC_CONTEXT]` joins nearest_settlement_name + settlement_role per cell (closes POL_001's V1+30d-already-spec'd slot which had no Settlement data until SET ships) | V1+30d |
| **api-gateway-bff** | Routes Forge UI POSTs for 3 new V1+30d DeltaKinds → world-service; player map UI GETs read populated settlements for settlement-marker rendering | V1+30d Forge UI |
| **knowledge-service** | Reads Settlement graph for entity-place enrichment (planned V1+ knowledge-service activation per CLAUDE.md two-layer pattern; e.g., "Khai Phong" entity gains settlement metadata) | Not V1+30d |
| **STRAT_001 service V2+** | Future consumer for army-position-on-settlement + siege-target modeling (separate service in V2+; consumes SET_001 V1+30d-locked schema as read-only) | V2+ |
| **future GEO_004 ROUTE_001 V1+30d** | Consumes Settlement graph as Dijkstra source/sink pairs for route network generation | V1+30d (SET ships first; ROUTE ships second) |

No new service introduced. All V1+30d implementation fits inside `world-service` extension + read-only consumers.

---

## §14 Multiverse inheritance

SET_001 V1+30d inherits GEO_001 §9 + POL_001 §14 fork-inheritance contract unchanged. Snapshot fork at event E:

- Parent's settlement_layer (settlements + Province.capital_settlement_id populated via stage 6 at parent bootstrap) copied bit-exactly into child.
- Parent's V1+30d SET DeltaKinds applied up to fork-point copied as part of `geography_deltas[..fork_point]` (alongside POL DeltaKinds and V1 GEO_001 DeltaKinds — all share the same ordered delta_log per continent).
- Child appends new V1+30d SET DeltaKinds locally; parent's post-fork DeltaKinds do NOT cascade.
- L1/L2 cascade: if author edits `creative_seed.canonical_settlements[i]` at L2, both parent and child see new value UNLESS child has L3-scoped DeltaKind override (RelocateSettlement / PromoteSettlement / RemoveSettlement) on the same settlement.

Determinism preserved: same `(settlement_seed, creative_seed_snapshot, generator_pipeline_version, POL stage 5 outputs, fork_point_delta_count)` → bit-identical settlements + Province.capital_settlement_id linkages across parent and child at fork point.

---

## §15 Sequences

### 15.1 Hybrid bootstrap — Yên Vũ Lâu wuxia setting (SET_001 V1+30d active alongside POL_001)

```
RealityManifest.continent_geometries[0].creative_seed = {
  archetype: Wuxia, world_scale: Region (~2048 cells), hemisphere: Northern, coastline: Coastal,
  political_seed_mode: Hybrid, canonical_states: [Tống, Liêu], canonical_provinces: [Lương Châu, Yên Vân, ...6 entries],
  settlement_seed_mode: Hybrid, settlement_density_hint: Medium,                                          // SET_001 V1+30d
  canonical_settlements: [
    { name: "Tương Dương", position_normalized: (0.40, 0.50), role: Capital, population_tier: 5, canon_ref: ... },
    { name: "Khai Phong", position_normalized: (0.50, 0.30), role: City, population_tier: 5, canon_ref: ... },
    { name: "Yên Vũ Lâu", position_normalized: (0.45, 0.55), role: Town, population_tier: 3, canon_ref: ... },
    // 7 more canonical settlements declared
  ],
  culture_hints: [han_jiangnan@(0.30,0.40), qidan@(0.75,0.15)],
  ...
}
  ↓ Stages 1-4 run (GEO_001 V1; ~50ms; biome/climate/heightmap/river populated; cells = 2048)
  ↓ Stage 5 (POL_001 V1+30d): provinces=10, states=3 (Tống / Liêu / Tây Cương_State_a3f9c2), stateless_provinces=1.
  ↓ Stage 6 (SET_001 V1+30d): STEP A burg_score precomputation; max_burg_score = 1.95 (some Plain + Coast + Temperate cell).
    STEP B canonical placement: 10 canonical_settlements placed; "Tương Dương" snaps to cell 832 (was originally
    at (0.40, 0.50); cell center 0.402, 0.498 within radius — accepted). 9 more placed similarly.
    STEP C procedural placement: target = 2048 / 400 = ~5 total; 10 canonical already exceed → procedural skipped.
    (NOTE: Medium-density on small world → canonical fully satisfies; this is a corner case. Dense or larger world
    would procedurally fill.)
    STEP D role assignment:
      - "Tương Dương" canonical decl.role=Capital, declared in Lương Châu province; matches Tống's capital_province
        → settlement.role stays Capital (canonical override per D3). provinces[Lương Châu].capital_settlement_id =
        Some(tuong_duong_id).
      - "Khai Phong" canonical decl.role=City; canonical override → role stays City. (Khai Phong is not declared
        as canonical Tống capital — author chose Tương Dương as the actual capital per Thần Điêu canon.)
      - "Yên Vũ Lâu" canonical decl.role=Town; stays Town.
      - Other 7 canonical settlements keep their decl roles.
    STEP E population_tier: all canonical, decl.population_tier used; no procedural derivation needed.
    Cost: ~8ms wall-clock (small world; little procedural work).
  ↓ Stage 8 (POL_001 V1+30d culture spread): unchanged from prior; ~40ms.
  ↓ state.culture_tag derived: Tống → han_jiangnan; Liêu → qidan; Tây Cương_State_a3f9c2 → han_jiangnan.
  ↓ WorldGeometry persisted: provinces=10, states=3, settlements=10, culture_regions=2.
    Province[Lương Châu].capital_settlement_id = Some(tuong_duong_id). Other state-capital provinces similarly linked
    (Liêu.capital_province.capital_settlement_id = Some(yen_van_capital_canonical_id_if_declared else None).
    Tây Cương_State_a3f9c2.capital_province.capital_settlement_id: if no canonical Capital was declared for the
    procedural state's capital province AND no procedural settlement was placed there (Medium-density small world)
    → step D1 forced-procedural-placement fires; emits a synthetic Settlement at capital_province centroid with
    role=Capital + population_tier=2 (low; reflects "small wilderness state capital").
  ↓ Prompt-assembly for cell:yen_vu_lau joins biomes[id]=Plain + climate=Subtropical +
    province_name="Lương Châu" + state_name="Tống triều" + culture_tag="han_jiangnan" +
    nearest_settlement_name="Yên Vũ Lâu" + settlement_role="Town" →
    [GEOGRAPHIC_CONTEXT] = "thị trấn Yên Vũ Lâu (Town), văn hóa Hán-Giang Nam, tỉnh Lương Châu (Tống triều),
                          đồng bằng cận nhiệt đới"
    LLM grounded with concrete settlement name + role — closes the LLM-context gap GEO_001 §1 Gap 2 named.
```

### 15.2 Forge RelocateSettlement — village rebuilt after flood

```
Forge:EditGeographyDelta { delta_kind: RelocateSettlement {
    settlement_id: tieu_thon_village_id,                       // small village in Lương Châu province
    new_cell_id: cell_854,                                     // 3 cells downstream along river_flux gradient
    reason: "Lụt sông Trường Giang phá hủy bản cũ; tái lập tại bờ trên...50+ char" },
    prev_delta_id: <last>, ... }
  ↓ EVT-T8 validator pipeline (SET_001 V1+30d):
    AuthorizationGate (has can_edit_settlement_geography claim) → SchemaGate → ReferentialIntegrityGate
    (SET-V4 new_cell biome = Plain ≠ Ocean/Lake/Glacier → pass;
     SET-V5 no other settlement at cell_854 → pass;
     SET-V6 settlement.role == Town ≠ Capital → SET-V6 trivially passes;
     SET-V7 settlement_id exists → pass)
    → OrderingGate → ContentSafetyGate (reason scrubbed per D-S04-4) → all pass.
  ↓ EVT-T3 Derived: apply_relocate_settlement(wg, payload):
    - wg.settlements[tieu_thon_village_id].cell_id = cell_854 (was cell_847; updated)
    - Province.capital_settlement_id linkage UNCHANGED (settlement was a Town, not Capital)
    - geography_deltas.push(delta_entry)
  ↓ Subsequent prompt-assembly for cells near cell_854 now shows nearest_settlement="Tiểu Thôn"; cells near
    old cell_847 fall back to next-nearest settlement (deterministic lookup by cell-to-settlement Euclidean distance).
  ↓ MAP_001 V1+ visual layer: town-tier channel "tiểu_thôn" map_layout.position updates to cell_854.center
    (auto-derivation per GEO-D5 V1+ activation activated at SET ship).
```

### 15.3 Forge PromoteSettlement — Hamlet grows to Town after canon event

```
Forge:EditGeographyDelta { delta_kind: PromoteSettlement {
    settlement_id: small_hamlet_id,
    new_role: Some(Town), new_population_tier: Some(3),
    reason: "Hoàng đế ban chiếu xây chợ; bản trở thành thị trấn...50+ char" },
    prev_delta_id: <last>, ... }
  ↓ EVT-T8 validator pipeline:
    AuthorizationGate (can_edit_settlement_geography) → ReferentialIntegrityGate
    (SET-V7 settlement_id exists → pass;
     SET-V8 at-least-one-Some (both Some) → pass;
     SET-V9 new_role != Capital → SET-V9 trivially passes;
     SET-V10 population_tier 3 ∈ [0, 6] → pass;
     SET-V11 old_role != Capital → SET-V11 trivially passes)
    → all pass.
  ↓ apply_promote_settlement(wg, payload):
    - wg.settlements[small_hamlet_id].role = Town (was Hamlet)
    - wg.settlements[small_hamlet_id].population_tier = 3 (was 0)
    - geography_deltas.push(delta_entry)
  ↓ PF_001 V1+30d procedural place generation per PF-D7 (if activated): re-runs PlaceType selection for the cell
    now that role=Town instead of Hamlet (more PlaceTypes available — market, inn, etc.). Cells previously
    unselected for this settlement now eligible for richer Place catalog.
```

### 15.4 Forge RemoveSettlement — village extinct after plague (capital-protection reject)

```
Forge:EditGeographyDelta { delta_kind: RemoveSettlement {
    settlement_id: tuong_duong_capital_id,                     // Tống's Capital settlement (Tương Dương)
    reason: "Đại dịch xóa sổ thành phố...50+ char" },
    prev_delta_id: <last>, ... }
  ↓ EVT-T8 validator pipeline:
    AuthorizationGate (can_edit_settlement_geography) → ReferentialIntegrityGate
    (SET-V7 settlement exists → pass;
     SET-V12 settlement.role == Capital → REJECT geography.cannot_remove_capital_settlement)
  ↓ Reject surfaces UI: "Không thể xóa thị trấn đang là thủ đô quốc gia. Hãy bổ nhiệm thủ đô mới trước."
  ↓ Admin retries with 2-delta sequence:
    1. PromoteSettlement { settlement_id: khai_phong_id, new_role: Some(Capital), new_population_tier: None,
                          reason: "Tống triều dời đô tới Khai Phong sau đại dịch...50+ char" }
       Validators: SET-V9 capital_role_invalid_context check — Khai Phong's cell IS in Tống's capital_province
       (Lương Châu); Lương Châu.capital_settlement_id == Some(tuong_duong_id) NOT None → SET-V9 REJECTS
       `geography.capital_role_invalid_context` because province already has a Capital.
  ↓ Admin retries with the correct sequence:
    1. SplitProvince Lương Châu into [Lương Châu Bắc heir-state=Tống, Lương Châu Nam state=None];
       Tương Dương stays in Lương Châu Bắc → still Tống's capital province → still Capital. (No actual change to
       capital linkage; this delta just reshapes the province.)
    2. TransferProvinceToState: actually no — this also won't help; the canon-event of "moving capital" needs a
       different primitive. V1+30d the CORRECT admin pattern for "destroy capital" is:
       (a) Author updates creative_seed.canonical_settlements at L2 (canon-layer); next reality bootstrap reflects
           the change.
       (b) For runtime-only (no canon rewrite): SplitProvince Tống's capital_province to isolate the dying-capital
           settlement into a new province; TransferProvinceToState the dying-capital province to state_id=None
           (now Tương Dương is stateless, not a Capital — its role auto-demotes to whatever PromoteSettlement is
           emitted next OR stays Capital as orphaned-stateless until admin promotes a new one in the
           still-canonical-Tống capital province).
       This V1+30d cycle is awkward. POL-D14 (V2+ CreateState/DestroyState DeltaKinds) + a future
       SET-D11 (V2+ SwapStateCapital DeltaKind that atomically PromoteSettlement-new + DemoteSettlement-old)
       would close this UX gap.
```

This sequence demonstrates that **the V1+30d admin tooling is asymmetric for "destroy state capital" scenarios** — intentional, since runtime canon rewrites of state capitals are rare + risky. Track as SET-D11 V2+ deferral.

---

## §16 Acceptance criteria

19 V1+30d-testable acceptance scenarios (15 original + 4 /review-impl coverage AC-SET-16..19 for MED-2 + HIGH-2 + HIGH-4 + MED-4). LOCK granted when ≥13 pass integration tests against SET reference module in `world-service` (extension of GEO_001 + POL_001 `geography-generator`).

| ID | Scenario | Reject rule_id (if applicable) |
|---|---|---|
| **AC-SET-1** | Bootstrap continent with `world_scale=Continent (~8192 cells)`, `settlement_seed_mode=Hybrid`, `settlement_density_hint=Medium` (~20 cells/settlement target), 10 canonical_settlements + POL_001 V1+30d stage 5 outputs available (3 states with capital_province assignments) → settlements.len() == 20 (10 canonical + 10 procedural; LOW-4/5 fix /review-impl: count pinned via world_scale spec), every state's capital_province has Some(capital_settlement_id) linked, Settlement.role and population_tier populated per hybrid algorithm. | — |
| **AC-SET-2** | Bootstrap with same `(settlement_seed, creative_seed, pipeline_version, POL stage 5 outputs)` → byte-identical settlements + Province.capital_settlement_id linkages (replay determinism per EVT-A9; CI gate inherits canonical-JSON discipline from SPIKE_04). | — |
| **AC-SET-3** | Bootstrap with `settlement_seed_mode=Canonical`, 5 canonical_settlements → settlements.len() == 5 (no procedural fill); states whose capital_province has no canonical settlement get None capital_settlement_id (V1+30d acceptable per Canonical-mode strict author-ownership). | — |
| **AC-SET-4** | Bootstrap with `settlement_seed_mode=Procedural`, canonical_settlements declared but ignored → settlements.len() = target_count per density, Capital role assigned by political-first algorithm to lowest-GeoCellId settlement in each state.capital_province (canonical names unused). | — |
| **AC-SET-5** | Bootstrap with canonical_settlement at water cell (no land within radius 0.1) → reject. | `geography.canonical_settlement_unreachable_v1` |
| **AC-SET-6** | Bootstrap with 2 canonical_settlements both snapping to same cell → reject on the second. | `geography.canonical_settlement_cell_collision` |
| **AC-SET-7** | Forge admin emits RelocateSettlement with target cell = Ocean → reject. | `geography.settlement_target_uninhabitable` |
| **AC-SET-8** | Forge admin emits RelocateSettlement with target cell already occupied by another settlement → reject. | `geography.settlement_cell_collision` |
| **AC-SET-9** | Forge admin emits RelocateSettlement on a Capital settlement to a cell OUTSIDE its state's capital_province → reject. | `geography.capital_relocate_outside_capital_province` |
| **AC-SET-10** | Forge admin emits PromoteSettlement with both new_role and new_population_tier None → reject. | `geography.promote_settlement_no_change` |
| **AC-SET-11** | Forge admin emits PromoteSettlement to assign Capital role on a settlement whose cell is NOT in any state's capital_province → reject. | `geography.capital_role_invalid_context` |
| **AC-SET-12** | Forge admin emits PromoteSettlement to assign Capital role on a settlement in state's capital_province but province already has another Capital → reject. | `geography.capital_role_invalid_context` |
| **AC-SET-13** | Forge admin emits PromoteSettlement with new_population_tier = 7 → reject. | `geography.population_tier_out_of_range` |
| **AC-SET-14** | Forge admin emits RemoveSettlement on a settlement currently marked Capital → reject. | `geography.cannot_remove_capital_settlement` |
| **AC-SET-15** | Forge admin holds `can_edit_geography` but NOT `can_edit_settlement_geography` → emits RelocateSettlement → reject at AuthorizationGate. | `geography.settlement_edit_capability_required` |
| **AC-SET-16** *(MED-2 coverage)* | RealityBootstrapper with 2 canonical_settlements declaring `role=Capital` in same state's capital_province (e.g., both in Tống's Lương Châu) → reject at stage 6 STEP B/D capital assignment. | `geography.canonical_capital_collision` |
| **AC-SET-17** *(HIGH-2 coverage)* | Bootstrap with canonical_settlement declaring `role=Town` at the lowest-GeoCellId cell in state's capital_province (no canonical_settlement declares Capital there) → settlement keeps Town role (canonical takes priority per STEP D0); STEP D1 picks the NEXT non-canonical-pinned settlement in the province (next-lowest GeoCellId among procedural settlements) for Capital. | — |
| **AC-SET-18** *(HIGH-4 coverage — mountain pass)* | Bootstrap with a continent containing a saddle-point cell (heightmap=20000, two opposing neighbors heightmap=55000 each) → SET stage 6 STEP D2 places a Fortress at the saddle cell (correctly identifying it as a pass, not a cliff). | — |
| **AC-SET-19** *(MED-4 coverage)* | Forge admin emits 2-delta sequence attempting capital-swap: first PromoteSettlement(new_capital_candidate, role=Capital) → reject SET-V9 (province already has Capital); admin cannot proceed. Documents V1+30d hard-block per SET-D11 V2+ deferral. | `geography.capital_role_invalid_context` |

---

## §17 Deferrals

| ID | Item | Tier | Notes |
|---|---|---|---|
| **SET-D1** | Sub-cell settlement interior layout (wards, walls, market squares) | V2+ | Owned by CSC_001's V2+ settlement-interior skeleton extension; SET_001 V1+30d stays at settlement-graph scope only. |
| **SET-D2** | V2+ T6 LLM settlement-evolution proposal (NarrativeSettlementEdit Generator) | V2+ | Parallel to POL-D2 + GEO-D12; LLM proposes Promote/Relocate/Remove based on economic + narrative events. Forge admin reviews + materializes via T8. |
| **SET-D3** | Burg_score component-weight tuning per author / per archetype | V1+30d+ | Currently fixed coefficients V1+30d. Wuxia worlds may want different weights than HighFantasy (e.g., spirit-vein cells get +bonus). Defer until author UX surfaces complaints. |
| **SET-D4** | Settlement-to-settlement adjacency derived from cell-neighbors graph (for travel/trade modeling) | V1+30d+ | Useful for TVL_001 V1+ + DIPL_001 V2+; not V1+30d-blocking (consumers derive at read time). |
| **SET-D5** | Settlement-to-population derived production rates (City × Plain → grain rate) | V2+ | Coupled with RES_001 V2+ NPCAutoCollect lazy migration RES-D19; SET_001 V1+30d schema only. |
| **SET-D6** | Multi-Capital states (state with 2+ capital provinces; e.g., dual-capital empires) | V2+ | Currently strict 1-Capital-per-state per POL_001 §3.1 State.capital_province_id field shape. Multi-capital requires POL_001 schema change V2+ + SET_001 alignment. |
| **SET-D7** | V2+ T6 NarrativeSettlementEdit reservation namespace | V2+ | Reserves `geography.settlement_narrative_proposal_pending` for V2+ Generator activation. |
| **SET-D8** | Settlement.channel_id V1+30d+ activation — town-tier channel materialization per Settlement | V1+30d+ | GEO_001 §3.1 declares Settlement.channel_id: Option<ChannelId>; V1+30d SET ships with None for all settlements. V1+30d+ when DP-Ch town-tier channels are created per City+Capital settlement (population_tier ≥ 3 threshold candidate). Coordinates with CSC_001 V1+30d+ cell-tier channels. |
| **SET-D9** | Multi-settlement-per-cell relaxation (urban-cluster modeling — large cities span multiple cells) | V2+ | V1+30d strict one-per-cell. V2+ if strategy gameplay or visual map needs urban-cluster footprint (e.g., Beijing-scale cities spanning 5-10 cells). |
| **SET-D10** | Forge:BundleDeltas transactional admin primitive (atomic multi-DeltaKind apply for capital-swap-style sequences) | V2+ | Current §15.4 sequence demonstrates V1+30d admin asymmetry for "destroy state capital" — requires multi-delta sequencing with intermediate invalid states. V2+ adds Forge:BundleDeltas that atomically applies a Vec<GeographyDeltaKind> with all-or-nothing validator transaction. Closes UX gap. |
| **SET-D11** | Forge:SwapStateCapital convenience DeltaKind (atomic PromoteSettlement-new-Capital + PromoteSettlement-old-Capital-demote) | V2+ | Higher-level admin primitive that wraps the 2-delta sequence; same effect as SET-D10 Forge:BundleDeltas but with role-specific safety checks (atomic capital transition). |
| **SET-D12** | Per-archetype role-distribution profile (e.g., Wuxia: more Town + Fortress; Cyberpunk: more City + Capital) | V1+30d+ | Currently uniform algorithm. Defer until creative_seed.archetype-driven role-weighting surfaces. |
| **SET-D13** | V2+ culture-aware procedural settlement naming via `creative_seed.naming_styles[cell.dominant_culture_tag]` Markov chain | V2+ | Deferred per HIGH-1 fix (/review-impl 2026-05-14) to sever stage-6/stage-8 cycle for settlement naming: stage 6 produces settlements; stage 8 produces culture_regions + cell.culture_tag. V1+30d uses culture-agnostic synthesis `format!("{}_{:06x}", biomes[cell_id].as_str(), settlement_id_short_hex)`; V2+ adds a post-stage-8 sub-pass that renames procedural settlements using the now-derived cell.culture_tag. Mirrors POL-D13 V2+ deferral pattern for procedural state naming. |
| **SET-D13** | Culture-aware procedural settlement naming (use `creative_seed.naming_styles[cell.dominant_culture_tag]` Markov chain to name procedural settlements) | V2+ | Currently deferred per HIGH-1 fix (/review-impl 2026-05-14) to sever stage-6/stage-8 ordering dependency: stage 6 procedural naming consuming stage-8 culture_tag is impossible since stage 8 runs AFTER stage 6 in the pipeline. V1+30d uses culture-agnostic naming (`{biome.as_str}_{6-hex-of-settlement-id}`); V2+ adds a post-stage-8 sub-pass that renames procedural settlements using the now-derived cell.culture_tag. Mirrors POL-D13 stage-cycle-deferral discipline. |

---

## §18 Open questions

| ID | Question | Resolution path |
|---|---|---|
| **SET-Q1** | Burg_score coefficients (population_potential, water_proximity, climate_friendliness) — V1+30d defaults vs. tuning? | V1+30d: lock fixed coefficients per §4.4; tuning slot deferred SET-D3. |
| **SET-Q2** | Capital role assignment when state's capital_province has 0 settlements after stage 6 step C: should SET-step-D1 emit a "forced procedural placement" (current spec) OR leave province.capital_settlement_id = None? | V1+30d: forced procedural placement at capital_province centroid (per §5.1 STEP D1 defensive note). Ensures Province.capital_settlement_id is always Some(_) for state-capital provinces. V1+30d+ revisit if author UX surfaces complaints (e.g., "I wanted my wilderness state to have no capital settlement"). |
| **SET-Q3** | When multiple canonical_settlements declared in same state.capital_province (e.g., author declares 3 cities in Tống's capital province), which gets Capital role? | V1+30d: the canonical with `role=Capital` declared explicitly. If multiple declared Capital → reject `geography.canonical_capital_collision` (defensive; not in §12 V1+30d but track SET-Q3-RESOLVE-DEFER for V1+30d implementation phase). If zero declared Capital → SET-step-D1 fallback to lowest-GeoCellId among canonical in that province. |
| **SET-Q4** | ~~Procedural naming style derivation~~ — **RESOLVED via HIGH-1 fix /review-impl 2026-05-14** | V1+30d uses culture-agnostic naming `format!("{}_{:06x}", biomes[cell_id].as_str(), settlement_id_short_hex)` per §5.1 STEP C4 (resolution option c — synthetic deterministic naming, no stage-cycle dependency). V2+ culture-aware Markov-chain naming via `creative_seed.naming_styles[cell.dominant_culture_tag]` tracked as new SET-D13 deferral. |
| **SET-Q5** | Storage representation: monolithic Vec<Settlement> (matches POL_001's Vec<Province> + Vec<State> pattern) OR per-settlement SQL table for spatial queries? | V1+30d: monolithic (~50KB / continent fine; matches GEO_001 + POL_001 pattern). V2+ STRAT_001 may force denormalization for settlement-graph SQL; revisit then. |

---

## §19 Cross-references

- [`cat_00_GEO_geography_foundation.md`](../../catalog/cat_00_GEO_geography_foundation.md) — catalog extended with SET-* sub-prefix (entries SET-1..SET-N added 2026-05-14)
- [`_index.md`](_index.md) — folder index; GEO_003 row added 2026-05-14
- [`GEO_001`](GEO_001_world_geometry.md) — schema parent (§3.1 Settlement + §4.3 SettlementRole + §4.5 GeographyDeltaKind AddNamedSettlement V1 + §5 stage 6 algorithm baseline + §16 GEO-D3 deferral activated here)
- [`GEO_001b`](GEO_001b_authoring_flow.md) — CreativeSeed authoring sibling; SET_001 additive within v4 schema (settlement_seed_mode + settlement_density_hint); LLM authoring template bump v2.tmpl → v3.tmpl
- [`GEO_002 POL_001`](GEO_002_political_layer.md) — sibling V1+30d feature; stage 5 (POL) runs before stage 6 (SET); SET populates Province.capital_settlement_id closing POL's V1+30d-standalone None field
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `world_geometry` annotation extended for SET_001 V1+30d activation (row added 2026-05-14)
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) — `geography.*` namespace extended with 14 V1+30d SET rule_ids (§1.4); GeographyDeltaKind closed-enum bump 9 V1+30d active → 12 with V1+30d active (§1); capability `can_edit_settlement_geography` added (§3)
- [`_boundaries/99_changelog.md`](../../_boundaries/99_changelog.md) — DRAFT 2026-05-14 entry top-anchored
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) — EVT-T3 / T8 sub-shapes unchanged (SET_001 reuses GEO_001 + POL_001 registrations)
- [`features/00_map/MAP_001_map_foundation.md`](../00_map/MAP_001_map_foundation.md) — V1+ position auto-derivation per GEO-D5 activates at SET ship (settlement centroids → map_layout.position for town-tier channels)
- [`features/00_place/PF_001_place_foundation.md`](../00_place/PF_001_place_foundation.md) — PF-D7 procedural place generation gains Settlement.role + population_tier input
- [`features/00_csc/CSC_001_cell_scene_composition.md`](../00_csc/CSC_001_cell_scene_composition.md) — V1+30d skeleton selection gains Settlement.role input (Capital → palace_complex; Fortress → fortified_keep; etc.)

---

## §20 Implementation readiness

**Design layer (this commit):** ✅ schema activation contract + 3 V1+30d DeltaKinds + stage 6 algorithm (burg-score Poisson-disk + hybrid role-assignment + hybrid population_tier) + 15 acceptance scenarios + 14 rule_ids + capability + composition with siblings (POL coordination critical) + fork inheritance + CreativeSeed v3 → v4 schema bump — all declared.

**Implementation phase (V1+30d):** 📦 stage 6 reference impl in `world-service` `geography-generator` Rust module (extends GEO_001 + POL_001 generator) · apply_delta total-function for 3 V1+30d DeltaKinds · capability `can_edit_settlement_geography` issuance flow in auth-service · one-shot migration job (mirrors POL_001 MED-6 precedent) · CI gates: replay-determinism (settlement_seed + POL stage 5 outputs → byte-identical settlements) + apply_delta total-function for 3 new variants + canonical-JSON normalization (per SPIKE_04 GAP-S2.A discipline inherited) + procedural-Poisson-disk acceptance-probability determinism + Capital-role-assignment-tiebreaker (lowest-GeoCellId in capital_province) deterministic.

**Downstream consumer integration (V1+30d / V1+30d+):** 📦 MAP_001 light reopen at LOCK should mark GEO-D5 row "ACTIVATED" (V1+ position auto-derivation now operative for settlement centroids) · PF_001 PF-D7 procedural place generation V1+30d gains Settlement.role + population_tier input · CSC_001 V1+30d skeleton selection per role · S9 prompt-assembly `[GEOGRAPHIC_CONTEXT]` extends with `nearest_settlement_name + settlement_role` fields (closes the slot POL_001 V1+30d already documented but had no Settlement data to populate).

**Status:** DRAFT. CANDIDATE-LOCK upon §16 acceptance scenarios passing integration tests against the reference SET implementation in `world-service`. LOCK upon downstream consumers integrating successfully + GEO_004 ROUTE_001 V1+30d design entry consuming the locked Settlement graph as Dijkstra source/sink pairs.
