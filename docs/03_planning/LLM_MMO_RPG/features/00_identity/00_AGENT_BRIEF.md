# 00_identity Agent Brief — IDF design ground rules

> **Audience:** Agent designing IDF_001 Race / IDF_002 Language / IDF_003 Personality / IDF_004 Origin / IDF_005 Ideology features.
>
> **Purpose:** Mandatory readings + design discipline learned from foundation tier 4/4 closure (EF/PF/MAP/CSC) + PL folder closure 2026-04-26. Apply uniformly to IDF features.

---

## Mandatory readings (in order)

### Tier 5 foundation pattern
1. [`EF_001 §5.1 ActorId / EntityId sibling types`](../00_entity/EF_001_entity_foundation.md) — sibling-type pattern that IDF inherits. ActorId is closed-set Pc/Npc/Synthetic; EntityId is closed-set Pc/Npc/Item/EnvObject. IDF_xxx aggregates are typically per-(reality, ActorId).
2. [`PF_001 §3.1 place aggregate`](../00_place/PF_001_place_foundation.md) — per-(reality, ChannelId) aggregate pattern; RealityManifest extension `places: Vec<PlaceDecl>` REQUIRED V1. IDF mirrors this for `races` / `languages` / `personality_archetypes` / `ideologies`.
3. [`MAP_001 §3.1 map_layout aggregate`](../00_map/MAP_001_map_foundation.md) — per-channel aggregate; closed-enum metadata + author-declared decl pattern.
4. [`CSC_001 architectural axiom CSC-A1`](../00_cell_scene/CSC_001_cell_scene_composition.md) — LLM scope discipline (categorical + creative tasks; deterministic engine for everything else). IDF features should NOT introduce LLM coupling at foundation tier.

### Cross-cutting i18n (RES_001)
5. [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md) — engine-wide display-string type. ALL IDF declarative names (race/language/personality/ideology display_name) USE I18nBundle from day 1 — greenfield, no legacy backfill.
6. **Distinction:** RES_001 `LangCode` (ISO-639-1 "en"/"vi"/"zh") is engine UI translation; IDF_002 `LanguageId` (e.g., "lang_quan_thoai") is in-fiction language stable-ID. They are SEPARATE types and MUST NOT collide.

### Lex axiom integration (IDF_001 Race + IDF_005 Ideology)
7. [`WA_001 Lex §3 axiom decl`](../02_world_authoring/WA_001_lex.md) — AxiomDecl is the gate point. IDF_001 + IDF_005 add OPTIONAL fields:
   - `requires_race: Option<Vec<RaceId>>` (if Some, axiom only available to actors of these races)
   - `requires_ideology: Option<Vec<IdeologyId>>` (if Some, axiom only available to actors with this ideology stance)
8. Stage 4 lex_check (per Stage 3.5 group + Stage 4 ordering) consumes axioms; Race + Ideology gates evaluated there.

### NPC_002 + opinion drift (IDF_003 Personality)
9. [`NPC_002 §6 priority algorithm`](../05_npc_systems/NPC_002_chorus.md) — Tier 1-4 priority filtering. IDF_003 PersonalityArchetype consumed at Tier 2 (opinion + relationship); per-personality opinion modifier resolves [PL_005c INT-INT-D5](../04_play_loop/PL_005c_interaction_integration.md) deferral.
10. [`PL_005b §2.1 InteractionSpeakPayload speaker_voice`](../04_play_loop/PL_005b_interaction_contracts.md) — voice register intersect with IDF_003.

### A6 canon-drift detector (IDF_002 Language)
11. [`SPIKE_01 turn 5`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — literacy slip canonical. LM01 body knows Quan thoại spoken but doesn't read 古文 / 道德经注; A6 detector flags this. IDF_002 `actor_language_proficiency` is the input.

### Boundary discipline
12. [`_boundaries/_LOCK.md`](../../_boundaries/_LOCK.md) — single-writer mutex; check OWNER before any boundary edit.
13. [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — Aggregate ownership SSOT; IDF features REGISTER their aggregates here on DRAFT promotion.
14. [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — RejectReason namespace; IDF features claim `race.*` / `language.*` / `personality.*` / `origin.*` / `ideology.*` prefixes.

### Closure pattern (mirror EF/PF/MAP/CSC)
15. **DRAFT** = full §1-§19 design with closed-enum + aggregate + Tier+scope + DP primitives + capability + subscribe + pattern choices + failure UX + cross-service handoff + sequences + V1 acceptance + deferrals + cross-refs + readiness checklist + boundary registrations
16. **Phase 3 cleanup** = Severity 1 (Rust correctness) + S2 (design gaps) + S3 (clarifications)
17. **Closure pass** = file status DRAFT → CANDIDATE-LOCK; matrix row updated; LOCK criterion split into DRAFT→CANDIDATE-LOCK vs CANDIDATE-LOCK→LOCK

---

## Design discipline (learned from EF/PF/MAP/CSC closure)

### Closed-set enum discipline (V1)
- All 5 IDF feature aggregates use **closed-set enums** at V1 (race / language / personality_archetype / ideology). V1+ extensions are ADDITIVE per I14 — new variants registered in boundary matrix.
- DO NOT introduce open-set / string-typed kinds. Every variant is a Rust enum constant declared in the feature design doc.

### Per-reality declaration via RealityManifest
- IDF_001 / IDF_002 / IDF_003 / IDF_005 add `Vec<XxxDecl>` to RealityManifest §2. Each reality declares which races / languages / archetypes / ideologies it contains — DIFFERENT realities have DIFFERENT closed-sets.
- Example: Wuxia reality declares races=[Human, Cultivator, Demon, Ghost, Beast]; Modern reality declares races=[Human]; Sci-fi declares races=[Human, AlienX, AlienY].
- IDF_004 Origin uses `origin_packs: Vec<OriginPackDecl>` (V1+ enrichment; V1 minimal stub only).

### V1 vs V1+ phasing (define NOW; ship V1 narrow)
Per user direction "tránh refactor lớn sau này":
- **V1 must-ship** = minimum viable substrate (covers SPIKE_01 + basic NPC reactions)
- **V1+ deferred** = enrichment declared upfront in §17 deferrals with concrete landing point
- Each feature's §17 deferrals MUST list V1+ items by ID (e.g., RAC-D1, LNG-D1, PRS-D1, ORG-D1, IDL-D1)

### Cross-actor uniformity
- Same aggregate covers PC + NPC. Future PCS_001 + NPC_003 query by `(reality_id, actor_id)` — no PC-only / NPC-only branching.
- Synthetic actors (ChorusOrchestrator / BubbleUpAggregator) MAY have IDF data (race=Synthetic / personality=neutral) — depends on per-feature semantics.

### Stage 3.5 validator integration
- IDF_001 Race + IDF_005 Ideology gate Lex axioms at Stage 4 (lex_check).
- IDF_002 Language gate canon-drift at Stage 8.
- IDF_003 Personality NOT a validator gate — purely consumed by NPC_002 priority + opinion drift modifier.
- IDF_004 Origin NOT a validator gate (V1) — read-only data.

### Source-of-truth uniformity
- ActorId source-of-truth = EF_001 §5.1 (already locked).
- IDF features' aggregates index by ActorId, NOT by EntityId or PcId/NpcId. Avoids drift with EF_001.

### I18nBundle for declarative names
- ALL display strings in `RaceDecl` / `LanguageDecl` / `PersonalityArchetypeDecl` / `OriginPackDecl` / `IdeologyDecl` use `I18nBundle` (default English + translations).
- Internal stable-IDs (RaceId, LanguageId, etc.) are language-neutral opaque strings (e.g., `race_cultivator`, `lang_quan_thoai`, `personality_stoic`, `ideology_dao`).

---

## Common anti-patterns (from prior feature closures)

1. **Don't define ActorId locally.** Always reference EF_001 §5.1.
2. **Don't add LLM coupling at foundation.** IDF aggregates are deterministic engine state. (LLM consumers like NPC_002 read IDF state, never write.)
3. **Don't conflate LangCode with LanguageId.** First is engine UI translation (RES_001); second is in-fiction language (IDF_002).
4. **Don't bake co-occurrence rules into envelope schema.** "If race=Cultivator then access qigong axiom" is a SEMANTIC rule (Lex axiom check at Stage 4), not a schema rule.
5. **Don't introduce open-set kinds.** Closed enum + V1+ additive only.
6. **Don't allocate `xxx.target_dead` rule_ids.** Per Stage 3.5.a entity_affordance allocation pattern, target_dead is `entity.lifecycle_dead` — never duplicate in feature namespace.

---

## Phase 0 → DRAFT → CANDIDATE-LOCK → LOCK transitions

```
[CONCEPT 2026-04-26]              ← this Phase 0 commit
        ↓ user approves Q-decisions
[DRAFT 2026-XX-XX]                ← full §1-§19 spec; lock-claim; boundary register
        ↓ Phase 3 cleanup
[DRAFT + Phase 3 applied]         ← Severity 1+2+3 fixes
        ↓ closure pass
[CANDIDATE-LOCK 2026-XX-XX]       ← matrix updated; LOCK criterion split
        ↓ V1 acceptance scenarios pass integration tests
[LOCK 2026-XX-XX]                 ← V1 implementation deployed; tests green
```

Each transition triggers a `_boundaries/99_changelog.md` entry.
