# 01 — Scope and Boundary

> **Status:** LOCKED. Scope decision: **Option C — 06_data_plane owns the kernel access contract.**
> **Supersedes:** None.
> **Depends on:** [02_invariants.md](02_invariants.md) for the axioms this scope induces.

---

## 1. The scope decision

Three scopes were considered during CLARIFY:

| Option | What 06 would own | What stayed in 02_storage |
|---|---|---|
| (a) Hot path only | Ephemeral memory + cache + tier policy | Entire read-path and write-path to durable state |
| (b) Hot path + runtime read cache | Tier policy + cache + runtime read API | Projection rebuild, schema evolution, durable write |
| **(c) Full kernel access contract** ✅ | The contract every game-layer service uses to touch kernel state, including durable tier | Implementation detail beneath the SDK |

**Locked: Option (c).** Rationale: making any service bypass trivially possible defeats the "no feature can violate the tier policy" guarantee. If some services read Postgres directly for T3 and use the SDK for T0–T2, the SDK is a recommendation, not a contract. Option (c) makes the SDK the only door.

---

## 2. What 06_data_plane owns

### 2.1. The access contract

Every read and write of kernel state by a game-layer service goes through the SDK defined here. The SDK is the only surface exposed to game services. Underlying mechanisms (Postgres event log, Redis cache, projection tables, outbox, snapshot engine) are implementation details behind the contract and may change without changing the SDK.

### 2.2. The tier taxonomy

Four tiers (DP-T0..T3) classify every kernel access by durability requirement and performance characteristic. See [03_tier_taxonomy.md](03_tier_taxonomy.md). Every feature design must declare the tier for each kernel access it performs — this is enforced at design review, not at runtime.

### 2.3. The control plane

A thin service owning:
- Tier policy registry (which aggregate types can be read/written at which tier)
- Schema versioning and migration coordination
- Cache coherency broadcast (invalidation events)
- Cold-start coordination (when a reality transitions from frozen to active)
- SLO enforcement hooks (latency budget, backpressure signals)

The control plane does NOT sit on the data path. Hot-path reads and writes do not round-trip through it. See [05_control_plane_spec.md](./) (Phase 2).

### 2.4. The data plane SDK (primitives only)

A Rust library embedded in every game-layer service. The SDK exposes a **small, stable set of primitive APIs (~20 methods)** — not feature-specific queries. Scope:
- Typed read/write primitives per tier: `t0_*`, `t1_*`, `t2_*`, `t3_*_write`, `t3_write_multi`, single-aggregate reads, scoped-query primitive
- Tier policy enforcement at compile time via traits + module privacy (see [DP-R5](11_access_pattern_rules.md#dp-r5--no-cross-tier-mixing-in-a-single-write-operation))
- `SessionContext` + `RealityId` newtype machinery ([DP-R1](11_access_pattern_rules.md#dp-r1--reality-scoping))
- `dp::cache_key!` macro and equivalent compile-time helpers ([DP-R4](11_access_pattern_rules.md#dp-r4--cache-keys-via-dp-macro-never-hand-built))
- Direct Redis access for T0–T2 reads and cache
- Delegates durable writes/reads to [02_storage/](../02_storage/) mechanisms
- Subscribes to control-plane invalidation broadcasts
- Emits telemetry hooks (`dp::instrumented!` macro, [DP-R8](11_access_pattern_rules.md#dp-r8--telemetry-on-every-t2t3-boundary-crossing))

**Explicitly NOT in SDK:** feature-specific queries (inventory list with filters, quest state aggregation, chat history windows, combat state rollup). Those live in feature repos, see §4 below.

See [04_kernel_api_contract.md](./) (Phase 2) for concrete Rust definitions.

### 2.5. Cache coherency protocol

Defines when cached state is invalidated, how invalidation is propagated across SDK instances, and what consistency guarantees each tier gives. See [06_cache_coherency.md](./) (Phase 2).

### 2.6. Failure and recovery semantics

Defines behavior during: cache node failure, control plane failure, cold start of a reality, partial network partition, split-brain detection. See [07_failure_and_recovery.md](./) (Phase 3).

### 2.7. Scale and SLO targets

Locked anchor numbers for V1/V2/V3, latency budgets, throughput targets, resource ceilings. See [08_scale_and_slos.md](08_scale_and_slos.md).

---

## 3. What 06_data_plane does NOT own

| Concern | Owner | Why not DP |
|---|---|---|
| Event log schema (tables, indexes) | [02_storage/](../02_storage/) | DP consumes the schema via a typed interface; schema evolution is storage engineering. |
| Snapshot cadence + retention | [02_storage/00_overview_and_schema.md](../02_storage/00_overview_and_schema.md) | Covered by existing policy (every 500 events or 1 hour, retain 3). |
| Projection rebuild algorithm | [02_storage/R02](../02_storage/R02_projection_rebuild.md) | Existing 5-layer rebuild strategy is authoritative. |
| Cross-reality isolation policy | [02_storage/R05](../02_storage/R05_cross_instance.md) | DP cache keys respect the existing isolation — does not weaken it. |
| Session single-writer concurrency | [02_storage/R07](../02_storage/R07_concurrency_cross_session.md) | DP T2/T3 writes route through the session command processor defined there. |
| Canon layer semantics (L1..L4) | [03_multiverse/](../03_multiverse/) | DP is orthogonal to canon layering; tier choice is independent of layer. |
| Feature-specific tier assignments | Per-feature design doc | DP defines the taxonomy; features pick from it. |
| LLM prompt assembly | [02_storage/S09](../02_storage/S09_prompt_assembly.md) + [05_llm_safety/](../05_llm_safety/) | Prompt assembly reads through DP but is not DP's concern. |
| Python LLM service protocol | Deferred ([99_open_questions.md](99_open_questions.md) Q2) | Roleplay-service is draft; its kernel-write semantics will be locked in its own doc later. Current rule: Python emits proposal events, Rust game layer validates and applies. |

---

## 3b. Feature-repo boundary (the other side of DP-A10)

Feature-specific query logic — inventory list with filters, quest state aggregation across multiple aggregates, chat history with visibility filtering, combat state rollup — lives in **feature repo modules** owned by the feature, **not** inside DP. The split is:

| Concern | Owner | Example |
|---|---|---|
| Primitive: read one aggregate by type + id | DP SDK | `dp::primitives::read_projection::<Player>(ctx, id)` |
| Primitive: scoped projection query by predicate | DP SDK | `dp::primitives::query_scoped(ctx, predicate_typed)` |
| Primitive: atomic multi-aggregate T3 write | DP SDK | `dp::primitives::t3_write_multi(ctx, &[...])` |
| Domain query: list player's inventory filtered by slot and tag, sorted by rarity | Feature repo (`inventory-repo`) | `inventory_repo::list_filtered(ctx, player_id, slot, tags)` |
| Domain query: quest state for player across active + completed + prerequisites | Feature repo (`quest-repo`) | `quest_repo::state_for_player(ctx, player_id)` |
| Domain command: trade 100 gold for item X between players A and B | Feature repo (`trade-repo`) | `trade_repo::execute(ctx, tx_proposal)` → internally one or more DP primitive calls |

**Rule (from [DP-A10](02_invariants.md#dp-a10--federated-feature-repos-dp-owns-primitives-not-domain-queries)):** feature repos import only `dp::primitives::*` and follow the [Rulebook](11_access_pattern_rules.md). Feature repos are not part of this folder — they live in their own feature's source tree, with their own design doc and tier table ([DP-R2](11_access_pattern_rules.md#dp-r2--tier-declaration-per-aggregate)).

**Consequence for DP's change rate:** primitive API is small and stable; feature repos change independently. DP-SDK major version bumps are expected to be rare (annual or less). Feature repo changes are routine and require no DP coordination.

---

## 4. Boundary with existing Go platform services

The Go platform services (book-service, auth-service, glossary-service, translation-service, provider-registry-service, usage-billing-service, chat-service — see [`CLAUDE.md`](../../../../CLAUDE.md)) are **not** game-layer services. They do not touch game state (player positions, NPC session memory, combat ticks, etc.) and do not use the DP SDK.

Boundary rule: if a service reads or writes any aggregate in a per-reality database (`reality_<id>_db`), it is a game-layer service and uses the DP SDK. If it only reads/writes the global platform databases (users, books, glossary, etc.), it does not.

Consequence: the SDK is Rust-only. No Go binding, no Python binding. Python roleplay-service's kernel access is through an async event bus into game services (deferred design).

---

## 5. Boundary with TS gateway

The TS gateway (api-gateway-bff) does not touch kernel state directly per the **gateway invariant** in [`CLAUDE.md`](../../../../CLAUDE.md) ("all external traffic through api-gateway-bff"). It calls game-layer Rust services over gRPC or HTTP, which in turn use the SDK. The gateway never uses the DP SDK.

---

## 6. Implications of Option C

Locking Option C induces the following downstream requirements (captured as axioms in [02_invariants.md](02_invariants.md)):

1. Game services **must not** have direct Postgres credentials for per-reality databases. Only the SDK does.
2. Game services **must not** have direct Redis credentials for the game-layer cache namespace. Only the SDK does.
3. The SDK itself runs in-process inside each game service and talks to Postgres/Redis on behalf of the service.
4. The control plane is the only process authorized to change schema, rotate cache namespace, or migrate tier assignments.
5. Every new gameplay feature's design review includes a tier assignment check — without it, the review cannot pass.

These are mechanical enforcement rules, not principles to be interpreted.

---

## 7. Migration implications

Existing `02_storage/` design stays as-is. No IDs are renumbered. R*, S*, C*, SR*, HMP remain stable. DP references those IDs by name and does not supersede them.

When Phase 2 and Phase 3 land, they will describe how existing 02_storage mechanisms (outbox, snapshot, rebuild, single-writer) are invoked from the SDK. If any gap is found between what the SDK needs and what 02_storage provides, a new R* item is raised in 02_storage rather than reimplementing the mechanism in DP.
