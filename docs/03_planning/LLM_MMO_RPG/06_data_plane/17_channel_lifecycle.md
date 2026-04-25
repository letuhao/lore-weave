# 17 — Channel Lifecycle, Membership & Pause (DP-Ch31..DP-Ch37)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q19 + Q28 + Q31](99_open_questions.md) — channel pause semantics, membership ops, and full lifecycle state machine. Implements [DP-A18](02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25).
> **Stable IDs:** DP-Ch31..DP-Ch37.

---

## Reading this file

Three Phase 4 questions cluster here because they share one state machine: a channel's lifecycle (Q31), the membership transitions that drive parts of it (Q28), and the orthogonal pause flag that gates writes during operational events (Q19). Splitting them across files would fragment the state machine.

- DP-Ch31: lifecycle states + transitions + invariants
- DP-Ch32: auto-dormant trigger (cell-only)
- DP-Ch33: dissolution + archival
- DP-Ch34: canonical `MemberJoined` / `MemberLeft` events
- DP-Ch35: `channel_pause` / `channel_resume` SDK primitives
- DP-Ch36: pause + lifecycle composition rules
- DP-Ch37: recovery + idempotency on lifecycle ops

---

## DP-Ch31 — Lifecycle states + transitions

### State machine

```
                ┌─────────────┐
                │   Active    │
                └──┬───────┬──┘
        auto/manual│       │admin only
                   ▼       ▼
              ┌─────────┐  ┌──────────┐
              │ Dormant │  │Dissolved │ ← terminal
              └─┬───────┘  └──────────┘
                │
       on first │ session bind
                ▼
              Active
```

| State | Meaning | Allowed ops |
|---|---|---|
| `Active` | Channel accepts ChannelScoped writes, advances turn, runs aggregators, services subscribe-events. | All ops; subject to pause flag (DP-Ch35) |
| `Dormant` | No active sessions; events not accepted; subscriptions inactive; aggregators paused-on-disk. | bind_session (auto-transitions back to Active); admin dissolve. |
| `Dissolved` | Terminal. Events archived per retention; ChannelId never reissued. | Read-only (events queryable for retention period); no new bindings. |

### Transitions table

| From | To | Trigger | Pre-conditions |
|---|---|---|---|
| (none) | Active | `create_channel` | parent exists, parent not Dissolved, not at max-depth |
| Active | Dormant (cell only, auto) | DP-Ch32 scheduler — no active sessions for ≥30min | level_name = "cell" (or whatever feature flag `auto_dormant_eligible` indicates) |
| Active | Dormant (admin) | admin CLI `channel-set-dormant` | no active sessions |
| Dormant | Active | first `bind_session` to this channel | not Dissolved |
| Active | Dissolved | `dissolve_channel` SDK + admin | all descendants Dissolved + no active sessions |
| Dormant | Dissolved | `dissolve_channel` SDK + admin | all descendants Dissolved |
| Dissolved | (any) | — | terminal, no transitions |

### Schema additions

```sql
-- channels table extended (per-reality DB)
ALTER TABLE channels
    ADD COLUMN paused_until         TIMESTAMPTZ,        -- NULL = not paused
    ADD COLUMN paused_reason        TEXT,
    ADD COLUMN paused_by            TEXT,                -- service identity that called pause
    ADD COLUMN became_dormant_at    TIMESTAMPTZ,         -- last active->dormant
    ADD COLUMN dissolved_at_eid     BIGINT;              -- channel_event_id of dissolution event

-- (existing) lifecycle TEXT NOT NULL CHECK (lifecycle IN ('active','dormant','dissolved'))
-- (existing) dissolved_at TIMESTAMPTZ from DP-Ch1
```

### Invariants

- **Single state at any time** — DB CHECK enforces enum.
- **Dissolved is terminal** — no UPDATE allowed away from Dissolved (enforced by row-level rule + SDK transition validator).
- **Pause only on Active** — `paused_until IS NOT NULL` requires `lifecycle = 'active'`. CHECK constraint:
  ```sql
  ALTER TABLE channels ADD CONSTRAINT channels_pause_active_only
    CHECK (paused_until IS NULL OR lifecycle = 'active');
  ```
- **Pre-conditions checked before transition** — SDK queries DB to verify (e.g., descendant lifecycle for dissolution); transitions inside DB transaction so concurrent transitions can't race (`SELECT ... FOR UPDATE`).

---

## DP-Ch32 — Auto-dormant trigger (cell-only)

### Scheduler

CP runs a periodic scan every **5 minutes** over each active reality:

```sql
SELECT id, last_member_left_at FROM channels
WHERE lifecycle = 'active'
  AND level_name = 'cell'                           -- only cells auto-dormant
  AND id NOT IN (SELECT current_channel_id FROM session_registry WHERE active = true)
  AND last_member_left_at < now() - interval '30 minutes';
```

For each candidate, CP coordinates the transition through the channel's writer node:

```text
1. CP -> writer-node SDK: "transition channel C to Dormant"
2. Writer SDK:
   a. Quiesce subscriptions
   b. Final aggregator snapshots
   c. Emit `ChannelStateTransition { from: Active, to: Dormant }` event
   d. UPDATE channels SET lifecycle = 'dormant', became_dormant_at = now() WHERE id = C
   e. ack to CP
3. CP updates channel-tree cache + pushes delta to subscribers
```

### Tunable per channel

`channels.metadata.auto_dormant_minutes: u32` overrides default (30). 0 = disabled (channel never auto-dormant).

### Non-cell channels

`level_name != 'cell'` channels never auto-dormant. Tavern, town, district, etc. transition to Dormant only via admin (`admin-channel-set-dormant`). Rationale: persistent locations are part of the world; their inactivity isn't auto-detected.

### Wakeup on bind

When a session calls `bind_session(reality_id, session_id, target_channel_id)` and `target` is Dormant:

```text
1. CP -> writer SDK: "wake channel C"
2. Writer SDK:
   a. Reload aggregators from snapshots
   b. Re-open subscriptions to descendants
   c. UPDATE channels SET lifecycle = 'active' WHERE id = C
   d. Emit `ChannelStateTransition { from: Dormant, to: Active }` event
   e. ack
3. CP updates cache
4. CP responds to bind_session with new SessionContext
```

Wakeup latency: ≤2 s p99 (snapshot reload + subscription reopen). Acceptable for player connecting to a dormant cell.

---

## DP-Ch33 — Dissolution + archival

### Dissolve flow

`DpClient::dissolve_channel(ctx, channel)` — capability-gated by `can_dissolve_channel: Vec<level_name>`.

```text
1. SDK validates pre-conditions:
   - All descendant channels are Dissolved (recursive query)
   - No active sessions in this channel
   - Channel currently Active or Dormant (not already Dissolved)
2. SDK acquires writer lease + DB tx:
   - Final aggregator snapshots
   - Emit `MemberLeft { reason: ChannelDissolved }` for each remaining member
     (typically 0 since pre-condition; this handles edge cases like
      sessions in mid-disconnect)
   - Emit `ChannelStateTransition { from: <current>, to: Dissolved }` event
   - UPDATE channels SET lifecycle = 'dissolved', dissolved_at = now(),
     dissolved_at_eid = <last channel_event_id> WHERE id = ?
3. CP updates channel-tree cache + delta push:
   - Subscribers of this channel receive `StreamEnd { reason: ChannelDissolved }`
   - Aggregators on parent see this channel disappear from `source_filter` matches
4. Event log + Redis Stream entries retained per retention policy.
```

### Archival policy

Dissolved channel events follow the per-reality retention policy in [02_storage R1](../02_storage/R01_event_volume.md):

- Events queryable via `event_log` table for full retention window (default 1 year)
- Redis Stream `dp:events:{reality}:{channel}` retained for original 7-day window then released (LRU eviction)
- Dissolved channel registry row kept indefinitely (small) — used to answer "did this channel exist?" historical queries
- Aggregator snapshots: kept for 90 days post-dissolution then GC'd (final state observable for that window)

### What happens to subscribers + aggregators

- Active subscribers receive `DurableStreamItem::StreamEnd { reason: ChannelDissolved }` per [DP-Ch20](14_durable_subscribe.md#dp-ch20--backpressure--disconnect--reconnect)
- Aggregators with this channel in their source_filter:
  - If filter is `Specific([X])` and X is dissolved: aggregator effectively becomes inactive (no more inputs)
  - If filter is `LevelName(...)` or `DirectChildren`: filter just stops matching this channel; other matches continue
  - Aggregators do NOT auto-unregister on partial source loss — feature owns that decision

### Re-create vs resurrect

A dissolved channel cannot be reactivated. To "have a tavern again", feature creates a NEW channel with `create_channel(parent, level_name = "tavern", ...)`, which gets a fresh ChannelId and starts at `last_event_id = 0`, `last_turn_number = 0`, etc. Optionally the new channel's metadata can carry `predecessor_id: ChannelId` so feature can show "this tavern is the successor to the old one" — DP doesn't interpret.

---

## DP-Ch34 — Canonical `MemberJoined` / `MemberLeft` events

### Event shapes

```rust
#[derive(serde::Serialize, serde::Deserialize)]
pub struct MemberJoined {
    pub actor: ActorId,
    pub joined_at: Timestamp,
    pub joined_via: JoinMethod,
}
impl ChannelEvent for MemberJoined {
    const EVENT_TYPE: &'static str = "member_joined";
}

#[derive(serde::Serialize, serde::Deserialize)]
pub enum JoinMethod {
    /// First time bind_session targets this channel.
    SessionBind,
    /// Session moved here from another channel.
    Migrated { from: ChannelId },
    /// Bind triggered Dormant -> Active wakeup.
    Reactivated,
}

#[derive(serde::Serialize, serde::Deserialize)]
pub struct MemberLeft {
    pub actor: ActorId,
    pub left_at: Timestamp,
    pub reason: LeaveReason,
}
impl ChannelEvent for MemberLeft {
    const EVENT_TYPE: &'static str = "member_left";
}

#[derive(serde::Serialize, serde::Deserialize)]
pub enum LeaveReason {
    /// Session called move_session_to_channel or disconnect intentionally.
    Voluntary,
    /// TCP/WebSocket dropped; CP detected via session-registry timeout.
    Disconnected,
    /// Session moved to another channel.
    Migrated { to: ChannelId },
    /// Channel was dissolved while this session held it.
    ChannelDissolved,
    /// Session idle-timeout (configurable per session).
    TimedOut,
}
```

### `ActorId`

```rust
pub enum ActorId {
    /// A player session — references PC + the session that hosts it.
    Player { player_id: PlayerId, session_id: SessionId },
    /// An NPC actor.
    Npc { npc_id: NpcId },
}
```

### When DP emits each event

| Event | Trigger |
|---|---|
| `MemberJoined { joined_via: SessionBind }` | First `bind_session` for this session+channel pair (channel was Active, no migration). |
| `MemberJoined { joined_via: Migrated { from } }` | `move_session_to_channel(target = this)` — emitted on `target` after committing the move. |
| `MemberJoined { joined_via: Reactivated }` | `bind_session` to a Dormant channel (channel transitions to Active first, then this join event). |
| `MemberLeft { reason: Voluntary }` | `move_session_to_channel(...)` — emitted on the SOURCE channel before commit. |
| `MemberLeft { reason: Migrated { to } }` | Equivalent of Voluntary but with destination annotated. (Voluntary used when the destination is reality-root or admin-driven.) |
| `MemberLeft { reason: Disconnected }` | Session-registry timeout (CP detects ≥60 s no heartbeat). |
| `MemberLeft { reason: ChannelDissolved }` | Channel transitioning to Dissolved while this session is still bound (rare edge case). |
| `MemberLeft { reason: TimedOut }` | Session idle-timeout per its capability TTL. |

### Forgery prevention

These event types are **reserved**: feature code cannot write them via `t2_write_channel<MemberJoined>(...)`. SDK type system blocks: `MemberJoined` does not implement `ChannelScoped` directly — only DP's internal emit path can construct + commit them. This guarantees the audit-grade invariant of DP-A18.

### Bubble-up consumption

Bubble-up aggregators see `MemberJoined` / `MemberLeft` like any other `SourceEvent`. Common patterns:

- **Cell-occupancy aggregator** in tavern: counts MemberJoined - MemberLeft per cell to know how busy each cell is.
- **Player-presence aggregator** at country level: tracks unique active players for analytics events.
- **Privacy-respecting**: aggregator on parent of a Private cell may receive `MemberJoined` events with `source_visibility = Private`; redaction policy applies (DP-Ch30).

---

## DP-Ch35 — `channel_pause` / `channel_resume` primitives

### API

```rust
impl DpClient {
    /// Pause a channel: game writes (advance_turn, ChannelScoped writes,
    /// bubble-up emits) reject with DpError::ChannelPaused. Lifecycle and
    /// administrative ops (member_left for disconnects, dissolve) continue.
    ///
    /// Capability-gated by `can_pause_channel: Vec<level_name>` JWT claim.
    ///
    /// `paused_until = Some(t)` schedules auto-resume at t.
    /// `paused_until = None` is indefinite — requires explicit `channel_resume`.
    ///
    /// `reason` is a free-form feature-defined string (e.g., "npc_reasoning",
    /// "admin_freeze", "drain_pending"). DP does not interpret.
    ///
    /// Idempotent: pausing an already-paused channel returns the existing
    /// PauseAck (no new event emitted).
    pub async fn channel_pause(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
        reason: String,
        paused_until: Option<Timestamp>,
    ) -> Result<PauseAck, DpError>;

    /// Clear the pause flag. Idempotent — resuming an unpaused channel is no-op.
    pub async fn channel_resume(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
    ) -> Result<(), DpError>;
}

pub struct PauseAck {
    /// channel_event_id of the ChannelPaused event committed.
    pub channel_event_id: u64,
    pub paused_until: Option<Timestamp>,
}
```

### Canonical pause events

```rust
#[derive(serde::Serialize, serde::Deserialize)]
pub struct ChannelPaused {
    pub reason: String,
    pub paused_until: Option<Timestamp>,
    pub paused_at: Timestamp,
    pub paused_by: String,    // service identity from capability JWT
}
impl ChannelEvent for ChannelPaused {
    const EVENT_TYPE: &'static str = "channel_paused";
}

#[derive(serde::Serialize, serde::Deserialize)]
pub struct ChannelResumed {
    pub resumed_at: Timestamp,
    pub resumed_by: String,    // service identity, OR "auto-expiry" on auto-resume
}
impl ChannelEvent for ChannelResumed {
    const EVENT_TYPE: &'static str = "channel_resumed";
}
```

Like membership events, pause events are **reserved** and emitted only by DP.

### Auto-resume on expiry

CP's scheduler (same loop as auto-dormant in DP-Ch32) checks every 60 s:

```sql
SELECT id FROM channels
WHERE lifecycle = 'active'
  AND paused_until IS NOT NULL
  AND paused_until < now();
```

For each match, CP coordinates resume through the writer (emits `ChannelResumed { resumed_by: "auto-expiry" }`). Result: pauses with explicit deadlines self-clean; indefinite pauses (`paused_until = None`) require explicit `channel_resume`.

### Pause check on writes

Every channel-scoped write op (in-SDK):

```rust
async fn t2_write_channel<A: T2Aggregate + ChannelScoped>(...) -> Result<_, DpError> {
    // ... existing capability + reality checks ...

    let ch = self.channel_tree.get(channel)?;
    if let Some(t) = ch.paused_until {
        if t > Timestamp::now() || ch.paused_until_indefinite() {
            return Err(DpError::ChannelPaused {
                channel: channel.as_str(),
                reason: ch.paused_reason.clone().unwrap_or_default(),
                paused_until: ch.paused_until,
            });
        }
    }
    // ... proceed with write ...
}
```

`advance_turn` and bubble-up aggregator emits use the same check.

### What pause does NOT block

- `move_session_to_channel(from = paused_channel)` — leaving a paused channel ALLOWED (player must be able to leave a freeze)
- `MemberLeft { reason: Disconnected | TimedOut }` — disconnect cleanup ALLOWED
- `dissolve_channel` — dissolution path ALLOWED (admin override)
- Read ops (`read_projection_channel`, `subscribe_channel_events_durable`) — ALLOWED
- Channel-tree inspection — ALLOWED

---

## DP-Ch36 — Pause + lifecycle composition rules

### Cross-state semantics

| Lifecycle | Pause flag effect |
|---|---|
| Active | Pause meaningful; halts game writes per DP-Ch35 |
| Dormant | Pause flag cleared on transition to Dormant (channel already inactive — pause meaningless) |
| Dissolved | Pause flag cleared on dissolution |

When transitioning Active → Dormant (auto or admin), if pause flag was set, it's cleared as part of the transition; CP emits `ChannelResumed { resumed_by: "lifecycle-dormant-transition" }` followed by `ChannelStateTransition { from: Active, to: Dormant }`.

When dissolving, pause flag is cleared similarly.

### Pause survives writer failover

Pause state lives in `channels` table (DB), not in writer's in-memory state. Failover writer reads pause state from DB on takeover and respects it. No in-flight writes between failover and recovery slip past pause check.

### Indefinite pause + writer failover

If an indefinite pause is in effect (paused_until = NULL) and the writer goes through reassignment, pause persists until explicit `channel_resume`. There is no auto-clear on failover — pause is a feature-driven state, not an operational one.

---

## DP-Ch37 — Recovery + idempotency

### Idempotent ops

- `create_channel(parent, level_name)` with same shape — returns existing ChannelId if a non-dissolved match exists ([DP-Ch8](12_channel_primitives.md#dp-ch8--channel-crud-primitives))
- `channel_pause(channel, ...)` on already-paused channel — returns existing PauseAck, no new event
- `channel_resume(channel)` on unpaused channel — no-op, no event
- `dissolve_channel(channel)` on already-dissolved channel — no-op error `DpError::ChannelAlreadyDissolved`

### Edge cases

| Scenario | Behavior |
|---|---|
| Bind to Dormant channel | Channel transitions to Active first (DP-Ch32 wakeup), then bind succeeds + MemberJoined { Reactivated } emitted |
| Bind to Dissolved channel | Hard error `DpError::ChannelDissolved`; no auto-resurrect |
| Move session to Dormant channel | Wakeup target first, then migrate (member_left old + member_joined new with `Reactivated` flag) |
| Move session to Dissolved channel | Hard error |
| Dissolve channel while sessions still bound | Pre-condition failure unless admin-force; admin-force emits `MemberLeft { ChannelDissolved }` for each remaining session |
| Dissolve channel while paused | Allowed; pause flag cleared as part of dissolution |
| Auto-dormant scheduler races with bind | CP holds session-registry lock while transitioning; bind that sees Active state proceeds; bind that sees Dormant triggers wakeup |

### Failover during lifecycle ops

Any in-flight lifecycle op that the writer was processing when it died: pre-condition checks may have read stale state. New writer re-validates pre-conditions before continuing. UNIQUE constraints on event_log + writer_state prevent double-emit of state-transition events during recovery race.

### Audit trail

Every lifecycle/pause op leaves a canonical event in the channel's event log:

- `ChannelStateTransition { from, to }`
- `ChannelPaused { reason, paused_until, paused_by }`
- `ChannelResumed { resumed_by }`
- `MemberJoined { actor, joined_via }`
- `MemberLeft { actor, reason }`

Plus an entry in `dp:writer_audit:{reality_id}` for ops that involve writer-state changes ([DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol)).

Operators can reconstruct any channel's history from these events. No untracked transitions.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch31 | 3-state lifecycle machine (Active / Dormant / Dissolved) + transition table + DB CHECK invariants; pause-only-on-Active constraint |
| DP-Ch32 | Auto-dormant scheduler for cells (default 30 min idle); per-channel tunable; non-cell admin-only; wakeup on first bind |
| DP-Ch33 | Dissolution flow with descendant pre-condition; event log retention per 02_storage R1; aggregator snapshots GC at +90 days; re-create != resurrect |
| DP-Ch34 | Canonical `MemberJoined` (with `JoinMethod`) + `MemberLeft` (with `LeaveReason`) reserved event types; emitted only by DP; readable via durable subscribe; bubble-up aggregators consume them |
| DP-Ch35 | `channel_pause(reason, paused_until)` + `channel_resume` SDK primitives; capability JWT `can_pause_channel`; reserved `ChannelPaused`/`ChannelResumed` canonical events; auto-resume on `paused_until` expiry |
| DP-Ch36 | Pause-flag composition with lifecycle (cleared on Dormant/Dissolved transitions); pause persists across writer failover via DB state |
| DP-Ch37 | Idempotency on lifecycle ops; edge-case taxonomy (bind-to-dormant, bind-to-dissolved, move during transitions); writer-failover lifecycle race handling; canonical audit trail |

---

## Cross-references

- [DP-A13](02_invariants.md#dp-a13--channel-hierarchy-as-first-class-scope-phase-4-2026-04-25) — channel hierarchy that this state machine operates on
- [DP-A18](02_invariants.md#dp-a18--channel-lifecycle-state-machine--canonical-membership-events-phase-4-2026-04-25) — the axiom this file implements
- [DP-Ch1](12_channel_primitives.md#dp-ch1--channelid-and-tree-structure) — `ChannelLifecycle` enum (now formally specified here) + max depth bound
- [DP-Ch2](12_channel_primitives.md#dp-ch2--channel-registry-per-reality-db-schema) — channels table schema (extended here with pause / dormant fields)
- [DP-Ch9](12_channel_primitives.md#dp-ch9--moving-a-session-to-a-different-channel) — `move_session_to_channel` triggers MemberJoined/MemberLeft per DP-Ch34
- [DP-Ch10](12_channel_primitives.md#dp-ch10--channel-tree-change-invalidation) — channel-tree-change events extended to include lifecycle transitions
- [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api) — durable subscribe delivers all canonical events to consumers
- [DP-Ch20](14_durable_subscribe.md#dp-ch20--backpressure--disconnect--reconnect) — `StreamEnd { ChannelDissolved }` semantics
- [DP-Ch25](16_bubble_up_aggregator.md#dp-ch25--bubbleupaggregator-trait--registerunregister-primitives) — aggregators consume membership + lifecycle events via SourceFilter
- [02_storage R1](../02_storage/R01_event_volume.md) — event-log retention this file delegates to for archival

---

## What this leaves to other Phase 4 items

| Q | Phase 4 progress |
|---|---|
| **Q19 channel pause** | ✅ Resolved here (DP-Ch35 + DP-Ch36). |
| **Q28 channel membership ops** | ✅ Resolved here (DP-Ch34); membership validation rules (capacity, prerequisites) remain feature-level per [DP-Ch8](12_channel_primitives.md#dp-ch8--channel-crud-primitives). |
| **Q31 channel lifecycle** | ✅ Resolved here (DP-Ch31..Ch33, Ch37). |
| **Q32 privacy bubble-up** | DP-Ch34 events include `source_visibility` per DP-Ch30 — Private channel membership events flow through with the visibility flag. Q32 will add policy templates for what's-emitted-vs-redacted. |
| **Q22 WrongWriterNode UX** | Independent — operational UX for misrouted writes during failover; not in this file. |
