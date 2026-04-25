# NPC_002 — Chorus (Multi-NPC Turn Ordering)

> **Conversational name:** "Chorus" (CHO). Multiple NPCs in a cell reacting to a PlayerTurn — like a Greek chorus, ordered, deterministic, capped. Resolves how SPIKE_01 turn 5 (PC literacy slip observed by Du sĩ + Tiểu Thúy + Lão Ngũ) becomes a sequence of EVT-T2 NPCTurn events without violating Continuum's Strict turn-slot.
>
> **Category:** NPC — NPC Systems
> **Status:** **CANDIDATE-LOCK 2026-04-26** (originally drafted 2026-04-25 as `PL_003_chorus.md` in `04_play_loop/`; relocated 2026-04-25 to `05_npc_systems/` per boundary review; Option C terminology applied 2026-04-25 by event-model agent; closure pass 2026-04-26 added §14 acceptance criteria — 10 scenarios)
> **Catalog refs:** NPC-7 (multi-NPC turn arbitration). Resolves [MV12-D8](../../decisions/locked_decisions.md) (narration taxonomy / NPC turn sub-shapes).
> **Builds on:** [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) (turn-slot Strict, channel ordering, causal_refs), [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) (PlayerTurn sub-shapes), [NPC_001 Cast](NPC_001_cast.md) (NPC identity, persona assembly, ActorId variants, owner-node binding, NpcOpinion::for_pc realization), [07_event_model EVT-T2](../../07_event_model/03_event_taxonomy.md) (NPCTurn category — already mandates "deterministic order, defined by feature in PL_003" — that note in 03_event_taxonomy.md predates this rename and refers to this file)
> **Stable ID rename:** PL_003 → NPC_002. Old ID `PL_003` MUST NOT be reused for a different feature (foundation I15 stable-ID rule); references in event-model agent's files (`07_event_model/03_event_taxonomy.md`, `04_producer_rules.md`) and SPIKE_01 graduation map will be reconciled when those files next update.

---

## §1 User story (concrete — SPIKE_01 turn 5)

PC `Lý Minh` says (turn 5, in `cell:yen_vu_lau`): "Tiểu nhị, vĩnh ngộ tại ư phi vi tà" — quotes a phrase from 《Đạo Đức Kinh chú》, a book that this 20yo Hàng Châu peasant body would not have read. Three NPCs are co-present:

1. **Lão Ngũ** (65, teahouse owner, ex-jianghu) — notices but stays silent (suspicion +1, says nothing)
2. **Tiểu Thúy** (16, illiterate orphan waitress) — confused, smiles awkwardly, looks down
3. **Du sĩ** (40s, scholar with 《Đạo Đức Kinh chú》 jian + scroll) — sharply looks up, sets down his tea, observes

The PlayerTurn commits one EVT-T1 with `outcome=Accepted, command_kind=None` (free narrative Speak with implicit literacy hint). Then Chorus orchestrator decides: how many NPCs react, in what order, with what reaction kind. Each reaction commits a separate EVT-T2 NPCTurn with `causal_refs=[player_turn_event_id]`.

**Key tension:** PL_001 §8.1 Strict turn-slot says one actor at a time per cell. Three NPCs reacting in sequence means three turn-slot claim/release cycles OR one batched orchestrator-held slot covering all three reactions. NPC_002 locks: **batched** (orchestrator holds slot across the entire reaction batch; releases only after all reactions commit). The PC's submission ack returns AFTER the full batch commits, so UI sees PC turn + all 3 NPC reactions together in the multiplex stream.

After this lock: world-service can implement the orchestrator; NPCs in SPIKE_01 turns 1-17 react with deterministic ordering; MV12-D8 narration taxonomy resolved (no new sub-shapes; metadata-rich Speak/Action covers all reaction kinds).

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **Trigger** | The committed EVT-T1 PlayerTurn (or rarely EVT-T2 NPCTurn) that may demand reactions. | Trigger event_id is the value used as causal_ref on each emitted reaction. |
| **SceneRoster** | Set of `ActorId` currently in the cell, with their `actor_type` (PC \| NPC). Derived from PL_001's `participant_presence` T1 + `actor_binding` T2. | Read once per Chorus invocation, cached for the duration of the batch. |
| **ReactionCandidate** | A potential `(actor: NpcId, priority_tier: u8, priority_score: u32, reaction_intent: ReactionIntent)` produced by the priority algorithm. | Closed set of `ReactionIntent` in §3.3. |
| **ReactionBatch** | Ordered list of `ReactionCandidate`, capped at V1=3, that the orchestrator commits as N back-to-back EVT-T2 NPCTurns under a single held turn-slot. | Empty batch valid (no NPC reacts; Chorus completes immediately). |
| **CascadeDepth** | Counter incremented when an EVT-T2 commit triggers further reactions. V1 cap = 1 (initial reactions only; reactions don't trigger further reactions). V2+ may raise. | Enforced at orchestrator level. |
| **Orchestrator** | The world-service component on the cell's writer node (per DP-A16) that runs Chorus per Trigger. One orchestrator instance per cell at any time. | Not a separate service; a logical role of world-service. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11; Option C redesign 2026-04-25)

**Updated 2026-04-25 Option C redesign:** EVT-T2 NPCTurn was `_withdrawn` per I15. NPC reactions now emit as **EVT-T1 Submitted with sub-type=NPCTurn** (mechanism: actor explicitly emits with intent — same as PCTurn, just different actor variant per ActorId enum). All references below updated.

NPC_002 emits / consumes events that all map to existing active categories — no new EVT-T* row needed.

| NPC_002 path | EVT-T* | Sub-type | Producer role | Notes |
|---|---|---|---|---|
| Trigger consumption (PCTurn) | **EVT-T1 Submitted** (consumed) | PCTurn | gateway → roleplay → commit-service (per PL_001/PL_002) | Read-only consumption via durable subscribe |
| Reaction emission (one per reacting NPC) | **EVT-T1 Submitted** (formerly EVT-T2 NPCTurn — `_withdrawn` 2026-04-25, merged into T1) | NPCTurn (Speak / Action / Narration) | Orchestrator role (world-service) | **REQUIRED** causal_refs to Trigger per EVT-A6 |
| Batched LLM proposals (one per reacting NPC) | **EVT-T6 Proposal** | NPCTurnProposal | LLM-Originator role (roleplay-service per orchestrator-coordinated call) | Each promoted to EVT-T1 Submitted/NPCTurn after validator chain |
| Opinion / relationship update (V2 — defer to NPC_001) | **EVT-T3 Derived** | aggregate_type=npc_pc_relationship_projection | Aggregate-Owner role (NPC_001 owns the aggregate) | NPC_002 only triggers; aggregate definition belongs to NPC_001 |
| Cascade event (V2+ — out of scope) | **EVT-T1 Submitted/NPCTurn** cascade | NPCTurn | same orchestrator | Cascade depth >1 V2+; V1 caps at 1 |

**Closed-set proof:** every Chorus-emitted event is **EVT-T1 Submitted/NPCTurn** (or EVT-T6 Proposal → EVT-T1 Submitted/NPCTurn). All triggers are existing EVT-T1 Submitted events. No new EVT-T*.

---

## §3 Aggregate inventory

Two new aggregates. Both reference NPC concepts that NPC_001 will own — NPC_002 declares only the priority-related state.

### 3.1 `npc_reaction_priority`

```rust
#[derive(Aggregate)]
#[dp(type_name = "npc_reaction_priority", tier = "T2", scope = "channel")]
pub struct NpcReactionPriority {
    pub channel_id: ChannelId,                     // cell channel
    pub actor: NpcId,                              // one row per (cell, NPC)
    pub base_priority_tier: u8,                    // 1..=4 (see §6 ordering algorithm)
    pub knowledge_tags: Vec<KnowledgeTag>,         // for Tier-3 relevant-knowledge matching ("daoist_text", "wuxia_lore", ...)
    pub last_reacted_turn: Option<u64>,            // last turn this NPC reacted on; for fairness rotation
}
```

- T2 + ChannelScoped: per-cell-per-NPC ordering hint, persistent across sessions.
- Authored at scene-bootstrap (per PL_001 §16 — book manifest's `CanonicalActorDecl` may carry priority hints) OR inferred from NPC role (e.g., scene-anchored NPCs default Tier 4 by entry order).
- `last_reacted_turn` updated by orchestrator on each reaction commit, used to rotate which NPCs react when more candidates exist than the cap.

### 3.2 `chorus_batch_state` (transient)

```rust
#[derive(Aggregate)]
#[dp(type_name = "chorus_batch_state", tier = "T1", scope = "channel")]
pub struct ChorusBatchState {
    pub channel_id: ChannelId,
    pub trigger_event_id: u64,                     // the EVT-T1 PlayerTurn that opened this batch
    pub batch_started_at_turn: u64,
    pub candidates: Vec<ReactionCandidate>,        // post-priority, post-cap selection
    pub committed_count: u8,                       // 0..=cap; advances per reaction
    pub cascade_depth: u8,                         // V1: 0 (initial) | 1 (max)
    pub state: ChorusBatchPhase,                   // Resolving | Reacting | Completed | Aborted
}

pub enum ChorusBatchPhase {
    Resolving,                                     // priority algorithm running
    Reacting,                                      // LLM calls + commits in progress
    Completed,                                     // all reactions committed; turn-slot released
    Aborted { reason: AbortReason },               // failure mid-batch (one NPC's LLM call failed)
}

pub enum AbortReason {
    LlmTimeout { actor: NpcId },
    CanonDriftRejection { actor: NpcId, flags: Vec<DriftFlag> },
    OrchestratorCrash,
}
```

- T1 + ChannelScoped: ephemeral per-batch state, ≤30s loss OK because batches complete within ~5-15s normally.
- One row at a time per cell (matches Strict turn-slot single-occupancy).
- Cleared on `Completed` or `Aborted` after batch resolves.
- **Why T1, not T2:** the audit trail is the COMMITTED EVT-T2 NPCTurns themselves; `chorus_batch_state` is just runtime coordination. Loss on writer-node crash → orchestrator re-derives from PC's TurnEvent + scene roster.

### 3.3 References

NPC_002 reads/writes the following aggregates without redefining them:

- **`participant_presence`** (PL_001 §3.3) — to find NPCs in scene
- **`actor_binding`** (PL_001 §3.6) — to confirm NPC location
- **`scene_state`** (PL_001 §3.2) — to read scene metadata for context (combat? private?)
- **NPC opinion / relationship aggregates** — owned by **NPC_001** (not yet designed); NPC_002 reads via abstract trait `NpcOpinion::for_pc(npc_id, pc_id) → OpinionScore`. V1 stub returns neutral.
- **`tool_call_allowlist`** (PL_002 §3.1) — for actor_type=NPC_Reactive when each NPC's reaction goes to LLM

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `npc_reaction_priority` | T2 | T2 | Channel (cell) | ~1 per Trigger (cached for batch duration) | ~3/cell/day (each reaction updates `last_reacted_turn`) | Per-NPC-per-cell ordering hint; survives restart; per-cell. |
| `chorus_batch_state` | T1 | T1 | Channel (cell) | ~3/batch by orchestrator | ~3/batch (start, advance, complete) | Ephemeral coordination; ≤30s loss tolerable (re-derive on crash). |

(All other touched aggregates inherit tier+scope from PL_001 / PL_002.)

---

## §5 DP primitives this feature calls

### 5.1 Reads

- `dp::read_projection_channel::<NpcReactionPriority>(ctx, &cell, npc_id)` — once per scene-NPC at batch start, cached for batch duration.
- `dp::query_scoped_channel::<ParticipantPresence>(ctx, &cell, predicate=field_eq(state, Active))` — get scene roster.
- `dp::read_projection_channel::<SceneState>(ctx, &cell, scene_id)` — for trigger context (combat? private?).

### 5.2 Writes

- `dp::t1_write::<ChorusBatchState>(ctx, batch_id, delta)` — start, advance, complete batch.
- `dp::t2_write::<NpcReactionPriority>(ctx, npc_id, UpdateLastReactedTurn { turn: N })` — once per reaction.
- `dp::advance_turn(ctx, &cell, turn_data: TurnEvent { actor: ActorId::Npc(npc_id), intent, causal_refs: [trigger_event_id] })` — once per reaction; this is the commit primitive for EVT-T2 NPCTurn.

### 5.3 Turn-slot

- `dp::claim_turn_slot(ctx, &cell, actor=ChorusOrchestrator, expected_duration=15s, reason="chorus_batch")` — held across the entire batch (V1: ≤3 reactions × ~5s each = ~15s).
- `dp::release_turn_slot(ctx, &cell)` — after batch completes or aborts.

**Why `actor=ChorusOrchestrator` rather than per-NPC:** Strict turn-slot mandates one actor at a time. If orchestrator claimed in NPC1's name, then released, then claimed in NPC2's name, a parallel PC submit could slip in between, breaking causal-ref integrity (PC's submit would be tagged after some but not all reactions). Locking the slot under an orchestrator-pseudo-actor for the batch duration solves this. `ChorusOrchestrator` is a synthetic ActorId scoped to world-service; not a JWT subject.

### 5.4 Subscribe

- `dp::subscribe_channel_events_durable::<TurnEvent>(ctx, &cell, from_event_id=last_seen)` — orchestrator subscribes to its own cell to detect Triggers. Filters in-process for `outcome=Accepted` PlayerTurns / NPCTurns.

---

## §6 Priority algorithm (the deterministic ordering rule)

The algorithm runs in `ChorusBatchPhase::Resolving`. Inputs: Trigger event + SceneRoster + per-NPC priority data. Output: ordered `Vec<ReactionCandidate>`, capped at V1=3.

### 6.1 Tier assignment

For each NPC in SceneRoster (excluding the Trigger's actor if it's an NPC), compute tier:

```rust
fn assign_tier(npc: &Npc, trigger: &TriggerContext) -> Option<u8> {
    // Tier 1: directly addressed
    if trigger.explicit_targets.contains(&npc.id) {
        return Some(1);
    }
    // Tier 2: high-relationship (opinion above threshold)
    let opinion = NpcOpinion::for_pc(npc.id, trigger.pc_id);  // NPC_001 stub; V1 returns neutral
    if opinion.score >= STRONG_OPINION_THRESHOLD {           // V1 threshold = 50 on -100..+100 scale
        return Some(2);
    }
    // Tier 3: relevant-knowledge match
    let trigger_tags = extract_knowledge_tags(trigger);     // e.g., ["daoist_text"] for the literacy slip
    if !trigger_tags.is_empty() && npc.priority_data.knowledge_tags.iter().any(|t| trigger_tags.contains(t)) {
        return Some(3);
    }
    // Tier 4: in-scene presence (default eligible)
    if npc.is_in_scene_and_awake() {
        return Some(4);
    }
    None  // not a candidate
}
```

### 6.2 Within-tier ordering

Two stable ordering criteria within each tier, applied in order:

1. **Fairness rotation:** NPCs who reacted MORE RECENTLY (`last_reacted_turn` close to `current_turn`) are pushed back. Rotation prevents the same NPC always speaking first when multiple are tied.
2. **Deterministic NPC ID hash:** `hash(npc_id, trigger_event_id) mod 1000` as the final tiebreaker. Reproducible per-Trigger ordering.

### 6.3 V1 cap selection

After tiers + within-tier ordering:

- Take the top 3 candidates. (V1=3; configurable per scene metadata in V2+.)
- If all candidates are Tier 4 (no addressed/high-relationship/knowledge match), only emit reactions from candidates whose hash falls in the top 1/3 quantile. This prevents "every NPC reacts to every PC sneeze".
- If 0 candidates exist, the batch is empty and Chorus completes without committing any EVT-T2.

### 6.4 ReactionIntent assignment per candidate

For each surviving candidate, the priority algorithm tags a `ReactionIntent` from a closed set:

```rust
pub enum ReactionIntent {
    DialogueResponse,                               // direct verbal reply (Speak)
    PhysicalAction,                                 // gesture, grimace, action (Action)
    SilentObservation,                              // notes, reacts inwardly, no visible output (Action::Observe)
    AsideToNeighbor,                                // whispers to another NPC (Speak with aside-target metadata)
    StartleOrFlee,                                  // exits scene (Action::Move + MemberLeft)
}
```

Choice rule:
- **Tier 1:** `DialogueResponse` (directly addressed → must answer)
- **Tier 2:** `DialogueResponse` or `PhysicalAction` (relationship → engage)
- **Tier 3:** `SilentObservation` or `PhysicalAction` (knowledge match → visible reaction without escalation)
- **Tier 4:** weighted random among all 5 with weights favoring `SilentObservation` and `AsideToNeighbor` (low-stakes ambient texture)

**Determinism:** the "random" choice is seeded by `hash(trigger_event_id, npc_id)` per DP-Ch27 deterministic RNG pattern, so replay reproduces.

---

## §7 Capability requirements

- All EVT-T2 NPCTurn commits go through world-service backend's JWT (per PL_001 §6 + EVT-A4).
- New JWT claim required: `produce: NPCTurn @ orchestrator-role` — present on world-service, absent on roleplay-service (which only emits LLMProposal).
- `chorus_batch_state` writes need standard `write: chorus_batch_state @ T1 @ cell-channel` capability.
- `npc_reaction_priority` writes need `write: npc_reaction_priority @ T2 @ cell-channel`.

PC sessions never call any of these primitives — Chorus is entirely backend-orchestrated.

---

## §8 Pattern choices

### 8.1 Batched orchestrator (locked) — NOT per-NPC slot churn

Locked: **single turn-slot held across entire batch by `ChorusOrchestrator` synthetic actor.** Alternatives considered and rejected:

- ~~**Per-NPC slot claim/release per reaction**~~ — opens a window for parallel PlayerTurns to interleave between NPC1's release and NPC2's claim, breaking causal-ref integrity. Rejected.
- ~~**Concurrent NPC turns (Concurrent pattern from DP-Ch51)**~~ — would let all 3 NPCs commit simultaneously. Rejected because narrative coherence requires deterministic ordering ("Lão Ngũ noticed first; THEN Tiểu Thúy looked confused").
- ~~**Bundled multi-actor reaction event**~~ — one EVT-T2 with 3 actors in payload. Rejected because EVT-T2's actor field is singular per spec, and event-log queries become awkward (can't filter "all events by NPC X"). Each NPC reaction stays its own event.

### 8.2 LLM call sequencing within batch (locked) — sequential, not parallel

For each candidate in the batch, the orchestrator runs an LLM call (one per NPC). Locked: **sequential, not parallel**. Alternatives:

- ~~**Parallel LLM streams**~~ — would reduce wall-clock latency from ~3×LLM_time to ~1×LLM_time, but each NPC's reaction may need to "see" what the previous NPC just said (Tier 4 fairness, narrative beat consistency). Sequential is the only way to feed `previous_reactions` into the LLM prompt for NPCs 2 and 3.

Sequential adds total wall-clock = sum of N LLM calls. V1 with ≤3 reactions and ~3-5s/call → 9-15s. Acceptable for turn-based; UI shows progress indicator ("Mọi người đang phản ứng...").

### 8.3 Cascade depth = 1 (locked V1)

Locked: NPC reactions do **NOT** trigger further NPC reactions in V1. The Chorus batch resolves once and completes. Reasons:

- Cascade depth ≥2 risks combinatorial explosion (3 NPCs each trigger 3 sub-reactions = 9; depth 3 = 27).
- LLM budget per turn becomes unpredictable.
- V2+ may introduce explicit `cascade_policy: { depth: 2, max_total: 6 }` per scene if narrative needs demand.

If a Tier-1 reaction includes content that naturally would provoke another NPC (e.g., NPC1 insults NPC2), that NPC2 reaction lands in the **next** PlayerTurn cycle (the PC's next submit), not within this Chorus batch. Players experience this as "Lão Ngũ scoffs at Du sĩ; on my next turn, I see Du sĩ glare back."

### 8.4 Cap = 3 (locked V1) — softening to "average 1.5"

Locked: V1 cap is at most 3 reactions per Trigger. Most triggers will produce 0-2 reactions because:

- Tier 4 (default) only emits if hash falls in top 1/3 quantile (§6.3).
- Quiet PC actions (e.g., sipping tea silently) produce zero candidates → zero reactions.
- Loud / addressed actions produce 1-3.

Across SPIKE_01's 17 turns, expected reaction-budget is ~10-15 EVT-T2 events, not 51 (= 17 × 3 max).

### 8.5 MV12-D8 narration taxonomy (resolved here)

MV12-D8 asked: "what kinds of TurnEvent payloads exist beyond Speak/Action/MetaCommand/FastForward?" NPC_002's answer: **no new sub-shapes; metadata-rich Speak/Action carries the granularity.**

Closed set (V1, locked):
- **EVT-T1 PlayerTurn sub-shapes:** Speak, Action, MetaCommand, FastForward, Narration (flavor, post-FastForward) — locked by PL_001 §3.5 + EVT-T1 spec
- **EVT-T2 NPCTurn sub-shapes:** Speak, Action, Narration (no MetaCommand, no FastForward in V1)

Within those sub-shapes, the `TurnEvent` payload metadata fields differentiate:

```rust
pub struct TurnEvent {
    // ... existing PL_001 §3.5 fields ...

    pub reaction_intent: Option<ReactionIntent>,    // None for PlayerTurn; Some for EVT-T2 (per §6.4)
    pub aside_target: Option<ActorId>,              // for Speak with reaction_intent=AsideToNeighbor
    pub action_kind: Option<ActionKind>,            // for Action: Move | Gesture | Observe | Use
}

pub enum ActionKind {
    Move { delta: PositionDelta },                  // intra-cell movement
    Gesture { kind: GestureKind, target: Option<ActorRef> },
    Observe { target_event_ref: u64 },              // SilentObservation: notes another event
    Use { item: ItemRef, target: Option<ActorRef> }, // V2 — depends on inventory; placeholder
}

pub enum GestureKind {
    Nod, Shake, Bow, Smile, Frown, Glare, Sigh, /* ... ~12 closed-set */
}
```

**Why no new sub-shape:** sub-shapes are coarse categories that affect commit primitive (advance_turn vs t2_write) and validator chain. Reaction-intent variations don't need different primitives or validators — they need different rendering hints. Metadata is the right granularity.

This resolves MV12-D8 by defining the V1 closed set + extension contract: "new payload kinds add fields to existing sub-shapes, never new sub-shapes, unless they need a different commit primitive or validator chain."

---

## §9 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| LLM timeout for one NPC mid-batch | NPC's LLM call >30s | Skip that NPC; emit `Action::SilentObservation` placeholder; continue batch with remaining candidates | Audit-log the timeout; orchestrator marks `chorus_batch_state.aborted_actors += [npc]`. UI shows "Lão Ngũ im lặng quan sát" generic line. |
| All NPC LLM calls fail | Roleplay-service down | Abort batch; commit only the PC's TurnEvent; UI shows reactionless scene | Audit; on next PlayerTurn the orchestrator retries with same NPCs (deferred reactions accumulate up to 1 retry; then dropped). |
| Orchestrator crashes mid-batch | Writer-node death between reactions | Other writer-node takes over per DP-A11 failover; reads `chorus_batch_state` T1 from snapshot (≤30s loss) | Resume batch from `committed_count`. If T1 lost, abort batch and let PC notice "scene felt thin" — no duplicate commits because each EVT-T2 has its own channel_event_id. |
| Cap exceeded (more candidates than 3) | Common at high-density scenes | Top 3 by tier+rotation+hash; rest skipped | `npc_reaction_priority.last_reacted_turn` rotation ensures next Trigger gives skipped NPCs higher rotational priority. |
| All candidates are Tier 4 and hash-quantile filters out all | Quiet PC actions | Empty batch; no EVT-T2 commits | This is the "PC sips tea, nobody notices" case. Healthy. |
| One candidate's reaction A6-rejected (canon drift) | LLM produces canon-violating output | That NPC's reaction is dropped; remaining NPCs continue | Audit-log; if drift rate exceeds threshold, alert ops (LLM model regression?). |

---

## §10 Cross-service handoff

```text
PC submits → gateway → roleplay-service (PC LLM, per PL_001 §11)
    │
    ▼
gateway → world-service:
    PC's PlayerTurn validator chain (PL_001 §10)
    advance_turn(player_turn) → channel_event_id = N
    release_turn_slot
    return causality_token to gateway

    THEN immediately (same world-service handler, same writer node):
    ┌─────────────────────────────────────┐
    │ Chorus orchestrator picks up        │
    │ Trigger event (event_id = N)        │
    └─────────────────────────────────────┘
    claim_turn_slot(actor=ChorusOrchestrator, 15s, "chorus_batch")
    create chorus_batch_state T1 row { trigger_event_id: N, state: Resolving }
    │
    ▼
    Priority algorithm (§6) — no LLM, no service hops, all in-process
    selects top-3 candidates with ReactionIntent
    advance state → Reacting
    │
    ▼
    For each candidate (sequential):
        ① world-service → roleplay-service:
             AssemblePrompt(intent=npc_reply, prev_reactions=...) per PL-4
             LLM stream
             A6 output filter (PL-20)
             emit LLMProposal (EVT-T6) with proposal_id, target_npc, reaction_intent
        ② world-service consumer:
             validator chain (schema → capability → A5 cross-check → A6 → world-rule → canon-drift → causal-ref)
             on Accept: advance_turn(turn_data: TurnEvent {
                          actor: ActorId::Npc(npc_id),
                          intent: <derived from reaction_intent>,
                          narrator_text: <llm output>,
                          reaction_intent: Some(<intent>),
                          causal_refs: [N]                    // ← references PlayerTurn
                        })  → channel_event_id = N + i + 1
             on Reject: drop this candidate, continue
        ③ t2_write::<NpcReactionPriority>(npc_id, UpdateLastReactedTurn { turn: N + i + 1 })
        ④ chorus_batch_state.committed_count += 1
    ▼
    All candidates processed:
    chorus_batch_state.state = Completed
    release_turn_slot
    │
    ▼
gateway → UI: subscribe-stream delivers PC's TurnEvent + N reactions in order
UI renders them in sequence (animation cadence ~1-2s between events for readability)
```

**Latency budget:** PC's TurnEvent ack returns immediately (~200ms wall-clock). NPC reactions stream via subscribe over the next 9-15s. UI shows PC's text rendered first, then progressively the NPC reactions with a typing indicator per upcoming reaction.

**Idempotency:** orchestrator's batch is idempotent on `trigger_event_id` — if writer-node crashes and another node picks up the cell, querying the channel events shows already-committed reactions, so orchestrator resumes from where it left off (NOT from scratch).

---

## §11 Sequence: SPIKE_01 turn 5 (PC literacy slip → 3 NPCs react)

PC says: "Tiểu nhị, vĩnh ngộ tại ư phi vi tà" (quoting 《Đạo Đức Kinh chú》 — meta-knowledge slip)

```text
①  gateway: idempotency cache miss; route to roleplay-service for classification
   roleplay-service: A5 → Intent::FreeNarrative (confidence 0.97)
   PL-4 prompt with scene context; PL-5 LLM stream:
     narrator_text = "Lý Minh nâng chén trà, miệng buột ra: Tiểu nhị, vĩnh ngộ tại ư phi vi tà..."
   emit LLMProposal

②  world-service consumer:
   validator chain → Accept
   advance_turn(PlayerTurn { actor: pc_id, intent: Speak,
                              narrator_text: ..., outcome: Accepted, ... })
       → event_id = 105
   release_turn_slot
   return causality_token = T_pc to gateway

③  Chorus orchestrator picks up trigger event 105:
   claim_turn_slot(actor=ChorusOrchestrator, 15s)
   chorus_batch_state.create { trigger_event_id: 105, state: Resolving }

④  Priority algorithm (§6):
   SceneRoster = { Lão Ngũ, Tiểu Thúy, Du sĩ }
   trigger_tags = extract_knowledge_tags(narrator_text)
                = ["daoist_text", "ancient_quote"]
                  (extracted by deterministic content-tag function, NOT LLM)

   For Lão Ngũ:
     explicit_targets contains Lão Ngũ? NO
     opinion(Lão Ngũ, pc) = neutral (V1 stub)
     knowledge_tags = ["wuxia_lore", "merchant_gossip"] — no overlap with trigger_tags
     → Tier 4
     hash(npc_id=lao_ngu, trigger=105) = 731 (in top 1/3 → eligible)

   For Tiểu Thúy:
     Tier 4
     knowledge_tags = ["servant_gossip"] — no overlap
     hash = 412 (NOT in top 1/3 → filtered out)

   For Du sĩ:
     explicit_targets? NO
     opinion = neutral
     knowledge_tags = ["daoist_text", "wuxia_lore", "scholar_canon"] — overlap with trigger_tags!
     → Tier 3 (relevant-knowledge match)

   Sort: [Du sĩ Tier 3, Lão Ngũ Tier 4, Tiểu Thúy filtered out]
   Cap V1=3, but only 2 survive.

⑤  ReactionIntent assignment (§6.4):
   Du sĩ Tier 3 → SilentObservation OR PhysicalAction
        deterministic RNG seeded by hash(105, du_si) → PhysicalAction
   Lão Ngũ Tier 4 → weighted across 5; deterministic → SilentObservation
   Tiểu Thúy: filtered out earlier — no reaction emitted

⑥  Sequential reactions:

   Reaction 1 — Du sĩ:
     world-service → roleplay-service:
       AssemblePrompt(intent=npc_reply, npc=du_si,
                      reaction_intent=PhysicalAction, prev_reactions=[])
     LLM: "Du sĩ ngừng tay, đặt chén trà xuống, nhìn thẳng Lý Minh"
     LLMProposal → validator → Accept
     advance_turn(NPCTurn {
       actor: ActorId::Npc(du_si),
       intent: TurnIntent::Action,
       narrator_text: "...",
       reaction_intent: Some(PhysicalAction),
       action_kind: Some(Gesture { kind: Glare, target: Some(pc_id) }),
       causal_refs: [105],
       outcome: Accepted, ...
     }) → event_id = 106
     t2_write npc_reaction_priority(du_si, last_reacted=106)

   Reaction 2 — Lão Ngũ:
     world-service → roleplay-service:
       AssemblePrompt(intent=npc_reply, npc=lao_ngu,
                      reaction_intent=SilentObservation,
                      prev_reactions=[ev106])
     LLM: "Lão Ngũ liếc nhìn thoáng, không nói gì, tiếp tục lau bàn"
     LLMProposal → validator → Accept
     advance_turn(NPCTurn {
       actor: ActorId::Npc(lao_ngu),
       intent: TurnIntent::Action,
       narrator_text: "...",
       reaction_intent: Some(SilentObservation),
       action_kind: Some(Observe { target_event_ref: 105 }),
       causal_refs: [105],
       outcome: Accepted, ...
     }) → event_id = 107
     t2_write npc_reaction_priority(lao_ngu, last_reacted=107)

⑦  Batch complete:
   chorus_batch_state.state = Completed
   release_turn_slot
   (orchestrator clears the T1 row at next batch start; lazy GC.)

⑧  UI multiplex stream delivers events 105 → 106 → 107 in order.
   UI renders with ~1.5s pause between for readability.
   PC sees: own line → Du sĩ glare → Lão Ngũ silent observation.
```

**Verification:**
- All 3 events have `causal_refs=[105]` → query "what reactions did turn 105 trigger?" returns events 106, 107.
- `turn_number` advances 3 times (104→105 PC, 105→106 Du sĩ, 106→107 Lão Ngũ).
- Tiểu Thúy not reacting is intentional (hash quantile filter); tracked in audit by NOT having an event with her as actor for trigger 105.
- Replay reproduces: same NPCs, same intents, same order, same narration (subject to LLM determinism configurable per PL-5).

---

## §12 Sequence: PC enters cell (membership trigger)

When a PC `/travel`s into a new cell (PL_001 §13), DP emits `MemberJoined { actor: pc_id }` SystemEvent. Should NPCs in the new cell react?

Locked: **YES, MemberJoined IS a Trigger.** Chorus orchestrator on the new cell observes the SystemEvent, runs priority algorithm with `TriggerContext { kind: MembershipChange, actor_added: pc_id }`. Existing NPCs in the cell are candidates. Tier assignment differs slightly:

- Tier 1: NPCs with explicit `greeting_obligation` flag (innkeepers, guards, vendors) — always greet new PCs. From `npc_reaction_priority.metadata.greeting_obligation = true`.
- Tier 2: NPCs with high opinion (V2+ when NPC_001 lands)
- Tier 3: skipped (no knowledge-tag matching for membership triggers)
- Tier 4: ambient default — small probability of acknowledgment

ReactionIntent for membership triggers:
- Tier 1 → DialogueResponse ("Welcome traveler" / "Greetings stranger" — tone per NPC personality)
- Tier 4 → AsideToNeighbor or SilentObservation (low-stakes ambient)

V1 LIMIT: only 1 NPC reacts to a MemberJoined trigger by default (cap=1, not 3) — too many "Hi, welcome!" lines feels spammy. Configurable per scene metadata in V2+.

---

## §13 Sequence: cascade rejected (V1)

Du sĩ's reaction at event 106 includes a Glare gesture targeting PC. Could Tiểu Thúy then react to Du sĩ's glare ("she gasps")?

V1 answer: **NO.** Cascade depth = 1; only events with `causal_refs ⊃ {pc_turn}` directly trigger reactions. NPC-to-NPC chains are deferred to V2+.

If narrative coherence demands Tiểu Thúy notice Du sĩ's reaction, the PC's NEXT turn (turn 6) sees the prior scene state and the LLM can include "Tiểu Thúy thấp giọng hỏi lão Ngũ: 'Du sĩ kia có vẻ tức giận?'" within Tiểu Thúy's reaction to that next PC turn.

The trade-off: less reactive scenes; more predictable cost. Acceptable for V1.

---

## §14 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service can pass these scenarios. Each is one row in the integration test suite. LOCK granted after all 10 pass.

### 14.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-CHO-1 SPIKE_01 TURN 5 REPRODUCIBILITY** | PC `Lý Minh` types literacy-slip narrator at `cell:yen_vu_lau` (turn 105). 3 NPCs co-present (Lão Ngũ, Tiểu Thúy, Du sĩ). | Priority algorithm runs deterministically: Du sĩ → Tier 3 (knowledge_tag overlap "daoist_text") → ReactionIntent=PhysicalAction; Lão Ngũ → Tier 4 hash 731 (top 1/3) → SilentObservation; Tiểu Thúy → Tier 4 hash 412 (NOT top 1/3) → filtered. Sequential LLM calls; 2 **EVT-T1 Submitted/NPCTurn** events committed at event_id 106 + 107 with `causal_refs=[105]` per EVT-A6. UI multiplex stream delivers events in order. |
| **AC-CHO-2 EMPTY BATCH** | PC submits a quiet action ("Lý Minh sips tea silently"); content-tag extraction returns empty trigger_tags; no NPC priority match. | All NPCs in scene fall to Tier 4; hash quantile filter (top 1/3) selects 0 candidates OR all candidates are filtered. Chorus orchestrator commits empty batch (no NPCTurn events); `chorus_batch_state.state = Completed` with `committed_count=0`; turn-slot released cleanly. |
| **AC-CHO-3 MEMBER-JOINED TRIGGER** | PC `/travel`s into a new cell; DP emits `MemberJoined { actor: pc_id }` SystemEvent. | Chorus picks up MemberJoined as Trigger per §12; priority assignment with `TriggerContext { kind: MembershipChange }`: greeting_obligation NPCs → Tier 1; cap=1 for membership triggers (tighter than cap=3 for PlayerTurns); single greeting NPCTurn committed with `reaction_intent=DialogueResponse`. |

### 14.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-CHO-4 LLM TIMEOUT MID-BATCH** | NPC #2's LLM call exceeds 30s timeout. | Skip that NPC; commit a placeholder `EVT-T1 Submitted/NPCTurn { reaction_intent: SilentObservation, narrator_text: "<NPC name> im lặng quan sát" }`; continue batch with NPC #3; `chorus_batch_state.aborted_actors += [npc_2]` for audit. Rest of batch unaffected. |
| **AC-CHO-5 CASCADE-DEPTH OVERFLOW** | NPC #1's reaction includes content that COULD trigger another NPC's reaction (e.g., a glare at NPC #2). | V1 cascade=1 enforced: orchestrator does NOT recursively trigger Chorus on NPC #1's reaction. NPC #2's potential reaction lands in NEXT PlayerTurn cycle (when PC submits next turn) per §13 V1 boundary. |
| **AC-CHO-6 ORCHESTRATOR CRASH MID-BATCH** | Writer-node death at NPC #2's commit (between #1 and #3). | New writer node takes over per DP-A11 failover; reads `chorus_batch_state` T1 from snapshot (≤30s loss); resumes batch from `committed_count=1`; emits NPC #2 + #3 fresh. No duplicate commits because each `EVT-T1 Submitted/NPCTurn` has unique `channel_event_id`. |
| **AC-CHO-7 ALL-CANDIDATES-LOW-PRIORITY** | 8 NPCs in scene; all Tier-4 (no addressed, no high-rel, no knowledge match); hash quantile filter applies. | Top 1/3 quantile = top 2-3 NPCs by hash; cap V1=3; commits up to 3 reactions; rest filtered out. `npc_reaction_priority.last_reacted_turn` rotation ensures next Trigger gives skipped NPCs higher rotational priority (fairness). |

### 14.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-CHO-8 STRICT TURN-SLOT** | While Chorus orchestrator holds turn-slot under `ChorusOrchestrator` synthetic actor, a PlayerTurn from another PC submit arrives at the same cell. | Concurrent submit detected by turn-slot Strict pattern (PL_001 §8.1); rejects with `world_rule.concurrent_turn` per PL_002 AC-GR-7-style; second PC's UI shows "Đợi nhân vật khác hành động xong"; first batch completes uninterrupted. |
| **AC-CHO-9 SEQUENTIAL LLM CALLS** | Batch with 3 candidates; verify LLM call ordering. | NPC #1 prompt has `prev_reactions=[]`; NPC #2 prompt has `prev_reactions=[<event_id of NPC #1>]`; NPC #3 prompt has `prev_reactions=[<event_id #1, event_id #2>]`. Each subsequent NPC's narration sees prior reactions; narrative consistency verified by integration test scoring. |
| **AC-CHO-10 EVENT-MODEL CITATION VALIDITY** | All 2 reactions from AC-CHO-1 verified at event-log level. | `query_scoped_channel<TurnEvent>(... predicate=field_eq(actor.is_npc, true))` returns 2 rows; each carries `event_kind=EVT-T1 Submitted` with `sub_type=NPCTurn`; no events with stale `EVT-T2` discriminator (Option C compliance). Causal_refs exactly `[105]` for both. |

**Lock criterion:** all 10 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-acceptance criteria) → `LOCKED` (after tests).

---

## §15 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| CHO-D1 | Cascade depth ≥2 with explicit policy | V2+ (after V1 stabilizes) |
| CHO-D2 | NPC-NPC reaction edge — Tier 5 = "react to another NPC's reaction" | V2+; needs cascade depth >1 |
| CHO-D3 | Per-scene `cap_override` (e.g., bustling market = cap 5; private bedroom = cap 1) | V2+ (scene metadata extension) |
| CHO-D4 | NPC-to-orchestrator binding for cross-cell NPCs (NPC walking into a different cell mid-scene) | NPC_001 (§3.6 PL_001 NPC handoff defer) |
| CHO-D5 | Concurrent NPC turns for Concurrent turn-slot pattern (DP-Ch51) — bypass Strict for high-throughput crowds | V2+; would require a separate NPCTurn ordering proof |
| CHO-D6 | Knowledge tag extraction from narrator_text | Phase 5 ops (initial dictionary; iterate from V1 telemetry) |
| CHO-D7 | Fairness rotation tuning — V1 uses `last_reacted_turn` distance; should it weight by character importance? | Phase 5 ops |
| CHO-D8 | LLM batch parallelism in V2+ — can NPCs react in parallel if their reactions don't see each other (e.g., Tier 4 ambient NPCs)? | V2+ optimization |

---

## §16 Cross-references

- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) — turn-slot Strict, channel ordering, causal_refs
- [PL_001b Continuum lifecycle](../04_play_loop/PL_001b_continuum_lifecycle.md) — sequence patterns this feature mirrors
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — tool-call allowlist for actor_type=NPC_Reactive
- [NPC_001 Cast](NPC_001_cast.md) — NPC foundation; provides ActorId variants, NpcOpinion::for_pc realization, persona assembly used by §6 priority + §10 cross-service handoff
- [07_event_model/02_invariants.md](../../07_event_model/02_invariants.md) — EVT-A1..A8 (esp. EVT-A4 producer binding, EVT-A6 typed causal-refs, EVT-A7 LLM proposal)
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T2 NPCTurn (this feature's primary emission category); EVT-T6 LLMProposal (input)
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — MV12-D8 resolved here (no new sub-shapes; metadata-rich Speak/Action)
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — turn 5 obs#6 grounding

---

## §17 Implementation readiness checklist

- [x] **§2.5** EVT-T* mapping (all events map to existing categories)
- [x] **§3** Aggregate inventory (2 new: `npc_reaction_priority`, `chorus_batch_state`)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives (incl. orchestrator-actor turn-slot pattern)
- [x] **§6** Priority algorithm with 4 tiers + within-tier ordering + cap
- [x] **§7** Capability requirements
- [x] **§8** Pattern choices: batched orchestrator, sequential LLM, cascade=1, cap=3, MV12-D8 resolved (no new sub-shapes)
- [x] **§9** Failure-mode UX (6 failure cases)
- [x] **§10** Cross-service handoff
- [x] **§11** SPIKE_01 turn 5 sequence (3-NPC scene, 2 commits)
- [x] **§12** Membership trigger sequence
- [x] **§13** Cascade-rejection sequence (V1 boundary)
- [x] **§14** Acceptance criteria (10 scenarios across happy-path / failure-path / boundary; SPIKE_01 turn 5 reproducibility verified by AC-CHO-1)
- [x] **§15** Deferrals (CHO-D1..D8)

**Status transition:** DRAFT 2026-04-25 (originally drafted as PL_003 Chorus then relocated to NPC_002 per boundary review) → Option C terminology applied by event-model agent (EVT-T2 → EVT-T1 sub-type=NPCTurn) → **CANDIDATE-LOCK 2026-04-26** (closure pass: §14 acceptance criteria added).

LOCK granted after the 10 §14 acceptance scenarios have passing integration tests. NPC_001 Cast (now CANDIDATE-LOCK) provides the real `NpcOpinion::for_pc` projection that Tier-2 priority resolution consumes.

**Next** (when this doc locks): world-service adds Chorus orchestrator module; roleplay-service adds NPC reaction prompt template; gateway no change (Chorus is server-internal). Vertical-slice target: SPIKE_01 turn 5 reproduces with deterministic 2-NPC reaction order.
