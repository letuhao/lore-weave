# IDF_003 — Personality Foundation

> **Conversational name:** "Personality" (PRS). Tier 5 Actor Substrate Foundation feature owning per-reality `PersonalityArchetypeId` closed-set (12 V1 archetypes per POST-SURVEY-Q1 LOCKED) + per-actor `actor_personality` aggregate + voice register integration (resolves [PL_005b §2.1](../04_play_loop/PL_005b_interaction_contracts.md) `speaker_voice` orphan ref). NPC_002 §6 priority algorithm Tier 2-3 + opinion drift modifier consume; resolves [PL_005c INT-INT-D5](../04_play_loop/PL_005c_interaction_integration.md) (per-personality opinion modifier) deferral.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** DRAFT 2026-04-26 (Phase 0 CONCEPT promoted to DRAFT after POST-SURVEY-Q1..Q7 user "A" confirmation; Q-decisions PRS-Q1..Q11 locked + Q1 expanded to 12 archetypes per POST-SURVEY-Q1)
> **Stable IDs:** `PRS-A*` axioms · `PRS-D*` deferrals · `PRS-Q*` decisions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types); [PL_005b §2.1 InteractionSpeakPayload](../04_play_loop/PL_005b_interaction_contracts.md) speaker_voice; [NPC_002 §6 priority algorithm](../05_npc_systems/NPC_002_chorus.md); [PL_005c INT-INT-D5](../04_play_loop/PL_005c_interaction_integration.md); [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md); [IDF_001 RaceId pattern](IDF_001_race.md).
> **Defers to:** future PCS_001 (PC personality at creation); NPC_001/`NPC_NNN` (NPC archetype canonical seed); V1+ Big-Five trait system; V1+ archetype evolution.
> **Event-model alignment:** Personality assignment events = EVT-T3 Derived (`aggregate_type=actor_personality`) + EVT-T8 Administrative (`Forge:EditPersonality`). No new EVT-T* category.

---

## §1 User story

A Wuxia reality bootstraps with 12 universal archetypes:

1. **Lý Minh** (PC) — archetype=Idealist (Lý tưởng); voice_register=Neutral (override per-utterance to Formal in court / Casual at home)
2. **Tiểu Thúy** (NPC, innkeeper daughter) — archetype=Innocent (Ngây thơ); voice_register=Casual
3. **Du sĩ** (NPC, scholar) — archetype=Pious (Mộ đạo); voice_register=Archaic (Daoist sage diction)
4. **Lão Ngũ** (NPC, innkeeper) — archetype=Worldly (Thế tục); voice_register=Casual
5. **Hypothetical Ma đạo cult leader** (V1+ NPC) — archetype=Ambitious (Tham vọng); voice_register=Formal (commanding tone)
6. **Hypothetical sect disciple** (V1+ NPC) — archetype=Loyal (Trung nghĩa); voice_register=Formal (deferential)
7. **Hypothetical Buddhist healer** (V1+ NPC) — archetype=Compassionate (Từ bi); voice_register=Archaic
8. **Hypothetical hermit** (V1+ NPC) — archetype=Aloof (Lạnh nhạt); voice_register=Neutral

Modern + Sci-fi presets ship same 12 universal archetypes (reality-specific archetypes V1+ enrichment per PRS-D4).

**SPIKE_01 turn 5 NPC_002 priority resolution (cross-feature):** Lý Minh quotes book (literacy slip per IDF_002 SPIKE_01 turn 5). NPC_002 §6 priority algorithm reads:
- Du sĩ archetype=Pious + Cổ ngữ Fluent → **Tier 3 knowledge_match primary candidate**
- Lão Ngũ archetype=Worldly + Cổ ngữ None → **Tier 4 ambient observer**
- Tiểu Thúy archetype=Innocent + Cổ ngữ None → **Tier 1 filtered out**

Personality archetype + IDF_002 language proficiency jointly drive realistic NPC reaction filtering.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **PersonalityArchetypeId** | `pub struct PersonalityArchetypeId(pub String);` typed newtype | Opaque per-reality (cross-reality collision allowed); follows IDF_001 RaceId / IDF_002 LanguageId pattern. |
| **PersonalityArchetypeDecl** | Author-declared per-reality entry | display_name (I18nBundle) + voice_register + opinion_modifier_table (HashMap<PersonalityArchetypeId, i8> -10..=+10 per other archetype) + speech_pattern_hints (Vec<String> for V1+ NPC_002 LLM prompt) + canon_ref. |
| **VoiceRegister** | Closed enum 5-variant: `Formal / Neutral / Casual / Crude / Archaic` | V1 closed set (PRS-Q3 LOCKED). Consumed by PL_005b InteractionSpeakPayload.utterance.speaker_voice. Per-utterance override allowed (PRS-Q10). |
| **actor_personality** | T2 / Reality aggregate; per-(reality, actor_id) row | Generic for PC + NPC. V1 single archetype field; V1+ multi-archetype overlay (PRS-D3). ActorId source = EF_001 §5.1. Synthetic actors: forbidden V1 (PRS-Q11). |
| **OpinionModifierTable** | `HashMap<PersonalityArchetypeId, i8>` (-10..=+10) | Per-other-archetype baseline opinion modifier. V1 12×12 = 144 entries per RealityManifest (POST-SURVEY-Q1). All entries required at canonical seed (PRS-Q9 LOCKED — missing entries default 0 explicitly). |
| **SpeechPatternHints** | `Vec<String>` (V1+ NPC_002 LLM prompt enrichment) | V1 list of natural-language hints embedded in NPC persona prompt. V1+ formalized. |

**Cross-feature consumers:**
- PL_005b §2.1 InteractionSpeakPayload — utterance.speaker_voice resolves from personality.archetype.voice_register (resolves orphan ref)
- NPC_002 §6 priority Tier 2-3 — reads archetype for filtering
- NPC_001 persona assembly — speech_pattern_hints embedded in LLM prompt
- PL_005c §4 opinion drift calibration — opinion_modifier_table consumed at OpinionDelta computation (resolves INT-INT-D5)

---

## §2.5 Event-model mapping

| Path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Personality assigned at canonical seed | **EVT-T3 Derived** | `aggregate_type=actor_personality`, delta_kind=`AssignPersonality` | Aggregate-Owner role | Causal-ref REQUIRED |
| Personality admin override (Forge edit) | **EVT-T8 Administrative** | `Forge:EditPersonality { actor_id, before_archetype, after_archetype, reason }` | Forge role (WA_003) | AC-PRS-9 atomicity |
| V1+ Archetype evolution | **EVT-T3 Derived** | delta_kind=`EvolveArchetype` | Aggregate-Owner role | V1+ scheduler-driven |

**Closed-set proof:** all paths use active EVT-T* (T3 / T8). No new EVT-T*.

---

## §3 Aggregate inventory

### 3.1 `actor_personality` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_personality", tier = "T2", scope = "reality")]
pub struct ActorPersonality {
    pub reality_id: RealityId,
    pub actor_id: ActorId,
    pub archetype_id: PersonalityArchetypeId,    // V1 single archetype; V1+ multi-archetype overlay
    pub assigned_at_turn: u64,
    pub schema_version: u32,
}
```

- T2 + RealityScoped; per-actor across reality lifetime
- One row per (reality_id, actor_id) (every actor MUST have personality row except Synthetic)
- V1 single archetype; V1+ overlay extends additively
- Synthetic actors forbidden V1 (no actor_personality row; matches IDF_001 + IDF_004 + IDF_005 discipline)

### 3.2 `PersonalityArchetypeDecl`

```rust
pub struct PersonalityArchetypeDecl {
    pub archetype_id: PersonalityArchetypeId,
    pub display_name: I18nBundle,
    pub voice_register: VoiceRegister,
    pub opinion_modifier_table: HashMap<PersonalityArchetypeId, i8>,  // -10..=+10
    pub speech_pattern_hints: Vec<String>,
    pub canon_ref: Option<GlossaryEntityId>,
}

pub enum VoiceRegister {
    Formal,
    Neutral,
    Casual,
    Crude,
    Archaic,
}
```

---

## §4 Tier+scope (DP-R2)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `actor_personality` | T2 | T2 | Reality | ~0.5 per turn (NPC_002 priority + opinion drift + Speak voice) | ~0 V1 (canonical seed only); V1+ rare | Per-actor across lifetime; V1 mostly immutable |

---

## §5 DP primitives

### 5.1 Reads
- `dp::read_projection_reality::<ActorPersonality>(ctx, actor_id)` — NPC_002 priority + opinion drift + Speak voice
- `dp::read_reality_manifest(ctx).personality_archetypes` — RealityManifest extension

### 5.2 Writes
- `dp::t2_write::<ActorPersonality>(ctx, actor_id, AssignPersonalityDelta { archetype_id, reason })` — canonical seed
- V1+ `dp::t2_write::<ActorPersonality>(ctx, actor_id, EvolveArchetypeDelta { from, to })` — V1+ evolution

### 5.3 Subscriptions
- UI subscribes via DP-X invalidation
- NPC_002 reads at SceneRoster build (cached)

### 5.4 Capability
- `produce: [Derived]` + `write: actor_personality @ T2 @ reality` — IDF_003 owner
- `produce: [Administrative]` + sub-shape `Forge:EditPersonality` — Forge admin

---

## §6 Capability requirements

Same pattern as IDF_001/002. Standard `produce: [Derived]` + `write: actor_personality` for owner; `read: actor_personality` for consumers (NPC_002 + PL_005b).

---

## §7 Subscribe pattern

UI invalidation via DP-X. NPC_002 reads at SceneRoster build (cached for batch duration per NPC_002 §6).

---

## §8 Pattern choices

### 8.1 12 archetypes V1 (PRS-Q1 LOCKED per POST-SURVEY-Q1)
Core 8 + Loyal/Aloof/Ambitious/Compassionate. All 4 optional fill universal narrative gaps + wuxia archetypes (sect-disciple/recluse/antagonist/Buddhist-healer).

### 8.2 Single archetype V1 (PRS-Q2 LOCKED)
V1 single field; V1+ overlay extends additively (PRS-D3).

### 8.3 5-variant VoiceRegister V1 (PRS-Q3 LOCKED per POST-SURVEY-Q7)
Formal/Neutral/Casual/Crude/Archaic. Eloquent + Hesitant V1+ as context modifiers (NOT archetype defaults).

### 8.4 i8 -10..=+10 opinion modifier range (PRS-Q4 LOCKED)
Narrow range forces meaningful baselines; opinion delta is small mods on top of kind base.

### 8.5 Strict immutable V1 (PRS-Q5 LOCKED)
With AdminOverride audit-only edit. Matches IDF_001 / IDF_004 pattern.

### 8.6 Universal 8/12 archetypes V1 (PRS-Q6 LOCKED)
Reality-specific archetype packs V1+ (PRS-D4).

### 8.7 String list speech_pattern_hints V1 (PRS-Q7 LOCKED)
Natural-language hints for LLM prompt; structured enum couples too tightly to NLP V1+.

### 8.8 NPC_002 priority hook V1 wires up (PRS-Q8 LOCKED)
IDF_003 V1 ships data + NPC_002 wires up in same wave — must show end-to-end SPIKE_01 turn 5 reproducibility (Du sĩ Pious → Tier 3 priority).

### 8.9 Required all archetypes opinion matrix (PRS-Q9 LOCKED)
Canonical seed validates 12×12 = 144 matrix complete; missing entries default 0 explicitly.

### 8.10 Per-utterance voice register override allowed (PRS-Q10 LOCKED)
Default from archetype + per-utterance override via PL_005b InteractionSpeakPayload.

### 8.11 Synthetic actor forbidden V1 (PRS-Q11 LOCKED)
No actor_personality row for Synthetic actors. Matches IDF_001 RAC-Q1 + IDF_004 ORG-Q7.

---

## §9 Failure-mode UX

| Reject reason | Stage | When | Vietnamese reject copy (I18nBundle) |
|---|---|---|---|
| `personality.unknown_archetype_id` | 0 schema | ArchetypeId not in RealityManifest.personality_archetypes | "Loại tính cách không tồn tại trong thế giới này." |
| `personality.assignment_immutable` | 7 world-rule | V1 mutation rejected | "Tính cách đã định và không thể thay đổi." |
| `personality.opinion_modifier_invalid` | 0 schema | Value outside -10..=+10 | (Schema check; not user-facing) |

**`personality.*` V1 rule_id enumeration** (3 V1 rules):
1. `personality.unknown_archetype_id` — Stage 0
2. `personality.assignment_immutable` — Stage 7
3. `personality.opinion_modifier_invalid` — Stage 0

V1+ reservations: `personality.archetype_evolution_invalid_path`; `personality.overlay_conflict`.

---

## §10 Cross-service handoff

```
1. Canonical seed: RealityBootstrapper assigns archetype per actor.
2. PL_005b Speak: utterance.speaker_voice defaults from
   actor_personality.archetype.voice_register; per-utterance override allowed.
3. NPC_002 §6 priority Tier 2-3: reads archetype + opinion_modifier_table
   for compatibility scoring (matches PL_005c INT-INT-D5 resolved).
4. Opinion drift (PL_005c §4.2): final_opinion_delta = base_kind_delta +
   agent_archetype.opinion_mod[recipient_archetype] +
   recipient_archetype.opinion_mod[agent_archetype].
```

---

## §11 Sequence: Canonical seed (Wuxia 12-archetype bootstrap)

```
RealityBootstrapper @ reality-bootstrap:
  Read RealityManifest:
    personality_archetypes: 12 PersonalityArchetypeDecl entries (Stoic..Compassionate)
  Validate:
    - 12 archetypes unique
    - opinion_modifier_table 12×12 = 144 entries each (each archetype has full table)
    - voice_register valid 5-variant enum
  ✓

  For each canonical actor:
    Determine archetype_id (Lý Minh → "personality_idealist")
    dp::t2_write::<ActorPersonality>(ctx, actor_id, AssignPersonalityDelta {
      archetype_id: "personality_idealist",
      reason: AssignmentReason::CanonicalSeed,
    }) → T1 Derived
```

---

## §12 Sequence: Speak voice register resolution

```
PC LM01 /verbatim "Speak utterance":
  PL_005b InteractionSpeakPayload.utterance.speaker_voice:
    a. dp::read_projection_reality::<ActorPersonality>(ctx, LM01)
       → archetype="personality_idealist"
    b. RealityManifest.personality_archetypes["personality_idealist"].voice_register
       → Neutral
    c. utterance.speaker_voice = Neutral (default; or per-utterance override)
```

---

## §13 Sequence: Opinion drift (resolves PL_005c INT-INT-D5)

```
LM01 (Idealist) gives Lão Ngũ (Worldly) coins for room (Give kind):
  PL_005c §4 opinion drift calculation:
    base = +1 trust (Give Payment kind)
    agent_personality_mod = idealist.opinion_modifier_table["personality_worldly"]
                          → +0 (Idealists neutral toward Worldly)
    recipient_personality_mod = worldly.opinion_modifier_table["personality_idealist"]
                              → +1 (Worldly appreciates Idealist's earnest)
    final_opinion_delta = +1 + 0 + 1 = +2 trust
  npc_pc_relationship_projection updated +2 trust on Lão Ngũ → LM01.
```

---

## §14 Sequence: NPC_002 priority resolution (SPIKE_01 turn 5)

```
SPIKE_01 turn 5 — Lý Minh quotes book (literacy slip per IDF_002):
  NPC_002 §6 priority algorithm at SceneRoster:
    a. Read each NPC's actor_personality + actor_language_proficiency
    b. Du sĩ archetype=Pious + Cổ ngữ Fluent → Tier 3 knowledge_match primary
    c. Lão Ngũ archetype=Worldly + Cổ ngữ None → Tier 4 ambient
    d. Tiểu Thúy archetype=Innocent + Cổ ngữ None → Tier 1 filtered
  Reaction batch emits 2 NPCTurns (Du sĩ + Lão Ngũ); causal_refs to LM01 Speak T1.
```

---

## §15 Acceptance criteria

### 15.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-PRS-1** | Reality declares 12 V1 archetypes; LM01 with archetype=Idealist | actor_personality row committed; voice_register=Neutral |
| **AC-PRS-2** | Tiểu Thúy declared archetype=Innocent | row committed; voice_register=Casual |
| **AC-PRS-3** | LM01 Speaks utterance no explicit voice → resolved Neutral default | PL_005b validator resolves correctly |
| **AC-PRS-4** | LM01 (Idealist) Gives Lão Ngũ (Worldly); opinion delta computed | base(+1) + idealist→worldly(+0) + worldly→idealist(+1) = +2 trust |
| **AC-PRS-5** | NPC_002 priority SPIKE_01 turn 5 — Du sĩ Tier 3 + Lão Ngũ Tier 4 | priority algorithm resolves correctly per archetype + language |
| **AC-PRS-6** | Reject `personality.unknown_archetype_id` | Stage 0 reject |
| **AC-PRS-7** | V1 mutation rejected | Stage 7 `personality.assignment_immutable` |
| **AC-PRS-8** | I18nBundle archetype display_name across locales | Lý tưởng / Idealist / 理想主义者 |

### 15.2 V1+ scenarios (deferred)

| ID | Scenario | Defers to |
|---|---|---|
| **AC-PRS-V1+1** | Multi-archetype overlay (LM01 primary=Idealist + secondary=Loyal) | V1+ PRS-D3 |
| **AC-PRS-V1+2** | Archetype evolution (Innocent → Worldly via story-events) | V1+ scheduler V1+30d |

### 15.3 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-PRS-9** | Forge admin override LM01.archetype | EVT-T8 audit emitted; 3-write atomic |
| **AC-PRS-10** | Reality declares opinion_modifier value outside -10..=+10 | Stage 0 schema reject |

### 15.4 Status transition

- **DRAFT → CANDIDATE-LOCK:** boundary registered (`actor_personality` + `personality.*` 3 V1 rules + `personality_archetypes` RealityManifest extension + `PRS-*` stable-ID prefix). All AC-PRS-1..10 specified.
- **CANDIDATE-LOCK → LOCK:** all AC-PRS-1..10 V1-testable scenarios pass integration tests.

---

## §16 Boundary registrations

DRAFT promotion registers:

1. `_boundaries/01_feature_ownership_matrix.md`:
   - NEW row: `actor_personality` aggregate (T2/Reality, IDF_003 DRAFT)
   - EVT-T8: NEW `Forge:EditPersonality` (IDF_003 owns)
   - Stable-ID prefix: NEW `PRS-*` row
2. `_boundaries/02_extension_contracts.md`:
   - §1.4 `personality.*` namespace: 3 V1 rule_ids + 2 V1+ reservations
   - §2 RealityManifest: NEW `personality_archetypes: Vec<PersonalityArchetypeDecl>` REQUIRED V1
3. `_boundaries/99_changelog.md`: append IDF folder 7/15 entry

---

## §17 Deferrals

| ID | Item | Defer to |
|---|---|---|
| **PRS-D1** | Big-Five trait vector (OCEAN × 0..100) | V1+ NPC personality system |
| **PRS-D2** | Archetype evolution | V1+ scheduler V1+30d |
| **PRS-D3** | Multi-archetype overlay (primary + secondary) | V1+ enrichment |
| **PRS-D4** | Reality-specific archetype packs | V1+ enrichment |
| **PRS-D5** | Archetype-driven dialogue style (LLM prompt enrichment beyond hints) | V1+ NLP enhancement |
| **PRS-D6** | Per-personality stress response | V1+ status × personality interaction |
| **PRS-D7** | Archetype-conflict drift beyond opinion table | V1+ NPC personality enrichment |
| **PRS-D-NEW** | Context-aware voice register modifier system (Eloquent / Hesitant / Apologetic / Sarcastic / etc. as overlays on base 5) | V1+ when LLM persona prompt needs more granularity (per POST-SURVEY-Q7 design) |

---

## §18 Cross-references

**Foundation tier:**
- [`EF_001 §5.1 ActorId`](../00_entity/EF_001_entity_foundation.md#5-actorid--entityid-sibling-types)
- [`RES_001 §2.3 I18nBundle`](../00_resource/RES_001_resource_foundation.md)
- [`IDF_001 RaceId pattern`](IDF_001_race.md)
- [`IDF_002 LanguageId pattern`](IDF_002_language.md)

**Sibling IDF:**
- [`IDF_004 Origin`](IDF_004_origin_concept.md) — origin pack may suggest default archetype (V1+)
- [`IDF_005 Ideology`](IDF_005_ideology_concept.md) — Pious archetype + Daoist ideology jointly affect NPC reactions (V1+ enrichment)

**Consumers:**
- [`PL_005b §2.1`](../04_play_loop/PL_005b_interaction_contracts.md) — speaker_voice (orphan ref RESOLVED)
- [`NPC_002 §6`](../05_npc_systems/NPC_002_chorus.md) — priority Tier 2-3
- [`PL_005c INT-INT-D5`](../04_play_loop/PL_005c_interaction_integration.md) — per-personality opinion modifier RESOLVED
- NPC_001 persona assembly
- Future PCS_001 PC creation form

**Spike:**
- [`SPIKE_01 turn 5`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Du sĩ Pious Tier 3 priority

---

## §19 Implementation readiness checklist

- [x] §2-§19 complete per EF_001 pattern
- [x] 3 V1 namespace rules + 2 V1+ reservations
- [x] 12 V1 archetypes locked (POST-SURVEY-Q1)
- [x] 10 AC + 2 V1+ deferred
- [x] 8 deferrals (PRS-D1..D7 + PRS-D-NEW)
- [x] PL_005b speaker_voice orphan ref RESOLVED
- [x] PL_005c INT-INT-D5 per-personality opinion modifier RESOLVED

**Phase 3 cleanup applied 2026-04-26 (IDF_003 commit 8/15):**
- S1.1 §2 PersonalityArchetypeId typed newtype clarification
- S1.2 §3.1 Synthetic actor exclusion confirmed (PRS-Q11 LOCKED)
- S2.1 §10 Cross-feature opinion drift formula explicit (final = base + agent_mod[recipient] + recipient_mod[agent])
- S2.2 §15.4 LOCK criterion split
- S3.1 §17 PRS-D-NEW deferral for context-aware voice register modifier system

**Status transition:** DRAFT 2026-04-26 (Phase 3 applied) → **CANDIDATE-LOCK** in next commit (9/15) → LOCK after AC-PRS-1..10 pass.
