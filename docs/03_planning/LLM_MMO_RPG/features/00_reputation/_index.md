# 00_reputation — Index

> **Category:** REP — Reputation Foundation (foundation tier candidate post-FAC_001)
> **Catalog reference:** `catalog/cat_00_REP_reputation_foundation.md` (NOT YET CREATED — defer to REP_001 DRAFT promotion)
> **Purpose:** The substrate for **per-(actor, faction) reputation** — captures one actor's *standing with a specific faction* (group). Distinct from NPC_001 NpcOpinion (per-(NPC, PC) personal feeling) and from RES_001 SocialCurrency::Reputation (per-actor *global* scalar — wuxia "danh tiếng"). Resolves FAC-D7 from FAC_001 (per-(actor, faction) reputation projection deferred). Wuxia critical (sect standing / Wulin reputation per sect / "thanh dự" tier-by-faction). D&D faction reputation pattern primary.

**Active:** REP_001 — **Reputation Foundation** (CONCEPT 2026-04-26 — Phase 0 brainstorm capture)

**Folder closure status:** **OPEN** — Phase 0 in progress (concept-notes + reference survey). Awaits user Q-deep-dive + DRAFT cycle. Resolves FAC-D7.

**V1+ priority signal:**
- FAC_001 FAC-D7 LOCKED: "Per-(actor, faction) reputation projection → V1+ REP_001 Reputation Foundation separate aggregate"
- FAC_001 _index.md: "Future REP_001 Reputation Foundation — per-(actor, faction) reputation projection"
- FAC_001 §1: "V1+ REP_001 = per-(actor, faction) reputation projection (separated)"
- 15_organization V2 RESERVATION: "individual NPC reputation only V1 (RES_001 SocialCurrency); faction-tier reputation is REP_001"
- IDF folder closure roadmap (50d65fa): "REP_001 = priority 6 post-IDF closure" (after FAC_001)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (concept) | **00_CONCEPT_NOTES.md** — REP_001 brainstorm capture | CONCEPT 2026-04-26 — captures user framing (post-FAC_001 priority + 3-layer separation discipline against NPC_001 opinion + RES_001 SocialCurrency) + 10-dimension gap analysis + Q1-Q10 critical scope questions | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — reference games survey | DRAFT 2026-04-26 — D&D 5e Faction Reputation (6-tier) primary + WoW (8-tier Hated→Exalted) + Fallout: NV (7-tier Vilified→Idolized) + Skyrim (per-hold bounty + faction questline rep) + CK3 (Prestige + Piety + Renown multi-axis) + Bannerlord (Renown) + Sands of Salzaar / Path of Wuxia (sect reputation) + EU4 (estate reputation) + Stellaris (empire-empire opinion) | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit) |
| REP_001 | **Reputation Foundation** (REP) | Per-(actor, faction) reputation projection — separate aggregate from FAC_001 actor_faction_membership. Engine-fixed bounded score range (proposed [-1000, +1000]). Tier mapping for display (Hated/Hostile/Unfriendly/Neutral/Friendly/Honored/Revered/Exalted; D&D + WoW pattern). V1 ships canonical seed only; V1+ runtime events. Resolves FAC-D7. | (DRAFT pending Q-deep-dive) | (defer) | (defer) |

---

## Why this folder is concept-first

User direction 2026-04-26 picked REP_001 as next deep-dive (post-FAC_001 closure). Reputation is THE missing piece between FAC_001 (membership) and downstream V1+ social mechanics (rival-sect Tier 4 priority modifier in NPC_002; sect-quest gating; trade discounts per faction standing).

But — reputation system is wide. Three competing patterns in market:
1. **Tier-based** (D&D 5e / WoW / Fallout: NV) — discrete buckets with engine-fixed thresholds; gameplay gates per tier
2. **Continuous score** (CK3 Prestige / Bannerlord Renown) — raw numeric; UI shows label but mechanics use score
3. **Multi-axis** (CK3 separates Prestige/Piety/Renown) — different axes for different reputation kinds

V1 scope must be narrow. Concept-notes phase captures:

1. User framing (post-FAC_001 priority + boundary discipline against NPC_001 opinion + RES_001 SocialCurrency)
2. Worked examples (Wuxia 5-sect rep / Modern police-vs-criminal-org / D&D faction questline)
3. Gap analysis (10 dimensions across 4 grouped concerns)
4. Boundary intersections with locked features (10+ touched)
5. Critical Q1-Q10 for V1 minimum + V1+ extensibility
6. Reference materials slot for incoming user-provided sources

Pattern proven: RES_001 + IDF + FF_001 + FAC_001 Phase 0 — concept-notes → reference survey → Q-deep-dive → DRAFT.

---

## Kernel touchpoints (anticipated; finalized at REP_001 DRAFT)

- `06_data_plane/02_invariants.md` — DP-A14 scope/tier annotations on actor_faction_reputation aggregate
- `07_event_model/03_event_taxonomy.md` — EVT-T3 Derived sub-types for reputation delta events; EVT-T4 System sub-types for ReputationBorn at canonical seed
- `_boundaries/01_feature_ownership_matrix.md` — actor_faction_reputation aggregate added at DRAFT
- `_boundaries/02_extension_contracts.md` §1.4 — `reputation.*` rule_id namespace
- `_boundaries/02_extension_contracts.md` §2 — RealityManifest extension for canonical_actor_faction_reputations
- `00_entity/EF_001_entity_foundation.md` — ActorId source-of-truth consumed
- `00_faction/FAC_001_faction_foundation.md` FAC-D7 — REP_001 RESOLVES (separate aggregate per-(actor, faction))
- `00_resource/RES_001_resource_foundation.md` SocialCurrency::Reputation — DISTINCT from REP_001; RES is per-actor global scalar, REP is per-(actor, faction)
- `05_npc_systems/NPC_001_cast.md` `npc_pc_relationship_projection` — DISTINCT from REP_001; NPC is per-(NPC, PC), REP is per-(actor, faction)
- `05_npc_systems/NPC_002_chorus.md` Tier 4 priority — V1+ rival-faction NPCs read REP_001 for opinion baseline
- `04_play_loop/PL_005_interaction.md` — V1+ Strike on faction member → REP_001 reputation drift event
- `02_world_authoring/WA_001_lex.md` — V1+ AxiomDecl.requires_reputation hook (faction-gated abilities require min rep)
- `02_world_authoring/WA_006_mortality.md` — sect-leader death event consumed by REP_001 (sect-collapse rep cascade V1+)
- Future PCS_001 — PC creation form may set initial rep with chosen faction (default 0 V1)
- Future TIT_001 Title Foundation — V1+ title-grant requires min rep with faction
- Future CULT_001 Cultivation Foundation — V1+ sect cultivation method requires min rep
- Future DIPL_001 Diplomacy Foundation — V1+ inter-faction war affects member rep with rival
- Future quest features (V2+ 13_quests) — quest reward = rep change with faction

---

## Naming convention

`REP_<NNN>_<short_name>.md`. Sequence per-category. REP_001 is the foundation; future REP_NNN reserved for V1+/V2 extensions (rep decay over time / cross-faction cascade / rep-driven trade discount system).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

REP_001 is **priority 6 post-IDF closure** per IDF folder closure roadmap (50d65fa). Resolves single V1+ deferral:

- **FAC-D7** (FAC_001): Per-(actor, faction) reputation projection → V1+ REP_001 (separate aggregate)

**3-layer separation discipline (CRITICAL — must hold post-DRAFT):**

| Layer | Owner | Shape | Use case |
|---|---|---|---|
| **NPC personal opinion** | NPC_001 `npc_pc_relationship_projection` | per-(NPC, PC) — trust + familiarity + stance_tags | Du sĩ's specific feeling toward Lý Minh after meta-knowledge moment |
| **Actor global reputation** | RES_001 `resource_inventory` SocialCurrency::Reputation | per-actor scalar — sum-style "danh tiếng" | Lý Minh's overall wuxia world reputation |
| **Actor-faction standing** | REP_001 `actor_faction_reputation` (proposed) | per-(actor, faction) — bounded score + tier label | Lý Minh's standing with Đông Hải Đạo Cốc specifically |

These three layers are COMPLEMENTARY not duplicative. NPC_002 Chorus consumes ALL THREE for priority/reaction:
- Tier 2: high opinion NPCs prioritize (NPC_001)
- Tier 4: rival-faction NPCs Tier 4 modifier (REP_001 V1+)
- Tier 5: famous actors (high SocialCurrency::Reputation) get NPC_002 attention (RES_001 V1+)

Boundary discipline (anticipated; locked at DRAFT):
- REP_001 V1 = per-(actor, faction) bounded score; sparse storage; canonical seed events V1; runtime events V1+
- REP_001 V1+ = decay over time + cascade rep (rival's enemy = bonus) + cross-actor influence (high-rep actor's friends boost rep cascade)
- V1+ DIPL_001 Diplomacy Foundation V2+ inter-faction war affects member rep automatic
- V2+ Heresy cross-reality rep migration (V2+ WA_002)
- Cross-feature: NPC_002 V1+ Tier 4 priority modifier reads REP_001
- Cross-feature: PL_005 V1+ Strike on faction member triggers rep delta (cascade per faction membership)
- Cross-feature: WA_001 V1+ AxiomDecl.requires_reputation gating (sect ability requires Honored+ rep)
- Synthetic actors forbidden V1 (consistent with IDF + FF + FAC discipline)
