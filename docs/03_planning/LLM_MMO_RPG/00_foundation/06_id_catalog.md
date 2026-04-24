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
| `SR1..SR12` | SRE review concerns | [`02_storage/SR01..SR07_*.md`](../02_storage/_index.md) | SR8..SR12 not yet designed | SR7 = Chaos drill cadence (2026-04-24) |
| `SR*-D*` | Per-SR decision numbers | same | next free per SR | SR7-D1..D10 |
| `M1..M7` | Multiverse risks | [`01_problems/M_multiverse_specific.md`](../01_problems/M_multiverse_specific.md) + [`03_multiverse/08_multiverse_risks.md`](../03_multiverse/08_multiverse_risks.md) | none (M8 if new) | M7 = Concept complexity |
| `M*-D*` | M-resolution decision numbers | [`03_multiverse/06_M_C_resolutions.md`](../03_multiverse/06_M_C_resolutions.md) | next free per M | M7-D1..D5 |
| `MV1..MV11` | Multiverse primitives | [`03_multiverse/`](../03_multiverse/_index.md) (across chunks) + [`decisions/locked_decisions.md`](../decisions/locked_decisions.md) | none (MV12 if new) | MV8 = DB subtree split threshold |
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
| `IF-1..IF-40` (+ `-a..-j` sub-chains) | Infrastructure features | [`catalog/cat_01_IF_infrastructure.md`](../catalog/cat_01_IF_infrastructure.md) | IF-41+ | IF-31 = SVID (S11) · IF-32 = WebSocket (S12) · IF-39 = Dependency registry (SR6) · IF-40 = Chaos registry (SR7) |
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
