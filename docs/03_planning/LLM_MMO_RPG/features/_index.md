# features — Index

> **Purpose:** Feature-design workspace for the LLM MMO RPG track. Started 2026-04-25 after kernel-design phase closed at SR12 / I19 (commit `c22aa25` on branch `mmo-rpg/design-resume`). All subsequent feature work lives here; kernel (`02_storage/` + `03_multiverse/`) extends on-demand only when concrete feature need surfaces.

**Active:** (empty — no agent currently editing root)

---

## Layout

**34 subfolders** as of 2026-07-17. The `00_*` tier is the **foundation substrate** — shared aggregates that the numbered category features consume rather than redefine.

```
features/
├── _index.md                                  # this file
├── _spikes/                                   # SPIKE — cross-category exploratory design
├── DF/                                        # big Deferred Features (DF1..DF15)
│   ├── DF04_world_rules/                      # V1-blocking
│   ├── DF05_session_group_chat/               # V1-blocking
│   └── DF07_pc_stats/                         # V1-blocking
│
│   ── 00_* foundation substrate (shared aggregates) ──
├── 00_actor/                                  # ACT — unified actor identity + AI-drive + opinion + memory
├── 00_cell_scene/                             # CSC — 4-layer cell→renderable-scene composition
├── 00_entity/                                 # EF  — EntityId taxonomy + spatial presence
├── 00_faction/                                # FAC — factions / sects / orders / clans / guilds
├── 00_family/                                 # FF  — biological/adoption family graph + dynasty
├── 00_geography/                              # GEO — world_geometry procedural substrate
├── 00_identity/                               # IDF — shared PC+NPC concepts (race, lineage, …)
├── 00_map/                                    # MAP — visual node-link map graph layer
├── 00_place/                                  # PF  — place aggregate + PlaceType + connection graph
├── 00_progression/                            # PROG— attributes / skills / cultivation stages
├── 00_reputation/                             # REP — per-(actor, faction) standing
├── 00_resource/                               # RES — ownable/transferable/producible value
├── 00_tilemap/                                # TMP — procedural tilemap visual layer
├── 00_titles/                                 # TIT — per-(actor, title) political/social rank
├── 00_travel/                                 # TVL — inter-settlement route traversal
│
│   ── numbered categories (mirror catalog/cat_NN_*) ──
├── 02_world_authoring/                        # WA
├── 03_player_onboarding/                      # PO
├── 04_play_loop/                              # PL
├── 05_npc_systems/                            # NPC
├── 06_pc_systems/                             # PCS
├── 07_social/                                 # SOC  (index only — no feature docs yet)
├── 08_narrative_canon/                        # NAR  (index only — no feature docs yet)
├── 09_emergent/                               # EM   (index only — no feature docs yet)
├── 10_platform_business/                      # PLT
├── 11_cross_cutting/                          # CC   (index only — no feature docs yet)
├── 12_daily_life/                             # DL   (index only — no feature docs yet)
├── 13_quests/                                 # QST  (V2 reserved — reservation note only)
├── 14_crafting/                               # CFT  (V2 reserved — reservation note only)
├── 15_organization/                           # ORG  (V3 reserved — reservation note only)
├── 16_ai_tier/                                # AIT — NPC tier hierarchy (PC/LLM/Rule/Untracked)
├── 17_time_dilation/                          # TDIL— per-realm/cell/actor fiction-time flow
└── 18_combat/                                 # combat resolution (concept notes only — no IDs yet)
```

**Numbering** for `02_`..`18_` matches `catalog/cat_NN_*.md` (01 = IF = already kernel-level in `02_storage/`, so skipped here). The `00_*` tier is **not** catalog-numbered — it is keyed by ID prefix (`cat_00_<PREFIX>_*.md`).

> ⚠️ **Number collision:** `features/18_combat/` and `catalog/cat_18_DF5_session_group_chat.md` both use `18` for different things. The `18` in the features tree is combat; the `18` in catalog is the DF5 chunk.

---

## How to add a new feature

1. **Load foundation first** — read `00_foundation/` 7 files (5 min total). See `00_foundation/07_feature_workflow.md` for full workflow.
2. **Identify the target folder:**
   - Extends a catalog category → put in that category subfolder (e.g., `05_npc_systems/NPC_001_<name>.md`)
   - Is a big Deferred Feature getting actively designed → create sub-sub-subfolder in `DF/` (e.g., `DF/DF05_session_group_chat/` with multiple design files)
   - Exploratory / cross-category → `_spikes/SPIKE_NN_<topic>.md`
3. **File naming within category folder:** `<catalog-ID>_<seq>_<name>.md` — e.g., `WA_001_world_template_schema.md`, `NPC_003_elena_arc.md`. Sequence increments per category.
4. **Feature doc shape** — target **~150-250 lines** per feature. Shape: user story · UI sketch (if applicable) · interaction flow · data model · kernel APIs used (by reference, don't redesign) · V1 scope cut · test plan. See [`07_feature_workflow.md`](../00_foundation/07_feature_workflow.md).
5. **Kernel extension on-demand** — if feature surfaces a real kernel gap, minimal extension in existing `02_storage/§12*` chunk + foundation cascade in same commit. **Not** a new SR concern.
6. **Update the category's `_index.md`** in the same commit (add row to status table).
7. **Clear your `Active:` header** when done.

---

## Phase rules (locked 2026-04-25)

- **Feature-first** — no more anticipatory kernel design
- **Kernel on-demand** — if feature needs kernel support, minimal extension in existing chunk, NOT new SR
- **Invariant bar raised** — new invariants require demonstrated feature-driven necessity, not "nice-to-have"
- **Reference kernel APIs** — features cite `contracts/*` packages by name; don't redesign them

See `SESSION_HANDOFF.md` 2026-04-24 phase-boundary row for full context.

---

## Category IDs owned

Features consume stable IDs from catalog (each category chunk owns its letter-ID namespace). Feature files in `05_npc_systems/` reference IDs from `catalog/cat_05_NPC_systems.md`, etc.

| Features subfolder | Catalog chunk | ID namespace |
|---|---|---|
| `00_actor/` | `cat_00_ACT_actor_foundation.md` | ACT-* |
| `00_cell_scene/` | `cat_00_CSC_cell_scene_composition.md` | CSC-* |
| `00_entity/` | `cat_00_EF_entity_foundation.md` | EF-* |
| `00_faction/` | (none — no catalog chunk yet) | FAC-* |
| `00_family/` | (none — no catalog chunk yet) | FF-* |
| `00_geography/` | `cat_00_GEO_geography_foundation.md` | GEO-* |
| `00_identity/` | (none — no catalog chunk yet) | IDF-* |
| `00_map/` | `cat_00_MAP_map_foundation.md` | MAP-* |
| `00_place/` | `cat_00_PF_place_foundation.md` | PF-* |
| `00_progression/` | `cat_00_PROG_progression.md` | PROG-* |
| `00_reputation/` | `cat_00_REP_reputation_foundation.md` | REP-* |
| `00_resource/` | `cat_00_RES_resource.md` | RES-* |
| `00_tilemap/` | `cat_00_TMP_tilemap_foundation.md` | TMP-* |
| `00_titles/` | `cat_00_TIT_title_foundation.md` | TIT-* |
| `00_travel/` | `cat_00_TVL_travel_foundation.md` | TVL-* |
| `02_world_authoring/` | `cat_02_WA_world_authoring.md` | WA-* |
| `03_player_onboarding/` | `cat_03_PO_player_onboarding.md` | PO-* |
| `04_play_loop/` | `cat_04_PL_play_loop.md` | PL-* |
| `05_npc_systems/` | `cat_05_NPC_systems.md` | NPC-* |
| `06_pc_systems/` | `cat_06_PCS_pc_systems.md` | PCS-* |
| `07_social/` | `cat_07_SOC_social.md` | SOC-* |
| `08_narrative_canon/` | `cat_08_NAR_narrative_canon.md` | NAR-* |
| `09_emergent/` | `cat_09_EM_emergent.md` | EM-* |
| `10_platform_business/` | `cat_10_PLT_platform_business.md` | PLT-* |
| `11_cross_cutting/` | `cat_11_CC_cross_cutting.md` | CC-* |
| `12_daily_life/` | `cat_12_DL_daily_life.md` | DL-* |
| `13_quests/` | (V2 reserved — `cat_13_QST_quests.md` deferred) | QST-* (V2 reserved 2026-04-26) |
| `14_crafting/` | (V2 reserved — `cat_14_CFT_crafting.md` deferred) | CFT-* (V2 reserved 2026-04-26) |
| `15_organization/` | (V3 reserved — `cat_15_ORG_organization.md` deferred) | ORG-* (V3 reserved 2026-04-26) |
| `16_ai_tier/` | `cat_16_AIT_ai_tier.md` | AIT-* |
| `17_time_dilation/` | `cat_17_TDIL_time_dilation.md` | TDIL-* |
| `18_combat/` | (none — concept notes only) | not yet allocated |
| `DF/` | `decisions/deferred_DF01_DF15.md` | DF1..DF15 |
| `_spikes/` | — (cross-category) | SPIKE-* |

Bird's-eye feature counts + V1/V2/V3/V4 scope rollup live in [`../catalog/_index.md`](../catalog/_index.md) (**474 features** across 12 categories). This file maps *folders*; that file maps *features*.

---

## Pending splits / follow-ups

- **3 foundation folders have no catalog chunk** — `00_faction/` (FAC), `00_family/` (FF), `00_identity/` (IDF). Their IDs are allocated and in use by feature docs, but the bird's-eye catalog has no corresponding `cat_00_*` chunk, so those features are absent from the 474 rollup.
- **`18_combat/` has no allocated ID prefix** — concept notes only.
- **5 categories are index-only** (no feature docs yet): `07_social/`, `08_narrative_canon/`, `09_emergent/`, `11_cross_cutting/`, `12_daily_life/`.

---

## Drift check

This index is hand-maintained and went stale once (2026-04-26 → 2026-07-17: it listed 14 subfolders while the directory had 34). Before trusting it:

```bash
ls -d docs/03_planning/LLM_MMO_RPG/features/*/ | wc -l   # must match the Layout tree
```

Per the "How to add a new feature" step 6 above, **a new subfolder must land in this file in the same commit.**
