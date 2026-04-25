# NPC_001 — Cast (NPC Foundation)

> **Conversational name:** "Cast" (CST). The cast of NPCs in a reality — their identity, persona, owner-node binding, handoff protocol, opinion-with-PC stub, and the EVT-T2 NPCTurn producer contract. Pairs with NPC_002 Chorus (which orchestrates multiple NPCs reacting): Cast designs the actors; Chorus directs them.
>
> **Category:** NPC — NPC Systems
> **Status:** **CANDIDATE-LOCK 2026-04-26** (DRAFT 2026-04-25 → Option C terminology applied by event-model agent → CANDIDATE-LOCK 2026-04-26 closure pass: §14 acceptance criteria added)
> **Catalog refs:** NPC-1 (proxy derivation), NPC-2 (persona assembly), NPC-10 (tool calling). NPC-3a/b/c/e/f (R8 storage) consumed unchanged.
> **Builds on:** [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) §3.6 actor_binding (resolves NPC handoff defer), [NPC_002 Chorus](NPC_002_chorus.md) (consumer of `npc_reaction_priority` + `NpcOpinion::for_pc` stub), [02_storage R8](../../02_storage/R08_npc_memory_split.md) (locks `npc` core + `npc_session_memory` + `npc_pc_relationship_projection`)
> **Resolves:** PL_001 §3.6 NPC handoff defer; NPC_002 §3 NPC_001 dependency stub; OOS-1 NPC↔SessionContext mapping (the part Event Model said belongs to features); ActorId variant model (used by NPC_002 §11)
> **Defers to:** [PCS_001](../06_pc_systems/) (not yet designed) for `PcId` newtype + xuyên không soul-body model — Cast references `PcId` abstractly. [DL_001](../12_daily_life/) (not yet) for NPC routine scenes (NPC-8 → DF1).

---

## §1 User story (concrete — SPIKE_01 cast)

A reality is born from Thần Điêu Đại Hiệp. RealityManifest declares 3 anchored NPCs at `cell:yen_vu_lau` for fiction-time 1256-thu-day3:

1. **Lão Ngũ** — 65, owner-keeper of Yên Vũ Lâu. core_beliefs: ex-jianghu, distrustful of strangers, loyal to old codes. flexible_state: today his joints ache (rainy season). knowledge_tags: {"wuxia_lore", "merchant_gossip", "river_routes"}. greeting_obligation: false (he's an innkeeper but selectively distant).
2. **Tiểu Thúy** — 16, illiterate orphan waitress. core_beliefs: kind, observant, indebted to Lão Ngũ for shelter. flexible_state: nervous around armed strangers. knowledge_tags: {"servant_gossip", "yen_vu_lau_layout"}. greeting_obligation: true (her job).
3. **Du sĩ** — 40s, traveling scholar. core_beliefs: classical scholar, judges by literacy. flexible_state: mid-journey, reading 《Đạo Đức Kinh chú》. knowledge_tags: {"daoist_text", "wuxia_lore", "scholar_canon"}. greeting_obligation: false (transient).

When PC `Lý Minh` arrives (turn 1) and quotes meta-knowledge (turn 5), all three should react per their persona — Du sĩ sharply observant (knowledge match), Lão Ngũ silently noting (Tier 4 ambient), Tiểu Thúy filtered out (NPC_002 §11). Their reactions feed back into per-(NPC, PC) opinion via the `npc_pc_relationship_projection` (R8-locked).

**This feature design specifies:** how each NPC has identity (NpcId, ActorId variant); where their persona lives (R8 aggregate references + new persona-assembly contract); which game-node owns the NPC's writes (refinement of PL_001 §3.6); how an NPC moves between cells across writer-node boundaries (resolves §3.6 defer); how NPC_002's `NpcOpinion::for_pc` stub becomes a real read; what JWT claims world-service needs to commit EVT-T2 NPCTurn on each NPC's behalf.

After this lock: world-service can implement NPC orchestration; NPC_002 Chorus can resolve Tier 2 (high-relationship) candidates from real opinion data; NPC reactions in SPIKE_01 are reproducible with deterministic ordering; cross-cell NPC moves work without breaking writer-node binding.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **NpcId** | Newtype `pub struct NpcId(pub Uuid)` | Distinct from `PcId` (owned by PCS_001) and `glossary_entity_id` (book-side). Derived deterministically from `(reality_id, glossary_entity_id)` for canonical NPCs (NPC-1 catalog: "NPC proxy derivation from glossary entity"). Author-created NPCs get fresh UUIDs. |
| **ActorId (closed enum)** | `pub enum ActorId { Pc(PcId), Npc(NpcId), Synthetic { kind: SyntheticActorKind }, Admin(AdminId) }` | Locked here. `Pc`/`PcId` deferred to PCS_001. `Synthetic` covers ChorusOrchestrator (NPC_002), BubbleUpAggregator, scheduler. `Admin` covers S5 actors. |
| **SyntheticActorKind** | Closed enum: `ChorusOrchestrator \| BubbleUpAggregator \| Scheduler \| RealityBootstrapper` | V1; V2+ adds. |
| **NpcOwnerNode** | Mapping `NpcId → NodeId` resolving who writes the NPC's events | Refines PL_001 §3.6 `BindingKind::NPC_OwnerNode_<node_id>`. V1: deterministic `hash(npc_id) mod cluster_size`. Failover: re-hash on cluster membership change with explicit handoff. |
| **NpcPersona** | Read-side projection assembled per LLM call | NOT a separate aggregate — derived from `npc.core_beliefs` + `npc.flexible_state` + `npc_session_memory` + `npc_pc_relationship_projection` per request. See §6. |
| **NpcOpinion** | Read view backed by `npc_pc_relationship_projection` (R8-locked) | Trait `NpcOpinion::for_pc(npc_id, pc_id) → OpinionScore` — implementation queries the projection. NPC_002 stub becomes real here. |
| **NpcCategory** | Closed enum: `Reactive \| Routine \| Ambient` | V1: `Reactive` only. `Routine` (V1+30d per EVT-T10) and `Ambient` (no LLM, decorative-only) are scaffolded but not active. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11; Option C redesign 2026-04-25)

**Updated 2026-04-25 Option C redesign:** EVT-T2 NPCTurn was `_withdrawn` per I15; "NPCTurn" now lives as a sub-type of EVT-T1 Submitted (which generalizes "actor explicitly emits with intent" — covers PC, NPC, future quest-engine actors uniformly).

| Cast-relevant event | EVT-T* | Sub-type | Producer | Notes |
|---|---|---|---|---|
| NPC speaks/acts (reaction or routine) | **EVT-T1 Submitted** | `NPCTurn` (formerly EVT-T2; merged 2026-04-25) | Orchestrator role (world-service) | Cast supplies persona context for AssemblePrompt; NPC_002 Chorus orchestrates ordering |
| NPC opinion update | **EVT-T3 Derived** | aggregate_type=`npc_pc_relationship_projection` | Aggregate-Owner role (world-service) post-validate | Causal-ref to triggering NPCTurn |
| NPC LLM proposal (pre-validate) | **EVT-T6 Proposal** | `NPCTurnProposal` | LLM-Originator role (roleplay-service) | Promoted to EVT-T1 Submitted/NPCTurn on validate |
| Canonical NPC bootstrap (RealityManifest seed) | **EVT-T4 System** | `MemberJoined { joined_via: CanonicalSeed }` | DP-Internal | Per PL_001 §16.4 |
| Cross-cell NPC handoff (V1+) | **EVT-T3 Derived** (`aggregate_type=actor_binding`) + DP-emitted **EVT-T4 System** (`MemberLeft` + `MemberJoined`) | (above) | Aggregate-Owner role + DP | See §12 |

No new EVT-T* row. **EVT-T2 references throughout this doc** updated semantically: NPCTurn is now "EVT-T1 Submitted with sub-type=NPCTurn".

---

## §3 Aggregate inventory

Five aggregates total: 3 imported from R8 (locked by 02_storage; Cast adds DP-A14 scope/tier annotations only), 2 new owned by Cast.

### 3.1 `npc` (R8-locked, scope/tier annotated by Cast)

```rust
// Aggregate body locked by 02_storage R8-L1 (R08_npc_memory_split.md §12H.2).
// Cast adds the DP-A14 scope/tier markers + ActorId integration.
#[derive(Aggregate)]
#[dp(type_name = "npc", tier = "T2", scope = "reality")]
pub struct Npc {
    pub npc_id: NpcId,
    pub glossary_entity_id: GlossaryEntityId,
    pub current_region_id: ChannelId,           // points to a cell channel — replaces R8's region notion with DP channel
    pub current_session_id: Option<SessionId>,  // R7-L6 invariant: NPC in ≤1 session at a time. None when idle/ambient.
    pub mood: NpcMood,                          // current emotional state (-100..+100)
    pub core_beliefs: CanonRef,                 // L1 canon reference (book-derived, immutable per realities)
    pub flexible_state: FlexibleState,          // L3 reality-local drift (per-reality emergent)
}
```

- T2 + RealityScoped: ~10-20 KB per row, stable regardless of player count (R8-L1). Reality-global because NPCs move across channels — they're not channel-bound.
- One row per `(reality_id, npc_id)`.
- Locked by R8; Cast does NOT redesign — only adds DP scope/tier and ActorId binding.

### 3.2 `npc_session_memory` (R8-locked, scope/tier annotated by Cast)

```rust
#[derive(Aggregate)]
#[dp(type_name = "npc_session_memory", tier = "T2", scope = "reality")]
pub struct NpcSessionMemory {
    pub id: NpcSessionMemoryId,                 // = uuidv5(npc_id, session_id) per R8
    pub npc_id: NpcId,
    pub session_id: SessionId,                  // session this memory belongs to
    pub summary: String,                        // ≤2000 chars per R8-L2
    pub facts: Vec<MemoryFact>,                 // ≤100 LRU per R8-L2
    pub embeddings_ref: Option<EmbeddingRef>,   // separated to pgvector dedicated table per R8-L6
}
```

- T2 + RealityScoped (NOT channel-scoped: memory follows the NPC, not the cell).
- Per R8-L2: bounded to 100 facts + 2000-char summary; LRU eviction; rolling LLM summary rewrite every 50 events.
- Locked by R8.

### 3.3 `npc_pc_relationship_projection` (R8-locked, scope/tier annotated by Cast)

```rust
#[derive(Aggregate)]
#[dp(type_name = "npc_pc_relationship_projection", tier = "T2", scope = "reality")]
pub struct NpcPcRelationshipProjection {
    pub id: NpcPcRelationshipId,                // = uuidv5(npc_id, pc_id)
    pub npc_id: NpcId,
    #[dp(indexed)] pub pc_id: PcId,
    pub trust: i16,                             // -100..+100
    pub familiarity: u16,                       // 0..u16::MAX (interaction count, capped)
    pub stance_tags: Vec<StanceTag>,            // {"wary", "respectful", "fond", "amused", ...} closed set
    pub last_updated_turn: u64,                 // for staleness telemetry
}
```

- T2 + RealityScoped.
- Derived from `npc_session_memory` at session-end (per R8 §12H.2) — Cast does NOT directly write; world-service derives + writes per-pair.
- Read by NPC_002 Chorus Tier-2 priority. **This is the realization of NPC_002's `NpcOpinion::for_pc` stub.**

### 3.4 `npc_node_binding` (NEW, owned by Cast)

```rust
#[derive(Aggregate)]
#[dp(type_name = "npc_node_binding", tier = "T2", scope = "reality")]
pub struct NpcNodeBinding {
    #[dp(indexed)] pub npc_id: NpcId,
    pub owner_node: NodeId,                     // current owner node (writes EVT-T2 NPCTurn for this NPC)
    pub current_cell: ChannelId,                // current cell location (denormalized from actor_binding for fast lookup; reconciled per turn)
    pub epoch: u64,                             // bumps on handoff; old owner's writes rejected after bump
    pub last_handoff_at_turn: Option<u64>,
}
```

- T2 + RealityScoped: critical for cross-node coordination; must survive restarts.
- One row per NPC.
- **Refines** PL_001 §3.6 `BindingKind::NPC_OwnerNode_<node_id>` from a string discriminator into an explicit aggregate. Reason: BindingKind was an `enum` in PL_001 (immutable until rewrite); Cast needs a dynamic owner that may handoff at runtime, requiring a real aggregate with epoch fencing.
- `owner_node` derivation: V1 = `hash(npc_id) mod live_node_count` snapshot at reality bootstrap; mutated only by explicit handoff (§12).

### 3.5 `npc_reaction_priority` — REFERENCE (NPC_002-owned)

NPC_002 §3.1 defined this aggregate. Cast does NOT redefine. NPC_001 only:

- Documents that `NpcReactionPriority.knowledge_tags` is **populated at NPC bootstrap** from `Npc.core_beliefs` (R8 aggregate's canon reference) — book canon declares which knowledge tags each canonical NPC has. Author UI may edit.
- `NpcReactionPriority.base_priority_tier` is a hint, NOT authoritative. Final tier is computed live by NPC_002 §6 algorithm using the data freshly read from `Npc` + `npc_pc_relationship_projection`.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `npc` | T2 | T2 | Reality | ~3/turn during Chorus (§6 persona assembly) | ~0.5/turn (mood drift) | R8-L1 locked. |
| `npc_session_memory` | T2 | T2 | Reality | ~1/NPC/turn during Chorus | ~1/NPC/turn (interaction logged) | R8-L1 locked. |
| `npc_pc_relationship_projection` | T2 | T2 | Reality | ~1/NPC/Chorus-batch | derived per session-end (R8 §12H.2) | R8-L1 locked. |
| `npc_node_binding` | T2 | T2 | Reality | ~1/NPC at orchestrator pickup | ~0 (only on handoff) | New; needed for cross-node writes. |
| (NPC_002 `npc_reaction_priority`) | (NPC_002 §4) | | | | | |

No T0, no T1, no T3 in this feature. Justification: NPC state must persist (no T0/T1); no cross-aggregate atomicity needed (no T3 — relationship + memory writes are independent commits with causal_refs).

---

## §5 DP primitives this feature calls

### 5.1 Reads (per Chorus batch)

```rust
// Persona assembly read fan-out (§6)
let npc       = dp::read_projection_reality::<Npc>(ctx, npc_id, wait_for=None, ...).await?;
let memory    = dp::read_projection_reality::<NpcSessionMemory>(ctx,
                  NpcSessionMemoryId::derive(npc_id, session_id),
                  wait_for=None, ...).await?;
let opinion   = dp::read_projection_reality::<NpcPcRelationshipProjection>(ctx,
                  NpcPcRelationshipId::derive(npc_id, pc_id),
                  wait_for=None, ...).await?;
let binding   = dp::read_projection_reality::<NpcNodeBinding>(ctx, npc_id, ...).await?;
```

Performed in parallel (4 reads). Cache hits expected (95%+ per DP-S* SLO). Wall-clock: ≤20ms p99 if all cache-hit.

### 5.2 Writes (per turn / handoff)

```rust
// Mood drift after a turn
dp::t2_write::<Npc>(ctx, npc_id, NpcDelta::MoodShift { delta }).await?;

// Session memory updated post-turn (R8 emission pattern, §12H.2)
dp::t2_write::<NpcSessionMemory>(ctx, memory_id, MemoryDelta::Interaction { event_ref, importance }).await?;

// Relationship projection: derived; world-service emits at session-end
dp::t2_write::<NpcPcRelationshipProjection>(ctx, rel_id, RelationshipDelta::FromSession { ... }).await?;

// Handoff (rare)
dp::t3_write::<NpcNodeBinding>(ctx, npc_id, BindingDelta::Handoff { new_owner, new_epoch }).await?;
```

The handoff write is T3 because it carries epoch fencing — must be globally visible before any new owner can write.

### 5.3 Channel ops (handoff only)

- `dp::DpClient::move_session_to_channel` — NOT applicable (NPCs are not sessions).
- Custom NPC-cell move: `dp::t2_write::<actor_binding>` (PL_001 §3.6) updates location; if cell change crosses node boundaries, follow §12 handoff protocol.

---

## §6 Persona assembly contract (NPC-2 catalog resolution)

The NPC's "persona" for an LLM prompt is assembled per-call from 4 reads + a deterministic combiner. NOT stored as a flat aggregate.

### 6.1 Inputs

```rust
pub struct PersonaAssemblyInputs {
    pub npc:       Npc,                         // core_beliefs, flexible_state, mood
    pub memory:    NpcSessionMemory,            // summary + recent facts
    pub opinion:   NpcPcRelationshipProjection, // trust, familiarity, stance_tags
    pub scene:     SceneState,                  // ambient context (PL_001 §3.2)
    pub trigger:   TurnEvent,                   // what we're reacting to
    pub prev_reactions: Vec<TurnEvent>,         // earlier reactions in this Chorus batch (§NPC_002 §10)
    pub reaction_intent: ReactionIntent,        // NPC_002 §6.4 assigned intent
    pub fiction_time: FictionTimeTuple,         // for "is it night? am I sleepy?" tone shifts
}
```

### 6.2 Combiner (deterministic)

```rust
fn assemble_persona(inputs: PersonaAssemblyInputs) -> PromptSlots {
    PromptSlots {
        system_voice: format!(
            "You are {npc_name}, a {role}. Core: {core_beliefs}. Today: {flexible_state}. \
             Mood: {mood_label}. You see PC {pc_name} ({stance}, trust {trust}, met {familiarity} times). \
             Recent memory: {summary}. Last 5 facts: {top5_facts}.",
            ...
        ),
        scene_context: format!(
            "Setting: {scene.ambient.weather} {scene.time_of_day_qualifier} at {place}. \
             Other actors here: {other_actor_names_redacted_by_visibility}. \
             Earlier this turn: {prev_reactions_rendered_or_none}.",
            ...
        ),
        intent_directive: match inputs.reaction_intent {
            DialogueResponse => "Respond verbally, in {npc_voice_register}.",
            PhysicalAction => "Describe a physical action — gesture, posture shift, expression.",
            SilentObservation => "Note silently. Output the brief 'observation' as 3rd-person narration; do NOT add dialogue.",
            AsideToNeighbor { target } => "Whisper to {target_name}. Output enclosed in quotes prefixed with whisper-marker.",
            StartleOrFlee => "React with surprise; describe an exit or step-back.",
        },
        canon_grounding: dp::oracle_query(/* PL-16 */).await,
        forbidden_paraphrase: "Do NOT repeat or summarize what PC just said. React, don't transcribe.",
    }
}
```

This combiner is deterministic (no LLM) and side-effect-free. All variability comes from the LLM stage that consumes `PromptSlots`.

### 6.3 Voice register

`Npc.flexible_state` carries an optional `voice_register: Option<VoiceRegister>` field — per-NPC stable speech patterns:

```rust
pub enum VoiceRegister {
    FormalClassical,                            // Du sĩ — uses 文言 phrasing, classical metaphors
    Vernacular,                                 // Lão Ngũ — earthy, jianghu slang
    Childlike,                                  // Tiểu Thúy — short sentences, common words
    Custom(String),                             // free-form per NPC
}
```

Optional because not every NPC needs a distinct register; default is "neutral narrator-friendly Vietnamese" matching PL-22 voice mode.

### 6.4 Memory-fact selection (which 5 facts to inject)

R8-L2 caps `npc_session_memory.facts` at 100 LRU. For prompt injection, select the top-5 by relevance:

```text
score(fact, trigger) = importance_score
                       + 0.5 * (1 if trigger.actor matches fact.subject else 0)
                       + 0.3 * (1 if fact.knowledge_tags overlaps trigger_tags else 0)
                       + 0.2 * recency_decay(fact.last_accessed_at)
```

Top 5 by score, ties broken by `fact_id` hash. Update `last_accessed_at` on use → LRU stays warm for relevant facts.

NPC-3g catalog ("semantic retrieval quality") is the V1-prototype-measurement layer that may refine this scoring; Cast locks the deterministic baseline above as V1-Day-1.

---

## §7 Capability requirements

### 7.1 World-service backend (per JWT)

The world-service backend session that writes EVT-T2 NPCTurn on behalf of NPCs needs:

```json
{
  "produce": ["NPCTurn", "AggregateMutation"],
  "write": [
    { "aggregate": "npc",                              "tiers": ["T2"] },
    { "aggregate": "npc_session_memory",               "tiers": ["T2"] },
    { "aggregate": "npc_pc_relationship_projection",   "tiers": ["T2"] },
    { "aggregate": "npc_node_binding",                 "tiers": ["T2", "T3"] },
    { "aggregate": "actor_binding",                    "tiers": ["T2"] }
  ],
  "read": [
    { "aggregate": "npc",                              "tiers": ["T2"] },
    { "aggregate": "npc_session_memory",               "tiers": ["T2"] },
    { "aggregate": "npc_pc_relationship_projection",   "tiers": ["T2"] },
    { "aggregate": "npc_node_binding",                 "tiers": ["T2"] },
    { "aggregate": "scene_state",                      "tiers": ["T2"] },
    { "aggregate": "fiction_clock",                    "tiers": ["T2"] }
  ],
  "can_advance_turn": ["cell"]
}
```

`produce: NPCTurn` is the new claim Cast adds to the JWT shape — required by EVT-A4 producer-category binding.

### 7.2 Per-node binding

A world-service node only commits NPC writes for NPCs whose `npc_node_binding.owner_node == self.node_id`. Cross-node attempts are routed transparently per DP-A16 / PL_001 §3.6 — but Cast adds a CHECK at SDK time:

```rust
fn require_npc_owner_or_route(npc_id: NpcId) -> Result<(), DpError> {
    let binding = dp::read_projection_reality::<NpcNodeBinding>(ctx, npc_id).await?;
    if binding.owner_node == self_node_id() {
        Ok(())  // proceed locally
    } else {
        // SDK transparently forwards to owner's gRPC endpoint (PL_001 §10 pattern)
        Err(DpError::WrongChannelWriter { ... })  // forwarded automatically; surfaces only if route fails
    }
}
```

---

## §8 Pattern choices

### 8.1 Owner-node binding: deterministic hash V1, dynamic V2+

Locked V1: `owner_node = hash(npc_id) mod live_node_count_at_bootstrap`. Snapshot at reality activation; doesn't change unless cluster membership changes (handoff per §12).

V2+ may add: load-balancing-driven dynamic binding (NPC migrates to less-loaded node); affinity binding (NPCs in same cell prefer same owner-node for locality); explicit author-pinning (book author can fix Du sĩ to a specific node).

### 8.2 Persona assembly: deterministic combiner, NOT cached

Locked: assemble fresh per LLM call. NOT cached because:

- The 4 inputs (Npc, memory, opinion, scene) all change frequently
- Caching would add staleness without significant savings (combiner is ~50µs in-process)
- Each call's `prev_reactions` is unique per Chorus batch step, so cache key would be too granular to be effective

### 8.3 Opinion update timing: at session-end, not per turn

Locked per R8 §12H.2: `npc_pc_relationship_projection` is **derived at session-end** from accumulated `npc_session_memory.facts`. Not updated per-turn.

Why: per-turn projection updates are O(turns × NPCs × PCs) write-amplification; session-end derivation is O(NPCs × PCs)-once. NPC_002 Chorus reads the projection at start of each batch — gets the LAST-SESSION-END snapshot, NOT real-time. This is ACCEPTABLE because opinion shifts are slow (days of fiction-time) and intra-session reads are rare.

V2+ may add: `npc_pc_relationship_projection.preview` — real-time derived view computed on read, used for high-stakes scenes (combat, romance) where intra-session opinion shift matters.

### 8.4 NPC categories (V1=Reactive only)

V1 supports only `NpcCategory::Reactive` — NPCs that wait for a Trigger (PlayerTurn or NPCTurn) and respond via Chorus. `Routine` (autonomous schedule, EVT-T10) deferred to DL_001 V1+30d. `Ambient` (decorative, no LLM, just presence) deferred to V2+ (no concrete need until crowded scenes — markets, festivals).

---

## §9 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| `NpcNodeBinding` read miss (NPC orphaned) | Cluster membership changed; binding stale | SDK rejects write with `WrongChannelWriter`; orchestrator skips this NPC for current Chorus batch; retry next turn after CP re-syncs | Background reconciliation re-derives binding from `hash(npc_id) mod current_cluster`. |
| Persona assembly combiner missing data | `npc_session_memory` for new (npc, session) pair doesn't exist yet | Lazy-create empty memory row; combiner falls back to "no prior knowledge of this PC" | First-encounter NPCs get a clean slate. Expected and not surfaced as failure. |
| Persona prompt exceeds LLM context window | Memory summary + recent facts + scene + trigger > token budget | World-service truncates LRU facts (last 3 facts only) + shortens summary preview; logs warning | NPC-3g catalog: V1 prototype measures + iterates. |
| Opinion read from stale projection | Projection-applier behind by >1 session | NPC_002 Chorus uses what it gets; UI shows narrative-stale reactions | Acceptable per §8.3. V2+ preview view if pain materializes. |
| NPC handoff race (two nodes claim same NPC) | Concurrent failover detection | Loser's writes rejected by epoch fencing per §12 | Loser observes the rejection, drops state, lets the winner proceed. No duplicate commits. |
| Canonical NPC has no glossary entity | RealityManifest declares a CanonicalActorDecl whose glossary_entity_id doesn't exist | Bootstrap rejects with `BootstrapError::OrphanedActor` | Operator fixes manifest before retry. PL_001 §16.5 idempotent bootstrap. |

---

## §10 Cross-service handoff (NPC turn end-to-end)

```text
[Trigger event] PlayerTurn N committed at cell C
    │
NPC_002 Chorus orchestrator (this cell's writer node):
    select reaction candidates including npc=du_si
    │
For each candidate (sequential):
    ① Cast: read NPC inputs (4 reads in parallel)
       npc / memory / opinion / binding
    ② Cast: assemble persona (deterministic, in-process)
       returns PromptSlots
    ③ world-service → roleplay-service:
       AssemblePrompt(intent=npc_reply, slots=PromptSlots)
       LLM stream
       A6 output filter (PL-20)
       emit LLMProposal (EVT-T6) tagged with target_npc=du_si
    ④ world-service consumer:
       require_npc_owner_or_route(du_si)
         IF self_node owns: proceed locally
         ELSE: SDK transparently routes to owner node
       validator chain (schema → capability → A5 → A6 → world-rule → canon-drift → causal-ref)
       on Accept: dp.advance_turn(NPCTurn { actor: ActorId::Npc(du_si), ... })
                                  → channel_event_id = N+i+1
       on Reject: skip (NPC_002 §9)
    ⑤ Cast: post-turn writes (in causality)
       dp.t2_write::<Npc>(npc_id, NpcDelta::MoodShift { ... })
       dp.t2_write::<NpcSessionMemory>(memory_id, MemoryDelta::Interaction { ... })
       (npc_pc_relationship_projection update DEFERRED to session-end per §8.3)
    │
After all candidates:
    Chorus releases turn-slot
    UI multiplex stream delivers events
```

Wall-clock per NPC: ~20ms reads + ~500ms persona + LLM (3-5s) + ~50ms commits + ~50ms post-writes ≈ 4-6s. NPC_002 cap=3 sequential ≈ 12-18s for full batch.

---

## §11 Sequence: bootstrap canonical NPCs (RealityManifest extension)

PL_001 §16 declared `CanonicalActorDecl`. Cast extends what fields each decl carries:

```rust
pub struct CanonicalActorDecl {
    pub actor_id: ActorId,                       // ActorId::Npc(npc_id) per Cast
    pub display_name: String,
    pub initial_cell_path: Vec<String>,
    pub binding_kind: BindingKind,               // PL_001 §3.6 — Cast refines

    // ─── Cast extension ───
    pub category: NpcCategory,                   // V1: Reactive
    pub core_beliefs_ref: CanonRef,              // L1 canon link
    pub flexible_state_init: FlexibleState,      // initial drift (mood, voice_register, ...)
    pub knowledge_tags: Vec<KnowledgeTag>,       // for NPC_002 Tier-3 priority
    pub greeting_obligation: bool,               // NPC_002 §12 membership trigger
    pub priority_tier_hint: Option<u8>,          // NPC_002 §3.1 base hint
}
```

Bootstrap sequence (within PL_001 §16.2 `t3_write_multi`):

```text
For each CanonicalActorDecl:
  ① t2_write::<Npc> { npc_id, glossary_entity_id, core_beliefs: CanonRef, flexible_state, mood: Neutral, current_region_id: <to-be-resolved>, current_session_id: None }
  ② t2_write::<NpcNodeBinding> { npc_id, owner_node: hash(npc_id) % live_nodes, current_cell: <path-resolved>, epoch: 0 }
  ③ t2_write::<NpcReactionPriority> { ... } at the cell channel (NPC_002 §3.1)
  ④ t2_write::<actor_binding> { actor: ActorId::Npc(npc_id), current_channel: cell, ... }

  (npc_session_memory NOT created here — lazy on first session bind)

When first PC enters the cell (per PL_001 §16.4):
  ⑤ DP emits MemberJoined { actor: ActorId::Pc(first_pc), join_method: Move }
  ⑥ For each canonical NPC at this cell:
       DP emits MemberJoined { actor: ActorId::Npc(npc_id), join_method: CanonicalSeed }
```

**Idempotency:** re-running RealityManifest with same `reality_id` short-circuits per PL_001 §16.5. Cast's writes are part of the same atomic `t3_write_multi`.

---

## §12 Sequence: NPC handoff (resolves PL_001 §3.6 defer)

NPC `du_si` is owned by node A. PC `/travel`s du_si to a cell on node B's territory (this is rare V1 — NPCs are mostly stationary; but the protocol must exist for V1+30d routine NPCs).

**Trigger:** an EVT-T2 NPCTurn or world-rule decides `du_si` should move from `cell:gia_hung_inn` (node A) to `cell:tương_dương_west` (node B).

```text
①  Source node A (current owner) detects move:
   needs to write actor_binding(du_si, new_cell=tuong_duong_west)
   look up new_cell's writer node: B (per DP-A16 channel writer binding)
   NPC's owner is A; channel writer is B → handoff required.

②  Source A initiates handoff:
   dp.t3_write::<NpcNodeBinding>(du_si, BindingDelta::HandoffStart { target_node: B, new_epoch: epoch+1 })
       → T3 sync: new_epoch globally visible
       → A's writes with old_epoch are now rejected by Postgres (epoch fence)

③  Source A flushes pending NPC writes:
   any in-flight t2_write::<Npc> / NpcSessionMemory commits with old_epoch — last-chance acks
   future writes from A: rejected with WrongChannelWriter (route to B)

④  Target B picks up:
   B's CP delta-stream notification of NpcNodeBinding change → B reloads binding
   B begins accepting writes for du_si

⑤  Move execution (now on B):
   t2_write::<actor_binding>(du_si, MoveTo { new_cell: tương_dương_west, turn: N })
   DP emits MemberLeft(gia_hung_inn, du_si) + MemberJoined(tương_dương_west, du_si)

⑥  Cleanup:
   B has full ownership; A's stale routes time out (≤60s).
   New EVT-T2 NPCTurn for du_si commits via B.
```

**Idempotency:** `HandoffStart` carries `new_epoch`; if A retries, second write with same target_epoch is no-op. If B fails before step ⑤, A's `WrongChannelWriter` errors continue until B's CP-driven reload kicks in.

**Failure recovery:** if B dies mid-handoff, CP detects and rebinds to a fresh target node C with `new_epoch+1`. Resilient cluster.

**SLO:** handoff completes ≤35s (matching DP-A16 channel-writer-failover budget). UI shows `du_si.location` as "moving" via stale T1 read with explicit caveat copy.

---

## §13 Sequence: opinion update (session-end derivation)

Per R8 §12H.2 + Cast §8.3: `npc_pc_relationship_projection` is derived at session-end from `npc_session_memory`.

```text
On session-end signal (PC closes browser, idle timeout, /signoff):
  world-service iterates each NPC the session interacted with:
    for each (npc_id, pc_id) pair:
      memory = read NpcSessionMemory(npc_id, session_id)
      if memory.facts.len() == 0: continue (no interactions)

      ① Compute deltas from this session:
         trust_delta = sum(fact.importance_score * sign(fact.valence)) over session_facts
         familiarity_delta = count(session_facts) capped at +50
         new_stance_tags = stance_classifier(memory.summary)  // deterministic, not LLM

      ② Read existing projection:
         existing = read NpcPcRelationshipProjection(npc_id, pc_id) || default

      ③ Merge:
         new = NpcPcRelationshipProjection {
           trust: clamp(existing.trust + trust_delta, -100, 100),
           familiarity: existing.familiarity.saturating_add(familiarity_delta),
           stance_tags: merge_dedupe(existing.stance_tags, new_stance_tags),
           last_updated_turn: current_turn,
         }

      ④ t2_write::<NpcPcRelationshipProjection>(rel_id, RelationshipDelta::FromSession { delta })
         (causal_ref to session-end SystemEvent)

      ⑤ Optional: if memory.facts.len() > 50 (R8 trigger): rewrite summary via LLM
         (separate sub-process; doesn't block opinion write)
```

**Why session-end, not per-turn:** see §8.3 reasoning. PC sees opinion shift on next session (next login).

**Edge case — orphan session:** if a session crashes without `/signoff`, world-service has a 30-min idle-timeout sweeper that triggers the same derivation. Worst-case opinion staleness ≤30 min wall-clock per session.

---

## §14 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service can pass these scenarios. Each is one row in the integration test suite. LOCK granted after all 10 pass.

### 14.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-CST-1 BOOTSTRAP CANONICAL NPCs** | RealityManifest activates `R-tdd-h` with 3 canonical actors (Lão Ngũ, Tiểu Thúy, Du sĩ at `cell:yen_vu_lau`). | Bootstrap atomic `t3_write_multi` creates: 3 `npc` core rows + 3 `npc_node_binding` rows (deterministic owner via `hash(npc_id) mod live_nodes`) + 3 `actor_binding` rows + 3 `npc_reaction_priority` rows (knowledge_tags pre-populated from canonical_actors decl). First PC into `cell:yen_vu_lau` sees 3 `MemberJoined { join_method: CanonicalSeed }` events for the canonical NPCs. |
| **AC-CST-2 PERSONA ASSEMBLY (Du sĩ reaction prompt)** | NPC_002 Chorus invokes Cast persona-assembly for Du sĩ with `reaction_intent=PhysicalAction`, trigger=PC literacy-slip turn 105. | Deterministic combiner reads 4 inputs (npc + npc_session_memory + npc_pc_relationship_projection + scene_state); produces `PromptSlots { system_voice, scene_context, intent_directive, canon_grounding, forbidden_paraphrase }`. system_voice references Du sĩ's `flexible_state.voice_register=FormalClassical`. Memory fact selection: top-5 by `importance_score + relevance + recency_decay` (deterministic; reproducible). |
| **AC-CST-3 OPINION-WITH-PC LOOKUP** | Chorus calls `NpcOpinion::for_pc(du_si, pc_ly_minh)` at start of priority resolution. | Read returns `OpinionScore` from `npc_pc_relationship_projection` row (lazy-default neutral=0 if no row exists; subsequent updates derived at session-end per §13). Used by Chorus Tier-2 priority. |

### 14.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-CST-4 NODE-BINDING WRONG NODE** | Cluster has nodes A, B; NPC_X owner=A; B-side service attempts a write for NPC_X. | SDK `require_npc_owner_or_route` reads `npc_node_binding` cache, detects owner=A; transparently RPCs to A via gRPC. If A unreachable + retries exhausted, surfaces `WrongChannelWriter`; SDK retries with backoff. |
| **AC-CST-5 PERSONA OVERFLOW** | NPC has 100 facts; combined system_voice + memory + scene + trigger > LLM context window. | Persona assembly truncates: top-3 facts (was top-5) + shortened summary preview (1 KB cap); logs `persona_overflow` warning telemetry; LLM call proceeds with reduced context. NPC-3g catalog item tracks for V1-prototype tuning. |
| **AC-CST-6 NPC HANDOFF EPOCH RACE** | Concurrent failover: nodes A and B both try to claim NPC_X writer role. | First T3 write of `NpcNodeBinding::HandoffStart { new_epoch }` succeeds; second loses on epoch fence (Postgres rejects stale epoch). Loser observes rejection, drops attempt, lets winner proceed. No duplicate commits. |
| **AC-CST-7 ORPHANED CANONICAL NPC** | RealityManifest declares `CanonicalActorDecl` with `glossary_entity_id` that doesn't exist. | Bootstrap rejects with `BootstrapError::OrphanedActor { actor_id, glossary_entity_id }`; reality stays in `Initializing` state; operator alerted; no PC can bind until manifest fixed + re-applied (idempotent re-run). |

### 14.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-CST-8 NPC RESPAWN AFTER NODE FAILOVER** | Owner-node A dies; CP detects (≤30s); reassigns NPC_X to node B with `new_epoch`. | CP delta-stream pushes `NpcNodeBinding` change to all SDKs within ≤35s; subsequent writes route to B; old A's writes (if any in flight) Postgres-rejected by epoch fence. NPC_X's `npc` core + `npc_session_memory` continue from last commit; no data loss. |
| **AC-CST-9 LAZY MEMORY CREATE** | First-ever interaction between PC X and NPC Y in any session. | `npc_session_memory(npc=Y, session=S)` lookup returns None; lazy-create empty memory row; persona-assembly combiner falls back to "no prior knowledge of this PC"; first-encounter NPCs get clean slate. Subsequent interactions populate facts. |
| **AC-CST-10 SESSION-END OPINION DERIVATION** | Session ends (PC `/signoff` or 30-min idle timeout). | World-service iterates each (NPC, PC) pair the session interacted with; computes `trust_delta = sum(fact.importance × valence_sign) over session_facts`; merges with existing `npc_pc_relationship_projection` row; commits via `t2_write` per §13 sequence. Causal_ref to session-end SystemEvent. PC sees opinion shift on next session bind (per §8.3 acceptable staleness). |

**Lock criterion:** all 10 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-acceptance criteria) → `LOCKED` (after tests).

---

## §15 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| CST-D1 | NPC-to-Session model — does an NPC have a "session" concept distinct from PC sessions? | Currently: NO. NPCs are not sessions; they are bound to owner-node + ID. R8's `current_session_id` field is the SDK-visible session the NPC is "participating in" for memory scoping, NOT an SDK session of its own. Future V2+ may revisit if multi-node NPC autonomy demands it. |
| CST-D2 | NPC-Routine category (autonomous behavior with no PC trigger) | DL_001 (V1+30d, EVT-T10 producer) |
| CST-D3 | NPC-Ambient category (no LLM, decorative-only crowds) | V2+; likely requires DP-Ch51 Concurrent turn-slot pattern |
| CST-D4 | Cross-reality NPC migration (NPC moves between realities) | DF12 (withdrawn); won't be implemented unless reinstated |
| CST-D5 | Author UI for editing `Npc.flexible_state` and `npc_reaction_priority.knowledge_tags` | DF4 World Rules (V2) |
| CST-D6 | NPC voice-register customization beyond closed enum (per-NPC LoRA-style fine-tuning) | V3+; needs LLM infrastructure not yet planned |
| CST-D7 | Real-time opinion preview (read-time derivation for high-stakes intra-session scenes) | V2+ optimization (combat, romance scenes) |
| CST-D8 | NPC tool-call allowlist customization per-NPC (e.g., du sĩ can call `quote_classical`; lão ngũ cannot) | NPC-10 catalog item; future PL_NNN_npc_tool_calls |
| CST-D9 | Author-pinning NPCs to specific nodes (override hash-based binding) | V2+ when load-balancing maturity demands |
| CST-D10 | NPC failure injection — what happens if `Npc.core_beliefs` CanonRef is broken (book canon edited mid-reality)? | DF8 canon-fork (V3+) |

---

## §16 Cross-references

- [PL_001 Continuum](../04_play_loop/PL_001_continuum.md) — §3.6 actor_binding (NPC handoff defer resolved here)
- [PL_001b Continuum lifecycle](../04_play_loop/PL_001b_continuum_lifecycle.md) — §16 bootstrap which Cast extends
- [PL_002 Grammar](../04_play_loop/PL_002_command_grammar.md) — tool-call allowlist for actor_type=NPC_Reactive
- [NPC_002 Chorus](NPC_002_chorus.md) — primary consumer; resolves §3 NPC_001 dependency stub + §6 NpcOpinion::for_pc trait
- [02_storage R08](../../02_storage/R08_npc_memory_split.md) — locked aggregate shapes Cast imports unchanged
- [07_event_model/02_invariants.md](../../07_event_model/02_invariants.md) — EVT-A4 producer binding (Cast adds `produce: NPCTurn` claim)
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T2 NPCTurn (this feature's primary emission category)
- [decisions/locked_decisions.md](../../decisions/locked_decisions.md) — no MV12-D resolved here (this is foundation, not lifecycle)
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — Lão Ngũ + Tiểu Thúy + Du sĩ used as concrete worked example

---

## §17 Implementation readiness checklist

- [x] **§2** ActorId closed enum locked (Pc, Npc, Synthetic, Admin)
- [x] **§2.5** EVT-T* mapping (every Cast event maps to existing categories)
- [x] **§3** Aggregate inventory (3 R8-imported with DP-A14 annotations + 2 new owned)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Persona assembly contract (NPC-2 catalog resolution; deterministic combiner spec)
- [x] **§7** Capability JWT claims with `produce: NPCTurn`
- [x] **§8** Pattern choices (deterministic owner hash, no persona cache, session-end opinion derivation, V1 Reactive only)
- [x] **§9** Failure-mode UX (6 failure cases)
- [x] **§10** Cross-service handoff per Chorus reaction
- [x] **§11** Bootstrap sequence (CanonicalActorDecl extension)
- [x] **§12** NPC cross-node handoff (resolves PL_001 §3.6)
- [x] **§13** Opinion update derivation (session-end)
- [x] **§14** Acceptance criteria (10 scenarios across happy-path / failure-path / boundary)
- [x] **§15** Deferrals (CST-D1..D10)

**Unblocks:** NPC_002 Chorus's `NpcOpinion::for_pc` stub becomes real. PL_001 §3.6 NPC handoff defer resolved. EVT-T1 Submitted/NPCTurn producer JWT claim shape locked (post Option C reframe). ActorId variant closed-set locked (Pc deferred to PCS_001 for the PcId newtype itself; PCS brief at `06_pc_systems/00_AGENT_BRIEF.md`).

**Status transition:** DRAFT 2026-04-25 → Option C terminology applied by event-model agent → **CANDIDATE-LOCK 2026-04-26** (closure pass: §14 acceptance criteria added).

LOCK granted after the 10 §14 acceptance scenarios have passing integration tests.

**Next** (when this doc locks): world-service adds Cast persona-assembly module; book-ingestion pipeline (knowledge-service) extends RealityManifest with Cast's CanonicalActorDecl fields; CP gains NPC node-binding registry (Phase 5 ops). Vertical-slice target: SPIKE_01 turn 5 with real (not stub) opinion data feeding NPC_002 Chorus Tier-2 selection.
