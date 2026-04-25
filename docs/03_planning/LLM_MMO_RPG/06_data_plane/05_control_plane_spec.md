# 05 — Control Plane Specification (DP-C1..DP-C10)

> **Status:** LOCKED (Phase 2). Defines the thin control-plane service that owns policy, schema coordination, credential issuance, and invalidation broadcast — but is **never on the hot path** ([DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split)). All data-plane reads and writes happen without CP involvement.
> **Stable IDs:** DP-C1..DP-C10. Partial resolution of [Q5](99_open_questions.md) (schema migration), [Q6](99_open_questions.md) (cold start), [Q9](99_open_questions.md) (capability issuance).

---

## DP-C1 — Responsibilities

The control plane (CP) owns exactly these concerns. Anything not listed is explicitly NOT its job.

| Concern | Responsibility |
|---|---|
| **Tier policy registry** | Authoritative record of which aggregate types exist, which tiers each supports, and which services have capability to read/write each at each tier. |
| **Schema coordination** | Gate schema changes: version numbers, compatibility windows, rolling-deploy sequencing, projection rebuild triggers. |
| **Capability issuance** | Sign JWTs (DP-K9) issued on `bind_session`, `verify_reality`, and `refresh_capability` RPCs. |
| **Invalidation broadcast orchestration** | Accept invalidation events from T3-write paths; fan them out via Redis pub/sub (not directly by CP — CP publishes once, Redis does fan-out). |
| **Cold-start coordination** | When a reality transitions frozen → active, CP warms the tier policy cache, signals subscribed services to prepare, and logs the transition. |
| **Session stickiness routing table** | NPC-to-node binding (DP-A11) and session-to-node lookup. Low-QPS, cache-friendly. |
| **Reality registry** | Maps `reality_id` → per-reality Postgres/Redis endpoints. Consumed at `DpClient::connect` and on reality open/freeze transitions. |
| **Channel tree cache (Phase 4)** | Per-reality in-memory cache of the channel tree + ancestor-chain lookups. Consumed by SDKs at `bind_session` and updated via Redis Stream consumption. Authoritative source is per-reality DB, not CP. See [DP-Ch3](12_channel_primitives.md#dp-ch3--cp-channel-tree-cache--delta-stream). |
| **Channel writer binding + handoff (Phase 4)** | One writer node per active channel; CP issues + revokes leases (epoch tokens), assigns writer at channel creation, coordinates cell handoff on creator-leave, reassigns on node death. Cached in same channel-tree structure. See [DP-A16](02_invariants.md#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) + [13_channel_ordering_and_writer.md](13_channel_ordering_and_writer.md). |
| **Bubble-up aggregator registry (Phase 4)** | Per-reality persistent registry of registered bubble-up aggregators. Restart-resilient: writer-node assignment loads aggregators + snapshots from per-reality DB. Delta updates flow on the channel-tree-update stream. See [DP-Ch28](16_bubble_up_aggregator.md#dp-ch28--cp-aggregator-registry--restart-restoration). |
| **Degraded-mode signaling** | On CP outage or partition, signal data plane to enter degraded mode (DP-C9). |

**NOT CP responsibilities:**

- Reading or writing aggregate state (that is DP SDK's job)
- Serving projection queries (SDK reads Postgres directly via credentials CP issued)
- Running the event log (that is 02_storage's job, consumed by SDK)
- Session state of any kind (sessions live in game services + Redis)
- LLM proposal bus (out of DP scope entirely)

---

## DP-C2 — Deployment model

**Process:** dedicated Rust service, single binary, gRPC server.

**Replication:** 2-node active-passive with etcd-based leader election. Active node handles all writes (tier policy mutations, schema migrations, capability signing key rotation). Passive node serves reads from replicated state and is ready to promote on failover.

**Storage:** CP's own small Postgres database (~100 MB working set at V3) storing:
- `tier_policy` table
- `reality_registry` table
- `npc_binding` table
- `schema_version` table
- `capability_signing_keys` table (rotated quarterly)
- `deploy_cohort` table (for schema migration sequencing)

**Failover latency:** ≤60 seconds (active dies → etcd detects → passive promotes → warm caches → serve). During this window, data plane runs in degraded mode (DP-C9).

**HA scope:** Single-region for V1/V2. Cross-region DR deferred to V3 aligned with 02_storage C3 meta-registry HA approach.

---

## DP-C3 — gRPC service surface

CP exposes a single gRPC service `DpControlPlane`. All methods are low-QPS (≤100/s global in normal operation).

```protobuf
service DpControlPlane {
  // Session + capability lifecycle
  rpc VerifyReality (VerifyRealityRequest) returns (VerifyRealityResponse);
  rpc BindSession (BindSessionRequest) returns (BindSessionResponse);
  rpc RefreshCapability (RefreshCapabilityRequest) returns (RefreshCapabilityResponse);

  // Policy
  rpc GetTierPolicy (GetTierPolicyRequest) returns (TierPolicySnapshot);
  rpc StreamTierPolicyUpdates (StreamTierPolicyRequest) returns (stream TierPolicyDelta);

  // Reality registry
  rpc ResolveReality (ResolveRealityRequest) returns (RealityEndpoints);
  rpc StreamRealityTransitions (StreamRealityTransitionsRequest) returns (stream RealityTransition);

  // Channel tree (Phase 4)
  rpc GetChannelTree (GetChannelTreeRequest) returns (ChannelTreeSnapshot);
  rpc StreamChannelTreeUpdates (StreamChannelTreeRequest) returns (stream ChannelTreeDelta);
  rpc ResolveAncestorChain (ResolveAncestorChainRequest) returns (AncestorChain);

  // Channel writer binding (Phase 4 DP-A16)
  rpc GetChannelWriter (GetChannelWriterRequest) returns (ChannelWriterLease);
  rpc RequestWriterHandoff (RequestWriterHandoffRequest) returns (Empty);
  rpc HeartbeatWriterLease (HeartbeatWriterLeaseRequest) returns (Empty);

  // Bubble-up aggregator registry (Phase 4 DP-Ch28)
  rpc RegisterBubbleUpAggregator (RegisterAggregatorRequest) returns (AggregatorHandle);
  rpc UnregisterBubbleUpAggregator (UnregisterAggregatorRequest) returns (Empty);
  rpc ListAggregatorsForChannel (ListAggregatorsRequest) returns (AggregatorList);

  // Session stickiness + NPC binding
  rpc GetSessionNode (GetSessionNodeRequest) returns (NodeAssignment);
  rpc GetNpcNode (GetNpcNodeRequest) returns (NodeAssignment);
  rpc ReportNodeHandoff (ReportNodeHandoffRequest) returns (Empty);

  // Schema + migration
  rpc GetSchemaVersion (GetSchemaVersionRequest) returns (SchemaVersion);
  rpc AnnounceMigrationStart (AnnounceMigrationStartRequest) returns (Empty);
  rpc AnnounceMigrationComplete (AnnounceMigrationCompleteRequest) returns (Empty);

  // Health / degraded mode
  rpc Health (Empty) returns (HealthReport);
}
```

**Transport:** gRPC over mTLS between CP and game services. Service-to-service auth uses mTLS certs issued via the existing service-to-service auth infrastructure ([02_storage/S11](../02_storage/S11_service_to_service_auth.md)).

**Debug endpoints:** HTTP/JSON sidecar server (port offset +1) exposes read-only versions of the same methods for operator debugging; write methods not exposed on HTTP.

---

## DP-C4 — Tier policy registry

The authoritative record of every aggregate type that exists in the system.

```sql
-- CP's own Postgres
CREATE TABLE tier_policy (
    aggregate_type    TEXT PRIMARY KEY,
    declared_tier     TEXT NOT NULL CHECK (declared_tier IN ('T0','T1','T2','T3')),
    schema_version    INT NOT NULL,
    feature_owner     TEXT NOT NULL,          -- which feature owns this aggregate
    registered_at     TIMESTAMPTZ NOT NULL,
    last_migration_at TIMESTAMPTZ,
    notes             TEXT                     -- design rationale, cross-ref to feature doc
);

CREATE TABLE tier_capability (
    service_id        TEXT NOT NULL,
    aggregate_type    TEXT NOT NULL REFERENCES tier_policy(aggregate_type),
    tiers_allowed     TEXT[] NOT NULL,         -- subset of {T0,T1,T2,T3}
    can_read          BOOL NOT NULL,
    can_write         BOOL NOT NULL,
    granted_at        TIMESTAMPTZ NOT NULL,
    revoked_at        TIMESTAMPTZ,
    PRIMARY KEY (service_id, aggregate_type)
);
```

**Registration flow:** When a feature lands a new aggregate type, its deploy manifest calls CP's admin API (offline, not gRPC — see DP-C10) to INSERT into `tier_policy` + `tier_capability` rows. Re-deploy without this step fails at `DpClient::connect` because the tier policy snapshot doesn't contain the aggregate.

**Tier mutation:** Changing an aggregate's declared tier is a schema migration (DP-C5), not an UPDATE. Migration produces a new aggregate type with version suffix, dual-writes during transition, then retires the old.

**Capability changes:** Granting a new service access to an existing aggregate is an UPDATE (INSERT new `tier_capability` row). Revoking is UPDATE setting `revoked_at` — subsequent `bind_session` calls produce JWTs without the revoked capability; next `refresh_capability` drops it.

---

## DP-C5 — Schema migration coordination

Resolves [Q5](99_open_questions.md) at the protocol level. Implementation details (projection rebuild, outbox replay) remain in [02_storage/R02, R03](../02_storage/).

**Migration protocol — Expand / Migrate / Contract:**

1. **Expand phase (no downtime):**
   - Feature deploys new SDK version `N+1` that reads both old schema `v_k` and new schema `v_{k+1}`, writes `v_{k+1}` shape.
   - CP marks `tier_policy.schema_version = k+1` with a "both active" flag.
   - Rolling deploy brings services from `N` to `N+1`. During rolling window, mix of writers produce both shapes; all readers accept both.

2. **Migrate phase (background):**
   - 02_storage's projection rebuild machinery (R02) rewrites existing `v_k` projected rows into `v_{k+1}` shape.
   - CP polls rebuild progress via an admin RPC; does not block the data plane.
   - Invalidation broadcast fires on each batch completion so readers re-populate cache from updated projection.

3. **Contract phase (opt-in cleanup):**
   - Once rebuild is ≥99.9% complete and all N-1 services are drained, a manual CP action flips `tier_policy.schema_version = k+1` without the "both active" flag.
   - Next `N+2` SDK release drops read support for `v_k`.

**CP is never in the synchronous path of a write during migration.** Writers pick their shape from cached tier policy (refreshed on the 60s schedule or on explicit `StreamTierPolicyUpdates` push), not by calling CP per-write.

**Catastrophic migration** (breaking change, no dual-read feasible):
- Acknowledged rare. Requires reality-freeze window (per 02_storage R9 lifecycle), drain, rebuild, unfreeze. CP coordinates the freeze via `ReportNodeHandoff` and the reality registry state machine.

---

## DP-C6 — Invalidation broadcast orchestration

CP **does not** fan out invalidations to every subscriber itself — that would put CP on the hot path. Instead:

**Write-time flow:**

1. `t3_write` commits to the per-reality Postgres (event log + projection).
2. SDK issues a Redis `PUBLISH` to `dp:inval:{reality_id}` with payload `{aggregate_type, id, at}`.
3. All SDK instances subscribed to that channel drop the affected cache entry (details in [06_cache_coherency.md](06_cache_coherency.md)).
4. CP is notified asynchronously via a Redis stream `dp:inval:audit:{reality_id}` for audit / observability only — it does not gate the write.

**CP's role:** maintain the list of channels (one per active reality), ensure Redis pub/sub capacity is sized correctly (see [08_scale_and_slos.md DP-S8](08_scale_and_slos.md#dp-s8--resource-ceilings-per-reality) pub/sub fan-out budget), and alert on channel backlog.

**Reality-level routing:** channels keyed by `reality_id` prevent one noisy reality from saturating subscribers of quiet realities. Aligns with [DP-A7](02_invariants.md#dp-a7--reality-boundary-in-cache-keys).

---

## DP-C7 — Cold-start coordination

Resolves [Q6](99_open_questions.md) at the protocol level.

**Trigger:** first player connection to a reality that was previously frozen (no active players). Latency target: ≤10s to ready state per [DP-S2](08_scale_and_slos.md#dp-s2--latency-budget-client-perceived).

**Protocol:**

1. Gateway receives player connect. Looks up reality status from reality registry (cached or fresh RPC to CP).
2. If reality is `frozen`, gateway sends a `WakeReality(reality_id)` signal to CP.
3. CP:
   a. Transitions `reality_registry.status = warming`
   b. Resolves per-reality Postgres/Redis endpoints, notifies game service(s) via `StreamRealityTransitions` push.
   c. Pre-warms the tier policy cache for this reality in the subscribing services' SDKs.
   d. Signals game service to proactively populate cache for known hot aggregates (per reality-specific hotset, maintained by CP based on last-freeze snapshot).
4. Game service binds first session (via `BindSession`). Cache warms lazily on first reads; hotset pre-warm runs in parallel.
5. Once the game service reports ready (via a health ping), CP transitions reality to `active`.

**Degraded path (CP unavailable):**

- Game service falls back to "reactive warm" — start serving from cold cache, first reads hit Postgres projection. Higher tail latency for the first 30–60 seconds but the reality is usable.
- Without CP, the reality cannot transition `frozen → warming` in the registry; gateway must queue the player connect or serve a "reality warming" user-facing error.

---

## DP-C8 — Capability issuance + rotation

### Signing key lifecycle

- CP holds the active capability signing key (RS256 or Ed25519). Rotated quarterly.
- Old signing keys retained as "verifying-only" for 2× the max capability lifetime (10 minutes) after rotation — JWTs issued just before rotation remain valid until they expire.
- Signing key storage: CP's Postgres, row-level encrypted with KMS.

### Issuance flow (summary)

For the full sequence see DP-K9 (SDK side) and DP-C3 (gRPC surface).

1. Game service calls `BindSession(reality_id, session_id)`.
2. CP validates:
   - Service identity (mTLS cert)
   - Service is authorized for this `aggregate_type` set (from `tier_capability` table)
   - Reality exists and is active
3. CP constructs claims (DP-K9 format), signs JWT, returns to caller.
4. Game service caches JWT in `SessionContext`; refresh 60s before `exp`.

### Revocation

- Immediate revocation requires: (a) remove the session's row from session registry (which invalidates future reads from other nodes); (b) rotate the signing key if the revocation is broad (e.g., security incident).
- Short expiry (5 min) bounds blast radius — no explicit JWT revocation list needed in the normal case.

### Capability denial

When a capability doesn't authorize an op, SDK returns `DpError::CapabilityDenied { aggregate, tier }`. CP receives an audit event via a fire-and-forget gRPC stream (not blocking the SDK response).

---

## DP-C9 — Degraded mode

What the data plane does when CP is unreachable. Locked at the axiom level by [DP-S7](08_scale_and_slos.md#dp-s7--availability-targets) ("failure of the control plane does NOT make the data plane unavailable").

**During CP outage, data plane:**

- **Continues** serving reads and writes using the last-known tier policy snapshot (SDKs cache it, refreshed every 60s; stale OK for minutes).
- **Continues** invalidation broadcast (SDKs publish to Redis directly; CP only audits).
- **Continues** existing session operations until capabilities expire (5 min).
- **Rejects** new `BindSession` calls that would require a fresh JWT. Existing sessions run to expiry; no new player connections accepted to realities not already in their local session registry.
- **Rejects** `verify_reality` calls. New gateway-forwarded player requests fail until CP recovers.
- **Rejects** `t3_write_multi` cross-aggregate writes that require CP-coordinated atomicity (single-aggregate T3 writes still work — they only need Postgres + Redis).

**Degraded-mode signals:**

- SDK detects CP unreachability via gRPC connection state + a dedicated health probe every 10s.
- On detection, SDK emits metric `dp.control_plane.reachable = 0` and structured log; background capability refresh is paused.
- On reconnection, SDK resumes refresh, re-fetches tier policy delta, processes any queued audit events.

**Degraded-mode upper bound:** realistic ceiling is ~60 minutes before the system becomes significantly degraded (stale tier policy + increasing ratio of expired capabilities). V1/V2 targets CP outage ≤15 min; V3 with HA targets ≤5 min typical.

---

## DP-C10 — HA, failover, admin interface

### HA model

- 2-node active-passive (V1/V2). Promoted to 3-node (1 active, 2 passive, quorum writes) at V3.
- Leader election via etcd (separate cluster or reuse platform etcd). Session TTL 5s; detection of active loss in ≤10s; promotion + warm in ≤60s.
- Passive nodes serve **read-only** gRPC methods (all methods in DP-C3 except `*Announce*` and `ReportNodeHandoff`). This lets read-dominated operations (tier policy snapshot fetch, resolve reality) load-balance across passives during healthy operation.

### Admin interface

Separate from the gRPC surface. Operator-only CLI + small web UI for:

- Registering new aggregate types (tier_policy INSERT)
- Granting / revoking tier capabilities
- Initiating schema migrations (expand / migrate / contract)
- Freezing / unfreezing realities (coordinates with 02_storage/R9 lifecycle)
- Rotating signing keys
- Inspecting invalidation audit log
- Inspecting per-reality cache hotset

Admin operations are gated by human approval per [02_storage/R13](../02_storage/R13_admin_discipline.md) and the existing [`ADMIN_ACTION_POLICY.md`](../../02_governance/ADMIN_ACTION_POLICY.md) — this axiom does not create a new governance model, it plugs into the existing one.

### Failover drill

Monthly failover drill triggered via admin CLI:
1. Admin marks active node "draining" → passive promotes.
2. Monitor client-facing latency for 5 minutes.
3. Failback is a second drill event — not automatic after the first node recovers.

---

## Summary

| ID | What it locks |
|---|---|
| DP-C1 | CP responsibilities enumerated; non-responsibilities explicit |
| DP-C2 | 2-node active-passive, own Postgres, ≤60s failover |
| DP-C3 | gRPC surface — 22 methods (13 Phase 2 + 3 Phase 4 channel-tree + 3 Phase 4 writer-binding + 3 Phase 4 aggregator-registry), low-QPS |
| DP-C4 | Tier policy registry schema + registration flow |
| DP-C5 | Expand / Migrate / Contract schema migration protocol |
| DP-C6 | Invalidation broadcast through Redis pub/sub, CP off hot path |
| DP-C7 | Cold-start coordination + degraded fallback |
| DP-C8 | JWT issuance + quarterly signing key rotation + short-expiry revocation model |
| DP-C9 | Degraded mode: continue existing ops, reject new session binds, ≤15 min ceiling |
| DP-C10 | HA: 2→3-node etcd-led, admin CLI plugs into existing admin policy |

---

## Cross-references

- [DP-A2](02_invariants.md#dp-a2--control-plane--data-plane-split) — CP/DP split axiom
- [DP-A4](02_invariants.md#dp-a4--redis-is-the-cache-technology) — Redis for invalidation (not CP)
- [DP-A8](02_invariants.md#dp-a8--durable-tier-delegates-to-02_storage-unchanged) — durable tier in 02_storage unchanged
- [DP-K9](04_kernel_api_contract.md#dp-k9--capability-tokens), [DP-K10](04_kernel_api_contract.md#dp-k10--sdk-initialization-and-session-binding) — SDK side of CP interactions
- [02_storage/R02](../02_storage/R02_projection_rebuild.md) — rebuild machinery DP-C5 orchestrates
- [02_storage/R13](../02_storage/R13_admin_discipline.md), [`ADMIN_ACTION_POLICY.md`](../../02_governance/ADMIN_ACTION_POLICY.md) — admin governance DP-C10 plugs into
- [02_storage/S11](../02_storage/S11_service_to_service_auth.md) — mTLS used by DP-C3
- [06_cache_coherency.md](06_cache_coherency.md) (next) — detailed coherency protocol behind DP-C6

---

## Deferred to Phase 3

- **Cross-region DR** (DP-C2 scope limit) — V3 addition, aligned with [02_storage/C3 meta-registry HA](../02_storage/C03_meta_registry_ha.md).
- **Exact token-bucket parameters** for backpressure ([Q12](99_open_questions.md)) — Phase 3 failure/recovery.
- **Hotset learning algorithm** for cold-start pre-warm (DP-C7) — V2 prototype data required before tuning.
- **Per-reality CP sharding** — V3 if CP QPS approaches limits on single active node (not expected).
