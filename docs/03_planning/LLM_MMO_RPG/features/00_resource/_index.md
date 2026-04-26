# 00_resource — Index

> **Category:** RES — Resource Foundation (foundation tier; sibling of EF_001 / PF_001 / MAP_001 / CSC_001; **5th and final V1 foundation feature**)
> **Catalog reference:** `catalog/cat_00_RES_resource.md` (PENDING — to be created at RES_001 DRAFT promotion)
> **Purpose:** Defines what counts as ownable, transferable, producible, consumable value across the game world. Resources flow through entities (PC/NPC/cell/town) per the user's 5-axiom definition: (1) resource = units-of-value owned by entity, (2) entities consume 0+ resources, (3) entities produce 0+ resources, (4) NPC/PC own 1+ resources, (5) resources are either directly-consumed OR exchange-mediums. Foundation for HP/Stamina/lương thực, currency, materials, items, cell-production, town-economy, and trade.

**Active:** RES_001 — **Resource Foundation** (DRAFT 2026-04-26 — Q1-Q12 ALL LOCKED + i18n cross-cutting pattern introduced)

**Genre clarification (2026-04-26):** Per user — LoreWeave is **simulation/strategy game with RPG core**, not pure RPG. V1 ships RPG vertical slice; V2+ expands to complex resource economy + giao thương + kinh tế module. RES_001 must accommodate both V1 simplicity AND V2+ extensibility without schema migration. See [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) §1.

**i18n notice (2026-04-26):** Per user direction — game is international, English is the engine standard. RES_001 is FIRST adopter of the **English `snake_case` stable IDs + `I18nBundle` user-facing strings** pattern. RejectReason envelope extended with `user_message: I18nBundle` field (engine-wide cross-cutting). Existing features' Vietnamese hardcoded reject copy = deferred audit (low priority). See RES_001 §2 + `00_CONCEPT_NOTES.md` §11.

**Q1-Q12 LOCKED 2026-04-26 (deep-dive discussion):**
- Q1: 5 V1 categories (Vital / Consumable / Currency / Material / SocialCurrency)
- Q2: Open economy + 3 V1 sinks (food / cell maintenance / trade spread)
- Q3: **2 aggregates split** (`vital_pool` body-bound + `resource_inventory` portable)
- Q4: Hybrid production (cell auto + NPC auto-collect + PC manual + day-boundary tick)
- Q5: Soft hunger PC+NPC (PL_006 Hungry magnitude 1→7; 7=Starvation mortality)
- Q6: NO PC cap V1 (schema reserved on entity_binding); Q7: NO grade V1; Q8: per-character + per-cell ownership
- Q9: Author-declared + Forge + body-substitution (xuyên không Q9c) + NPC death orphan
- Q10: Author-configurable currencies (default single Copper); Q11: RealityManifest canonical rates
- Q12: Global pricing + buy/sell spread (sink #3) + NPC finite liquidity validator

Full decision matrix in [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) §10. Full design in [`RES_001_resource_foundation.md`](RES_001_resource_foundation.md).

**Folder closure status:** Open — DRAFT 2026-04-26. CANDIDATE-LOCK pending Phase 3 review cleanup + closure pass + 17 downstream impacts applied (per RES_001 §17.2).

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — RES_001 brainstorm capture | CONCEPT 2026-04-26 — captures user's 5 axioms + gap analysis (10 dimensions) + boundary intersections + Q1-Q7 | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — 10-game survey informing V1 scope | RESEARCH 2026-04-26 — surveys CK3 / M&B Bannerlord / Anno 1800 / Civ 6 / Stellaris / DF / RimWorld / Vic3 / EU4 / Patrician. Distills 12 recurring patterns. Maps to V1 / V1+30d / V2 / V3 phases. Revises Q1-Q7 + adds Q8-Q12. | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit) |
| RES_001 | **Resource Foundation** (RES) | Resource value substrate. Owns **2 aggregates** (Q3 split): `vital_pool` (T2/Reality, body-bound, actor-only, NON-TRANSFERABLE) + `resource_inventory` (T2/Reality, portable, EntityRef-any). Owns **5-category ResourceKind enum** (V1: Vital/Consumable/Currency/Material/SocialCurrency; V1+30d reserved Item; V2 reserved Recipe; V3 reserved Knowledge/Influence). Owns **3 V1 sinks** (food consumption + cell maintenance cost + trade buy/sell spread) + **4 V1 day-boundary Generators** (CellProduction → NPCAutoCollect → CellMaintenance → HungerTick). Owns **`resource.*` namespace** (12 V1 rule_ids). Owns **9 OPTIONAL RealityManifest extensions** (all engine-defaulted). Owns **i18n cross-cutting pattern** (English IDs + I18nBundle; engine-wide standard). Hybrid production (cell auto + NPC auto-collect + PC manual harvest); body-bound cell ownership for xuyên không (Q9c); NPC finite liquidity validator (Q12c). 10 V1-testable acceptance scenarios AC-RES-1..10. 27 deferrals across V1+30d/V2/V3 (RES-D1..27). 6 open questions for closure pass (RES-Q1..6). | **DRAFT 2026-04-26** | [`RES_001_resource_foundation.md`](RES_001_resource_foundation.md) | (this commit) |

---

## Why this folder is concept-first

User raised Resource Foundation as a critical V1 gap on 2026-04-26 with a clear core model (5 axioms) + 4 worked examples. Initial review surfaced ~10 missing dimensions (ontology / lifecycle / container / production / consumption / exchange / conservation / boundaries / time / V1-scope) plus 5 boundary intersections with locked features (PL_006 / WA_006 / PCS_001 / PL_005 / EF_001).

To avoid the "design while clarifying" anti-pattern that caused PL_005 root scope creep (later corrected with Option C redesign), we capture concept + open questions in `00_CONCEPT_NOTES.md` FIRST, get user answers to Q1-Q7, then promote to RES_001 DRAFT with locked V1 scope.

This mirrors the discipline established by:
- **07_event_model agent brief** — full Q&A before Phase 1 axioms
- **PL_005 Interaction** — Q1-Q8 + B1-B6 mappings before Phase 1 contracts
- **PCS_001 agent brief** — §10 first-session deliverable for user approval before drafting

---

## Kernel touchpoints (anticipated; finalized at RES_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on resource aggregate(s)
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types `aggregate_type=resource_*`; EVT-T4 System resource-creation sub-types; EVT-T5 Generated for time-driven production (per EVT-G framework)
- `07_event_model/12_generation_framework.md` — EVT-G2 trigger source `FictionTimeMarker` for periodic cell production
- `_boundaries/01_feature_ownership_matrix.md` — resource aggregate(s) to be added at RES_001 DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `resource.*` RejectReason namespace to be added at RES_001 DRAFT
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for resource declarations TBD
- `00_entity/EF_001_entity_foundation.md` — entity_binding consumed for ownership scope
- `00_place/PF_001_place_foundation.md` — place (cell-tier) consumed for cell-production binding
- `04_play_loop/PL_005_interaction.md` — OutputDecl `aggregate_type=resource_*` for transfer mechanics
- `04_play_loop/PL_006_status_effects.md` — boundary clarity (Resource = numeric pool; Status = categorical flag)
- `02_world_authoring/WA_006_mortality.md` — HP=0 → MortalityTransition integration
- `06_pc_systems/00_AGENT_BRIEF.md` — PCS_001 stats stub vs Resource boundary

---

## Naming convention

`RES_<NNN>_<short_name>.md`. Sequence per-category. RES_001 is the foundation; future RES_NNN reserved for V1+ extensions (decay/spoilage RES_002 / national-economy RES_003 / quality-grades RES_004 — all V2+).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

RES_001 is the **5th and final V1 foundation feature** — completes the foundation tier covering: WHO (EF_001), WHERE-semantic (PF_001), WHERE-visual-graph (MAP_001), WHAT-inside-cell (CSC_001), **WHAT-flows-through-entity (RES_001)**.

Boundary discipline (anticipated; locked at RES_001 DRAFT):
- Resource value/pool/transfer stays in RES_001
- Status categorical flags stay in PL_006 (Resource is numeric, Status is boolean/enum)
- Death state machine stays in WA_006 (Resource provides HP=0 trigger; Mortality owns transition)
- Stats modifiers (STR/INT) stay in DF7 PC Stats V1+ (Resource = pool that gets modified; Stats = modifier rate)
- Ownership scope stays in EF_001 (Resource references entity_binding; doesn't redefine entity)
- Transfer mechanics stay in PL_005 (Resource provides aggregate_type for OutputDecl; PL_005 owns the kind/intent/cascade)

Five foundations compose cleanly without overlap; RES_001 is the value substrate that makes the foundation tier complete for V1 economic-readiness.
