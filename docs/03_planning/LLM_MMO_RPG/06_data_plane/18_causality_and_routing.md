# 18 — Causality Token + Session-Writer Routing UX (DP-Ch38..DP-Ch42)

> **Status:** LOCKED (Phase 4, 2026-04-25). Resolves [99_open_questions.md Q21 + Q22](99_open_questions.md) — intra-session read-your-writes consistency across service boundaries (Q21) and session-writer transparent-routing UX on stale gateway routing (Q22). Implements [DP-A19](02_invariants.md#dp-a19--intra-session-causality-preservation-via-opaque-token-phase-4-2026-04-25).
> **Stable IDs:** DP-Ch38..DP-Ch42.

---

## Reading this file

Two operational gaps clustered here because they share a common audience — feature designers building services that interact within a session. Q21 covers cross-service correctness (read-your-writes); Q22 covers cross-node correctness (stale routing).

- DP-Ch38: `CausalityToken` type
- DP-Ch39: `wait_for_token` semantics + projection-apply checkpoint
- DP-Ch40: read-primitive extension with `wait_for` parameter
- DP-Ch41: Session-writer transparent routing (extends DP-Ch14 pattern from channel writers to session writers)
- DP-Ch42: Routing failure UX, error taxonomy, gateway contract

---

## DP-Ch38 — `CausalityToken` type

### Definition

```rust
/// Opaque token issued by DP on successful T2/T3 write acks. Cannot be
/// constructed by feature code — module-private constructor. Hand off
/// to other services via RPC arg or message-bus payload to preserve
/// read-your-writes across the service boundary.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct CausalityToken {
    pub(crate) reality_id: RealityId,
    pub(crate) scope: TokenScope,
    pub(crate) event_id: u64,         // channel_event_id for Channel scope; event_log id for Reality scope
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) enum TokenScope {
    Reality,
    Channel { channel_id: ChannelId },
}

impl CausalityToken {
    pub(crate) fn new_reality(reality_id: RealityId, event_id: u64) -> Self { /* ... */ }
    pub(crate) fn new_channel(reality_id: RealityId, channel_id: ChannelId, event_id: u64) -> Self { /* ... */ }
}
```

`CausalityToken` is `Serialize + Deserialize` so it travels over gRPC and message-bus payloads safely. Encoded form is opaque — feature code does not parse, compare, or compose tokens.

### Where tokens come from

Existing ack types are extended:

```rust
pub struct T2Ack {
    pub event_id: EventId,                          // existing
    pub applied_at_projection: Option<Instant>,     // existing
    pub causality_token: CausalityToken,            // NEW Phase 4 (DP-Ch38)
}

pub struct T3Ack {
    pub event_id: EventId,                          // existing
    pub applied_at_projection: Instant,             // existing
    pub invalidation_fanout_ms: Duration,           // existing
    pub causality_token: CausalityToken,            // NEW Phase 4 (DP-Ch38)
}

pub struct MultiAck {
    pub txn_id: TxnId,                              // existing
    pub event_ids: Vec<EventId>,                    // existing
    pub applied_at: Instant,                        // existing
    pub causality_token: CausalityToken,            // NEW Phase 4 (DP-Ch38) — covers all ops in the transaction
}

pub struct PauseAck { /* DP-Ch35 */ pub causality_token: CausalityToken, }
pub struct TurnAck  { /* DP-Ch21 */ pub causality_token: CausalityToken, }
```

T0 (ephemeral) writes do not produce a token — there's nothing to wait for. T1 (volatile) writes do not produce a token by default — T1 has its own broadcast path; if a feature genuinely needs RYW for a T1 aggregate, it should use T2.

### Cross-scope hand-off

A T2 channel-scoped write produces a `CausalityToken` with `scope = Channel { channel_id }`. The reader can use it on `read_projection_channel<A: ChannelScoped>(...)` for the **same channel** OR on `read_projection_reality<B: RealityScoped>(...)` for the same reality (the token still bounds the projection's overall progress).

A T2 reality-scoped write produces `scope = Reality`; reader can wait on it for any read in that reality.

Cross-reality tokens are rejected at runtime with `DpError::RealityMismatch`.

---

## DP-Ch39 — `wait_for_token` semantics + projection-apply checkpoint

### Checkpoint table

A new per-reality DB table tracks the projection-applier's progress:

```sql
CREATE TABLE projection_apply_state (
    reality_id              UUID NOT NULL,
    channel_id              UUID,                            -- NULL = reality-scoped
    last_applied_event_id   BIGINT NOT NULL DEFAULT 0,
    last_applied_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (reality_id, channel_id)
);

CREATE INDEX projection_apply_state_idx
    ON projection_apply_state(reality_id, channel_id, last_applied_event_id);
```

Updated by the existing projection-applier from [02_storage R2](../02_storage/R02_projection_rebuild.md) on every batch commit. Maintaining this checkpoint is cheap (one UPDATE per batch). Read-side cost is one indexed lookup per `wait_for` call.

### Wait algorithm

```rust
async fn wait_for_token(
    ctx: &SessionContext,
    token: &CausalityToken,
    timeout: Duration,
) -> Result<(), DpError> {
    // Validate token reality matches session reality.
    if token.reality_id != *ctx.reality_id() {
        return Err(DpError::RealityMismatch { /* ... */ });
    }

    let deadline = Instant::now() + timeout;
    let mut attempt: u32 = 0;

    loop {
        // Cheap checkpoint query.
        let row = match &token.scope {
            TokenScope::Reality => {
                self.db.query_one(
                    "SELECT last_applied_event_id FROM projection_apply_state
                     WHERE reality_id = $1 AND channel_id IS NULL",
                    &[ctx.reality_id()],
                ).await
            }
            TokenScope::Channel { channel_id } => {
                self.db.query_one(
                    "SELECT last_applied_event_id FROM projection_apply_state
                     WHERE reality_id = $1 AND channel_id = $2",
                    &[ctx.reality_id(), channel_id],
                ).await
            }
        }?;

        let last_applied: u64 = row.get(0);
        if last_applied >= token.event_id {
            return Ok(());
        }

        let now = Instant::now();
        if now >= deadline {
            return Err(DpError::CausalityWaitTimeout {
                token: token.clone(),
                last_applied,
                requested: token.event_id,
                waited: timeout,
            });
        }

        // Backoff: 10 ms, 20 ms, 40 ms, ..., capped at 100 ms.
        let backoff = Duration::from_millis(min(100, 10 * (1 + attempt))) as u64;
        let next_wake = now + backoff;
        tokio::time::sleep(min(deadline - now, backoff)).await;
        attempt += 1;
    }
}
```

### Why polling, not subscribing

Subscribe-based wait would open a brief durable subscribe (Q16) on the channel and wait for the token's event to appear. More efficient under high write rate but more complex.

For the turn-based scale (1-10 events/s/channel typical, 100/s peak), **polling with a fast checkpoint query is sufficient and simpler.** Polling cost: ~1 indexed lookup per 10ms during wait, max 5s total = ~500 lookups worst case, in practice <10 because typical projection lag is ≤1 s.

If a future profile shows polling overhead is significant at scale, a subscribe-based variant can be added without breaking the API (`wait_for` parameter shape unchanged).

### Timeout policy

- **Default:** 5 seconds. Sufficient for typical projection lag (≤1 s p99) plus comfortable safety margin.
- **Caller override:** read primitives accept an optional `causality_timeout: Duration` argument.
- **Exceeded:** returns `DpError::CausalityWaitTimeout` with diagnostics (token's event_id, observed last_applied, time waited). Caller decides: retry, surface as user-facing "system slow", or fail.

### Edge cases

| Scenario | Behavior |
|---|---|
| Token's event_id ≤ last_applied at first check | Returns immediately, no sleep |
| Projection-applier offline (no progress) | Times out at deadline; surfaces as outage to caller |
| Token from a Dissolved channel | Channel's projection-apply state is preserved through retention; token still works on a dissolved channel's reads |
| Token belongs to a write that was rolled back | Impossible — token is only handed out on successful ack; rolled-back writes don't produce tokens |
| Multiple tokens passed (rare) | Caller picks the latest; SDK doesn't accept array of tokens (would imply join semantics; out of scope) |

---

## DP-Ch40 — Read-primitive extension with `wait_for` parameter

### Updated signatures

```rust
/// Phase 4 extension: optional wait_for + causality_timeout.
pub async fn read_projection_reality<A: RealityScoped>(
    ctx: &SessionContext,
    id: A::Id,
    wait_for: Option<&CausalityToken>,                  // NEW Phase 4
    causality_timeout: Option<Duration>,                // NEW Phase 4 (default 5 s)
) -> Result<A::Projection, DpError>;

pub async fn read_projection_channel<A: ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    id: A::Id,
    wait_for: Option<&CausalityToken>,                  // NEW Phase 4
    causality_timeout: Option<Duration>,                // NEW Phase 4 (default 5 s)
) -> Result<A::Projection, DpError>;

pub async fn query_scoped_reality<A: RealityScoped>(
    ctx: &SessionContext,
    predicate: Predicate<A>,
    limit: usize,
    wait_for: Option<&CausalityToken>,                  // NEW Phase 4
    causality_timeout: Option<Duration>,                // NEW Phase 4
) -> Result<Vec<A::Projection>, DpError>;

pub async fn query_scoped_channel<A: ChannelScoped>(
    ctx: &SessionContext,
    channel: &ChannelId,
    predicate: Predicate<A>,
    limit: usize,
    wait_for: Option<&CausalityToken>,                  // NEW Phase 4
    causality_timeout: Option<Duration>,                // NEW Phase 4
) -> Result<Vec<A::Projection>, DpError>;
```

`wait_for = None` (the default) keeps prior eventual-consistency semantics. Only callers who explicitly opt in pay the projection-wait cost.

### Ergonomic alternative: builder pattern (suggestion, not locked)

For features that find positional args verbose, the SDK can expose a fluent builder:

```rust
// Equivalent to read_projection_channel above but without positional defaults clutter:
let projection = dp
    .read::<MyAggregate>()
    .channel(&channel_id)
    .id(id)
    .wait_for(token)
    .causality_timeout(Duration::from_secs(2))
    .await?;
```

The fluent form is implementation-level; the contract is the underlying free-function signatures listed above.

### Composition with `dp::instrumented!` macro

The instrumentation macro (`dp::instrumented!`, see [DP-K8](04_kernel_api_contract.md#dp-k8--dpinstrumented-telemetry-macro)) records `causality_wait_ms` as a separate label on the read latency histogram. Distinguishes "fast read on cached projection" from "slow read waiting on causality token" in dashboards.

---

## DP-Ch41 — Session-writer transparent routing

### The problem

[DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes) requires session-sticky routing — the node hosting a player session is the sole writer for T1 / RealityScoped state on that session. Gateway uses session-sticky routing (cookie or hash); under normal operation, requests reach the right node.

Failure modes:
- Gateway's sticky cookie expired → request hits a different node
- Session migrated (node death + handoff per DP-F2) but gateway hasn't refreshed routing
- LB glitch / connection pool reuse misrouted

The receiving node returns `DpError::WrongWriterNode { owner, current }`. The caller (gateway or another service) needs to retry. Q22 spec: SDK transparently auto-routes, mirroring the channel-writer routing in [DP-Ch14](13_channel_ordering_and_writer.md#dp-ch14--cross-node-write-routing).

### Routing dispatch (extends DP-Ch14 pattern)

```rust
async fn t1_write<A: T1Aggregate>(
    ctx: &SessionContext,
    id: A::Id,
    delta: A::Delta,
) -> Result<(), DpError> {
    let session_owner = self.session_route_cache.get(ctx.session_id()).await
        .or_else(|| self.cp.get_session_node(ctx.session_id()))
        .await?;

    if session_owner == self.local_node_id {
        // local fast path
        self.write_t1_local(ctx, id, delta).await
    } else {
        // route to session owner via internal gRPC
        self.route_to_session_node(ctx, &session_owner, /* request payload */).await
    }
}

async fn route_to_session_node(
    ctx: &SessionContext,
    target: &NodeId,
    /* payload */: ...,
) -> Result<_, DpError> {
    match grpc_client_for(target).route_session_write(...).await {
        Ok(ack) => Ok(ack),
        Err(e) if is_unreachable(&e) => {
            // Refresh from CP (session may have migrated), retry once.
            self.session_route_cache.invalidate(ctx.session_id());
            let new_owner = self.cp.get_session_node(ctx.session_id()).await?;
            if new_owner != *target {
                grpc_client_for(&new_owner).route_session_write(...).await
                    .map_err(DpError::from)
            } else {
                // Same target unreachable on retry: circuit open.
                Err(DpError::CircuitOpen { service: "session_router" })
            }
        }
        Err(e) => Err(DpError::from(e)),
    }
}
```

### gRPC method (internal routing)

Each game node exposes:

```protobuf
service DpInternalRouting {
  rpc RouteChannelWrite (RouteChannelWriteRequest) returns (RouteChannelWriteResponse);   // existing DP-Ch14
  rpc RouteSessionWrite (RouteSessionWriteRequest) returns (RouteSessionWriteResponse);   // NEW DP-Ch41
}

message RouteSessionWriteRequest {
  bytes serialized_session_context = 1;
  string operation = 2;             // "t1_write", "t2_write_reality", etc.
  string aggregate_type = 3;
  bytes serialized_id = 4;
  bytes serialized_delta = 5;
}
```

Receiving node verifies the forwarded SessionContext (capability JWT signature + reality match) — the capability already encodes service authorization for the operation.

### Session route cache

SDK maintains `session_route_cache: HashMap<SessionId, NodeId>` with:
- TTL: **300 seconds** (longer than channel writer cache because sessions migrate less frequently)
- Invalidation: on routing failure (auto-refresh from CP)
- Population: on first session activity + opportunistic refresh on bind_session response

### Latency cost

~5 ms LAN hop added when caller is not the session owner. Session writes are typically already on the right node (gateway's sticky routing works most of the time), so the hop happens rarely.

---

## DP-Ch42 — Routing failure UX + error taxonomy + gateway contract

### Error taxonomy

| Error | Meaning | Caller action |
|---|---|---|
| `WrongWriterNode { owner, current }` | Surface only when transparent routing is disabled or fails after retry. Normally SDK absorbs. | Caller refreshes session context and retries; or surfaces to user. |
| `WrongChannelWriter { channel, expected, stale_epoch }` (DP-Ch14) | Same pattern for channel writes. | Same. |
| `CircuitOpen { service: "session_router" }` | Auto-routing failed twice (target unreachable on first attempt, refreshed target also unreachable). | Treat as transient — retry with exponential backoff at caller level. |
| `SessionNotFound { session_id }` | CP has no record of this session — likely expired or never bound. | Caller must re-bind via `bind_session`. |
| `CausalityWaitTimeout { token, last_applied, requested, waited }` | wait_for exceeded timeout. | Caller decides — retry with longer timeout, surface as user-facing slow-system, or accept stale read by re-issuing without wait_for. |
| `RealityMismatch { ctx, requested }` (existing) | Token from one reality used in a context bound to a different reality. | Caller bug — typed handoff broke. |

### Retry budget

Both routing primitives (DP-Ch14 channel writes, DP-Ch41 session writes) follow the same budget:
- **1 automatic retry** by SDK on routing failure (refresh from CP, retry once)
- Beyond → `CircuitOpen` bubbles up
- Caller-level retry (gateway, feature code) is independent of SDK's auto-retry

### Gateway contract

DP makes no assumptions about gateway internals beyond:

1. **Gateway routes session-bound requests to a specific node** based on its own sticky-routing discipline (cookie, hash, etc.).
2. **Gateway's routing may go stale.** When that happens, the request hits the wrong node.
3. **DP's SDK absorbs the staleness transparently** by auto-routing to the correct node (DP-Ch41).
4. **Gateway should refresh its routing cache** on receiving the SDK's response if the response includes a `routed: { from, to }` hint header — but this is a hint, not a contract obligation. SDK functions correctly even if gateway never refreshes.

The hint header (optional, gateway-level optimization):

```
X-Dp-Session-Route-Hint: from=node-7,to=node-12
```

Gateway implementations may consume this to update their routing table, or ignore it. DP doesn't observe gateway's behavior either way.

### Implications for feature code

Feature code mostly **does not see routing errors** — SDK handles transparently. The exceptions:

- After 1 SDK retry fails: `CircuitOpen { service }` — feature should surface to user as "service slow, please retry".
- Session expired: `SessionNotFound` — feature must re-bind. Typically only happens at long player idle.

For Phase 5 (operator concerns) — gateway-cache-staleness rate is a metric to track. High staleness rate suggests gateway routing discipline is broken; investigate.

---

## Summary

| ID | What it locks |
|---|---|
| DP-Ch38 | `CausalityToken` opaque newtype (module-private constructor); attached to T2/T3/Multi/Pause/Turn acks; cross-scope handoff (Channel token can wait Reality reads in same reality) |
| DP-Ch39 | `wait_for_token` algorithm: poll `projection_apply_state` checkpoint table with backoff; default 5 s timeout; `CausalityWaitTimeout` on exceed; new per-reality DB table for projection-applier progress |
| DP-Ch40 | Read primitives extended with optional `wait_for: Option<&CausalityToken>` + `causality_timeout: Option<Duration>`; default None preserves prior eventual-consistency semantics; instrumentation records `causality_wait_ms` |
| DP-Ch41 | Session-writer transparent routing extends DP-Ch14 pattern: SDK detects WrongWriterNode, auto-routes to session owner via `RouteSessionWrite` gRPC; 300 s session route cache; refresh-on-fail then 1 retry |
| DP-Ch42 | Error taxonomy + retry budget (1 SDK auto-retry → CircuitOpen on second failure); gateway contract documented as best-effort hint-based; SDK absorbs stale gateway routing transparently |

---

## Cross-references

- [DP-A11](02_invariants.md#dp-a11--session-node-owns-t1-writes) — session sticky writer this file extends
- [DP-A19](02_invariants.md#dp-a19--intra-session-causality-preservation-via-opaque-token-phase-4-2026-04-25) — invariant this file implements
- [DP-K3](04_kernel_api_contract.md#dp-k3--dperror-enum) — DpError variants extended (CausalityWaitTimeout, SessionNotFound)
- [DP-K4](04_kernel_api_contract.md#dp-k4--read-primitives) — read primitive signatures extended
- [DP-K8](04_kernel_api_contract.md#dp-k8--dpinstrumented-telemetry-macro) — instrumentation extended with causality_wait_ms label
- [DP-Ch14](13_channel_ordering_and_writer.md#dp-ch14--cross-node-write-routing) — channel-writer routing pattern this file mirrors for sessions
- [02_storage R2](../02_storage/R02_projection_rebuild.md) — projection applier maintains the checkpoint table introduced here
- [DP-F2](07_failure_and_recovery.md#dp-f2--game-node-death--session-handoff) — session migration on node death; routing-cache invalidation tracks this

---

## What this leaves to other Phase 4 items

| Q | Phase 4 progress |
|---|---|
| **Q21 RYW cross-service** | ✅ Resolved here (DP-Ch38..Ch40). |
| **Q22 routing UX** | ✅ Resolved here (DP-Ch41..Ch42). |
| **Q29 fan-out at high channels** | Independent — operational tuning concern; ops doc territory. |
| **Q32 privacy formalization** | Independent — extends DP-Ch30 with policy templates; no overlap. |
| **Q20 LLM latency** | Deferred until V1 prototype data. |
