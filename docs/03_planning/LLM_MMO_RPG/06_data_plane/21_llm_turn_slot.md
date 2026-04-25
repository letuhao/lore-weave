# 21 — LLM Turn Slot Primitive + Patterns (DP-Ch51..DP-Ch53)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q20 — Phần B](99_open_questions.md) (LLM turn slot primitive + pattern documentation). **Phần A** (quantitative DP-S\* rescale based on V1 prototype data) remains deferred — no design action available without measurement.
> **Stable IDs:** DP-Ch51..DP-Ch53.

---

## Reading this file

LLM calls dominate the hot path: 1-10s per NPC "think" vs DP's <50ms write budget. This file does **not** redesign latency targets (that needs V1 data). Instead it adds two small DP primitives (turn-slot claim + auto-timeout) and documents three feature-level patterns that compose existing DP primitives (`channel_pause` from DP-Ch35 + `advance_turn` from DP-Ch21 + capability gating) into LLM-aware turn coordination.

Most of Q20's value is the **pattern doc** — features pick a pattern and use existing primitives. The two new primitives (DP-Ch51-52) are convenience hooks that make UI + auto-recovery cleaner; they're not strictly required for any pattern to work.

- DP-Ch51: `claim_turn_slot` / `release_turn_slot` / `get_turn_slot` primitives + schema
- DP-Ch52: Auto-timeout scheduler + canonical `TurnSlotTimedOut` event
- DP-Ch53: Three LLM turn slot patterns (Strict / Concurrent / Cancellable) with composition recipes

---

## DP-Ch51 — Turn slot primitive

### What it is — and is NOT

**Is:** an advisory hint stored in the channel's writer state. Says "actor X is currently expected to act, until time T". Read by UI ("NPC X is thinking..."), used by the auto-timeout scheduler (DP-Ch52), consumed by feature-level patterns.

**Is NOT:** an enforcement primitive. The slot does **not** block other writes from being committed at DP level. Blocking is `channel_pause`'s job ([DP-Ch35](17_channel_lifecycle.md#dp-ch35--channel_pause--channel_resume-primitives)). Slot + pause compose in feature patterns (DP-Ch53).

### Schema extension

Extends `channel_writer_state` ([DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol)):

```sql
ALTER TABLE channel_writer_state
    ADD COLUMN current_turn_actor   JSONB,        -- serialized ActorId, NULL = no slot held
    ADD COLUMN turn_started_at      TIMESTAMPTZ,
    ADD COLUMN turn_expected_until  TIMESTAMPTZ,  -- soft deadline; auto-timeout if exceeded
    ADD COLUMN turn_slot_reason     TEXT;         -- feature-defined ("npc_llm_thinking", "player_acting", etc.)
```

All columns nullable; default to NULL = no slot held.

### Primitives

```rust
pub struct TurnSlot {
    pub actor: ActorId,
    pub started_at: Timestamp,
    pub expected_until: Timestamp,
    pub reason: String,
}

pub struct TurnSlotAck {
    /// channel_event_id of the TurnSlotClaimed event committed.
    pub channel_event_id: u64,
    pub expected_until: Timestamp,
}

impl DpClient {
    /// Claim the turn slot for `actor` on `channel`, expected to last
    /// `expected_duration`. Capability-gated by `can_advance_turn` (slot
    /// management is a turn-advance concern). Idempotent on the same actor
    /// — re-claiming extends `expected_until` and returns the existing slot.
    /// Re-claiming when ANOTHER actor holds the slot fails with
    /// `DpError::TurnSlotHeldBy { actor, expected_until }`.
    pub async fn claim_turn_slot(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
        actor: ActorId,
        expected_duration: Duration,
        reason: String,
    ) -> Result<TurnSlotAck, DpError>;

    /// Release the slot. Typically called after the actor's action emits +
    /// advance_turn. Idempotent — releasing an unclaimed slot is no-op.
    /// Forced release (admin / ops) is allowed via separate `force_release_
    /// turn_slot(ctx, channel)` capability-gated by `can_admin_channel`.
    pub async fn release_turn_slot(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
    ) -> Result<(), DpError>;

    /// Cheap read of current slot state. Returns None if no slot held.
    /// Used by UI ("who is thinking?"), feature orchestrators, and DP-Ch52
    /// scheduler.
    pub async fn get_turn_slot(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
    ) -> Result<Option<TurnSlot>, DpError>;
}
```

### Canonical events

Like membership/lifecycle events, slot transitions are reserved canonical events emitted by DP — features cannot forge them.

```rust
#[derive(serde::Serialize, serde::Deserialize)]
pub struct TurnSlotClaimed {
    pub actor: ActorId,
    pub started_at: Timestamp,
    pub expected_until: Timestamp,
    pub reason: String,
    pub claimed_by: String,    // service identity from JWT
}
impl ChannelEvent for TurnSlotClaimed {
    const EVENT_TYPE: &'static str = "turn_slot_claimed";
}

#[derive(serde::Serialize, serde::Deserialize)]
pub struct TurnSlotReleased {
    pub actor: ActorId,
    pub released_at: Timestamp,
    pub release_kind: ReleaseKind,
}
#[derive(serde::Serialize, serde::Deserialize)]
pub enum ReleaseKind {
    /// Holder explicitly called release_turn_slot.
    Voluntary,
    /// Auto-released by scheduler (DP-Ch52) on expected_until expiry.
    Timeout,
    /// Admin / ops forced release.
    Forced { released_by: String },
}
impl ChannelEvent for TurnSlotReleased {
    const EVENT_TYPE: &'static str = "turn_slot_released";
}
```

### Capability gating

`claim_turn_slot` + `release_turn_slot` use the existing `can_advance_turn: Vec<level_name>` claim ([DP-Ch23](15_turn_boundary.md#dp-ch23--capability-gating)). No new capability — turn-slot management is a turn-advance concern.

`force_release_turn_slot` requires admin capability `can_admin_channel: Vec<level_name>` (a generic channel-admin claim used here + by future admin ops).

### Slot uniqueness

Per channel, **exactly one slot** at a time. Re-claiming by the same actor extends; re-claiming by a different actor fails. Avoids ambiguity about "whose turn is it really".

To pre-empt (steal slot from another actor): force-release first, then claim. Audit-logged via `TurnSlotReleased { kind: Forced }`.

---

## DP-Ch52 — Auto-timeout scheduler + `TurnSlotTimedOut` event

### Why timeout

LLM calls can stall (provider outage, infinite loop, network hang). Without a deadline, a stuck NPC freezes the channel forever. Auto-timeout via expected_until is the safety net.

### Scheduler

CP runs a periodic scan every **30 seconds** over each active reality:

```sql
SELECT channel_id, current_turn_actor, turn_expected_until
FROM channel_writer_state
WHERE current_turn_actor IS NOT NULL
  AND turn_expected_until < now();
```

For each match, CP coordinates the timeout through the channel's writer node:

```text
1. CP -> writer SDK: "timeout slot on channel C"
2. Writer SDK:
   a. Re-check expected_until (anti-race; another release may have just happened)
   b. If still expired:
       Emit canonical TurnSlotTimedOut event (channel_event_id allocated)
       UPDATE channel_writer_state SET current_turn_actor = NULL,
              turn_started_at = NULL, turn_expected_until = NULL,
              turn_slot_reason = NULL WHERE channel_id = C
       Emit TurnSlotReleased { kind: Timeout }
3. CP updates channel-tree cache; subscribers receive the events via durable
   subscribe.
```

### `TurnSlotTimedOut` event

```rust
#[derive(serde::Serialize, serde::Deserialize)]
pub struct TurnSlotTimedOut {
    pub actor: ActorId,
    pub claimed_at: Timestamp,
    pub expected_until: Timestamp,
    pub timed_out_at: Timestamp,
    pub reason: String,    // copy from original claim
}
impl ChannelEvent for TurnSlotTimedOut {
    const EVENT_TYPE: &'static str = "turn_slot_timed_out";
}
```

Followed by `TurnSlotReleased { kind: Timeout }` in the same writer transaction.

Features observing the channel's event stream can react: alert, retry the LLM call, advance to next actor, surface "NPC took too long" UI.

### Feature responsibility

Auto-timeout **does not** kill the in-flight LLM call. The LLM call is owned by the feature (roleplay-service); when feature observes `TurnSlotTimedOut`, it decides whether to:
- Cancel the in-flight LLM call and discard the response (typical)
- Let the LLM call complete and apply the result (rare, only if late-result is still valuable)

Cancellation is feature-level — DP doesn't reach into LLM client state.

### Tunable timeout

`expected_duration` is per-claim (caller specifies). Reasonable defaults per pattern:

| Pattern | Typical `expected_duration` |
|---|---:|
| Strict turn order — short LLM | 15 s |
| Strict turn order — long LLM (multi-turn reasoning) | 30 s |
| Concurrent thinking | 60 s (more tolerant; concurrent activity continues) |
| Cancellable thinking | 30 s |

Hard ceiling: claims with `expected_duration > 5 minutes` rejected with `DpError::ExpectedDurationTooLong` — protects against runaway slot holds.

---

## DP-Ch53 — Three LLM turn slot patterns

These are **feature-level recipes** composing DP primitives. Roleplay-service (or whichever service drives NPC turns) picks a pattern per channel-type and implements it. DP exposes the building blocks; feature owns the orchestration.

### Pattern 1: Strict turn order

**Use when:** turn-based discipline matters; players expect "wait for NPC then act".

**Composition:**

```text
1. claim_turn_slot(actor=NPC, expected_duration=20s, reason="npc_llm_thinking")
2. channel_pause(reason="npc_thinking", paused_until=Some(now + 25s))
3. Make LLM call (1-10s typical, 20s timeout safety)
4. Validate output (canon-drift lint, world-rules check, capability gate)
5. t2_write_channel(npc_action_event)  // or t3_write_channel for canon
6. advance_turn(turn_data={"actor": NPC, ...})
7. channel_resume()
8. release_turn_slot()
```

**Player behavior during NPC turn:** writes blocked by `channel_pause`. Players see "NPC X is thinking..." UI sourced from `get_turn_slot`. Action queued client-side or surfaced as "wait" toast.

**Failure modes:**
- LLM exceeds expected_duration → DP-Ch52 auto-timeout → channel resumes; feature detects via `TurnSlotTimedOut` and either retries or skips NPC turn.
- LLM call fails (provider error) → feature catches, calls release_turn_slot + channel_resume; emits NPC fallback action ("NPC X says: ...generic line...").

### Pattern 2: Concurrent thinking

**Use when:** real-time-feeling chat where multiple actors act in parallel; turn-based purity is relaxed.

**Composition:**

```text
1. claim_turn_slot(actor=NPC, expected_duration=60s, reason="npc_llm_thinking")
2. (NO channel_pause — channel stays open)
3. Make LLM call (concurrent with player activity)
4. While LLM is running:
    - Players can write actions (t2_write_channel)
    - advance_turn happens for THEIR turns (with their actor identity)
    - Other NPCs can claim THEIR own slots (parallel slots not allowed —
      BUT feature can use per-actor "thinking flag" instead of slot if
      slot uniqueness is too restrictive)
5. LLM returns
6. Validate + write NPC action
7. release_turn_slot()
```

**Player behavior:** UI shows "NPC X is thinking..." but doesn't block them. NPC's action eventually appears in chat as a delayed event.

**Caveat:** slot is exclusive per channel. If multiple NPCs need to "think concurrently", feature uses presence (T1) / typing-indicator pattern instead, NOT slot. Slot is for "this is whose authoritative turn is currently being computed".

**Best for:** social RP channels where chat flow > turn discipline.

### Pattern 3: Cancellable thinking

**Use when:** preserve turn discipline but allow player to interrupt slow NPCs.

**Composition:**

```text
1. claim_turn_slot(actor=NPC, expected_duration=20s, reason="npc_llm_thinking")
2. (NO channel_pause — channel stays open for cancellation signal)
3. Make LLM call with feature-level cancellation token
4. Player A acts:
    a. Feature detects (writes to channel)
    b. Feature cancels LLM call (kills in-flight HTTP / closes stream)
    c. release_turn_slot() (kind: Voluntary)
    d. Process player A's action normally
5. (Race resolution: if LLM returns just as player A acts, feature decides
   "winner" — typically player wins; LLM result discarded.)
```

**Player behavior:** UI shows "NPC X is thinking..." with optional "skip" button. Action goes through normally; NPC's pending think is discarded.

**Caveat:** burns LLM API call without using result. Cost-conscious deployments may prefer Pattern 1 with shorter timeouts.

### Choosing a pattern

| Concern | Pattern 1 (Strict) | Pattern 2 (Concurrent) | Pattern 3 (Cancellable) |
|---|:---:|:---:|:---:|
| Turn discipline | Strong | Weak | Strong |
| Player wait time | Up to LLM duration | None | Up to interrupt |
| LLM cost waste | Low (timeout-bounded) | Low | Higher (cancellations) |
| Implementation complexity | Lowest | Medium (race handling) | Highest (cancellation token) |
| Best for | Turn-based combat, scripted scenes | Social RP chat | Mixed / player-friendly |

DP supports all three. Feature designs (DF4 World Rules, DF5 Session+Group Chat, future roleplay-service work) pick per channel-type.

### Cross-channel composition

A reality may use **different patterns at different channel levels**:
- Cell sessions: Pattern 1 (strict, scripted scenes) or Pattern 3 (cancellable, RP chat)
- Tavern broadcast events: Pattern 2 (ambient drama emissions don't block tavern conversation)
- Town-level narrative beats: Pattern 1 (significant moments stop everyone)

This is feature design, not DP enforcement.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch51 | `claim_turn_slot` / `release_turn_slot` / `get_turn_slot` SDK primitives; channel_writer_state extended with current_turn_actor + turn_expected_until + turn_slot_reason; canonical TurnSlotClaimed / TurnSlotReleased reserved events; per-channel slot uniqueness; capability gated by `can_advance_turn` |
| DP-Ch52 | CP scheduler (30-s cadence) auto-times-out expired slots; emits canonical TurnSlotTimedOut + TurnSlotReleased{Timeout}; feature catches event and decides retry/cancel/skip; hard ceiling 5 min on expected_duration |
| DP-Ch53 | Three feature-level patterns: Strict (slot + pause + advance), Concurrent (slot only), Cancellable (slot + cancellation token); composition recipes; pattern-choice decision matrix; cross-channel composition allowed |

---

## Cross-references

- [DP-Ch21](15_turn_boundary.md#dp-ch21--turnboundary-event--advance_turn-primitive) — `advance_turn` + capability gating; slot is companion to advance_turn
- [DP-Ch23](15_turn_boundary.md#dp-ch23--capability-gating) — `can_advance_turn` JWT claim, reused for slot management
- [DP-Ch35](17_channel_lifecycle.md#dp-ch35--channel_pause--channel_resume-primitives) — `channel_pause` used by Pattern 1 (Strict) to block writes
- [DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol) — `channel_writer_state` table extended here
- [02_storage R6](../02_storage/R06_R12_publisher_reliability.md) — outbox publisher delivers slot events to subscribers
- [04_kernel_api_contract.md](04_kernel_api_contract.md) — primitive signatures registered

---

## What this leaves to other Phase 4 items

| Q | Status |
|---|---|
| **Q20 Phần A** quantitative DP-S\* rescale | Still V1-data-deferred. No design action without prototype measurement. |
| **Q20 Phần B** LLM turn slot primitive + patterns | ✅ Resolved here. |
| **Phase 2b** Rust implementation of slot primitives | Picked up when V1 game services begin coding. |

After this file, **Phase 4 has only Q20-Phần-A remaining** — purely a measurement question, not a design question. 06_data_plane design is functionally complete; SDK implementation is the next phase of work.
