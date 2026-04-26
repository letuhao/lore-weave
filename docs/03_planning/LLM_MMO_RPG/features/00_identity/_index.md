# 00_identity — Tier 5 Actor Substrate Foundation

> **Tier:** Foundation (Tier 5 — Actor Substrate). Sibling of `00_entity` / `00_place` / `00_map` / `00_cell_scene` / `00_resource`.
>
> **Purpose:** Define **shared PC+NPC concepts** that BOTH PCS_001 (V1+) and NPC_003 (V1+) consume without redefining. Avoids drift risk where two consumer features independently define `race` / `language` / `personality` / etc.
>
> **Pattern:** Mirrors `00_entity` (EF_001) — a foundation feature owns a closed-set enum + per-instance aggregate referenced by entire ecosystem. See [foundation tier discipline pattern](../00_entity/EF_001_entity_foundation.md).
>
> **Status (folder):** Phase 0 concept-notes 2026-04-26 — **all 5 features at CONCEPT stage**, awaiting user Q-decision approval before DRAFT promotion.

---

## Why this folder exists

PC and NPC share many architectural concepts that should be foundation-tier:

| Shared concept | PC (PCS_001) usage | NPC (NPC_001/003) usage |
|---|---|---|
| Race / Species | gates Lex axiom access (Cultivator → qigong); affects lifespan / mortality_kind | same — NPC race determines opinion drift modifiers + ability access |
| Language | A6 canon-drift detector (SPIKE_01 turn 5 literacy slip); Speak utterance.language field | NPC persona prompt includes language proficiency; multilingual NPC reactions |
| Personality archetype | NPC_002 priority filtering (knowledge_match + opinion); voice register | NPC_002 reaction filtering; opinion drift calibration per personality (PL_005c INT-INT-D5) |
| Origin / Culture | birthplace + native_language ref (V1+) | birthplace + lineage + faction (V1+) |
| Ideology / Religion | Lex axiom gate (Daoist → qigong access); convert events | Lex gate; sect/order membership (V1+ faction) |

**Without IDF foundation**: PCS_001 + NPC_001/003 would each define `race` / `language` / `personality` enum variants → drift risk → V1+ refactor pain.

**With IDF foundation**: 5 closed-set enums declared once at Tier 5; PCS + NPC consume by name with zero drift risk.

---

## Feature list

| ID | Conversational name | Title | Status | File | V1 priority |
|---|---|---|---|---|---|
| IDF_001 | **Race** (RAC) | Race Foundation — closed-set RaceId per-reality + race_assignment T2/Reality aggregate; 6-variant SizeCategory (Tiny/Small/Medium/Large/Huge/Gargantuan; Pathfinder 2e full); lifespan / mortality_kind override / V1+ Lex axiom hook. RealityManifest extension `races: Vec<RaceDecl>` REQUIRED V1. Cross-actor uniformity: same enum referenced by PC + NPC (no drift). 10 V1-testable AC + 3 V1+ deferred. RAC-D11: cultivation realm = SEPARATE V1+ CULT_001. | **CANDIDATE-LOCK** 2026-04-26 (Phase 3 + closure pass) | [`IDF_001_race.md`](IDF_001_race.md) | ★ V1 essential |
| IDF_002 | **Language** (LNG) | Language Foundation — closed-set in-fiction LanguageId per-reality + actor_language_proficiency T2/Reality aggregate (HashMap<LanguageId, ProficiencyMatrix> 4-axis × 5-level). 5-variant WritingSystem (None/Logographic/Alphabetic/Syllabary/Custom). SPIKE_01 turn 5 literacy slip canonical reproducibility gate. A6 canon-drift detector V1+ consumes at Stage 8. PL_005b Speak validator consumes at Stage 7. RealityManifest extension `languages: Vec<LanguageDecl>` REQUIRED V1. **Distinct from RES_001 `LangCode`** (in-fiction vs engine UI ISO-639-1; runtime newtype assert V1; LNG-D8 compile-time V1+). 10 V1-testable AC + 2 V1+ deferred. | **CANDIDATE-LOCK** 2026-04-26 (Phase 3 + closure pass) | [`IDF_002_language.md`](IDF_002_language.md) | ★ V1 essential |
| IDF_003 | **Personality** (PRS) | Personality Foundation — closed-set 12 V1 archetypes per-reality (POST-SURVEY-Q1 LOCKED: Stoic/Hothead/Cunning/Innocent/Pious/Cynic/Worldly/Idealist + Loyal/Aloof/Ambitious/Compassionate) + actor_personality T2/Reality aggregate; 5-variant VoiceRegister; opinion_modifier_table 12×12=144 entries. **Resolves PL_005b §2.1 speaker_voice orphan ref + PL_005c INT-INT-D5 per-personality opinion modifier**. NPC_002 §6 priority Tier 2-3 + opinion drift consume. RealityManifest extension `personality_archetypes: Vec<PersonalityArchetypeDecl>` REQUIRED V1. 10 V1-testable AC + 2 V1+ deferred. | **CANDIDATE-LOCK** 2026-04-26 (Phase 3 + closure pass) | [`IDF_003_personality.md`](IDF_003_personality.md) | ★ V1 essential |
| IDF_004 | **Origin** (ORG) | Origin Foundation — V1 minimal stub 4 fields (birthplace + lineage_id opaque + native_language + default_ideology_refs) per POST-SURVEY-Q4 LOCKED. **V1+ FF_001 Family Foundation HIGH priority post-IDF closure** (BEFORE PCS_001) per ORG-D12. OriginPackDecl V1+ enrichment (cultural_tradition_pack + naming convention + values + arts). RealityManifest extension `origin_packs: Vec<OriginPackDecl>` OPTIONAL V1. ORG-D11: birth event metadata V1+. 10 V1-testable AC + 3 V1+ deferred; 12 deferrals (ORG-D1..D12). | **CANDIDATE-LOCK** 2026-04-26 (Phase 3 + closure pass) | [`IDF_004_origin.md`](IDF_004_origin.md) | V1+ stub V1 |
| IDF_005 | **Ideology** (IDL) | Ideology Foundation — V1 minimal stub: closed-set `ideology` enum per-reality (e.g., Wuxia: Đạo / Phật / Nho / pure-martial / animism / atheist); per-actor `actor_ideology_stance: Vec<(IdeologyId, FervorLevel)>` (multi-stance V1). Lex axiom gate hook (`requires_ideology: Option<IdeologyId>` on AxiomDecl). V1+ deep: tenet system + sect/faction membership + ideology-conflict opinion drift. | CONCEPT 2026-04-26 | [`IDF_005_ideology_concept.md`](IDF_005_ideology_concept.md) | V1+ stub V1 |

**5 features total.** Folder closure pattern = 5 × (DRAFT + Phase 3 + closure pass) = ~15 commits when ready (post-CONCEPT user approval).

---

## Dependency chain (design order)

```
IDF_001 Race          (no deps; pure foundation)
    ↓
IDF_002 Language      (Race optional ref — race may have native language hint)
    ↓
IDF_003 Personality   (no hard deps; voice register intersect with PL_005b §2.1)
    ↓
IDF_004 Origin        (Race + Language refs; declares cultural pack proposing default ideologies)
    ↓
IDF_005 Ideology      (Origin ref for default suggestions; WA_001 Lex axiom gate hook)
    ↓
[ready for PCS_001 + NPC_003 consumers]
```

---

## i18n integration (cross-cutting per RES_001)

Per [RES_001 §2.3 I18nBundle contract](../00_resource/RES_001_resource_foundation.md), all user-facing display strings use the `I18nBundle` type (engine-wide):

```rust
pub struct I18nBundle {
    pub default: String,                          // English required
    pub translations: HashMap<LangCode, String>,  // ISO-639-1 ("vi", "zh", ...)
}
```

**Each IDF feature inherits this for declarative names:**
- `RaceDecl.display_name: I18nBundle` (e.g., default="Cultivator", translations: {"vi": "Tu sĩ", "zh": "修士"})
- `LanguageDecl.display_name: I18nBundle` (e.g., default="Mandarin", translations: {"vi": "Quan thoại"})
- `PersonalityArchetypeDecl.display_name: I18nBundle`
- `OriginPackDecl.display_name: I18nBundle`
- `IdeologyDecl.display_name: I18nBundle`

**Distinction from in-fiction LanguageId (IDF_002):**
- `LangCode` (RES_001) — engine-wide UI translation language code (ISO-639-1)
- `LanguageId` (IDF_002) — reality-specific in-fiction language stable-ID (e.g., "lang_quan_thoai", "lang_co_ngu") — independent of LangCode

These two concepts MUST NOT collide. IDF_002 design clarifies this in §2 domain concepts.

---

## V1 vs V1+ scope (locked early per "narrow V1, define NOW")

| Feature | V1 must-ship | V1+ deferred (declared upfront) |
|---|---|---|
| IDF_001 Race | Closed enum (5-7 races per reality preset); lifespan; size; mortality_kind override; Lex axiom hook | Race traits affecting combat / V1+ ability access; race-conflict opinion modifier; mixed-race lineage |
| IDF_002 Language | Closed enum (3-5 languages per reality); proficiency 4-axis × 5 levels per actor; A6 canon-drift consumes | Dialect/accent V1+; learning over time V1+; written-only languages (古文) V1+; sign language V2+ |
| IDF_003 Personality | 8-12 archetype closed enum; voice register field; NPC_002 priority hook | Big-Five trait vector V1+; archetype evolution V1+; per-personality opinion modifier (resolves PL_005c INT-INT-D5) |
| IDF_004 Origin | birthplace + lineage_id (opaque) + native_language ref + default ideology refs (read-only suggestions) | Family graph + cultural_tradition_pack + bloodline traits; per-culture naming convention; multi-cultural origin V2+ |
| IDF_005 Ideology | Ideology enum per-reality; multi-stance per actor with FervorLevel (5-level enum); Lex axiom-gate hook (`requires_ideology`); convert-event audit log | Tenet system V1+; sect/faction membership V1+; ideology-conflict opinion drift V1+; missionary mechanic V2+ |

---

## Open questions (folder-level) — LOCKED 2026-04-26 per market survey + user "A" confirmation

All 7 folder-level Q-decisions VALIDATED by [`_research_character_systems_market_survey.md`](_research_character_systems_market_survey.md) §9.6 + user confirmation. **Locked per survey defaults below.**

| ID | Question | Locked answer | Validation source |
|---|---|---|---|
| **IDF-FOLDER-Q1** | Folder name | ✅ **`00_identity/`** | shorter; matches `IDF_*` prefix |
| **IDF-FOLDER-Q2** | 5 features vs 4 (merge Origin+Ideology) | ✅ **5 features** | CK3 + Pathfinder 2e + VtM all explicitly separate culture from faith |
| **IDF-FOLDER-Q3** | Voice register own feature? | ✅ **Stay under IDF_003** | VtM Nature has voice; CK3 personality has speech pattern; couples to personality |
| **IDF-FOLDER-Q4** | Skills/Abilities = IDF_006? | ✅ **NO — V1+ combat feature** | Disco Elysium's skills-as-personality is novel but couples to combat too tightly |
| **IDF-FOLDER-Q5** | Knowledge inventory in IDF? | ✅ **NO — PCS_001 internal** | D&D knowledge proficiencies are class-based; matches PCS_001-internal V1+ scope |
| **IDF-FOLDER-Q6** | Cross-reality migration | ✅ **V2+ defer** | No mainstream game does cross-engine migration; per WA_002 Heresy |
| **IDF-FOLDER-Q7** | Existing-features i18n audit | ✅ **DEFER** | RES_001 §2.3 already locked this; IDF features ship I18nBundle from day 1 |

---

## Post-survey adjustments LOCKED 2026-04-26 (per `_research_character_systems_market_survey.md` §9 + §10)

User confirmed "A" on POST-SURVEY-Q1..Q7 — survey-informed adjustments locked into folder + per-feature concept-notes:

| Q | Adjustment | Files affected |
|---|---|---|
| **POST-SURVEY-Q1** | IDF_003 archetype count V1: 8 → **12** (add Loyal/Aloof/Ambitious/Compassionate — all wuxia-relevant universal archetypes) | IDF_003 §6 + §8 Q1 locked |
| **POST-SURVEY-Q2** | IDF_001 size categories: 4 → **6** (Tiny/Small/Medium/Large/Huge/Gargantuan; Pathfinder 2e full coverage) | IDF_001 §2 SizeCategory + §8 Q4 locked |
| **POST-SURVEY-Q3** | IDF_005 conversion cost V1: **Free V1**; cost mechanic deferred V1+ via NEW IDL-D11 | IDF_005 §8 Q3 locked + §9 NEW IDL-D11 deferral |
| **POST-SURVEY-Q4** | Family graph: V1 IDF_004 lineage_id **opaque only** (no parent/sibling refs); V1+ FF_001 Family Foundation = **first priority post-IDF closure** (before PCS_001) | IDF_004 §3.1 lineage_id contract + §8 Q4 locked + §9 NEW ORG-D11/D12 |
| **POST-SURVEY-Q5** | Cultivation realm: **V1+ separate CULT_001** confirmed (NOT in IDF_001) | IDF_001 §9 NEW RAC-D11 deferral signal |
| **POST-SURVEY-Q6** | Reputation: **V1+ separate REP_001** confirmed (NOT within FAC_001) | Folder-level V1+ roadmap (this _index.md) |
| **POST-SURVEY-Q7** | Voice register: **5 V1** (current); Eloquent + Hesitant V1+ as context modifiers (NOT archetype defaults) | IDF_003 §8 Q3 locked |

### V1+ feature roadmap (post-IDF closure — locked priority order)

```
IDF folder closure (5 features × ~3 commits) ~15 commits
    ↓
FF_001 Family Foundation         ★ NEW PRIORITY 1 (wuxia-critical; insertion before PCS_001)
    ↓
PCS_001 + NPC_003 (consume IDF + RES_001 + FF_001)
    ↓
FAC_001 Faction Foundation       ★ Priority 2 (sect / order / clan)
    ↓
REP_001 Reputation Foundation    ★ Priority 3 (per-(actor, faction) rep projection)
    ↓
CULT_001 Cultivation Foundation  ★ Wuxia-genre-specific (defer until first non-SPIKE_01 wuxia content)
    ↓
[V1+ second wave: DIPL_001 / SCH_001 / TIT_001 / WAR_001 / etc.]
```

**Society V1 ready** (PCS + NPC + FF + FAC + REP) = ~44 commits across 7-9 lock-cycles.

---

## Mandatory readings (before designing any IDF feature)

1. **Foundation tier discipline pattern** — [EF_001](../00_entity/EF_001_entity_foundation.md) ActorId/EntityId §5.1 (sibling-types pattern that IDF mirrors)
2. **PF_001** — RealityManifest extension pattern (per-reality `places: Vec<PlaceDecl>` shape)
3. **WA_001 Lex** — axiom gate consumers (IDF_001 Race + IDF_005 Ideology will hook here)
4. **PL_005b §2.1 InteractionSpeakPayload** — `speaker_voice: VoiceRegister` field (IDF_003 Personality intersect)
5. **NPC_002 §6** — priority algorithm Tier 1-4 (IDF_003 Personality consumed by Chorus)
6. **PL_005c §4 INT-INT-D5** — per-personality opinion modifier deferral that IDF_003 resolves
7. **RES_001 §2.3 I18nBundle** — engine-wide cross-cutting type for display strings
8. **SPIKE_01 turn 5** — literacy slip canonical (IDF_002 Language reproducibility gate)
9. **`_boundaries/01_feature_ownership_matrix.md`** — read aggregate ownership before claiming new aggregates
10. **`_boundaries/02_extension_contracts.md` §1.4** — RejectReason namespace ownership (IDF features get prefixes: `race.*` / `language.*` / `personality.*` / `origin.*` / `ideology.*`)

---

## Naming convention

`IDF_<NNN>_<short_name>_concept.md` for CONCEPT stage; rename to `IDF_<NNN>_<short_name>.md` on DRAFT promotion.

## How to promote CONCEPT → DRAFT

1. User reviews folder + 5 concept-notes; approves Q-decisions (folder + per-feature)
2. Lock-claim `_boundaries/_LOCK.md`
3. Per feature:
   - Rename `IDF_NNN_xxx_concept.md` → `IDF_NNN_xxx.md`
   - Promote header status CONCEPT → DRAFT
   - Lock all Q-decisions; add full §1-§19 spec (mirror EF/PF/MAP/CSC structure)
   - Register aggregate(s) in `01_feature_ownership_matrix.md`
   - Register namespace in `02_extension_contracts.md` §1.4 (e.g., `race.*` → IDF_001)
   - Register RealityManifest extension in `02_extension_contracts.md` §2
   - Append `99_changelog.md` row
4. Lock-release after all 5 features DRAFT (or per-feature if cycle prefers)
5. Each feature follows Phase 3 cleanup + closure pass cycle (mirror EF/PF/MAP/CSC pattern)

---

## Coordination note

IDF folder Phase 0 (this commit) creates **concept-notes only** — no boundary changes (no aggregate / namespace / RealityManifest registration). Boundary changes happen in CONCEPT → DRAFT promotion under lock-claim per per-feature DRAFT commit cadence.

This avoids lock contention with RES_001 ongoing work (user has `_LOCK.md` claimed for RES_001 DRAFT promotion as of this commit).
