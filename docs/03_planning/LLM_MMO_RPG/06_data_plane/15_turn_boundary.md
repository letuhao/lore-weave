# 15 — Turn Boundary Primitive (DP-Ch21..DP-Ch24)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q15](99_open_questions.md) — per-channel page/turn boundary as a first-class primitive. Implements [DP-A17](02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25) (per-channel turn numbering invariant).
> **Stable IDs:** DP-Ch21..DP-Ch24.

---

## Reading this file

This file specifies the **mechanism** behind DP-A17:

- DP-Ch21 — `TurnBoundary` event shape and the `advance_turn` SDK primitive.
- DP-Ch22 — `turn_number` column on `event_log`, `last_turn_number` on `channel_writer_state`, and the writer's allocation algorithm.
- DP-Ch23 — capability gating: which JWT claim authorizes a service to advance a channel's turn.
- DP-Ch24 — composition with the rest of Phase 4 (pause / bubble-up / move-session).

Turn boundaries are the **central sync primitive of the game** per the user's clarified model — every reality is a book with discrete page flips that all members of a channel see in order. DP makes this a first-class concept rather than letting each feature invent its own counter.

---

## DP-Ch21 — `TurnBoundary` event + `advance_turn` primitive

### Event shape

`TurnBoundary` is a `ChannelEvent` impl ([DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api)) with a fixed discriminator. Subscribers receive it via `subscribe_channel_events_durable<S>` like any other channel event:

```rust
#[derive(serde::Serialize, serde::Deserialize)]
pub struct TurnBoundary {
    /// New turn number — strictly previous + 1.
    pub turn_number: u64,

    /// Opaque feature-defined payload (D&D round, narrative scene title,
    /// "player A's turn", etc.). DP does not interpret.
    pub turn_data: serde_json::Value,
}

impl ChannelEvent for TurnBoundary {
    const EVENT_TYPE: &'static str = "turn_boundary";
}
```

When deserialized from a stream, a `TurnBoundary` event arrives as `DurableStreamItem::Event { payload: TurnBoundary, .. }` carrying:

- `channel_event_id` — its position in the channel's total order ([DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25))
- `writer_epoch` — writer that emitted it ([DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol))
- `causal_refs: Vec<EventRef>` — optional ([DP-Ch15](13_channel_ordering_and_writer.md#dp-ch15--causal-references-for-bubble-up-preview-full-design--q27)); features may cite the events that triggered the turn end
- `payload: TurnBoundary { turn_number, turn_data }` — this file's contribution

### `advance_turn` SDK primitive

```rust
impl DpClient {
    /// Advance the channel's turn counter by 1 and emit a TurnBoundary event.
    ///
    /// Capability-gated: SessionContext's capability JWT must include
    /// `can_advance_turn` for this channel level. Failure → CapabilityDenied.
    ///
    /// `turn_data` is opaque feature-defined payload; DP does not interpret.
    /// `causal_refs` is optional; features may cite the events that triggered
    /// the turn end (per DP-Ch15 schema).
    pub async fn advance_turn(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
        turn_data: serde_json::Value,
        causal_refs: Vec<EventRef>,
    ) -> Result<TurnAck, DpError>;
}

pub struct TurnAck {
    pub channel_event_id: u64,   // position of the TurnBoundary event
    pub turn_number: u64,         // new turn number (prev + 1)
    pub applied_at: Timestamp,
}
```

### What `advance_turn` does (writer-side)

When the call reaches the channel's writer node (transparently routed per [DP-Ch14](13_channel_ordering_and_writer.md#dp-ch14--cross-node-write-routing) if caller is on a different node):

```text
1. Verify capability: JWT.can_advance_turn for channel.level_name → else CapabilityDenied.
2. Begin DB transaction on per-reality Postgres.
3. Read channel_writer_state.last_turn_number (or 0 if not present) → call this prev.
4. Allocate next channel_event_id (per DP-Ch11).
5. Insert into event_log:
     reality_id, channel_id, channel_event_id (new), writer_epoch,
     turn_number = prev + 1, event_type = "turn_boundary",
     payload = serialize(TurnBoundary { turn_number: prev + 1, turn_data }),
     causal_refs.
6. UPDATE channel_writer_state SET last_turn_number = prev + 1.
7. Commit transaction.
8. Append to Redis Stream dp:events:{reality}:{channel} (DP-Ch17).
9. Return TurnAck { channel_event_id, turn_number: prev + 1, applied_at }.
```

Step 6 (UPDATE last_turn_number) is part of the same DB transaction as the event insert — if either fails, neither commits. No partial state observable.

### Subsequent events tagged with the new turn_number

After `advance_turn` commits, every subsequent channel event committed by the writer is tagged with the new `turn_number` in its event log row (see DP-Ch22). This applies to ChannelScoped writes (`t2_write_channel`, `t3_write_channel`), bubble-up emits ([Q27](99_open_questions.md)), and any other writer-driven event.

### What `advance_turn` does NOT do

- **Does not pause writes** — non-turn-advance events continue to be accepted; subscribers see the TurnBoundary event in order alongside any other events.
- **Does not block on subscriber acknowledgment** ([G4a decision](99_open_questions.md)) — slow consumers fall behind in the channel timeline; they catch up via the durable stream's normal protocol.
- **Does not affect ancestor channels** — advancing turn in cell C does not advance turn in tavern T. Each channel has its own turn counter. If a feature wants synchronized turns across channels (rare), the feature emits multiple `advance_turn` calls.
- **Does not gate other writes during the advance** — the DB transaction is atomic but quick (single insert + single update). Concurrent writes to the same channel route through the same writer's serialized command processor (writer is single-threaded per channel).

---

## DP-Ch22 — Schema extensions and writer allocation

### `event_log` extension

Building on the channel-event extension in [DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism), one more column is added:

```sql
ALTER TABLE event_log
    ADD COLUMN turn_number BIGINT NOT NULL DEFAULT 0;

CREATE INDEX event_log_turn_number_idx
    ON event_log(reality_id, channel_id, turn_number)
    WHERE channel_id IS NOT NULL;
```

For RealityScoped events (`channel_id IS NULL`), `turn_number` stays at the default 0 and is never read — it is only meaningful for channel events.

For channel events:

- `turn_number` is set on every insert by the writer.
- The default value 0 covers both "channel never advanced turns" and "TurnBoundary `turn_number=1` is in flight before any other event" — first event ever in a channel has `turn_number = 0` (or 1 if it's the first turn boundary itself).
- Index supports `WHERE turn_number = N` queries ("what happened in turn N").

### `channel_writer_state` extension

```sql
ALTER TABLE channel_writer_state
    ADD COLUMN last_turn_number BIGINT NOT NULL DEFAULT 0;
```

Updated atomically with each `advance_turn` (in the same DB transaction as the TurnBoundary event insert).

### Writer allocation algorithm

Pseudocode for the writer's in-memory state and per-call algorithm (extends [DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism)):

```rust
struct ChannelWriterState {
    channel_id: ChannelId,
    last_event_id: u64,       // DP-Ch11
    last_turn_number: u64,    // NEW in DP-Ch22
    epoch: u64,               // DP-Ch13
    in_flight: Vec<EventId>,
}

// On writer takeover:
async fn on_takeover(channel_id: ChannelId) -> ChannelWriterState {
    let row = db.query_one(
        "SELECT MAX(channel_event_id) AS max_eid,
                MAX(turn_number) AS max_turn
         FROM event_log
         WHERE reality_id = $1 AND channel_id = $2",
        &[reality_id, channel_id],
    ).await?;

    ChannelWriterState {
        channel_id,
        last_event_id: row.get("max_eid").unwrap_or(0),
        last_turn_number: row.get("max_turn").unwrap_or(0),
        epoch: cp.fetch_lease(channel_id).await?.epoch,
        in_flight: vec![],
    }
}

// On advance_turn:
async fn handle_advance_turn(state: &mut ChannelWriterState, ...) -> TurnAck {
    let new_event_id = state.last_event_id + 1;
    let new_turn = state.last_turn_number + 1;
    db.execute(
        "BEGIN;
         INSERT INTO event_log (..., turn_number, ...) VALUES (..., $new_turn, ...);
         UPDATE channel_writer_state SET last_turn_number = $new_turn WHERE channel_id = $cid;
         COMMIT;"
    ).await?;
    state.last_event_id = new_event_id;
    state.last_turn_number = new_turn;
    TurnAck { channel_event_id: new_event_id, turn_number: new_turn, applied_at: now() }
}

// On every other channel-event commit by the writer:
async fn handle_channel_event_write(state: &mut ChannelWriterState, ...) -> _Ack {
    let new_event_id = state.last_event_id + 1;
    db.execute(
        "INSERT INTO event_log (..., turn_number, ...) VALUES (..., $current_turn, ...)",
        &[..., state.last_turn_number /* current, NOT incremented */, ...],
    ).await?;
    state.last_event_id = new_event_id;
}
```

### Recovery / failover

On writer death and reassignment ([DP-Ch12](13_channel_ordering_and_writer.md#dp-ch12--writer-assignment-rules)):

- New writer's `MAX` query reseeds both `last_event_id` and `last_turn_number`.
- In-flight `advance_turn` whose DB tx did not commit is lost (caller's `advance_turn` returned an error). Caller decides whether to retry — DP does not auto-retry advance.
- An `advance_turn` whose tx committed but whose ack didn't reach the caller is **observable** by the caller via stream subscription (the TurnBoundary event arrives via durable subscribe even if the original ack was lost) — caller treats this as success on retry-detection.

### `MAX(turn_number)` race during failover

A subtle case: writer N1 commits TurnBoundary with `turn_number=5`, then dies before updating `channel_writer_state.last_turn_number` (UPDATE was inside the same tx as INSERT, but if the tx itself was interrupted between INSERT and UPDATE, both rolled back). New writer N2 queries `MAX(turn_number)`, gets 4, allocates 5 next — same number, but for a different event. **No conflict** because UNIQUE on `(channel_id, channel_event_id)` ensures the events are distinct rows; they happen to share a turn number, which is conceptually correct ("the same turn 5"). Subscribers see two TurnBoundary events with `turn_number=5`; this is a recovery anomaly, but no invariant is violated.

To avoid this surprise, the schema can add a stronger constraint:

```sql
CREATE UNIQUE INDEX event_log_unique_turn_per_channel
    ON event_log(reality_id, channel_id, turn_number)
    WHERE event_type = 'turn_boundary';
```

This makes the second TurnBoundary insert fail with a UNIQUE violation — N2's allocator detects, retries with `turn_number=6`. Acceptable cost: one DB constraint check per advance.

---

## DP-Ch23 — Capability gating

### JWT claim

Capability tokens (per [DP-K9](04d_capability_and_lifecycle.md#dp-k9--capability-tokens)) gain a new field in the `capabilities` array:

```json
{
  "aggregate": "...",
  "tiers": ["..."],
  "read": true,
  "write": true,
  "can_advance_turn": ["cell", "tavern"]   // list of channel level_names this service may advance
}
```

`can_advance_turn` is a list of `level_name` strings. The service may call `advance_turn` only on channels whose `level_name` matches one of the listed values. If absent or empty, the service cannot advance any turn.

### SDK enforcement

```rust
pub async fn advance_turn(...) -> Result<TurnAck, DpError> {
    // ... existing capability check (reality match, etc.) ...

    let channel_meta = self.channel_tree.get(channel)?;
    let allowed_levels = ctx.capability().claims.can_advance_turn();

    if !allowed_levels.contains(&channel_meta.level_name) {
        return Err(DpError::CapabilityDenied {
            aggregate: "advance_turn",
            tier: Tier::T3,  // turn boundary effectively T3 (durable, sync)
        });
    }

    // ... proceed with writer-side handle_advance_turn ...
}
```

### Typical capability assignments (feature-level guidance, not DP-locked)

| Service | Likely `can_advance_turn` |
|---|---|
| Game-rules engine (cell turn arbitration) | `["cell"]` |
| Narrative GM service | `["tavern", "town"]` |
| World-tick service (rare narrative beats at higher levels) | `["country", "continent"]` |
| Player-facing chat service | `[]` (no turn advance authority) |
| LLM roleplay-service (Python) | `[]` (proposes events via bus, never advances directly per [DP-A6](02_invariants.md#dp-a6--python-is-event-producer-only-for-game-state)) |

Concrete assignments are made at service-deploy time via the CP `tier_capability` table extension — not part of this design doc.

---

## DP-Ch24 — Composition with other Phase 4 items

### Pause ([Q19](99_open_questions.md))

When a channel is paused (Q19 territory), `advance_turn` is rejected with the same error as any other write — `DpError::ChannelPaused`. The channel's `last_turn_number` is unchanged during pause. Resume restores normal operation; the next `advance_turn` increments from the pre-pause value.

Pause and turn boundary are **orthogonal**: pause stops all writes including turn advances; resume continues. DP does not auto-emit a TurnBoundary on pause/resume — that is feature-level (a feature may decide that resuming should advance the turn, but DP doesn't bake it in).

### Bubble-up ([Q27](99_open_questions.md))

The bubble-up aggregator running on a parent channel's writer can observe TurnBoundary events from descendant cells via [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api). Common patterns the aggregator might implement (feature-level, not DP-locked):

- **Aggregate within a turn:** between two consecutive TurnBoundary events on cell C, aggregator collects events; on the second TurnBoundary, runs threshold check; emits parent event if threshold met.
- **Trigger on turn count:** every N turns at cell level, emit a tavern event ("the conversation has been going on for a while").
- **Causal cite:** parent event's `causal_refs` includes the descendant's TurnBoundary as the trigger.

Q27 will specify the aggregator's RNG-seeded threshold logic; this file just establishes that turn boundaries are observable inputs.

### Move session ([DP-Ch9](12_channel_primitives.md#dp-ch9--moving-a-session-to-a-different-channel))

A session moving from cell A (turn 5) to cell B (turn 12) doesn't affect either channel's turn counter. The session's local view of "current turn" jumps from cell-A.turn=5 to cell-B.turn=12 — feature/UX presents this naturally as "you moved to a new conversation that has been going on for a while."

### Channel dissolution ([DP-Ch1 lifecycle](12_channel_primitives.md#dp-ch1--channelid-and-tree-structure))

When a channel is dissolved, its `last_turn_number` is preserved in `channel_writer_state` (or reflected in archived event log). Re-creating a channel with the same purpose creates a new `ChannelId` with `last_turn_number = 0`; turn counters are not inherited.

### Reality-scoped events

RealityScoped events (player inventory change, currency mutation) are **not** tagged with turn_number — they are not part of any channel's timeline. Their ordering follows the existing per-aggregate / per-session R7 model. Features that want to correlate a RealityScoped change with a channel's turn boundary do so by including a reference (e.g., the channel_id + turn_number at write time) in the event payload — DP does not auto-correlate.

### Turn 0 semantics

A channel that never calls `advance_turn` has all its events at `turn_number = 0`. Feature code reading the stream sees `turn_number: 0` and may interpret that as "this channel doesn't use turn semantics." Alternatively the feature may emit an initial `advance_turn` to put the channel at `turn_number = 1` from the start — DP doesn't enforce either choice.

The first call to `advance_turn` increments from 0 to 1; the TurnBoundary event itself is tagged with `turn_number = 1` (the new value), not 0 (the old value). Subsequent events until the next advance carry `turn_number = 1`.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch21 | `TurnBoundary` event shape + `advance_turn(ctx, channel, turn_data, causal_refs)` SDK primitive; transparent routing to writer; uniform stream delivery; non-blocking on subscribers |
| DP-Ch22 | `event_log.turn_number BIGINT` column + `channel_writer_state.last_turn_number` extension; writer allocation algorithm with `MAX(turn_number)` reseed on takeover; optional UNIQUE index to prevent failover-race duplicate turn numbers |
| DP-Ch23 | JWT claim `can_advance_turn: Vec<level_name>` gates the primitive; SDK enforcement; concrete assignments at service-deploy time (not DP-locked) |
| DP-Ch24 | Composition: pause rejects advance; bubble-up observes turn boundaries as inputs; move-session doesn't affect counters; dissolution preserves; reality-scoped events don't get turn_number; turn 0 is "never advanced" sentinel |

---

## Cross-references

- [DP-A17](02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25) — invariant axiom this file implements
- [DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) — `channel_event_id` ordering that turn boundaries occupy positions in
- [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) — single-writer guarantees gapless turn allocation
- [DP-K9](04d_capability_and_lifecycle.md#dp-k9--capability-tokens) — capability JWT shape that DP-Ch23 extends
- [DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) — `event_log` schema this file extends
- [DP-Ch13](13_channel_ordering_and_writer.md#dp-ch13--writer-handoff--epoch-fencing-protocol) — `channel_writer_state` table this file extends
- [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api) — `ChannelEvent` trait + durable subscribe that delivers TurnBoundary events
- [DP-Ch15](13_channel_ordering_and_writer.md#dp-ch15--causal-references-for-bubble-up-preview-full-design--q27) — `causal_refs` carried by TurnBoundary

---

## What this leaves to other Phase 4 items

| Q | Phase 4 progress |
|---|---|
| **Q27 bubble-up primitive** | TurnBoundary events are now observable inputs for the aggregator; bubble-up's RNG-threshold logic + aggregator state machine = Q27 |
| **Q19 channel pause** | Composition described; concrete `channel_pause` primitive + reason payload + write-rejection details = Q19 |
| **Q15** | ✅ Resolved here. |
