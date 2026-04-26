# IDF_002 — Language Foundation

> **Conversational name:** "Language" (LNG). Tier 5 Actor Substrate Foundation feature owning per-reality `LanguageId` closed-set (in-fiction languages — Quan thoại / Cổ ngữ / Tiếng Anh / Common Tongue / etc.) + per-actor `actor_language_proficiency` aggregate (4-axis read/write/speak/listen × 5-level proficiency). A6 canon-drift detector consumes (SPIKE_01 turn 5 literacy slip canonical reproducibility gate).
>
> **Critical distinction:** `LanguageId` (IDF_002 — in-fiction) ≠ `LangCode` (RES_001 — engine UI translation ISO-639-1). Runtime newtype prevents accidental cross-type assignment.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** DRAFT 2026-04-26 (Phase 0 CONCEPT promoted to DRAFT after POST-SURVEY-Q1..Q7 user "A" confirmation; Q-decisions LNG-Q1..Q11 locked per concept-note)
> **Stable IDs in this file:** `LNG-A*` axioms · `LNG-D*` deferrals · `LNG-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types); [SPIKE_01 turn 5 literacy slip](../_spikes/SPIKE_01_two_sessions_reality_time.md); [PL_005b §2.1 InteractionSpeakPayload.language](../04_play_loop/PL_005b_interaction_contracts.md); [RES_001 §2.3 I18nBundle + LangCode](../00_resource/RES_001_resource_foundation.md); [IDF_001 RaceId pattern](IDF_001_race.md).
> **Defers to:** future PCS_001 (PC language proficiency at creation); NPC_001/`NPC_NNN` (NPC language declared at canonical seed); 05_llm_safety A6 (canon-drift literacy mismatch detector V1+); V1+ dialect/accent feature.
> **Event-model alignment:** Language proficiency events = EVT-T3 Derived (`aggregate_type=actor_language_proficiency`). No new EVT-T* category.

---

## §1 User story (concrete — SPIKE_01 + multi-reality presets)

A reality is born from Thần Điêu Đại Hiệp (Wuxia preset). Its RealityManifest declares 4 languages: Quan thoại / Cổ ngữ / Tiếng địa phương / Đạo ngôn.

**SPIKE_01 turn 5 literacy slip canonical scenario:**

1. **Lý Minh** (PC, body originally Phàm nhân peasant) — proficiencies:
   - `lang_quan_thoai`: Read=None / Write=None / Speak=Native / Listen=Native (illiterate peasant; speaks vernacular)
   - `lang_co_ngu`: Read=None / Write=None / Speak=None / Listen=Basic (rural exposure to liturgical chant only)
   - `lang_tieng_dia_phuong`: Read=None / Write=None / Speak=Conversational / Listen=Native (regional dialect)
   - `lang_dao_ngon`: None all axes

2. **Du sĩ** (NPC, scholar) — proficiencies:
   - `lang_quan_thoai`: Native all 4 axes
   - `lang_co_ngu`: Read=Fluent / Write=Fluent / Speak=Conversational / Listen=Fluent (literary scholar)
   - `lang_tieng_dia_phuong`: Conversational all axes
   - `lang_dao_ngon`: Read=Basic / others=None

3. **Tiểu Thúy** (NPC, innkeeper daughter) — Quan thoại Native + Tiếng địa phương Native; Cổ ngữ + Đạo ngôn None.

4. **Lão Ngũ** (NPC, innkeeper) — Quan thoại Native (spoken/listen); Quan thoại Read=Basic (rudimentary literacy for ledgers); Tiếng địa phương Native; Cổ ngữ + Đạo ngôn None.

**Turn 5 SPIKE_01 reproducibility gate:** Lý Minh attempts to "Speak with Quote-kind utterance referencing 《Đạo Đức Kinh chú》 (a Cổ ngữ canonical text)." Speak validator passes (Quan thoại Native sufficient for Speech). At Stage 8 canon-drift detector, A6 reads LM01.proficiencies[`lang_co_ngu`].Read = None — body cannot have read this book — flags `BodyKnowledgeMismatch` in canon_drift_flags. UI presents the literacy-slip warning to PC; LLM-driven NPC reactions (Du sĩ Tier 3 priority + Lão Ngũ Tier 4) acknowledge the mismatch via Chorus.

**A second reality (Modern Saigon)** declares 3 languages: Tiếng Việt / Tiếng Anh / Tiếng Trung. Most PCs/NPCs proficient Vietnamese only; some scholars Tiếng Trung Read+Listen.

**This feature design specifies:** the closed-set `LanguageId` per reality declared in `RealityManifest.languages`; the per-actor `actor_language_proficiency` aggregate (HashMap<LanguageId, ProficiencyMatrix>); the 4-axis × 5-level proficiency model; the V1+ A6 canon-drift consumer hook; the PL_005b Speak utterance.language validation; the rejection UX with Vietnamese reject copy in `language.*` namespace.

After this lock: SPIKE_01 turn 5 reproducible (data layer correct); A6 detector consumes proficiency at V1+; LLM persona prompt assembly includes language matrix for realistic NPC dialogue.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **LanguageId** | `pub struct LanguageId(pub String);` typed newtype (e.g., `LanguageId("lang_quan_thoai".to_string())`) | Opaque language-neutral; per-reality scope. **Distinct from RES_001 `LangCode`** (engine UI ISO-639-1 string) — runtime newtype enforces. Per LNG-Q11 LOCKED: runtime assert V1; compile-time newtype V1+ via LNG-D8. |
| **LanguageDecl** | Author-declared per-reality entry (in RealityManifest.languages) | display_name (I18nBundle) + writing_system + default_in_origin_packs (Vec<OriginPackId> V1+ IDF_004 ref; empty V1) + canon_ref. |
| **WritingSystem** | Closed enum 5-variant: `None / Logographic / Alphabetic / Syllabary / Custom { name: String }` | None = spoken-only; Logographic = Chinese-style (Cổ ngữ + Quan thoại 漢字); Alphabetic = Latin / Cyrillic; Syllabary = Japanese kana V1+; Custom = reality-fictional script. |
| **ProficiencyLevel** | Closed enum 5-level: `None / Basic / Conversational / Fluent / Native` | Order-comparable. None = no understanding; Basic = phrases; Conversational = daily speech; Fluent = literary capable; Native = first-language depth. |
| **ProficiencyAxis** | Closed enum: `Read / Write / Speak / Listen` | 4-axis matrix per language per actor. Realistic asymmetry supported (illiterate native: Native-Speak/Listen + None-Read/Write; scholar: Fluent-Read/Write + Basic-Speak). |
| **actor_language_proficiency** | T2 / Reality aggregate; per-(reality, actor_id) row holds `HashMap<LanguageId, ProficiencyMatrix>` | Generic for PC + NPC. ActorId source = EF_001 §5.1. SPIKE_01 turn 5 = LM01 Cổ ngữ Read=None despite Quan thoại Native. |
| **ProficiencyMatrix** | `{ read: ProficiencyLevel, write: ProficiencyLevel, speak: ProficiencyLevel, listen: ProficiencyLevel }` | 4 fields × 5 levels = 5^4 = 625 combinations possible. V1 most actors have realistic patterns. |

**Cross-feature consumers:**
- 05_llm_safety A6 (V1+) — canon-drift detector at Stage 8 reads speaker proficiency
- PL_005b §2.7 — Speak validator rejects when speaker proficiency < threshold
- NPC_002 persona prompt assembly — embeds proficiency matrix in LLM context
- IDF_004 Origin — origin pack `default_native_language` ref (V1+ enrichment)

---

## §2.5 Event-model mapping

| IDF_002 path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Initial proficiency seed (canonical bootstrap) | **EVT-T4 System** | (no dedicated sub-type V1; emitted alongside EF_001 EntityBorn + IDF_001 RaceBorn) | Bootstrap role | V1: per-actor proficiency declared in canonical actor entry; no separate System event needed. V1+ may add `LanguageProficiencySeeded` if granularity needed. |
| Proficiency apply (V1+ learning Apply event) | **EVT-T3 Derived** | `aggregate_type=actor_language_proficiency`, delta_kind=`ApplyProficiency` | Aggregate-Owner role | V1: not active (V1 immutable post-canonical-seed); V1+ scheduler-driven learning |
| Proficiency admin override (Forge edit) | **EVT-T8 Administrative** | `Forge:EditLanguageProficiency { actor_id, language_id, axis, before, after }` | Forge role (WA_003) | Uses forge_audit_log; AC-LNG-9 covers atomicity |

**Closed-set proof:** every language path produces active EVT-T* (T3 Derived V1+ / T4 System bootstrap-coupled / T8 Administrative). No new EVT-T* row.

---

## §3 Aggregate inventory

### 3.1 `actor_language_proficiency` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_language_proficiency", tier = "T2", scope = "reality")]
pub struct ActorLanguageProficiency {
    pub reality_id: RealityId,
    pub actor_id: ActorId,                        // EF_001 §5.1 source
    pub proficiencies: HashMap<LanguageId, ProficiencyMatrix>,
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
    None,            // 0 — no understanding
    Basic,           // 1 — phrases / liturgical exposure
    Conversational,  // 2 — daily speech
    Fluent,          // 3 — literary capable
    Native,          // 4 — first-language depth
}

pub enum ProficiencyAxis {
    Read,
    Write,
    Speak,
    Listen,
}
```

- T2 + RealityScoped; per-actor across reality lifetime
- One row per `(reality_id, actor_id)` (every actor MUST have proficiency row, even if all-None for newborns)
- V1 mostly immutable post-canonical-seed; V1+ learning Apply / Decay events
- Synthetic actors: don't get proficiency rows V1

### 3.2 `LanguageDecl` (RealityManifest declarative entry)

```rust
pub struct LanguageDecl {
    pub language_id: LanguageId,
    pub display_name: I18nBundle,                            // RES_001 §2.3
    pub writing_system: WritingSystem,
    pub default_in_origin_packs: Vec<OriginPackId>,          // V1+ IDF_004 ref; empty V1
    pub canon_ref: Option<GlossaryEntityId>,
}

pub enum WritingSystem {
    None,
    Logographic,
    Alphabetic,
    Syllabary,
    Custom { name: String },
}
```

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `actor_language_proficiency` | T2 | T2 | Reality | ~0.5-1 per turn (Speak validator + A6 detector V1+ + UI tooltip + NPC_002 persona prompt) | ~0 per turn V1 (canonical seed only); V1+ ~0.01/turn (learning Apply) | Per-actor across reality lifetime; eventual consistency OK; V1 mostly immutable |

---

## §5 DP primitives

### 5.1 Reads
- `dp::read_projection_reality::<ActorLanguageProficiency>(ctx, actor_id)` — Speak validator + A6 + UI + NPC_002 prompt
- `dp::query_scoped_reality::<ActorLanguageProficiency>(ctx, predicate=field_eq(language_id, X))` — operator queries
- `dp::read_reality_manifest(ctx).languages` — RealityManifest extension

### 5.2 Writes
- `dp::t2_write::<ActorLanguageProficiency>(ctx, actor_id, SeedProficiencyDelta { proficiencies })` — canonical seed
- `dp::t2_write::<ActorLanguageProficiency>(ctx, actor_id, AdminOverrideDelta { language_id, axis, level })` — Forge admin (V1 supported via Forge:EditLanguageProficiency)
- V1+ `dp::t2_write::<ActorLanguageProficiency>(ctx, actor_id, ApplyProficiencyDelta { language_id, axis_deltas })` — learning Apply

### 5.3 Subscriptions
- UI subscribes to `actor_language_proficiency` invalidations via DP-X cache invalidation
- NPC_002 reads at SceneRoster build (cached for batch duration)

### 5.4 Capability + lifecycle
- `produce: [Derived]` + `write: actor_language_proficiency @ T2 @ reality` — IDF_002 owner (world-service V1)
- `produce: [Administrative]` + sub-shape `Forge:EditLanguageProficiency` — Forge admin

---

## §6 Capability requirements (JWT claims)

Inherits IDF_001 + EF_001 patterns. No new claim category.

| Claim | Granted to | Why |
|---|---|---|
| `produce: [Derived]` + `write: actor_language_proficiency @ T2 @ reality` | world-service backend | seed at canonical bootstrap; V1+ learning |
| `produce: [Administrative]` + sub-shape `Forge:EditLanguageProficiency` | Forge admin (WA_003) | admin override audit |
| `read: actor_language_proficiency @ T2 @ reality` | every PC session + NPC_002 + A6 detector V1+ | UI + persona + canon-drift |

---

## §7 Subscribe pattern

UI receives proficiency updates via DP-X invalidation → re-renders language tooltip. NPC_002 reads at SceneRoster build per NPC_002 §6 (cached).

---

## §8 Pattern choices

### 8.1 4-axis × 5-level proficiency matrix (LNG-Q1 + Q2 LOCKED)
4-axis (Read/Write/Speak/Listen) needed for SPIKE_01 turn 5 literacy slip (asymmetric Speak vs Read); 2-axis collapses too coarse. 5-level matches CEFR-like granularity sufficient for SPIKE_01.

### 8.2 LanguageId opaque string per-reality (LNG-Q3 LOCKED)
Same pattern as RaceId / PlaceId. Cross-reality collision allowed semantically.

### 8.3 RealityManifest `languages` REQUIRED V1 (LNG-Q4 LOCKED)
Every reality declares ≥1 language. Mirrors PF_001 + IDF_001 pattern.

### 8.4 Speak validator threshold = Speak ≥ Basic (LNG-Q5 LOCKED)
Basic phrases sufficient for Cry/exclamation; Conversational threshold too high for V1.

### 8.5 Listener proficiency check DEFERRED V1+ (LNG-Q6 LOCKED + LNG-D5)
V1 listener proficiency stored but not validator-enforced; A6 detector consumes for narrative quality.

### 8.6 default_in_origin_packs schema slot V1 (LNG-Q7 LOCKED)
Empty Vec V1; IDF_004 V1+ fills (origin pack proposes default native language).

### 8.7 5 WritingSystem variants V1 (LNG-Q8 LOCKED)
Covers SPIKE_01 (Logographic Cổ ngữ + Quan thoại 漢字) + Custom for fictional realities.

### 8.8 Canonical-seed-only V1 (LNG-Q9 LOCKED)
V1 immutable post-seed; learning V1+ via LNG-D2 Apply events.

### 8.9 V1 data-layer-only A6 wiring (LNG-Q10 LOCKED)
A6 wires up at 05_llm_safety folder design; IDF_002 V1 just stores data correctly + AC-LNG-5 dataset.

### 8.10 Runtime assert vs compile-time newtype (LNG-Q11 LOCKED)
LanguageId + LangCode are both String wrappers; runtime check at RealityManifest validation; V1+ compile-time newtypes via LNG-D8.

---

## §9 Failure-mode UX

| Reject reason | Stage | When | Vietnamese reject copy (I18nBundle) |
|---|---|---|---|
| `language.unknown_language_id` | 0 schema | LanguageId not in RealityManifest.languages | "Ngôn ngữ không tồn tại trong thế giới này." |
| `language.speaker_proficiency_insufficient` | 7 world-rule | Speaker Speak < Basic for utterance language | "Bạn không nói được [ngôn ngữ]." |
| `language.listener_proficiency_insufficient` | 7 world-rule (V1+) | All direct_targets Listen < Basic | (V1+ enforces; V1 warning only) |
| `language.proficiency_axis_invalid` | 0 schema | (V1+ learning) Apply event references invalid axis | (Schema check; not user-facing) |

**`language.*` V1 rule_id enumeration** (registered in `_boundaries/02_extension_contracts.md` §1.4):

1. `language.unknown_language_id` — Stage 0
2. `language.speaker_proficiency_insufficient` — Stage 7
3. `language.listener_proficiency_insufficient` — Stage 7 (V1+ active; V1 warning only)
4. `language.proficiency_axis_invalid` — Stage 0 (V1+ learning context)

V1+ reservations: `language.dialect_mismatch`; `language.code_switch_unsupported` (LNG-D7).

V1 user-facing rejects: `language.unknown_language_id` + `language.speaker_proficiency_insufficient`.

---

## §10 Cross-service handoff

```
1. Canonical bootstrap:
   For each canonical actor, RealityBootstrapper emits seed:
     dp::t2_write::<ActorLanguageProficiency>(ctx, actor_id, SeedProficiencyDelta {
       proficiencies: HashMap<LanguageId, ProficiencyMatrix>
     }) → T1 Derived
   E.g., Lý Minh: { lang_quan_thoai: {Native/Native/None/None}, lang_co_ngu: {Basic/None/None/None}, ... }

2. Speak validator (Stage 7 world-rule):
   PL_005b InteractionSpeakPayload.utterance.language=lang_quan_thoai
     a. dp::read_projection_reality::<ActorLanguageProficiency>(ctx, agent_id)
     b. proficiencies[lang_quan_thoai].speak >= Basic ✓
     c. continue Stage 8

3. A6 canon-drift detector (V1+ at Stage 8):
   Speak utterance Quote-kind references lang_co_ngu canonical text:
     a. read agent.proficiencies[lang_co_ngu].read = None (LM01 SPIKE_01 turn 5)
     b. flag canon_drift_flag::BodyKnowledgeMismatch
     c. populate canon_drift_flags in TurnEvent payload

4. NPC_002 persona prompt:
   Du sĩ persona: "Du sĩ knows Quan thoại Native + Cổ ngữ Fluent (literary scholar);
   speaks deferentially when literary references arise."
```

---

## §11-§14 Sequences

### §11 Canonical seed (Wuxia 4-language bootstrap)

Per §1 canonical actors, RealityBootstrapper seeds ActorLanguageProficiency for each:
- Lý Minh: Quan thoại Native+Native+Speak/Listen Native, Cổ ngữ Read=None Listen=Basic, etc.
- Du sĩ: scholar pattern with Cổ ngữ Fluent
- Tiểu Thúy: vernacular pattern
- Lão Ngũ: vernacular + ledger-literacy pattern

Each seed emits T3 Derived with causal_refs=[reality_bootstrap_event_id].

### §12 Speak validator (canonical pass)

LM01 `/verbatim "Tiểu nhị, vĩnh ngộ tại ư phi vi tà"` (Quan thoại Speak):
- Stage 0: utterance.language=lang_quan_thoai exists in RealityManifest.languages ✓
- Stage 7: agent.proficiencies[lang_quan_thoai].speak = Native ≥ Basic ✓
- Stage 8: A6 detector flags canon-drift (Cổ ngữ Read=None) — non-blocking
- Commit Speak T1.

### §13 Speak validator (reject — speaker can't speak)

Hypothetical: LM01 attempts utterance.language=lang_dao_ngon (Daoist canon — LM01 None all axes):
- Stage 7: agent.proficiencies[lang_dao_ngon].speak = None < Basic
- Reject with `language.speaker_proficiency_insufficient`
- turn_number unchanged

### §14 Forge admin override

Admin edits LM01.proficiencies[lang_co_ngu].read from None → Basic (story-event: LM01 begins literacy training):
- EVT-T8 Administrative `Forge:EditLanguageProficiency { actor_id, language_id, axis: Read, before: None, after: Basic }`
- 3-write transaction atomic (proficiency row + EVT-T8 + forge_audit_log)
- Audit log shows admin reason

---

## §15 Acceptance criteria

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-LNG-1** | Wuxia 4-language preset; LM01 seeded with literacy slip pattern | proficiency row committed; matrix shows Quan thoại Native + Cổ ngữ Read=None |
| **AC-LNG-2** | LM01 Speaks Quan thoại utterance | Stage 7 passes; Speak commits |
| **AC-LNG-3** | LM01 attempts Speak Cổ ngữ (Speak=None) | rejected with `language.speaker_proficiency_insufficient` |
| **AC-LNG-4** | Speak utterance.language=`lang_unknown` (not in RealityManifest) | rejected at Stage 0 with `language.unknown_language_id` |
| **AC-LNG-5** | (SPIKE_01 turn 5 reproducibility) LM01 Speaks Quan thoại Quote-kind referencing 道德经注 | Speak commits + A6 detector flags `canon_drift_flag::BodyKnowledgeMismatch` (V1: data layer correct; V1+ A6 wires up) |
| **AC-LNG-6** | Tiểu Thúy Quan thoại Native + Cổ ngữ Native; Examine her diary | Examine succeeds (she can read it) |
| **AC-LNG-7** | I18nBundle resolves Quan thoại / Mandarin / 官话 across locales | display_name correctly localized |
| **AC-LNG-8** | NPC_002 persona prompt for Du sĩ includes proficiency matrix | persona prompt assembly reads proficiency correctly |

### 15.2 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-LNG-V1+1** | A6 detector wired; SPIKE_01 turn 5 produces canon_drift_flag end-to-end | V1+ 05_llm_safety A6 design |
| **AC-LNG-V1+2** | Learning Apply event raises Cổ ngữ Read None → Basic | V1+ scheduler V1+30d |

### 15.3 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-LNG-9** | Forge admin override LM01.lang_co_ngu.Read = Basic | EVT-T8 audit emitted; 3-write atomic |
| **AC-LNG-10** | LangCode collision attempt: actor seed uses LanguageId="en" (collides with LangCode "en") | runtime assert at RealityManifest validation rejects (LNG-Q11 path); LanguageId namespace must NOT use ISO-639-1 codes |

### 15.4 Status transition criteria

- **DRAFT → CANDIDATE-LOCK:** design complete + boundary registered (`actor_language_proficiency` + `language.*` 4 V1 rules + `languages` RealityManifest extension + `LNG-*` stable-ID prefix). All AC-LNG-1..10 specified.
- **CANDIDATE-LOCK → LOCK:** all AC-LNG-1..10 V1-testable scenarios pass integration tests against Wuxia + Modern reality fixtures. V1+ scenarios (AC-LNG-V1+1..2) deferred.

---

## §16 Boundary registrations

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `actor_language_proficiency` aggregate (T2/Reality, IDF_002 DRAFT)
   - EVT-T8 Administrative sub-shape: NEW `Forge:EditLanguageProficiency` (IDF_002 owns)
   - Stable-ID prefix: NEW `LNG-*` row
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 RejectReason namespace: NEW `language.*` row with 4 V1 rule_ids + 2 V1+ reservations
   - §2 RealityManifest: NEW `languages: Vec<LanguageDecl>` REQUIRED V1
3. `_boundaries/99_changelog.md`: append IDF folder 4/15 entry

---

## §17 Deferrals

| ID | Item | Defer to |
|---|---|---|
| **LNG-D1** | Dialect / accent variants | V1+ enrichment |
| **LNG-D2** | Learning over time (Apply / Decay events) | V1+ scheduler V1+30d |
| **LNG-D3** | Written-only languages full library / dictionary feature | V1+ literary feature |
| **LNG-D4** | Sign language | V2+ |
| **LNG-D5** | Listener proficiency reject (currently warning) | V1+ when integration tests show drift |
| **LNG-D6** | Telepathic / mental languages | V2+ |
| **LNG-D7** | Code-switching (multi-language concurrent in single utterance) | V1+ NLP enhancement |
| **LNG-D8** | Compile-time newtype for LanguageId vs LangCode collision | V1+ engine-wide refactor |
| **LNG-D9** | Per-language script vs spoken split (Quan thoại spoken-only vs Quan thoại + 漢字 written) | V1+ when Cổ ngữ deeper |

---

## §18 Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types)
- [`RES_001 §2.3 I18nBundle + LangCode`](../00_resource/RES_001_resource_foundation.md) — distinct from LanguageId
- [`IDF_001 RaceId pattern`](IDF_001_race.md) — sibling typed-newtype pattern

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race.md) — race may have native language hint (LNG-D9 V1+)
- [`IDF_004 Origin`](IDF_004_origin_concept.md) — origin pack default_native_language ref

**Consumers:**
- 05_llm_safety A6 (V1+) — canon-drift detector at Stage 8
- [`PL_005b §2.7`](../04_play_loop/PL_005b_interaction_contracts.md) — Speak validator
- NPC_002 persona prompt assembly
- Future PCS_001 — PC creation form

**Boundaries:**
- `_boundaries/01_feature_ownership_matrix.md` — `actor_language_proficiency`
- `_boundaries/02_extension_contracts.md` §1.4 — `language.*` namespace; §2 — `languages` RealityManifest extension
- `_boundaries/03_validator_pipeline_slots.md` — Stage 7 world-rule (Speak validator) + Stage 8 canon-drift (V1+ A6)

**Spike:**
- [`SPIKE_01 turn 5`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — literacy slip canonical reproducibility gate

---

## §19 Implementation readiness checklist

- [x] §2 Domain concepts (LanguageId / LanguageDecl / actor_language_proficiency / ProficiencyMatrix / ProficiencyLevel / ProficiencyAxis / WritingSystem)
- [x] §2.5 Event-model mapping (T3 / T4 / T8; no new EVT-T*)
- [x] §3 Aggregate inventory (1 new: actor_language_proficiency)
- [x] §4 Tier+scope (DP-R2)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT
- [x] §7 Subscribe pattern
- [x] §8 Pattern choices (10 LNG-Q decisions LOCKED)
- [x] §9 Failure UX (language.* 4 V1 namespace + 2 V1+ reservations)
- [x] §10 Cross-service handoff (4 flows)
- [x] §11-§14 Sequences (canonical seed / Speak pass / Speak reject / Forge override)
- [x] §15 Acceptance criteria (10 V1-testable + 2 V1+ deferred)
- [x] §16 Boundary registrations
- [x] §17 Deferrals LNG-D1..D9
- [x] §18 Cross-references
- [x] §19 Readiness

**Phase 3 cleanup applied 2026-04-26 (in IDF_002 commit 5/15 cycle):**
- S1.1 §2 LanguageId clarified as typed newtype `pub struct LanguageId(pub String)`; runtime newtype distinct from RES_001 LangCode
- S1.2 §3.1 Synthetic actor exclusion clarified (no proficiency rows V1)
- S2.1 §10 + §13 Stage 7 Speak validator threshold note (Speak ≥ Basic per LNG-Q5 LOCKED)
- S2.2 §17 LNG-D9 deferral wording tightened (per-language script vs spoken split — Cổ ngữ deeper V1+)
- S3.1 §15.4 LOCK criterion split (DRAFT→CANDIDATE-LOCK vs CANDIDATE-LOCK→LOCK)

**Status transition:** DRAFT 2026-04-26 (Phase 3 applied) → **CANDIDATE-LOCK** in next commit (6/15) → **LOCK** when AC-LNG-1..10 pass + V1+ scenarios after 05_llm_safety A6 + V1+30d scheduler ships.
