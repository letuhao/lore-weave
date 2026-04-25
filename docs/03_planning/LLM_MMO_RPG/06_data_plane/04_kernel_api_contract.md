# 04 — Kernel API Contract (DP-K1..DP-K12)

> **Status:** LOCKED (Phase 2). Concrete Rust SDK primitive API surface — the only sanctioned path for game-layer services to touch per-reality kernel state ([DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state), [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries)). Feature repos are built on top of this API following the [Access Pattern Rulebook](11_access_pattern_rules.md).
> **Stable IDs:** DP-K1..DP-K12. Resolves Q1 (SDK API shape) and Q14 (concrete Rust definitions) from [99_open_questions.md](99_open_questions.md).

---

## Reading this file

Code blocks are **contract sketches** — they show the shape of the API, not the final production signatures. Phase 2 locks the semantics; the exact syntax (`async fn` vs `impl Future`, trait method vs free function, `Arc<Service>` vs `&Service`) lands in the SDK crate implementation. Any deviation from the shapes below must be justified and surfaced as a superseding entry in [../decisions/](../decisions/).

---

## DP-K1 — Core types

### RealityId

```rust
/// Reality identifier. Newtype with module-private constructor — cannot be
/// forged by feature code. Produced only by SDK during session bind
/// (DP-K10) after verification against the control plane.
#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct RealityId(pub(crate) Uuid);

impl RealityId {
    pub fn as_str(&self) -> String { self.0.to_string() }
    pub(crate) fn new_verified(uuid: Uuid) -> Self { Self(uuid) }
}
```

**Enforces:** [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype), [DP-R1](11_access_pattern_rules.md#dp-r1--reality-scoping).

### SessionId, NodeId, AggregateId

```rust
#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct SessionId(pub(crate) Uuid);

#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct NodeId(pub(crate) String); // hostname or k8s pod id

/// Aggregate identity, typed by aggregate kind. Each aggregate type declares
/// its `Id` type (typically a strongly-typed wrapper over Uuid or i64).
pub trait Aggregate: Send + Sync + 'static {
    type Id: Clone + Eq + Hash + Debug;
    type Projection: Send + Sync;
    type Delta: Send + Sync;
    const TYPE_NAME: &'static str; // used in cache keys + telemetry
}
```

### Tier marker traits

Tier choice is encoded at the **type level** to implement [DP-R5](11_access_pattern_rules.md#dp-r5--no-cross-tier-mixing-in-a-single-write-operation) at compile time:

```rust
pub trait T0Aggregate: Aggregate {}
pub trait T1Aggregate: Aggregate { fn snapshot_interval() -> Duration { Duration::from_secs(10) } }
pub trait T2Aggregate: Aggregate {}
pub trait T3Aggregate: Aggregate {}
```

A feature declares exactly one of these per aggregate type. Writing to a `T2Aggregate` via a `t1_write` call fails to compile (trait bound reject).

### Scope marker traits (Phase 4, DP-A14)

Orthogonal to tier markers, every aggregate declares its **scope** (see [DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25) and [12_channel_primitives.md](12_channel_primitives.md)):

```rust
pub trait RealityScoped: Aggregate {}
pub trait ChannelScoped: Aggregate {}
```

Enforced exactly-one-scope via `#[derive(Aggregate)]` macro's `#[dp(scope = "reality" | "channel", tier = "...")]` attribute. Scope determines cache-key shape (DP-K7) and API signature (DP-K4/K5).

### ChannelId

```rust
/// Channel identifier. Newtype with module-private constructor, parallel to
/// RealityId — cannot be forged by feature code. Produced by SDK during
/// channel-tree resolution (at bind_session or on delta stream updates).
/// Full details in [12_channel_primitives.md DP-Ch1](12_channel_primitives.md#dp-ch1--channelid-and-tree-structure).
#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct ChannelId(pub(crate) Uuid);

impl ChannelId {
    pub fn reality_root(reality_id: &RealityId) -> Self { /* deterministic derivation */ }
    pub fn as_str(&self) -> String { self.0.to_string() }
    pub(crate) fn new_verified(uuid: Uuid) -> Self { Self(uuid) }
}
```

### Tier enum (runtime)

```rust
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Tier { T0, T1, T2, T3 }
```

Used in telemetry, error messages, capability checks — never in write-path dispatch (the compile-time traits dispatch).

---

## DP-K2 — SessionContext

Every SDK entry point takes `&SessionContext`. It is constructed once per session during bind (DP-K10) and passed through request-context (not thread-local, to remain async-safe).

```rust
#[derive(Clone)]
pub struct SessionContext {
    reality_id: RealityId,
    session_id: SessionId,
    node_id: NodeId,           // local node, for session-sticky checks
    capability: CapabilityToken,
    bound_at: Instant,

    // Phase 4 (DP-Ch6): channel hierarchy
    current_channel_id: ChannelId,       // session's active channel (typically a cell)
    ancestor_channels: Vec<ChannelId>,   // [current, parent, ..., root]; ≤16 entries
}

impl SessionContext {
    pub fn reality_id(&self) -> &RealityId { &self.reality_id }
    pub fn session_id(&self) -> &SessionId { &self.session_id }
    pub(crate) fn capability(&self) -> &CapabilityToken { &self.capability }

    /// Returns `Err(DpError::CapabilityExpired)` if the token has expired.
    /// Feature code does not call this directly — SDK does, on every entry.
    pub(crate) fn check_live(&self) -> Result<(), DpError> { /* ... */ }

    // Phase 4 (DP-Ch6): channel accessors
    pub fn current_channel(&self) -> &ChannelId { &self.current_channel_id }
    pub fn ancestor_chain(&self) -> &[ChannelId] { &self.ancestor_channels }
    pub fn is_ancestor(&self, target: &ChannelId) -> bool {
        self.ancestor_channels.contains(target)
    }
}
```

**Mutation:** SessionContext is effectively immutable. Channel changes happen via `DpClient::move_session_to_channel` which returns a **new** SessionContext (details in [12_channel_primitives.md DP-Ch9](12_channel_primitives.md#dp-ch9--moving-a-session-to-a-different-channel)).

---

## DP-K3 — DpError enum

One error type for every SDK return. Uses `thiserror` for derivation.

```rust
#[derive(Debug, thiserror::Error)]
pub enum DpError {
    #[error("reality id mismatch: ctx={ctx:?} requested={requested:?}")]
    RealityMismatch { ctx: String, requested: String },

    #[error("capability expired; refresh required")]
    CapabilityExpired,

    #[error("capability denies {aggregate} on {tier:?}")]
    CapabilityDenied { aggregate: &'static str, tier: Tier },

    #[error("rate limited on {tier:?}; retry after {retry_after:?}")]
    RateLimited { tier: Tier, retry_after: Duration },

    #[error("circuit open for {service}")]
    CircuitOpen { service: String },

    #[error("wrong writer node: session_owner={owner} current={current}")]
    WrongWriterNode { owner: NodeId, current: NodeId },

    /// Phase 4 (DP-A16): channel-scoped write attempted on a non-writer node
    /// AND transparent routing failed or is disabled. Normally SDK auto-routes;
    /// this surfaces only on routing failure.
    #[error("wrong channel writer: channel={channel} expected_node={expected} stale_epoch={stale_epoch}")]
    WrongChannelWriter { channel: String, expected: NodeId, stale_epoch: u64 },

    #[error("tier violation: {aggregate} requested={requested:?} allowed={allowed:?}")]
    TierViolation { aggregate: &'static str, requested: Tier, allowed: Tier },

    #[error("aggregate not found: {aggregate}/{id}")]
    AggregateNotFound { aggregate: &'static str, id: String },

    #[error("schema version mismatch: on_disk={on_disk} expected={expected}")]
    SchemaVersionMismatch { on_disk: u32, expected: u32 },

    #[error("control plane unavailable: {reason}")]
    ControlPlaneUnavailable { reason: String },

    #[error("backend io: {0}")]
    BackendIo(#[source] Box<dyn std::error::Error + Send + Sync>),
}
```

**Backpressure variants** (RateLimited, CircuitOpen) MUST be propagated by callers per [DP-R6](11_access_pattern_rules.md#dp-r6--backpressure-propagation-not-swallow-and-retry).

---

## DP-K4 — Read primitives

Read primitives dispatch on aggregate scope ([DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25)). Two forms per primitive: one for `RealityScoped`, one for `ChannelScoped`.

### Single-aggregate read

```rust
/// Read a reality-scoped aggregate. Cache-first; on miss, hits projection.
pub async fn read_projection_reality<A: RealityScoped>(
    ctx: &SessionContext,
    id: A::Id,
) -> Result<A::Projection, DpError>;

/// Read a channel-scoped aggregate. Requires explicit channel_id.
/// Fails with `DpError::CapabilityDenied` if session lacks visibility on the channel.
pub async fn read_projection_channel<A: ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    id: A::Id,
) -> Result<A::Projection, DpError>;
```

### Scoped query

```rust
/// Query reality-scoped aggregates matching a typed predicate.
pub async fn query_scoped_reality<A: RealityScoped>(
    ctx: &SessionContext,
    predicate: Predicate<A>,
    limit: usize,
) -> Result<Vec<A::Projection>, DpError>;

/// Query channel-scoped aggregates within a specific channel.
pub async fn query_scoped_channel<A: ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    predicate: Predicate<A>,
    limit: usize,
) -> Result<Vec<A::Projection>, DpError>;
```

### Predicate builder

Closed set of predicate operators; expressive enough for feature repos, restricted enough to compile to cached lookups or indexed projection queries. **No raw SQL escape hatch** — per [DP-R3](11_access_pattern_rules.md#dp-r3--no-raw-db-or-cache-client-imports-in-feature-code).

```rust
pub struct Predicate<A: Aggregate> { /* typed internal */ }

impl<A: Aggregate> Predicate<A> {
    pub fn field_eq<F: Field<A>>(f: F, v: F::Value) -> Self { /* ... */ }
    pub fn field_in<F: Field<A>>(f: F, vs: Vec<F::Value>) -> Self { /* ... */ }
    pub fn field_range<F: Field<A>>(f: F, lo: F::Value, hi: F::Value) -> Self { /* ... */ }
    pub fn and(self, other: Self) -> Self { /* ... */ }
    pub fn or(self, other: Self) -> Self { /* ... */ }
    // Limit: no joins across aggregate types; no arbitrary OR nesting beyond depth 3.
}
```

Fields are declared per aggregate via a derive macro (separate item Phase 2b):

```rust
#[derive(Aggregate)]
#[dp(type_name = "player_inventory", tier = "T2")]
pub struct PlayerInventory {
    #[dp(indexed)] pub player_id: PlayerId,
    #[dp(indexed)] pub slot: InventorySlot,
    pub items: Vec<Item>,
}
```

The derive macro generates `Field<PlayerInventory>` impls only for fields marked `#[dp(indexed)]` — preventing feature code from filtering by non-indexed fields (which would fall back to scans and break SLOs).

---

## DP-K5 — Write primitives (tier-typed)

**Phase 4 routing note:** for `ChannelScoped` writes (T2/T3), the SDK transparently routes to the channel's writer node ([DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25), [13_channel_ordering_and_writer.md DP-Ch14](13_channel_ordering_and_writer.md#dp-ch14--cross-node-write-routing)) when the calling node is not the writer. Feature code does not see this — the call signature is unchanged. Surfaced errors include `DpError::WrongChannelWriter` only when transparent routing itself fails (writer unreachable + retry exhausted). `RealityScoped` writes follow [DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes) (session-node sticky) for T1 and 02_storage R7 for T2/T3.

### T0 / T1 / T2 single-aggregate write

```rust
/// T0 ephemeral write. No durability, no broadcast.
pub fn t0_write<A: T0Aggregate>(
    ctx: &SessionContext,
    id: A::Id,
    delta: A::Delta,
) -> Result<(), DpError>;

/// T1 volatile write. In-memory update + Redis pub/sub broadcast.
/// Fails with `WrongWriterNode` if the current node is not the session-sticky
/// owner (DP-A11).
pub async fn t1_write<A: T1Aggregate>(
    ctx: &SessionContext,
    id: A::Id,
    delta: A::Delta,
) -> Result<(), DpError>;

/// T2 durable-async write. Cache write-through + outbox append, ack after
/// local apply.
pub async fn t2_write<A: T2Aggregate>(
    ctx: &SessionContext,
    id: A::Id,
    delta: A::Delta,
) -> Result<T2Ack, DpError>;
```

### T3 single-aggregate write

```rust
/// T3 durable-sync write. Synchronous event-log append + projection update +
/// cache invalidation broadcast. Ack only after invalidation is acknowledged
/// to be propagated (≤20ms), so post-ack reads on any node see the new value.
pub async fn t3_write<A: T3Aggregate>(
    ctx: &SessionContext,
    id: A::Id,
    delta: A::Delta,
) -> Result<T3Ack, DpError>;
```

### T3 multi-aggregate atomic write

```rust
/// Atomic write across multiple T3 aggregates. Wraps in a single Postgres
/// transaction, rollbacks on any failure, invalidation broadcast happens
/// only after commit.
///
/// All ops must target T3 aggregates (compile-enforced via trait bound in
/// the `T3WriteOp` constructor). Mixing tiers is DP-R5 violation.
pub async fn t3_write_multi(
    ctx: &SessionContext,
    ops: Vec<T3WriteOp>,
) -> Result<MultiAck, DpError>;

pub struct T3WriteOp { /* constructed via T3WriteOp::new::<A: T3Aggregate>(...) */ }
```

### Acknowledgment types

```rust
pub struct T2Ack { pub event_id: EventId, pub applied_at_projection: Option<Instant> }
pub struct T3Ack { pub event_id: EventId, pub applied_at_projection: Instant, pub invalidation_fanout_ms: Duration }
pub struct MultiAck { pub txn_id: TxnId, pub event_ids: Vec<EventId>, pub applied_at: Instant }
```

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

## DP-K9 — Capability tokens

### Token format

JWT signed by the control plane with a short expiry (default 5 minutes). Claims payload:

```json
{
  "iss": "dp-control-plane",
  "sub": "service:world-service",
  "reality_id": "r_<uuid>",
  "session_id": "s_<uuid>",
  "node_id": "game-node-42",
  "capabilities": [
    { "aggregate": "player_position",  "tiers": ["T1"],      "read": true, "write": true },
    { "aggregate": "player_inventory", "tiers": ["T2"],      "read": true, "write": true },
    { "aggregate": "player_currency",  "tiers": ["T3"],      "read": true, "write": false }
  ],
  "exp": 1714000000,
  "iat": 1713999700
}
```

### Capability check flow

Every SDK entry:
1. Verify JWT signature (cached CP public key).
2. Check `exp` > now. On expired, return `DpError::CapabilityExpired` — caller must refresh (DP-K10).
3. Check `reality_id` in token matches `SessionContext.reality_id`. Mismatch → `RealityMismatch`.
4. Check operation (aggregate + tier + read/write) against `capabilities` list. No match → `CapabilityDenied`.

### Refresh protocol

```rust
pub async fn refresh_capability(
    current: &SessionContext,
) -> Result<SessionContext, DpError>;
```

Calls CP with current session_id + node_id, receives new JWT, constructs a new `SessionContext`. Caller swaps in for subsequent ops. A background task in the SDK can refresh proactively 60s before expiry to avoid hot-path failures.

---

## DP-K10 — SDK initialization and session binding

### Service startup

```rust
pub struct DpClient { /* ... */ }

impl DpClient {
    /// Connect to the control plane, fetch tier policy, open cache/outbox
    /// connections. Called once per service process at startup.
    pub async fn connect(cfg: DpClientConfig) -> Result<Self, DpError>;
}

pub struct DpClientConfig {
    pub control_plane_endpoint: Url,
    pub service_id: String,        // "world-service", "combat-service", ...
    pub node_id: NodeId,
    pub service_credentials: ServiceCredentials, // mTLS cert or signed token
    pub redis_endpoint: Url,
    pub pg_endpoint: Url,          // per-reality discovery delegates to CP
}
```

### Session bind

```rust
impl DpClient {
    /// Bind a new SessionContext for a player connection (or an internal
    /// session — e.g. NPC owner node). Issues a capability request to CP,
    /// receives JWT, constructs a verified SessionContext.
    pub async fn bind_session(
        &self,
        reality: RealityId,  // already a verified newtype — caller must have
                             // received it via a previous trusted channel
                             // (e.g. gateway forwarded a player request
                             // carrying a reality reference that CP signs)
        session_id: SessionId,
    ) -> Result<SessionContext, DpError>;
}
```

**Chicken-and-egg note:** the caller cannot forge `RealityId`, but it has to come from somewhere. The flow is:

1. Player connects → gateway authenticates the player, looks up their current reality via platform DB.
2. Gateway sends a gRPC call to the game service carrying the player's reality id as a `String` + a signed gateway token.
3. Game service calls `DpClient::verify_reality(signed_token)` → CP verifies, returns a typed `RealityId` newtype.
4. Game service now holds a verified `RealityId` and can call `bind_session`.

`verify_reality` is a separate primitive:

```rust
impl DpClient {
    pub async fn verify_reality(
        &self,
        gateway_signed_reality_ref: &SignedRealityRef,
    ) -> Result<RealityId, DpError>;
}
```

### Channel primitives (Phase 4, cross-ref [DP-Ch8](12_channel_primitives.md#dp-ch8--channel-crud-primitives) / [DP-Ch9](12_channel_primitives.md#dp-ch9--moving-a-session-to-a-different-channel))

```rust
impl DpClient {
    /// Move session to a different channel. Returns a new SessionContext with
    /// refreshed ancestor chain + capability. Caller swaps in.
    pub async fn move_session_to_channel(
        &self,
        ctx: &SessionContext,
        target: ChannelId,
    ) -> Result<SessionContext, DpError>;

    /// Create a new channel as child of parent. Returns new ChannelId.
    pub async fn create_channel(
        &self,
        ctx: &SessionContext,
        parent: ChannelId,
        level_name: String,
        metadata: serde_json::Value,
    ) -> Result<ChannelId, DpError>;

    /// Dissolve a channel (descendants must already be dissolved).
    pub async fn dissolve_channel(
        &self,
        ctx: &SessionContext,
        channel: ChannelId,
    ) -> Result<(), DpError>;
}
```

---

## DP-K11 — Clippy lint skeletons

Custom clippy rules in a `dp-clippy` crate (separate compile artifact used in CI). Skeletons (Rust-ish pseudocode):

### `dp::forbid_raw_kernel_client` (R-3)

```rust
// Declare: no feature crate may import these
const FORBIDDEN_IMPORTS_IN_FEATURE_CRATES: &[&str] = &[
    "sqlx::PgPool", "sqlx::Pool", "tokio_postgres::Client",
    "redis::Client", "redis::Connection", "deadpool_postgres::Pool",
    "deadpool_redis::Pool",
];

// Rule: in any crate whose Cargo.toml does NOT have `dp-crate = true`, any
// `use` item resolving to the forbidden paths is a lint error.
```

### `dp::forbid_manual_cache_key` (R-4)

```rust
// Rule: match on `format!("dp:*", ...)` or binary string concat producing
// a literal starting with "dp:" where the call site is not inside the
// `dp::cache_key!` macro expansion. Error level.
```

### `dp::forbid_swallowed_backpressure` (R-6)

```rust
// Rule: match on `.ok()`, `.unwrap_or_default()`, `.unwrap_or_else(|_| ...)`
// applied to expressions of type `Result<_, DpError>` where the error
// variant set intersects {RateLimited, CircuitOpen}. Error level unless
// the closure explicitly matches & logs & re-raises or returns a user error.
```

### `dp::missing_instrumentation` (R-8)

```rust
// Rule: in feature crates, detect direct calls to `dp::t2_*`, `dp::t3_*`,
// `dp::read_projection`, `dp::query_scoped` not lexically wrapped by the
// `dp::instrumented!` macro. Warn level (not error — tight loops opt out
// with `#[allow(dp::missing_instrumentation)]` + aggregated metrics).
```

---

## DP-K12 — API surface summary

| Category | Count | Items |
|---|---:|---|
| Core types | 9 | `RealityId`, `ChannelId`, `SessionId`, `NodeId`, `Tier`, `Aggregate`, `T0/T1/T2/T3Aggregate` traits, `RealityScoped`/`ChannelScoped` traits, `Predicate` |
| Session | 3 | `SessionContext`, `bind_session`, `refresh_capability` |
| Error | 1 | `DpError` (13 variants incl. `WrongChannelWriter` per Phase 4 DP-A16) |
| Read | 4 | `read_projection_reality`, `read_projection_channel`, `query_scoped_reality`, `query_scoped_channel` |
| Write | 5 | `t0_write`, `t1_write`, `t2_write`, `t3_write`, `t3_write_multi` |
| Subscription | 2 | `subscribe_invalidation`, `subscribe_broadcast` |
| Macros | 2 | `cache_key!` (scope-dispatched), `instrumented!` |
| Client | 2 | `DpClient::connect`, `DpClient::verify_reality` |
| Channel | 3 | `DpClient::move_session_to_channel`, `create_channel`, `dissolve_channel` |
| **Total SDK primitives** | **~31** | Feature repos compose these into domain APIs. Channel primitives (Phase 4) are additive; earlier scope APIs subsumed into the scope-typed reads. |

~31 primitives vs. a god-interface of hundreds — the Federated Repo pattern ([DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries)) keeps DP small by design, even with channel support added in Phase 4.

---

## Cross-references

- [DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state) — the axiom this contract implements
- [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries) — federated feature repo split
- [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype) — `RealityId` newtype rationale
- [11_access_pattern_rules.md](11_access_pattern_rules.md) — Rulebook that feature repos follow over this API
- Phase 2 `05_control_plane_spec.md` — CP surface that `DpClient::connect`, `bind_session`, `verify_reality`, `refresh_capability` call into
- Phase 2 `06_cache_coherency.md` — protocol behind `subscribe_invalidation` and cache read semantics
- [08_scale_and_slos.md](08_scale_and_slos.md) — latency budgets the SDK must fit inside

---

## Deferred to Phase 2b / Phase 3

- **`#[derive(Aggregate)]` proc-macro** — concrete derivation of `Aggregate` + `Field<A>` impls from struct attributes. Behavior sketched in DP-K4 but macro code lives in `dp-derive` crate (separate artifact).
- **Schema versioning and migration** — `SchemaVersionMismatch` variant exists but migration protocol is [Q5](99_open_questions.md) in CP spec.
- **Cross-reality read** — `cross_reality_read` API referenced by [Q11](99_open_questions.md) is explicit out-of-scope for Phase 2; coordinator-owned, not SDK-primitive.
- **Backpressure exact shape** — [Q12](99_open_questions.md); `RateLimited.retry_after` value comes from CP-managed token bucket, design in Phase 3 failure doc.
