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
| IDF_001 | **Race** (RAC) | Race Foundation — closed-set enum per-reality (5-7 races); lifespan / size / mortality_kind override / Lex axiom hook. RealityManifest extension `races: Vec<RaceDecl>` REQUIRED V1. Cross-actor uniformity: same enum referenced by PC + NPC (no drift). | CONCEPT 2026-04-26 | [`IDF_001_race_concept.md`](IDF_001_race_concept.md) | ★ V1 essential |
| IDF_002 | **Language** (LNG) | Language Foundation — closed-set in-fiction language enum per-reality (3-5 languages); per-actor `actor_language_proficiency` aggregate (4-axis: read / write / speak / listen × 5 levels). A6 canon-drift detector consumes (SPIKE_01 turn 5 reproducibility gate). RealityManifest extension `languages: Vec<LanguageDecl>` REQUIRED V1. **Distinct from RES_001 `LangCode`** which is engine-wide ISO-639-1 for UI translation. | CONCEPT 2026-04-26 | [`IDF_002_language_concept.md`](IDF_002_language_concept.md) | ★ V1 essential |
| IDF_003 | **Personality** (PRS) | Personality Foundation — closed-set archetype enum (8-12 V1 archetypes: Stoic / Hothead / Cunning / Innocent / Pious / Cynic / Worldly / Idealist / etc.); per-actor `actor_personality` aggregate; voice register field intersect. NPC_002 §6 priority algorithm + opinion drift modifier consume. RealityManifest extension `personality_archetypes: Vec<PersonalityArchetypeDecl>` REQUIRED V1. | CONCEPT 2026-04-26 | [`IDF_003_personality_concept.md`](IDF_003_personality_concept.md) | ★ V1 essential |
| IDF_004 | **Origin** (ORG) | Origin Foundation — V1 minimal stub: per-actor `actor_origin` aggregate with `birthplace: ChannelId` + `lineage_id: Option<LineageId>` + `native_language: LanguageId` + `default_ideology_refs: Vec<IdeologyId>`. V1+ deep: family graph + cultural_tradition_pack + bloodline traits. RealityManifest extension `origin_packs: Vec<OriginPackDecl>` (V1+). | CONCEPT 2026-04-26 | [`IDF_004_origin_concept.md`](IDF_004_origin_concept.md) | V1+ stub V1 |
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

## Open questions (folder-level)

These cross-cutting questions need user confirmation BEFORE individual DRAFT promotion:

| ID | Question | Default proposal |
|---|---|---|
| **IDF-FOLDER-Q1** | Folder name: `00_identity/` (current proposal) vs `00_actor_substrate/`? | `00_identity/` — shorter, matches `IDF_*` prefix |
| **IDF-FOLDER-Q2** | 5 features (D-5) vs 4 features merging IDF_004 + IDF_005 (D-4)? | **5 features (D-5)** — Origin (immutable) and Ideology (mutable) have different lifecycles + Lex coupling differs |
| **IDF-FOLDER-Q3** | Should Voice register be its own feature (IDF_006) or stay intersect under IDF_003 Personality? | Stay under IDF_003 — voice is personality-coupled (Stoic actor speaks differently from Hothead); separate feature is over-design V1 |
| **IDF-FOLDER-Q4** | Should Skills/Abilities be IDF_006 V1+ or land elsewhere (combat feature)? | Land in V1+ combat feature, NOT IDF folder — abilities are reality-specific (qigong / firearm) and tightly coupled to Lex axioms; IDF stays at "demographic substrate" abstraction layer |
| **IDF-FOLDER-Q5** | Should Knowledge inventory (PCS_001 brief INT-D6 / knowledge_tags) be IDF_007 V1+ or stay PCS_001-internal? | Stay PCS_001-internal V1+ — knowledge accrual is PC-dynamic, not actor-static; NPC has separate `npc_session_memory` per NPC_001 | 
| **IDF-FOLDER-Q6** | Cross-reality race/language/ideology — what happens when PC moves between realities (Wuxia → Modern)? Does race get re-mapped, hidden, or rejected? | Defer to V2+ cross-reality contamination layer (per WA_002 Heresy); V1 PC bound to one reality |
| **IDF-FOLDER-Q7** | I18nBundle integration — apply to ALL existing features' Vietnamese hardcoded reject copy in same wave, or defer existing features audit? | **Defer existing features audit** per RES_001 §2.3 stance (low-priority cosmetic); IDF features ship I18nBundle from day 1 (greenfield) |

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
