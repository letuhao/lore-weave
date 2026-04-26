# features — Index

> **Purpose:** Feature-design workspace for the LLM MMO RPG track. Started 2026-04-25 after kernel-design phase closed at SR12 / I19 (commit `c22aa25` on branch `mmo-rpg/design-resume`). All subsequent feature work lives here; kernel (`02_storage/` + `03_multiverse/`) extends on-demand only when concrete feature need surfaces.

**Active:** (empty — no agent currently editing root)

---

## Layout

```
features/
├── _index.md                                  # this file
├── _spikes/                                   # cross-category exploratory design
├── DF/                                        # big Deferred Features (DF1..DF15)
│   ├── DF04_world_rules/                      # V1-blocking (placeholder)
│   ├── DF05_session_group_chat/               # V1-blocking (placeholder)
│   └── DF07_pc_stats/                         # V1-blocking (placeholder)
├── 02_world_authoring/                        # WA namespace
├── 03_player_onboarding/                      # PO namespace
├── 04_play_loop/                              # PL namespace
├── 05_npc_systems/                            # NPC namespace
├── 06_pc_systems/                             # PCS namespace
├── 07_social/                                 # SOC namespace
├── 08_narrative_canon/                        # NAR namespace
├── 09_emergent/                               # EM namespace
├── 10_platform_business/                      # PLT namespace
├── 11_cross_cutting/                          # CC namespace
├── 12_daily_life/                             # DL namespace (DF1 umbrella)
├── 13_quests/                                 # QST namespace (V2 reserved 2026-04-26)
├── 14_crafting/                               # CFT namespace (V2 reserved 2026-04-26)
└── 15_organization/                           # ORG namespace (V3 reserved 2026-04-26)
```

**Numbering** matches `catalog/cat_NN_*.md` (01 = IF = already kernel-level in `02_storage/`, so skipped here).

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
| `DF/` | `decisions/deferred_DF01_DF15.md` | DF1..DF15 |
| `_spikes/` | — (cross-category) | no owned IDs |

---

## Pending splits / follow-ups

None yet; subfolder is fresh.
