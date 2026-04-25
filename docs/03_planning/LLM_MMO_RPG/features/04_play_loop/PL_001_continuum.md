# PL_001 — Continuum (Place + Time + Reality Foundation)

> **Conversational name:** "Continuum" (CON). The fabric of place + time + reality that all play sits on. PC at any moment is at one cell channel + one fiction-time tuple within one reality — that joint state is "PC's continuum position". Use "Continuum" in conversation; the file ID `PL_001` is the stable referenceable ID.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** DRAFT 2026-04-25 (first implementation-ready feature design after kernel-design-CLOSED at SR12 + DP Phase 4 LOCK)
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

### 3.4 Canonical membership events (DP-emitted, NOT a feature aggregate)

`MemberJoined` / `MemberLeft` channel events are emitted by DP itself per DP-A18 §c when:

- A session moves into a cell via `move_session_to_channel` → DP emits `MemberJoined { actor, join_method: Move }` on the cell.
- A session moves away or disconnects → DP emits `MemberLeft { actor, leave_reason: Move | Disconnect | Migration }`.
- An NPC enters/leaves via a feature-level write that itself triggers an explicit DP membership op — see §3.6.

**Feature reads them via durable subscribe** (DP-K6 `subscribe_channel_events_durable`) to (a) drive the live `participant_presence` T1 view, (b) recover that view after node failover, (c) feed bubble-up aggregators at tavern/town levels.

### 3.5 `turn_envelope` — NOT an aggregate

The turn payload IS a channel event. There is no separate aggregate. SSOT = channel event log entry tagged with `turn_number`. Read via `subscribe_channel_events_durable` or `query_scoped_channel<TurnEvent>`.

```rust
// Event shape (committed via dp.advance_turn(turn_data=...))
pub struct TurnEvent {
    pub actor: ActorId,
    pub intent: TurnIntent,                       // Speak | Action | MetaCommand | FastForward
    pub fiction_duration_proposed: FictionDuration,
    pub narrator_text: Option<String>,            // LLM-generated narration (post-validation)
    pub command_kind: Option<CommandKind>,        // None for free narrative; Some(Sleep|Travel|Verbatim|...) for commands
    pub command_args: Option<serde_json::Value>,
    pub canon_drift_flags: Vec<DriftFlag>,        // populated by world-rule validator (PL-15..PL-21)
}
```

### 3.6 `actor_binding`

```rust
#[derive(Aggregate)]
#[dp(type_name = "actor_binding", tier = "T2", scope = "reality")]
pub struct ActorBinding {
    #[dp(indexed)] pub actor: ActorId,            // PC or NPC
    pub current_channel: ChannelId,               // cell where this actor is "physically" present
    pub last_moved_turn: u64,                     // channel-event-id at last move (for ordering)
    pub binding_kind: BindingKind,                // PC | NPC_OwnerNode_<node_id> | NPC_AmbientFloating
}
```

- T2 + RealityScoped: every actor in a reality has exactly one current location at any time. Querying "where is Tiểu Thúy?" = `read_projection_reality<ActorBinding>(ctx, actor_id)`.
- Updated whenever `move_actor_to_cell` is invoked (which is itself a feature method that wraps `move_session_to_channel` for PCs and an internal NPC handoff for NPCs).
- Required because cells can host actors who don't have an SDK session (NPCs without active LLM interaction). Channel `MemberJoined`/`MemberLeft` covers session-bound presence; `actor_binding` covers everyone else.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq (per active session) | Write freq | Eligibility justification |
|---|---|---|---|---|---|---|
| `fiction_clock` | T2 | T2 | Reality | ~1 per turn (UI clock) | ~1 per turn | Canon time advancement; ≤1s projection lag fine; reality-global. |
| `scene_state` | T2 | T2 | Channel (cell) | ~1 at session bind + on ambient change | ~0.1/turn | Re-load must show same scene; per-cell. |
| `participant_presence` | T1 | T1 | Channel (cell) | high (every render frame in UI) | ~1 on enter/leave/idle | Live "who's here"; 30s loss OK because re-derivable from `MemberJoined` log. |
| Canonical `MemberJoined`/`MemberLeft` | n/a (subscribe) | DP-internal | Channel | streamed | DP-emitted only (DP-A18 §c) | Audit-grade canonical, gap-free durable subscribe. |
| `TurnEvent` (channel event) | n/a (event log) | T2 (via `advance_turn`) | Channel (cell) | streamed | 1 per turn | Per DP-A17 every channel event is tagged with `turn_number`; SSOT is event log. |
| `actor_binding` | T2 | T2 | Reality | ~1 per turn for resolved participants | ~1 per move | Reality-global query "where is X". |

No T0, no T3. Justification:
- **No T0:** PC turns persist across sessions (T2 minimum — DP-T0 eligibility rule fails clause 3 "lifetime bounded by single session").
- **No T3:** No money / no item trade / no canon-promotion in this feature. Canon promotion is DF8 (separate feature). Currency is PCS-* (separate feature). PL_001 deals only with where + when, both of which tolerate ≤1s eventual consistency.

---

## §5 DP primitives this feature calls

By name, with arity. No raw `sqlx` / `redis` (DP-R3).

### 5.1 Reads

- `dp::read_projection_reality::<FictionClock>(ctx, FictionClockId::SINGLETON, wait_for=None, ...)` — every turn-render in UI.
- `dp::read_projection_channel::<SceneState>(ctx, &cell, scene_state_id, wait_for=None, ...)` — at session bind + after each turn for ambient updates.
- `dp::read_projection_reality::<ActorBinding>(ctx, actor_id, wait_for=Some(turn_token), ...)` — when world-service resolves "is NPC X in this cell?" right after a movement turn. **CausalityToken use case.**
- `dp::query_scoped_channel::<ParticipantPresence>(ctx, &cell, Predicate::field_eq(state, Active), limit=8)` — UI list of who's-here.

### 5.2 Writes

- `dp::advance_turn(ctx, &cell, turn_data, causal_refs)` — once per submitted turn. Returns `TurnAck { channel_event_id, turn_number, applied_at }` + a `CausalityToken` (via the underlying T2 commit).
- `dp::t2_write::<FictionClock>(ctx, FictionClockId::SINGLETON, FictionClockAdvance { fiction_duration })` — same RPC handler, after `advance_turn` succeeds, advances the fiction clock by the proposed duration.
- `dp::t2_write::<SceneState>(ctx, scene_id, SceneStateDelta::AmbientUpdate { ambient })` — when ambient changes (weather, crowd).
- `dp::t1_write::<ParticipantPresence>(ctx, presence_id, PresenceDelta::Transition { from, to })` — on enter/leave/idle, in response to `MemberJoined`/`MemberLeft` durable events.
- `dp::t2_write::<ActorBinding>(ctx, actor_id, ActorBindingDelta::MoveTo { new_cell, turn })` — on PC `/travel` or NPC handoff.

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
| `read: actor_binding @ T2` | every PC session | "who is in this cell" resolution. |
| `read: participant_presence @ T1 @ cell-channel` | every PC session | live presence list. |
| `subscribe: channel_events @ cell + ancestor_chain` | every PC session | turn render + bubble-up. |
| `write: fiction_clock @ T2` | world-service backend session ONLY (NOT PC sessions) | Per DP-A6: PCs propose via Python LLM bus → Rust validates → Rust writes. |
| `write: scene_state @ T2 @ cell-channel` | world-service backend ONLY | same. |
| `write: actor_binding @ T2` | world-service backend ONLY | same. |
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
- `/travel` is a multi-step chain (advance_turn → fiction_clock advance → actor_binding move → create_channel → move_session_to_channel → MemberJoined emit). UI's first read after the chain may need to wait longer; UI passes `causality_timeout=Some(Duration::from_secs(20))` on the first `read_projection_reality<ActorBinding>` after a travel.
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

  3e. dp.t2_write::<ActorBinding>(new_ctx, pc_id,
        ActorBindingDelta::MoveTo { new_cell, turn: T1.turn_number })  →  T2Ack { causality_token = T3 }

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

**Token chain:** T1 (advance_turn ack) → T2 (clock ack) → T3 (actor_binding ack). Step 5 passes T3 — the latest in the chain — to `wait_for`. DP guarantees that any read with `wait_for=T3` reflects T1, T2, T3 because they were committed in sequence within the same writer's session and `last_applied_event_id` is monotonic per channel + monotonic per reality outbox.

V1 can simplify by passing T2 to UI (since T3 is reality-scoped and T2 is also reality-scoped after the cell exists); but the safest contract is "always pass the last token in the chain". Locked: world-service returns the LAST `causality_token` from the chain.

---

## §11 Sequence: one normal turn (Session 1, Turn 4 — PC says "Tiểu nhị, lấy cho ta một bình trà")

```text
UI: type text + send → gateway POST /v1/turn

gateway → roleplay-service:
  intent = FreeNarrative (Speak)
  PL-4 prompt assembly with NPC=Tiểu Thúy + scene from SceneState read
  PL-5 LLM stream → narrator_text "Tiểu Thúy mỉm cười, gật đầu rồi quay đi pha trà..."
  PL-19/PL-20 sanitize/filter passes
  emit proposal: TurnProposal { actor: pc_id, intent: Speak, narrator_text, fiction_duration: 30s }

world-service (consumer):
  PL-15 classify (cross-check): Speak ✓
  PL-16 oracle: tea-pot exists in scene props ✓
  PL-21 retrieval-isolation: ok ✓
  claim_turn_slot
  advance_turn(turn_data=TurnEvent::Speak { ... })           → T1
  t2_write FictionClock += 30s                                → T2
  release_turn_slot
  return T2 to gateway

UI: subscribe-stream delivers TurnEvent → render narrator_text + advance clock display

NPC react (next turn, automatic):
  world-service schedules NPC turn for Tiểu Thúy
  emit NPC proposal via internal LLM call
  → same flow, ending with another advance_turn
```

Wall-clock budget per turn (DP latency budgets): claim_turn_slot ≤10ms + advance_turn ≤50ms (T2 ack) + t2_write ≤5ms + release ≤5ms = **~70ms DP overhead**. The dominant cost is LLM streaming (1-10s, NOT in DP scope).

---

## §12 Sequence: `/sleep until dawn` (Session 2, Turn 11 — 8h fast-forward, day-boundary crossed)

```text
PC turn 10 ends at 1256-thu-day3-Tý-sơ (~23h00). PC types "/sleep until dawn".

gateway → roleplay-service:
  intent = MetaCommand → Sleep
  args = { until: "dawn" }

world-service:
  resolve dawn = next Mão-sơ from current FictionClock = ~5h00 of day4
  fiction_duration = 6h (Tý-sơ → Mão-sơ across day boundary)
  validate world-rule: PC is in a rented room (scene metadata.private_safe=true) ✓
  validate canon: nothing canonical happens to Lý Minh between 23h-5h that night ✓
  (if siege starts here — see SPIKE_01 obs#15 — world-rule rejects sleep, returns CommandRejected)

  claim_turn_slot
  advance_turn(turn_data = FastForward { fiction_duration: 6h })  → T1 (turn_number incremented by 1)
  t2_write FictionClock += 6h                                       → T2 (day boundary crossed; day=4, sub_day=Mão-sơ)
  release_turn_slot
  return T2

LLM-narration step (decoupled):
  roleplay-service polls for FictionClock projection with wait_for=T2, generates wake-up narration
  emit a follow-up TurnEvent::Narration via internal command (NOT a new turn — same turn_number)

UI: clock advances visually; narrator_text "Lý Minh tỉnh giấc khi gà gáy lần đầu..."
```

**MV12-D5 validation (date-boundary):** SPIKE_01 observed that day boundary is "atomic" — no events occur between 23h and 5h that PC sees, because the only writer (PC's own cell) is in fast-forward mode. Other realities at the parent tavern level may have events, but bubble-up is filtered by `paused_until`-equivalent semantic at the cell (cell is in fast-forward = effectively unsubscribed from ambient).

V1 implementation: cell does NOT pause on fast-forward; instead, world-service's bubble-up consumer drops events with `arrived_at_cell_after_fast_forward_completes` flag set. Detail in PL_002 (gossip aggregator).

---

## §13 Open questions deferred + their landing point

| ID | Question | Defer to |
|---|---|---|
| MV12-D8 | Narration taxonomy — what kinds of TurnEvent payloads exist beyond Speak/Action/MetaCommand/FastForward? | PL_003 (multi-NPC turn) |
| MV12-D9 | Scope of `command_args` schema per command kind (sleep, travel, verbatim, prose, ...) | PL_002 (command grammar) — already cataloged as PL-2 |
| MV12-D10 | NPC-only routine scenes happening in the cell while PC is asleep — do they emit TurnEvents tagged with future turn_numbers? | DL_001 (NPC routine foundations) |
| MV12-D11 | Drift tolerance: does `fiction_clock` advance even when world-rule rejects the turn? | PL_002 (rejection path) — current answer in this doc: NO, advance only on accepted advance_turn. |
| Cell auto-dormant policy | What inactivity window (DP-Ch32 default 30min) is right for our cells? | Operational tuning (Phase 5 ops) |
| Cross-reality clock | Multiverse extensions — does fiction_clock vary per-reality independently? Yes per DP-A14 reality-scope. Cross-reality time queries via R5. | DF12 cross-reality (already withdrawn) |

---

## §14 Cross-references

- [00_foundation/02_invariants.md](../../00_foundation/02_invariants.md) — I1..I19 invariants
- [00_foundation/05_vocabulary.md](../../00_foundation/05_vocabulary.md) — TurnState 8-state, PresenceState 6-state, fiction-time vocab
- [03_multiverse/01_four_layer_canon.md](../../03_multiverse/) — canon layer this feature respects
- [05_llm_safety/](../../05_llm_safety/) — A3 World Oracle, A5 intent classifier, A6 injection defense — all run BEFORE world-service writes
- [06_data_plane/02_invariants.md](../../06_data_plane/02_invariants.md) DP-A1..A19
- [06_data_plane/03_tier_taxonomy.md](../../06_data_plane/03_tier_taxonomy.md) DP-T0..T3
- [06_data_plane/11_access_pattern_rules.md](../../06_data_plane/11_access_pattern_rules.md) DP-R1..R8
- [06_data_plane/04a..04d_*.md](../../06_data_plane/) DP-K1..K12 SDK surface
- [06_data_plane/12_channel_primitives.md](../../06_data_plane/12_channel_primitives.md) DP-Ch1..Ch10 channel CRUD
- [06_data_plane/15_turn_boundary.md](../../06_data_plane/15_turn_boundary.md) DP-Ch21..Ch24 advance_turn
- [06_data_plane/18_causality_and_routing.md](../../06_data_plane/18_causality_and_routing.md) DP-Ch38..Ch40 CausalityToken
- [06_data_plane/21_llm_turn_slot.md](../../06_data_plane/21_llm_turn_slot.md) DP-Ch51..Ch53 turn-slot patterns
- [06_data_plane/22_feature_design_quickstart.md](../../06_data_plane/22_feature_design_quickstart.md) — design template this doc follows
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative validation source

---

## §15 Implementation readiness checklist

This doc satisfies every required item per DP-R2 + 22_feature_design_quickstart.md §"Required feature doc contents":

- [x] **§3** Aggregate inventory with `#[derive(Aggregate)]` declarations
- [x] **§4** Tier+scope table per aggregate (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Capability JWT claim requirements
- [x] **§7** Subscribe pattern
- [x] **§8** Pattern choices (turn-slot Strict, redaction Transparent, causality timeout 5s/20s)
- [x] **§9** Failure-mode UX (every DpError variant has user copy)
- [x] **§10** Cross-service handoff with CausalityToken chain
- [x] **§11/§12** End-to-end sequences for normal turn + fast-forward
- [x] **§13** Deferrals named with landing point

**Next** (when this doc locks): world-service + roleplay-service can be scaffolded against this contract. The first vertical-slice implementation target is the SPIKE_01 turn 1-4 path (PC enters Yên Vũ Lâu → orders tea → Tiểu Thúy responds), wall-clock target ≤2s end-to-end excluding LLM streaming.
