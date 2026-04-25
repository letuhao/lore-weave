# 14 — Durable Per-Channel Event Subscribe (DP-Ch16..DP-Ch20)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q16](99_open_questions.md) — durable per-channel subscribe with resume token.
> **Stable IDs:** DP-Ch16..DP-Ch20.

---

## Reading this file

Phase 1-3 had `subscribe_invalidation` (cache coherency) and `subscribe_broadcast` (T1 fan-out) — both fire-and-forget on Redis pub/sub. Adequate for invalidation (idempotent) and best-effort broadcast (T1 tolerates loss). **Inadequate** for the event-linear game model: if a player disconnects 30 s and reconnects, missed channel events are the missed *story*, not just stale cache.

This file specifies the **durable** subscribe primitive — events are persisted, replayable, and can be resumed from any point in the channel's history within retention. The two earlier subscribe APIs remain for their original purposes; this is a **third subscribe primitive**, not a replacement.

Consumers: human players via gateway/WebSocket fan-out, internal services that need to react to channel events (the bubble-up aggregator from [Q27](99_open_questions.md), turn-boundary watchers from [Q15](99_open_questions.md), feature-level analytics).

---

## DP-Ch16 — `DurableEventStream` API

### Primitive: per-channel durable subscribe

```rust
/// Subscribe to a channel's event stream from a specific point. Returns a
/// stream that yields events in per-channel total order (DP-A15).
///
/// `from_event_id` = 0 means "from the beginning of retention". Pass the last
/// successfully-processed `channel_event_id` to resume.
///
/// Stream type `S` is a feature-defined deserialized shape; SDK returns a
/// typed enum `ChannelEvent<S>` carrying metadata + the deserialized payload.
pub async fn subscribe_channel_events_durable<S: ChannelEvent>(
    ctx: &SessionContext,
    channel: &ChannelId,
    from_event_id: u64,
) -> Result<DurableEventStream<S>, DpError>;
```

`ChannelEvent` is a trait implemented by feature-side event types. The SDK provides a tagged-enum decoder for the union of known event categories:

```rust
pub trait ChannelEvent: serde::Serialize + serde::DeserializeOwned + Send + 'static {
    const EVENT_TYPE: &'static str;     // discriminator for serialized payload
}

/// Concrete shape yielded by the stream — metadata always present, payload
/// deserialized into `S` when discriminator matches.
pub enum DurableStreamItem<S: ChannelEvent> {
    Event {
        channel_event_id: u64,
        writer_epoch: u64,
        causal_refs: Vec<EventRef>,
        payload: S,
        timestamp: Timestamp,
    },
    Heartbeat { last_event_id: u64 },    // emitted every 30s on idle channels
    StreamEnd { reason: StreamEndReason }, // graceful close
}
```

Heartbeats let consumers know "no events since N, stream is alive" — important for clients to distinguish "quiet channel" from "lost connection".

### Lifetime + cancellation

`DurableEventStream<S>` is a Rust async stream. Dropping it cancels the gRPC server-streaming RPC and releases the consumer slot. Cancellation is **idempotent**; the SDK handles in-flight events as best-effort cleanup.

### Visibility check

At subscribe time, SDK verifies:
- Caller's `SessionContext` includes `channel` in `ancestor_channels` **OR** caller has explicit observer capability for the channel.
- Capability JWT includes read permission for ChannelScoped events on this channel.

Mismatch → `DpError::CapabilityDenied`.

---

## DP-Ch17 — Hybrid backing store

### Two backing stores, one logical stream

| Tier | Store | Retention | Latency | Purpose |
|---|---|---|---|---|
| Live tail | **Redis Streams** `dp:events:{reality_id}:{channel_id}` | 7 days or 1M entries | ≤50 ms publish-to-deliver | Default subscribe path |
| Historical | **Postgres `event_log` table** | per [02_storage R1](../02_storage/R01_event_volume.md) (years) | Query latency, ~ms per page | Catch-up when resume token > Redis retention |

Both are populated by the channel's writer ([DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25)) on every channel event commit:

```text
1. Writer commits event to event_log (DB tx) -- canonical.
2. Same tx (or outbox per 02_storage R6) appends to Redis Stream
   dp:events:{reality}:{channel} with channel_event_id as the stream entry id.
3. On Redis-write failure, writer retries via outbox; live tail subscribers
   may see slight delay but never miss events (stream is best-effort live;
   DB is canonical).
```

### Stream entry shape (Redis Streams)

```
Stream:  dp:events:{reality_id}:{channel_id}
Entry id: {channel_event_id}-0   (uses channel_event_id as the major component
                                  so XRANGE / XREAD with explicit IDs work)
Fields:
  v             schema version
  writer_epoch  uint64
  causal_refs   JSON array
  event_type    string
  payload       MessagePack-encoded
  timestamp     unix-ms
```

Postgres `event_log` carries the same data verbatim (canonical) per the schema extension in [DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism).

### Retention sizing

- Per channel: 1M entries × ~1 KB serialized = ~1 GB — well-bounded.
- Per reality at peak (1000 active channels): ~1 TB Redis if all hit retention. Realistic = far less; cell channels churn rapidly and dissolve, only persistent (tavern+) channels accumulate.
- Eviction: Redis Streams `MAXLEN ~7000000` approximate trim on each append (cheap).

### What if Redis Streams data is lost (incident)?

Per [DP-F4 cache failure](07_failure_and_recovery.md#dp-f4--cache-layer-failure):
- Live subscribers see `StreamEnd { reason: BackingFailover }`.
- Subscribers reconnect with their last `channel_event_id`; SDK falls back to Postgres `event_log` query (see DP-Ch18 catch-up).
- Once Redis Streams recover, SDK switches back to live tail.

---

## DP-Ch18 — Resume token semantics + catchup→live transition

### Resume token = `channel_event_id`

Client-side cursor only. SDK is stateless w.r.t. subscriptions. Client tracks the last-successfully-processed `channel_event_id` per channel; passes it on reconnect.

```rust
// Pseudocode in feature/client code:
let mut last_seen: u64 = persistent_storage.get_last_seen(channel_id).unwrap_or(0);
let mut stream = dp.subscribe_channel_events_durable::<MyEvent>(ctx, channel, last_seen).await?;
while let Some(item) = stream.next().await {
    match item? {
        DurableStreamItem::Event { channel_event_id, payload, .. } => {
            handle(payload).await;
            last_seen = channel_event_id;
            persistent_storage.set_last_seen(channel_id, last_seen).await;
        }
        DurableStreamItem::Heartbeat { last_event_id } => {
            // optional: persist heartbeat as resume baseline
            last_seen = last_seen.max(last_event_id);
        }
        DurableStreamItem::StreamEnd { reason } => break,
    }
}
```

### Monotonicity contract

For any successful stream:
- Events delivered in strictly increasing `channel_event_id` order.
- No duplicates (same `channel_event_id` never delivered twice).
- No gaps within a connected stream session — if event N is delivered, event N+1 is delivered next, OR `StreamEnd` is delivered.
- After reconnect, client may see events ≥ resume token. If client passed `from = N`, first delivered event has `channel_event_id ≥ N+1` (note: client's resume token is the last *processed*, so the first event delivered is N+1).

If retention loss makes a gap unavoidable (resume token < oldest available), SDK returns `DpError::ResumeTokenExpired { earliest: u64 }` rather than silently delivering with a gap. Client must decide: skip-ahead, abort, or escalate.

### Catchup → live transition algorithm

When `from_event_id = N` and Redis Stream contains entries from `M..max` where `N < M` (i.e., resume point is older than Redis retention):

```text
1. SDK opens DB query:
     SELECT * FROM event_log
     WHERE reality_id = $1 AND channel_id = $2 AND channel_event_id > N
     ORDER BY channel_event_id ASC
     LIMIT 1000  -- page size
2. SDK simultaneously opens Redis Stream subscription (XREAD BLOCK ...)
   from the current Redis stream cursor (position M).
3. Buffer Redis stream events while DB query iterates.
4. Deliver DB-paged events to consumer in order until DB exhausted.
5. At DB-page end, check: did DB return events with channel_event_id >= M?
     - If yes: switch to delivering from buffered Redis events that were NOT
       already returned by DB (deduplicate by channel_event_id).
     - If no: continue paging DB until catch-up reaches M.
6. After Redis cursor reaches "live tail" (no buffered backlog), stream is in
   pure live mode.
```

**Idempotency:** events appearing in both DB and Redis Stream are detected by `channel_event_id` and not delivered twice. The merge is monotonic and gap-free.

**Latency cost:** during catchup, delivery rate is dominated by DB query throughput. Acceptable: catch-up of 10 k events from a stale resume token completes in seconds; turn-based gameplay tolerates a brief "loading recent events" UX.

**Resume token = 0** is treated as "from earliest available". For a freshly-created channel with no events, returns empty + heartbeat. For an old channel with events outside retention, may return `ResumeTokenExpired { earliest }` if "earliest" > 0 — client picks whether to start from `earliest` or fail.

---

## DP-Ch19 — Multi-channel batch subscribe convenience

### Use case

A player typically wants events from their **current cell + every ancestor**: cell, tavern, town, district, country, continent. That is up to 6 streams, each with its own resume token.

### Convenience API

```rust
/// Auto-subscribes to current_channel + all ancestors of the session.
/// Returns a multiplexed stream yielding events from any channel in the chain.
/// Each event carries its own channel_id so the consumer can dispatch.
pub async fn subscribe_session_channels<S: ChannelEvent>(
    ctx: &SessionContext,
    from_tokens: HashMap<ChannelId, u64>,  // resume token per channel
) -> Result<MultiplexedDurableStream<S>, DpError>;

pub enum MultiplexedItem<S: ChannelEvent> {
    Event {
        channel_id: ChannelId,
        channel_event_id: u64,
        writer_epoch: u64,
        causal_refs: Vec<EventRef>,
        payload: S,
        timestamp: Timestamp,
    },
    Heartbeat { channel_id: ChannelId, last_event_id: u64 },
    ChannelEnd { channel_id: ChannelId, reason: StreamEndReason },
}
```

### Implementation

The convenience API is a thin SDK-side wrapper:

```text
1. SDK enumerates ctx.ancestor_chain() = [cell, tavern, town, ...]
2. For each channel, opens an underlying subscribe_channel_events_durable
   stream with the matching from_tokens entry (or 0 if absent).
3. SDK tokio::select!s over all sub-streams, yielding to the consumer with
   channel_id annotated.
4. Consumer sees a single Stream<MultiplexedItem<S>> as a unified timeline.
```

### Ordering guarantees

- **Per-channel ordering preserved** — events from channel C arrive in `channel_event_id` order on the multiplexed stream.
- **Cross-channel ordering NOT guaranteed** — events from channel A and channel B can interleave arbitrarily based on arrival order.

Consumers that need cross-channel timeline (rare) must merge by `timestamp` or implement their own ordering policy. Most game UIs render per-channel timelines (e.g., separate chat tabs per ancestor), so cross-channel order is not needed.

### Subscription churn on `move_session_to_channel`

When the session changes channels ([DP-Ch9](12_channel_primitives.md#dp-ch9--moving-a-session-to-a-different-channel)):

- The new SessionContext has a new `ancestor_chain`.
- Old multiplexed stream emits `ChannelEnd { reason: AncestorChainChanged }` for channels no longer in the new chain.
- Caller needs to issue `subscribe_session_channels` with the new context (the SDK does NOT auto-re-subscribe — it would silently change the stream identity, which is bug-prone). Convenience helper `resubscribe_for_new_context` simplifies the pattern:

```rust
let new_ctx = dp.move_session_to_channel(&ctx, target).await?;
let new_stream = stream.resubscribe_for_new_context(&new_ctx, last_seen_per_channel).await?;
```

---

## DP-Ch20 — Backpressure + disconnect / reconnect

### Backpressure: TCP-level + 60s stall threshold

The gRPC server-streaming RPC is the natural backpressure boundary:

- Server (CP / writer-node SDK serving the stream) pushes events as fast as it can; client's gRPC read rate gates the server.
- Server's send buffer is bounded (~1 MB per stream); when full, server suspends pulling from the upstream Redis Stream / DB query.
- If client doesn't drain for **60 s consecutively** (no reads, buffer remains full), server emits `StreamEnd { reason: ConsumerStalled }` and closes the gRPC stream.
- Client reconnect: new stream with the last-successfully-processed token. No data loss; consumer just re-paid for the catchup.

### Disconnect detection

Two signals:
- **Client-side:** gRPC stream's underlying TCP RST or graceful close → SDK's stream returns `DurableStreamItem::StreamEnd { reason: NetworkError }`.
- **Server-side:** TCP keepalive miss → server closes server-side stream state.

### Reconnect protocol

Reconnect is just "subscribe again with the last token". The SDK does not auto-reconnect — explicit, so the consumer can decide retry policy. A typical feature wrapper:

```rust
let mut last_seen = persistent_storage.get_last_seen(channel).unwrap_or(0);
loop {
    let mut stream = match dp.subscribe_channel_events_durable::<MyEvent>(ctx, channel, last_seen).await {
        Ok(s) => s,
        Err(DpError::ResumeTokenExpired { earliest }) => {
            log::warn!("resume token {} expired, starting from {}", last_seen, earliest);
            last_seen = earliest;
            continue;
        }
        Err(e) => return Err(e),
    };
    while let Some(item) = stream.next().await {
        match item? {
            DurableStreamItem::Event { channel_event_id, payload, .. } => {
                handle(payload).await?;
                last_seen = channel_event_id;
                persistent_storage.set_last_seen(channel, last_seen).await?;
            }
            DurableStreamItem::Heartbeat { .. } => {}
            DurableStreamItem::StreamEnd { reason } => {
                if reason.is_retryable() { break } else { return Err(...) }
            }
        }
    }
    // Brief backoff before reconnect
    tokio::time::sleep(Duration::from_millis(500)).await;
}
```

### `StreamEndReason` taxonomy

```rust
pub enum StreamEndReason {
    /// gRPC server initiated close (planned drain, etc.). Retryable.
    ServerInitiated { detail: String },
    /// Consumer stalled >60s. Retryable after consumer drains.
    ConsumerStalled,
    /// Network error or peer reset. Retryable.
    NetworkError,
    /// Channel dissolved while subscribed (DP-Ch10). NOT retryable on this channel.
    ChannelDissolved,
    /// Backing-store failover (Redis Streams lost). Retryable; SDK may fall back to DB-only.
    BackingFailover,
    /// Caller's session moved away from this channel (multiplex case).
    /// NOT retryable on this channel; resubscribe with new SessionContext.
    AncestorChainChanged,
    /// Capability expired or revoked. Retryable after capability refresh.
    CapabilityRevoked,
}

impl StreamEndReason {
    pub fn is_retryable(&self) -> bool { /* obvious mapping */ }
}
```

### Idle channel behavior

A channel with no recent events (turn-based pacing, idle tavern at 3am in-game-time) doesn't burn server resources:

- Server emits `Heartbeat { last_event_id }` every 30 s during idle.
- Client uses heartbeats as keepalive proof (channel + connection both healthy).
- If 90 s elapse without any event or heartbeat, client treats stream as broken and reconnects.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch16 | `subscribe_channel_events_durable<S: ChannelEvent>` primitive returning `DurableEventStream<S>` of `DurableStreamItem` (Event / Heartbeat / StreamEnd); visibility check via session capability + ancestor chain |
| DP-Ch17 | Hybrid backing: Redis Streams `dp:events:{reality}:{channel}` for live tail (7-day or 1M-entry retention) + Postgres `event_log` for historical catchup; populated by channel writer in same tx as commit; outbox-resilient |
| DP-Ch18 | Resume token = `channel_event_id`, client-side cursor; monotonic delivery, no duplicates, no gaps within a connected stream; explicit `ResumeTokenExpired` error rather than silent gap; catchup → live transition via parallel DB-page + Redis-stream merge with `channel_event_id` deduplication |
| DP-Ch19 | `subscribe_session_channels` convenience for ancestor-chain auto-multiplex; per-channel ordering preserved, cross-channel arbitrary; `resubscribe_for_new_context` helper on `move_session_to_channel`; `ChannelEnd { AncestorChainChanged }` on session move |
| DP-Ch20 | TCP-level backpressure + 60s stall threshold; client-driven explicit reconnect; idle-channel heartbeat every 30s; `StreamEndReason` taxonomy distinguishing retryable vs non-retryable terminations |

---

## Cross-references

- [DP-A4](02_invariants.md#dp-a4--redis-is-the-cache-technology) — Redis usage extended: cache + pub/sub + **Streams** (this file)
- [DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) — total-ordering invariant that resume tokens encode
- [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) — single-writer-per-channel publishes to both Redis Stream + Postgres in same tx
- [DP-K6](04_kernel_api_contract.md#dp-k6--subscription-primitives) — extended with `subscribe_channel_events_durable` + `subscribe_session_channels`
- [DP-Ch10](12_channel_primitives.md#dp-ch10--channel-tree-change-invalidation) — `ChannelDissolved` `StreamEndReason` plugs into channel-tree-change handling
- [DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) — `event_log` schema this file consumes
- [DP-Ch15](13_channel_ordering_and_writer.md#dp-ch15--causal-references-for-bubble-up-preview-full-design--q27) — `causal_refs` carried in stream items, foundation for Q27 bubble-up
- [DP-X2](06_cache_coherency.md#dp-x2--invalidation-message-protocol) — invalidation pub/sub remains separate; **this file does NOT replace `subscribe_invalidation`**
- [DP-F4](07_failure_and_recovery.md#dp-f4--cache-layer-failure) — Redis Streams failover behavior plugs into existing cache-failure semantics

---

## What this leaves to other Phase 4 items

| Q | Phase 4 progress |
|---|---|
| **Q15 turn boundary** | Foundation in place: turn boundary = a `ChannelEvent` impl with discriminator `"turn_boundary"`, occupying a specific `channel_event_id`. Subscribers see it via this stream. Concrete event shape + advance protocol = Q15. |
| **Q27 bubble-up** | Foundation in place: aggregator at parent channel uses `subscribe_channel_events_durable` over each descendant cell, consumes events, emits parent events via writer (DP-A16). Aggregator state persistence + RNG-based threshold = Q27. |
| **Q19 channel pause** | Subscribers can be informed via `Heartbeat` + a "paused" flag; or via a special `ChannelEvent` type. Detail = Q19. |
| **Q31 channel lifecycle** | `ChannelDissolved` `StreamEndReason` hooks in already; full lifecycle Q31. |
| **Q16** | ✅ Resolved here. |
