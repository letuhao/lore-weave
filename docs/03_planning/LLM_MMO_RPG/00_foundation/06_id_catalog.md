# ID Catalog

> **Directory of all stable ID namespaces in the LLM MMO RPG track.** Each namespace is owned by exactly one subfolder (where the authoritative row lives). Use this table to find where to read or add an ID. Do not duplicate an ID across subfolders.

---

## Active namespaces

| Prefix | Scope | Owner subfolder / file | Open slots | Example |
|---|---|---|---|---|
| `R1..R13` | Storage risks (R12 merged into R6) | [`02_storage/R01..R13_*.md`](../02_storage/_index.md) | none (R14 if new risk found) | R9 = Safe reality closure |
| `R*-L*`, `R*-Dn`, `R*-impl-order` | Layers / decisions / impl order per risk | same | next free per risk | R1-L1..L6 |
| `C1..C5` | SA+DE Critical concerns | [`02_storage/C01..C05_*.md`](../02_storage/_index.md) | C6+ if new | C2 = DB subtree split |
| `C1-OW-1..5` | Orphan-worlds extension to C1 | [`02_storage/C01_severance_orphan_worlds.md`](../02_storage/C01_severance_orphan_worlds.md) | C1-OW-6+ | Severance fires at `pending_close → frozen` |
| `C*-D*` | Per-C decision numbers | same | next free per C | C5-D1..D6 |
| `H1..H6` · `M-REV-1..6` · `P1..P4` | Adversarial review follow-ups | [`02_storage/HMP_followups.md`](../02_storage/HMP_followups.md) | next free per tier | H3-NEW-D1..D6 |
| `S1..S13` | Security review concerns | [`02_storage/S01_03..S13_*.md`](../02_storage/_index.md) | S14+ if new | S9 = Prompt assembly |
| `S*-D*`, `S*-NEW-D*` | Per-S decision numbers | same | next free per S | S9-D1..D10 |
| `SR1..SR12` | SRE review concerns | [`02_storage/SR01..SR12_*.md`](../02_storage/_index.md) | **SRE Review COMPLETE 12/12 (2026-04-24)** | SR12 = Observability cost + cardinality (2026-04-24; I19 approved) |
| `SR*-D*` | Per-SR decision numbers | same | next free per SR | SR12-D1..D11 |
| `M1..M7` | Multiverse risks | [`01_problems/M_multiverse_specific.md`](../01_problems/M_multiverse_specific.md) + [`03_multiverse/08_multiverse_risks.md`](../03_multiverse/08_multiverse_risks.md) | none (M8 if new) | M7 = Concept complexity |
| `M*-D*` | M-resolution decision numbers | [`03_multiverse/06_M_C_resolutions.md`](../03_multiverse/06_M_C_resolutions.md) | next free per M | M7-D1..D5 |
| `MV1..MV12` | Multiverse primitives | [`03_multiverse/`](../03_multiverse/_index.md) (across chunks) + [`decisions/locked_decisions.md`](../decisions/locked_decisions.md) | MV13+ | MV8 = DB subtree split threshold · MV12 = reality time model (page-turn fiction-time, 2026-04-25) |
| `WA-1..WA-4` · `WA4-D1..D5` | World Authoring features + heuristics | [`catalog/cat_02_WA_world_authoring.md`](../catalog/cat_02_WA_world_authoring.md) + [`03_multiverse/01_four_layer_canon.md`](../03_multiverse/01_four_layer_canon.md) | next free | WA-4 = L1/L2 category heuristic |
| `DF1..DF15` | Deferred Big Features (DF12 withdrawn) | [`decisions/deferred_DF01_DF15.md`](../decisions/deferred_DF01_DF15.md) | DF16+ if new | DF4 = World Rules · DF5 = Session/Group Chat |
| `PC-A1..A3` · `PC-B1..B3` · `PC-C1..C3` · `PC-D1..D3` · `PC-E1..E3` | Player Character semantics | [`04_player_character/`](../04_player_character/_index.md) (per-letter chunk) | next free per letter | PC-D1 = No parties; sessions replace |
| `PCS-*` | PC Systems schema slots | [`04_player_character/08_data_model.md`](../04_player_character/08_data_model.md) | next free | PCS stats slots |
| `A1..A6` | Category A (LLM reasoning) problems | [`01_problems/A_llm_reasoning.md`](../01_problems/A_llm_reasoning.md) | A7+ | A4 = Retrieval quality (OPEN) |
| `B1..B5` | Category B (Distributed systems) | [`01_problems/B_distributed_systems.md`](../01_problems/B_distributed_systems.md) | B6+ | |
| `C1..C6` (problems) | Category C (Product / UX) problems — distinct from SA+DE `C1..C5` | [`01_problems/C_product_ux.md`](../01_problems/C_product_ux.md) | C7+ | C2 = Narrative pacing (ACCEPTED) |
| `D1..D3` | Category D (Economics) | [`01_problems/D_economics.md`](../01_problems/D_economics.md) | D4+ | D1 = LLM cost (OPEN) |
| `E1..E3` | Category E (Moderation/safety/legal) | [`01_problems/E_moderation_safety_legal.md`](../01_problems/E_moderation_safety_legal.md) | E4+ | E3 = IP ownership (OPEN) |
| `F1..F5` | Category F (Content design) | [`01_problems/F_content_design.md`](../01_problems/F_content_design.md) | F6+ | F2 = AI GM (ACCEPTED) |
| `G1..G3` | Category G (Testing/ops) | [`01_problems/G_testing_ops.md`](../01_problems/G_testing_ops.md) | G4+ | Designs in `05_qa/LLM_MMO_TESTING_STRATEGY.md` |
| `IF-1..IF-45` (+ `-a..-j` sub-chains) | Infrastructure features | [`catalog/cat_01_IF_infrastructure.md`](../catalog/cat_01_IF_infrastructure.md) | IF-46+ | IF-31 = SVID (S11) · IF-32 = WebSocket (S12) · IF-39 = Dependency registry (SR6) · IF-40 = Chaos registry (SR7) · IF-41 = Capacity budget registry (SR8) · IF-42 = Alert rule registry (SR9) · IF-43 = Supply chain registry (SR10) · IF-44 = Turn state machine (SR11) · IF-45 = Observability inventory (SR12) |
| `WA-*` (features) | World Authoring features | [`catalog/cat_02_WA_world_authoring.md`](../catalog/cat_02_WA_world_authoring.md) | next free | |
| `PO-*` | Player Onboarding | [`catalog/cat_03_PO_player_onboarding.md`](../catalog/cat_03_PO_player_onboarding.md) | next free | |
| `PL-*` | Play Loop (core runtime) | [`catalog/cat_04_PL_play_loop.md`](../catalog/cat_04_PL_play_loop.md) | next free | |
| `NPC-*` | NPC Systems | [`catalog/cat_05_NPC_systems.md`](../catalog/cat_05_NPC_systems.md) | next free | |
| `SOC-*` | Social | [`catalog/cat_07_SOC_social.md`](../catalog/cat_07_SOC_social.md) | SOC-8+ (SOC-6/SOC-7 are **out-of-scope** markers, do not reuse) | |
| `NAR-*` | Narrative / Canon | [`catalog/cat_08_NAR_narrative_canon.md`](../catalog/cat_08_NAR_narrative_canon.md) | next free | |
| `EM-*` | Emergent / Advanced (fork, travel, lifecycle) | [`catalog/cat_09_EM_emergent.md`](../catalog/cat_09_EM_emergent.md) | next free | |
| `PLT-*` | Platform / Business | [`catalog/cat_10_PLT_platform_business.md`](../catalog/cat_10_PLT_platform_business.md) | next free | |
| `CC-1..CC-6` + `CC-6-D1..D7` | Cross-cutting concerns (a11y, i18n, telemetry) | [`catalog/cat_11_CC_cross_cutting.md`](../catalog/cat_11_CC_cross_cutting.md) | CC-7+ | CC-6 = A11y |
| `DL-*` | Daily Life (DF1 umbrella) | [`catalog/cat_12_DL_daily_life.md`](../catalog/cat_12_DL_daily_life.md) | next free | |
| `Q-*` | Pending questions (external input required) | [`decisions/pending_questions.md`](../decisions/pending_questions.md) | Q-A5+ | Q-A4 / Q-D1 / Q-E3 |
| `L1..L4` + `LMV-*` | Locked top-level storage + multiverse decisions | [`decisions/locked_decisions.md`](../decisions/locked_decisions.md) | rarely extended | LMV-Fork = Snapshot fork (MV4-a) |
| `RTM-A1..A9` · `RTM-Q1..Q10` · `RTM-D1..D10` | Realtime movement & presence authority (axioms / decisions) | [`08_realtime_movement_authority.md`](../08_realtime_movement_authority.md) | RTM-A10+ / next free | RTM-A2 = predict→validate(WASM)→reconcile · RTM-Q8 = seamless cross-region (V1) |
| `ILR-A1..A3` · `ILR-D1..D9` | Interaction layer ↔ graphical-medium reconciliation (axioms / decisions) | [`09_interaction_layer_reconciliation.md`](../09_interaction_layer_reconciliation.md) | next free | ILR-A2 = three-layer position stack · ILR-A3 = hybrid NPC movement |
| `TG-A1..A4` · `TG-D1..D8` | Tactical-grid combat (axioms / decisions); extends COMB | [`features/18_combat/COMB_002_tactical_grid.md`](../features/18_combat/COMB_002_tactical_grid.md) | next free | TG-A1 = LLM-zero-space · TG-A3 = move+act budgets (FFT/XCOM) |
| `AGT-A1..A6` · `AGT-D1..D8` | Agent Decision Standard & SDK (driver-agnostic agent contract) | [`11_agent_decision_standard.md`](../11_agent_decision_standard.md) | next free | AGT-A2 = bounded vocab = MCP tool set · AGT-A3 = pluggable drivers (cost lever) |
| `ITM-A1..A9` · `ITM-D1..D23` · `ITM-Q1..Q8` · `ITM-V1..V18` · `ITM-C1..C13` | Item + equipment + inventory substrate — the body behind `EntityId::Item` (closes AUD-F5) | 3 files, one namespace: [`PL_007_item.md`](../features/04_play_loop/PL_007_item.md) **§1–§8** (axioms A1–A7) · [`PL_007c_integration.md`](../features/04_play_loop/PL_007c_integration.md) **§9–§19, continuing the numbering** (V1–V13, C1–C11, D1–D12+D19–D23, Q1–Q5) · [`PL_007b_inventory.md`](../features/04_play_loop/PL_007b_inventory.md) (A8–A9, V14–V18, D13–D18+D20+D23, Q6–Q8) | next free per series | ITM-A2 = the representation rule (instanced ⇒ entity, fungible ⇒ resource balance; enforced at bootstrap) · ITM-A5 = equipment is a slot assignment, not a location · ITM-A9 = fixed-size inventory context. **All Q1–Q8 resolved at the 2026-07-26 review pass.** |
| `DF7-A1..A14` · `DF7-Q1..Q14` · `DF7-D1..D15` · `DF7-V1..V6` · `AC-DF7-1..21` · `EC-1..EC-15` | Actor Stat Block — derived-stat projection layer (axioms / decisions / deferrals / validators / acceptance / edge cases) | [`features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md`](../features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md) (law) + [`DF07_002_edge_cases_and_closure.md`](../features/DF/DF07_pc_stats/DF07_002_edge_cases_and_closure.md) (`EC-*`, A12..A14, Q12..Q14, AC-16..21) | next free per family | DF7-A1 = closed engine slot set · DF7-A2 = derived, never stored as truth · DF7-A8 = stat-layer vs resolution-time boundary · DF7-A14 = clamp order is a security property |

| `THR-A1..A6` · `THR-Q1..Q8` · `THR-D1..D8` · `THR-V1..V7` · `AC-THR-1..12` | Threat & Targeting — who a hostile attacks (axioms / decisions / deferrals / validators / acceptance) | [`features/18_combat/COMB_003_threat_and_targeting.md`](../features/18_combat/COMB_003_threat_and_targeting.md) | AUD-F9 (threat third) |
| `SPO-A1..A7` · `SPO-Q1..Q14` · `SPO-D1..D12` · `SPO-V1..V10` · `AC-SPO-1..20` | Loot & Spoils — what an encounter produces; **§16 Binding Contest** (`BindTier` defeat-time disposition, SPO-Q10..Q14) | [`features/18_combat/COMB_004_loot_and_spoils.md`](../features/18_combat/COMB_004_loot_and_spoils.md) | AUD-F9 (loot third); adds seed roles `loot` + `bind` to COMB_001 Q8 |
| `SPN-A1..A9` · `SPN-Q1..Q9` · `SPN-D1..D9` · `SPN-V1..V9` · `AC-SPN-1..13` | Encounter Spawning & Hostile Population — epoch respawn, aggro, formation, danger band | [`features/18_combat/COMB_005_encounter_spawning.md`](../features/18_combat/COMB_005_encounter_spawning.md) | AUD-F9 (spawning third); builds COMB_001 §9 closure item 8 |
| `PVP-A1..A8` · `PVP-Q1..Q10` · `PVP-D1..D8` · `PVP-V1..V7` · `AC-PVP-1..14` | PvP & Stakes — consent channels, stakes, disparity-cap waiver, notoriety | [`features/18_combat/COMB_006_pvp_and_stakes.md`](../features/18_combat/COMB_006_pvp_and_stakes.md) | closes `COMB-Q3`; discharges `PC-D2` (2026-04-23) |
| `ABL-A1..A7` · `ABL-Q1..Q10` · `ABL-D1..D12` · `ABL-V1..V9` · `AC-ABL-1..15` | Ability Foundation — the activatable-effect catalogue; owns the `EffectOp` shared vocabulary | [`features/19_ability/ABL_001_ability_foundation.md`](../features/19_ability/ABL_001_ability_foundation.md) | AUD-F10; **new namespace `19_ability/`** |

### Backfill (2026-07-27 — design-lint findings)

> Every namespace below was already in live use across the corpus but never declared here —
> `scripts/design-lint.py --check symbol` reported them all as `unregistered-prefix`. Owners follow the
> registrations in [`_boundaries/01_feature_ownership_matrix.md`](../_boundaries/01_feature_ownership_matrix.md)
> where a row exists there; otherwise the declaring doc found by search. Same table shape and rules as above.

| Prefix | Scope | Owner subfolder / file | Open slots | Example |
|---|---|---|---|---|
| `DP-A*` · `DP-T*` · `DP-R*` · `DP-S*` · `DP-K*` · `DP-C*` · `DP-X*` · `DP-F*` · `DP-Ch*` | Data-plane axioms / tiers / rules / snapshots / kernel API / coherency / prohibitions / flows / chapters (LOCKED) | [`06_data_plane/`](../06_data_plane/_index.md) | per DP change control | DP-A16 = epoch fence · DP-Ch18 |
| `EVT-A*` · `EVT-T*` · `EVT-P*` · `EVT-V*` · `EVT-L*` · `EVT-S*` · `EVT-G*` · `EVT-Q*` | Event-model axioms / taxonomy / payloads / validation / lifecycle / schema / generation framework / questions (Phase 1-6 LOCKED + Option C redesign) | [`07_event_model/`](../07_event_model/_index.md) | per event-model track | EVT-A4 = producer roles · EVT-T5 = Generated |
| `OOS-1..2` | Data-plane out-of-scope pointers | [`06_data_plane/99_open_questions.md`](../06_data_plane/99_open_questions.md) | OOS-3+ | OOS-1 = NPC ↔ SessionContext mapping |
| `REAL-1..6` | Realtime review findings, reframed into DP Phase 4 Q15..Q20 | [`06_data_plane/99_open_questions.md`](../06_data_plane/99_open_questions.md) | closed set | REAL-6 = LLM turn latency |
| `EF-*` | Entity Foundation (`EF-A*` axioms · `EF-D*` deferrals · `EF-Q*` questions · `AC-EF-*` acceptance) | [`features/00_entity/EF_001_entity_foundation.md`](../features/00_entity/EF_001_entity_foundation.md) + [`catalog/cat_00_EF_entity_foundation.md`](../catalog/cat_00_EF_entity_foundation.md) | next free per family | EF-Q2 |
| `PF-*` | Place Foundation | [`features/00_place/PF_001_place_foundation.md`](../features/00_place/PF_001_place_foundation.md) + [`catalog/cat_00_PF_place_foundation.md`](../catalog/cat_00_PF_place_foundation.md) | next free per family | AC-PF-7 |
| `MAP-*` | Map Foundation | [`features/00_map/MAP_001_map_foundation.md`](../features/00_map/MAP_001_map_foundation.md) + [`catalog/cat_00_MAP_map_foundation.md`](../catalog/cat_00_MAP_map_foundation.md) | next free per family | MAP-Q3 |
| `TMP-*` | Tilemap Foundation (TMP_001..TMP_009) | [`features/00_tilemap/TMP_001_tilemap_foundation.md`](../features/00_tilemap/TMP_001_tilemap_foundation.md) + [`catalog/cat_00_TMP_tilemap_foundation.md`](../catalog/cat_00_TMP_tilemap_foundation.md) | next free per family | TMP-A4 = deterministic seed |
| `PLACE-Q*` · `PIPE-Q*` · `TPL-Q*` · `BIOME-Q*` · `TR-Q*` · `CONN-Q*` · `LLM-Q*` · `ASSET-Q*` | Per-chunk question namespaces of the TMP_00N tilemap sub-docs (zone placement / pipeline modificators / template authoring / biome+obstacles / treasure+objects / connections+guards / LLM integration / isometric asset pipeline) | [`features/00_tilemap/`](../features/00_tilemap/_index.md) (TMP_002..TMP_009, one namespace per chunk) | next free per chunk | ASSET-Q10 · LLM-Q4 |
| `CSC-*` | Cell Scene Composition | [`features/00_cell_scene/CSC_001_cell_scene_composition.md`](../features/00_cell_scene/CSC_001_cell_scene_composition.md) + [`catalog/cat_00_CSC_cell_scene_composition.md`](../catalog/cat_00_CSC_cell_scene_composition.md) | next free per family | CSC-A1 = LLM categorical-only |
| `RES-*` | Resource Foundation | [`features/00_resource/RES_001_resource_foundation.md`](../features/00_resource/RES_001_resource_foundation.md) + [`catalog/cat_00_RES_resource.md`](../catalog/cat_00_RES_resource.md) | next free per family | RES-Q1 |
| `ACT-*` | Actor Foundation (unification refactor) | [`features/00_actor/ACT_001_actor_foundation.md`](../features/00_actor/ACT_001_actor_foundation.md) + [`catalog/cat_00_ACT_actor_foundation.md`](../catalog/cat_00_ACT_actor_foundation.md) | next free per family | ACT-A7 = Synthetic excluded V1 |
| `PROG-*` | Progression Foundation | [`features/00_progression/PROG_001_progression_foundation.md`](../features/00_progression/PROG_001_progression_foundation.md) + [`catalog/cat_00_PROG_progression.md`](../catalog/cat_00_PROG_progression.md) | next free per family | PROG-A1 |
| `RAC-*` · `LNG-*` · `PRS-*` · `ORG-*` · `IDL-*` | Identity Foundation quintet — race / language / personality / origin / ideology (Tier 5 Actor Substrate) | [`features/00_identity/`](../features/00_identity/_index.md) (IDF_001..IDF_005) | next free per feature | PRS-Q9 = 12×12 opinion matrix |
| `IDF-1..5` | Identity Foundation feature-row shorthand (IDF-n ↔ IDF_00n) used in catalog cross-refs | [`features/00_identity/`](../features/00_identity/_index.md) | IDF-6+ if a new identity feature | IDF-2 = LanguageId |
| `FF-*` | Family Foundation | [`features/00_family/FF_001_family_foundation.md`](../features/00_family/FF_001_family_foundation.md) | next free per family | FF-A1 |
| `FAC-*` | Faction Foundation | [`features/00_faction/FAC_001_faction_foundation.md`](../features/00_faction/FAC_001_faction_foundation.md) | next free per family | FAC-1 |
| `REP-*` | Reputation Foundation | [`features/00_reputation/REP_001_reputation_foundation.md`](../features/00_reputation/REP_001_reputation_foundation.md) + [`catalog/cat_00_REP_reputation_foundation.md`](../catalog/cat_00_REP_reputation_foundation.md) | next free per family | REP-A1 |
| `TIT-*` | Title Foundation (political-rank triangle) | [`features/00_titles/TIT_001_title_foundation.md`](../features/00_titles/TIT_001_title_foundation.md) + [`catalog/cat_00_TIT_title_foundation.md`](../catalog/cat_00_TIT_title_foundation.md) | next free per family | TIT-C1 |
| `AIT-*` | AI Tier (3-tier NPC architecture) | [`features/16_ai_tier/AIT_001_ai_tier_foundation.md`](../features/16_ai_tier/AIT_001_ai_tier_foundation.md) + [`catalog/cat_16_AIT_ai_tier.md`](../catalog/cat_16_AIT_ai_tier.md) | next free per family | AIT-A1 |
| `TDIL-*` | Time Dilation (4-clock relativity) | [`features/17_time_dilation/TDIL_001_time_dilation_foundation.md`](../features/17_time_dilation/TDIL_001_time_dilation_foundation.md) + [`catalog/cat_17_TDIL_time_dilation.md`](../catalog/cat_17_TDIL_time_dilation.md) | next free per family | TDIL-A9 = replay determinism |
| `COMB-*` | Combat Foundation (the COMB_002..006 sub-docs own their own `TG-*`/`THR-*`/`SPO-*`/`SPN-*`/`PVP-*` rows above) | [`features/18_combat/COMB_001_combat_foundation.md`](../features/18_combat/COMB_001_combat_foundation.md) | next free per family | COMB-Q3 |
| `TVL-*` | Travel Foundation | [`features/00_travel/TVL_001_travel.md`](../features/00_travel/TVL_001_travel.md) + [`catalog/cat_00_TVL_travel_foundation.md`](../catalog/cat_00_TVL_travel_foundation.md) | next free per family | TVL-16 |
| `CTV-*` | Composite Travel (TVL_002) | [`features/00_travel/TVL_002_composite_travel.md`](../features/00_travel/TVL_002_composite_travel.md) | next free per family | CTV-D1 |
| `TVM-*` | Mount & Vehicle Travel (TVL_003) | [`features/00_travel/TVL_003_mount_vehicle_travel.md`](../features/00_travel/TVL_003_mount_vehicle_travel.md) | next free per family | TVM-Q1 |
| `CTE-*` | Travel Encounters (TVL_004) | [`features/00_travel/TVL_004_travel_encounters.md`](../features/00_travel/TVL_004_travel_encounters.md) | next free per family | CTE-Q1 |
| `TVP-*` | Group / Party Travel (TVL_005) | [`features/00_travel/TVL_005_group_party_travel.md`](../features/00_travel/TVL_005_group_party_travel.md) | next free per family | TVP-Q1 |
| `GEO-*` | Geography Foundation (world geometry) | [`features/00_geography/GEO_001_world_geometry.md`](../features/00_geography/GEO_001_world_geometry.md) + [`catalog/cat_00_GEO_geography_foundation.md`](../catalog/cat_00_GEO_geography_foundation.md) | next free per family | GEO-D10 |
| `POL-*` | Political Layer (GEO_002) | [`features/00_geography/GEO_002_political_layer.md`](../features/00_geography/GEO_002_political_layer.md) | next free per family | POL-Q1 |
| `SET-*` | Settlement Generator (GEO_003) — settlements, **not** the platform settings standard | [`features/00_geography/GEO_003_settlement_generator.md`](../features/00_geography/GEO_003_settlement_generator.md) | next free per family | SET-Q1 |
| `ROUTE-*` | Route Network Generator (GEO_004) | [`features/00_geography/GEO_004_route_network_generator.md`](../features/00_geography/GEO_004_route_network_generator.md) | next free per family | ROUTE-V8 |
| `INT-*` | PL_005 Interaction (incl. compound `INT-CON-D*` deferrals and `AC-INT-*` acceptance ids) | [`features/04_play_loop/PL_005_interaction.md`](../features/04_play_loop/PL_005_interaction.md) (+ PL_005b / PL_005c) | next free per family | INT-D9 |
| `STA-*` | PL_006 Status Effects | [`features/04_play_loop/PL_006_status_effects.md`](../features/04_play_loop/PL_006_status_effects.md) | next free per family | STA-D4 |
| `GR-*` | PL_002 Grammar per-feature deferral / question IDs | [`features/04_play_loop/PL_002_command_grammar.md`](../features/04_play_loop/PL_002_command_grammar.md) | next free | GR-D1 |
| `LX-*` · `HER-*` · `FRG-*` · `MOR-*` | World-Authoring per-feature deferral / question IDs (WA_001 Lex · WA_002 Heresy · WA_003 Forge · WA_006 Mortality) | [`features/02_world_authoring/`](../features/02_world_authoring/_index.md) | next free per feature | HER-D2 |
| `CHR-*` · `SUC-*` | Platform per-feature deferral / question IDs (PLT_001 Charter · PLT_002 Succession) | [`features/10_platform_business/`](../features/10_platform_business/_index.md) | next free per feature | CHR-D9 |
| `CST-*` · `CHO-*` · `DSR-*` | NPC per-feature deferral / question IDs (NPC_001 Cast · NPC_002 Chorus · NPC_003 Desires) | [`features/05_npc_systems/`](../features/05_npc_systems/_index.md) | next free per feature | CST-D1 |
| `GAP-S*` | SPIKE_04 geo-procgen validation gap findings (GAP-S⟨step⟩.⟨letter⟩) | [`features/_spikes/SPIKE_04_geo_procgen_validation.md`](../features/_spikes/SPIKE_04_geo_procgen_validation.md) | per spike section | GAP-S3.E |
| `SPIKE-04-Q1..Q5` | Spike-scoped open questions | [`features/_spikes/SPIKE_04_geo_procgen_validation.md`](../features/_spikes/SPIKE_04_geo_procgen_validation.md) | per spike | SPIKE-04-Q2 |
| `AUD-F*` · `AUD-D*` | Medium-correction blast-radius audit findings + decisions | [`10_medium_blast_radius_audit.md`](../10_medium_blast_radius_audit.md) | next free | AUD-F9 |
| `SL-A*` · `SL-D*` · `SL-Q*` | Simulation loop & scheduler standard | [`13_simulation_loop.md`](../13_simulation_loop.md) | next free per family | SL-A2 = slower class never blocks faster |
| `SC-A*` · `SC-D*` | `sim-core` crate implementation spec | [`14_sim_core_spec.md`](../14_sim_core_spec.md) | next free per family | SC-A1 = order-independent safety |
| `CS-A*` · `CS-D*` | commit-service standard (admission + durability around `sim-core`) | [`15_commit_service.md`](../15_commit_service.md) | next free per family | CS-A6 = encounter is an ephemeral child channel |
| `RLS-A*` · `RLS-I*` · `RLS-D*` · `RLS-Q*` | Ruleset loader & registry standard | [`16_ruleset_loader_and_registry.md`](../16_ruleset_loader_and_registry.md) (+ annex 16a) | next free per family | RLS-A13 = `ruleset_digest` envelope pin |
| `CLS-1..3` | Ruleset field-classification findings | [`16a_ruleset_field_classification.md`](../16a_ruleset_field_classification.md) | CLS-4+ | CLS-2 = 144-entry archetype matrix completion |
| `GDA-A*` · `GDA-D*` · `GDA-F*` · `GDA-Q*` | Game data architecture flows + audit findings | [`17_game_data_architecture.md`](../17_game_data_architecture.md) | next free per family | GDA-F11 = island model vs T3 tiers |
| `RBS-A*` · `RBS-D*` · `RBS-F*` · `RBS-Q*` | Reality bootstrap spec | [`18_reality_bootstrap.md`](../18_reality_bootstrap.md) | next free per family | RBS-A3 = role hosted by the seeding worker |
| `REC-01..` | Reconciliation register rows (typed EDIT / LOCK / DECISION / AMEND) | [`19_reconciliation_register.md`](../19_reconciliation_register.md) | next free | REC-28 = writer-role gap |
| `POC-1..2` | Build-phase PoC findings (reconciliation register §15a) | [`19_reconciliation_register.md`](../19_reconciliation_register.md) | POC-3+ | POC-2 = validity 50% → 83% on fix |
| `CWC-*` | Client wire contract (DRAFT) | [`20_client_wire_contract.md`](../20_client_wire_contract.md) | next free per family | CWC-A1 |
| `CEI-*` | Measured architecture ceilings (commit + fan-out budget) | [`21_architecture_ceilings.md`](../21_architecture_ceilings.md) | next free per family | CEI-9 = fan-out has 11× the commit path's headroom |
| `IAS-*` | Ingress & action admission standard (DRAFT) | [`22_ingress_and_admission.md`](../22_ingress_and_admission.md) | next free per family | IAS-A2 = validation splits by state-readership, not cost |
| `CNC-*` | Concurrency & cache audit (thread → CPU → node) | [`23_concurrency_and_cache_audit.md`](../23_concurrency_and_cache_audit.md) | next free per family | CNC-F6 = durable idempotency written but never read |
| `IMG-*` | Island manager — writer liveness + island lifecycle | [`24_island_manager.md`](../24_island_manager.md) | next free per family | IMG-A1 = put liveness where safety already is |
| `PID-*` | Producer identity & trust derivation (bus auth) | [`25_producer_identity.md`](../25_producer_identity.md) | next free per family | PID-A1 = a trust attribute is derived, never read from the message |
| `IMP-*` | Implementation architecture — code vs config, module boundaries, anti-rot | [`26_implementation_architecture.md`](../26_implementation_architecture.md) | next free per family | IMP-A1 = code owns SHAPE, config owns VALUES |
| `XST-*` | Extensibility stress test + live-defect record | [`27_extensibility_stress_test.md`](../27_extensibility_stress_test.md) | next free per family | XST-D5 = the ruleset digest is decorative |
| `PRD-*` | Product definition — the core loop + what "extensible mechanics" concretely means | [`28_product_definition.md`](../28_product_definition.md) | next free per family | PRD-A2 = a mechanic is WHEN·IF·THEN·ON |
| `ONT-*` | Ontology — tồn tại / ta / chúng: existence ladder, the self, the others | [`29_ontology_existence_self_others.md`](../29_ontology_existence_self_others.md) | next free per family | ONT-A2 = the self is not the decider |
| `EXC-*` | Exchange model — three currencies, the transaction dataflow, ledger laws | [`30_exchange_model_and_dataflow.md`](../30_exchange_model_and_dataflow.md) | next free per family | EXC-A1 = time / resource / imprint obey different laws |
| `WSA-*` | World-simulation architecture + spec reconciliation (4 layers, local writes, near/far reads) | [`31_world_simulation_architecture.md`](../31_world_simulation_architecture.md) | next free per family | WSA-A3 = every write is local and unilateral |
| `TRG-*` | Trigger group order + failure tolerance (8 locked groups, aspect lifecycle) | [`33_trigger_group_order.md`](../33_trigger_group_order.md) | next free per family | TRG-A1 = ordered groups, commutative within |
| `NV-*` | **Non-vacuity** — a check must be ABLE to fail, and you must have watched it. Repo-wide, **not** track-scoped: the authoritative file lives outside this folder | [`docs/standards/non-vacuity.md`](../../../standards/non-vacuity.md) | next free | NV-1 = a check that cannot fail is a claim in the costume of evidence · NV-4 = an adjacent decision defeats it |
| `QTY-*` | Quantity architecture — the four layers (laws · roles+derived · declared quantities · sources), who may add a quantity, and what growth costs | [`35_quantity_architecture.md`](../35_quantity_architecture.md) | next free per family | QTY-A3 = laws bind to **roles**, not to quantities · QTY-A1 = arithmetic is code, arrangement is data |
| `SPG-*` | **Space graph / map architecture** — the `MapKind` closed set + containment matrix (replacing `MAP_001`'s retired `ChannelTier` ladder, `SPG-R1`), parent-relative coordinates, the containment-vs-control two-graph split, control as possession, collision as topology | [`36_map_architecture.md`](../36_map_architecture.md) | next free per family | SPG-A1 = an entity may HOLD an interior (the converse of WSA-A7) · SPG-A4 = containment is a strict acyclic tree, control is free, **they never interact** · SPG-A5 = no node stores an absolute position · SPG-A8 = collision is topological, not dynamic · SPG-A10 = control is a **binding**, not an attribute |
| `WDS-*` | **World data storage** — where the world's bytes live: generated content is CONTENT not HISTORY, a pinned `content_hash` as a causal record, `O(1)` genesis, the content-addressed `WorldBaselineStore`, and bytes-as-SSOT with regeneration reserved for audit | [`37_world_data_storage.md`](../37_world_data_storage.md) | next free per family | WDS-A1 = a baseline is the initial condition the event log is written AGAINST, so the log carries only divergence; narrows `GDA-D4` (WDS-F1) and dissolves `RBS-Q1` (WDS-F2) |
| `CPL-*` | **Content pipeline** — the tier between a LoreWeave book and a loadable reality: extraction (what the book SAYS) vs enrichment (what it does not), one generator MODULE per element under one contract, a human gate at every stage boundary, and the pinned artifact as SSOT | [`38_content_pipeline_architecture.md`](../38_content_pipeline_architecture.md) | next free per family | CPL-A1 = extraction and enrichment are different pipelines and must never be one function · CPL-A2 = the generator's output is admitted by the ENGINE'S OWN validator, not a copy · CPL-A3 = there is no universal generator, one module per element under one contract · CPL-A8 = the manifest is pinned into the reality binding exactly as the ruleset is |

---

## Retired / withdrawn IDs (never reuse)

| ID | Reason | Row |
|---|---|---|
| R12 | Merged into R6 (Redis ephemerality is just publisher reliability) | `R06_R12_publisher_reliability.md` |
| DF12 | Cross-Reality Analytics & Search — no justifying feature (R5 anti-pattern applies) | `decisions/deferred_DF01_DF15.md` |
| SOC-6 | Parties — out of scope (PC-D1 → sessions replace parties) | `catalog/cat_07_SOC_social.md` |
| SOC-7 | Global chat — out of scope (PC-D3) | `catalog/cat_07_SOC_social.md` |
| IF-25 / IF-26 | Renumbered to IF-27 / IF-28 during S8 (one-time migration; do not repeat) | `catalog/cat_01_IF_infrastructure.md` |

---

## How to pick a new ID

1. **Find your namespace above.** Match scope to a prefix.
2. **Open the owner subfolder's `_index.md`** — it lists the highest-used number in that namespace.
3. **Take the next free number.** Do not reserve ranges.
4. **Check for collisions across problem categories** — problem `C1..C6` and SA+DE `C1..C5` share the letter; always qualify ("C1 problem" vs "C1 SA+DE critical").
5. **Commit the new ID + its row + update to the owner `_index.md`** in the same commit.

If your feature doesn't fit any existing namespace, propose a new letter in SESSION_HANDOFF — do not invent a letter unilaterally. New namespaces require architect sign-off (same workflow as new invariants per `02_invariants.md`).
