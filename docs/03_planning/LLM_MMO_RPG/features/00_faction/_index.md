# 00_faction — Index

> **Category:** FAC — Faction Foundation (foundation tier candidate post-FF_001)
> **Catalog reference:** `catalog/cat_00_FAC_faction_foundation.md` (NOT YET CREATED — defer to FAC_001 DRAFT promotion)
> **Purpose:** The substrate for **factions / sects / orders / clans / guilds** — actor-level membership with role + rank + ideology binding. Resolves V1+ deferrals from FF_001 (sect/master-disciple/sworn brotherhood per Q4 LOCKED) + IDF_005 (sect membership requirement per IDL-D2). Wuxia critical (sect rivalries / master-disciple / Wulin Meng).

**Active:** FAC_001 — **Faction Foundation** (DRAFT 2026-04-26 — Q1-Q10 LOCKED via 49a17ed; full §1-§19 spec + boundary registered this commit 2/4)

**Folder closure status:** Open — DRAFT phase. Phase 3 + closure pass cycle pending (commits 3/4 + 4/4).

**V1+ priority signal:**
- IDF_005 IDL-D2 LOCKED: "Sect / order / giáo phái membership (faction system) → V1+ FAC_001 Faction Foundation"
- FF_001 Q4 LOCKED + FF-D6 + FF-D7: "V1+ FAC_001 owns sect/master-disciple/sworn relationships (NOT FF_001)"
- IDF folder closure roadmap (50d65fa): "FAC_001 = priority 5 post-IDF closure"

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — FAC_001 brainstorm capture | CONCEPT 2026-04-26 — captures user framing (wuxia priority + sect/master-disciple resolution from FF_001+IDF_005) + 12-dimension gap analysis + Q1-Q10 critical scope questions | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — reference games survey | DRAFT 2026-04-26 — Wuxia sect mechanics primary (Sands of Salzaar / Path of Wuxia / Sword & Fairy) + CK3 court/vassalage + Bannerlord clan + VtM clans+sects + Total War 3K sworn brotherhood + EU4 estates + Stellaris factions | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit) |
| FAC_001 | **Faction Foundation** (FAC) | Per-reality faction declarative entity (sparse) + per-actor actor_faction_membership (V1 cap=1 per Q2 REVISION; Vec future-proofs V1+ multi). 6-variant FactionKind (Sect/Order/Clan/Guild/Coalition/Other). Author-declared role taxonomy per FactionDecl (Q3). Numeric rank u16 only V1 (Q4 REVISION). master_actor_id field RESOLVES FF-D7. FactionDecl.requires_ideology RESOLVES IDL-D2. Static default_relations (3-variant Hostile/Neutral/Allied) per Q5; V1+ DIPL_001 dynamic. **Q7 REVISION: defer sworn brotherhood V1+** via FAC-D10. RealityManifest extension `canonical_factions` + `canonical_faction_memberships` REQUIRED V1. 8 V1 reject rules (faction.* namespace) + 4 V1+ reservations. 10 V1-testable AC + 4 V1+ deferred. 17 deferrals (FAC-D1..D17). | **DRAFT** 2026-04-26 (Q1-Q10 LOCKED 49a17ed; full spec + boundary register this commit 2/4) | [`FAC_001_faction_foundation.md`](FAC_001_faction_foundation.md) | (this commit) |

---

## Why this folder is concept-first

User direction 2026-04-26 picked Option C (FAC_001 deep-dive next; all dependencies CANDIDATE-LOCK). Wuxia narrative needs sect mechanics — sect rivalries, master-disciple, Wulin Meng, sect-faction politics. FAC_001 is the resolver for V1+ deferrals from FF_001 + IDF_005.

But — faction system is wide (CK3 vassalage + court + estates + ranks; Bannerlord clan tiers; VtM 13 clans + sects). V1 scope must be narrow. Concept-notes phase captures:

1. User framing (wuxia priority + V1+ deferral resolution from FF_001 + IDF_005)
2. Worked examples (Wuxia 5-sect preset / Modern guild / Sci-fi corporate house)
3. Gap analysis (12 dimensions across 5 grouped concerns)
4. Boundary intersections with locked features (12+ touched)
5. Critical Q1-Q10 for V1 minimum + V1+ extensibility
6. Reference materials slot for incoming user-provided sources

Pattern proven: RES_001 + IDF + FF_001 Phase 0 — concept-notes → reference survey → Q-deep-dive → DRAFT.

---

## Kernel touchpoints (anticipated; finalized at FAC_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on faction aggregate(s)
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types for faction membership delta events; EVT-T4 System sub-types for FactionBorn at canonical seed
- `_boundaries/01_feature_ownership_matrix.md` — faction + actor_faction_membership aggregates to be added at DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `faction.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for canonical_factions + canonical_faction_memberships
- `00_entity/EF_001_entity_foundation.md` — entity_binding consumed for actor + faction-as-entity (V1+ IF needed)
- `00_identity/IDF_004_origin.md` — origin pack may declare default sect (V1+ enrichment)
- `00_identity/IDF_005_ideology.md` IDL-D2 — sect membership = ideology-bound; FAC_001 RESOLVES this
- `00_family/FF_001_family_foundation.md` Q4 / FF-D6 / FF-D7 — RESOLVES sworn brotherhood + master-disciple
- `05_npc_systems/NPC_001_cast.md` — NPC faction membership declared at canonical seed
- `04_play_loop/PL_005_interaction.md` — V1+ Strike on rival-faction member triggers cascade opinion drift
- `02_world_authoring/WA_001_lex.md` — V1+ AxiomDecl.requires_faction hook for faction-gated abilities (Daoist-sect-only qigong)
- `02_world_authoring/WA_006_mortality.md` — sect-leader death triggers V1+ TIT_001 succession
- Future PCS_001 — PC creation form selects faction or unaffiliated
- Future TIT_001 Title Foundation — sect-leader title inheritance via FAC_001 + FF_001
- Future REP_001 Reputation Foundation — per-(actor, faction) reputation projection
- Future CULT_001 Cultivation Foundation — sect-bound cultivation method (V1+ wuxia)
- Future DIPL_001 Diplomacy Foundation — V1+ inter-faction relations / treaties / wars

---

## Naming convention

`FAC_<NNN>_<short_name>.md`. Sequence per-category. FAC_001 is the foundation; future FAC_NNN reserved for V1+/V2 extensions (faction-faction relations / sect cultivation method binding / WulinMeng martial alliance / cross-faction marriage politics).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

FAC_001 is **priority 5 post-IDF closure** per IDF folder closure roadmap (50d65fa). Resolves multiple V1+ deferrals:

- **FF-D5** (FF_001): Marriage as faction alliance currency → V1+ FAC_001 + V1+ DIPL_001
- **FF-D6** (FF_001): Sworn brotherhood → V1+ FAC_001 (NOT FF_001)
- **FF-D7** (FF_001): Master-disciple sect lineage → V1+ FAC_001 (NOT FF_001 per Q4 LOCKED)
- **IDL-D2** (IDF_005): Sect / order / giáo phái membership (faction system) → V1+ FAC_001

Boundary discipline (anticipated; locked at DRAFT):
- Faction = SECT / order / clan / guild (multi-actor social entity); membership has role + rank + ideology binding
- Master-disciple = sect role/rank within FAC_001 (NOT FF_001 family)
- Sworn brotherhood = bonded relationship within FAC_001 (NOT FF_001)
- Family-as-clan (CK3 dynasty + Bannerlord clan retinue) overlap: FF_001 owns blood; FAC_001 owns sect-as-faction membership; clan-of-blood-only is FF_001; clan-with-non-blood-retainers is FF_001 + FAC_001 join
- V1+ TIT_001 Title Foundation reads dynasty.current_head (from FF_001) + sect_leader_role (from FAC_001) for heir succession
- V1+ REP_001 Reputation Foundation = separate projection per-(actor, faction) reputation; FAC_001 V1 doesn't ship reputation (separation discipline)
- V1+ CULT_001 Cultivation Foundation V1+ binds cultivation method to sect_id (FAC_001); spirit-root inheritance via FF_001 graph
- V1+ DIPL_001 Diplomacy Foundation V2+ inter-faction relations / treaties / wars
