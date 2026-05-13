# 00_family — Index

> **Category:** FF — Family Foundation (foundation tier candidate post-IDF closure; HIGH priority per IDF_004 ORG-D12 + POST-SURVEY-Q4)
> **Catalog reference:** `catalog/cat_00_FF_family_foundation.md` (NOT YET CREATED — defer to FF_001 DRAFT promotion)
> **Purpose:** The substrate for **biological/adoption family graph + dynasty + family events** that resolves IDF_004 lineage_id opaque tag. Wuxia critical (sect lineage / family inheritance / dynasty politics). Mirrors CK3 dynasty + Bannerlord clan + Total War 3K family + VtM clan-as-family pattern.

**Active:** FF_001 — **Family Foundation** (CANDIDATE-LOCK 2026-04-26 — 4-commit cycle complete: Q-lock 2db3fc2 + DRAFT 2ffd9b1 + Phase 3 7df5045 + closure 4/4 this commit)

**Folder closure status:** **COMPLETE 2026-04-26** — FF_001 at CANDIDATE-LOCK. Folder ready. Resolves IDF_004 ORG-D12 lineage_id opaque tag. Next post-IDF priority: PCS_001 PC substrate (consumes IDF + RES_001 + FF_001).

**V1+ priority signal (per IDF folder closure):**
> POST-SURVEY-Q4 LOCKED + IDF_004 ORG-D12: **FF_001 Family Foundation = HIGH priority post-IDF closure (BEFORE PCS_001).** Wuxia content REQUIRES family graph (sect lineage / family inheritance / dynasty politics).

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — FF_001 brainstorm capture | CONCEPT 2026-04-26 — captures user framing (wuxia priority + IDF_004 lineage_id resolution) + 12-dimension gap analysis + 8 critical Q1-Q8 + cross-feature integration table | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — reference games survey | DRAFT 2026-04-26 — CK3 dynasty system + Bannerlord clan + Total War 3K family + xianxia sect lineage + D&D background + VtM clan-as-family + Stellaris ruler succession + Pillars of Eternity tabletop precedent | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit) |
| FF_001 | **Family Foundation** (FF) | Per-actor family graph (parent/sibling/spouse/child explicit V1 + extended computed V1+) + Dynasty (sparse storage; multi-generational house) + 5 V1 family events (1 EVT-T4 FamilyBorn + 4 EVT-T3 Derived: AddSpouse + MarkDeceased + V1+ AddChild/RemoveSpouse/AddAdoptedParent). Resolves IDF_004 lineage_id opaque tag per ORG-D12. 6-variant RelationKind enum (adoption flag per Q6). Boundary discipline: FF_001 = biological + adoption only; V1+ FAC_001 owns sect/master-disciple/sworn (per Q4). 10 V1-testable AC + 4 V1+ deferred. 12 deferrals (FF-D1..D12). | **CANDIDATE-LOCK** 2026-04-26 (4-commit cycle complete) | [`FF_001_family_foundation.md`](FF_001_family_foundation.md) | 2db3fc2 → 2ffd9b1 → 7df5045 → 4/4 this commit |

---

## Why this folder is concept-first

User direction 2026-04-26 ("đi sâu vào các tính năng liên quan tới background của PC/NPC trước đi"): deep-dive PC/NPC background features. Family is core background — wuxia narrative without sect lineage / family dynasty is incomplete. FF_001 IS the natural next priority after IDF closure.

But — family system is broad (CK3 has 60+ trait family interactions). V1 scope must be narrow per "narrow V1 + define NOW for V+" philosophy. Concept-notes phase captures:

1. User's framing (wuxia critical + IDF_004 lineage_id resolution + ORG-D12 priority signal)
2. Worked examples from references (CK3 + Bannerlord + xianxia)
3. Gap analysis (12 dimensions across 5 grouped concerns)
4. Boundary intersections with locked features (8+ touched)
5. Critical Q1-Q8 for V1 minimum + V1+ extensibility
6. Reference materials slot for incoming user-provided sources

Pattern proven: RES_001 + IDF folder Phase 0. Same approach.

---

## Kernel touchpoints (anticipated; finalized at FF_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on family aggregate(s)
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types for family delta events; possibly EVT-T4 System sub-types for Birth/Marriage/Death/Divorce/Adoption
- `_boundaries/01_feature_ownership_matrix.md` — family_node / dynasty / family_event_log aggregates to be added at FF_001 DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `family.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for canonical_dynasties + canonical_family_relations
- `00_entity/EF_001_entity_foundation.md` — entity_binding consumed for actor identification
- `00_identity/IDF_004_origin.md` — lineage_id opaque tag resolved by FF_001 graph attachment
- `00_identity/IDF_001_race.md` — V1+ hybrid races (RAC-D3) consume FF_001 lineage for race inheritance
- `00_identity/IDF_005_ideology.md` — family-default ideology pack (V1+ inherited from parent)
- `05_npc_systems/NPC_001_cast.md` — NPC family declared at canonical seed
- `04_play_loop/PL_005_interaction.md` — family-driven Strike opinion drift (kill someone's child → faction-wide opinion penalty)
- `02_world_authoring/WA_006_mortality.md` — death events propagate to family graph (orphan + heir notification)
- `00_resource/RES_001_resource_foundation.md` — V2+ family-shared inventory (e.g., clan treasury)
- Future PCS_001 — PC creation form selects family / generates orphan / ties to canonical dynasty
- Future FAC_001 Faction Foundation — sect membership often family-bound (clan = small faction); master-disciple is QUASI-family but lives in FAC_001 (separation discipline)
- Future TIT_001 Title Foundation — title inheritance rules through FF_001 family graph

---

## Naming convention

`FF_<NNN>_<short_name>.md`. Sequence per-category. FF_001 is the foundation; future FF_NNN reserved for V1+/V2 extensions (lineage trait inheritance / dynasty conflict mechanics / cross-reality family migration).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

FF_001 is **first priority post-IDF closure** per:
- IDF_004 ORG-D12 (HIGH; before PCS_001)
- IDF folder _index.md V1+ roadmap (priority 1 post-IDF)
- POST-SURVEY-Q4 LOCKED (V1 IDF_004 lineage_id opaque only; V1+ FF_001 resolves)
- _research_character_systems_market_survey.md §5.5 (every grand-strategy game tracks family)

Boundary discipline (anticipated; locked at DRAFT):
- Biological + adoption family stays in FF_001 (parent/sibling/spouse/child relations)
- Sect lineage (master-disciple) stays in V1+ FAC_001 Faction Foundation (rank/role within sect)
- Title inheritance stays in V1+ TIT_001 (consumes FF_001 graph for heir selection)
- Race-driven hybrid bloodline stays V1+ in IDF_001 RAC-D3 (consumes FF_001 lineage)
- Per-PC identity stays in PCS_001 (FF_001 references ActorId; doesn't redefine identity)
- Per-NPC family stays in NPC_001 canonical actor decl (FF_001 reads from there at canonical seed)

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) currently has no family field — PC creation form will need V1+ family selection / generation flow when FF_001 + PCS_001 both ship.

IDF_004 ORG-D12 explicitly named FF_001 as resolver for opaque lineage_id tag — first concrete consumer.
