# PL_005b — Interaction Contracts (Per-Sub-Type Payload Schemas)

> **Continued from:** [`PL_005_interaction.md`](PL_005_interaction.md). That file holds the conceptual layer (§1-§19): 4-role pattern + 5 V1 InteractionKinds + closed-set proof + Event-model mapping + DP primitives + capability + subscribe + pattern choices + failure UX + cross-service handoff + 5 high-level sequences + 6 acceptance criteria + deferrals. This file holds the **contract layer (§1-§12)**: concrete payload schemas per kind + OutputDecl taxonomy + per-kind validator subset + per-kind reject rule_ids + expanded acceptance scenarios.
>
> **Conversational name:** "Interaction contracts" (INT-C). Read [`PL_005_interaction.md`](PL_005_interaction.md) FIRST — this file assumes you know the 4-role pattern and 5 V1 kinds.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** DRAFT 2026-04-26 (Phase 2 of PL_005 design)
> **Stable IDs in this file:** none new — references PL_005 §2 domain concepts. All sub-type ownership already registered in [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md).
> **Builds on:** PL_005 §1-§19. Same DP contracts + same Event-model mappings.

---

## §1 Common payload base (inherited by all 5 V1 kinds)

Every Interaction sub-type extends this base. Per [PL_005 §2](PL_005_interaction.md#2-domain-concepts) 4-role pattern + ProposedOutputs/ActualOutputs split. **TargetRef + ActorId types inherit from PL_005 §2** — PlaceId(ChannelId) newtype per PF_001 §3.1; ActorId from EF_001 §5.1.

```rust
pub struct InteractionPayloadBase {
    // 4-role pattern (PL_005 §2)
    pub agent: Option<ActorId>,             // None ⇒ shifts to EVT-T5 Generated category (per Q2/B3)
                                            // ActorId source-of-truth: EF_001 §5.1 (sibling of EntityId)
    pub tools: Vec<InstrumentRef>,          // 0+ — empty for body/non-physical
    pub direct_targets: Vec<TargetRef>,     // 1+ — receivers of direct interaction
                                            // TargetRef::Place uses PlaceId(ChannelId) newtype per PF_001 §3.1
    pub indirect_targets: Vec<TargetRef>,   // 0+ V1 — bystanders observable in cell at fire-time

    // Outputs (atomic at validator stage per Q6/B4)
    pub proposed_outputs: Vec<OutputDecl>,  // agent's INTENT; populated at emit
    pub actual_outputs: Vec<OutputDecl>,    // world-rule-DERIVED outcome; populated by validator pre-commit

    // Audit + canon
    pub canon_drift_flags: Vec<DriftFlag>,  // populated by A6 (PL_001 §3.5 inherit)
    pub narrator_text: Option<String>,      // post-validation LLM narration (≤2 KB after A6 sanitize);
                                            // Speak-kind narrator_text flows through CSC_001 §[layer 4] LLM creative narration
    pub causal_refs: Vec<CausalRef>,        // EVT-A6 typed causal-refs (REQUIRED for NPCTurn-type Interactions)
}

pub struct OutputDecl {
    pub target: TargetRef,                  // which entity is affected
    pub aggregate_type: String,             // closed-set per per-kind allowlist (§8 below)
    pub delta: serde_json::Value,           // typed per (aggregate_type, delta_kind)
    pub estimated_severity: SeverityLevel,  // for Lex evaluation + audit
}

pub enum SeverityLevel {
    Negligible,  // cosmetic / observational only
    Minor,       // small state mutation (opinion +1)
    Moderate,    // notable state mutation (HP delta < 30%)
    Major,       // significant state mutation (HP delta 30-70%; status_flag transition)
    Critical,    // life-changing (mortality transition / faction reputation flip)
}
```

**Per-kind contracts below extend this base.** Each kind specifies: required fields beyond base, allowed `InstrumentRef` variants, allowed `TargetRef` variants, allowed agent kinds, ProposedOutputs allowed `aggregate_type` set, kind-specific reject rule_ids, validator subset.

---

## §2 Interaction:Speak contract

**Use case:** PC/NPC speaks aloud to one or more listeners. SPIKE_01 turn 5 literacy slip is canonical example.

### 2.1 Payload extension

```rust
pub struct InteractionSpeakPayload {
    pub base: InteractionPayloadBase,

    // Speak-specific
    pub verbal_kind: VerbalKind,            // mirror tools[0] for explicit type discrimination
    pub utterance: Utterance,               // the actual content
    pub volume: VolumeKind,                 // affects who hears (visibility filter)
    pub language: LanguageRef,              // which language used (canon-drift body-knowledge check)
}

pub enum VerbalKind {
    Quote,          // quoting external text (e.g., book passage — SPIKE_01 turn 5)
    Statement,      // direct speech (assertion)
    Question,       // interrogative
    Declaration,    // formal pronouncement
    Whisper,        // private — visibility limited to direct_targets
    Cry,            // exclamation / call-out
}

pub struct Utterance {
    pub raw_text: String,           // ≤2 KB after A6 sanitization
    pub speaker_voice: VoiceRegister, // inherited from PCS_001 PcVoiceRegister
}

pub enum VolumeKind {
    Whisper,        // direct_targets only; bystanders typically can't hear
    Normal,         // cell members (current visibility per DP-A18 channel)
    Shout,          // V1+ — extends visibility to ancestor channel
}
```

### 2.2 Allowed InstrumentRef

| Variant | Allowed? | Notes |
|---|:---:|---|
| Verbal(VerbalKind) | ✅ | exactly 1; mirrors verbal_kind field |
| Item | ❌ | Items don't speak (V2+: Items with magic voices) |
| BodyPart | ❌ | (V1+: gestures via Action sub-type, future) |
| Ability | ❌ | (V2+: telepathic communication via Ability) |

### 2.3 Allowed TargetRef

| Variant | direct_targets | indirect_targets | Notes |
|---|:---:|:---:|---|
| Actor | ✅ 1+ | ✅ 0+ | listeners (direct) + bystanders (indirect) |
| Place | ❌ V1 | ❌ V1 | (V2+ broadcast to channel — Shout extension) |
| Item | ❌ | ❌ | (Items don't listen) |

### 2.4 Allowed agent

| ActorId variant | Allowed? | Notes |
|---|:---:|---|
| Pc(PcId) | ✅ | typical PC speech |
| Npc(NpcId) | ✅ | NPC reaction speech |
| Synthetic | ❌ V1 | (Synthetic actors don't speak in V1) |
| Admin | ❌ | (Admin uses EVT-T8 Administrative for system messages) |
| None (no agent) | ❌ | Speak requires speaker |

### 2.5 ProposedOutputs allowed

Speak is **observational** — typically `proposed_outputs: []`. Outputs come from Chorus reactions (NPC_002), not Speak directly.

| aggregate_type | allowed delta_kind | When |
|---|---|---|
| (none expected V1) | — | typical case empty |

### 2.6 ActualOutputs (validator-derived)

| aggregate_type | delta_kind | When |
|---|---|---|
| (none) | — | typical Speak |
| `npc_pc_relationship_projection` | OpinionDelta (small, e.g., ±1) | rare — when Speak content directly references an NPC's relationship |
| canon_drift_flags populated | (in payload, not aggregate) | A6 detects body-knowledge mismatch (SPIKE_01 turn 5) |

### 2.7 Validation rules (kind-specific)

- `agent` MUST be `Pc` or `Npc` (not Synthetic / Admin / None)
- `tools` MUST contain exactly 1 `InstrumentRef::Verbal(VerbalKind)`
- `direct_targets` MUST be 1+ Actor refs
- agent MUST NOT be in `direct_targets` (no self-monologue V1; per INT-D9)
- All targets MUST be in same cell as agent (V1 same-cell invariant)
- `utterance.raw_text` non-empty after A6 sanitization
- `volume = Whisper` limits `direct_targets` to exactly 1 (no group whisper V1)
- `volume = Shout` rejected V1 (V1+ ancestor channel feature)

### 2.8 Reject rule_ids (per `interaction.*` namespace)

| rule_id | Trigger | Vietnamese reject copy |
|---|---|---|
| `interaction.speak.no_targets` | `direct_targets` empty | "Bạn nói nhưng không ai để nghe." |
| `interaction.speak.target_not_in_cell` | cross-cell V1 reject | "[Tên người đó] không ở đây để nghe." |
| `interaction.speak.self_monologue` | agent in direct_targets | "Bạn không thể nói với chính mình. (V1+ sẽ hỗ trợ độc thoại nội tâm.)" |
| `interaction.speak.empty_utterance` | sanitized text empty | "Lời nói trống rỗng." |
| `interaction.speak.whisper_multi_target` | Whisper with >1 target | "Thì thầm chỉ thì thầm được với một người tại một lúc." |
| `interaction.speak.shout_unsupported` | Volume=Shout V1 | "(V1+ hỗ trợ tiếng hét vang đến khu vực rộng hơn.)" |

---

## §3 Interaction:Strike contract

**Use case:** PC/NPC physically attacks another actor. V1 minimum for combat — full combat feature deferred to V1+.

### 3.1 Payload extension

```rust
pub struct InteractionStrikePayload {
    pub base: InteractionPayloadBase,

    // Strike-specific
    pub strike_kind: StrikeKind,            // physical motion type
    pub strike_intent: StrikeIntent,        // outcome the agent intends
    pub force_estimate: ForceLevel,         // feeds physics engine (Lex)
}

pub enum StrikeKind {
    Slash,      // edge-weapon swing (sword, blade)
    Thrust,     // pointed-weapon thrust (spear, dagger)
    Punch,      // body-weapon — fist
    Kick,       // body-weapon — leg
    Push,       // non-damaging displacement
    // V1+: Throw, Bite, Grapple
}

pub enum StrikeIntent {
    Lethal,     // intent to kill — mortality-config-aware
    Disarm,     // V1+ — remove tool from target's hand (needs Item aggregate)
    Stun,       // V1+ — apply status_flag(Stunned) — needs PCS_001 stat extensions
    Restrain,   // V1+ — grapple
}

pub enum ForceLevel {
    Light,      // exploratory / warning
    Medium,     // normal combat
    Heavy,      // committed strike
}
```

### 3.2 Allowed InstrumentRef

| Variant | Allowed? | Notes |
|---|:---:|---|
| Item(weapon) | ✅ | sword / spear / staff / etc. — V1+ Item aggregate validates wielding |
| BodyPart(BodyPartKind) | ✅ | fist / leg / etc. |
| Verbal | ❌ | Verbal damage is `Threaten` sub-type (V1+) |
| Ability | ❌ V1 | (V1+ — Lex axiom-allowed abilities like Qigong) |

### 3.3 Allowed TargetRef

| Variant | direct_targets | indirect_targets | Notes |
|---|:---:|:---:|---|
| Actor | ✅ exactly 1 V1 | ✅ 0+ | single target V1; multi-target sweep V1+ per INT-D3 |
| Item | ❌ V1 | ❌ | (V1+ — strike to break an item) |
| Place | ❌ | ❌ | (Strike a wall is non-meaningful V1) |

### 3.4 Allowed agent

| ActorId variant | Allowed? |
|---|:---:|
| Pc | ✅ |
| Npc | ✅ |
| Synthetic | ❌ V1 |
| Admin | ❌ |
| None | ❌ V1 (V1+ environmental hazards as None-agent Strikes via EVT-T5 Generated) |

### 3.5 ProposedOutputs allowed

| aggregate_type | delta_kind | When |
|---|---|---|
| `pc_stats_v1_stub` | HpDelta(negative) | always — agent intends damage |
| `pc_mortality_state` | MortalityTransition (Alive→Dying) | only when StrikeIntent=Lethal AND target current_hp ≤ proposed damage |

V1 Strike emits agent's INTENT; world-rule clamps to actual.

### 3.6 ActualOutputs (validator-derived)

| aggregate_type | delta_kind | When |
|---|---|---|
| `pc_stats_v1_stub` | HpDelta clamped to [target.hp..0] | always |
| `pc_mortality_state` | MortalityTransition | derived if hp would reach 0; transition determined per `mortality_config` (Permadeath → Dead; RespawnAtLocation → Dying; Ghost → Ghost) |
| `npc_pc_relationship_projection` | OpinionDelta (large negative) | when target is NPC; opinion plummets per relationship_drift rules |

### 3.7 Validation rules (kind-specific)

- agent + target both `pc_mortality_state` MUST be Alive (not Dying / Dead / Ghost)
- tool[0]=Item: V1+ Item aggregate MUST confirm agent wields tool (V1 placeholder check via PC stats stub `wielded_tool_ref`)
- tool[0]=BodyPart: agent body has that part (V1: assume yes)
- target in same cell as agent
- StrikeIntent=Disarm/Stun/Restrain rejected V1 (V1+ extensions)
- ForceLevel=Heavy with no weapon (BodyPart only) caps damage at PCS_001 unarmed cap

### 3.8 Reject rule_ids

| rule_id | Trigger | Vietnamese reject copy |
|---|---|---|
| `interaction.strike.target_dead` | target Mortality≠Alive | "Mục tiêu đã không còn ở thế giới này." |
| `interaction.strike.agent_dead` | agent Mortality≠Alive | (Should not reach validator — turn-slot rejected earlier) |
| `interaction.strike.tool_not_held` | Item not in agent inventory | "Bạn không cầm [vũ khí] trong tay." |
| `interaction.strike.target_not_in_cell` | cross-cell reject | "Mục tiêu không ở đây để bạn tấn công." |
| `interaction.strike.intent_unsupported` | V1 Disarm/Stun/Restrain | "(V1+ sẽ hỗ trợ chiến đấu phức tạp hơn.)" |
| `interaction.strike.lex_forbidden` | Lex axiom rejects (e.g., MagicSpells in non-magic reality) | (Lex-derived copy from WA_001) |

---

## §4 Interaction:Give contract

**Use case:** PC/NPC transfers item(s) to another actor. SPIKE_01 turn 8 (LM01 pays Lão Ngũ for room) is canonical.

### 4.1 Payload extension

```rust
pub struct InteractionGivePayload {
    pub base: InteractionPayloadBase,

    // Give-specific
    pub gift_count: u32,                    // for stackable items
    pub give_intent: GiveIntent,            // why agent is giving
    pub price_paid_for: Option<TransactionPurpose>,  // if Payment: what for
}

pub enum GiveIntent {
    Gift,           // unconditional offering
    Payment,        // exchange for service/goods
    Bribe,          // attempt to influence behavior
    Tribute,        // formal/ritual offering
}

pub enum TransactionPurpose {
    Lodging,        // SPIKE_01 turn 8 — paying for room
    Food,
    Information,
    Service,
    Other(String),
}
```

### 4.2 Allowed InstrumentRef

| Variant | Allowed? | Notes |
|---|:---:|---|
| Item | ✅ exactly 1+ | item(s) being given |
| Verbal/BodyPart/Ability | ❌ | non-Item gifts (V2+: gift of intangibles) |

### 4.3 Allowed TargetRef

| Variant | direct_targets | indirect_targets | Notes |
|---|:---:|:---:|---|
| Actor | ✅ exactly 1 | ✅ 0+ | recipient |
| Item/Place | ❌ | ❌ | (you don't give to a place) |

### 4.4 Allowed agent

Pc / Npc only; Synthetic and Admin don't give.

### 4.5 ProposedOutputs allowed

| aggregate_type | delta_kind | When |
|---|---|---|
| `pc_inventory` (V1+) | InventoryDelta (item -gift_count) on agent | V1+ when Item aggregate ships |
| `npc_inventory` (V1+) | InventoryDelta (item +gift_count) on recipient | V1+ |
| `npc_pc_relationship_projection` | OpinionDelta | always — opinion drift on Give |

### 4.6 ActualOutputs (validator-derived)

V1 simplification (no Item aggregate yet): inventory deltas are placeholder-logged only; opinion delta is the canonical visible outcome.

| aggregate_type | delta_kind | When |
|---|---|---|
| `npc_pc_relationship_projection` | OpinionDelta scaled by GiveIntent | always; magnitude varies (Bribe = smaller +; Gift = larger +; Tribute = formal-context-dependent) |

### 4.7 Validation rules

- tool[0]=Item: V1 placeholder check (agent's inventory references tool's glossary-entity-id); V1+ enforces via Item aggregate
- recipient acceptance: V1 NPCs always accept unless world-rule rejects (e.g., `mortality_config` says recipient is Dead)
- gift_count > 0
- target in same cell

### 4.8 Reject rule_ids

| rule_id | Trigger | Vietnamese reject copy |
|---|---|---|
| `interaction.give.tool_not_held` | item not in agent inventory | "Bạn không có [item] để tặng." |
| `interaction.give.recipient_unable` | recipient Mortality≠Alive | "Người nhận đã không còn." |
| `interaction.give.recipient_refused` | NPC opinion below acceptance threshold | "[NPC] không nhận." |
| `interaction.give.target_not_in_cell` | cross-cell | "Người nhận không ở đây." |
| `interaction.give.zero_count` | gift_count = 0 | "Số lượng phải lớn hơn 0." |

---

## §5 Interaction:Examine contract

**Use case:** PC inspects something visible — Item / Place / Actor — to learn details. May trigger Oracle query (PL-16) for canonical facts.

### 5.1 Payload extension

```rust
pub struct InteractionExaminePayload {
    pub base: InteractionPayloadBase,

    // Examine-specific
    pub examine_depth: ExamineDepth,        // how thorough
    pub examine_focus: ExamineFocus,        // what to look for
    pub oracle_query_id: Option<OracleQueryId>,  // populated post-validate if Oracle invoked
}

pub enum ExamineDepth {
    Glance,         // ~3s fiction — surface only
    Inspect,        // ~30s — moderate detail
    DeepStudy,      // ~5min — full detail; V1+ may reveal Hidden focus
}

pub enum ExamineFocus {
    Surface,        // visible attributes
    Detail,         // specific feature (e.g., "the seal on the scroll")
    Hidden,         // V1+ — requires DeepStudy + skill check
}
```

### 5.2 Allowed InstrumentRef

| Variant | Allowed? | Notes |
|---|:---:|---|
| (none) | ✅ V1 | examining = looking; no tool needed |
| Item | ❌ V1 | (V1+ — magnifying glass / lens / spell scroll) |
| BodyPart | ❌ | (eyes are implicit) |
| Ability | ❌ V1 | (V1+ — DetectMagic / TrueSight abilities) |

### 5.3 Allowed TargetRef (ExamineTarget extension)

Examine uses the **ExamineTarget enum** (PL_005 §2 — extends TargetRef with `MapNode` variant, resolves PF-Q4 + MAP-Q3).

| Variant | direct_targets | Notes |
|---|:---:|---|
| `ExamineTarget::Actor(ActorId)` | ✅ exactly 1 | examining a person |
| `ExamineTarget::Item(GlossaryEntityId)` | ✅ exactly 1 | examining an object (glossary-id ref V1; runtime Item aggregate V1+) |
| `ExamineTarget::Place(PlaceId)` | ✅ exactly 1 | examining a location/scene at cell tier (per PF_001 §3.1; resolves PF-Q4) — see PL_005 §14.1 sequence |
| `ExamineTarget::MapNode(ChannelId, ChannelTier)` | ✅ exactly 1 V1+ | examining non-cell map node ("examine the country") — V1 schema accepts; V1+ author-content-gated runtime activation per INT-D11 (resolves MAP-Q3) — see PL_005 §14.2 sequence |
| (multi-target) | ❌ V1 | one-thing-at-a-time |

`indirect_targets`: V2+ when bystander-observer feature ships (see §11 INT-D4).

**ExamineTarget::MapNode V1 semantics:** schema accepts the variant + Stage 3.5.c map_layout validates ChannelTier matches map_layout aggregate; world-rule (Stage 7) rejects with `interaction.intent_unsupported` until first author reality registers MapNode-examine flow.

### 5.4 Allowed agent

Pc / Npc. NPCs may examine via Chorus orchestration (Du sĩ examines book on his table).

### 5.5 ProposedOutputs allowed

Typically empty — Examine is observational.

### 5.6 ActualOutputs (validator-derived)

| aggregate_type | delta_kind | When |
|---|---|---|
| `oracle_audit_log` (DP-internal) | OracleQueryRecorded | when Examine triggers Oracle query |
| (V1+ knowledge_tags on PCS_001) | KnowledgeAccrual | V1+ when PCS_001 knowledge_tags structure ships |
| (visibility marker — feature-defined) | "agent looks at target" — observable to others | V1+ bystander system |

### 5.7 Validation rules

- target in same cell (V1)
- target visible (V1+: stealth system may hide targets)
- ExamineDepth=DeepStudy requires turn-slot ≥5min remaining
- Hidden focus rejected V1 (V1+ skill check)

### 5.8 Reject rule_ids

| rule_id | Trigger | Vietnamese reject copy |
|---|---|---|
| `interaction.examine.target_not_visible` | V1+ stealth hides target | "Không thấy [mục tiêu] để xem xét." |
| `interaction.examine.target_not_in_cell` | cross-cell | "[Mục tiêu] không ở đây." |
| `interaction.examine.deep_study_unavailable` | turn-slot too short | "Quan sát kỹ cần thêm thời gian." |
| `interaction.examine.hidden_focus_unsupported` | V1 Hidden focus | "(V1+ sẽ hỗ trợ tìm kiếm chi tiết ẩn.)" |

---

## §6 Interaction:Use contract

**Use case:** PC uses an Item on a target — key on lock, potion on self/ally, tool on object. V1+ requires Item aggregate; V1 works with limited Item glossary refs.

### 6.1 Payload extension

```rust
pub struct InteractionUsePayload {
    pub base: InteractionPayloadBase,

    // Use-specific
    pub use_intent: UseIntent,              // how to use
    pub effect_magnitude: Option<u32>,      // for items with adjustable effect (potion dose)
}

pub enum UseIntent {
    Activate,       // turn on / unlock / trigger
    Apply,          // use on something else (key on lock, potion on wound)
    Consume,        // self-consume (drink wine)
    Combine,        // V1+ — combine items (recipe)
}
```

### 6.2 Allowed InstrumentRef

| Variant | Allowed? | Notes |
|---|:---:|---|
| Item | ✅ exactly 1 | the item being used |
| BodyPart/Verbal/Ability | ❌ | not "Use" — those are other kinds |

### 6.3 Allowed TargetRef

| Variant | direct_targets | Notes |
|---|:---:|---|
| Actor(ActorId) | ✅ exactly 1 | potion on someone (self or other); ActorId from EF_001 §5.1 |
| Item(GlossaryEntityId) | ✅ exactly 1 | key on lock; tool on object — **V1 includes EnvObject targets (door-locks, wine-bottles, etc.) referenced via glossary-entity-id per B2.** No runtime Item or EnvObject state aggregate V1; world-rule simulates state transitions in audit-log only until V1+ Item substrate ships. PF_001 §3.1 EnvObject fixtures are author-declared; runtime mutation deferred. |
| Place(PlaceId) | ✅ exactly 1 | torch lit in dark cell (PlaceId per PF_001 §3.1) — extends scene_state via PL_001 §3.5 envelope |

### 6.4 Allowed agent

Pc / Npc.

### 6.5 ProposedOutputs allowed

Highly item-dependent. Common patterns:

| aggregate_type | delta_kind | When |
|---|---|---|
| `pc_stats_v1_stub` | HpDelta (positive) | Use heal potion on self/ally |
| `pc_stats_v1_stub` | StatusFlagDelta | Use wine → Drunk; Use buff potion → Buffed |
| (V1+ item_state aggregate) | LockTransition | Use key on lock |
| (V1+ scene_state extension) | LightingChange | Use torch in dark cell |

### 6.6 ActualOutputs (validator-derived)

Lex axioms (WA_001) gate `Use` per item compatibility:
- Reality 1 (Wuxia): healing potion ✓; spell scroll ✗ (`lex.ability_forbidden`)
- Reality 2 (Sci-fi): firearm OK; qigong potion ✗
- Reality 3 (Permissive default): all Use kinds pass through Lex no-op

V1 ActualOutputs limited to items with V1-supported targets (e.g., Heal potion on `pc_stats_v1_stub`). Other items audit-only without state mutation.

### 6.7 Validation rules

- tool=Item MUST be in agent inventory (V1 placeholder; V1+ Item aggregate enforces)
- target compatible with Use (V1+ Item compatibility table; V1 hardcoded list per UseIntent)
- agent capable of use (V1+: literacy for scrolls; skill checks)
- effect_magnitude within item's valid range (V1+ enforces; V1 placeholder)

### 6.8 Reject rule_ids

| rule_id | Trigger | Vietnamese reject copy |
|---|---|---|
| `interaction.use.tool_not_held` | item not in agent inventory | "Bạn không có [item]." |
| `interaction.use.target_incompatible` | item can't be used on target | "[Item] không dùng được trên [target]." |
| `interaction.use.effect_unsupported` | V1+ effect like Combine | "(V1+ sẽ hỗ trợ kết hợp vật phẩm.)" |
| `interaction.use.target_not_in_cell` | cross-cell | "[Mục tiêu] không ở đây." |
| `interaction.use.lex_forbidden` | Lex axiom rejects (spell scroll in non-magic reality) | (Lex-derived copy from WA_001) |

---

## §7 OutputDecl taxonomy table

Cross-kind summary of `aggregate_type` allowed in `proposed_outputs` / `actual_outputs`. Owner = feature that owns the aggregate.

| aggregate_type | Owner | delta_kinds | Used by Interaction kinds |
|---|---|---|---|
| `npc_pc_relationship_projection` | NPC_001 (R8) | OpinionDelta(±) | Speak (rare) / Give (always) / Strike (NPC target) |
| `pc_stats_v1_stub` | PCS_001 (V1+ when designed) | HpDelta · StatusFlagDelta · WieldedTool | Strike (HpDelta) / Use (HpDelta + StatusFlag) |
| `pc_mortality_state` | PCS_001 (V1+ when designed) | MortalityTransition | Strike (when hp→0) |
| `npc.flexible_state.liveness` | NPC_001 (V1 placeholder per B1) | NpcLivenessTransition | Strike (when target=NPC and "dies") — placeholder until NPC_003 |
| `oracle_audit_log` | DP-internal / 05_llm_safety A3 | OracleQueryRecorded | Examine (when Oracle invoked) |
| (V1+ `pc_inventory`) | PCS_001 (V1+) | InventoryDelta | Give / Use |
| (V1+ `item_state`) | future Item substrate | LockTransition · DamageDelta · DurabilityDelta | Use / Strike-on-Item |
| (V1+ `scene_state.lighting`) | PL_001 extension | LightingChange | Use (torch / candle) |

**`aggregate_type` not in this table = forbidden in OutputDecl.** Adding a new aggregate_type goes through `_boundaries/01_feature_ownership_matrix.md` lock-claim per EVT-A11.

---

## §8 Per-kind validator subset

Beyond the framework-level pipeline (per [`07_event_model/05_validator_pipeline.md`](../../07_event_model/05_validator_pipeline.md) + [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md)), each kind hits **Stage 3.5 group** (foundation-tier structural validators; fail-fast before Lex) + **Stage 4 lex_check** + **Stage 7 world-rule physics**.

Pipeline order (canonical):

```
Stage 0  schema          → InteractionPayloadBase + per-kind extension fields
Stage 1  capability      → DP-K9 produce: [Submitted] + write claims per OutputDecl
Stage 2  A5 intent       → Story / Command classification per A5-D1
Stage 3  A6 sanitize     → narrator_text + utterance.raw_text injection scan
Stage 3.5 GROUP          → foundation-tier structural validators (fail-fast)
  3.5.a entity_affordance → EF_001 (lifecycle_dead/destroyed; affordance_missing)
  3.5.b place_structural  → PF_001 (place destroyed; connection target unknown)
  3.5.c map_layout        → MAP_001 (Travel-related cross-cell reach checks)
  3.5.d cell_scene        → CSC_001 (actor_on_non_walkable; item_on_non_placeable)
Stage 4  lex_check        → WA_001 axiom evaluation (KIND-SPECIFIC severity below)
Stage 5  heresy_check     → WA_002 (V1 no-op; V2+ contamination budget)
Stage 6  A6 output filter → narrator_text cross-PC leak / persona-break / NSFW
Stage 7  world-rule       → ProposedOutputs → ActualOutputs derivation (KIND-SPECIFIC physics below)
Stage 8  canon-drift      → A6 body-knowledge mismatch; conflicting Oracle facts
Stage 9  causal-ref       → EVT-A6 typed causal-refs (REQUIRED for NPCTurn / orchestrated)
[commit] dp::advance_turn → Submitted T1
[post-commit]              → side-effect EVT-T3 Derived events per OutputDecl
```

### §8.1 Per-kind Stage 3.5 sub-stage applicability

| Kind | Stage 3.5.a entity_affordance | Stage 3.5.b place_structural | Stage 3.5.c map_layout | Stage 3.5.d cell_scene |
|---|---|---|---|---|
| **Speak** | ✅ for each Actor target — affordance_listening / lifecycle Existing | ✅ same-cell agent+target | ❌ skipped (not Travel) | ❌ skipped (no cell write) |
| **Strike** | ✅ for direct_target — affordance_strikable / lifecycle Existing (target_dead → `entity.lifecycle_dead`) | ✅ same-cell | ❌ skipped (V1 no cross-cell) | ✅ target on walkable tile (V1+ refinement) |
| **Give** | ✅ for recipient — affordance_acceptable / lifecycle Existing | ✅ same-cell | ❌ skipped | ❌ skipped (no cell write) |
| **Examine** | ✅ for Actor/Item targets — affordance_examinable / Existing; SKIPPED for Place + MapNode targets | ✅ same-cell for Actor/Item; **REQUIRED for ExamineTarget::Place** (StructuralState ≠ Destroyed) | **REQUIRED for ExamineTarget::MapNode** (ChannelId + ChannelTier present in map_layout) | ❌ skipped (Examine non-mutating) |
| **Use** | ✅ for direct_target — affordance_usable; ✅ for tool — agent holds | ✅ same-cell | ❌ skipped (V1) | ✅ target on placeable/walkable tile when applicable (V1 minimal) |

### §8.2 Per-kind Stage 4 (lex_check) severity

| Kind | Lex severity | Notes |
|---|---|---|
| **Speak** | no-op | Speak mundane in all V1 realities |
| **Strike** | medium | StrikeKind/StrikeIntent axiom-allowed (e.g., MagicSpell strike rejects in non-magic reality) |
| **Give** | no-op | Give mundane |
| **Examine** | no-op | Examine mundane |
| **Use** | **CRITICAL** | item × reality compatibility matrix; primary reject path for cross-reality items |

### §8.3 Per-kind Stage 7 (world-rule physics) actions

| Kind | World-rule stage actions |
|---|---|
| **Speak** | A6 canon-drift detector flags body-knowledge mismatch (SPIKE_01 turn 5); ActualOutputs typically empty |
| **Strike** | read mortality_config for outcome semantics; physics damage calculation with HP clamping; MortalityTransition derivation if hp would reach 0 (note: target_dead pre-rejected at Stage 3.5.a, so this stage assumes target Alive) |
| **Give** | read NPC opinion to determine acceptance threshold; opinion delta calculation per GiveIntent + relationship history |
| **Examine** | Oracle query if target is canonical (Actor/Item/Place/MapNode); KnowledgeAccrual derivation (V1+); MapNode targets reject with `interaction.intent_unsupported` until V1+ author content registers |
| **Use** | per-item effect derivation; target compatibility check (V1+ table); cross-namespace early-return: tool_unavailable / target_invalid checked here (not Stage 3.5) |

---

## §9 Expanded acceptance criteria

Extends [PL_005 §16](PL_005_interaction.md#16-acceptance-criteria-lock-gate) with kind-specific scenarios. **PL_005 + PL_005b combined = 16 acceptance scenarios.**

### §9.0 Namespace allocation note (Phase 3 cleanup)

PL_005b reject rule_ids in §2.8 / §3.8 / §4.8 / §5.8 / §6.8 use the **descriptive sub-namespace pattern** `interaction.{kind}.{specific}` for UX-readability. At validator-runtime, each reject scenario maps to one of:

| Sub-namespace pattern | Canonical namespace | Stage | Owner |
|---|---|---|---|
| `interaction.{kind}.target_not_in_cell` | `place.connection_target_unknown` | Stage 3.5.b | PF_001 |
| `interaction.{kind}.target_dead` / `recipient_unable` | `entity.lifecycle_dead` | Stage 3.5.a | EF_001 |
| `interaction.{kind}.target_destroyed` | `entity.entity_destroyed` | Stage 3.5.a | EF_001 |
| `interaction.{kind}.target_suspended` | `entity.entity_suspended` | Stage 3.5.a | EF_001 |
| `interaction.{kind}.target_not_visible` | `entity.affordance_missing` | Stage 3.5.a | EF_001 |
| `interaction.{kind}.lex_forbidden` | `lex.ability_forbidden` | Stage 4 | WA_001 |
| `interaction.{kind}.tool_not_held` | `interaction.tool_unavailable` | Stage 7 | PL_005 |
| `interaction.{kind}.target_incompatible` | `interaction.target_invalid` | Stage 7 | PL_005 |
| `interaction.{kind}.intent_unsupported` / `effect_unsupported` / `shout_unsupported` / `hidden_focus_unsupported` / `deep_study_unavailable` | `interaction.intent_unsupported` | Stage 7 | PL_005 |
| `interaction.{kind}.recipient_refused` | `interaction.target_invalid` (Give-specific opinion threshold) | Stage 7 | PL_005 |
| `interaction.{kind}.empty_utterance` / `zero_count` / `whisper_multi_target` | (schema-level) | Stage 0 | DP-K9 |
| `interaction.{kind}.self_monologue` / `no_targets` | `interaction.target_invalid` | Stage 0 (schema) or Stage 7 | PL_005 |

The sub-namespaced IDs are NOT individually registered in `_boundaries/02_extension_contracts.md` §1.4 (would explode the 5 V1 root rules into 25+). Per-kind sub-IDs are PL_005b-internal UX hints; canonical resolution is the right column.

### 9.1 Speak-specific (4)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-SPK-1** | SPIKE_01 turn 5 — Lý Minh quotes book; body-knowledge mismatch | committed Submitted/Interaction:Speak; canon_drift_flags populated by A6; 2-3 NPCTurn reactions via Chorus |
| **AC-INT-SPK-2** | Whisper to specific NPC | committed; visibility filter applies — bystanders don't see whisper text in their UI stream |
| **AC-INT-SPK-3** | Speak with empty utterance after A6 sanitize | rejected with `interaction.speak.empty_utterance`; turn_number unchanged |
| **AC-INT-SPK-4** | Self-monologue attempted | rejected with `interaction.speak.self_monologue` |

### 9.2 Strike-specific (3) — V1+ scenarios; integration tests run only when combat feature ships

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-STK-1** (V1+) | PC strikes bandit with sword; HP→0 lethal | HpDelta committed; MortalityTransition Alive→Dying (per RespawnAtLocation default) committed; Chorus reaction from bandit_companions |
| **AC-INT-STK-2** (V1+) | PC strikes Dead actor | rejected at Stage 3.5.a with canonical `entity.lifecycle_dead` (sub-namespaced as `interaction.strike.target_dead` in §3.8); turn_number unchanged |
| **AC-INT-STK-3** (V1+) | PC tries Strike with item not held | rejected with canonical `interaction.tool_unavailable` (sub-namespaced as `interaction.strike.tool_not_held` in §3.8) |

### 9.3 Give-specific (3)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-GIV-1** | SPIKE_01 turn 8 — Lý Minh pays 30 đồng to Lão Ngũ for lodging | OpinionDelta(+small) committed on npc_pc_relationship_projection; Chorus reaction from lao_ngu (gives key) |
| **AC-INT-GIV-2** | Give to Dead actor | rejected at Stage 3.5.a with canonical `entity.lifecycle_dead` (sub-namespaced as `interaction.give.recipient_unable` in §4.8) |
| **AC-INT-GIV-3** | Give 0 count | rejected at Stage 0 schema check (sub-namespaced as `interaction.give.zero_count` in §4.8; not user-facing) |

### 9.4 Examine-specific (2)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-EXM-1** | Lý Minh examines du_si_book — canonical 《Đạo Đức Kinh chú》 | committed Submitted/Interaction:Examine; oracle_audit_log entry; Du sĩ may react via Chorus (notices Lý Minh looking) |
| **AC-INT-EXM-2** | Examine with DeepStudy depth, turn-slot remaining only 30s | rejected with `interaction.examine.deep_study_unavailable` |

### 9.5 Use-specific (4)

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-USE-1** | Lý Minh drinks wine (self-Use, Consume intent) | committed; StatusFlagDelta(Drunk) on PcStatsV1Stub for LM01 |
| **AC-INT-USE-2** (V1+) | Use heal potion on self | committed; HpDelta(+X) on agent |
| **AC-INT-USE-3** | Use spell scroll in Wuxia reality (Lex forbids MagicSpells) | rejected with `interaction.use.lex_forbidden` (Lex-derived copy from WA_001) |
| **AC-INT-USE-4** (V1+) | Use key on lock | committed; lock state transition via item_state Derived (V1+ when Item aggregate ships) |

**Total acceptance scenarios for PL_005 + PL_005b: 6 (root) + 16 (this file) = 22.** V1 testable: ~14 (excluding V1+ marked); V1+ remaining when consumer features ship.

**Lock criterion:** ≥14 V1-testable scenarios pass integration tests. CANDIDATE-LOCK status for PL_005+PL_005b until tests green-light.

---

## §10 Phase 2 deferrals + landing points

Beyond [PL_005 §17](PL_005_interaction.md#17-open-questions-deferred--landing-point) (INT-D1..D11 incl. Phase 3 ExamineTarget extensions):

| ID | Question | Defer to |
|---|---|---|
| **INT-CON-D1** | V1+ multi-target Strike (sweep arc hits N targets) — ordering of HpDelta + Mortality across targets | Future combat feature |
| **INT-CON-D2** | V1+ Give to multiple recipients (split-stack) | V1+ when Item aggregate + inventory mechanics ship |
| **INT-CON-D3** | Examine of `indirect_targets` (bystanders observable as "looking at X") | V1+ bystander observation feature |
| **INT-CON-D4** | Use:Combine (recipe / crafting) | V1+ crafting feature |
| **INT-CON-D5** | Strike outcome variation per `mortality_config` (Permadeath vs RespawnAtLocation vs Ghost) — exact actual_outputs decision tree | Co-design with WA_006 + PCS_001 mortality flow when implementation begins |
| **INT-CON-D6** | Speak with `volume=Shout` propagating to ancestor channel | V1+ when bubble-up + ancestor visibility feature ships |
| **INT-CON-D7** | Use with V1+ items (potion / scroll / key) — full effect catalog | V1+ Item substrate + per-item effect registry |
| **INT-CON-D8** | NPC Strike outcome when target NPC dies (placeholder npc liveness vs V1+ NPC_003) | When NPC_003 mortality ships per B1 |
| **INT-CON-D9** (NEW Phase 3) | ProposedOutputs vs ActualOutputs serialization rules per EVT-T category — Proposal payload includes proposed_outputs only? Submitted carries both? Derived inherits from Submitted's actual_outputs? | When event-model agent Phase 4 hardens per-T category-specific payload contracts |
| **INT-CON-D10** (NEW Phase 3) | Sub-namespace pattern (`interaction.{kind}.{specific}`) registry — formal mapping table beyond §9.0 OR retire pattern entirely in favor of canonical-only | V1+ when first integration test discovers UX needs sub-IDs vs canonical-only |

---

## §11 Cross-references

**Foundation tier (Stage 3.5 group + ActorId source):**
- [`EF_001 Entity Foundation`](../00_entity/EF_001_entity_foundation.md) — ActorId/EntityId source-of-truth (§5.1); entity_affordance Stage 3.5.a validator owner; `entity.lifecycle_dead` canonical reject for target-dead scenarios
- [`PF_001 Place Foundation`](../00_place/PF_001_place_foundation.md) — PlaceId(ChannelId) newtype (§3.1); place_structural Stage 3.5.b validator owner; `place.connection_target_unknown` canonical reject for cross-cell scenarios
- [`MAP_001 Map Foundation`](../00_map/MAP_001_map_foundation.md) — map_layout Stage 3.5.c validator owner; ExamineTarget::MapNode tier validation
- [`CSC_001 Cell Scene Composition`](../00_cell_scene/CSC_001_cell_scene_composition.md) — cell_scene Stage 3.5.d validator owner; Layer 4 LLM narration consumes Speak narrator_text per §1 base note

**Play-loop substrate:**
- [`PL_005 Interaction`](PL_005_interaction.md) — root file (§1-§19): conceptual layer + 4-role pattern + 5 V1 kind list + sequences + ExamineTarget enum (§2) + Phase 3 cleanup
- [`PL_001 Continuum`](PL_001_continuum.md) §3.5 — TurnEvent envelope inherited
- [`PL_001b lifecycle`](PL_001b_continuum_lifecycle.md) §15 — rejection-path semantics inherited
- [`PL_002 Grammar`](PL_002_command_grammar.md) — command-driven Interactions emerge through PL_002 dispatch
- [`PL_006 Status Effects`](PL_006_status_effects.md) — actor_status aggregate; Use:wine outcome applies Drunk via OutputDecl

**NPC + world-authoring consumers:**
- [`NPC_001 Cast`](../05_npc_systems/NPC_001_cast.md) — ActorId enum (now sourced from EF_001) + npc_pc_relationship_projection
- [`NPC_002 Chorus`](../05_npc_systems/NPC_002_chorus.md) — consumes Interaction events as Triggers
- [`WA_001 Lex`](../02_world_authoring/WA_001_lex.md) — Stage 4 lex_check; Use kind has CRITICAL Lex check per §8.2
- [`WA_006 Mortality`](../02_world_authoring/WA_006_mortality.md) — `mortality_config` input to Strike outcomes
- [`PCS_001 brief`](../06_pc_systems/00_AGENT_BRIEF.md) — `pc_mortality_state` + `pc_stats_v1_stub` output targets

**Event model + boundaries:**
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) EVT-A1..A12 — taxonomy + extensibility
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) EVT-T1 Submitted — sub-type ownership
- [`07_event_model/05_validator_pipeline.md`](../../07_event_model/05_validator_pipeline.md) — framework pipeline; Interaction adds kind-specific Stage 3.5/4/7 rules
- [`07_event_model/06_per_category_contracts.md`](../../07_event_model/06_per_category_contracts.md) — common envelope
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — sub-type ownership for `Interaction:*`; aggregate_type ownership for OutputDecl targets
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `interaction.*` V1 rule_id enumeration (5 root rules)
- [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) — Stage 3.5 group + applicability matrix per §8 + §8.1
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) turns 5 + 8 — narrative grounding (Speak / Give canonical scenarios)

---

## §12 Implementation readiness checklist

PL_005 + PL_005b combined satisfy all DP-R2 + 22_feature_design_quickstart.md required items:

PL_005 (root):
- [x] §1-§3 Domain concepts + aggregate inventory (zero new aggregates V1)
- [x] §4 Tier+scope (no owned aggregates)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT (no new claims)
- [x] §7 Subscribe pattern
- [x] §8 Pattern choices
- [x] §9 Failure-mode UX
- [x] §10 Cross-service handoff with CausalityToken
- [x] §11-§15 5 high-level sequences
- [x] §16 Acceptance (6 scenarios)
- [x] §17 Deferrals INT-D1..D9
- [x] §18 Cross-references
- [x] §19 Readiness

PL_005b (this file):
- [x] §1 Common payload base struct (Phase 3: PlaceId + ActorId source-of-truth notes; Speak narrator_text → CSC_001 Layer 4)
- [x] §2-§6 Per-kind contracts (Speak / Strike / Give / Examine / Use); Phase 3: §5.3 Examine ExamineTarget extension; §6.3 Use V1 EnvObject simplification note
- [x] §7 OutputDecl taxonomy
- [x] §8 Per-kind validator subset (Phase 3: full Stage 0-9 pipeline + §8.1 Stage 3.5 sub-stage applicability matrix + §8.2 Stage 4 lex severity + §8.3 Stage 7 world-rule actions)
- [x] §9 Expanded acceptance (16 kind-specific scenarios — combined 22 total); Phase 3: §9.0 namespace allocation note + AC-INT-STK-2 + AC-INT-GIV-2 + AC-INT-GIV-3 canonical rule_id alignment
- [x] §10 Phase 2 deferrals INT-CON-D1..D10 (Phase 3 added D9 + D10)
- [x] §11 Cross-references (Phase 3: foundation tier EF/PF/MAP/CSC + Stage 3.5 boundary added; categorized)
- [x] §12 Readiness (this section)

**Phase 3 cleanup applied 2026-04-26 (PL folder closure):**
- S1.1 PlaceId(ChannelId) inheritance noted in §1 base
- S1.2 §6.3 EnvObject targets via Item(GlossaryEntityId) per B2 (V1 no runtime EnvObject state)
- S2.1 Stage 3.5 group integration in §8 (full pipeline) + §8.1 sub-stage applicability matrix
- S2.2 §9.0 namespace allocation note + per-kind reject rule_id canonical mapping
- S2.3 16 acceptance scenarios — 3 (STK-2/GIV-2/GIV-3) updated with canonical rule_id allocation
- S3.1 ProposedOutputs vs ActualOutputs deferral INT-CON-D9 (per-EVT-T category serialization rules) added

**Status transition:** PL_005 + PL_005b DRAFT 2026-04-26 → **CANDIDATE-LOCK 2026-04-26** (Phase 3 + closure pass; PL_005 already CANDIDATE-LOCK in commit 2; PL_005b promotes in next commit). LOCK when ≥14 V1-testable acceptance scenarios pass integration tests against SPIKE_01 fixtures + small Lex test config.

**Next** (when CANDIDATE-LOCK granted): world-service can implement Interaction validation + commit using these contracts. Vertical-slice target = AC-INT-1 (SPEAK MULTI-NPC) reusing SPIKE_01 turn 5 fixture. AC-INT-GIV-1 (SPIKE_01 turn 8 fixture) is second target. AC-INT-EXM-1 third.
