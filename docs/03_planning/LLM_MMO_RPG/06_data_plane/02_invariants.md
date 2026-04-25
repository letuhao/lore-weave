# 02 — Invariants (Axioms)

> **Status:** LOCKED. Every axiom here was decided in a user conversation and may not be changed without a superseding decision recorded in [../decisions/](../decisions/) and a cross-reference entry in [99_open_questions.md](99_open_questions.md).
> **Stable IDs:** DP-A1..DP-A16. These IDs are referenceable from any other doc in this project. Never renumber.

---

## How to use this file

Each axiom below is a locked constraint on every gameplay feature design. When designing a feature:

1. Read every axiom before proposing any kernel access pattern.
2. If a feature requirement appears to conflict with an axiom, escalate — do not work around.
3. When referencing an axiom from another doc, cite it by ID (e.g., "per DP-A3, ...").

Axioms are not principles. They are mechanically checked at design review.

---

## DP-A1 — DP primitives + Rulebook are the only sanctioned path to kernel state

**Rule:** All reads and writes of per-reality kernel state by any game-layer service happen through DP primitive APIs, used according to the DP Access Pattern Rulebook ([11_access_pattern_rules.md](11_access_pattern_rules.md), DP-R1..DP-R8). Feature-specific query logic (feature repos) is built on top of these primitives; DP itself does not own feature query logic (see [DP-A10](#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries)).

**Threat model — IN scope (this axiom enforces against):**

- **Accidental bypass** by an engineer or AI coder writing direct Postgres/Redis access in game-layer code. Enforced at:
  - **Compile-time** — Rust newtypes ([DP-A12](#dp-a12--session-context-gated-access-via-realityid-newtype)) and module privacy (R-1); forbidden imports (R-3); typed tier-specific write APIs (R-5).
  - **Lint-time** — custom clippy rules detect raw `sqlx`/`redis` imports in non-DP crates, hand-built cache keys (R-4), swallowed backpressure errors (R-6).
  - **Review-time** — design checklist rejects missing tier tables (R-2), unexplained direct-DB paths.
- **Cross-service contract violation** — DP primitives are the only APIs sanctioned for touching per-reality kernel state; any feature design that names a non-primitive path is rejected at governance review.

**Threat model — OUT of scope (accepted risk, addressed separately):**

- **Malicious code injection** inside a game service process (RCE): the service process holds DB and cache credentials at the OS level; an attacker with RCE can open direct connections regardless of SDK rules. Defense-in-depth mitigations — network policy (allowed egress hosts/ports only), DB role least-privilege, connection audit logging — are the responsibility of infrastructure and security review, not this axiom.
- **Control plane compromise** — out of scope for DP; a dedicated security review is required when the control plane spec lands (Phase 2).

**Future hardening (roadmap, not Phase 1):**

- **Sidecar credential proxy per game node.** DB and Redis credentials held by a separate process (sidecar); the game service communicates via a local unix socket to the sidecar, which authenticates and forwards. The game service process never holds kernel credentials directly. This converges "no bypass" toward airtight but adds a per-operation latency hop and operational complexity; deferred until V3 benchmark shows the cost is acceptable or a specific incident justifies it.

**Scope:** Per-reality Postgres databases and the game-layer Redis cache namespace. Platform Go services' access to global platform databases (users, books, glossary) is outside DP scope and not governed by this axiom.

---

## DP-A2 — Control Plane / Data Plane split

**Rule:** Policy (tier registry, schema version, invalidation broadcast, cold-start coordination) lives in a thin **control plane** service. Hot-path reads and writes happen in a **data plane** embedded as a library (SDK) inside each game service. The control plane is never on the hot path of a player action.

**Why:** A single-gateway-service model (every read and write RPCs through a dedicated kernel service) adds one network hop per op, creates a SPOF on the hot path, and becomes a throughput bottleneck under MMO load. The CP/DP split delivers "no bypass" via the SDK without paying the hot-path latency cost.

**Enforcement:** SDK APIs for hot-path reads and writes do not require a control-plane call. Control-plane calls happen only at: service startup (register, fetch tier policy), schema-migration events, invalidation broadcast subscribe, cold-start handshake.

---

## DP-A3 — Rust is the game-layer language

**Rule:** Every new game-layer service (world-service, and any future combat/inventory/economy/social/AI-action service) is written in Rust. The DP SDK is Rust-only. No Go or Python binding to the SDK is produced.

**Why:** (a) Rust's compile-time contract enforcement (traits + lifetimes + module privacy) makes DP-A1's "no bypass" airtight — Go reaches only ~80% via `internal/` packages. (b) MMO hot path benefits from Rust's no-GC determinism and lock-free concurrency primitives. (c) Human-learning-curve arguments against Rust do not apply when AI is the coder. (d) Game layer is greenfield — there is no existing Go pattern corpus to copy (existing Go platform services are REST services, not tick servers).

**Consequence:** Platform Go services and LLM Python services remain in their respective languages. Their interaction with game state goes through event bus and gateway, not through the SDK.

---

## DP-A4 — Redis is the cache + pub/sub + streams technology

**Rule:** Redis serves three distinct DP roles:

1. **Shared hot-path cache** (T0 ephemeral excluded; T1/T2/T3 cache hits served from Redis)
2. **Pub/sub for cache invalidation broadcast** (fire-and-forget, idempotent — see [DP-X2](06_cache_coherency.md#dp-x2--invalidation-message-protocol))
3. **Streams for durable per-channel event delivery** (Phase 4 — see [14_durable_subscribe.md DP-Ch17](14_durable_subscribe.md#dp-ch17--hybrid-backing-store))

In-process (per-node) caches are permitted as an optional second cache layer but must be invalidated by Redis pub/sub messages — they are not a separate tier.

**Why:** Redis is mature, already in the LoreWeave stack, supports pub/sub + Streams + TTL natively, and has battle-tested Rust clients (redis-rs, fred). No alternative (NATS JetStream, etcd, custom in-process) offers a strong enough advantage to justify adding a new dependency to the stack. Streams add per-channel event durability (7-day default retention) without introducing a new infrastructure component.

**Topology constraints (partial — full decision deferred):** Per [99_open_questions.md Q3](99_open_questions.md#q3--redis-topology), the exact Redis topology (single cluster vs per-reality instance vs Redis Cluster sharded by reality_id) is open. All DP designs must work under any of these topologies — cache keys and stream keys always include `reality_id` as the first component to allow sharding later.

---

## DP-A5 — Four-tier persistence taxonomy

**Rule:** Every kernel access is classified into exactly one of four tiers at design time:

- **DP-T0 Ephemeral** — memory-only, loss on crash OK, never persisted
- **DP-T1 Volatile** — memory + periodic snapshot, ≤30s loss window OK
- **DP-T2 Durable-async** — write-through cache + async event log, no loss, eventual consistency on cross-session reads
- **DP-T3 Durable-sync** — synchronous event log write + cache invalidation, strong consistency, no loss

No new tiers, no "between T1 and T2", no per-feature special cases. See [03_tier_taxonomy.md](03_tier_taxonomy.md) for eligibility rules and examples per tier.

**Why:** A closed taxonomy with four well-separated points prevents the gradient of ad-hoc durability decisions that infect long-lived MMO codebases. Each tier has clear performance and consistency characteristics that feature designers reason about once, not per-feature.

**Enforcement:** Feature design review rejects any ambiguous tier assignment. If a feature argues "this data is between T1 and T2", the answer is T2 — the safer tier.

---

## DP-A6 — Python is event-producer-only for game state

**Rule:** The Python LLM layer (roleplay-service, knowledge-service, future LLM services) does not write directly to kernel state. LLM-produced actions (NPC says X, NPC moves to Y, NPC attacks Z) are emitted as **proposal events** onto an event bus consumed by the Rust game layer. The Rust game layer validates the proposal against world rules, canon, and tier policy, then applies it via the SDK as an authoritative write.

**Why:** (a) LLMs are slow (100ms–10s per action) and hot-path-blocking an LLM call freezes the game. (b) LLM outputs are untrusted — canon-drift lint, injection defense, and world-rule validation must sit between LLM output and kernel state. (c) Keeping the Rust game layer as the sole authoritative writer collapses validation logic into one language and one place.

**Consequence:** Python services have a thin read-only projection query client for grounding (retrieval for prompt assembly). They do not have write access to the kernel.

**Note:** The exact bus protocol (Redis Streams? NATS? dedicated topic per event type? event schema versioning?) is deferred. This axiom only locks the direction (Python → bus → Rust, never Python → kernel).

---

## DP-A7 — Reality boundary in cache keys

**Rule:** Every cache key in the game-layer Redis namespace starts with `reality_id` as its first component. Canonical form: `dp:{reality_id}:{tier}:{aggregate_type}:{aggregate_id}[:subkey]`. No cache entry spans multiple realities; no cache operation accidentally reads a key from another reality.

**Why:** [03_multiverse/](../03_multiverse/) establishes peer realities with cross-reality isolation (R5 policy). DP cache must not weaken this. Putting `reality_id` first also enables future Redis Cluster sharding by reality without re-keying.

**Enforcement:** SDK API always takes `reality_id` as an argument; keys are constructed inside the SDK, not by the caller. Direct key construction by callers is not exposed.

---

## DP-A8 — Durable tier delegates to 02_storage unchanged

**Rule:** DP-T3 and DP-T2 durable writes go through existing [02_storage/](../02_storage/) mechanisms (event log append, outbox, single-writer session processor, snapshot engine, projection rebuild) without modification. DP does not reimplement event sourcing; it is a contract layer above it.

**Why:** 02_storage took ~30+ resolved R/S/C/SR items to stabilize. Reimplementing even part of it in DP would duplicate risk without benefit. DP's value is the tier taxonomy, cache layer, and access contract — not the durable storage.

**Consequence:** If DP needs a primitive 02_storage does not provide (e.g., bulk projection read API, specific snapshot metadata), the gap is raised as a new R* item in 02_storage, not implemented inside DP. Single source of truth for durable storage stays in 02_storage.

---

## DP-A9 — Feature tier assignment is part of feature design, not runtime

**Rule:** Every gameplay feature declares, per field or per access pattern, which tier (DP-T0..T3) it uses. This declaration lives in the feature's own design doc and is locked at design review. The tier is **not** chosen at runtime, not configurable per player, not switchable without a design-change.

**Why:** Runtime-tier-switching produces a combinatorial explosion of consistency semantics that cannot be reasoned about. Locking the tier at design time gives each feature exactly one consistency model to think about. If the tier needs to change later, it is a design change with explicit migration — not a config toggle.

**Enforcement:** Feature design review requires a tier table per aggregate the feature touches. Missing or ambiguous assignment blocks review. See [catalog/](../catalog/) for the cross-reference map once features start landing.

---

## DP-A10 — Federated feature repos; DP owns primitives, not domain queries

**Rule:** The DP SDK exposes a small, stable set of **primitive APIs** (~20 methods) — single-aggregate read, scoped query, single-tier write, multi-aggregate atomic write, invalidation subscribe, telemetry emit. **Feature-specific query logic** (inventory list with filters, quest state aggregation, chat history with visibility filter, combat state aggregation) lives in **feature repo modules owned by the feature**, not inside DP. Feature repos use only DP primitives and must follow the Access Pattern Rulebook ([11_access_pattern_rules.md](11_access_pattern_rules.md), DP-R1..DP-R8).

**Why:** A single SDK that exposes every feature's query surface becomes a god-interface that can only grow; every new feature requires DP changes; DP becomes the serialization point for all feature development. Splitting between DP (primitives + rules) and features (domain query logic) bounds DP's change rate, gives feature designers clear ownership of their query surface, and matches the mature "small kernel + user land" pattern of Kafka clients, Postgres/sqlx, and Envoy's control/data split.

**Enforcement:**
- **(a) Import discipline** — feature code imports only the `dp::primitives::*` module; direct DB/cache client imports rejected by clippy (R-3).
- **(b) Rule compliance** — every feature design review checks the rulebook (DP-R1..DP-R8) and rejects violations.
- **(c) Redundancy check** — a feature repo that is only a trivial wrapper around a DP primitive (e.g., `fn get_player(id) -> Player { dp::read_projection(...) }` with no added semantics) is a smell and should be refactored; the DP primitive should be called directly.

**Consequence:**

- Feature repos are **NOT** part of the `06_data_plane/` folder. They live in the feature's own module and are referenced from the feature's design doc.
- Tier choice per aggregate is made **inside the feature repo** following DP-A9 and DP-A5 — DP does not pre-classify aggregates.
- DP primitive API change = SDK major version bump; expected to be rare (once per year or less once stable).
- Feature repo change = frequent, independent of DP; does not require DP coordination.

---

## DP-A11 — Session-node owns T1 writes

**Rule:** Every player session is sticky-routed to a single game node; that node is the **authoritative single-writer** for all DP-T1 aggregates owned by that session (player position, emote state, presence, and any feature-declared T1 state scoped to the session). NPC aggregates that are not session-scoped have their writer node determined by an **NPC-to-node binding** table maintained by the control plane — startup registration, client-side cached for 60 seconds, not on the hot path. Session failover re-pins the session to a new node; the new node reloads the last Redis snapshot for each T1 aggregate (≤30 s loss per the DP-T1 guarantee).

**Why:** High-frequency T1 writes to the same aggregate from multiple nodes require either distributed locks (too slow — Redlock round-trip is 5–10 ms per acquisition, infeasible at thousands of writes/s) or last-writer-wins (race conditions that corrupt state). A single-writer discipline at the node level aligns with the existing single-writer-per-session rule in [02_storage R07](../02_storage/R07_concurrency_cross_session.md) and extends that discipline cleanly into the cache layer.

**Enforcement:** Load-balancer layer (ingress / gateway → game service) must route by session ID via consistent hashing or sticky cookie. SDK `t1_write(...)` fails with `DpError::WrongWriterNode` if invoked on a node that is not the session's current owner. Control plane exposes a `get_session_node(session_id)` lookup for routing but expects callers to cache aggressively — this is not a hot-path lookup per request.

**Consequence:**

- Session migration (rolling deploy, graceful node drain, failover) must flush the T1 Redis snapshot and transfer the session token before the old node accepts further writes for that session.
- NPC aggregates that physically move across regions handled by different nodes need an explicit NPC-handoff protocol. This is deferred — V2 operates with static NPC-to-node binding per reality; handoff becomes an issue only when per-reality NPC count crosses what a single node can hold.
- Sticky routing is a platform-level assumption; not having it defeats the axiom.

**Cross-ref:** Phase 2 SDK API and Phase 3 failure doc describe the exact sticky-routing mechanism and NPC-handoff protocol.

---

## DP-A12 — Session-context-gated access via RealityId newtype

**Rule:** Every DP SDK entry point takes `&SessionContext` as its first argument. `SessionContext` carries `RealityId` (the reality the session is bound to), `SessionId`, and a capability token. `RealityId` is a **Rust newtype with a module-private constructor** — instances can only be produced by the SDK during session bind at service startup, following verification against the control plane. Callers **cannot** construct `RealityId` from an integer directly. The SDK asserts that every aggregate access matches the session's reality; cross-reality reads require an explicit, capability-gated API (`cross_reality_read`, out of scope for Phase 1 — see [99_open_questions.md](99_open_questions.md) Q11).

**Why:** [DP-A7](#dp-a7--reality-boundary-in-cache-keys) asserts that `reality_id` is the first component of every cache key, but that is an invariant about key format — it does not prevent a caller from passing the wrong reality_id to the SDK as a parameter. Making `RealityId` a newtype with gated construction makes cross-reality leak **impossible at the type level**, not merely at the convention level. This is the concrete mechanism that implements rule **DP-R1** (reality-scoping) from the Rulebook.

**Enforcement:**
- **Compile-time** — code that attempts to construct `RealityId` outside the DP crate fails to compile (module privacy).
- **Runtime** — code that passes a `RealityId` from session A into an operation invoked with session B's `SessionContext` compiles (both are valid `RealityId` values) but fails at runtime with `DpError::RealityMismatch`. SDK logs the breach as a security event.

**Consequence:**

- Every feature repo method takes `&SessionContext` as its first argument (transitively through to DP primitives). This is ergonomic cost — every function signature is one parameter longer — in exchange for a compile-time guarantee.
- `SessionContext` binding happens once per session at startup and is passed via request context (not thread-local, to remain async-safe).
- Cross-reality coordination (canon propagation, cross-reality read) cannot use this axiom's mechanism — they use an explicit coordinator API owned by the cross-instance policy ([R5](../02_storage/R05_cross_instance.md)).

**Cross-ref:** Implementation of **DP-R1** in [11_access_pattern_rules.md](11_access_pattern_rules.md). Concrete Rust definitions (newtype, macro, error enum) land in Phase 2 `04_kernel_api_contract.md` per Q1 and Q14.

---

## DP-A13 — Channel hierarchy as first-class scope (Phase 4, 2026-04-25)

**Rule:** Every reality has a **tree of channels** rooted at the reality itself. Each channel has a unique `ChannelId` (UUID newtype, constructor DP-module-private), a `parent_id` (except the root), and a free-form `level_name: String` tag. The tree shape is **per-reality** (book-specific) — a reality declares its own levels via a book schema. DP is **agnostic** to `level_name` semantics; feature/book layer interprets level names (e.g., `"tavern"`, `"town"`, `"continent"`).

**Why:** The game model groups players into nested channels (cell → tavern → town → district → country → continent) with probabilistic event bubble-up across levels. Making channel a first-class DP concept prevents every feature from inventing its own hierarchy, and gives Q27 bubble-up + Q17 per-channel ordering + Q34 writer binding a shared foundation.

**Enforcement:**
- **(a)** Channel registry lives in **per-reality Postgres DB** (same DB as reality's event log); cell creation/dissolution writes don't cross into CP hot path.
- **(b)** CP caches channel tree per-reality (small, ≤hundreds of channels per reality typical) and serves it at `bind_session` + streams deltas via `StreamChannelTreeUpdates`.
- **(c)** `SessionContext` carries `current_channel_id` + `ancestor_channels: Vec<ChannelId>` (derived from tree); changes via `move_session_to_channel` SDK primitive.
- **(d)** DP does NOT validate `level_name` values — feature code asserts its own level semantics. If a book declares `"tavern"` as a level but feature code treats it as `"town"`, that is a feature-level bug, not a DP violation.

**Consequence:**
- Not every reality has all 6 conventional levels. A book set in a single city might use `reality → city → district → building → room`. DP handles any depth.
- Channel tree is mutable during reality lifetime (create new cells, dissolve old ones). Mutations propagate via the delta stream; SDKs invalidate cached ancestor chains on change.
- Root channel is implicit and identified as `ChannelId::reality_root(reality_id)`. All reality-scoped aggregates (see DP-A14) live at the root conceptually.

**Cross-ref:** [12_channel_primitives.md](12_channel_primitives.md) for concrete `ChannelId` type, tree schema, and SDK primitives (DP-Ch1..Ch10). Resolves [99_open_questions.md Q26](99_open_questions.md).

---

## DP-A14 — Aggregate scope: reality-scoped vs channel-scoped, design-time choice (Phase 4, 2026-04-25)

**Rule:** Every `Aggregate` declares exactly one **scope** via a marker trait: `RealityScoped` (follows the reality, identified by `(reality_id, aggregate_id)`) or `ChannelScoped` (lives in a specific channel, identified by `(reality_id, channel_id, aggregate_id)`). The scope is chosen at design time per aggregate, cannot be switched at runtime, and determines the shape of cache keys, read/write API, and event-log partitioning.

**Why:** Not every aggregate belongs to a channel. A player's PC / inventory / currency / quest state follows the player across channels — those are **reality-scoped**. A chat message / tavern furniture state / cell-scoped quest state exists in a specific channel — those are **channel-scoped**. Conflating both into one scope model forces awkward tradeoffs (nullable channel_id, or root-channel hack); separating them at the type level makes the choice explicit at every call site.

**Enforcement:**
- **(a) Compile-time** — marker traits `RealityScoped: Aggregate {}` and `ChannelScoped: Aggregate {}` on the aggregate type; tier marker (T0..T3) is orthogonal to scope marker. `#[derive(Aggregate)]` macro enforces exactly one scope via the `#[dp(scope = "reality" | "channel", ...)]` attribute.
- **(b) API surface** — read/write primitives come in scope-typed forms: `read_projection_reality<A: RealityScoped>(ctx, id)` and `read_projection_channel<A: ChannelScoped>(ctx, channel_id, id)`. Calling the wrong form fails compile (trait bound).
- **(c) Cache key** — macro `dp::cache_key!` generates `dp:{reality}:r:{tier}:{type}:{id}` for reality-scoped, `dp:{reality}:c:{channel}:{tier}:{type}:{id}` for channel-scoped. Scope marker `r`/`c` at position 2 makes key self-describing.

**Consequence:**
- Scope migration (a T2 aggregate moves from reality-scoped to channel-scoped) is a **design change** requiring a new aggregate type + dual-write + migration — analogous to tier migration per DP-C5 Expand/Migrate/Contract.
- Channel-scoped reads require an explicit channel_id argument; they do not default to `ctx.current_channel_id`. This forces call-site clarity: reading tavern furniture from a cell session must explicitly pass the tavern's channel_id.
- `t3_write_multi` accepts a mix of reality-scoped and channel-scoped aggregates in one atomic transaction, as long as the channel-scoped aggregates all sit in the same per-reality DB (which they do — see DP-A13).

**Cross-ref:** [12_channel_primitives.md DP-Ch4..Ch5](12_channel_primitives.md) for trait definitions and cache key specifics. Updates [04_kernel_api_contract.md DP-K4/K5/K7](04_kernel_api_contract.md) with scope-typed primitives.

---

## DP-A15 — Per-channel total event ordering (Phase 4, 2026-04-25)

**Rule:** Every active channel has a **strict total order** over its channel-scoped events, expressed as `channel_event_id: u64` monotonically increasing per channel (no gaps, no duplicates). Subscribers receive events in this order; gaps detected during subscribe-resume MUST trigger catch-up before live delivery. Reality-scoped events are NOT covered by this axiom — they retain per-aggregate / per-session ordering as defined in [02_storage R7](../02_storage/R07_concurrency_cross_session.md).

**Why:** The user's clarified game model requires "everyone in a channel sees the same story in the same order" — a total order per channel is the simplest mechanism that encodes this invariant. Without total order, two members of the same cell could see events shuffled differently, breaking the "shared story" guarantee that makes the channel meaningful as a social context.

**Enforcement:**
- **(a) DB level** — `event_log` table extended with composite UNIQUE constraint `(reality_id, channel_id, channel_event_id)`. Duplicate or non-monotonic insert rejected by Postgres.
- **(b) Single-writer level** — [DP-A16](#dp-a16--channel-writer-node-binding-phase-4-2026-04-25) ensures only one node allocates `channel_event_id` for a given channel at any time, making monotonic allocation trivial.
- **(c) Subscriber level** — durable subscribe ([Q16](99_open_questions.md), to be designed) carries `from_channel_event_id` resume token; subscriber catches up gaps before delivering live events.

**Consequence:**
- **Bubble-up causal references** ([Q27](99_open_questions.md)) record source events as `(child_channel_id, child_channel_event_id)` tuples — a stable reference because child events are totally ordered.
- **Deterministic RNG seed for bubble-up triggers** ([Q27](99_open_questions.md)) = `channel_event_id` of triggering child event; replay reproduces same RNG output.
- **Turn boundary events** ([Q15](99_open_questions.md), to be designed) occupy specific `channel_event_id` positions, making "page flip" a queryable point in the event log.
- Total-ordering invariant scopes to channel — there is NO global "events across all channels in a reality" ordering, intentionally.

**Cross-ref:** [13_channel_ordering_and_writer.md DP-Ch11](13_channel_ordering_and_writer.md#dp-ch11--channel_event_id-allocation-mechanism) for concrete allocation + recovery algorithm. Resolves [99_open_questions.md Q17](99_open_questions.md).

---

## DP-A16 — Channel writer-node binding (Phase 4, 2026-04-25)

**Rule:** Each **active** channel has exactly **one writer node** at any time. All channel-scoped writes (T2/T3 ChannelScoped aggregates) and channel events (turn boundaries, bubble-up emits) for that channel MUST execute on that node. Non-writer-node writes are routed transparently by the SDK via gRPC. Writer assignment differs by channel level:

- **Cell channels:** writer = creator's session node by default. CP coordinates handoff if creator's session leaves while the cell still has active sessions; cell goes dormant if no active sessions remain.
- **Non-cell channels (tavern / town / district / country / continent / any non-cell level):** writer = CP-assigned at channel creation time, persistent for the channel's lifetime; reassigned only on writer-node death.

**Why:** Single-writer discipline gives gapless monotonic `channel_event_id` allocation ([DP-A15](#dp-a15--per-channel-total-event-ordering-phase-4-2026-04-25)) without distributed-coordination overhead. It also provides a natural home for turn-boundary discipline ([Q15](99_open_questions.md)) and bubble-up aggregator state ([Q27](99_open_questions.md)). Cell writer = creator's node leverages session stickiness ([DP-A11](#dp-a11--session-node-owns-t1-writes)) — writes are local to the originating session in the common case. Non-cell writer is CP-assigned because non-cell channels (tavern, town, ...) are not tied to a specific user session.

**Enforcement:**
- **(a)** CP holds writer assignment per channel in its [channel-tree cache](12_channel_primitives.md#dp-ch3--cp-channel-tree-cache--delta-stream); SDK queries CP at session bind + on writer-change push events.
- **(b)** SDK detects "is this node the writer?" before each channel-scoped write. If yes, write directly. If no, SDK transparently RPCs to the writer node via a `route_channel_write` gRPC method.
- **(c) Direct write attempt on a non-writer node bypassing the SDK** fails at the DB layer because the writer's epoch token is required to insert into `event_log`. Non-SDK paths cannot forge an epoch.
- **(d)** Writer reassignment goes through CP's existing health-probe + channel-tree-delta-stream infrastructure ([DP-Ch3](12_channel_primitives.md#dp-ch3--cp-channel-tree-cache--delta-stream)). Failover budget: ≤35 s (30 s detection per [DP-F2](07_failure_and_recovery.md#dp-f2--game-node-death--session-handoff) + 5 s reassignment + push-out delta).

**Consequence:**
- **Cell creator leave is a feature-relevant event** (creator's departure may trigger handoff + a "creator-changed" event that participants see). Feature designs must declare how their cell creator-leave flow interacts with handoff.
- **Non-cell writer reassignment is invisible to features.** During the ≤35 s failover window, writes to that channel return `DpError::WrongChannelWriter` (transient) or `RateLimited` if the SDK's route cache is stale; SDK retries with backoff.
- **Writer fencing via epoch token** prevents split-brain double-write during transient overlap (old writer unaware it has been replaced). Postgres rejects writes carrying an expired epoch.
- Cross-node write adds **one LAN hop** (~5 ms) when the calling node is not the channel's writer. Acceptable in turn-based gameplay (1–10 events/s/channel typical, well below latency-sensitive realtime thresholds).

**Composition with [DP-A11](#dp-a11--session-node-owns-t1-writes):**
- DP-A11 binds **T1 + RealityScoped writes** to the session's node.
- DP-A16 binds **T2/T3 + ChannelScoped writes** to the channel's writer node.
- T0 has no writer concept (in-process only).
- A session may participate in writes to multiple channels (its current cell + ancestors via bubble-up); each routes to that channel's writer. A session's own node remains writer for its own session's T1 / RealityScoped state.

**Cross-ref:** [13_channel_ordering_and_writer.md DP-Ch12..Ch14](13_channel_ordering_and_writer.md#dp-ch12--writer-assignment-rules) for assignment rules, handoff protocol, and routing implementation. Resolves [99_open_questions.md Q34](99_open_questions.md).

---

## Locked-decision summary (for cross-reference)

| ID | Short name | One-line |
|---|---|---|
| DP-A1 | Primitives + Rulebook = sanctioned path | Kernel state reached only via DP primitives following Rulebook; threat model labeled (accidental bypass in scope; RCE out of scope; sidecar proxy deferred). |
| DP-A2 | CP/DP split | Policy in control plane, data in embedded SDK; CP not on hot path. |
| DP-A3 | Rust game layer | All new game services in Rust; SDK Rust-only. |
| DP-A4 | Redis cache + pub/sub + streams | Redis serves three roles: hot-path cache, pub/sub invalidation, durable per-channel event streams (Phase 4); per-reality key prefix. |
| DP-A5 | Four tiers only | DP-T0..T3, closed set, design-time choice. |
| DP-A6 | Python event-only | LLM emits proposals, Rust validates and applies. |
| DP-A7 | Reality-scoped keys | `reality_id` first in every cache key. |
| DP-A8 | Durable = 02_storage | DP does not reimplement event sourcing. |
| DP-A9 | Tier is design-time | Per-feature, per-field, locked in design doc, not runtime. |
| DP-A10 | Federated feature repos | DP owns primitives + rulebook; feature repos own domain query logic. |
| DP-A11 | Session-node T1 writer | Sticky-routed session node is authoritative T1 writer; failover reloads ≤30 s snapshot. |
| DP-A12 | RealityId newtype | `SessionContext`-gated access; `RealityId` constructor is DP-module-private; cross-reality violations fail type-check or runtime-check. |
| DP-A13 | Channel hierarchy first-class | Per-reality tree of channels with `ChannelId` newtype + free-form `level_name`; DP agnostic to level semantics; registry in per-reality DB, cache in CP. |
| DP-A14 | Aggregate scope is design-time | Aggregates declare `RealityScoped` or `ChannelScoped` via marker trait; scope determines cache key shape + API signature; compile-time enforced. |
| DP-A15 | Per-channel total event ordering | `channel_event_id: u64` monotonic per channel, gapless; subscribers catch up gaps before live delivery; reality-scoped events use existing R7 ordering. |
| DP-A16 | Channel writer-node binding | One writer per active channel; cell writer = creator's session node + handoff; non-cell writer = CP-assigned, persistent; cross-node writes routed transparently via gRPC; epoch-fenced for failover. |

Any change to an axiom is logged in [../decisions/](../decisions/) with a new locked-decision entry and the superseded axiom gets a `_withdrawn` suffix rather than being deleted.
