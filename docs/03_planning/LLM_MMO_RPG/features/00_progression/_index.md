# 00_progression — Index

> **Category:** PROG — Progression Foundation (foundation tier candidate; 6th foundation feature alongside EF_001 / PF_001 / MAP_001 / CSC_001 / RES_001)
> **Catalog reference:** `catalog/cat_00_PROG_progression.md` (NOT YET CREATED — defer to PROG_001 DRAFT promotion)
> **Purpose:** The substrate for **dynamic per-reality attribute + skill + stage/cultivation systems**. Defines what counts as a progressable numeric/tiered value owned by an actor, how it grows (training mechanisms), how it caps, and how it integrates with combat/dialogue/LLM context. Author-configurable schema per reality enables modern social-life game / tu tiên cultivation / traditional RPG / sandbox-no-progression — all from same engine substrate.

**Active:** (empty — folder closure 2026-04-27)

**Folder closure status:** **COMPLETE 2026-04-27** — PROG_001 **CANDIDATE-LOCK 2026-04-27** (DRAFT 2026-04-26 → 5 NEW deferrals D33..D37 cross-cultivation extensibility audit b20c4dcb → CULT_001 V2+ deferred d57fb7fc → TDIL closure-pass-extension Q3f day-boundary → turn-boundary applied at TDIL DRAFT bdc8d8e1 → CANDIDATE-LOCK closure pass single combined `[boundaries-lock-claim+release]` commit). All 7 critical scope questions LOCKED via 6-batch deep-dive (Q1+Q6 / Q2 / Q3 / Q4+Q5 batched / Q4+Q5 REVISED quantum-observation / Q7). 26 V1 catalog entries PROG-1..PROG-26 + 5 V1+30d (PROG-27..PROG-31) + 6 V2/V3+ (PROG-32..PROG-37) = 37 total + PROG-38..PROG-42 cross-cultivation extensibility deferrals. 7 axioms PROG-A1..A7 (per-reality schema / no-level-no-chiến-lực / unified ProgressionKind ontology / quantum-observation NPC model / BodyOrSoul discriminator / hybrid combat damage / English IDs + I18nBundle). 7 V1 reject rule_ids in `progression.*` namespace + 6 V1+ reservations. 4 RealityManifest extensions OPTIONAL V1. 12 V1-testable acceptance scenarios. PROG-Q1..Q5 deferred to consumer feature closures (PCS_001+NPC_001 first-design-pass / V1 default eager + V1+30d offline mode / V1 BodyOrSoul auto + V1+30d author mapping / i18n cross-cutting commit / future AI Tier ownership).

**Foundation tier 6/6 COMPLETE** — PROG_001 was the 6th and final V1 foundation feature; with CANDIDATE-LOCK 2026-04-27, the foundation tier closure status: EF + PF + MAP + CSC + RES + PROG all CANDIDATE-LOCK. PROG_001 V1 substrate proven cross-cultivation-extensible via PROG-D33..D37 audit (11-cultivation-system survey: Cầu Ma + Tiên Nghịch + Mo Dao Zu Shi 魔修 + Lifespan-burning + Mị ma song tu + đa phúc đa tử family + Rebirth of God Emperor + Heart demon 心魔 + Đấu Phá pet bond + 御剑 sword spirit + kiếm hiệp neigong-waigong) — verified 3 NATIVELY V1, 3 already-reserved (PROG-D2 + Q6b Item ActorRef + PROG-D10 ActorClassMatch), 5 require NEW deferrals D33..D37 (all schema-additive per I14; zero PROG_001 redesign needed for ANY per-reality cultivation system).

**LOCK target after** acceptance scenarios pass integration tests + V1+ PROG-D1..D5 ship + cross-cultivation scenarios validated.

**Foundation tier discipline note:** This is **revisit of "foundation tier 5/5 ĐỦ V1" claim** made earlier 2026-04-26. After deeper discussion of progression mechanics (user clarified 2026-04-26 that LoreWeave is simulation/strategy with multiple dynamic progression systems, not level-based RPG), progression IS legitimately a 6th substrate feature — not a domain feature. Every actor in every reality has progression dimensions; without PROG_001, DF7 PC Stats placeholder cannot be made concrete + LLM cannot reason about NPC capability.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — PROG_001 brainstorm capture | CONCEPT 2026-04-26 — captures user core framing + 14-dimension gap analysis + Q1-Q7 critical scope questions; awaits user reference materials | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — reference games survey | NOT YET STARTED — awaits user-provided reference materials before main session adds engine-known references | (TBD) | — |
| PROG_001 | **Progression Foundation** (PROG) | Multi-genre dynamic progression substrate. Owns 1 NEW T2/Reality aggregate `actor_progression` (owner=Actor V1; Item V1+30d reserved; tracking_tier reserved for future AI Tier feature). Owns 3 V1 ProgressionType variants (Attribute/Skill/Stage; ResourceBound V1+30d) + BodyOrSoul discriminator (xuyên không cross-reality stat translation; Body default) + 3 V1 curves (Linear/Log/Stage flat tier list with breakthrough; per-tier WithinTierCurve override) + 4 V1 CapRules (SoftCap/HardCap/TierBased/Unbounded) + Q2j validity matrix. Owns 2 V1 training sources (Action via PL_005 cascade hot-path + Time via day-boundary `Scheduled:CultivationTick` Generator sequenced 5th after RES_001 4) + 3 V1 TrainingConditions (LocationMatch + StatusRequired + StatusForbidden). **Hybrid observation-driven NPC model (Q4 REVISED)**: PCs eager Generator + Tracked NPCs lazy materialization on observation + Untracked NPCs = no aggregate (future AI Tier feature owns; Schrödinger pattern; solves billion-NPC scaling). Hybrid combat damage Q7: LLM proposes within engine bounds derived from offense/defense stat sums; silent clamp; full chaos-backend law chain V1+ DF7-equivalent. NO atrophy V1 (V1+ lazy at materialization). 4 RealityManifest extensions (progression_kinds + class_defaults + actor_overrides + strike_formula) all OPTIONAL V1. Empty default = sandbox/freeplay valid. 12 V1 acceptance scenarios AC-PROG-1..12 + 30+ deferrals (PROG-D1..D32) + 6 open questions PROG-Q1..Q6. **DF7 PC Stats placeholder SUPERSEDED at DRAFT** (DF7-V1+ becomes "Combat Damage Formulas Full" sub-feature reading PROG_001 ProgressionInstance per chaos-backend law chain). Foundation tier 6/6 COMPLETE 2026-04-26 (closes V1 substrate). | **DRAFT 2026-04-26** | [`PROG_001_progression_foundation.md`](PROG_001_progression_foundation.md) | (this commit) |

---

## Why this folder is concept-first

User raised progression system 2026-04-26 with clear genre framing (modern social / tu tiên / traditional RPG) but explicit acknowledgment that "không hề đơn giản" (not simple to design due to required generality). User stated they have prepared the idea for a long time + will provide reference materials.

Before drafting PROG_001, capture:
1. User's core framing + worked examples (§1, §2 in CONCEPT_NOTES)
2. Gap analysis (14 dimensions surfaced by initial discussion — §3)
3. Boundary intersections with locked features (§4)
4. Critical scope questions (Q1-Q7 in §5) for V1 minimum + V1+/V2 extensibility
5. Reference materials slot for incoming user-provided sources (§6)

This mirrors the discipline established by RES_001 Resource Foundation (2026-04-26 commit `2516107`) — concept-notes + reference-games-survey + Q-deep-dive + DRAFT promotion. Pattern proven; same approach applies.

---

## Kernel touchpoints (anticipated; finalized at PROG_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on progression aggregate(s)
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types for progression deltas; EVT-T5 Generated for time-driven training tick
- `_boundaries/01_feature_ownership_matrix.md` — progression aggregate(s) to be added at PROG_001 DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `progression.*` rule_id namespace to be added
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for attribute/skill/stage schema declarations
- `00_entity/EF_001_entity_foundation.md` — entity_binding consumed for actor identification
- `00_resource/RES_001_resource_foundation.md` — Vital pool referenced for HP/Stamina (those are RES not PROG); cultivation-elixir Consumable kind feeds PROG progression
- `06_pc_systems/PCS_001` (when designed) — PC stats stub will reference PROG_001 schema; per-PC values in progression aggregate
- `05_npc_systems/NPC_001 Cast` — NPC progression schema (depends on Q5: NPC train or static?)
- `04_play_loop/PL_005 Interaction` — action-driven training (Use kind on tool/skill); skill/attribute checks at validator stage
- `04_play_loop/PL_006 Status Effects` — temporary stat modifiers (Drunk reduces alchemy skill?)

---

## Naming convention

`PROG_<NNN>_<short_name>.md`. Sequence per-category. PROG_001 is the foundation; future PROG_NNN reserved for V1+/V2 extensions (combat damage formulas / mentor system / cultivation method declarations / cross-reality stat translation rules).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

PROG_001 is the **6th and final V1 foundation feature** (revising prior "5/5 ĐỦ V1" claim). Foundation tier covers:
- WHO (EF_001 Entity Foundation)
- WHERE-semantic (PF_001 Place Foundation)
- WHERE-graph (MAP_001 Map Foundation)
- WHAT-inside-cell (CSC_001 Cell Scene Composition)
- WHAT-flows-through-entity (RES_001 Resource Foundation)
- **HOW-actors-grow (PROG_001 Progression Foundation — this folder)**

Boundary discipline (anticipated; locked at DRAFT):
- Numeric attribute/skill values + training rules + caps + curves stay in PROG_001
- Vital pools (HP/Stamina/Mana) stay in RES_001 (transient state, not progression)
- Status modifiers (Drunk/Wounded) stay in PL_006 (temporary boolean/categorical)
- Combat damage formulas stay in DF7 PC Stats V1+ (consume PROG attribute/skill values)
- Per-PC identity stays in PCS_001 (PROG references PcId; doesn't redefine)
- Per-NPC identity stays in NPC_001 (PROG references NpcId; doesn't redefine)
- Action-driven training trigger stays in PL_005 (PROG declares trainable; PL_005 cascades emit progression delta event)

PCS_001 brief at [`../06_pc_systems/00_AGENT_BRIEF.md`](../06_pc_systems/00_AGENT_BRIEF.md) §S5 currently has `pc_stats_v1_stub` — this WILL be superseded by PROG_001 when DRAFT lands. PCS_001 brief update scheduled at PROG_001 CANDIDATE-LOCK.
