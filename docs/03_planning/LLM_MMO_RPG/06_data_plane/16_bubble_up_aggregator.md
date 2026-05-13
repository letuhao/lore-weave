# 16 — Bubble-Up Aggregator (DP-Ch25..DP-Ch30)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q27](99_open_questions.md) — event bubble-up primitive. Composes with [Q16](14_durable_subscribe.md) durable subscribe + [Q34](13_channel_ordering_and_writer.md) writer binding + [DP-Ch15](13_channel_ordering_and_writer.md#dp-ch15--causal-references-for-bubble-up-preview-full-design--q27) causal references + [DP-A17](02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25) turn boundary as natural aggregation window.
> **Stable IDs:** DP-Ch25..DP-Ch30.
> **Phase 4 status after this file:** all design blockers resolved.

---

## Reading this file

The user-clarified game model groups players into nested channels (cell → tavern → ... → continent) where event rates **decay ~10× per level up**. This decay isn't enforced — it emerges because lower-level events probabilistically trigger higher-level events through aggregation. A drama in a cell session triggers a tavern-level "ambient drama" event with some probability; enough tavern dramas in a town trigger a town-level event; and so on.

This file specifies the **mechanism** for that aggregation — the **bubble-up aggregator**. DP provides the runtime, scheduling, state persistence, deterministic RNG, and emission glue. Features provide the *logic* — what counts as a trigger, what the threshold is, what payload to emit. The mechanism is general; the policies are feature-specific.

DP-Ch25 defines the trait and SDK API. DP-Ch26 covers state persistence (event-sourced + snapshot). DP-Ch27 the deterministic RNG. DP-Ch28 the CP registry. DP-Ch29 cascading semantics. DP-Ch30 privacy.

---

## DP-Ch25 — `BubbleUpAggregator` trait + register/unregister primitives

### The trait

```rust
/// Implemented by feature crates. Each implementation is a pure
/// `(state, event, rng) -> (next_state, emit_decisions)` transition function
/// over a typed state. SDK manages subscription, dispatch, snapshot, restart,
/// and emission.
pub trait BubbleUpAggregator: Send + Sync + 'static {
    /// Stable, registry-keyed identifier. UPPER_SNAKE convention. Used for
    /// audit logs, snapshot keying, and CP registry rows. MUST NOT change
    /// between deployments without a migration.
    const AGGREGATOR_TYPE: &'static str;

    /// Aggregator's persistent state. Must serialize for snapshots and reload
    /// to identical value on restart. `Default::default()` is the fresh state
    /// for a freshly registered aggregator.
    type State: serde::Serialize + serde::DeserializeOwned + Default + Clone + Send + 'static;

    /// Filter declaring which descendant channels this aggregator consumes
    /// from. Evaluated once at registration + re-evaluated whenever a new
    /// channel under the parent appears (channel-tree-update).
    fn source_filter(&self) -> SourceFilter;

    /// Pure transition function. SDK calls this for every event arriving
    /// from a source channel matching `source_filter`, in per-channel order
    /// (DP-A15). The `rng` is seeded deterministically from the source
    /// event's `(channel_id, channel_event_id)` (DP-Ch27).
    ///
    /// Returns `(next_state, emit_decisions)`. Emit decisions are committed
    /// by the SDK via the parent's writer (DP-Ch26 commit flow).
    ///
    /// MUST be deterministic: same `(state, event, rng)` MUST produce the
    /// same `(next_state, emit_decisions)`. Replay correctness depends on it.
    fn on_event(
        &self,
        state: &Self::State,
        event: &SourceEvent,
        rng: &mut Rng,
    ) -> (Self::State, Vec<EmitDecision>);
}
```

### Source filter shapes

```rust
pub enum SourceFilter {
    /// Subscribe to all channels with matching level_name (e.g. "cell").
    /// Most common — "all cells in this tavern".
    LevelName(String),

    /// Subscribe to specific channels by id. Used for narrow targeting.
    Specific(Vec<ChannelId>),

    /// Subscribe to all immediate-child channels of the parent.
    DirectChildren,

    /// Subscribe to all descendants transitively (cell + tavern + ...).
    /// Use sparingly — high event volume.
    AllDescendants,

    /// Subscribe to descendants matching ANY of the given filters.
    Any(Vec<SourceFilter>),
}
```

`source_filter()` is invoked at registration; SDK enumerates current matching channels via the channel-tree cache ([DP-Ch3](12_channel_primitives.md#dp-ch3--cp-channel-tree-cache--delta-stream)). When a new channel matching the filter is created (channel-tree-update event), SDK auto-extends the subscription to it. When a matching channel dissolves, SDK gracefully ends that subscription branch.

### Source event shape

```rust
pub struct SourceEvent {
    pub source_channel_id: ChannelId,
    pub source_event_id: u64,                  // channel_event_id at source
    pub source_writer_epoch: u64,
    pub source_turn_number: u64,
    pub source_visibility: ChannelVisibility,  // Public | Private (see DP-Ch30)
    pub event_type: String,                    // discriminator
    pub payload: serde_json::Value,            // opaque to DP
    pub causal_refs: Vec<EventRef>,            // upstream causation chain (DP-Ch15)
    pub timestamp: Timestamp,
}
```

### Emit decisions

```rust
pub struct EmitDecision {
    /// Tier for the emitted event. Typically T2 (most bubble-up is durable-
    /// async). T3 only when the bubble-up has currency / canon impact.
    /// T0/T1 are not allowed — bubble-up events are channel-scoped and must
    /// be ordered + persisted per DP-A15.
    pub tier: Tier,

    /// Discriminator for the new event at the parent channel.
    pub event_type: String,

    /// Opaque payload. Feature interprets when consumers deserialize.
    pub payload: serde_json::Value,

    /// Optional causal refs override. If empty, SDK auto-populates with
    /// `[(source_channel_id, source_event_id)]` from the triggering event.
    /// See DP-Ch30 for redaction patterns.
    pub causal_refs: Option<Vec<EventRef>>,
}
```

### Register / unregister

```rust
impl DpClient {
    /// Register a bubble-up aggregator at a parent channel. Aggregator is
    /// persisted in the CP registry (DP-Ch28); SDK begins consuming source
    /// events from `source_filter()` matches; state begins at
    /// `Self::State::default()`.
    pub async fn register_bubble_up_aggregator<A: BubbleUpAggregator>(
        &self,
        ctx: &SessionContext,
        parent_channel: ChannelId,
        aggregator: A,
        config: AggregatorConfig,
    ) -> Result<AggregatorHandle, DpError>;

    /// Unregister. Subscriptions terminate; final snapshot is written;
    /// registry row marked unregistered_at = now.
    pub async fn unregister_bubble_up_aggregator(
        &self,
        ctx: &SessionContext,
        handle: &AggregatorHandle,
    ) -> Result<(), DpError>;
}

pub struct AggregatorConfig {
    /// Snapshot every N consumed events. Default 100.
    pub snapshot_every_n_events: u32,

    /// Cap on emit_decisions per `on_event` call. Prevents runaway cascades.
    /// Default 5.
    pub max_emit_per_event: u32,

    /// Soft timeout for `on_event` invocation. Slow aggregators are killed
    /// and reloaded from last snapshot. Default 100ms.
    pub timeout_per_call: Duration,
}

pub struct AggregatorHandle {
    pub aggregator_id: AggregatorId,    // newtype around UUID
    pub aggregator_type: String,        // copy of A::AGGREGATOR_TYPE
    pub parent_channel: ChannelId,
}
```

### Capability gating

Registering an aggregator requires the JWT capability `can_register_aggregator: Vec<level_name>` listing parent channel levels the service may register on. Mirrors [DP-Ch23](15_turn_boundary.md#dp-ch23--capability-gating) `can_advance_turn`.

---

## DP-Ch26 — State model: event-sourced + periodic snapshots

### What gets persisted

For each registered aggregator, two things land in the per-reality DB:

**Registry row** (DP-Ch28) — durable record that the aggregator exists, what type, on which parent, with what config.

**State snapshot table** — periodic JSONB snapshots of the aggregator's `State` plus a per-source cursor map.

```sql
CREATE TABLE bubble_up_aggregator_snapshot (
    aggregator_id      UUID NOT NULL REFERENCES bubble_up_aggregator(aggregator_id),
    snapshot_seq       BIGINT NOT NULL,    -- monotonic per aggregator
    cursor             JSONB NOT NULL,     -- { source_channel_id: last_consumed_event_id }
    state              JSONB NOT NULL,     -- serialized A::State
    snapshotted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (aggregator_id, snapshot_seq)
);

CREATE INDEX bubble_up_snapshot_latest_idx
    ON bubble_up_aggregator_snapshot(aggregator_id, snapshot_seq DESC);
```

### Runtime loop (per aggregator)

The SDK on the parent channel's writer node runs:

```text
1. On startup / restart:
     a. Load latest snapshot: SELECT * ORDER BY snapshot_seq DESC LIMIT 1.
        If none: state = State::default(), cursor = {} for all matching sources.
     b. Open durable subscribe (DP-Ch16) on each source channel from
        cursor[ch].next_event_id (or 0 if absent).
2. For each incoming SourceEvent (in per-source-channel order):
     a. Construct rng = deterministic_rng(source_channel_id, source_event_id).
     b. Call on_event(state, event, rng) — pure transition.
        If timeout exceeded: kill, reload from last snapshot, log.
        If panic: same.
     c. Apply state := next_state.
     d. For each emit_decision in result:
        Construct EventRef = (source_channel_id, source_event_id).
        causal_refs = decision.causal_refs.unwrap_or_else(|| vec![EventRef]).
        Submit emit via SDK's t2_write_channel / t3_write_channel
          (matched by tier) with payload + causal_refs to parent_channel.
     e. cursor[source_channel_id] = source_event_id.
     f. events_consumed += 1.
     g. If events_consumed >= config.snapshot_every_n_events:
        INSERT INTO bubble_up_aggregator_snapshot (state, cursor, ...).
        events_consumed = 0.
3. On unregister:
     Final snapshot. Close subscriptions. Mark registry row.
```

### Determinism guarantees

- **Same input event sequence + same RNG seeds** → same state + same emit decisions.
- **Snapshot recovery is correct** because state is fully determined by the events consumed up to `cursor`.
- **Replay from event log alone** (no snapshot) reconstructs the same state by re-running `on_event` from event 0 — this is the DR fallback if snapshots are corrupted.

### Failure modes + recovery

| Scenario | Behavior |
|---|---|
| Aggregator panics on a specific event | Killed, reloaded from last snapshot, replays — but same panic recurs. SDK escalates (`DpError::AggregatorStuck`); operator must unregister or fix code. Audit log records the offending event_id. |
| Aggregator timeout (`on_event` >100 ms) | Killed, reloaded from snapshot, retried once. Second timeout = same escalation. |
| Source channel dissolves mid-stream | SDK drops that subscription branch; aggregator state retains accumulated state from that source. A new channel matching `source_filter` later starts fresh from event 0 of that channel. |
| Writer-node failover (parent's writer changes) | New writer reloads snapshot + replays from cursor. Subscription cursors recover via DP-Ch16 resume tokens. Aggregator state continuity preserved. |
| Snapshot table corruption | DR: replay from event log full — `cursor = {}`, state from default, consume all source events. Slow but correct. |

### Cost guardrails

- **Snapshot rate-limit:** at most one snapshot per aggregator per second (regardless of `snapshot_every_n_events`) — prevents snapshot storms on bursty channels.
- **State size cap:** 1 MB serialized per aggregator. Larger states must be redesigned (paginate, or split into multiple aggregators).
- **Cascade depth:** max 16 (channel tree depth). DP rejects emits that would exceed cascade-depth invariant.

---

## DP-Ch27 — Deterministic RNG primitive

### API

```rust
/// Returns an RNG seeded deterministically from (channel_id, channel_event_id).
/// Same inputs → same RNG outputs, byte-for-byte. Replay-safe.
///
/// SDK passes this to `BubbleUpAggregator::on_event` so probabilistic
/// decisions reproduce on replay.
pub fn deterministic_rng(channel_id: &ChannelId, channel_event_id: u64) -> Rng;
```

`Rng` is the standard `rand::rngs::StdRng` from rand crate, seeded via:

```rust
use rand::{SeedableRng, rngs::StdRng};
use blake3;

fn deterministic_rng(channel_id: &ChannelId, channel_event_id: u64) -> StdRng {
    let mut hasher = blake3::Hasher::new();
    hasher.update(b"dp-bubble-up-rng-v1");
    hasher.update(channel_id.as_uuid().as_bytes());
    hasher.update(&channel_event_id.to_le_bytes());
    let seed: [u8; 32] = hasher.finalize().into();
    StdRng::from_seed(seed)
}
```

### Usage in aggregator

```rust
fn on_event(&self, state: &State, event: &SourceEvent, rng: &mut Rng) -> (State, Vec<EmitDecision>) {
    // Probabilistic threshold: 5% chance per drama event.
    let mut next = state.clone();
    next.drama_count += 1;

    if event.event_type == "drama" && rng.gen::<f64>() < 0.05 {
        let emit = EmitDecision {
            tier: Tier::T2,
            event_type: "tavern_ambient_drama".to_string(),
            payload: serde_json::json!({ "intensity": next.drama_count }),
            causal_refs: None,  // SDK auto-fills with source event
        };
        next.drama_count = 0;
        return (next, vec![emit]);
    }
    (next, vec![])
}
```

### Why blake3 + dedicated context

- **Cryptographic hash** ensures uniform distribution over seed space — no pathological inputs causing biased RNG.
- **`"dp-bubble-up-rng-v1"` context string** prevents seed collision with other DP RNG uses (none today, but future-proofing).
- **Versioned context** means we can rev to `v2` if we change the seeding scheme without losing replay-correctness for events emitted under `v1`.

### Multi-event composition

Aggregators that need multiple random draws per event use the same RNG sequentially:

```rust
let attack_chance = rng.gen::<f64>();      // first draw
let crit_chance = rng.gen::<f64>();        // second draw, also deterministic
```

The RNG's internal state advances deterministically — replay produces same draws in same order.

### What about wall-clock time?

Aggregators MUST NOT use `Instant::now()` or `SystemTime::now()` in `on_event`. Time-based decisions use `event.timestamp` (the source event's timestamp, recorded at write time and persisted in the event log). Wall-clock at replay differs from wall-clock at original commit — using it breaks determinism.

If a feature legitimately needs "current time" semantics in a deterministic way, it can use `event.timestamp` as the time-of-decision proxy.

---

## DP-Ch28 — CP aggregator registry + restart restoration

### Registry table (per-reality DB)

```sql
CREATE TABLE bubble_up_aggregator (
    aggregator_id     UUID PRIMARY KEY,
    parent_channel    UUID NOT NULL REFERENCES channels(id),
    aggregator_type   TEXT NOT NULL,
    source_filter     JSONB NOT NULL,
    config            JSONB NOT NULL,
    registered_by     TEXT NOT NULL,            -- service identity
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    unregistered_at   TIMESTAMPTZ
);

CREATE INDEX bubble_up_active_idx
    ON bubble_up_aggregator(parent_channel, aggregator_type)
    WHERE unregistered_at IS NULL;

CREATE UNIQUE INDEX bubble_up_unique_active
    ON bubble_up_aggregator(parent_channel, aggregator_type, source_filter)
    WHERE unregistered_at IS NULL;
```

The UNIQUE on `(parent, type, source_filter)` prevents duplicate aggregators with the same shape on the same parent. Re-registering with same shape is a no-op (returns existing handle).

### CP cache

CP caches the registry per reality alongside the channel-tree cache (DP-Ch3). Updates flow via the same channel-tree-update stream (`dp:channel_changes:{reality_id}`) extended with aggregator delta entries:

```
{
  "v": 1,
  "op": "aggregator_registered" | "aggregator_unregistered",
  "aggregator_id": "...",
  "parent_channel": "...",
  ...
}
```

### Writer-node responsibility

When a node is assigned as channel writer (per [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25)) for a parent channel, the SDK on that node:

1. Queries the registry for active aggregators on that parent.
2. For each, looks up the corresponding `BubbleUpAggregator` impl in its registered-types map (features register impls at service startup).
3. Loads latest snapshot + cursor.
4. Opens subscriptions per source filter.
5. Begins the runtime loop (DP-Ch26).

If a registry row references an `aggregator_type` not registered in the service's runtime (deployment mismatch), SDK logs error + leaves that aggregator dormant; once a deploy with the right code lands, aggregator resumes.

### gRPC additions to CP

Extends [DP-C3](05_control_plane_spec.md#dp-c3--grpc-service-surface):

```protobuf
service DpControlPlane {
  // ... existing methods ...

  // Bubble-up aggregator registry (Phase 4)
  rpc RegisterBubbleUpAggregator (RegisterAggregatorRequest) returns (AggregatorHandle);
  rpc UnregisterBubbleUpAggregator (UnregisterAggregatorRequest) returns (Empty);
  rpc ListAggregatorsForChannel (ListAggregatorsRequest) returns (AggregatorList);
}
```

CP method count: 19 → 22 after Phase 4 Q27.

### Garbage collection

Unregistered aggregators (with `unregistered_at IS NOT NULL`) are GC'd 30 days after unregistration: registry row deleted, snapshot history pruned. Provides forensic window without unbounded growth.

---

## DP-Ch29 — Cascading + recursive bubble-up

### Cascading is natural, not special

A tavern aggregator subscribes to cell events. It emits a tavern event (committed via `t2_write_channel` on the tavern). The tavern's event log now contains that bubble-up event. A *town* aggregator subscribed to tavern events sees the bubble-up event like any other tavern event and may itself emit a town event. And so on.

DP doesn't have a special "cascade" mode — cascading falls out of the trait + subscription mechanism.

### Loop prevention

A loop would require:
- Aggregator at level L emits to level L (its own parent)
- That emit triggers an aggregator at level L+1 that emits back down to level L
- The new event at level L re-triggers the original aggregator
- ... ad infinitum

DP prevents this because:
- **Aggregators only subscribe to descendants of their parent** — never ancestors. Bubble-up is strictly bottom-up.
- **Emit goes to the aggregator's bound parent only** — not back down.
- The channel tree is a tree (not a DAG), so descendants and ancestors are disjoint sets.

The only way to get a loop is for a feature to register two aggregators at different levels with broken filters — DP rejects at registration time if `source_filter()` resolves to channels that include the parent or its ancestors.

### Cascade-depth bound

Because the channel tree has max depth 16 ([DP-Ch1](12_channel_primitives.md#dp-ch1--channelid-and-tree-structure)), a cascade can chain at most 15 times (cell → tavern → ... → continent). Each level adds latency (DB write + Redis Stream publish + downstream subscriber pickup), so deep cascades are observable in latency budgets.

Realistic: most cascades are 1–2 levels (cell → tavern, occasionally cell → tavern → town). Deeper cascades require explicit feature design at multiple levels and rare RNG triggers — they don't happen by accident.

### Determinism under cascade

Each level's events are deterministic given inputs (DP-Ch26). Cascading aggregator at L+1 receives events that include both regular L-level events and bubbled-up events emitted by aggregators at L. All deterministic if their seeds are deterministic — and they are (DP-Ch27, all seeded by `channel_event_id`).

So replay reproduces the entire cascade tree given the original cell-level events.

### Cascade rate decay (the user's intent)

User stated: "events at higher levels should be ~10× rarer than the level below". DP doesn't enforce this — it emerges if features pick threshold probabilities sensibly. Suggested feature-level design rule: aggregator's RNG threshold should produce an emit roughly 1-in-N where N matches the desired rate decay (1-in-10 for typical cell→tavern, 1-in-100 for tavern→town, etc.). DP provides the mechanism; feature tunes the numbers.

---

## DP-Ch30 — Privacy + redaction patterns

### Visibility metadata on channels

Channels carry a visibility flag in their metadata (set at creation via [DP-Ch8](12_channel_primitives.md#dp-ch8--channel-crud-primitives)):

```rust
pub enum ChannelVisibility {
    Public,        // events visible to anyone with read capability on parent
    Private,       // events visible only to authorized members + parent's authorized aggregators
}
```

Default is `Public`. Private channels are explicitly opted-into by features (e.g., "secret meeting cell").

### What aggregators see

When a private channel matches an aggregator's `source_filter`, the aggregator **does** receive its events — but with `event.source_visibility = Private` flagged on the `SourceEvent`. The aggregator decides how to handle:

```rust
fn on_event(&self, state: &State, event: &SourceEvent, rng: &mut Rng) -> (State, Vec<EmitDecision>) {
    if event.source_visibility == ChannelVisibility::Private {
        // Aggregator can choose:
        //  (a) ignore private events
        //  (b) update state but emit nothing
        //  (c) emit but with redacted causal_refs
        //  (d) emit normally (transparent — leaks private channel existence!)
    }
    // ...
}
```

### Redaction patterns

**Pattern 1: skip private** — aggregator returns `(state, vec![])` on `Private` events.

**Pattern 2: aggregate but emit anonymously**:
```rust
let emit = EmitDecision {
    tier: Tier::T2,
    event_type: "tavern_undisclosed_event".to_string(),
    payload: serde_json::json!({ "magnitude": ... }),
    causal_refs: Some(vec![]),  // empty — no source pointer
};
```

**Pattern 3: aggregate transparent** — include source `EventRef`. Leaks private channel id to subscribers of the parent. Acceptable when leak is intentional (e.g., tavern crowd "noticing" a hidden conversation happened).

### What DP enforces

- Aggregator subscribes only if it has read capability on the source channel (capability JWT claim). Private channels with strict ACLs reject subscriptions from unauthorized aggregators.
- DP does NOT auto-redact — feature decides per `EmitDecision.causal_refs`.
- Subscribers reading the parent channel's events see whatever causal_refs the aggregator emitted. There is no DP-level "decode private references differently for different subscribers."

### Policy templates (Phase 4 Q32 — see [19_privacy_redaction_policies.md](19_privacy_redaction_policies.md))

DP-Ch30 establishes the data shape (visibility flag exposed, redaction is feature-level). Phase 4 Q32 / DP-Ch43..Ch45 builds on this with a **RedactionPolicy library** so most features pick a standard policy at registration:

- **Transparent** — no redaction (default)
- **SkipPrivate** — drop events from Private sources before dispatch (aggregator never sees them)
- **AnonymizeRefs** — pass events to on_event but strip causal_refs from private sources before commit
- **Custom(filter)** — feature-defined `RedactionFilter` trait

`register_bubble_up_aggregator` now takes a `redaction_policy: RedactionPolicy` parameter. SDK applies the policy in the runtime loop around `on_event` (DP-Ch44).

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch25 | `BubbleUpAggregator` trait (`AGGREGATOR_TYPE`, `State`, `source_filter`, `on_event`); `register_bubble_up_aggregator` + `unregister_bubble_up_aggregator` SDK primitives; `SourceFilter` shapes; `SourceEvent` + `EmitDecision` types; capability JWT `can_register_aggregator` claim |
| DP-Ch26 | Event-sourced state with periodic snapshots in `bubble_up_aggregator_snapshot` table; SDK runtime loop on parent's writer node; failure handling (panic / timeout / dissolve / failover); 1 MB state cap, 16-level cascade cap, 1/s snapshot rate-limit |
| DP-Ch27 | `deterministic_rng(channel_id, channel_event_id)` returning blake3-seeded `StdRng`; replay-safe; aggregators MUST use this and NOT wall-clock time |
| DP-Ch28 | CP aggregator registry table `bubble_up_aggregator`; cache delta via channel-tree-update stream; writer-node restart restoration; 3 new CP gRPC methods (`Register`, `Unregister`, `List`); 30-day GC of unregistered |
| DP-Ch29 | Cascading is natural (no special mode); loop prevention via tree-shape guarantee + filter-validation; max cascade depth 16; determinism preserved through cascade levels |
| DP-Ch30 | Channel `visibility: Public/Private` exposed to aggregator via `SourceEvent.source_visibility`; redaction is feature-level decision (skip / anonymize / transparent); DP capability-gates subscription on private channels but does not auto-redact emits |

---

## Cross-references

- [DP-A15](02_invariants.md#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25) — per-channel total ordering aggregators rely on
- [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) — aggregators run on parent channel's writer node
- [DP-A17](02_invariants.md#dp-a17--per-channel-turn-numbering-phase-4-2026-04-25) — `turn_number` available on `SourceEvent` for turn-based aggregation windows
- [DP-Ch1](12_channel_primitives.md#dp-ch1--channelid-and-tree-structure) — channel tree depth bound, visibility metadata
- [DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) — `channel_event_id` is the RNG seed input
- [DP-Ch15](13_channel_ordering_and_writer.md#dp-ch15--causal-references-for-bubble-up-preview-full-design--q27) — causal_refs schema (this file's full design)
- [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api) — durable subscribe used by aggregator runtime
- [DP-Ch21](15_turn_boundary.md#dp-ch21--turnboundary-event--advance_turn-primitive) — TurnBoundary events arrive as `SourceEvent` like any other
- [04c_subscribe_and_macros.md DP-K6](04c_subscribe_and_macros.md#dp-k6--subscription-primitives) — subscribe primitives
- [05_control_plane_spec.md DP-C3](05_control_plane_spec.md#dp-c3--grpc-service-surface) — CP gRPC surface (extended with aggregator methods)

---

## What this leaves to other Phase 4 items

| Q | Phase 4 progress |
|---|---|
| **Q19 channel pause** | Aggregator-on-paused-channel: SDK pauses dispatch to `on_event`; resume restores. Concrete `channel_pause` primitive = Q19. |
| **Q28 channel membership ops** | Aggregator may consume `member_join`/`member_leave` events as `SourceEvent`; specific event shapes = Q28. |
| **Q31 channel lifecycle** | Aggregator on dissolved parent: unregistered automatically with final snapshot; on dissolved source: subscription branch ends gracefully. Full lifecycle = Q31. |
| **Q32 privacy bubble-up** | ✅ Resolved 2026-04-25 in [19_privacy_redaction_policies.md](19_privacy_redaction_policies.md) DP-Ch43..Ch45 — RedactionPolicy enum (Transparent / SkipPrivate / AnonymizeRefs / Custom) + telemetry + per-channel visibility (no inheritance). |
| **Q27** | ✅ Resolved here. **Last design blocker — all Phase 4 design blockers now complete.** |

---

## Phase 4 design phase — complete after Q27

With Q27 resolved, **all design blockers for the channel-model extension are locked**. Phase 1-3 baseline + Phase 4 channel/ordering/writer/subscribe/turn/bubble-up extensions form a complete kernel-contract design.

Remaining Phase 4 work falls into:

| Track | Items | Nature |
|---|---|---|
| Significant gaps | Q18, Q19, Q20, Q21, Q22, Q28, Q29, Q31, Q32 | 🟡 Smaller items that don't block feature design from starting; many are feature-level concerns or V1-data-dependent |
| Nits / operational | Q23, Q24, Q25, Q33 | 🟢 Operator concerns, dashboards, retention tuning |
| Phase 1-3 residuals (carry-over) | Q2, Q3, Q7, Q10, Q11, Q13 | Carry over from earlier phases, already triaged |

**Feature design (DF4 / DF5 / DF7 etc.) can now begin** consuming the locked DP contract. Phase 4 cleanup of the remaining 🟡 + 🟢 items can proceed in parallel without blocking gameplay design.
