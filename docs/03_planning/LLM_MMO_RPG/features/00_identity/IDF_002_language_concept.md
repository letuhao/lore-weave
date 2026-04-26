# IDF_002 — Language Foundation (CONCEPT)

> **Conversational name:** "Language" (LNG). Tier 5 Actor Substrate Foundation feature owning the per-reality `LanguageId` closed-set (in-fiction languages — Quan thoại / Cổ ngữ / Tiếng Anh / Common Tongue / etc.) + per-actor `actor_language_proficiency` aggregate (4-axis read/write/speak/listen × 5-level proficiency). A6 canon-drift detector consumes (SPIKE_01 turn 5 literacy slip canonical reproducibility gate).
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** CONCEPT 2026-04-26
> **Stable IDs:** `LNG-A*` axioms · `LNG-D*` deferrals · `LNG-Q*` open questions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md); [SPIKE_01 turn 5 literacy slip](../_spikes/SPIKE_01_two_sessions_reality_time.md); [05_llm_safety A6 canon-drift detector](../../05_llm_safety/) (V1+ when designed); [PL_005b §2.1 InteractionSpeakPayload.language](../04_play_loop/PL_005b_interaction_contracts.md); [RES_001 §2.3 I18nBundle + LangCode](../00_resource/RES_001_resource_foundation.md).
> **Defers to:** PCS_001 (PC language proficiency at creation); NPC_001/003 (NPC language declared at canonical seed); 05_llm_safety A6 (canon-drift literacy mismatch detector V1+); V1+ dialect/accent feature.

---

## §1 Concept summary

Every actor (PC + NPC) has language proficiency across reality's declared in-fiction languages. The 4-axis × 5-level structure is critical for **A6 canon-drift detection** — SPIKE_01 turn 5 establishes that a speaker's body-knowledge of language(s) gates what they can canonically quote/read.

**V1 must-ship:**
- Closed-set `LanguageId` per reality (3-5 languages typical; reality-specific stable-IDs)
- Per-actor `actor_language_proficiency` aggregate with 4-axis × 5-level matrix
- `LanguageDecl` declarative metadata: display_name (I18nBundle), writing_system, default_in_culture (Vec<OriginPackId>), canon_ref
- A6 canon-drift consumption hook (V1+ when 05_llm_safety A6 designed)
- Speak utterance.language field validation (rejects when speaker proficiency < threshold)
- RealityManifest extension `languages: Vec<LanguageDecl>` REQUIRED V1
- Reality presets:
  - **Wuxia/Tiên Hiệp** (4 languages): Quan thoại (spoken Mandarin) / Cổ ngữ (classical written Chinese — read/write only) / Tiếng địa phương (regional dialects) / Đạo ngôn (esoteric Daoist canon — V1+ Cultivator-only)
  - **Modern**: Tiếng Việt / Tiếng Anh / Tiếng Trung
  - **Sci-fi**: Common Tongue / AlienXLanguage / AlienYLanguage

**V1+ deferred:**
- Dialect/accent (LNG-D1)
- Learning over time (LNG-D2)
- Written-only languages full support (LNG-D3 — V1 partial)
- Sign language (LNG-D4 — V2+)
- Telepathic / mental languages (V2+)
- Multi-language concurrent speech (code-switching) (V1+)

**Critical distinction (per RES_001 §2.3 + IDF folder _index.md):**

| Type | Owner | Purpose | Examples |
|---|---|---|---|
| `LangCode` | RES_001 (engine-wide) | UI translation language | "en", "vi", "zh" (ISO-639-1 lowercase) |
| `LanguageId` | IDF_002 (in-fiction) | Reality-specific in-game language | "lang_quan_thoai", "lang_co_ngu", "lang_alien_x" |

These are SEPARATE types and MUST NOT collide. `I18nBundle.translations: HashMap<LangCode, String>` uses LangCode for engine UI; in-fiction utterance.language uses LanguageId.

---

## §2 Domain concepts (proposed)

| Concept | Maps to | Notes |
|---|---|---|
| **LanguageId** | Stable-ID newtype `String` (e.g., `lang_quan_thoai`, `lang_co_ngu`) | Opaque per-reality. Closed-set declared in RealityManifest.languages. |
| **LanguageDecl** | Author-declared per-reality entry | display_name (I18nBundle) + writing_system + default_in_origin_packs (V1+) + canon_ref. |
| **WritingSystem** | Closed enum: `None / Logographic / Alphabetic / Syllabary / Custom` | None = spoken-only; Logographic = Chinese-style (Cổ ngữ); Alphabetic = Latin/Cyrillic; Syllabary = Japanese kana (V1+); Custom = reality-fictional script. |
| **ProficiencyLevel** | Closed enum 5-level: `None / Basic / Conversational / Fluent / Native` | Order-comparable. None = no understanding; Basic = phrases; Conversational = daily speech; Fluent = literary capable; Native = first-language depth. |
| **ProficiencyAxis** | Closed enum: `Read / Write / Speak / Listen` | 4-axis matrix per language per actor. Realistic asymmetry: native speaker may be Native-Speak/Listen + Basic-Read/Write (illiterate); scholar may be Fluent-Read/Write + Basic-Speak (textual scholar). |
| **actor_language_proficiency** | T2 / Reality aggregate; per-(reality, actor_id) row holds `HashMap<LanguageId, ProficiencyMatrix>` | Generic for PC + NPC. SPIKE_01 turn 5 literacy slip = LM01 has `lang_co_ngu` Read=None despite Speak=Native for `lang_quan_thoai`. |
| **ProficiencyMatrix** | `{ read: ProficiencyLevel, write: ProficiencyLevel, speak: ProficiencyLevel, listen: ProficiencyLevel }` | 4 fields × 5 levels = 5^4 = 625 combinations possible. V1 most actors have realistic patterns. |

**Cross-feature consumers:**
- A6 canon-drift detector (V1+) — at Stage 8 (canon-drift check), reads speaker's proficiency for utterance.language; flags mismatch when Quote-kind utterance references content speaker can't Read
- PL_005b InteractionSpeakPayload.language — validator rejects when speaker proficiency < threshold (Speak < Basic OR Listen < Basic for direct_targets)
- NPC_002 persona prompt assembly — includes language proficiency for realistic dialogue gen
- IDF_004 Origin — origin pack declares default native_language (PC creation default)

---

## §3 Aggregate inventory (proposed)

### 3.1 `actor_language_proficiency` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_language_proficiency", tier = "T2", scope = "reality")]
pub struct ActorLanguageProficiency {
    pub reality_id: RealityId,
    pub actor_id: ActorId,
    pub proficiencies: HashMap<LanguageId, ProficiencyMatrix>,  // declared at canonical seed; mutable V1+ via learning
    pub last_modified_at_turn: u64,
    pub schema_version: u32,
}

pub struct ProficiencyMatrix {
    pub read: ProficiencyLevel,
    pub write: ProficiencyLevel,
    pub speak: ProficiencyLevel,
    pub listen: ProficiencyLevel,
}

pub enum ProficiencyLevel {
    None,            // 0
    Basic,           // 1
    Conversational,  // 2
    Fluent,          // 3
    Native,          // 4
}

pub enum ProficiencyAxis {
    Read,
    Write,
    Speak,
    Listen,
}
```

- T2 + RealityScoped: per-actor across reality lifetime
- One row per `(reality_id, actor_id)` (every actor MUST have proficiency row, even if all-None)
- V1 mostly immutable post-canonical-seed; V1+ learning adds Apply/Decay events

### 3.2 `LanguageDecl` (RealityManifest declarative entry — not a runtime aggregate)

```rust
pub struct LanguageDecl {
    pub language_id: LanguageId,
    pub display_name: I18nBundle,
    pub writing_system: WritingSystem,
    pub default_in_origin_packs: Vec<OriginPackId>,  // V1+ IDF_004 ref (suggestion only)
    pub canon_ref: Option<GlossaryEntityId>,
}

pub enum WritingSystem {
    None,           // spoken-only
    Logographic,    // Chinese-style; Cổ ngữ
    Alphabetic,     // Latin / Cyrillic
    Syllabary,      // V1+
    Custom { name: String },  // reality-fictional script
}
```

---

## §4 Tier+scope (DP-R2 — proposed)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `actor_language_proficiency` | T2 | T2 | Reality | ~0.5-1 per turn (Speak validator + A6 detector + UI tooltip) | ~0 per turn V1 (canonical seed only); V1+ ~0.01/turn (learning Apply event) | Per-actor across reality lifetime; eventual consistency OK; V1 mostly immutable. |

---

## §5 Cross-feature integration (proposed)

### 5.1 A6 canon-drift detector (V1+ at 05_llm_safety A6 design)

A6 detector at Stage 8 reads `actor_language_proficiency` for the speaker; flags `canon_drift_flag::BodyKnowledgeMismatch` when:

- Quote-kind utterance references content in language X but speaker.proficiencies[X].Read < Basic (SPIKE_01 turn 5 — LM01 quotes 道德经注 but `proficiencies["lang_co_ngu"].read == None`)
- Statement utterance is in language X but speaker.proficiencies[X].Speak < Conversational

V1: A6 detector NOT yet active (waits for 05_llm_safety folder design). V1 IDF_002 ships data layer; V1+ A6 wires consumer.

### 5.2 PL_005b InteractionSpeakPayload validator

Per [PL_005b §2.7 validation rules](../04_play_loop/PL_005b_interaction_contracts.md):

- `utterance.language` field MUST exist in reality's RealityManifest.languages
- Speaker MUST have Speak ≥ Basic for utterance.language (Stage 0 schema check OR Stage 7 world-rule)
- Listeners (direct_targets) SHOULD have Listen ≥ Basic — V1+ enforces; V1 warning only

### 5.3 Reject UX (language.* namespace — proposed V1)

| rule_id | Stage | When |
|---|---|---|
| `language.unknown_language_id` | 0 schema | LanguageId not in RealityManifest.languages |
| `language.speaker_proficiency_insufficient` | 7 world-rule | Speaker Speak proficiency < Basic for utterance language |
| `language.listener_proficiency_insufficient` | 7 world-rule (V1+) | All direct_targets Listen proficiency < Basic — currently warning V1 |
| `language.proficiency_axis_invalid` | 0 schema | (V1+ learning) Apply event references invalid axis variant |

V1+ reservations: `language.dialect_mismatch`; `language.code_switch_unsupported`.

### 5.4 PC + NPC creation defaults

- PC creation form: select native_language from origin_pack's languages (V1+ — IDF_004 ref); V1 ships fixed Wuxia default = Quan thoại Native + Cổ ngữ Read=None (literacy slip enabled)
- NPC canonical seed: per-NPC ProficiencyMatrix declared per language explicitly

---

## §6 RealityManifest extension (proposed)

```rust
pub struct RealityManifest {
    // ... existing fields ...
    pub languages: Vec<LanguageDecl>,    // NEW V1 from IDF_002
}
```

REQUIRED V1.

**Example RealityManifest excerpt (Wuxia preset):**

```rust
languages: vec![
    LanguageDecl {
        language_id: "lang_quan_thoai".to_string(),
        display_name: I18nBundle {
            default: "Mandarin".to_string(),
            translations: HashMap::from([("vi", "Quan thoại"), ("zh", "官话")]),
        },
        writing_system: WritingSystem::Logographic,
        default_in_origin_packs: vec![],  // V1+ IDF_004 fills
        canon_ref: None,
    },
    LanguageDecl {
        language_id: "lang_co_ngu".to_string(),
        display_name: I18nBundle {
            default: "Classical Chinese".to_string(),
            translations: HashMap::from([("vi", "Cổ ngữ"), ("zh", "古文")]),
        },
        writing_system: WritingSystem::Logographic,
        default_in_origin_packs: vec![],
        canon_ref: None,
    },
    // ... 2 more (Tiếng địa phương, Đạo ngôn V1+)
]
```

---

## §7 V1 acceptance criteria (preliminary)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-LNG-1** | Reality declares Wuxia 4-language preset; LM01 created with proficiency Quan thoại Native (all axes) + Cổ ngữ Read=None Listen=Basic Speak=None Write=None | row committed; UI tooltip shows correct matrix |
| **AC-LNG-2** | LM01 Speaks utterance.language=Quan thoại | Stage 7 world-rule passes; Speak commits |
| **AC-LNG-3** | LM01 attempts Speak utterance.language=Cổ ngữ (Speak=None) | rejected with `language.speaker_proficiency_insufficient` |
| **AC-LNG-4** | LM01 Speaks utterance.language=`lang_unknown` (not in RealityManifest) | rejected at Stage 0 with `language.unknown_language_id` |
| **AC-LNG-5** | (SPIKE_01 turn 5 reproducibility) LM01 Speaks Quan thoại utterance Quote-kind referencing 道德经注 (Cổ ngữ canon); A6 detector configured | Speak commits (Quan thoại valid); A6 detector flags `canon_drift_flag::BodyKnowledgeMismatch` due to Cổ ngữ Read=None — V1: data layer correct; V1+: A6 wires up |
| **AC-LNG-6** | Tiểu Thúy declared with Quan thoại Native + Cổ ngữ Native (educated NPC); PCS examines her diary | Examine succeeds; she can read diary content |
| **AC-LNG-7** | I18nBundle resolves Quan thoại in Vietnamese UI; Mandarin in English UI | display_name.translations["vi"] = "Quan thoại"; default = "Mandarin" |
| **AC-LNG-8** | Cross-feature: NPC_002 persona prompt for Du sĩ includes "Du sĩ knows Quan thoại Native + Cổ ngữ Fluent (literary scholar)" | persona prompt assembly reads proficiency correctly |

---

## §8 Open questions (CONCEPT — user confirm before DRAFT)

| ID | Question | Default proposal |
|---|---|---|
| **LNG-Q1** | ProficiencyLevel — 5-level (current) vs 4-level (drop Conversational) vs 6-level (add Expert)? | **5-level V1** — matches CEFR-like granularity; sufficient for SPIKE_01 + general realistic gradation |
| **LNG-Q2** | 4-axis (Read/Write/Speak/Listen) vs 2-axis (Comprehension/Production)? | **4-axis V1** — needed for SPIKE_01 turn 5 (literacy slip = asymmetric Speak vs Read); 2-axis collapses too coarse |
| **LNG-Q3** | LanguageId vs language_id field name — opaque string (current) vs typed enum per reality (RaceId pattern)? | **Opaque string** — same as RaceId pattern; cross-reality enums collide |
| **LNG-Q4** | RealityManifest `languages` REQUIRED V1 vs OPTIONAL? | **REQUIRED V1** — every reality has ≥1 language; pattern with PF_001 places + IDF_001 races |
| **LNG-Q5** | Speak validator threshold — Speak ≥ Basic (current) vs Speak ≥ Conversational? | **Speak ≥ Basic V1** — Basic = phrases sufficient for Cry/exclamation; Conversational threshold too high for V1 |
| **LNG-Q6** | Listener proficiency check — warning V1 vs reject V1 vs defer V1+? | **Defer V1+** (LNG-D5) — V1 listener proficiency stored but not validator-enforced; A6 detector consumes for narrative quality |
| **LNG-Q7** | `default_in_origin_packs` field — exists V1 with empty list (current) vs defer V1+? | **Exists V1 empty** — schema slot for IDF_004 V1+ to fill; avoids future migration |
| **LNG-Q8** | WritingSystem variants — 5 (current) vs minimal 3 (None/Latin/Logographic)? | **5 variants V1** — covers SPIKE_01 (Logographic Cổ ngữ + Logographic Quan thoại spoken script) + Custom for fictional realities |
| **LNG-Q9** | Learning Apply events V1 (proficiency Decay/Apply mutations) vs canonical-seed-only V1? | **Canonical-seed-only V1** — learning V1+ enrichment (LNG-D2); V1 immutable post-seed |
| **LNG-Q10** | A6 canon-drift detector wiring — V1 ships A6 hook stub vs V1 data-layer-only? | **V1 data-layer-only** — A6 wires up at 05_llm_safety folder design; IDF_002 V1 just stores data correctly + tests AC-LNG-5 dataset |
| **LNG-Q11** | LanguageId vs LangCode collision prevention — runtime assert (current) vs compile-time newtype? | **Runtime assert V1** — LanguageId and LangCode are both String wrappers; runtime check at RealityManifest validation; V1+ may add compile-time newtypes |

---

## §9 Deferrals (V1+ landing point)

| ID | Item | Defer to |
|---|---|---|
| **LNG-D1** | Dialect / accent variants per language (Northern Mandarin vs Southern Mandarin) | V1+ enrichment |
| **LNG-D2** | Learning over time (Apply event increases proficiency; Decay event drops) | V1+ when scheduler ships V1+30d |
| **LNG-D3** | Written-only languages full support (Cổ ngữ V1 stub; full library / dictionary feature) | V1+ literary feature |
| **LNG-D4** | Sign language | V2+ |
| **LNG-D5** | Listener proficiency reject (currently warning) | V1+ when integration tests show drift |
| **LNG-D6** | Telepathic / mental languages | V2+ |
| **LNG-D7** | Code-switching (multi-language concurrent in single utterance) | V1+ NLP enhancement |
| **LNG-D8** | Compile-time newtype for LanguageId vs LangCode collision prevention | V1+ engine-wide refactor |
| **LNG-D9** | Per-language script vs spoken split (Quan thoại spoken-only vs Quan thoại + 漢字 written) | V1+ when Cổ ngữ deeper |

---

## §10 Cross-references

**Foundation tier:**
- [`EF_001`](../00_entity/EF_001_entity_foundation.md) §5.1 — ActorId
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) §2.3 — I18nBundle + LangCode (distinct from LanguageId)

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race_concept.md) — race may have native language hint (LNG-D9 V1+)
- [`IDF_004 Origin`](IDF_004_origin_concept.md) §V1+ — origin pack declares default native language

**Consumers:**
- 05_llm_safety A6 (V1+) — canon-drift detector at Stage 8
- PL_005b §2.7 — Speak validator
- NPC_002 persona prompt assembly
- Future PCS_001 — PC creation form

**Boundaries (DRAFT registers):**
- `_boundaries/01_feature_ownership_matrix.md` — `actor_language_proficiency` aggregate
- `_boundaries/02_extension_contracts.md` §1.4 — `language.*` namespace (4 V1 rules + 2 V1+ reservations)
- `_boundaries/02_extension_contracts.md` §2 RealityManifest — `languages` extension

**Spike:**
- [`SPIKE_01 turn 5`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — literacy slip canonical reproducibility gate

---

## §11 CONCEPT → DRAFT promotion checklist

When user approves Q1-Q11:
- [ ] Lock-claim `_boundaries/_LOCK.md`
- [ ] Rename: `IDF_002_language_concept.md` → `IDF_002_language.md`
- [ ] Status CONCEPT → DRAFT
- [ ] Lock Q-decisions; replace §8 with §8 Pattern choices
- [ ] Add full §1-§19 spec mirroring EF_001
- [ ] Register `actor_language_proficiency` aggregate
- [ ] Register `language.*` namespace (4 V1 rules)
- [ ] Register `languages: Vec<LanguageDecl>` in RealityManifest §2
- [ ] Register Stable-ID prefix `LNG-*`
- [ ] Append `99_changelog.md` row
- [ ] Lock-release (or hold for next IDF feature DRAFT)
