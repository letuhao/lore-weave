# 12 — Channel Primitives (DP-Ch1..DP-Ch10)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q26](99_open_questions.md) — channel hierarchy as first-class DP concept. Implements axioms [DP-A13](02_invariants.md#dp-a13--channel-hierarchy-as-first-class-scope-phase-4-2026-04-25) and [DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25).
> **Stable IDs:** DP-Ch1..DP-Ch10.

---

## Reading this file

Channels are the game's nested social contexts — cell session inside tavern inside town inside district inside country inside continent, rooted at the reality. This file locks the DP-level primitives: identity type, tree schema, registry ownership, scope marker traits, cache-key format, SessionContext extension, and the SDK primitives that manipulate channel state.

It does **not** lock: per-channel event ordering (→ Q17/Q30), writer node binding per channel (→ Q34), turn/page boundary primitives (→ Q15), bubble-up aggregator (→ Q27), pause semantics (→ Q19), membership validation rules (→ Q28), lifecycle details (→ Q31), or privacy rules on bubble-up (→ Q32). Those are separate Phase 4 items that build on the primitives here.

---

## DP-Ch1 — ChannelId and tree structure

### ChannelId newtype

```rust
/// Channel identifier. Newtype with module-private constructor — cannot be
/// forged by feature code. Produced only by the SDK during channel-tree
/// resolution (at bind_session or on delta-stream updates).
#[derive(Clone, Debug, Eq, PartialEq, Hash)]
pub struct ChannelId(pub(crate) Uuid);

impl ChannelId {
    /// Reserved: the root channel of a reality. Stable per-reality derivation
    /// so reality-scoped aggregates can reference an implicit root without
    /// an extra CP lookup.
    pub fn reality_root(reality_id: &RealityId) -> Self { /* deterministic derivation */ }

    pub fn as_str(&self) -> String { self.0.to_string() }

    pub(crate) fn new_verified(uuid: Uuid) -> Self { Self(uuid) }
}
```

Parallel shape to [`RealityId`](04_kernel_api_contract.md#realityid) (see [DP-K1](04_kernel_api_contract.md#dp-k1--core-types)) — same module-privacy story, same newtype discipline, compile-time forgery prevention.

### Tree structure

A reality's channel tree is a strict tree (not a DAG): every channel except the root has exactly one parent. Nodes carry metadata:

```rust
pub struct Channel {
    pub id: ChannelId,
    pub parent: Option<ChannelId>, // None for root
    pub reality_id: RealityId,
    pub level_name: String,        // free-form tag ("tavern", "cell", ...)
    pub display_name: Option<String>, // human-readable, optional
    pub depth: u8,                 // root = 0
    pub lifecycle: ChannelLifecycle, // Active | Dormant | Dissolved — full state machine in [17_channel_lifecycle.md](17_channel_lifecycle.md)
    pub metadata: serde_json::Value, // feature-level bag; DP does not interpret
    pub created_at: Timestamp,
    pub dissolved_at: Option<Timestamp>,
}

pub enum ChannelLifecycle { Active, Dormant, Dissolved }
```

Tree invariants:

- **Single root per reality.** Root's `id == ChannelId::reality_root(reality_id)`, `parent == None`, `level_name` conventional (e.g., `"reality"`).
- **No cycles.** Enforced by `depth` field (root = 0, children = parent.depth + 1) + referential integrity on `parent`.
- **Max depth ≤16.** Protects against pathological trees; feature-level books declaring deeper trees fail validation.
- **Dissolution is terminal.** A `Dissolved` channel cannot be re-activated; its events archive per 02_storage retention (→ Q33).

---

## DP-Ch2 — Channel registry (per-reality DB schema)

Lives in each reality's own Postgres database (the same DB that holds the reality's event log and projections). Owned by the reality's own data plane, not CP.

```sql
-- In each per-reality DB
CREATE TABLE channels (
    id            UUID PRIMARY KEY,
    parent        UUID REFERENCES channels(id),
    level_name    TEXT NOT NULL,
    display_name  TEXT,
    depth         SMALLINT NOT NULL CHECK (depth >= 0 AND depth <= 16),
    lifecycle     TEXT NOT NULL CHECK (lifecycle IN ('active','dormant','dissolved')),
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dissolved_at  TIMESTAMPTZ,

    CONSTRAINT channels_root_single UNIQUE (id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT channels_no_orphan CHECK (
        (parent IS NULL AND depth = 0) OR (parent IS NOT NULL AND depth > 0)
    )
);

CREATE INDEX channels_parent_idx ON channels(parent);
CREATE INDEX channels_level_idx ON channels(level_name) WHERE lifecycle = 'active';
CREATE INDEX channels_lifecycle_idx ON channels(lifecycle);
```

**Why per-reality DB and not CP:**

- Cell creation can be frequent (~10–100/minute per active reality). Putting this on CP makes CP a serialization point for channel churn → violates [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split) "CP not on hot path."
- Channel operations are naturally reality-local — a cell in reality A doesn't affect reality B. Scaling per-reality matches the reality-scoped Postgres sharding already in [02_storage/R4](../02_storage/R04_fleet_ops.md).
- CP still knows about all channels via its cache (DP-Ch3), refreshed lazily + on delta stream.

**Writes to this table** happen via the SDK's channel-CRUD primitives (DP-Ch8), not via raw SQL. The SDK is the only writer; feature code goes through SDK.

---

## DP-Ch3 — CP channel tree cache + delta stream

CP holds a **cached snapshot** of every active reality's channel tree for fast `bind_session` handshake and for resolving ancestor chains. CP does NOT own the tree — it is a consumer of the per-reality registry.

### Cache shape

Per reality, CP holds:

- Full `Vec<Channel>` (all active channels) in memory
- Derived ancestor-chain map: `HashMap<ChannelId, Vec<ChannelId>>` (fast lookup for any channel → path to root)
- Version counter + last-sync timestamp

Size estimate: ~200–500 channels × ~300 bytes × 1000 active realities = ~150 MB in CP memory. Comfortable.

### Sync protocol

**Initial sync** — on reality warm (`frozen → active` per [DP-C7](05_control_plane_spec.md#dp-c7--cold-start-coordination)):

1. CP opens a read connection to the reality's Postgres.
2. `SELECT * FROM channels WHERE lifecycle IN ('active', 'dormant')`.
3. Build in-memory tree + ancestor map; record version = now.

**Delta stream** — during active reality life:

1. Reality's SDK emits a structured event `channel_tree_change { op: Insert|Update|Dissolve, channel: Channel }` onto a dedicated Redis Stream `dp:channel_changes:{reality_id}`.
2. CP consumes this stream with a durable cursor per reality.
3. On each event, CP updates its in-memory tree + invalidates the ancestor map for affected subtree.

### Serving to SDK

When an SDK calls `bind_session(reality_id, session_id, current_channel_id)`:

1. CP looks up `current_channel_id` in its cache for that reality.
2. CP returns the resolved ancestor chain + JWT with scope claims including `allowed_channels`.
3. SDK stores chain in `SessionContext.ancestor_channels`.

**SDK-side delta subscription** — an SDK can subscribe to `StreamChannelTreeUpdates(reality_id)` (new gRPC method on [DP-C3](05_control_plane_spec.md#dp-c3--grpc-service-surface)). CP forwards filtered channel-tree changes; SDK refreshes its own local ancestor cache.

### Degraded-mode

If CP is unreachable (per [DP-F3](07_failure_and_recovery.md#dp-f3--control-plane-outage--recovery)):
- Existing `SessionContext` ancestor chains remain valid (they were resolved at bind time).
- `move_session_to_channel` to a previously-unseen channel fails with `DpError::ControlPlaneUnavailable` — SDK cannot verify the target channel exists.
- Channel CRUD (create/dissolve) continues locally against per-reality DB; delta stream backlogs in Redis Stream; CP catches up on recovery.

---

## DP-Ch4 — Scope marker traits

```rust
/// Marker: aggregate is identified by (reality_id, aggregate_id).
/// Aggregate follows the reality, not any channel. Default scope.
pub trait RealityScoped: Aggregate {}

/// Marker: aggregate is identified by (reality_id, channel_id, aggregate_id).
/// Aggregate lives in a specific channel.
pub trait ChannelScoped: Aggregate {}
```

**Exclusivity:** an aggregate type implements **exactly one** of these. Enforced via `#[derive(Aggregate)]` macro:

```rust
#[derive(Aggregate)]
#[dp(scope = "reality", tier = "T2")]
pub struct PlayerInventory {
    pub player_id: PlayerId,
    pub items: Vec<Item>,
}
// -> generates: impl RealityScoped for PlayerInventory {}

#[derive(Aggregate)]
#[dp(scope = "channel", tier = "T2")]
pub struct ChatMessage {
    pub author: PlayerId,
    pub body: String,
}
// -> generates: impl ChannelScoped for ChatMessage {}
```

Accidentally declaring `#[dp(scope = "reality_and_channel")]` fails macro compilation with a clear error.

**Note on tier × scope orthogonality:**

- `PlayerInventory` is (T2, Reality) — durable, reality-scoped.
- `ChatMessage` is (T2, Channel) — durable, channel-scoped.
- `TypingIndicator` is (T0, Channel) — ephemeral, channel-scoped.
- `ReputationScore` is (T3, Reality) — durable-sync, reality-scoped (money-adjacent).

All 4 tiers × 2 scopes = 8 combinations, all valid.

---

## DP-Ch5 — Cache key format with scope marker

```
Reality-scoped:   dp:{reality_id}:r:{tier}:{aggregate_type}:{aggregate_id}[:subkey]
Channel-scoped:   dp:{reality_id}:c:{channel_id}:{tier}:{aggregate_type}:{aggregate_id}[:subkey]
```

The `r` / `c` marker at position 2 makes keys self-describing for debugging + operator tooling.

Macro `dp::cache_key!` is updated to dispatch on scope:

```rust
// Compile-time: macro knows scope from the aggregate type's trait impl
dp::cache_key!(ctx, T2, PlayerInventory, player_id)
// -> "dp:{reality}:r:t2:player_inventory:{player_id}"  (RealityScoped)

dp::cache_key!(ctx, T2, ChatMessage, msg_id; channel = tavern_id)
// -> "dp:{reality}:c:{tavern_id}:t2:chat_message:{msg_id}"  (ChannelScoped, channel arg required)
```

Macro compile-error cases:
- Passing `channel = ...` argument for a `RealityScoped` aggregate → rejected.
- Omitting `channel = ...` for a `ChannelScoped` aggregate → rejected.
- Passing a `ChannelId` that does not match the scope → rejected (type-level).

**Supersession:** [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys) is extended (not withdrawn) — the original "reality_id first" invariant still holds; scope marker `r`/`c` is inserted at position 2.

---

## DP-Ch6 — SessionContext extension

```rust
#[derive(Clone)]
pub struct SessionContext {
    // Existing (Phase 2, DP-K2):
    reality_id: RealityId,
    session_id: SessionId,
    node_id: NodeId,
    capability: CapabilityToken,
    bound_at: Instant,

    // NEW (Phase 4, DP-Ch6):
    current_channel_id: ChannelId,
    ancestor_channels: Vec<ChannelId>, // [current, parent, grandparent, ..., root]
}

impl SessionContext {
    pub fn current_channel(&self) -> &ChannelId { &self.current_channel_id }

    /// Ancestor chain INCLUDING current. First element = current, last = root.
    pub fn ancestor_chain(&self) -> &[ChannelId] { &self.ancestor_channels }

    /// Is `target` an ancestor (inclusive of current) of this session's channel?
    /// Used for visibility checks — events from target reach this session.
    pub fn is_ancestor(&self, target: &ChannelId) -> bool {
        self.ancestor_channels.contains(target)
    }
}
```

**Ancestor chain depth** = tree depth ≤ 16, so `Vec<ChannelId>` is small and cheap to clone.

**Mutation:** SessionContext is effectively immutable during its lifetime; to change channel, SDK issues `move_session_to_channel` which **creates a new SessionContext** (new ancestor chain, same session_id + capability-refresh if needed). Callers swap in the new context for subsequent ops.

---

## DP-Ch7 — Channel ancestor lookup

SDK exposes a synchronous helper for feature code that needs to walk the chain:

```rust
impl SessionContext {
    /// Walk ancestors starting from current, returning Some(channel_id) when
    /// the predicate matches; None if no ancestor matches.
    pub fn find_ancestor<F>(&self, predicate: F) -> Option<&ChannelId>
        where F: Fn(&ChannelId) -> bool;

    /// Ancestor at a given depth from root (0 = root, depth_from_root increases downward).
    /// None if depth exceeds the chain.
    pub fn ancestor_at_depth(&self, depth_from_root: u8) -> Option<&ChannelId>;
}
```

For richer queries (e.g., "find the nearest ancestor whose `level_name` is `'tavern'`"), feature code calls `read_projection_reality::<Channel>(ctx, channel_id)` and inspects metadata — channel metadata is a RealityScoped T2 aggregate under the hood.

---

## DP-Ch8 — Channel CRUD primitives

Channel lifecycle mutations are SDK primitives that write to the per-reality `channels` table + emit the delta-stream event.

```rust
impl DpClient {
    /// Create a new channel as child of parent. Feature code provides level_name
    /// and metadata; DP generates a new ChannelId + writes to channels table +
    /// publishes channel_tree_change { op: Insert }.
    pub async fn create_channel(
        &self,
        ctx: &SessionContext,
        parent: ChannelId,
        level_name: String,
        metadata: serde_json::Value,
    ) -> Result<ChannelId, DpError>;

    /// Update channel metadata or display_name. Level_name and parent cannot
    /// be changed (would invalidate ancestor chains of descendants).
    pub async fn update_channel_metadata(
        &self,
        ctx: &SessionContext,
        channel: ChannelId,
        updates: ChannelUpdate, // display_name, metadata
    ) -> Result<(), DpError>;

    /// Mark channel dissolved. Descendants must already be dissolved (SDK
    /// validates recursion). Dissolved channels retain events per retention policy.
    pub async fn dissolve_channel(
        &self,
        ctx: &SessionContext,
        channel: ChannelId,
    ) -> Result<(), DpError>;
}
```

**Validation NOT in DP scope:**
- Capacity limits per channel (how many cells per tavern) → feature-level rule.
- Prerequisites for creation (does player have rights to spawn a cell?) → feature + capability.
- Cascading effects on dissolve (migrate active sessions away first) → feature-level orchestration.

DP only enforces structural invariants (tree integrity, depth cap, no cycles, dissolve-descendants-first).

---

## DP-Ch9 — Moving a session to a different channel

```rust
impl DpClient {
    /// Issue a capability refresh + new ancestor chain for the session under
    /// the new channel. Returns a new SessionContext; caller swaps in.
    ///
    /// Fails with CapabilityDenied if the session's capabilities don't include
    /// the target channel. Fails with ChannelNotFound if target doesn't exist
    /// or is Dissolved.
    pub async fn move_session_to_channel(
        &self,
        ctx: &SessionContext,
        target: ChannelId,
    ) -> Result<SessionContext, DpError>;
}
```

**Observer effects (feature-level, not enforced by DP):**
- Feature that tracks "player is in cell X" emits appropriate leave/enter events (T2 writes).
- Bubble-up aggregators may react to presence changes (Q27 territory).

DP's concern is the SessionContext + capability refresh. Everything else is feature.

---

## DP-Ch10 — Channel-tree-change invalidation

When a channel is created, updated, or dissolved, multiple caches must be coherent:

1. **Per-reality DB** — authoritative, updated first (SDK write).
2. **Redis Stream `dp:channel_changes:{reality_id}`** — delta event published in same transaction (outbox pattern via [DP-K5](04_kernel_api_contract.md#dp-k5--write-primitives-tier-typed) / [02_storage R6](../02_storage/R06_R12_publisher_reliability.md)).
3. **CP in-memory channel tree cache** — consumes stream, updates.
4. **SDK-side ancestor caches on each node** — CP pushes to subscribed SDKs via `StreamChannelTreeUpdates`.
5. **Active SessionContexts holding stale ancestor chains** — see below.

### Stale SessionContext handling

A SessionContext's `ancestor_channels` is a snapshot from bind-time or last move. If the tree changes (e.g., a tavern's parent moves from town-A to town-B), existing SessionContexts are stale.

Policy:

- **Channel create / dissolve / metadata update does not invalidate existing SessionContexts** — their ancestor chains are still correct for their current_channel.
- **Re-parenting** is not permitted (see DP-Ch8 — `parent` cannot change). This is the reason; supporting re-parent would require invalidating every SessionContext in the affected subtree.
- **Channel dissolution while sessions hold it as `current_channel_id`** — SDK's subscribe stream receives the dissolution; subsequent ops from stale SessionContext fail with `DpError::ChannelDissolved`; feature code re-binds session to parent or a new cell.

### Redis Stream schema

```
Stream key:   dp:channel_changes:{reality_id}
Entry shape (MessagePack):
{
  "v": 1,
  "op": "insert" | "update" | "dissolve",
  "channel_id": "<uuid>",
  "parent": "<uuid|null>",
  "level_name": "<string>",
  "lifecycle": "active|dormant|dissolved",
  "version": <monotonic per reality>,
  "at": <unix ms>
}
```

Stream retention: 7 days or 1M entries per reality. Consumers (CP + SDK instances) use durable cursors.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch1 | `ChannelId` newtype with module-private constructor; tree structure with level_name tag; max depth 16 |
| DP-Ch2 | `channels` table lives in **per-reality Postgres DB**, not CP; structural invariants enforced by DB constraints |
| DP-Ch3 | CP caches channel tree per reality; delta stream via Redis Stream; degraded-mode behavior |
| DP-Ch4 | `RealityScoped` vs `ChannelScoped` marker traits; `#[derive(Aggregate)]` enforces exactly one; orthogonal to tier |
| DP-Ch5 | Cache key format with scope marker `r`/`c` at position 2; `dp::cache_key!` macro dispatches on scope trait |
| DP-Ch6 | `SessionContext` adds `current_channel_id` + `ancestor_channels` chain; immutable, swapped on `move_session_to_channel` |
| DP-Ch7 | Ancestor walk helpers on SessionContext; complex metadata queries go through Channel aggregate read |
| DP-Ch8 | Channel CRUD primitives on DpClient; DP enforces structural invariants, feature enforces business rules |
| DP-Ch9 | `move_session_to_channel` issues capability refresh + new ancestor chain; feature-level leave/enter events separate |
| DP-Ch10 | Channel-tree-change invalidation via Redis Stream; no re-parenting; stale SessionContext handling on dissolve |

---

## Cross-references

- [DP-A13](02_invariants.md#dp-a13--channel-hierarchy-as-first-class-scope-phase-4-2026-04-25) — the axiom this file implements
- [DP-A14](02_invariants.md#dp-a14--aggregate-scope-reality-scoped-vs-channel-scoped-design-time-choice-phase-4-2026-04-25) — aggregate scope companion axiom
- [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys) — reality boundary; now extended with scope marker
- [DP-K2](04_kernel_api_contract.md#dp-k2--sessioncontext) — SessionContext (now extended — see file 04 diff)
- [DP-C3](05_control_plane_spec.md#dp-c3--grpc-service-surface) — CP gRPC surface (now has `StreamChannelTreeUpdates`)
- [02_storage R4](../02_storage/R04_fleet_ops.md) — per-reality Postgres; channel registry slots into existing sharding
- [02_storage R6](../02_storage/R06_R12_publisher_reliability.md) — outbox publisher used for channel-change events

---

## What Q26 leaves to other Phase 4 items

DP-Ch1..Ch10 give channels a concrete home in the DP contract. Other Phase 4 Qs still need resolution, now unblocked:

| Q | What it adds | Progress |
|---|---|---|
| **Q17** per-channel total event ordering | `channel_event_id` invariant + axiom DP-A15 | ✅ resolved 2026-04-25 in [13_channel_ordering_and_writer.md DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) |
| **Q30** ordering mechanism | Single-writer in-memory counter + DB UNIQUE constraint | ✅ resolved 2026-04-25 in [13 DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) |
| **Q34** channel writer node binding | Cell = creator's node + handoff; non-cell = CP-assigned + epoch fence | ✅ resolved 2026-04-25 in [13 DP-Ch12..Ch14](13_channel_ordering_and_writer.md#dp-ch12--writer-assignment-rules) |
| **Q15** per-channel turn/page boundary | First-class event type + subscribe-completion rule | Unblocked |
| **Q16** durable per-channel subscribe | `subscribe_channel_events_durable(ctx, channel_id, from_event_id)` | Unblocked |
| **Q27** event bubble-up | Aggregator at parent channel reading descendant events | Unblocked |
| **Q28** membership ops | T3 events for join/leave; feature-level validation | Unblocked (Ch8/Ch9 give structural primitives) |
| **Q31** channel lifecycle | Active/Dormant/Dissolved transitions + archive | ✅ resolved 2026-04-25 in [17_channel_lifecycle.md](17_channel_lifecycle.md) DP-Ch31..Ch37 |
| **Q18** T1 reframe for channel presence | T1 aggregate examples (typing indicator, presence) | Unblocked |
| **Q19** per-channel pause | `channel_pause(ctx, channel_id, reason)` + write-rejection | Unblocked |
| **Q32** privacy bubble-up | Channel visibility flag in metadata; bubble-up respects | Unblocked (metadata field supports it) |

Resolution order in Phase 4 continues with Q17 + Q30 + Q34 next (per-channel ordering + writer binding).
