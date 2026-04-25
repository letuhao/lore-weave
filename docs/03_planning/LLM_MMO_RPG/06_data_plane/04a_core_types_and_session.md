# 04a — Kernel API Contract: Core Types + Session + Errors (DP-K1..DP-K3)

> **Status:** LOCKED. Part of the Kernel API Contract (DP-K1..DP-K12) — see also [04b_read_write.md](04b_read_write.md), [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md), [04d_capability_and_lifecycle.md](04d_capability_and_lifecycle.md). Originally one file `04_kernel_api_contract.md` (891 lines); split on 2026-04-25 into four files for maintainability after Phase 4 expansion.
> **Stable IDs in this file:** DP-K1 (Core types), DP-K2 (SessionContext), DP-K3 (DpError enum).

---

## Reading this file

Code blocks are **contract sketches** — they show the shape of the API, not the final production signatures. Phase 2 locks the semantics; the exact syntax (`async fn` vs `impl Future`, trait method vs free function, `Arc<Service>` vs `&Service`) lands in the SDK crate implementation. Any deviation from the shapes below must be justified and surfaced as a superseding entry in [../decisions/](../decisions/).

This file covers the foundational types every other DP API uses: `RealityId`, `ChannelId`, scope traits, `SessionContext`, and the unified `DpError` enum.

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

### CausalityToken (Phase 4, DP-Ch38)

```rust
/// Opaque token issued on T2/T3/Multi/Pause/Turn write acks. Hand off to
/// other services to preserve read-your-writes via the optional `wait_for`
/// parameter on read primitives. Module-private constructor — cannot be
/// forged by feature code. Full semantics in
/// [18_causality_and_routing.md](18_causality_and_routing.md).
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct CausalityToken(/* opaque internals */);
```

### Tier enum (runtime)

```rust
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Tier { T0, T1, T2, T3 }
```

Used in telemetry, error messages, capability checks — never in write-path dispatch (the compile-time traits dispatch).

---

## DP-K2 — SessionContext

Every SDK entry point takes `&SessionContext`. It is constructed once per session during bind ([DP-K10](04d_capability_and_lifecycle.md#dp-k10--sdk-initialization-and-session-binding)) and passed through request-context (not thread-local, to remain async-safe).

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

    /// Phase 4 (DP-Ch35): channel is paused; game writes blocked until resume
    /// (or paused_until expiry). Lifecycle/admin ops still accepted.
    #[error("channel paused: channel={channel} reason={reason} until={paused_until:?}")]
    ChannelPaused { channel: String, reason: String, paused_until: Option<Timestamp> },

    /// Phase 4 (DP-Ch37): operation targeting a Dissolved channel.
    #[error("channel dissolved: channel={channel}")]
    ChannelDissolved { channel: String },

    /// Phase 4 (DP-Ch37): cannot dissolve a channel that has non-dissolved descendants.
    #[error("cannot dissolve: channel {channel} has {descendant_count} non-dissolved descendants")]
    ChannelHasDescendants { channel: String, descendant_count: u32 },

    /// Phase 4 (DP-Ch37): operation already applied; result returned without effect.
    #[error("channel already in target state: channel={channel} state={state}")]
    ChannelAlreadyInState { channel: String, state: String },

    /// Phase 4 (DP-A19, DP-Ch39): wait_for token's event_id never reached
    /// projection-applied state within the timeout window.
    #[error("causality wait timeout: requested={requested} last_applied={last_applied} waited={waited:?}")]
    CausalityWaitTimeout { token: CausalityToken, last_applied: u64, requested: u64, waited: Duration },

    /// Phase 4 (DP-Ch42): CP has no record of the session (expired or never
    /// bound). Caller must re-bind via bind_session.
    #[error("session not found: session_id={session_id}")]
    SessionNotFound { session_id: String },

    /// Phase 4 (DP-Ch51): turn slot already held by a different actor.
    #[error("turn slot held by other actor: actor={actor:?} expected_until={expected_until:?}")]
    TurnSlotHeldBy { actor: ActorId, expected_until: Timestamp },

    /// Phase 4 (DP-Ch52): claimed expected_duration exceeds the 5-minute hard
    /// ceiling. Reduce expected_duration or split into multiple slots.
    #[error("turn slot expected_duration too long: requested={requested:?} max=5min")]
    ExpectedDurationTooLong { requested: Duration },

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

## Cross-references

- [DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state) — the axiom this contract implements
- [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries) — federated feature repo split
- [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype) — `RealityId` newtype rationale
- [11_access_pattern_rules.md](11_access_pattern_rules.md) — Rulebook that feature repos follow over this API
- [04b_read_write.md](04b_read_write.md) — DP-K4 / K5: read + write primitives
- [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md) — DP-K6 / K7 / K8: subscribe + macros
- [04d_capability_and_lifecycle.md](04d_capability_and_lifecycle.md) — DP-K9 / K10 / K11 / K12: capability + client + lints + summary
