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
