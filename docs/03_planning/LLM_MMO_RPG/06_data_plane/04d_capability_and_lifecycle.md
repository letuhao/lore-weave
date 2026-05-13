# 04d — Kernel API Contract: Capability + Client + Lifecycle + Lints + Summary (DP-K9..DP-K12)

> **Status:** LOCKED. Part of the Kernel API Contract (DP-K1..DP-K12) — see also [04a_core_types_and_session.md](04a_core_types_and_session.md), [04b_read_write.md](04b_read_write.md), [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md). Originally part of `04_kernel_api_contract.md`; split on 2026-04-25 for maintainability.
> **Stable IDs in this file:** DP-K9 (Capability tokens), DP-K10 (SDK init + session bind + channel + lifecycle + slot primitives), DP-K11 (Clippy lint skeletons), DP-K12 (API surface summary).

---

## Reading this file

This file covers the SDK lifecycle: capability JWT issuance + verification (DP-K9), `DpClient::connect` + `bind_session` + the full set of channel/lifecycle/turn-slot primitives on `DpClient` (DP-K10), the four custom clippy lints that enforce the Rulebook (DP-K11), and the complete API surface summary (DP-K12).

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

    /// Phase 4 (DP-Ch21): advance the channel's turn counter by 1 and emit
    /// a TurnBoundary event. Capability-gated by `can_advance_turn` JWT claim.
    /// See 15_turn_boundary.md for full semantics.
    pub async fn advance_turn(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
        turn_data: serde_json::Value,
        causal_refs: Vec<EventRef>,
    ) -> Result<TurnAck, DpError>;

    /// Phase 4 (DP-Ch25): register a bubble-up aggregator on a parent channel.
    /// Aggregator persists in CP registry; SDK manages subscribe + dispatch +
    /// snapshot + restart. Capability-gated by `can_register_aggregator` claim.
    /// `redaction_policy` (Phase 4 Q32, DP-Ch43) controls how SDK handles
    /// events from Private-visibility source channels: Transparent (default,
    /// no redaction) / SkipPrivate / AnonymizeRefs / Custom. See
    /// 16_bubble_up_aggregator.md + 19_privacy_redaction_policies.md.
    pub async fn register_bubble_up_aggregator<A: BubbleUpAggregator>(
        &self,
        ctx: &SessionContext,
        parent_channel: ChannelId,
        aggregator: A,
        config: AggregatorConfig,
        redaction_policy: RedactionPolicy,           // Phase 4 Q32
    ) -> Result<AggregatorHandle, DpError>;

    pub async fn unregister_bubble_up_aggregator(
        &self,
        ctx: &SessionContext,
        handle: &AggregatorHandle,
    ) -> Result<(), DpError>;

    /// Phase 4 (DP-Ch51): claim turn slot for `actor` on `channel` with
    /// expected duration. Hint only — does NOT block writes (use channel_pause
    /// for that). Capability-gated by `can_advance_turn`. Idempotent on same
    /// actor; fails if a different actor holds the slot.
    /// See 21_llm_turn_slot.md for full semantics + patterns.
    pub async fn claim_turn_slot(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
        actor: ActorId,
        expected_duration: Duration,
        reason: String,
    ) -> Result<TurnSlotAck, DpError>;

    pub async fn release_turn_slot(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
    ) -> Result<(), DpError>;

    pub async fn get_turn_slot(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
    ) -> Result<Option<TurnSlot>, DpError>;

    /// Phase 4 (DP-Ch35): pause a channel. Game writes (advance_turn,
    /// ChannelScoped writes, bubble-up emits) reject with ChannelPaused.
    /// Lifecycle and admin ops continue. Capability-gated by
    /// `can_pause_channel: Vec<level_name>` JWT claim.
    /// `paused_until = None` is indefinite. Idempotent.
    pub async fn channel_pause(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
        reason: String,
        paused_until: Option<Timestamp>,
    ) -> Result<PauseAck, DpError>;

    /// Clear the pause flag. Idempotent.
    pub async fn channel_resume(
        &self,
        ctx: &SessionContext,
        channel: &ChannelId,
    ) -> Result<(), DpError>;
}

pub struct PauseAck {
    pub channel_event_id: u64,
    pub paused_until: Option<Timestamp>,
}

pub struct TurnAck {
    pub channel_event_id: u64,
    pub turn_number: u64,
    pub applied_at: Timestamp,
}

/// Phase 4 (DP-Ch51): turn slot claim ack.
pub struct TurnSlotAck {
    pub channel_event_id: u64,
    pub expected_until: Timestamp,
}

/// Phase 4 (DP-Ch51): turn slot read.
pub struct TurnSlot {
    pub actor: ActorId,
    pub started_at: Timestamp,
    pub expected_until: Timestamp,
    pub reason: String,
}

/// Phase 4 (DP-Ch27): deterministic RNG seeded by a channel event id.
/// Used by bubble-up aggregators to make probabilistic decisions that
/// reproduce on replay. Aggregators MUST use this and MUST NOT use
/// wall-clock time for randomness.
pub fn deterministic_rng(channel_id: &ChannelId, channel_event_id: u64) -> Rng;
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
| Core types | 10 | `RealityId`, `ChannelId`, `SessionId`, `NodeId`, `Tier`, `Aggregate`, `T0/T1/T2/T3Aggregate` traits, `RealityScoped`/`ChannelScoped` traits, `Predicate`, `CausalityToken` (Phase 4) |
| Session | 3 | `SessionContext`, `bind_session`, `refresh_capability` |
| Error | 1 | `DpError` (21 variants — see [04a DP-K3](04a_core_types_and_session.md#dp-k3--dperror-enum)) |
| Read | 4 | `read_projection_reality`, `read_projection_channel`, `query_scoped_reality`, `query_scoped_channel` |
| Write | 5 | `t0_write`, `t1_write`, `t2_write`, `t3_write`, `t3_write_multi` |
| Subscription | 4 | `subscribe_invalidation` (pub/sub) · `subscribe_broadcast<T1>` (pub/sub) · `subscribe_channel_events_durable<S>` (Streams + DB catchup, Phase 4) · `subscribe_session_channels<S>` (multiplex, Phase 4) |
| Macros | 2 | `cache_key!` (scope-dispatched), `instrumented!` |
| Client | 2 | `DpClient::connect`, `DpClient::verify_reality` |
| Channel | 11 | `DpClient::move_session_to_channel`, `create_channel`, `dissolve_channel`, `advance_turn`, `register_bubble_up_aggregator`, `unregister_bubble_up_aggregator`, `channel_pause`, `channel_resume`, `claim_turn_slot`, `release_turn_slot`, `get_turn_slot` (Phase 4) |
| Aggregator | 1 | `deterministic_rng` (Phase 4) |
| **Total SDK primitives** | **~42** | Feature repos compose these into domain APIs. Channel + durable subscribe + turn boundary + bubble-up + lifecycle/pause + turn-slot (Phase 4) are additive. |

~42 primitives vs. a god-interface of hundreds — the Federated Repo pattern ([DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries)) keeps DP small by design, even with full channel + ordering + subscribe + turn + bubble-up + lifecycle + turn-slot support added in Phase 4.

---

## Cross-references

- [04a_core_types_and_session.md](04a_core_types_and_session.md) — DP-K1 / K2 / K3
- [04b_read_write.md](04b_read_write.md) — DP-K4 / K5
- [04c_subscribe_and_macros.md](04c_subscribe_and_macros.md) — DP-K6 / K7 / K8
- [DP-A1](02_invariants.md#dp-a1--dp-primitives--rulebook-are-the-only-sanctioned-path-to-kernel-state) — the axiom this contract implements
- [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries) — federated feature repo split
- [DP-A12](02_invariants.md#dp-a12--session-context-gated-access-via-realityid-newtype) — `RealityId` newtype rationale
- [11_access_pattern_rules.md](11_access_pattern_rules.md) — Rulebook that feature repos follow over this API
- [05_control_plane_spec.md](05_control_plane_spec.md) — CP surface that `DpClient::connect`, `bind_session`, `verify_reality`, `refresh_capability` call into
- [06_cache_coherency.md](06_cache_coherency.md) — protocol behind `subscribe_invalidation` and cache read semantics
- [08_scale_and_slos.md](08_scale_and_slos.md) — latency budgets the SDK must fit inside
- [12_channel_primitives.md](12_channel_primitives.md) — channel CRUD primitives full semantics
- [15_turn_boundary.md](15_turn_boundary.md) — `advance_turn` full semantics
- [16_bubble_up_aggregator.md](16_bubble_up_aggregator.md) — bubble-up aggregator primitives full semantics
- [17_channel_lifecycle.md](17_channel_lifecycle.md) — channel pause + lifecycle full semantics
- [18_causality_and_routing.md](18_causality_and_routing.md) — causality + routing extensions
- [19_privacy_redaction_policies.md](19_privacy_redaction_policies.md) — `RedactionPolicy` parameter on register_bubble_up_aggregator
- [21_llm_turn_slot.md](21_llm_turn_slot.md) — turn-slot primitives full semantics + patterns

---

## Deferred to Phase 2b / Phase 3

- **`#[derive(Aggregate)]` proc-macro** — concrete derivation of `Aggregate` + `Field<A>` impls from struct attributes. Behavior sketched in [04b DP-K4](04b_read_write.md#dp-k4--read-primitives) but macro code lives in `dp-derive` crate (separate artifact).
- **Schema versioning and migration** — `SchemaVersionMismatch` variant exists but migration protocol is [Q5](99_open_questions.md) in CP spec.
- **Cross-reality read** — `cross_reality_read` API referenced by [Q11](99_open_questions.md) is explicit out-of-scope for Phase 2; coordinator-owned, not SDK-primitive.
- **Backpressure exact shape** — [Q12](99_open_questions.md); `RateLimited.retry_after` value comes from CP-managed token bucket, design in Phase 3 failure doc.
