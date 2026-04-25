# 13 — Channel Ordering and Writer Binding (DP-Ch11..DP-Ch15)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q17 + Q30 + Q34](99_open_questions.md). Implements [DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) (per-channel total ordering) and [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) (writer-node binding).
> **Stable IDs:** DP-Ch11..DP-Ch15.

---

## Reading this file

This file specifies the **mechanism** behind two axioms locked in 02_invariants:

- DP-A15 says "channels have total order"; DP-Ch11 specifies how the `channel_event_id` is allocated and the event log is shaped.
- DP-A16 says "channels have a single writer"; DP-Ch12 specifies assignment rules, DP-Ch13 specifies handoff protocol, DP-Ch14 specifies cross-node write routing, DP-Ch15 sketches the causal-reference shape that the bubble-up aggregator (Q27) will consume.

The mechanisms here build on [12_channel_primitives.md](12_channel_primitives.md) (channel identity, registry, scope traits) and extend the event-log model from [02_storage R7](../02_storage/R07_concurrency_cross_session.md) with channel scope.

---

## DP-Ch11 — `channel_event_id` allocation mechanism

### Event log schema extension

The per-reality `event_log` table (existing per [02_storage 00](../02_storage/00_overview_and_schema.md)) gains channel-aware columns:

```sql
ALTER TABLE event_log
    ADD COLUMN channel_id          UUID,            -- NULL = reality-scoped event
    ADD COLUMN channel_event_id    BIGINT,          -- NULL = reality-scoped event
    ADD COLUMN writer_epoch        BIGINT,          -- monotonic per channel; for fence
    ADD COLUMN causal_refs         JSONB DEFAULT '[]'::jsonb,  -- see DP-Ch15
    ADD COLUMN turn_number         BIGINT NOT NULL DEFAULT 0;   -- per-channel turn counter (DP-A17 / DP-Ch22)

-- Channel-scoped events have a strict total order per channel:
ALTER TABLE event_log
    ADD CONSTRAINT event_log_channel_order
        UNIQUE (reality_id, channel_id, channel_event_id)
        WHERE channel_id IS NOT NULL;

CREATE INDEX event_log_channel_order_idx
    ON event_log(reality_id, channel_id, channel_event_id ASC)
    WHERE channel_id IS NOT NULL;
```

Reality-scoped events leave `channel_id` and `channel_event_id` as `NULL` and rely on existing per-aggregate ordering (R7).

### Allocation algorithm (single-writer, by DP-A16)

The writer node holds an in-memory map per active channel:

```rust
struct ChannelWriterState {
    channel_id: ChannelId,
    last_event_id: u64,         // last allocated channel_event_id
    epoch: u64,                 // CP-issued, fence token
    in_flight: Vec<EventId>,    // pending DB commits, for crash recovery
}
```

**On writer takeover** (initial assignment or post-failover):

1. CP grants writer lease: `(channel_id, epoch)` pair signed by CP.
2. Writer queries `SELECT MAX(channel_event_id) FROM event_log WHERE reality_id = $1 AND channel_id = $2` → seeds `last_event_id`.
3. Writer ready to accept writes; subsequent allocation increments in-memory.

**On each write:**

```text
1. allocated_id = self.last_event_id + 1
2. Insert into event_log: (reality_id, channel_id, allocated_id, writer_epoch, ...)
3. Commit transaction
4. On commit success: self.last_event_id = allocated_id
5. On commit failure (UNIQUE violation — rare race during failover overlap):
     log security event
     re-query MAX(channel_event_id), reseed self.last_event_id
     retry once
6. On commit failure for other reasons: bubble up DpError to caller
```

**Failure modes:**

- **Writer dies mid-flight** — uncommitted writes are lost (acceptable; client did not receive ack). New writer's `MAX` query skips them.
- **Network partition** — old writer continues attempting writes; CP has assigned new writer with `epoch+1`; old writer's commits with stale epoch rejected by Postgres trigger or app-level epoch check (DP-Ch12).
- **Postgres replica lag** — irrelevant for this allocation; writes go to primary (per [DP-X10](06_cache_coherency.md#dp-x10--failure-modes--fail-safe)).

### Reality-scoped events — unchanged

Reality-scoped events do not use this scheme. They retain whatever ordering [02_storage R7](../02_storage/R07_concurrency_cross_session.md) provides per aggregate / per session.

---

## DP-Ch12 — Writer assignment rules

### Cell channels

**Default writer:** the node hosting the session that **created** the cell.

```text
1. Player A's session on node N1 calls DpClient::create_channel(parent: tavern_X, level_name: "cell")
2. SDK on N1 writes channels row + emits channel_tree_change.
3. CP receives delta, assigns writer = N1 by default for the new cell.
4. CP issues writer lease (channel_id, epoch=1) to N1.
5. Subsequent writes to this cell from any session route to N1 (DP-Ch14).
```

**Multi-creator caveat:** two players cannot simultaneously create the same cell — `create_channel` has its own concurrency story (CP issues channel_id; first commit wins). The cell's writer is always the creator's node, deterministic.

### Cell handoff (creator leaves)

If the creator's session leaves the cell while other sessions remain:

```text
1. Creator's session calls move_session_to_channel(target = some other channel)
2. SDK detects creator was the cell's writer; signals CP "writer-vacating-cell".
3. CP picks new writer from active sessions in cell:
     priority order: longest-active session in cell > random
4. CP increments epoch (epoch+1), issues new lease to new writer's node.
5. Old node N1 receives channel-tree-update push: "you are no longer writer of cell C".
6. New writer's SDK queries MAX(channel_event_id) and is ready.
7. CP pushes channel-tree-update to all SDKs subscribing to cell C: writer = new node.
8. SDKs invalidate their cached writer route for cell C.
```

**Total handoff latency p99:** ≤ 200 ms (CP picks + epoch issue + push + new writer ready). Writes during this window get `WrongChannelWriter`; SDK retries once after re-fetching writer; transient.

**Edge: creator was the only session in cell** — cell goes dormant (per [DP-Ch1 lifecycle](12_channel_primitives.md#dp-ch1--channelid-and-tree-structure)). No writer needed until a new session joins; CP assigns writer at next join.

### Non-cell channels (tavern, town, district, country, continent, ...)

**Assignment at channel creation:**

```text
1. Channel created (e.g., tavern Y under town X).
2. CP picks writer using load-balancing: least-loaded game-node currently hosting any session in this reality.
3. CP issues lease (channel_id, epoch=1) to chosen node.
4. Writer is **persistent** — does not move on session changes; only on node death.
```

**Reassignment (involuntary, node death):**

```text
1. CP detects node death via health probe (≤30s, per DP-F2).
2. CP enumerates channels writer-bound to dead node.
3. For each: increment epoch, pick replacement node, issue new lease.
4. Push channel-tree-updates to all SDKs.
5. Total reassignment time: ≤35s end-to-end during which writes return WrongChannelWriter.
```

**No voluntary handoff for non-cell channels.** A non-cell writer node going through graceful drain ([DP-F9](07_failure_and_recovery.md#dp-f9--graceful-drain--quiescence)) triggers reassignment as part of drain.

---

## DP-Ch13 — Writer handoff + epoch fencing protocol

### Epoch fence

Every channel has a **monotonic epoch** that increments on every writer assignment / reassignment. Writes carry the epoch they believe is current; Postgres or app-level check rejects writes with a stale epoch.

**App-level check (recommended for V1/V2):**

```rust
// Inside SDK's t2_write_channel / t3_write_channel:
let cached_lease = self.writer_lease(channel_id);
let cached_epoch = cached_lease.epoch;

let result = pg_tx
    .execute("INSERT INTO event_log (..., writer_epoch, ...) VALUES (..., $epoch, ...)
              WHERE NOT EXISTS (
                  SELECT 1 FROM channel_writer_state
                  WHERE channel_id = $cid AND current_epoch > $epoch
              )")
    .await?;

if result.rows_affected() == 0 {
    return Err(DpError::WrongChannelWriter { stale_epoch: cached_epoch });
}
```

**`channel_writer_state` table** (per-reality DB):

```sql
CREATE TABLE channel_writer_state (
    channel_id      UUID PRIMARY KEY REFERENCES channels(id),
    current_epoch   BIGINT NOT NULL,
    writer_node     TEXT NOT NULL,
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

CP updates this table on every reassignment. Writer node updates `last_heartbeat` periodically (every 10s); CP detects stale heartbeats as a secondary signal in addition to gRPC health probes.

**Phase 4 extensions to this table:**
- [DP-Ch22](#dp-ch22--schema-extensions-and-writer-allocation) added `last_turn_number BIGINT NOT NULL DEFAULT 0` for turn-number allocator state.
- [DP-Ch51](21_llm_turn_slot.md#dp-ch51--turn-slot-primitive) added `current_turn_actor JSONB`, `turn_started_at TIMESTAMPTZ`, `turn_expected_until TIMESTAMPTZ`, `turn_slot_reason TEXT` for the LLM turn slot hint.

All Phase 4 columns nullable; default to NULL = no slot held / no turn advanced. Together they let writer node serve `get_turn_slot` queries without scanning event log.

### Race scenarios + protocol behavior

| Scenario | Behavior |
|---|---|
| Old writer's network blips, CP reassigns, old writer recovers and tries to write | Write rejected by epoch check; SDK on old writer surfaces `WrongChannelWriter`; old writer queries CP, learns new writer, transparently routes the pending write |
| New writer takes over but hasn't queried `MAX(channel_event_id)` yet, attempts an allocation | Race window is tiny (~ms); but if it occurs, UNIQUE constraint on `(channel_id, channel_event_id)` rejects duplicate; new writer re-seeds and retries |
| Both old and new writer believe they have lease (CP partition) | Postgres serializes via `channel_writer_state.current_epoch` comparison; only one succeeds; the other gets `WrongChannelWriter` |
| Writer crashes mid-write | Transaction aborts; in-flight write lost (no ack); new writer's MAX query starts from last committed event_id; gap in client's perception (their request errored), no DB inconsistency |

### Handoff observability

Every writer assignment / reassignment / failover emits a structured event to a dedicated audit stream:

```
Stream:  dp:writer_audit:{reality_id}
Entry:   { channel_id, prev_writer, new_writer, prev_epoch, new_epoch, reason: "create"|"creator_left"|"node_death"|"drain"|"manual", at }
```

Used by CP for observability, by ops for incident review.

---

## DP-Ch14 — Cross-node write routing

### Routing decision

Every channel-scoped write goes through this dispatch:

```rust
async fn t2_write_channel<A: T2Aggregate + ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    id: A::Id,
    delta: A::Delta,
) -> Result<T2Ack, DpError> {
    let lease = self.writer_lease_cache.get(channel).await?;

    if lease.writer_node == self.local_node_id {
        // local fast path
        self.write_local::<A>(ctx, channel, id, delta, lease.epoch).await
    } else {
        // route to writer node via gRPC
        self.route_to_writer::<A>(ctx, channel, id, delta, &lease.writer_node).await
    }
}
```

### `route_to_writer` gRPC method

Each game node exposes a gRPC server endpoint `route_channel_write`:

```protobuf
service DpInternalRouting {
  rpc RouteChannelWrite (RouteChannelWriteRequest) returns (RouteChannelWriteResponse);
}

message RouteChannelWriteRequest {
  bytes serialized_session_context = 1;  // forwarded SessionContext
  string channel_id = 2;
  string aggregate_type = 3;
  bytes serialized_delta = 4;
  uint32 tier = 5;  // T2 or T3
}
```

**Authorization:** the receiving node verifies the forwarded `SessionContext` (capability JWT signature + reality match). The capability already encodes which aggregates the originating service may write — the routing node is just executing the write on its behalf.

**Latency:** ~5 ms LAN round-trip + the local write cost. T3 budget therefore ~50ms (Phase 1) + 5ms route ≈ 55ms p99 for cross-node T3. Slight breach of [DP-S3](08_scale_and_slos.md#dp-s3--per-tier-write-latency-targets-sdk-internal-p99); accepted because turn-based gameplay tolerates this.

### Writer route cache

SDK maintains `writer_lease_cache: HashMap<ChannelId, WriterLease>` with:

- **TTL:** 60 seconds, refreshed on use.
- **Invalidation:** on channel-tree-update event from CP indicating writer change.
- **Population:** on first access (CP query) + on bind_session (CP includes writer info for ancestor channels).

Cache miss = synchronous CP query (~5 ms LAN). Acceptable cost; happens once per channel per 60 s.

### Failure: writer unreachable

```rust
async fn route_to_writer(...) -> Result<_, DpError> {
    match grpc_client.route_channel_write(...).await {
        Ok(ack) => Ok(ack),
        Err(grpc_err) if is_unreachable(&grpc_err) => {
            // Likely writer just died. Trigger CP query.
            self.writer_lease_cache.invalidate(channel);
            let new_lease = self.cp_client.get_writer(channel).await?;
            // Retry once with new writer.
            grpc_client_for(&new_lease.writer_node)
                .route_channel_write(...).await
                .map_err(DpError::from)
        },
        Err(other) => Err(DpError::from(other)),
    }
}
```

One automatic retry on writer-unreachable; further failures bubble to caller as `DpError::CircuitOpen { service: "writer" }`.

---

## DP-Ch15 — Causal references for bubble-up (preview; full design in [16_bubble_up_aggregator.md](16_bubble_up_aggregator.md))

Channel events carry an optional `causal_refs` field linking back to source events (typically at child channels) that triggered them. This is the foundation that the Q27 bubble-up aggregator consumes.

### Schema

```rust
pub struct EventRef {
    pub channel_id: ChannelId,
    pub channel_event_id: u64,
}

// In the event metadata:
pub struct EventMetadata {
    // ... existing fields ...
    pub causal_refs: Vec<EventRef>,
}
```

Stored as `JSONB` in the event log per the schema extension in DP-Ch11.

### Usage pattern (Q27 territory, sketched here)

```text
1. Cell C has events e1, e2, e3, ... (channel_event_ids in C).
2. Tavern T's bubble-up aggregator (running on T's writer node) reads cell events from descendants.
3. After ≥N cell events accumulate within a window, aggregator's deterministic-RNG check fires.
   RNG seed = XOR of triggering event_ids (deterministic, replayable).
4. Aggregator emits tavern event T_e7 with causal_refs = [(C, 1), (C, 2), (C, 3)].
5. Subscribers at tavern level see T_e7; can drill down via causal_refs if UI wants to show "this tavern event was triggered by these cell happenings".
```

### Causal-ref invariants

- `causal_refs[i].channel_id` is always a **descendant** of the emitting event's channel (never sibling, never ancestor — would create circular causality).
- `causal_refs[i].channel_event_id` is always **less than current time** (in the descendant's per-channel order); aggregator does not reference future events.
- Empty `causal_refs` = primary event (player action, NPC turn) not derived from descendant events. Most events.
- Bubble-up cascading (cell → tavern → town) is supported: a tavern event can have causal_refs to cell events; a town event can have causal_refs to tavern events; the chain depth is bounded by tree depth (≤16).

### Replay semantics

Determinism is the goal: replaying the event log up to time T yields the same bubble-up events. Achieved by:

- Single-writer ordering ([DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25)) ensures aggregator sees descendants' events in deterministic order.
- RNG seed derived from triggering event_ids (not wall-clock).
- Aggregator state is itself event-sourced — its decisions are functions of its inputs.

Full aggregator spec, threshold tuning, and probabilistic-trigger details are [Q27](99_open_questions.md), not this file.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch11 | `channel_event_id` allocation: in-memory counter on writer, seeded from `MAX` query at takeover, gaplessness via DB UNIQUE constraint, retry-on-violation for rare failover races; reality-scoped events unaffected (NULL channel_id) |
| DP-Ch12 | Cell writer = creator's session node + handoff on creator-leave; non-cell writer = CP-assigned, persistent, only reassigned on node death |
| DP-Ch13 | Epoch fence: monotonic per channel, stored in `channel_writer_state` table, app-level check rejects writes with stale epoch; handoff audit stream `dp:writer_audit:{reality_id}` |
| DP-Ch14 | SDK transparent cross-node routing via gRPC `RouteChannelWrite`; writer lease cache 60s TTL + invalidation; one auto-retry on unreachable; ~5ms LAN hop cost |
| DP-Ch15 | `causal_refs: Vec<EventRef>` field on every channel event; descendant-only references, replay-deterministic; foundation for Q27 bubble-up aggregator |

---

## Cross-references

- [DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) — total ordering invariant this file implements
- [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) — writer binding axiom this file implements
- [DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes) — composes with DP-A16; T1 writer = session node, channel writer = channel-bound node, no conflict
- [12_channel_primitives.md](12_channel_primitives.md) — channel identity + registry foundation
- [02_storage R7](../02_storage/R07_concurrency_cross_session.md) — reality-scoped event ordering still applies for non-channel events
- [02_storage R6](../02_storage/R06_R12_publisher_reliability.md) — outbox publisher used for invalidation broadcasts that reference channel_event_id
- [04_kernel_api_contract.md](04_kernel_api_contract.md) — `WrongChannelWriter` `DpError` variant; transparent routing in write primitives
- [05_control_plane_spec.md](05_control_plane_spec.md) — CP writer assignment + handoff RPC additions

---

## What this leaves to other Phase 4 items

| Q | Phase 4 progress |
|---|---|
| **Q27 bubble-up primitive** | DP-Ch15 gives causal-ref shape + replay determinism; aggregator implementation, threshold tuning, RNG seed derivation = Q27 |
| **Q15 turn boundary** | Per-channel ordering gives `channel_event_id` positions for turn marks; concrete event shape + subscribe-completion rule = Q15 |
| **Q16 durable subscribe** | Resume token = `channel_event_id`; protocol + Postgres LISTEN vs Redis Stream choice = Q16 |
| **Q19 channel pause** | Pause = writer rejects new writes for the channel until resume; specific primitive (`channel_pause`) + reason payload = Q19 |
| **Q31 channel lifecycle** | Cell dormant transition partly covered (Ch12 creator-leaves-cell-with-no-others); full lifecycle + dissolution + archival = Q31 |
| **Q34** | ✅ Resolved here (DP-Ch12 + DP-Ch13 + DP-Ch14) |

Resolution order continues with Q15 + Q16 + Q27 (the remaining Phase 4 blockers) next.
