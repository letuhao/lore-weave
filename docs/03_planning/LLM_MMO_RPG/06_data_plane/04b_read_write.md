# 04b — Kernel API Contract: Read + Write Primitives (DP-K4..DP-K5)

> **Status:** LOCKED. Part of the Kernel API Contract (DP-K1..DP-K12) — see also [04a_core_types_and_session.md](04a_core_types_and_session.md), [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md), [04d_capability_and_lifecycle.md](04d_capability_and_lifecycle.md). Originally part of `04_kernel_api_contract.md`; split on 2026-04-25 for maintainability.
> **Stable IDs in this file:** DP-K4 (Read primitives), DP-K5 (Write primitives).

---

## Reading this file

This file specifies the read and write primitives. They dispatch on aggregate scope ([DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25)) — two forms per primitive: one for `RealityScoped`, one for `ChannelScoped`. Type-related foundations (`Aggregate`, `RealityScoped`/`ChannelScoped` traits, `CausalityToken`) live in [04a DP-K1](04a_core_types_and_session.md#dp-k1--core-types).

---

## DP-K4 — Read primitives

Read primitives dispatch on aggregate scope ([DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25)). Two forms per primitive: one for `RealityScoped`, one for `ChannelScoped`.

### Single-aggregate read

Phase 4 extension: optional `wait_for` for intra-session causality (DP-A19, DP-Ch40).

```rust
/// Read a reality-scoped aggregate. Cache-first; on miss, hits projection.
/// `wait_for = Some(token)` blocks until projection has applied the token's event
/// or `causality_timeout` (default 5s) elapses → CausalityWaitTimeout.
pub async fn read_projection_reality<A: RealityScoped>(
    ctx: &SessionContext,
    id: A::Id,
    wait_for: Option<&CausalityToken>,                  // Phase 4
    causality_timeout: Option<Duration>,                // Phase 4
) -> Result<A::Projection, DpError>;

/// Read a channel-scoped aggregate. Requires explicit channel_id.
pub async fn read_projection_channel<A: ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    id: A::Id,
    wait_for: Option<&CausalityToken>,                  // Phase 4
    causality_timeout: Option<Duration>,                // Phase 4
) -> Result<A::Projection, DpError>;
```

### Scoped query

```rust
/// Query reality-scoped aggregates matching a typed predicate.
pub async fn query_scoped_reality<A: RealityScoped>(
    ctx: &SessionContext,
    predicate: Predicate<A>,
    limit: usize,
    wait_for: Option<&CausalityToken>,                  // Phase 4
    causality_timeout: Option<Duration>,                // Phase 4
) -> Result<Vec<A::Projection>, DpError>;

/// Query channel-scoped aggregates within a specific channel.
pub async fn query_scoped_channel<A: ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    predicate: Predicate<A>,
    limit: usize,
    wait_for: Option<&CausalityToken>,                  // Phase 4
    causality_timeout: Option<Duration>,                // Phase 4
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
pub struct T2Ack {
    pub event_id: EventId,
    pub applied_at_projection: Option<Instant>,
    pub causality_token: CausalityToken,            // Phase 4 (DP-Ch38)
}
pub struct T3Ack {
    pub event_id: EventId,
    pub applied_at_projection: Instant,
    pub invalidation_fanout_ms: Duration,
    pub causality_token: CausalityToken,            // Phase 4 (DP-Ch38)
}
pub struct MultiAck {
    pub txn_id: TxnId,
    pub event_ids: Vec<EventId>,
    pub applied_at: Instant,
    pub causality_token: CausalityToken,            // Phase 4 (DP-Ch38) — covers all ops in txn
}
```

---

## Cross-references

- [04a_core_types_and_session.md](04a_core_types_and_session.md) — DP-K1 / K2 / K3: types referenced here (`SessionContext`, scope traits, `DpError`, `CausalityToken`)
- [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md) — DP-K7 `cache_key!` macro used by read/write internals
- [04d_capability_and_lifecycle.md](04d_capability_and_lifecycle.md) — DP-K9 capability check applied to every read/write entry
- [DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25) — scope marker rationale
- [DP-A19](02_invariants.md#dp-a19--intra-session-causality-preservation-via-opaque-token-phase-4-2026-04-25) — RYW invariant powering `wait_for`
- [13_channel_ordering_and_writer.md DP-Ch14](13_channel_ordering_and_writer.md#dp-ch14--cross-node-write-routing) — channel-writer transparent routing
- [18_causality_and_routing.md](18_causality_and_routing.md) — causality token + session-writer routing
