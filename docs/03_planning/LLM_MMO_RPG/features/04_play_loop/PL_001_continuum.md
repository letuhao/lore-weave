# PL_001 — Continuum (Place + Time + Reality Foundation)

> **Conversational name:** "Continuum" (CON). The fabric of place + time + reality that all play sits on. PC at any moment is at one cell channel + one fiction-time tuple within one reality — that joint state is "PC's continuum position". Use "Continuum" in conversation; the file ID `PL_001` is the stable referenceable ID.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** CANDIDATE-LOCK 2026-04-25 (extended from DRAFT, then split, then **boundary-review tightened 2026-04-25** — applied O1 thin-RejectReason, B1 envelope-ownership rule, G2 actor-removal hook; see PL_001b §18 for B2/B3 cross-cutting deferrals). Awaiting integration tests for LOCK.
> **Companion file:** [`PL_001b_continuum_lifecycle.md`](PL_001b_continuum_lifecycle.md) — sequences (normal / sleep / travel / reconnect / rejection), bootstrap, acceptance criteria, deferrals, readiness.
> **Boundary contract:** TurnEvent envelope owned by Continuum per [`_boundaries/02_extension_contracts.md` §1](../../_boundaries/02_extension_contracts.md). Features extend additively per foundation I14.
> **Catalog refs:** PL-1 (session lifecycle), PL-3 (turn submission), PL-7 (event emission). Foundation layer beneath all PL-2..PL-25.
> **Validates:** [MV12-D1..D7](../../decisions/locked_decisions.md) (page-turn fiction-time)
> **Grounded in:** [SPIKE_01](../_spikes/SPIKE_01_two_sessions_reality_time.md) (Yên Vũ Lâu, 17 turns across 2 sessions, /sleep + /travel validated)
> **Builds on:** DP-A1..A19 axioms, DP-T0..T3 tiers, DP-R1..R8 rulebook, DP-K1..K12 SDK, channel hierarchy DP-Ch1..Ch53

---

## §1 User story (concrete)

A reality is born from a book (Thần Điêu Đại Hiệp). The reality has ONE linear timeline ([MV12-D2](../../decisions/locked_decisions.md)) starting at year 1256, mùa thu, ngày 3, giờ Thân sơ. PC `Lý Minh` (xuyên không, body=Hàng Châu peasant, soul=2026 student) sits in cell channel `cell:yen_vu_lau:T1`, child of tavern channel `tavern:yen_vu_lau:gia_hung`, child of town `town:gia_hung`, child of country `country:southern_song`, child of root.

PC submits 17 turns over 2 sessions. Each turn advances `turn_number` by 1 in the cell, advances reality fiction time by `fiction_duration` (the LLM-proposed duration validated by world-rule), emits a channel event tagged with `turn_number`, and updates scene presence. Turn 11 is `/sleep until dawn` (8h fast-forward, day boundary crossed). Turn 16 is `/travel to Tương Dương` (23 fiction-days, scene change to a new cell channel under different town).

**This feature design specifies:** what aggregates exist, where they live (tier+scope), which DP primitives the feature calls, what JWT claims are required, the turn-slot pattern, the redaction policy, the cross-service handoff with CausalityToken, and the failure-mode UX. After this lock, `world-service` (Rust) and `roleplay-service` (Python) can be implemented against this contract without further discussion.

---

## §2 Domain concepts

| Concept | Maps to DP | Notes |
|---|---|---|
| **Reality** | `RealityId` newtype (DP-K1) | One book → one reality at V1. `1256_thien_long_v1`. |
| **Place** | A node in the channel tree (DP-A13). | level_name ∈ `{ "reality_root", "continent", "country", "district", "town", "tavern", "cell" }`. Free-form per book. |
| **Cell** | The leaf channel where a player session is currently bound. | `SessionContext.current_channel_id` always points to a cell. PC moves between cells via `move_session_to_channel`. |
| **FictionTime** | A `(book_year, season, day, sub_day_phase)` tuple stored in a RealityScoped T2 aggregate `fiction_clock`. | Advances ONLY when `advance_turn` is called on a cell channel. No wall-clock derivation. |
| **Turn** | One `advance_turn` invocation on a cell channel (DP-A17). | Per-channel `turn_number: u64` monotonic gapless. Tagged on every cell event. |
| **Scene** | Active state of a cell channel — who's here, what's the ambient situation. ChannelScoped T2 aggregate `scene_state`. | A scene starts at cell creation, ends at cell dissolution or channel pause. |
| **Participant** | An `ActorId` (PC or NPC) currently in a cell's `MemberJoined` set (DP-A18). | DP emits canonical `MemberJoined`/`MemberLeft` events; feature reads them via durable subscribe. |
| **TurnEnvelope** | The `turn_data: serde_json::Value` payload of one `advance_turn` call. | Carries `{ actor, intent, fiction_duration_proposed, narrator_text, command_kind, command_args }`. Channel event log is the SSOT. |

DP is agnostic to `level_name` semantics (DP-A13 §c). This feature defines them for the Thần Điêu reality. Other realities (other books) declare their own.

---

## §3 Aggregate inventory

Six aggregates, all with explicit tier + scope per DP-A14 + DP-A9.

### 3.1 `fiction_clock`

```rust
#[derive(Aggregate)]
#[dp(type_name = "fiction_clock", tier = "T2", scope = "reality")]
pub struct FictionClock {
    pub reality_id: RealityId,                    // (also from key)
    #[dp(indexed)] pub current_year: i32,         // 1256
    #[dp(indexed)] pub current_season: Season,    // enum: Xuân, Hạ, Thu, Đông
    #[dp(indexed)] pub current_day_of_season: u32,
    pub current_sub_day: SubDayPhase,             // enum: Tý, Sửu, ..., Hợi (12 chi) + sub-phase {sơ, chính, mạt}
    pub last_turn_event_id: u64,                  // channel_event_id that last advanced this clock
    pub last_advanced_at: Timestamp,              // wall-clock — debugging only, NOT consumed by gameplay
}
```

- One row per reality. Singleton — `FictionClock::Id = ()`-equivalent (use `reality_id` as id, or a fixed `FictionClockId::SINGLETON`).
- `Delta = FictionClockAdvance { fiction_duration: FictionDuration }` where `FictionDuration` is a typed sum of `(years, seasons, days, sub_day_phases)`.
- T2: durability mandatory (canon time advancement is permanent), but ≤1s projection lag is fine because turns don't fire faster than humans type.
- Reality-scoped: no channel context — fiction time is global to a reality.

### 3.2 `scene_state`

```rust
#[derive(Aggregate)]
#[dp(type_name = "scene_state", tier = "T2", scope = "channel")]
pub struct SceneState {
    pub channel_id: ChannelId,                    // cell channel — the scene IS the cell
    pub started_at_turn: u64,
    pub ended_at_turn: Option<u64>,
    #[dp(indexed)] pub primary_actor: ActorId,    // PC who anchors the scene; for NPC-only scenes, the NPC owner-node
    pub ambient: AmbientState,                    // weather, mood-lighting, background NPCs (non-participants)
    pub canon_anchor: Option<CanonAnchorId>,      // optional: ref to a book passage that grounded this scene
}

pub struct AmbientState {
    pub weather: String,                          // "drizzle", "clear", ... (free-form, world-service interprets)
    pub time_of_day_qualifier: String,            // "dusk", "midnight", "dawn" — derived from FictionClock + lat/long
    pub crowd_density: u8,                        // 0..255 hint for LLM ambient generation
    pub notable_props: Vec<PropRef>,              // tea pot, jian, scroll on table, ...
}
```

- One row per cell channel. Identified by `(channel_id,)`.
- Created at `create_channel` (cell-level) by world-service; updated by ambient changes; ended at cell dissolution.
- T2 because re-loading a session must show the same scene; ChannelScoped because it lives in one cell.

### 3.3 `participant_presence` (live)

```rust
#[derive(Aggregate)]
#[dp(type_name = "participant_presence", tier = "T1", scope = "channel")]
pub struct ParticipantPresence {
    pub channel_id: ChannelId,                    // cell
    pub actor: ActorId,
    pub state: PresenceState,                     // see foundation 05_vocabulary.md PresenceState 6-state enum
    pub idle_since_turn: Option<u64>,
}
```

- T1 + ChannelScoped: live "who's here right now" view, ≤30s loss tolerable per DP-T1 (re-derived from the durable T2 MemberJoined/Left log on miss).
- One row per `(channel_id, actor)` pair.
- Snapshot interval: default 10s (DP-T1 default). Acceptable because cell cardinality is small (typically 2–5 actors).

**Rebuild algorithm (after T1 loss / writer-node failover):**

```text
seed_set = {}
stream = subscribe_channel_events_durable::<MembershipEvent>(ctx, cell, from_event_id=0)
WHILE stream.next() returns within bounded-catchup-window:
  evt = stream.next()
  MATCH evt:
    MemberJoined { actor, .. } → seed_set.insert(actor, PresenceState::Active, idle_since=evt.turn_number)
    MemberLeft   { actor, .. } → seed_set.remove(actor)
write seed_set as bulk T1 via t1_write_batch (one call per actor)
```

Bounded-catchup-window for a cell ≤ 1 second wall-clock at typical cell cardinality (≤500 cumulative join/leave events over a cell's lifetime). For long-lived cells exceeding that, world-service maintains a daily T2 snapshot of the seed_set and rebuilds from latest snapshot + tail catchup.

### 3.4 Canonical membership events (DP-emitted, NOT a feature aggregate)

`MemberJoined` / `MemberLeft` channel events are emitted by DP itself per DP-A18 §c when:

- A session moves into a cell via `move_session_to_channel` → DP emits `MemberJoined { actor, join_method: Move }` on the cell.
- A session moves away or disconnects → DP emits `MemberLeft { actor, leave_reason: Move | Disconnect | Migration }`.
- An NPC enters/leaves via a feature-level write that itself triggers an explicit DP membership op — see §3.6.

**Feature reads them via durable subscribe** (DP-K6 `subscribe_channel_events_durable`) to (a) drive the live `participant_presence` T1 view, (b) recover that view after node failover, (c) feed bubble-up aggregators at tavern/town levels.

### 3.5 `turn_envelope` — NOT an aggregate (Continuum-owned envelope schema)

The turn payload IS a channel event. There is no separate aggregate. SSOT = channel event log entry tagged with `turn_number`. Read via `subscribe_channel_events_durable` or `query_scoped_channel<TurnEvent>`.

**Envelope ownership:** Continuum owns the `TurnEvent` struct ENVELOPE; other features extend it ADDITIVELY per foundation I14. See [`_boundaries/02_extension_contracts.md` §1](../../_boundaries/02_extension_contracts.md) for the contract that governs how features add fields. Schema version `TurnEventSchema = 1` (2026-04-25); bump on additive extensions.

```rust
// TurnEventSchema = 1 (Continuum-owned envelope; features add fields per
// _boundaries/02_extension_contracts.md §1).
pub struct TurnEvent {
    // ─── Continuum-owned core (MUST exist) ───
    pub actor: ActorId,
    pub intent: TurnIntent,                       // closed enum below; Continuum-owned
    pub fiction_duration_proposed: FictionDuration,
    pub narrator_text: Option<String>,            // LLM-generated narration (post-validation; None on Rejected)
    pub canon_drift_flags: Vec<DriftFlag>,        // populated by 05_llm_safety A6 validator
    pub outcome: TurnOutcome,                     // closed enum below; Continuum-owned
    pub idempotency_key: Uuid,                    // client-issued at submit; server caches 60s — see §14
    pub causal_refs: Vec<CausalRef>,              // EVT-A6 typed causal-refs

    // ─── Feature-extended (additive per I14) ───
    pub command_kind: Option<CommandKind>,        // PL_002 Grammar owns CommandKind enum closed set
    pub command_args: Option<serde_json::Value>,  // PL_002 owns per-command schemas
    pub reaction_intent: Option<ReactionIntent>,  // NPC_002 Chorus owns ReactionIntent enum
    pub aside_target: Option<ActorId>,            // NPC_002
    pub action_kind: Option<ActionKind>,          // NPC_002 owns ActionKind + GestureKind closed sets
    // future feature fields per the extension contract
}

pub enum TurnIntent {                             // Continuum-owned closed set
    Speak,
    Action,
    MetaCommand,
    FastForward,
    Narration,
}

pub enum TurnOutcome {                            // Continuum-owned closed set
    Accepted,                                     // turn_number was advanced; fiction_clock advanced (if intent demanded)
    Rejected { reason: RejectReason },            // turn_number NOT advanced; fiction_clock NOT advanced (MV12-D11)
}

pub struct RejectReason {                         // Continuum-owned envelope shape;
                                                  // rule_id namespaces are feature-owned
    pub rule_id: String,                          // namespaced; see below
    pub detail: serde_json::Value,                // feature-defined per rule_id namespace
}
```

**RejectReason `rule_id` namespace ownership** (per [`_boundaries/02_extension_contracts.md` §1.4](../../_boundaries/02_extension_contracts.md)):
- `lex.*` → WA_001 Lex
- `heresy.*` → WA_002 Heresy
- `mortality.*` → WA_006 Mortality (provisional)
- `world_rule.*` → cross-cutting (any feature may use)
- `oracle.*` → 05_llm_safety A3
- `canon_drift.*` → 05_llm_safety A6
- `capability.*` → DP-K9 / 05_llm_safety
- `parse.*` → PL_002 Grammar
- `chorus.*` → NPC_002 Chorus
- `forge.*` / `charter.*` / `succession.*` → WA_003 / PLT_001 (formerly WA_004) / PLT_002 (formerly WA_005)

Continuum DOES NOT enumerate every variant. Each feature's design doc owns its prefix's rule_ids and the corresponding Vietnamese reject copy.

**Why `outcome` is on the event (not absence-of-event):** rejected turns DO get committed as channel events for audit — operator can debug "why is PC bouncing?" with `query_scoped_channel<TurnEvent>(... predicate=field_eq(outcome, Rejected))`. But because they tag with the *previous* `turn_number` (no advance per DP-A17 §c — `advance_turn` only increments on Accepted), rejected events sit at `turn_number = N` alongside the previous Accepted turn `N` — distinguishable by `outcome`.

**Why `idempotency_key`:** prevents duplicate-turn commits when client retries after disconnect (§14). Server-side cache at gateway: `(session_id, idempotency_key) → response` for 60 seconds; second submit with same key returns the cached response without re-running the LLM/validator chain.

### 3.6 `entity_binding` (transferred to EF_001 2026-04-26)

> **OWNERSHIP TRANSFERRED:** `entity_binding` was originally owned by PL_001 (PC + NPC only). Transferred to **[EF_001 Entity Foundation](../00_entity/EF_001_entity_foundation.md)** 2026-04-26 and renamed `entity_binding` with extended scope: 4 EntityType variants (Pc/Npc/Item/EnvObject) + 4-state `LocationKind` (InCell/HeldBy/InContainer/Embedded) + 4-state `LifecycleState` (Existing/Suspended/Destroyed/Removed). See [EF_001 §3.1](../00_entity/EF_001_entity_foundation.md#31-entity_binding-t2--reality--primary) for the V1+ struct definition. PL_001 retains operational responsibility for PC turn-time movement (the writer flow); EF_001 owns the aggregate + lifecycle + cross-entity addressability.

V1 PC+NPC subset shape (full struct in EF_001):

```rust
// see EF_001 §3.1 for full V1+ struct (4-state LocationKind + LifecycleState + affordance_overrides)
#[derive(Aggregate)]
#[dp(type_name = "entity_binding", tier = "T2", scope = "reality")]
pub struct EntityBinding {
    #[dp(indexed)] pub entity_id: EntityId,       // V1: Pc | Npc; V1+: Item | EnvObject (per EF_001)
    pub entity_type: EntityType,
    pub location: EntityLocation,                 // InCell { cell_id } V1 default for PC/NPC
    pub owner_node: NodeId,
    pub lifecycle_state: LifecycleState,
    pub last_moved_fiction_time: FictionTime,
    pub last_lifecycle_change_fiction_time: FictionTime,
    pub affordance_overrides: Option<AffordanceSet>,
}
```

- T2 + RealityScoped: every entity in a reality has exactly one current location at any time. Querying "where is Tiểu Thúy?" = `read_projection_reality<EntityBinding>(ctx, EntityId::Npc(npc_id))`.
- Updated whenever `move_entity_to_cell` is invoked (which is itself a feature method that wraps `move_session_to_channel` for PCs and an internal NPC handoff for NPCs).
- Required because cells can host entities who don't have an SDK session (NPCs without active LLM interaction; Items dropped in cell). Channel `MemberJoined`/`MemberLeft` covers session-bound presence; `entity_binding` covers everyone else.

**NPC handoff — explicitly DEFERRED to NPC_001:** when an NPC physically moves between cells whose writer nodes differ (e.g., NPC walks from tavern T1 to tavern T2 in another district owned by node B), the handoff protocol — old-node releases, new-node binds, intermediate state during transit — is NOT designed in PL_001. PL_001 only locks the read-side contract: `entity_binding` is the SSOT for "where is X". The write side for cross-node NPC moves is NPC_001's responsibility. V1 mitigation: NPCs are statically bound to a single cell at reality-bootstrap and do not migrate; only PC `/travel` triggers cross-cell moves, and PCs are session-sticky to their own node (DP-A11) which simplifies the protocol to a single `move_session_to_channel` call.

**Entity removal hook (resolves boundary-review G2; superseded by EF_001 lifecycle 2026-04-26):** when an entity is REMOVED from the reality (PC enters Permadeath state per WA_006 Mortality, account deleted, NPC dissolved), `entity_binding(entity_id)` MUST transition to `LifecycleState::Destroyed` or `LifecycleState::Removed` per EF_001 §6. The transition itself is PCS_001 / NPC_001 / WA_002 territory (per-entity lifecycle owners); PL_001 provides only the cleanup HOOK contract:

```rust
// PCS_001 / NPC_001 / WA_002 calls this when an entity is permanently removed
// EF_001 §6 forbids hard delete: lifecycle_state transitions to Destroyed (in-fiction) or Removed (out-of-fiction)
pub async fn transition_entity_lifecycle(
    ctx: &SessionContext,
    entity_id: EntityId,
    new_state: LifecycleState,    // Destroyed | Removed
    reason_kind: LifecycleReasonKind,
) -> Result<(), DpError>;
// world-service updates the entity_binding row + appends to entity_lifecycle_log + emits
// MemberLeft event on the entity's current cell (for audit + bubble-up)
```

V1 implementation: NO hard delete (audit trail preserved in `entity_lifecycle_log` per EF_001 §3.2). The `entity_binding` row stays with `lifecycle_state = Destroyed | Removed`; `location` is FROZEN at last value for forensic value.

### 3.7 Hard limits (V1)

Locked to keep the design analyzable. Any value crossed at runtime → `WorldRuleViolation` reject; not a panic.

| Limit | Value | Why | Enforcement point |
|---|---|---|---|
| Max channel tree depth | 16 | Per DP-Ch1 invariant. | DP — `create_channel` rejects deeper trees. |
| Max actors per cell | 32 | Cell is a "scene"; >32 actors degrades narrative coherence and LLM context-window usability. Tavern-or-bigger channels host crowds via bubble-up summaries, not full presence. | world-service before `move_entity_to_cell`; rejects with `RejectReason::WorldRuleViolation { rule_id: "cell_capacity" }`. |
| Max active turn-slots per writer node | 64 | Memory bound on outstanding LLM streams. Exceeded → new claims get `RateLimited`. | DP-A11 writer node. |
| Max `fiction_duration` per single turn | 30 days fiction-time | Prevents accidental "/sleep for 1000 years" wedging the world. `/travel` caps at 30 days; longer journeys split across multiple turns or use a dedicated `/long_journey` command (V2). | world-service validator. |
| Max idempotency-key TTL | 60 seconds wall-clock | §14 reconnect window. Beyond TTL, retry is treated as a new turn. | gateway in-memory cache. |
| Max `narrator_text` size | 8 KB | LLM output filter; bigger outputs are rejected as `WorldRuleViolation { rule_id: "narrator_size" }` before commit. | output-filter (PL-20). |
| Max ambient `notable_props` per scene | 16 | Scene complexity ceiling for LLM context. | world-service on `t2_write::<SceneState>`. |

These are V1 caps. Tuning happens in Phase 5 ops — but any change is a design event, not a config flip (per DP-A9 spirit: tier and limits are design-time choices).

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq (per active session) | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `fiction_clock` | T2 | T2 | Reality | ~1 per turn (UI clock) | ~1 per turn | Canon time advancement; ≤1s projection lag fine; reality-global. |
| `scene_state` | T2 | T2 | Channel (cell) | ~1 at session bind + on ambient change | ~0.1/turn | Re-load must show same scene; per-cell. |
| `participant_presence` | T1 | T1 | Channel (cell) | high (every render frame in UI) | ~1 on enter/leave/idle | Live "who's here"; 30s loss OK because re-derivable from `MemberJoined` log. |
| Canonical `MemberJoined`/`MemberLeft` | n/a (subscribe) | DP-internal | Channel | streamed | DP-emitted only (DP-A18 §c) | Audit-grade canonical, gap-free durable subscribe. |
| `TurnEvent` (channel event) | n/a (event log) | T2 (via `advance_turn`) | Channel (cell) | streamed | 1 per turn | Per DP-A17 every channel event is tagged with `turn_number`; SSOT is event log. |
| `entity_binding` | T2 | T2 | Reality | ~1 per turn for resolved participants | ~1 per move | Reality-global query "where is X". |

No T0, no T3. Justification:
- **No T0:** PC turns persist across sessions (T2 minimum — DP-T0 eligibility rule fails clause 3 "lifetime bounded by single session").
- **No T3:** No money / no item trade / no canon-promotion in this feature. Canon promotion is DF8 (separate feature). Currency is PCS-* (separate feature). PL_001 deals only with where + when, both of which tolerate ≤1s eventual consistency.

---

## §5 DP primitives this feature calls

By name, with arity. No raw `sqlx` / `redis` (DP-R3).

### 5.1 Reads

- `dp::read_projection_reality::<FictionClock>(ctx, FictionClockId::SINGLETON, wait_for=None, ...)` — every turn-render in UI.
- `dp::read_projection_channel::<SceneState>(ctx, &cell, scene_state_id, wait_for=None, ...)` — at session bind + after each turn for ambient updates.
- `dp::read_projection_reality::<EntityBinding>(ctx, entity_id, wait_for=Some(turn_token), ...)` — when world-service resolves "is NPC X in this cell?" right after a movement turn. **CausalityToken use case.**
- `dp::query_scoped_channel::<ParticipantPresence>(ctx, &cell, Predicate::field_eq(state, Active), limit=8)` — UI list of who's-here.

### 5.2 Writes

- `dp::advance_turn(ctx, &cell, turn_data, causal_refs)` — once per submitted turn. Returns `TurnAck { channel_event_id, turn_number, applied_at }` + a `CausalityToken` (via the underlying T2 commit).
- `dp::t2_write::<FictionClock>(ctx, FictionClockId::SINGLETON, FictionClockAdvance { fiction_duration })` — same RPC handler, after `advance_turn` succeeds, advances the fiction clock by the proposed duration.
- `dp::t2_write::<SceneState>(ctx, scene_id, SceneStateDelta::AmbientUpdate { ambient })` — when ambient changes (weather, crowd).
- `dp::t1_write::<ParticipantPresence>(ctx, presence_id, PresenceDelta::Transition { from, to })` — on enter/leave/idle, in response to `MemberJoined`/`MemberLeft` durable events.
- `dp::t2_write::<EntityBinding>(ctx, entity_id, EntityBindingDelta::MoveTo { new_cell, turn })` — on PC `/travel` or NPC handoff.

### 5.3 Channel ops

- `dp::DpClient::create_channel(ctx, parent=town_id, level_name="cell", metadata)` — when a PC `/travel`s to a place that has no existing cell, world-service creates one. Metadata includes `place_canon_ref` and `created_for_actor`.
- `dp::DpClient::move_session_to_channel(ctx, target=new_cell)` — when PC physically relocates. Returns a new `SessionContext`.
- `dp::DpClient::dissolve_channel(ctx, old_cell)` — V1 deferred: cells go `Dormant` automatically (DP-Ch32). Explicit dissolution is admin-only.

### 5.4 Subscriptions

- `dp::subscribe_channel_events_durable::<TurnEvent>(ctx, &cell, from_event_id=resume_token)` — UI consumes turn events for rendering.
- `dp::subscribe_channel_events_durable::<MembershipEvent>(ctx, &cell, ...)` — world-service consumes to maintain `participant_presence` T1.
- `dp::subscribe_session_channels::<ChannelEvent>(ctx, from_tokens=...)` — UI multiplex: cell + ancestor chain (so player sees tavern-level rumors bubbling up).

### 5.5 Capability + lifecycle

- `dp::DpClient::bind_session(reality, session_id)` — at gateway-handoff.
- `dp::DpClient::refresh_capability(ctx)` — background task, 60s before JWT expiry.
- `dp::DpClient::claim_turn_slot(ctx, &cell, actor=pc_id, expected_duration=30s, reason="player_turn")` — see §8.1 for pattern.

---

## §6 Capability requirements (JWT claims)

Each session's JWT (DP-K9) must declare the following capabilities for this feature to function. CP issues per session at bind.

| Claim | Granted to | Why |
|---|---|---|
| `read: fiction_clock @ T2` | every PC session | UI clock display + Oracle ground-truth. |
| `read: scene_state @ T2 @ cell-channel` | every PC session | ambient render. |
| `read: entity_binding @ T2` | every PC session | "who is in this cell" resolution. |
| `read: participant_presence @ T1 @ cell-channel` | every PC session | live presence list. |
| `subscribe: channel_events @ cell + ancestor_chain` | every PC session | turn render + bubble-up. |
| `write: fiction_clock @ T2` | world-service backend session ONLY (NOT PC sessions) | Per DP-A6: PCs propose via Python LLM bus → Rust validates → Rust writes. |
| `write: scene_state @ T2 @ cell-channel` | world-service backend ONLY | same. |
| `write: entity_binding @ T2` | world-service backend ONLY | same. |
| `write: participant_presence @ T1 @ cell-channel` | world-service backend ONLY (driven by MemberJoined/Left subscribe) | same. |
| `can_advance_turn @ level=cell` | world-service backend ONLY | `advance_turn` is capability-gated per DP-A17 §d. PC sessions never call it directly. |
| `can_register_aggregator @ level=tavern,town` | world-service backend ONLY (one registration per parent at startup) | bubble-up gossip aggregators (deferred to PL_002). |

**Non-capability of PC sessions:** PC sessions cannot call `advance_turn`. They submit a turn intent through the gateway, which forwards to roleplay-service (Python LLM) → emits proposal event → world-service (Rust) consumes, validates, calls `advance_turn` on PC's behalf. This is the DP-A6 + DP-R7 flow made concrete.

---

## §7 Subscribe pattern

### 7.1 UI client (per active session)

```text
ON session_bind:
  multiplex_stream = dp::subscribe_session_channels::<ChannelEvent>(
    ctx,
    from_tokens = { cell_id: last_seen_event_id_for_cell,
                    tavern_id: last_seen_event_id_for_tavern,
                    town_id: last_seen_event_id_for_town,
                    ... up the ancestor chain ... }
  )

WHILE session_active:
  event = multiplex_stream.next()
  RENDER event.kind:
    TurnEvent      → render-narrator-text + advance-UI-clock
    MemberJoined   → presence-list.add(actor)
    MemberLeft     → presence-list.remove(actor)
    ChannelPaused  → render-pause-overlay
    BubbleUpEvent  → render-rumor-toast (filtered by ancestor depth)
```

Resume tokens persisted client-side (per CLAUDE.md "preferences synced server-side") so reconnect picks up missed events; gap-free per DP-A15.

### 7.2 world-service backend (per cell it manages)

```text
ON channel-writer-bind for cell:
  member_stream = dp::subscribe_channel_events_durable::<MembershipEvent>(ctx, cell, from=current_eventid)
  WHILE writer:
    evt = member_stream.next()
    MATCH evt:
      MemberJoined { actor, join_method } →
        dp::t1_write::<ParticipantPresence>(ctx, presence_id(cell, actor),
                                             PresenceDelta::Enter { join_method })
      MemberLeft { actor, leave_reason } →
        dp::t1_write::<ParticipantPresence>(ctx, presence_id(cell, actor),
                                             PresenceDelta::Leave { leave_reason })
```

Single-writer (DP-A16) means world-service only runs this on the node that owns the cell channel. Failover replays from `from=last_committed`.

---

## §8 Pattern choices

### 8.1 Turn-slot pattern: **Strict**

Per [21_llm_turn_slot.md](../../06_data_plane/21_llm_turn_slot.md) DP-Ch51 patterns: **Strict** = one actor at a time per cell during a turn; concurrent claim rejected with `TurnSlotHeldBy`.

- Claim before LLM call: `dp::claim_turn_slot(ctx, &cell, actor=pc_id, expected_duration=30s, reason="player_turn")`.
- Release on commit: `dp::release_turn_slot(ctx, &cell)` (or auto-expire at `expected_until`).
- Why Strict: Vietnamese / Chinese teahouse turn-based interaction model (validated in SPIKE_01) — PC speaks, then NPC reacts; never simultaneous. NPCs in the same cell react in deterministic order driven by world-rule, not concurrency.

V2+ may introduce **Concurrent** for cells representing crowds (e.g., 50-NPC market square) — out of scope here.

### 8.2 Redaction policy for bubble-up: **Transparent**

Per [19_privacy_redaction_policies.md](../../06_data_plane/19_privacy_redaction_policies.md) DP-Ch43.

- V1 cells are all "public observable" (anyone in the parent tavern channel could plausibly overhear). No private cells in the SPIKE_01 narrative.
- When PC + NPC step into a private bedroom (V2+), that cell is created with `metadata.visibility = "private"` and any aggregator at tavern level uses `RedactionPolicy::SkipPrivate`.
- V1 aggregators (deferred to PL_002 gossip-feature) register with `Transparent` for now.

### 8.3 Causality wait timeout: **default 5s** for cross-service reads, **20s** for `/travel` chains

- Standard turn read-after-write: 5s default (DP-A19) is fine — projection-applier p99 is ≤1s.
- `/travel` is a multi-step chain (advance_turn → fiction_clock advance → entity_binding move → create_channel → move_session_to_channel → MemberJoined emit). UI's first read after the chain may need to wait longer; UI passes `causality_timeout=Some(Duration::from_secs(20))` on the first `read_projection_reality<EntityBinding>` after a travel.
- Beyond 20s → `CausalityWaitTimeout` → UI surfaces "đường đi gặp trở ngại, thử lại?" with a retry button. Never silently render stale.

---

## §9 Failure-mode UX

| DpError variant | When | UX |
|---|---|---|
| `RateLimited { tier: T2, retry_after }` | Outbox saturated under burst (multi-PC simultaneous /travel) | Toast: "Cảnh giới hơi mệt mỏi, đợi {retry_after.as_secs()}s rồi thử lại". DO NOT auto-retry per DP-R6. |
| `CircuitOpen { service }` | CP unreachable, breaker open | Banner: "Hệ thống thực tại tạm thời ngắt kết nối — phiên hiện tại đang giữ nguyên". UI freezes input but shows last-rendered scene. Reconnect via session refresh. |
| `WrongChannelWriter` | Writer node crashed, route cache stale, retry exhausted | Internal — SDK retries. Surfaces as 1-2s extra latency. UI shows turn-pending spinner. |
| `ChannelPaused { reason, paused_until }` | Admin paused this cell (drain, debug, content review) | Modal: "Cảnh đang tạm dừng vì {reason}. Sẽ tiếp tục lúc {paused_until}". Input disabled. |
| `ChannelDissolved` | Old cell after PC has moved away ≥48h, attempt to /goback | Modal: "Cảnh đó đã trôi vào quá khứ, không thể quay lại." (V1 — V2 may allow recall via DF8 canon-fork.) |
| `CausalityWaitTimeout` | Projection-applier lag on /travel chain | Toast: "Cảnh mới đang được dệt, thử nhập lệnh sau giây lát." 1 free retry without re-confirming. |
| `CapabilityExpired` | JWT not refreshed in time | Background SDK refresh kicks in; if also fails: gateway re-auth flow. |

No silent failures. No swallow-and-retry (DP-R6). Every error has user-facing copy.

---

## §10 Cross-service handoff (CausalityToken flow)

Concrete example: PC submits `/travel to Tương Dương` (SPIKE_01 turn 16-17). 4 services participate. CausalityToken (DP-A19) glues read-your-writes across them.

```text
1. UI (browser) → gateway:
     POST /v1/turn { session_id, turn_text: "/travel to Tương Dương" }

2. gateway → roleplay-service (Python LLM):
     classify intent (PL-15): MetaCommand → Travel
     extract args: { destination: "tương_dương", days_estimate: ~23 }
     emit proposal event to LLM bus → out of DP scope per DP-A6

3. world-service (Rust, consuming bus):
     validate: destination is canon (Tương Dương 1256-thu under siege by Mongols, plausible) ✓
     resolve days: ~23 (canon distance from Gia Hưng) ✓
     call dp.claim_turn_slot(ctx, &current_cell, actor=pc_id, expected_duration=15s, reason="travel_chain")

  3a. dp.advance_turn(ctx, &current_cell, turn_data=TurnEvent::FastForward {
        actor: pc_id, fiction_duration: 23 days, command_kind: Travel,
        command_args: { destination: "tương_dương" }
      }, causal_refs=[])  →  TurnAck { causality_token = T1 }

  3b. dp.t2_write::<FictionClock>(ctx, SINGLETON,
        FictionClockAdvance { fiction_duration: 23 days })  →  T2Ack { causality_token = T2 }

  3c. existing_cell = dp.query_scoped_reality::<ChannelMetadata>(... level=cell, place_canon_ref="tương_dương_west_gate")
        .first()
      OR  new_cell = dp.create_channel(ctx, parent=town_tương_dương,
                                        level_name="cell",
                                        metadata={ place_canon_ref: "tương_dương_west_gate", ... })
                                                    →  ChannelId(new_cell)

  3d. new_ctx = dp.move_session_to_channel(ctx, new_cell)  →  SessionContext'
       (DP emits MemberLeft on old_cell + MemberJoined on new_cell automatically per DP-A18 §c)

  3e. dp.t2_write::<EntityBinding>(new_ctx, pc_id,
        EntityBindingDelta::MoveTo { new_cell, turn: T1.turn_number })  →  T2Ack { causality_token = T3 }

  3f. dp.release_turn_slot(new_ctx, &new_cell)

  3g. respond to gateway: { ok: true, causality_token: T3, new_session_ctx: SessionContext' }

4. gateway → UI:
     200 OK { causality_token: T3, new_cell: <id>, new_fiction_time: 1256-thu-day26 }

5. UI on receiving 200:
     re-bind multiplex stream against new_cell
     read_projection_reality::<FictionClock>(ctx, SINGLETON,
                                              wait_for=Some(T3), causality_timeout=Some(20s))
     read_projection_channel::<SceneState>(ctx, &new_cell, scene_id,
                                            wait_for=Some(T3), causality_timeout=Some(20s))
     render new scene
```

**Token chain:** T1 (advance_turn ack) → T2 (clock ack) → T3 (entity_binding ack). Step 5 passes T3 — the latest in the chain — to `wait_for`. DP guarantees that any read with `wait_for=T3` reflects T1, T2, T3 because they were committed in sequence within the same writer's session and `last_applied_event_id` is monotonic per channel + monotonic per reality outbox.

V1 can simplify by passing T2 to UI (since T3 is reality-scoped and T2 is also reality-scoped after the cell exists); but the safest contract is "always pass the last token in the chain". Locked: world-service returns the LAST `causality_token` from the chain.

---

## §11..§20 — Continued in PL_001b

End of contract layer. The dynamic layer (sequences, bootstrap, acceptance criteria) is in the companion file:

→ **[`PL_001b_continuum_lifecycle.md`](PL_001b_continuum_lifecycle.md)**

Sections:

- §11 Sequence: normal turn
- §12 Sequence: /sleep (fast-forward across day boundary)
- §13 Sequence: /travel (5-op chain, ASCII flow, edge cases)
- §14 Reconnect/resume + idempotency (UUID key, 60s gateway cache + world-service `turn_idempotency_log`)
- §15 Rejection path (Q1=option-b: `TurnEvent { outcome: Rejected }` committed via plain `t2_write`, NOT `advance_turn`; `turn_number` stays at N, MV12-D11 honored)
- §16 Bootstrap (Q2=hybrid: book manifest declares root tree + fiction_clock; cells lazy-create)
- §17 Acceptance criteria (16 scenarios — AC-1..AC-16)
- §18 Open questions deferred + landing point
- §19 Cross-references
- §20 Implementation readiness checklist (combined PL_001 + PL_001b)

PL_001b is required reading before implementing world-service handlers.
