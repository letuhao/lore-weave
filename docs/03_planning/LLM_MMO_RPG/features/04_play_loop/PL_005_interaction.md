# PL_005 — Interaction (Core Gameplay Primitive)

> **Conversational name:** "Interaction" (INT). Core gameplay primitive — formalizes how an actor explicitly does something to the world (speaks, strikes, gives, examines, uses) with explicit roles for agent / tool / target / receivers + outputs that gate downstream cascades. Sits on top of [Continuum (PL_001)](PL_001_continuum.md) + [Grammar (PL_002)](PL_002_command_grammar.md) as the **action layer** that turns command/free-narrative into committed canonical change.
>
> **Two-file structure:** This file (PL_005 root) holds the **conceptual layer** (§1-§19): 4-role pattern + 5 V1 InteractionKinds + closed-set proof + Event-model mapping + DP primitives + capability + subscribe + pattern choices + failure UX + cross-service handoff + 5 high-level sequences + 6 acceptance criteria + deferrals. Companion [`PL_005b_interaction_contracts.md`](PL_005b_interaction_contracts.md) holds the **contract layer** (§1-§12): concrete payload schemas per kind + OutputDecl taxonomy + per-kind validator subset + per-kind reject rule_ids + 16 expanded acceptance scenarios. Read this file FIRST.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** DRAFT 2026-04-26
> **Catalog refs:** PL-2 (command grammar consumes Interaction), PL-7 (event emission), PL-8 (action resolution). Resolves the "how does an action interact with the world?" question that PL_001/002 deferred.
> **Builds on:** [PL_001 Continuum](PL_001_continuum.md) (turn-slot, channel, fiction-clock), [PL_002 Grammar](PL_002_command_grammar.md) (5 V1 commands — `/verbatim`/`/prose` typically produce Interaction:Speak; `/sleep`/`/travel` are FastForward not Interaction), [NPC_001 Cast](../05_npc_systems/NPC_001_cast.md) (ActorId enum), [NPC_002 Chorus](../05_npc_systems/NPC_002_chorus.md) (consumes Interaction events as Triggers for multi-NPC reactions), [WA_001 Lex](../02_world_authoring/WA_001_lex.md) (validator slot for axiom-rejection + actual_outputs derivation).
> **Defers to:** [PCS_001](../06_pc_systems/00_AGENT_BRIEF.md) (`pc_mortality_state` + `pc_stats_v1_stub` aggregates that Interaction outputs target); future `NPC_003_mortality` (NPC death state — V1 placeholder via npc.flexible_state liveness flag); future Item aggregate (V1+ — V1 Items referenced abstractly via glossary-entity-id, no runtime per-reality Item state).
> **Event-model alignment:** Interaction events are EVT-T1 Submitted with new sub-types `Interaction:Speak` / `Interaction:Strike` / `Interaction:Give` / `Interaction:Examine` / `Interaction:Use`. No new EVT-T* category needed. Sub-type ownership registered in [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md).

---

## §1 User story (concrete — 5 V1 kinds across SPIKE_01 + extended scenarios)

A reality is born from Thần Điêu Đại Hiệp. Lý Minh interacts with the world in 5 V1 ways:

1. **Speak** (SPIKE_01 turn 5) — Lý Minh quotes 《Đạo Đức Kinh chú》: agent=LM01, tool=Verbal, direct_targets=[Du sĩ + Tiểu Thúy + Lão Ngũ], indirect_targets=[]. Outputs: NPC opinion drift on each (NPC_001 npc_pc_relationship_projection deltas) + L3 canon seed (NPC speech becomes canon).

2. **Strike** (hypothetical V1+ combat) — Lý Minh swings sword at bandit: agent=LM01, tool=Item(jian_001), direct_targets=[bandit_npc_001], indirect_targets=[]. Outputs (world-rule-derived per WA_001 Lex): HP delta on bandit + possibly mortality state transition.

3. **Give** (item transfer) — Lý Minh gives 30 đồng to Lão Ngũ for room: agent=LM01, tool=Item(coins_id), direct_targets=[laongu_001], indirect_targets=[]. Outputs: PCS_001 inventory delta on LM01 (-30 đồng) + Lão Ngũ acceptance + opinion drift.

4. **Examine** (look-deeper) — Lý Minh examines du sĩ's book on table: agent=LM01, tool=(none/eyes), direct_targets=[Item(book_dao_de_kinh_chu)], indirect_targets=[]. Outputs: Oracle query trigger (PL-16) returning fact + knowledge accrual on LM01 + visible "looking" gesture observable to others (Du sĩ may notice).

5. **Use** (item-on-target) — Lý Minh uses chìa khóa on phòng X-01 lock: agent=LM01, tool=Item(key_x01), direct_targets=[Item(lock_x01)], indirect_targets=[]. Outputs: lock state transition (locked → unlocked); door-open derived event.

**SPIKE_01 turn 5 mapping:** the literacy slip is `Interaction:Speak` with metadata-rich payload (intent_class=Story per A5-D1 + canon-drift_flags from A6 detector). NPC_002 Chorus consumes the committed Interaction event as Trigger; orchestrator decides which NPCs react with what reaction_intent.

**This feature design specifies:** the 4-role payload pattern (agent / tool / direct_targets / indirect_targets) shared across all 5 V1 sub-types; the typed `InstrumentRef` + `TargetRef` enums; the proposed → actual outputs derivation by world-rule (WA_001 Lex) at validator-pipeline time; how Interaction events become Triggers for downstream Generators (police investigation, family grief — V1+ butterfly cascades) per [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) Generator Registry; the rejection UX with Vietnamese reject copy per `interaction.*` rule_id namespace; the cross-service handoff with CausalityToken across multi-output side-effects.

After this lock: world-service can implement Interaction validation + commit + side-effect emission; NPC_002 Chorus reactions to Interaction events are reproducible; PCS_001 mortality_state transitions correctly fire on Strike outcomes; WA_001 Lex axiom enforcement gates forbidden Interaction:Use (e.g., spell items in Reality 2 sci-fi).

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Interaction** | Top-level abstraction; an actor explicitly does something with role-typed inputs producing typed outputs | Always emits as **EVT-T1 Submitted** with sub-shape `Interaction:<Kind>`. Per [EVT-A1](../../07_event_model/02_invariants.md#evt-a1--closed-set-event-taxonomy) closed-set + [EVT-A11](../../07_event_model/02_invariants.md#evt-a11--sub-type-ownership-discipline-new-2026-04-25) sub-type ownership. |
| **InteractionKind** (closed enum V1) | `enum { Speak, Strike, Give, Examine, Use }` | V1 closed set of 5. V1+ extensions (Collide / Shoot / Cast / Embrace / Threaten) ADDITIVE per I14 — new variants registered in boundary matrix without envelope bump. |
| **4-role pattern** | `agent` (indirect interactor — ActorId) + `tools` (direct interactors — Vec\<InstrumentRef\>) + `direct_targets` (direct receivers — Vec\<TargetRef\>) + `indirect_targets` (indirect receivers — bystanders Vec\<TargetRef\>) | Locked schema — every InteractionKind payload extends this base. `agent: Option<ActorId>` per Q2 (None ⇒ shifts to EVT-T5 Generated). |
| **InstrumentRef** | Typed enum: `Item(GlossaryEntityId)` \| `BodyPart(BodyPartKind)` \| `Verbal(VerbalKind)` \| `Ability(AbilityRef)` | V1 supports Item refs (no runtime Item aggregate per B2; refs by glossary-entity-id only) + BodyPart + Verbal. Ability deferred to V1+ when Lex axioms more concrete. |
| **TargetRef** | Typed enum: `Actor(ActorId)` \| `Item(GlossaryEntityId)` \| `Place(ChannelId)` | V1 closed set. V2+ adds: `Concept` (idea / belief), `Faction`, `Relationship` (the social bond between two actors). |
| **ProposedOutputs** | What the agent / orchestrator INTENDS as outputs at emit time | `Vec<OutputDecl>` in payload. Player intent ≠ actual outcome. |
| **ActualOutputs** | What the world-rule (WA_001 Lex + physics validator) DERIVES as actual outputs at validator stage | Computed pre-commit by validator; populated in committed event payload. Replay-deterministic. |
| **OutputDecl** | `OutputDecl { target: TargetRef, aggregate_type: String, delta: serde_json::Value }` | Each output declares which aggregate it touches + the delta. Side-effect EVT-T3 Derived events emitted post-commit per [EVT-V6](../../07_event_model/05_validator_pipeline.md#evt-v6--post-commit-side-effects). |
| **LocalEvent** | Bounded participants + outputs in a single Interaction commit; downstream cascades via Generators (per [EVT-G framework](../../07_event_model/12_generation_framework.md)) | Butterfly effects (police investigation, grief, reputation drift across realities) live OUTSIDE local event scope — separate Generators with conditional/probability triggers. |
| **InteractionAuditTrail** | The `causal_refs` graph traced backward from any committed Interaction event | Per [EVT-L15](../../07_event_model/09_causal_references.md#evt-l15--graph-walk-patterns). Bounded-depth walk for forensic + replay. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11; Option C taxonomy)

Every PL_005 Interaction emits zero or more events. Mapping each path to active EVT-T* taxonomy:

| PL_005 path | EVT-T* category | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Interaction emitted (any V1 kind) | **EVT-T1 Submitted** | `Interaction:Speak` \| `Interaction:Strike` \| `Interaction:Give` \| `Interaction:Examine` \| `Interaction:Use` | Player-Actor (gateway → roleplay → commit-service) for PC; Orchestrator (NPC_002) for NPC | Carries 4-role payload + ProposedOutputs (intent) + ActualOutputs (validator-derived per Lex) |
| Interaction proposal (LLM-mediated path: free narrative or LLM-rephrased command) | **EVT-T6 Proposal** → **EVT-T1 Submitted** | `PCTurnProposal` (sub-shape declares Interaction kind via inner payload) | LLM-Originator (roleplay-service) | Promoted to Submitted/Interaction:* after validator chain |
| Side-effect outputs (committed actual_outputs) | **EVT-T3 Derived** | per `aggregate_type` of each OutputDecl (e.g., `pc_mortality_state` / `pc_stats_v1_stub` / `npc_pc_relationship_projection` / `actor_binding`) | Aggregate-Owner role per feature (PCS_001 / NPC_001 / etc.) | Causal-ref REQUIRED to parent Interaction event |
| NPC reaction to Interaction (Chorus orchestration) | **EVT-T1 Submitted** | `NPCTurn` (per NPC_002) | Orchestrator role | Causal-ref REQUIRED to triggering Interaction; not part of PL_005 output but visible cascade |
| Downstream Generator triggered (V1+ butterfly) | **EVT-T5 Generated** | per Generator registry (e.g., `Investigation:PoliceCallout` / `GriefDrift:FamilyOpinion` / `RumorSeed:CrimeWitness` — all V1+) | Generator role per [EVT-G1](../../07_event_model/12_generation_framework.md#evt-g1--generator-registry-as-first-class-concept) | Triggered conditionally; replay-deterministic per EVT-A9 |
| Rejected Interaction (Lex/world-rule violation) | **EVT-T1 Submitted** with `outcome=Rejected` | `Interaction:*` sub-type with `actual_outputs=[]` + `RejectReason::WorldRuleViolation { rule_id: "interaction.*" \| "lex.*" \| "world_rule.*" }` | Player-Actor / Orchestrator | Per [EVT-V4 rejection-path](../../07_event_model/05_validator_pipeline.md#evt-v4--rejection-path-semantics-resolves-mv12-d11): commit via `t2_write` not advance_turn; turn_number unchanged |

**Closed-set proof for PL_005:** every Interaction path produces an active EVT-T* category from the closed set (T1 / T3 / T5 / T6). No new EVT-T* row needed; PL_005 fits inside locked taxonomy.

---

## §3 Aggregate inventory

**Zero new aggregates V1.** Interaction is dispatch + side-effect emission logic. State changes happen via existing aggregates owned by other features (lazy boundary discipline learned from WA_006 thin-rewrite pattern).

References to existing aggregates:

| Aggregate | Owner | How Interaction uses |
|---|---|---|
| `participant_presence` (T1 / Channel) | PL_001 Continuum | SceneRoster read at validate stage (who's in cell to be a target / bystander) |
| `actor_binding` (T2 / Reality) | PL_001 Continuum | Resolve target locations; validate "target is in same cell as agent" |
| `npc` core (T2 / Reality) | NPC_001 Cast (R8-locked) | Read NPC state for reaction-eligibility + opinion lookups |
| `npc_pc_relationship_projection` (T2 / Reality) | NPC_001 Cast (R8-locked) | Output target — opinion deltas as EVT-T3 Derived side-effects |
| `pc_mortality_state` (T2 / Reality) | PCS_001 (brief seeded) | Output target — Alive→Dying / Dying→Dead transitions on Strike outputs |
| `pc_stats_v1_stub` (T2 / Reality) | PCS_001 (brief seeded) | Output target — HP deltas on Strike; status_flags on Give (drunk after Use:Drink) |
| `lex_config` (T2 / Reality singleton) | WA_001 Lex | Validator INPUT — Lex axioms gate Interaction kinds + tools per reality |
| `actor_contamination_state` (T2 / Reality) | WA_002 Heresy | Validator INPUT — contamination budget gates forbidden cross-reality Interactions (V2+) |
| `mortality_config` (T2 / Reality singleton) | WA_006 Mortality | Validator INPUT — death mode determines what Strike outcomes mean (Permadeath / RespawnAtLocation / Ghost) |
| `tool_call_allowlist` (T2 / Reality) | PL_002 Grammar | Validator INPUT — allowlist gates which Verbal/Ability tools an LLM may propose |
| `npc_reaction_priority` (T2 / Channel) | NPC_002 Chorus | Consumed by Chorus orchestrator (reactions to Interaction); not direct Interaction usage |

**No PL_005-owned aggregate.** This is the deliberate scope discipline: Interaction is a **payload pattern + dispatch contract**, not a state owner.

---

## §4 Tier+scope table (DP-R2)

PL_005 has zero owned aggregates → no tier+scope table required. References to other features' aggregates are read-only at validator + write at side-effect-emission via Aggregate-Owner roles per [EVT-A4](../../07_event_model/02_invariants.md#evt-a4--producer-role-binding-reframed-2026-04-25). Each feature's aggregate is governed by its OWN tier+scope per its design doc (DP-R2 satisfied at owner level).

---

## §5 DP primitives this feature calls

By name. No raw `sqlx` / `redis` (DP-R3).

### 5.1 Reads (at validator stage)

- `dp::query_scoped_channel::<ParticipantPresence>(ctx, &cell, predicate, limit)` — SceneRoster
- `dp::read_projection_reality::<ActorBinding>(ctx, agent_id)` + per-target `read_projection_reality::<ActorBinding>` — verify same-cell co-location
- `dp::read_projection_reality::<LexConfig>(ctx, SINGLETON)` — read world axioms for Lex check
- `dp::read_projection_reality::<MortalityConfig>(ctx, SINGLETON)` — read death mode for Strike outcomes
- `dp::read_projection_reality::<NpcPcRelationshipProjection>(ctx, (npc_id, pc_id))` — current opinion (input to LLM persona for NPC reactions; input to Give-acceptance threshold)
- `dp::read_projection_reality::<PcStatsV1Stub>(ctx, target_pc_id)` — current HP for Strike damage clamping

### 5.2 Writes (commit + side-effects)

- `dp::advance_turn(ctx, &cell, turn_data: TurnEvent { sub_shape: Interaction:* }, causal_refs)` — commit Interaction event itself; once on Accepted path
- `dp::t2_write::<TurnEvent>(ctx, channel, event_id, payload)` — Rejected path per EVT-V4 (turn_number UNCHANGED)
- Side-effect Derived events emitted by Aggregate-Owner role services (NOT directly by Interaction feature):
  - `dp::t2_write::<NpcPcRelationshipProjection>(ctx, id, OpinionDelta { ... })` — by NPC_001 owner-service
  - `dp::t2_write::<PcMortalityState>(ctx, pc_id, MortalityTransition { ... })` — by PCS_001 owner-service
  - `dp::t2_write::<PcStatsV1Stub>(ctx, pc_id, HpDelta { ... })` — by PCS_001 owner-service

### 5.3 Subscriptions

- `dp::subscribe_channel_events_durable::<TurnEvent>(ctx, &cell, from_event_id)` — UI consumes Interaction events for rendering (existing PL_001 §7 pattern)
- NPC_002 Chorus subscribes to same stream filtered by `Interaction:*` sub-shapes for Trigger consumption (already documented in NPC_002 §7)
- V1+ Generator services subscribe via `dp::subscribe_channel_events_durable<Submitted>` filtered by `Interaction:*` for downstream cascades

### 5.4 Capability + lifecycle

- `dp::DpClient::claim_turn_slot(ctx, &cell, actor=agent, expected_duration=15s, reason="interaction")` — Strict turn-slot per PL_001 §8.1 inherited
- `dp::DpClient::release_turn_slot(ctx, &cell)` — after commit + side-effects done

---

## §6 Capability requirements (JWT claims)

Inherits PL_001 §6 + PL_002 §6 patterns. No new claim category.

| Claim | Granted to | Why |
|---|---|---|
| `produce: [Submitted]` | commit-service (world-service) — already granted per PL_001 | Interaction commits as Submitted |
| `produce: [Proposal]` | roleplay-service — already granted per PL_001 | LLM-mediated Interaction goes via Proposal |
| `can_advance_turn @ level=cell` | commit-service — already granted | Interaction commits via advance_turn |
| `write: <aggregate_type> @ <tier> @ <scope>` per OutputDecl target | per Aggregate-Owner service (PCS_001, NPC_001, etc.) | Side-effect Derived events use Aggregate-Owner role per EVT-A4 |

**No new capability needed for V1.** Interaction reuses existing Submitted producer + Proposal pre-validation lifecycle.

---

## §7 Subscribe pattern

### 7.1 UI client

Existing PL_001 §7 multiplex stream — UI receives committed Interaction events alongside other Submitted/PCTurn variants. Visibility filter per [EVT-L16](../../07_event_model/10_replay_semantics.md#evt-l16--session-catch-up-replay): all `Interaction:*` sub-types are user-visible (PC actions are core narrative).

### 7.2 NPC_002 Chorus orchestrator

NPC_002 §7 already documents this pattern — orchestrator subscribes to channel events and treats committed Interaction events as Triggers for multi-NPC reaction batches.

### 7.3 V1+ downstream Generators

Future Generators (police-callout / grief-drift / rumor-seed) subscribe to `Interaction:*` filtered streams per EVT-G2 trigger source kind (a). Each Generator's registration in `_boundaries/01_feature_ownership_matrix.md` Generator Registry declares its Interaction sub-type filter + probability + capacity ceiling.

---

## §8 Pattern choices

### 8.1 Turn-slot pattern: **Strict** (inherited)

Per [PL_001 §8.1](PL_001_continuum.md). Single-actor turn-slot + claim/release across full validate+commit+side-effect cycle.

### 8.2 Redaction policy: **Transparent** (V1)

V1 cells are public-observable. V1+ may add `SkipPrivate` for Interaction:Speak in private bedrooms / whispers; Interaction:Examine never propagates (private knowledge accrual).

### 8.3 Outputs derivation: **atomic at validator stage** (per Q6/B4)

ProposedOutputs (intent) declared by agent/orchestrator in payload. ActualOutputs (outcome) computed by validator pipeline:
1. Schema → Capability → A5 intent classify → A5 command dispatch (if /verb-driven) → A6 5-layer
2. **Lex (WA_001) check** — kind+tool axiom-allowed in this reality?
3. **World-rule physics (Lex extension or PL_005-internal)** — convert ProposedOutputs → ActualOutputs based on physics state (HP delta clamped by stat ceilings; mortality transition determined per mortality_config; opinion delta scaled by relationship history)
4. Canon-drift → causal-ref integrity → commit

Committed Submitted carries BOTH `proposed_outputs` (audit) + `actual_outputs` (canonical). Side-effect Derived events emit FROM actual_outputs only.

### 8.4 Self-output: **simple** (per Q3/B3)

Agent in `direct_targets` is allowed; no special schema. Lý Minh hangover after `Interaction:Use` (drinking wine on himself) = `agent: LM01, tools: [Item(wine)], direct_targets: [Actor(LM01)]`.

### 8.5 Causality wait timeout: **default 5s** (inherited)

Per PL_001 §8.3. Multi-output side-effect chain may need 10-15s for cascading Chorus reactions; UI passes `causality_timeout=Some(Duration::from_secs(15))` after Strike or Give for first post-Interaction read.

---

## §9 Failure-mode UX

| DpError / RejectReason | When | UX |
|---|---|---|
| `LexViolation { rule_id: "lex.ability_forbidden" }` | Interaction:Use with item that violates reality axioms (e.g., spell scroll in Reality 2 sci-fi) | Reject copy from WA_001 (Vietnamese: "Trong thế giới này [item] không có tác dụng"). turn_number unchanged. |
| `WorldRuleViolation { rule_id: "interaction.target_unreachable" }` | Strike target moved out of cell mid-turn; Examine target dissolved (cell GC'd) | Toast: "Mục tiêu đã rời đi". 1 free retry. turn_number unchanged. |
| `WorldRuleViolation { rule_id: "interaction.tool_unavailable" }` | Give item not in agent's inventory (per PCS_001 inventory check); Use key not held | Reject: "Bạn không có [item] trong tay". |
| `WorldRuleViolation { rule_id: "interaction.target_invalid" }` | Speak to a Place (concept-level only V2+); Strike a non-actor (V1 closed-set rejects) | Reject with kind-specific copy. |
| `MortalityViolation { rule_id: "interaction.target_dead" }` | Strike a Dead actor; Give to Ghost actor | Reject: "Mục tiêu đã không còn ở thế giới này." (per WA_006 mortality_config) |
| `CapabilityDenied` | Service tries to emit without `produce: [Submitted]` claim | Standard DP-K9 rejection; should not surface to user (security misconfig) |
| `CausalityWaitTimeout` (post-Interaction read) | Multi-output chain still propagating after 15s | Toast: "Hệ quả đang được dệt..." 1 free retry. |

All copy locked in `interaction.*` rule_id namespace per `_boundaries/02_extension_contracts.md` §1.4 (registered in §boundary update of this commit).

---

## §10 Cross-service handoff (CausalityToken flow)

Concrete example: PC `/strike bandit_001 with jian` (V1+ but illustrates pattern).

```
1. UI → gateway:
     POST /v1/turn { session_id, command: "/strike bandit_001 with jian_001" }

2. gateway → roleplay-service:
     intent classify (PL-15): Command → Strike
     args: { target: bandit_001, tool: jian_001 }
     proposal emitted: Interaction:Strike { agent: LM01, tools: [Item(jian_001)],
                                            direct_targets: [Actor(bandit_001)],
                                            indirect_targets: [],
                                            proposed_outputs: [
                                              { target: Actor(bandit_001), aggregate: pc_stats_v1_stub,
                                                delta: HpDelta(-30) }
                                            ] }

3. world-service (consumer):
     a. claim_turn_slot(cell, LM01, 15s)
     b. validator pipeline:
        - schema ✓ / capability ✓ / A5 classify Command ✓ / A6 sanitize ✓
        - Lex check: jian_001 = Item; Strike with Sword = within Wuxia axioms ✓
        - world-rule physics: read pc_stats_v1_stub for bandit_001 (current_hp=50);
          actual_outputs = [HpDelta(-30)] (no clamp); if hp would reach 0,
          add MortalityTransition(Alive→Dying)
        - canon-drift ✓ / causal-ref ✓
     c. dp.advance_turn(ctx, &cell, turn_data: TurnEvent {
          sub_shape: "Interaction:Strike",
          payload: InteractionStrikePayload {
            agent: LM01, tools: [Item(jian_001)],
            direct_targets: [Actor(bandit_001)],
            actual_outputs: [HpDelta(-30)],
          }
        }, causal_refs=[])  →  T1 (Submitted commit)

  Side-effect Derived events (committed by PCS_001 owner-service):
     d. dp.t2_write::<PcStatsV1Stub>(ctx, bandit_001, HpDelta(-30))  → T2
        (causal_refs=[T1])
     e. (if hp=0) dp.t2_write::<PcMortalityState>(ctx, bandit_001,
                  Transition { from: Alive, to: Dying }) → T3 (causal_refs=[T1])

  f. release_turn_slot(cell)
  g. respond to gateway: { ok: true, causality_token: T3 (last in chain) }

4. NPC_002 Chorus consumes Interaction:Strike from durable subscribe:
     - SceneRoster: bandit_companions in cell → 2 candidates
     - Reaction batch: 2 NPCTurn reactions emitted (causal_refs=[T1])
     - Each NPC reaction may trigger further Interaction:Strike (cascade)
     - V1 cascade depth cap = 1 (per DP-Ch29 / EVT-G3); deeper cascades reject

5. UI on receiving 200:
     re-bind multiplex stream from T3
     read pc_stats_v1_stub (bandit_001) with wait_for=Some(T3), timeout=15s
     read pc_mortality_state (bandit_001) with wait_for=Some(T3), timeout=15s
     render strike + reaction cascade
```

**Token chain:** T1 (Interaction commit) → T2 (HpDelta Derived) → T3 (MortalityTransition Derived). UI passes T3. Multi-output causality preserved per DP-A19 monotonic per-channel ordering.

---

## §11 Sequence: Speak (SPIKE_01 turn 5 — multi-NPC observation)

```
PC `/verbatim "Tiểu nhị, vĩnh ngộ tại ư phi vi tà"` (PL_002 Verbatim → Interaction:Speak)

world-service:
  a. claim_turn_slot
  b. validator: schema ✓ / capability ✓ / A5 Story ✓ / A6 sanitize ✓ / Lex no-op (Speak is mundane) ✓
     world-rule: ActualOutputs = []  (Speak in V1 produces no immediate state delta;
                                       NPC opinion drifts come from Chorus reactions, not from Speak itself)
     canon-drift: A6 detects body-knowledge mismatch → flag added to canon_drift_flags;
                  NOT a hard reject (per A6-D4 — flagging, not blocking)
  c. dp.advance_turn(ctx, &cell, turn_data: TurnEvent {
       sub_shape: "Interaction:Speak",
       payload: InteractionSpeakPayload {
         agent: LM01, tools: [Verbal(Quote)],
         direct_targets: [Actor(du_si), Actor(tieu_thuy), Actor(lao_ngu)],
         indirect_targets: [],
         narrator_text: "Lý Minh đặt chén trà xuống, ngẩng đầu nhìn du sĩ và quote lời sách...",
         actual_outputs: [],
         canon_drift_flags: [BodyKnowledgeMismatch { detail: "literacy of book name" }]
       }
     }, causal_refs=[])  →  T1
  d. release_turn_slot

NPC_002 Chorus consumes T1:
  - SceneRoster: 3 NPCs co-present in yen_vu_lau
  - Priority algorithm (NPC_002 §6): du_si=Tier3 (knowledge_match), lao_ngu=Tier4 (ambient),
                                      tieu_thuy=Tier1 (filtered out)
  - Reaction batch (cap=3, V1): 2 reactions emitted as EVT-T1 Submitted/NPCTurn
    each with causal_refs=[T1]
  - Each NPC reaction may emit Derived opinion-delta (npc_pc_relationship_projection)

UI: stream delivers T1 (Speak) + 2 NPCTurn reactions + opinion-delta Deriveds.
    Renders Lý Minh's quote → Du sĩ sharp look (NPCTurn 1) → Lão Ngũ silent observation (NPCTurn 2).
```

---

## §12 Sequence: Strike (V1+ combat — illustrative; full combat = future feature)

Already shown in §10. Key points:
- Strike with Item(weapon) → HP delta + possible Mortality transition
- Per-physics damage clamp (HP can't go below 0)
- Strike with hands (BodyPart) → smaller HP delta
- Multi-target (Strike with sweep arc) supported via `direct_targets: Vec` — V1+ per `combat:*` feature

---

## §13 Sequence: Give (item transfer — SPIKE_01 turn 8 — PC pays for room)

```
PC `/use coins on lao_ngu for room` (V1+ syntax; V1 may use free-narrative
"đặt 30 đồng lên quầy" → roleplay-service classifies as Interaction:Give)

world-service:
  a. claim_turn_slot
  b. validator pipeline:
     - schema / capability / A5 Story (or Command) / A6 ✓
     - Lex: Give-money = mundane, no axiom violation
     - world-rule physics: read PCS_001 inventory for LM01 — has 50 đồng ✓
                          read NPC_001 lao_ngu.opinion (currently neutral) — accepts ✓
                          ActualOutputs = [
                            { target: Actor(LM01), aggregate: pc_inventory (V1+), delta: -30 đồng },
                            { target: Actor(lao_ngu), aggregate: npc_inventory (V1+), delta: +30 đồng },
                            { target: Actor(lao_ngu), aggregate: npc_pc_relationship_projection,
                              delta: OpinionDelta(LM01, +1 trust) }
                          ]
                          Note: V1 inventory aggregates not designed yet; V1 may simplify to
                                opinion-only outcome with money-tracked in PC stats stub
     - canon-drift / causal-ref ✓
  c. advance_turn(... Interaction:Give ...)  → T1
  d. side-effect Deriveds emit (PCS_001 inventory + NPC_001 opinion)
  e. release_turn_slot

Chorus consume:
  - lao_ngu reacts (NPCTurn): grants chìa khóa phòng X-01
  - This NPC reaction MAY itself contain an Interaction:Give (lao_ngu gives key to LM01) —
    cascade depth = 1; V1 cap = 1; OK
```

---

## §14 Sequence: Examine (look-deeper — SPIKE_01 turn 4-5 transition)

```
PC `/look at du_si_book` or free narrative "nhìn vào quyển sách của du sĩ"
(roleplay-service classifies → Interaction:Examine)

world-service:
  a. validator: schema / capability / A5 / A6 ✓
     Lex no-op (Examine is mundane)
     world-rule: ActualOutputs depend on what's seen:
       - target.is_canonical → Oracle query (PL-16) returns book metadata
       - PC knowledge_tags get += [book.tag] (KnowledgeAccrual on PCS_001)
       - Visible "looking" gesture observable to others (Du sĩ may notice)
  b. advance_turn(... Interaction:Examine ...)  → T1
  c. side-effects:
     - Oracle returns: 《Đạo Đức Kinh chú》 (book canon — A3 deterministic)
     - PCS_001 KnowledgeAccrual Derived: LM01 now knows this book exists (already knew via soul-layer)
     - NPC_002 Chorus may react: Du sĩ notices being watched

Note: V1 KnowledgeAccrual aggregate may not exist; V1 minimum is just Oracle return + audit log.
Knowledge effects defer to V1+ when PCS_001 knowledge_tags structure ships.
```

---

## §15 Sequence: Use (item-on-target — chìa khóa on lock)

```
PC `/use key_x01 on door_x01` (V1+ command grammar; V1 may use free-narrative)

world-service:
  a. validator:
     - Lex: Use-key on lock = mundane in Wuxia + Modern realities ✓
     - world-rule: read item_state for door_x01 (V1+ Item aggregate)
                   if locked: ActualOutputs = [
                     { target: Item(door_x01), aggregate: item_state (V1+), delta: Unlock },
                     { target: Place(room_x01), aggregate: cell_metadata, delta: AccessGranted(LM01) }
                   ]
                   if not locked: reject "interaction.target_invalid"
                   if wrong key: reject "interaction.tool_invalid"
  b. advance_turn(... Interaction:Use ...)  → T1
  c. side-effects: lock state transition

V1 status: Use of items requires V1+ Item aggregate. V1 minimum = doorless / direct-access cells;
Use kind reserved in payload schema but not actively triggered. Reuses pattern when V1+ Items ship.
```

---

## §16 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service + roleplay-service + gateway can pass these scenarios. Each is one row in the integration test suite.

### 16.1 V1 happy-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-1 SPEAK MULTI-NPC** | SPIKE_01 turn 5 — Lý Minh quotes book; 3 NPCs co-present | Interaction:Speak commits; Chorus consumes; ≤3 NPCTurn reactions emit with causal_refs to Speak; canon_drift_flags carry body-knowledge mismatch |
| **AC-INT-2 GIVE OPINION DRIFT** | SPIKE_01 turn 8 — Lý Minh gives Lão Ngũ 30 đồng for room | Interaction:Give commits; npc_pc_relationship_projection delta committed; lao_ngu's NPCTurn (grant key) emits |
| **AC-INT-3 EXAMINE ORACLE** | Lý Minh examines du_si_book | Interaction:Examine commits; Oracle returns canonical book info; Du sĩ may react via Chorus |
| **AC-INT-4 SELF-USE** | LM01 drinks wine (Use:Drink, agent in direct_targets) | Interaction:Use commits with self-target; status_flag (drunk) added via PcStatsV1Stub Derived |

### 16.2 Failure-path

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-INT-5 LEX REJECT** | LM01 tries Interaction:Use with spell scroll in Wuxia world (Lex forbids MagicSpells) | Reject with `LexViolation { rule_id: "lex.ability_forbidden" }`; turn_number UNCHANGED; outcome=Rejected committed via t2_write per EVT-V4 |
| **AC-INT-6 TARGET UNREACHABLE** | Strike target left cell mid-turn-slot | Reject with `WorldRuleViolation { rule_id: "interaction.target_unreachable" }`; turn-slot released; PC sees retry toast |

**Lock criterion:** all 6 scenarios have corresponding integration tests passing. CANDIDATE-LOCK status until tests green-light.

---

## §17 Open questions deferred + landing point

| ID | Question | Defer to |
|---|---|---|
| **INT-D1** | Item aggregate ownership for V1+ (vehicles / weapons / consumables with state) | Future `IF_NNN_item_substrate.md` OR PCS_001 inventory extension. V1 uses glossary-entity refs only. |
| **INT-D2** | NPC mortality for Strike outcomes | Future `NPC_003_mortality.md` (B1 deferred per Phase 0). V1 NPC death = npc.flexible_state liveness flag placeholder. |
| **INT-D3** | Multi-target ordering when Strike sweep hits N actors | Future combat feature. V1 = single direct_target only. |
| **INT-D4** | Indirect_targets V1+ scope: bystander witnesses observable in cell vs cascade-discovered family/faction members | V1+ when butterfly-cascade Generators design (e.g., `Investigation:PoliceCallout` Generator) |
| **INT-D5** | InstrumentRef::Ability scope (V1+ Lex magic axioms) | V1+ `combat:*` and `magic:*` features when WA_001 axioms expand |
| **INT-D6** | Examine knowledge accrual aggregate shape | PCS_001 knowledge_tags structure (brief seeded; design pending) |
| **INT-D7** | V1+ Interaction kinds (Collide / Shoot / Cast / Embrace / Threaten) | Per-modern-setting feature (V1+ when modern-reality realities supported) |
| **INT-D8** | Cross-cell Interaction (LM01 throws stone from cell A into cell B) | V2+ — V1 strict same-cell agent+target invariant |
| **INT-D9** | Self-Speak (PC talks to self / monologue) | V1+ — V1 requires direct_targets non-empty for Speak |

---

## §18 Cross-references

- [`PL_001 Continuum`](PL_001_continuum.md) — turn-slot, channel, fiction-clock substrate
- [`PL_001b lifecycle`](PL_001b_continuum_lifecycle.md) §15 — rejection-path pattern (Interaction inherits)
- [`PL_002 Grammar`](PL_002_command_grammar.md) — command-driven Interactions emerge through PL_002 dispatch
- [`NPC_001 Cast`](../05_npc_systems/NPC_001_cast.md) — ActorId enum + npc_pc_relationship_projection target
- [`NPC_002 Chorus`](../05_npc_systems/NPC_002_chorus.md) — consumes Interaction events as Triggers
- [`WA_001 Lex`](../02_world_authoring/WA_001_lex.md) — validator slot + actual_outputs derivation
- [`WA_002 Heresy`](../02_world_authoring/WA_002_heresy.md) — cross-reality contamination (V2+)
- [`WA_006 Mortality`](../02_world_authoring/WA_006_mortality.md) — death-mode config (input to Strike outcomes)
- [`PCS_001 brief`](../06_pc_systems/00_AGENT_BRIEF.md) — pc_mortality_state + pc_stats_v1_stub output targets
- [`07_event_model/02_invariants.md`](../../07_event_model/02_invariants.md) EVT-A1..A12 — taxonomy + extensibility
- [`07_event_model/03_event_taxonomy.md`](../../07_event_model/03_event_taxonomy.md) — EVT-T1 Submitted (Interaction sub-types)
- [`07_event_model/05_validator_pipeline.md`](../../07_event_model/05_validator_pipeline.md) EVT-V4 — rejection-path semantics
- [`07_event_model/12_generation_framework.md`](../../07_event_model/12_generation_framework.md) — V1+ butterfly Generators
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — sub-type ownership SSOT
- [`_boundaries/02_extension_contracts.md`](../../_boundaries/02_extension_contracts.md) §1.4 — `interaction.*` rule_id namespace registered
- [`SPIKE_01`](../_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative grounding (Speak / Examine / Give scenarios)

---

## §19 Implementation readiness checklist

This doc satisfies items per DP-R2 + 22_feature_design_quickstart.md:

- [x] §2 Domain concepts + 4-role pattern + InstrumentRef/TargetRef/OutputDecl typed enums
- [x] §2.5 Event-model mapping (closed-set proof: 5 V1 InteractionKinds map to EVT-T1 Submitted; no new EVT-T*)
- [x] §3 Aggregate inventory — **zero new aggregates V1** (deliberate scope discipline; references existing aggregates)
- [x] §4 No tier+scope table needed (no owned aggregates)
- [x] §5 DP primitives by name
- [x] §6 Capability JWT requirements (no new claims)
- [x] §7 Subscribe pattern (Chorus + UI + V1+ Generators)
- [x] §8 Pattern choices (turn-slot Strict, redaction Transparent V1, atomic outputs derivation, self-output simple, causality timeout 15s for cascades)
- [x] §9 Failure-mode UX (Vietnamese reject copy locked in `interaction.*` namespace)
- [x] §10 Cross-service handoff with CausalityToken chain (Strike example)
- [x] §11-15 End-to-end sequences for 5 V1 kinds
- [x] §16 Acceptance criteria (6 scenarios)
- [x] §17 Deferrals named with landing point (9 deferrals INT-D1..D9)
- [x] §18 Cross-references

**Status transition:** DRAFT 2026-04-26 → CANDIDATE-LOCK after §16 acceptance scenarios have integration tests → LOCK after green tests.

**Boundary registration in same commit:** EVT-T1 Submitted sub-type ownership row updated in `_boundaries/01_feature_ownership_matrix.md` to include 5 V1 Interaction:* kinds owned by PL_005; `interaction.*` prefix added to `_boundaries/02_extension_contracts.md` §1.4 RejectReason namespace.

**Next** (when this doc CANDIDATE-LOCKs): world-service can scaffold against this contract. First vertical-slice target = AC-INT-1 (SPEAK MULTI-NPC) reusing SPIKE_01 turn 5 fixture; AC-INT-2 (GIVE) reusing SPIKE_01 turn 8 fixture. AC-INT-5 (LEX REJECT) requires WA_001 Lex implementation co-deployed.
