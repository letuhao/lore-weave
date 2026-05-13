# 03 — Tier Taxonomy (DP-T0..T3)

> **Status:** LOCKED. Four tiers, closed set. Adding a fifth tier requires a superseding decision recorded in [../decisions/](../decisions/) and supersedes [DP-A5](02_invariants.md#dp-a5--four-tier-persistence-taxonomy).
> **Stable IDs:** DP-T0, DP-T1, DP-T2, DP-T3. Referenceable from any doc.

---

## Why four tiers and no more

Every persistence tier beyond the first creates a new consistency model that feature designers, testers, and operators must hold in their heads. Four is the minimum number that separates the four distinct behaviors an MMO needs:

1. Something that is **purely transient** (no value after current interaction ends)
2. Something that **should persist but can tolerate short loss** (re-derivable or low-stakes)
3. Something that **must not be lost** but can be read stale for moments
4. Something that **must not be lost and must be read consistent with writes** (money, canon)

A fifth tier — "semi-durable between T1 and T2" or "strong consistency with relaxed read-your-writes" — introduces ambiguity at the boundary without serving a use case that T2 or T3 cannot cover. If a feature is on the boundary, it picks the safer tier (T2 over T1, T3 over T2).

---

## Tier matrix

| ID | Name | Crash loss | Persisted | Consistency | Write latency budget | Read latency budget | Typical examples |
|---|---|---|---|---|---|---|---|
| **DP-T0** | Ephemeral | All | Never | N/A (in-process only) | N/A (no wire write) | <1ms (in-process) | Typing indicator, cursor hover, UI hint visibility per session, transient presence flag |
| **DP-T1** | Volatile | ≤30s | Periodic snapshot to Redis | Single-writer, eventual on replica | <1ms write to local, <10ms to Redis | <10ms from Redis | Player position (live tick), active emote, combat tick ticks, chat-presence |
| **DP-T2** | Durable-async | None | Event log (async, via outbox) + cache write-through | Read-your-writes in-session, eventual cross-session | <5ms ack (cache + outbox), ≤1s until projected | <10ms cache, <50ms projection | Chat messages, most gameplay actions (move intent, NPC dialog line, skill use), non-canon state changes |
| **DP-T3** | Durable-sync | None | Event log (sync) + cache invalidation + projection wait | Strong — no acknowledge until projection reflects write | <50ms ack (includes DB commit + invalidate) | <10ms cache, <50ms projection | Currency mutations, item trades (both sides), canon promotion, permission grants, identity changes |

**Latency budgets above are the contract.** Missing them is a defect, not a tuning opportunity. See [08_scale_and_slos.md](08_scale_and_slos.md) for the wider SLO context.

---

## DP-T0 — Ephemeral

### Definition

In-process state with no durability and no wire-level replication. Lives entirely in the Rust service's memory for the duration of a session, connection, or request. Lost on any restart. Not visible to any other service, node, or process.

### Eligibility rule

A feature may use T0 only if **all three** are true:

1. Losing every instance of this data on a process restart causes no user-visible problem beyond "the UI hint re-appears the next time" or equivalent.
2. No other service, no other player, no future reader needs to see this data.
3. The data's lifetime is bounded by a single session or shorter.

Fail any of the three → not T0.

### Examples

- Typing indicator ("Player X is typing...")
- Cursor hover / mouse target state
- Per-connection UI hint seen/dismissed flags for current session only
- Transient presence "last heartbeat" timestamps within a single node's connection manager

### Non-examples (do not T0 these)

- Player position — T1 (other players need it; 30s loss tolerable)
- "Player seen tutorial" — T2 at minimum (persists across sessions)
- Any chat message — T2 minimum (visible to others, durable)

### Implementation

In-process data structure. No SDK call needed for writes (they are just memory writes). Reads may still go through the SDK for telemetry or for the typed API surface, but the SDK does not hit Redis or Postgres for T0. Cache key space is not used.

---

## DP-T1 — Volatile

### Definition

In-memory live state with periodic snapshot to Redis. A crash may lose up to the last snapshot interval (≤30 seconds). **Single-writer discipline:** the game node holding the player's session is the authoritative writer for all T1 aggregates owned by that session; NPC aggregates have their writer node tracked by the control plane. See [DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes) for the full binding and failover rule.

### Eligibility rule (revised Phase 4 for turn-based + channel model)

A feature may use T1 only if **all three** are true:

1. A 30-second data loss on node crash is acceptable (re-derivable from current play state, re-emitted on reconnect, or staleness tolerable until next durable update).
2. Data is **high-churn or explicitly transient** — frequent updates from session activity, OR ephemeral UI state that exists only during active play. (Phase 4: dropped the prior "≥1/s sustained" hard rule — it was a pre-channel-model assumption baked in MMO-realtime semantics; channel presence at lower update rates is still appropriate T1 if the data is transient.)
3. Data is per-aggregate, scoped to either reality (`RealityScoped`) or a specific channel (`ChannelScoped`) — not a global counter or cross-reality state.

### Examples (turn-based + channel model)

- **Channel presence** — "actors currently in cell C" — high churn on join/leave; the live set is T1, while canonical join/leave history is T2 via DP-Ch34 `MemberJoined`/`MemberLeft` events. The two are **complementary**: T1 answers "who's here now"; T2 answers "who joined when, why did they leave".
- **Typing indicator** — "actor X is composing in cell C" — high churn (start/stop), explicitly transient, low-stakes.
- **Hover / cursor / target state** — UI hints during active play; ephemeral by definition.
- **Active emote / animation state** — visible to other channel members during the current scene; resets on session end or scene boundary.
- **Idle-since timestamp** — recomputed on every action; staleness OK because it's a bounded re-derivation.

**Composition with scope traits ([DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25)):** T1 is orthogonal to scope. `T1Aggregate + RealityScoped` (e.g., player's session-wide presence flag) and `T1Aggregate + ChannelScoped` (e.g., presence-in-this-cell) are both valid. Most Phase 4 T1 use cases are channel-scoped because presence is naturally per-channel.

**Examples retired (kept here for migration audit):** ~~Player position 30Hz client update / 5Hz server broadcast~~ — turn-based has no continuous-position concept; positional changes are channel events. ~~Combat tick ticks~~ — combat is event-based per turn boundaries (DP-A17); no separate tick stream. ~~Chat-presence per session~~ — supplanted by channel presence (per cell, scoped via DP-A14 `ChannelScoped`).

### Snapshot cadence

Default: 10 seconds per aggregate or 1 second after the last change, whichever is later. Tunable per aggregate type by the control plane. Snapshots write to Redis with TTL; long-idle aggregates evict and reload from the last snapshot on re-activation.

### Broadcast

T1 aggregates that other players see (player position, emote) publish to a Redis pub/sub channel `dp:{reality_id}:t1:{aggregate_type}:broadcast` on each write. Subscribers (broadcast-service or WebSocket fan-out) consume these for real-time delivery.

### Implementation

SDK exposes `t1_write(reality_id, aggregate_type, aggregate_id, value)` (in-memory update + pub/sub publish) and `t1_snapshot_flush(reality_id, aggregate_type, aggregate_id)` (periodic, invoked by the runtime, not by feature code). Reads by other services go through `t1_read(reality_id, aggregate_type, aggregate_id)` which hits Redis.

### Recovery on crash

On node restart, T1 aggregates reload their last snapshot from Redis. Updates that occurred after the last snapshot are lost — this is the accepted 30s window. No event-log replay for T1.

---

## DP-T2 — Durable-async

### Definition

Write-through cache + async event log (via existing 02_storage outbox pattern). Writes ack once cache and outbox are updated (~5ms). Event log and projection catch up asynchronously (≤1s to projection visibility). Durable across crashes — no data loss. Read-your-writes consistency within the writing session; eventual consistency for other sessions.

### Eligibility rule

Default tier for non-canon, non-financial gameplay actions. Use T2 when:

1. Data must not be lost on crash.
2. Other players/services seeing the data 500ms–1s late is acceptable.
3. The write is not of a type where reading stale data produces a wrong outcome (e.g., not currency or item trade — those are T3).

Most gameplay lands here.

### Examples

- Chat messages (session and channel)
- Player action events (move intent, skill use, interaction start)
- NPC dialog lines (after LLM proposal is validated by Rust and applied via T2 write)
- Non-canon world state changes (weather shift, ambient event, NPC mood change)
- Session scoped memory writes into `npc_session_memory_projection`

### Write path

```
1. SDK.t2_write(reality_id, aggregate_type, aggregate_id, delta)
2. Cache: SET dp:{reality_id}:t2:{aggregate_type}:{aggregate_id} value EX <TTL>
3. Outbox: INSERT INTO outbox (reality_id, event) VALUES (...)
4. Ack to caller — all in one transaction, ~5ms
5. Async: outbox publisher reads outbox → appends to event log → updates projection
6. Invalidation: publish "dp:{reality_id}:inval:{aggregate_type}:{aggregate_id}" so other SDK instances' local caches invalidate
```

### Read path

```
1. SDK.t2_read(reality_id, aggregate_type, aggregate_id)
2. Try Redis cache → hit: return (≤10ms)
3. Miss → read projection (Postgres), populate cache, return (≤50ms)
```

### Consistency semantics

- **Writer session**: reads after its own writes see the write immediately (cache is updated before ack).
- **Other sessions on the same node**: see the write within cache-propagation time (same node, in-process invalidation is immediate).
- **Other sessions on other nodes**: see the write within pub/sub invalidation latency (≤100ms typical).
- **Cross-reality reads**: not permitted via T2 — use the cross-instance policy (R5) which goes through T3-equivalent paths.

### Implementation

Delegates write persistence to existing outbox mechanism in [02_storage/](../02_storage/); cache layer + invalidation broadcast is new in DP. Read cache populated lazily on miss and proactively by invalidation on miss-trigger.

---

## DP-T3 — Durable-sync

### Definition

Synchronous event log write + projection wait + cache invalidation before ack. Writes ack only after the projection reflects the new state, so any subsequent read on any session sees the new value. Strong consistency, no loss, highest latency.

### Eligibility rule

Use T3 only if **any** is true:

1. The write changes money, items, or anything with real-world value.
2. The write affects canon (promotes emergent state to canonical layer).
3. Reading the old value immediately after the write would produce a wrong business outcome (trade where the counterparty sees "you haven't paid yet" would lose the item).
4. The write is across entities whose atomicity matters (trade = debit A, credit B; both must be visible together).
5. Permission, identity, or security-critical state.

Default if in doubt → T3 (safer).

### Examples

- Currency debits/credits
- Item trades, transfers, drops (atomic across giver and receiver)
- Canon promotion events (writing to the canonical layer per [03_multiverse/](../03_multiverse/))
- Character creation finalization (after character is committed)
- Permission grants, revocations
- Identity binding (user ↔ PC)
- Any admin action that changes policy or data (per S13, SR5)

### Write path

```
1. SDK.t3_write(reality_id, aggregate_type, aggregate_id, delta, tx_context)
2. Begin transaction on per-reality Postgres
3. Append to event log (sync)
4. Update projection table (sync, in same txn)
5. Commit
6. Publish invalidation broadcast to Redis pub/sub
7. Wait for local cache invalidation to propagate (≤20ms)
8. Ack to caller (total: ≤50ms p99)
```

### Multi-aggregate atomicity

Trades and other cross-aggregate operations MUST use the atomic T3 API (`t3_write_multi`) which wraps all aggregate writes in a single Postgres transaction. No partial-state observable.

### Read path

After a T3 ack, reads on any node see the new value. Cache is populated (or invalidated, forcing repopulation) before ack returns.

### Consistency semantics

- **Writer session**: synchronous — read after write sees the write (obviously).
- **All other sessions everywhere**: reads after the writer's ack see the new value. Invalidation broadcast completes before ack.
- **Cross-reality**: T3 writes do not cross realities. Cross-reality coordination uses the existing R5 policy (which itself routes through T3 writes on each side).

### Implementation

Delegates to existing [02_storage/](../02_storage/) event log + projection mechanism; DP adds the synchronous projection wait, the invalidation broadcast, and the ack gating. Under load, T3 is more expensive than T2 — this is deliberate and correct.

---

## Tier-choice decision tree

For each aggregate a feature touches:

```
Is data lost on crash acceptable?
├── Yes, entirely (never persisted) → DP-T0
└── No
    ├── ≤30s loss acceptable AND write rate high (≥1/s)?
    │   └── Yes → DP-T1
    │   └── No  → continue
    ├── Is this money / item / canon / permission / cross-entity atomicity?
    │   └── Yes → DP-T3
    │   └── No  → DP-T2
```

When in doubt between adjacent tiers, pick the safer (higher) one. T2 over T1, T3 over T2. Moving down a tier later is easy; recovering lost data is not.

---

## Cross-references

- [02_invariants.md#dp-a5--four-tier-persistence-taxonomy](02_invariants.md) — the invariant locking this taxonomy.
- [08_scale_and_slos.md](08_scale_and_slos.md) — throughput and latency targets per tier, at scale.
- [02_storage/00_overview_and_schema.md](../02_storage/00_overview_and_schema.md) — the durable-tier infrastructure T2/T3 delegate to.
- [02_storage/R07_concurrency_cross_session.md](../02_storage/R07_concurrency_cross_session.md) — single-writer per session applies to T2/T3 writes.
- Phase 2 `04b_read_write.md` (split from `04_kernel_api_contract.md` 2026-04-25) — the Rust SDK surface that exposes `t0_*` / `t1_*` / `t2_*` / `t3_*` APIs.
