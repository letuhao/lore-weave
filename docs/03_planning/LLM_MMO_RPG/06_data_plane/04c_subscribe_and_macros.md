# 04c — Kernel API Contract: Subscriptions + Macros (DP-K6..DP-K8)

> **Status:** LOCKED. Part of the Kernel API Contract (DP-K1..DP-K12) — see also [04a_core_types_and_session.md](04a_core_types_and_session.md), [04b_read_write.md](04b_read_write.md), [04d_capability_and_lifecycle.md](04d_capability_and_lifecycle.md). Originally part of `04_kernel_api_contract.md`; split on 2026-04-25 for maintainability.
> **Stable IDs in this file:** DP-K6 (Subscription primitives), DP-K7 (`dp::cache_key!` macro), DP-K8 (`dp::instrumented!` macro).

---

## Reading this file

This file specifies subscription APIs (invalidation pub/sub, T1 broadcast, durable per-channel events) and the two compile-time macros (`cache_key!`, `instrumented!`). Macros enforce key-format and telemetry rulebook items at the type level + lint level.

---

## DP-K6 — Subscription primitives

### Invalidation stream

```rust
/// Subscribe to cache invalidations for the caller's reality. SDK's internal
/// cache manager is already a subscriber; feature code rarely uses this
/// directly — it is exposed for features that maintain their own
/// computed views (e.g., leaderboard rollups) outside DP's cache.
pub async fn subscribe_invalidation(
    ctx: &SessionContext,
    filter: InvalidationFilter,
) -> Result<InvalidationStream, DpError>;

pub struct InvalidationFilter {
    pub aggregate_types: Vec<&'static str>,
    pub tiers: Vec<Tier>,
}

pub struct InvalidationStream { /* async Stream<Item = Invalidation> */ }
pub struct Invalidation { pub aggregate: &'static str, pub id: String, pub at: Instant, pub tier: Tier }
```

### T1 broadcast stream

```rust
/// Subscribe to T1 broadcasts (player position, emote, etc.) for aggregates
/// of type `A` in the session's reality. Used by WebSocket fan-out or game
/// broadcast service to deliver real-time updates to clients.
pub async fn subscribe_broadcast<A: T1Aggregate>(
    ctx: &SessionContext,
    scope: BroadcastScope,
) -> Result<BroadcastStream<A>, DpError>;

pub enum BroadcastScope {
    Reality,                    // all T1<A> in this reality
    Session(SessionId),         // only from one session (rare)
    Region(RegionId),           // players in one region (common for position)
}

pub struct BroadcastStream<A: T1Aggregate> { /* ... */ }
```

**Visibility filtering** (e.g., stealth / GM-invisible) is NOT part of this primitive — it is a feature-repo concern applied **before** broadcast. SDK delivers everything the subscriber is entitled to by capability; the feature decides what to emit. See [99_open_questions.md](99_open_questions.md) F2 follow-up.

### Durable per-channel event subscribe (Phase 4, [DP-Ch16](14_durable_subscribe.md#dp-ch16--durableeventstream-api))

```rust
/// Subscribe to a channel's durable event stream from a resume point.
/// Replays missed events on reconnect; gap-free delivery guaranteed within
/// retention. See 14_durable_subscribe.md for full semantics.
pub async fn subscribe_channel_events_durable<S: ChannelEvent>(
    ctx: &SessionContext,
    channel: &ChannelId,
    from_event_id: u64,
) -> Result<DurableEventStream<S>, DpError>;

/// Auto-multiplex over current_channel + ancestor chain.
pub async fn subscribe_session_channels<S: ChannelEvent>(
    ctx: &SessionContext,
    from_tokens: HashMap<ChannelId, u64>,
) -> Result<MultiplexedDurableStream<S>, DpError>;
```

These complement (not replace) `subscribe_invalidation` (cache coherency) and `subscribe_broadcast<A: T1Aggregate>` (T1 fan-out) — those remain pub/sub fire-and-forget. Durable subscribe is for canonical channel events that are part of the game's story and must not be lost.

---

## DP-K7 — `dp::cache_key!` macro

Compile-time cache key constructor. Implements [DP-R4](11_access_pattern_rules.md#dp-r4--cache-keys-via-dp-macro-never-hand-built). Dispatches on scope trait ([DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25)).

**Shape:**

```rust
// Reality-scoped (no channel arg)
dp::cache_key!($ctx:expr, $tier:ident, $aggregate:ident, $id:expr [, $subkey:expr]*)

// Channel-scoped (channel arg required after `;`)
dp::cache_key!($ctx:expr, $tier:ident, $aggregate:ident, $id:expr ; channel = $channel:expr [, $subkey:expr]*)
```

**Expansion (conceptual):**

```rust
// Reality-scoped:
// dp::cache_key!(ctx, T2, PlayerInventory, player_id)
// ->
format!(
    "dp:{reality}:r:{tier}:{typ}:{id}",
    reality = ctx.reality_id().as_str(),
    tier = Tier::T2.as_key(),
    typ = <PlayerInventory as Aggregate>::TYPE_NAME,
    id = dp::KeyId::from(player_id).as_str(),
)

// Channel-scoped:
// dp::cache_key!(ctx, T2, ChatMessage, msg_id; channel = tavern_id)
// ->
format!(
    "dp:{reality}:c:{channel}:{tier}:{typ}:{id}",
    reality = ctx.reality_id().as_str(),
    channel = tavern_id.as_str(),
    tier = Tier::T2.as_key(),
    typ = <ChatMessage as Aggregate>::TYPE_NAME,
    id = dp::KeyId::from(msg_id).as_str(),
)
```

**Compile-time checks:**

- `$tier` must match the tier trait of `$aggregate` — else type-check failure.
- `$aggregate` must implement `Aggregate` + exactly one scope marker (`RealityScoped` or `ChannelScoped`).
- **Passing `channel = ...` for a `RealityScoped` aggregate fails to compile.**
- **Omitting `channel = ...` for a `ChannelScoped` aggregate fails to compile.**
- `$id` must implement `Into<KeyId>`.

**Lint rule `dp::forbid_manual_cache_key`:** detects string concatenation or `format!` that produces a `dp:*` prefix outside the macro's expansion. CI-breaking.

**Cross-ref:** [12_channel_primitives.md DP-Ch5](12_channel_primitives.md#dp-ch5--cache-key-format-with-scope-marker) for full scope-marker rationale.

---

## DP-K8 — `dp::instrumented!` telemetry macro

Wraps T2/T3 read/write calls with metric emission. Implements [DP-R8](11_access_pattern_rules.md#dp-r8--telemetry-on-every-t2t3-boundary-crossing).

```rust
let inventory = dp::instrumented!(
    tier = T2,
    op = "read",
    aggregate = "player_inventory",
    {
        dp::read_projection::<PlayerInventory>(ctx, player_id).await
    }
);
```

**Emits:**

- `dp.read.latency_ms{tier,aggregate,cache_hit}` histogram
- `dp.read.count{tier,aggregate,result}` counter
- Traces a `tracing::span!` with the same labels for distributed tracing correlation

**Lint rule `dp::missing_instrumentation`:** flags T2/T3 primitive calls not wrapped by `instrumented!`. Warn-level (not hard error) because some tight inner loops intentionally skip per-op telemetry and emit aggregate metrics.

---

## Cross-references

- [04a_core_types_and_session.md](04a_core_types_and_session.md) — types referenced (`SessionContext`, `Tier`, `T1Aggregate`)
- [04b_read_write.md](04b_read_write.md) — read/write primitives this file's macros wrap
- [04d_capability_and_lifecycle.md DP-K11](04d_capability_and_lifecycle.md#dp-k11--clippy-lint-skeletons) — clippy lint skeletons enforcing macro usage
- [14_durable_subscribe.md](14_durable_subscribe.md) — full durable subscribe protocol
- [DP-R4](11_access_pattern_rules.md#dp-r4--cache-keys-via-dp-macro-never-hand-built) — Rulebook rule that `cache_key!` implements
- [DP-R8](11_access_pattern_rules.md#dp-r8--telemetry-on-every-t2t3-boundary-crossing) — Rulebook rule that `instrumented!` implements
- [20_operational_residuals.md DP-Ch46](20_operational_residuals.md#dp-ch46--histogram-bucket-layouts) — histogram bucket layouts that `instrumented!` emits into
