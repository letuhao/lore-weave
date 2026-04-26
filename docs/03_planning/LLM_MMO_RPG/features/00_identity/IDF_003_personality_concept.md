# IDF_003 — Personality Foundation (CONCEPT)

> **Conversational name:** "Personality" (PRS). Tier 5 Actor Substrate Foundation feature owning the per-reality `personality_archetype` closed-set enum (8-12 V1 archetypes) + per-actor `actor_personality` aggregate. Voice register field intersects (single source of truth for [PL_005b §2.1](../04_play_loop/PL_005b_interaction_contracts.md) `speaker_voice` field). NPC_002 §6 priority algorithm Tier 2-3 + opinion drift modifier consume; resolves [PL_005c INT-INT-D5](../04_play_loop/PL_005c_interaction_integration.md) (per-personality opinion modifier) deferral.
>
> **Category:** IDF — Identity Foundation (Tier 5 Actor Substrate)
> **Status:** CONCEPT 2026-04-26 (Q-decisions LOCKED 2026-04-26 per market survey + user "A" confirmation; ready for DRAFT promotion)
> **Stable IDs:** `PRS-A*` axioms · `PRS-D*` deferrals · `PRS-Q*` open questions
> **Builds on:** [EF_001 §5.1 ActorId](../00_entity/EF_001_entity_foundation.md); [PL_005b §2.1 InteractionSpeakPayload](../04_play_loop/PL_005b_interaction_contracts.md) speaker_voice; [NPC_002 §6 priority algorithm](../05_npc_systems/NPC_002_chorus.md); [PL_005c INT-INT-D5](../04_play_loop/PL_005c_interaction_integration.md) per-personality opinion modifier; [RES_001 §2.3 I18nBundle](../00_resource/RES_001_resource_foundation.md).
> **Defers to:** PCS_001 (PC personality at creation); NPC_001/003 (NPC archetype canonical seed); V1+ Big-Five trait system; V1+ archetype evolution.

---

## §1 Concept summary

Every actor has a personality archetype affecting Speak voice register + NPC_002 reaction priority + opinion drift calibration. V1 ships 8-12 closed-set archetypes (drawn from xianxia/wuxia tradition + Western literature crossover). Voice register integrates here (was orphan reference in PL_005b §2.1).

**V1 must-ship:**
- Closed-set `PersonalityArchetypeId` per reality (**12 archetypes V1 LOCKED 2026-04-26 per POST-SURVEY-Q1**)
- Per-actor `actor_personality` aggregate (T2/Reality scope)
- `PersonalityArchetypeDecl` declarative metadata: display_name (I18nBundle) + voice_register (5-variant enum) + opinion_modifier_table (per-other-archetype baseline) + speech_pattern_hints (V1+ NPC_002 prompt)
- NPC_002 §6 Tier 2-3 priority hook (consume archetype for reaction filtering)
- Opinion drift modifier per-personality table (resolves PL_005c INT-INT-D5)
- RealityManifest extension `personality_archetypes: Vec<PersonalityArchetypeDecl>` REQUIRED V1
- Default V1 archetypes (**12 universal** — applied to all reality presets per POST-SURVEY-Q1; opinion modifier matrix = 12×12 = 144 entries):
  - **Core 8** (POST-SURVEY base):
    - Stoic / Lãnh diện
    - Hothead / Nóng nảy
    - Cunning / Xảo trá
    - Innocent / Ngây thơ
    - Pious / Mộ đạo
    - Cynic / Hoài nghi
    - Worldly / Thế tục
    - Idealist / Lý tưởng
  - **Wuxia + universal coverage 4** (LOCKED V1 per POST-SURVEY-Q1):
    - Loyal / Trung nghĩa (sect-disciple archetype)
    - Aloof / Lạnh nhạt (recluse / hermit / assassin archetype)
    - Ambitious / Tham vọng (power-seeker / antagonist archetype)
    - Compassionate / Từ bi (Buddhist / healer archetype)

**V1+ deferred:**
- Big-Five trait vector (Openness/Conscientiousness/Extraversion/Agreeableness/Neuroticism × 0..100) (PRS-D1)
- Archetype evolution (PC develops from Innocent → Worldly via story events) (PRS-D2)
- Multi-archetype overlay (PC primary=Stoic + secondary=Loyal) (PRS-D3)
- Personality conflict drift (Hothead × Stoic baseline antagonism)
- Reality-specific archetype packs (Modern adds Corporate-archetype etc.)

---

## §2 Domain concepts (proposed)

| Concept | Maps to | Notes |
|---|---|---|
| **PersonalityArchetypeId** | Stable-ID newtype `String` (e.g., `personality_stoic`, `personality_hothead`) | Opaque per-reality. Closed-set declared in RealityManifest. |
| **PersonalityArchetypeDecl** | Author-declared per-reality entry | Name + voice_register + opinion_modifier_table + speech_pattern_hints + canon_ref. |
| **VoiceRegister** | Closed enum 5-variant: `Formal / Neutral / Casual / Crude / Archaic` | V1 = 5 variants. Consumed by PL_005b §2.1 InteractionSpeakPayload.utterance.speaker_voice. Stoic typically Formal/Neutral; Hothead Casual/Crude; Pious Archaic. |
| **actor_personality** | T2 / Reality aggregate; per-(reality, actor_id) row | Generic for PC + NPC. V1 single archetype field; V1+ multi-archetype overlay (PRS-D3). |
| **OpinionModifierTable** | `HashMap<PersonalityArchetypeId, i8>` | Per-other-archetype baseline opinion modifier. E.g., Stoic.opinion_modifier_table["personality_hothead"] = -3 (Stoics dislike Hotheads slightly); Loyal.opinion_modifier_table["personality_cunning"] = -8. Range -10..=+10. |
| **SpeechPatternHints** | `Vec<String>` (V1+ NPC_002 LLM prompt enrichment) | V1 list of natural-language hints embedded in NPC persona prompt: "Stoic NPCs use short factual statements; rare exclamation; reserved emotional display". V1+ formalized. |

**Cross-feature consumers:**
- PL_005b §2.1 InteractionSpeakPayload — utterance.speaker_voice resolves from personality.voice_register
- NPC_002 §6 priority algorithm — Tier 2-3 reads personality archetype for filtering (e.g., Hothead NPC prioritized for combat reactions; Stoic deprioritized)
- NPC_001 persona assembly — speech_pattern_hints embedded in LLM prompt
- PL_005c §4 opinion drift calibration — opinion_modifier_table consumed at OpinionDelta computation

---

## §3 Aggregate inventory (proposed)

### 3.1 `actor_personality` (T2 / Reality scope — primary)

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_personality", tier = "T2", scope = "reality")]
pub struct ActorPersonality {
    pub reality_id: RealityId,
    pub actor_id: ActorId,
    pub archetype_id: PersonalityArchetypeId,    // V1 single archetype; V1+ overlay
    pub assigned_at_turn: u64,
    pub schema_version: u32,
}
```

- T2 + RealityScoped: per-actor across reality lifetime
- One row per `(reality_id, actor_id)` (every actor MUST have personality row)
- V1 single archetype; V1+ multi-archetype overlay extends additively

### 3.2 `PersonalityArchetypeDecl`

```rust
pub struct PersonalityArchetypeDecl {
    pub archetype_id: PersonalityArchetypeId,
    pub display_name: I18nBundle,
    pub voice_register: VoiceRegister,
    pub opinion_modifier_table: HashMap<PersonalityArchetypeId, i8>,  // -10..=+10
    pub speech_pattern_hints: Vec<String>,                            // V1+ LLM prompt hints
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

## §4 Tier+scope (DP-R2 — proposed)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `actor_personality` | T2 | T2 | Reality | ~0.5 per turn (NPC_002 priority + opinion drift + Speak voice) | ~0 per turn V1 (canonical seed only); V1+ rare (archetype evolution PRS-D2) | Per-actor across reality lifetime; eventual consistency OK; V1 mostly immutable. |

---

## §5 Cross-feature integration (proposed)

### 5.1 NPC_002 §6 priority algorithm hook

NPC_002 §6 Tier 2-3 consume archetype:

- Tier 2 (high opinion + relationship match): personality compatibility check via opinion_modifier_table — Loyal NPCs prioritized for ally reactions; Cunning NPCs for betrayal reactions
- Tier 3 (knowledge match): no archetype filtering V1
- Tier 4 (ambient): archetype affects reaction style (Stoic = silent observation; Worldly = murmured comment)

### 5.2 Opinion drift modifier (resolves PL_005c INT-INT-D5)

PL_005c §4.2 opinion delta calibration table V1 ships defaults; IDF_003 layer adds per-personality overlay:

```
final_opinion_delta = base_delta_from_kind(Speak/Strike/Give/etc.)
                    + agent_archetype.opinion_modifier_table[recipient_archetype]
                    + recipient_archetype.opinion_modifier_table[agent_archetype]  // mutual
```

Example: Lý Minh (Idealist) gives Lão Ngũ (Worldly) coins. Base Give+Payment delta = +1 trust. Idealist→Worldly modifier = +0; Worldly→Idealist = +1 (Worldly appreciates idealist's earnest). Final = +2 trust.

### 5.3 Speak voice register (resolves PL_005b orphan ref)

`InteractionSpeakPayload.utterance.speaker_voice: VoiceRegister` resolves from `actor_personality.archetype_id → PersonalityArchetypeDecl.voice_register`. PL_005b currently references `PCS_001 PcVoiceRegister` (which doesn't exist V1) — IDF_003 fills this gap as foundation.

PL_005b cross-ref update on closure: replace "inherited from PCS_001 PcVoiceRegister" → "resolved from IDF_003 actor_personality.archetype.voice_register".

### 5.4 Reject UX (personality.* namespace — proposed V1)

| rule_id | Stage | When |
|---|---|---|
| `personality.unknown_archetype_id` | 0 schema | ArchetypeId not in RealityManifest.personality_archetypes |
| `personality.assignment_immutable` | 7 world-rule | V1 attempt to mutate actor_personality.archetype_id rejected (V1+ archetype evolution lifts) |
| `personality.opinion_modifier_invalid` | 0 schema | OpinionModifierTable value outside -10..=+10 range (canonical seed validation) |

V1+ reservations: `personality.archetype_evolution_invalid_path` (V1+ when evolution ships); `personality.overlay_conflict` (V1+ multi-archetype).

---

## §6 RealityManifest extension (proposed)

```rust
pub struct RealityManifest {
    // ... existing fields ...
    pub personality_archetypes: Vec<PersonalityArchetypeDecl>,    // NEW V1 from IDF_003
}
```

REQUIRED V1.

**V1 default 12 archetypes** (universal — applied to Wuxia + Modern + Sci-fi presets uniformly per POST-SURVEY-Q1 LOCKED 2026-04-26; reality-specific archetypes V1+):

```
Core 8:    [Stoic, Hothead, Cunning, Innocent, Pious, Cynic, Worldly, Idealist]
Wuxia+universal 4: [Loyal, Aloof, Ambitious, Compassionate]
Total V1:  12 archetypes
```

Reality presets ship with these 12 + opinion_modifier_table populated with realistic baselines (12×12 = 144 entries; populate iteratively at DRAFT — start with diagonal-zero matrix, fill quadrants per-archetype-pair semantics).

---

## §7 V1 acceptance criteria (preliminary)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-PRS-1** | Reality declares 12 V1 archetypes; LM01 created with archetype=Idealist | actor_personality row committed; voice_register=Neutral; UI displays Lý tưởng badge |
| **AC-PRS-2** | NPC tieu_thuy declared with archetype=Innocent | actor_personality row committed; voice_register=Casual |
| **AC-PRS-3** | LM01 Speaks utterance with no explicit speaker_voice | Speak validator resolves voice_register from actor_personality.archetype.voice_register = Neutral |
| **AC-PRS-4** | LM01 (Idealist) Gives coins to Lão Ngũ (Worldly) for lodging | OpinionDelta computed = base(+1) + idealist→worldly(+0) + worldly→idealist(+1) = +2 trust |
| **AC-PRS-5** | NPC_002 priority Tier 2 — Du sĩ (Pious) vs Lão Ngũ (Worldly) reaction to Lý Minh's literacy slip | Du sĩ archetype=Pious (Tier 2 high opinion + book-quote match → primary candidate); Lão Ngũ archetype=Worldly (Tier 4 ambient) |
| **AC-PRS-6** | Reject `personality.unknown_archetype_id` when assigning unknown ID | rejected at Stage 0 schema |
| **AC-PRS-7** | Mutate actor_personality.archetype_id rejected V1 | rejected with `personality.assignment_immutable` |
| **AC-PRS-8** | I18nBundle resolves Lý tưởng (Vietnamese) / Idealist (English) | display_name correctly localized |

---

## §8 Open questions (CONCEPT — user confirm before DRAFT)

| ID | Question | Default proposal |
|---|---|---|
| **PRS-Q1** | Archetype count V1 — 8 (current) vs 12 (add Loyal/Aloof/Ambitious/Compassionate)? | ✅ **LOCKED 2026-04-26 per POST-SURVEY-Q1:** **12 V1** — all 4 optional archetypes (Loyal/Aloof/Ambitious/Compassionate) are universal + wuxia-relevant. Without them: sect-disciple → Loyal exact (vs Idealist loose); Ma đạo antagonist → Ambitious exact (vs Cunning loose); Buddhist healer → Compassionate exact (vs Pious loose); recluse → Aloof exact (vs Cynic loose). Opinion modifier matrix 12×12 = 144 entries (manageable). |
| **PRS-Q2** | Multi-archetype overlay V1 (primary + secondary) vs single V1? | **Single V1** — overlay = PRS-D3 V1+ enrichment; single archetype sufficient for SPIKE_01 NPC reactions |
| **PRS-Q3** | Voice register count — 5 (current) vs 7 (add Eloquent + Hesitant)? | ✅ **LOCKED 2026-04-26 per POST-SURVEY-Q7:** **5 V1** (Formal/Neutral/Casual/Crude/Archaic). Eloquent + Hesitant feel like CONTEXT modifiers (not archetype defaults) — V1+ landing as overlay layer (PRS-D-NEW: context-aware voice register modifier system). |
| **PRS-Q4** | Opinion modifier range — i8 -10..=+10 (current) vs -5..=+5 vs -100..=+100? | **i8 -10..=+10 V1** — narrow range forces meaningful baselines; opinion delta is small mods on top of kind base; V1+ may widen if needed |
| **PRS-Q5** | Mutation V1 — strict immutable (current) vs allow Admin override V1? | **Strict immutable V1** with AdminOverride audit-only edit (matches IDF_001 RAC-Q1 pattern) |
| **PRS-Q6** | Per-reality archetype packs (Wuxia archetypes vs Modern archetypes) vs universal 8 archetypes (current)? | **Universal 8 V1** — simplifies V1; reality-specific archetype packs V1+ enrichment |
| **PRS-Q7** | speech_pattern_hints field — String list V1 (current) vs structured `Vec<SpeechPatternHint>` enum? | **String list V1** — natural-language hints for LLM prompt; structured enum couples too tightly to NLP V1+ |
| **PRS-Q8** | NPC_002 priority hook — V1 ships actual filtering vs V1 stores data only (NPC_002 wires V1+)? | **V1 ships data + NPC_002 wires up in same wave** — IDF_003 must show end-to-end SPIKE_01 turn 5 reproducibility (Du sĩ Pious → Tier 2 priority) |
| **PRS-Q9** | Opinion modifier table — required for all archetypes (8×8=64 entries) vs optional with default 0? | **Required all archetypes V1** — canonical seed validates 8×8 matrix complete; missing entries default 0 explicitly (avoid "unknown means undefined" trap) |
| **PRS-Q10** | Voice register Speak override — actor_personality.archetype default vs per-utterance override? | **Default + per-utterance override allowed V1** — actor may speak Formal in court vs Casual at home; PL_005b InteractionSpeakPayload allows explicit voice_register field overriding default |
| **PRS-Q11** | Synthetic actor archetype — required (Synthetic-default Neutral) vs forbidden (Synthetic actors have no personality)? | **Forbidden V1** — Synthetic actors don't have actor_personality row; their writes (e.g., ChorusOrchestrator) are mechanical and don't need archetype data |

---

## §9 Deferrals (V1+ landing point)

| ID | Item | Defer to |
|---|---|---|
| **PRS-D1** | Big-Five trait vector (OCEAN × 0..100) on top of archetype | V1+ NPC personality system |
| **PRS-D2** | Archetype evolution (PC story-driven Innocent → Worldly) | V1+ when scheduler ships V1+30d |
| **PRS-D3** | Multi-archetype overlay (primary + secondary) | V1+ enrichment |
| **PRS-D4** | Reality-specific archetype packs (Modern adds Corporate-archetype) | V1+ enrichment |
| **PRS-D5** | Archetype-driven dialogue style (LLM prompt enrichment beyond hints) | V1+ NLP enhancement |
| **PRS-D6** | Per-personality stress response (Hothead under stress → Crude voice; Stoic stays Formal) | V1+ when status effects + personality interact |
| **PRS-D7** | Archetype-conflict drift (Hothead × Stoic baseline antagonism beyond opinion table) | V1+ NPC personality enrichment |

---

## §10 Cross-references

**Foundation tier:**
- [`EF_001`](../00_entity/EF_001_entity_foundation.md) §5.1 — ActorId
- [`RES_001`](../00_resource/RES_001_resource_foundation.md) §2.3 — I18nBundle

**Sibling IDF:**
- [`IDF_001 Race`](IDF_001_race_concept.md) — independent
- [`IDF_002 Language`](IDF_002_language_concept.md) — independent
- [`IDF_004 Origin`](IDF_004_origin_concept.md) — origin pack may suggest default archetype (V1+)
- [`IDF_005 Ideology`](IDF_005_ideology_concept.md) — Pious archetype + Daoist ideology jointly affect NPC reactions

**Consumers:**
- [`PL_005b §2.1`](../04_play_loop/PL_005b_interaction_contracts.md) — InteractionSpeakPayload speaker_voice (orphan ref resolved)
- [`NPC_002 §6`](../05_npc_systems/NPC_002_chorus.md) — priority algorithm Tier 2-3
- [`PL_005c INT-INT-D5`](../04_play_loop/PL_005c_interaction_integration.md) — per-personality opinion modifier (resolved by IDF_003)
- NPC_001 persona assembly
- Future PCS_001 PC creation form

**Boundaries (DRAFT registers):**
- `_boundaries/01_feature_ownership_matrix.md` — `actor_personality` aggregate
- `_boundaries/02_extension_contracts.md` §1.4 — `personality.*` namespace (3 V1 rules + 2 V1+ reservations)
- `_boundaries/02_extension_contracts.md` §2 RealityManifest — `personality_archetypes` extension

**Spike:**
- [`SPIKE_01 turn 5`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Du sĩ (Pious) Tier 2 priority validation

---

## §11 CONCEPT → DRAFT promotion checklist

Same pattern as IDF_001/002 (see those concept-notes §11). Boundary registrations: `actor_personality` aggregate; `personality.*` namespace (3 V1 rules); `personality_archetypes: Vec<PersonalityArchetypeDecl>` RealityManifest extension; Stable-ID prefix `PRS-*`.

**Cross-feature touch on DRAFT:**
- PL_005b closure pass UPDATE — `speaker_voice` reference from "PCS_001 PcVoiceRegister" → "IDF_003 actor_personality.archetype.voice_register" (resolves orphan ref)
- PL_005c INT-INT-D5 deferral marked RESOLVED via IDF_003 opinion_modifier_table
