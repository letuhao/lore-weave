# L4 — SDK / Kernel API + `#[derive(Aggregate)]` Macro

> **Parent:** [_index.md](_index.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass enumeration

---

## §1. Scope of L4

The DP-kernel Rust framework + ALL `contracts/*` SDK packages that services import.

**The keystone deliverable** of the foundation: every service depends on this layer.

**IN scope:**
- L4.A `crates/dp-kernel/` — core Rust traits (Event, Aggregate, Projection, Snapshot, EventStore)
- L4.B `crates/dp-kernel-macros/` — `#[derive(Aggregate)]`, `#[derive(Projection)]` proc-macros
- L4.C `contracts/meta/` — (already L1.B; **cross-ref + Rust client port** here)
- L4.D `contracts/prompt/` — `AssemblePrompt()` + `ResolveContext()` skeleton (L6 fills LLM logic)
- L4.E `contracts/entity_status/` — `GetEntityStatus()` (S10)
- L4.F `contracts/resilience/` — `WithTimeout`, `Breaker`, `Retry`, `Bulkhead` (SR06 I16)
- L4.G `contracts/lifecycle/` — `Drain`, `ServiceMode`, `presence.go` (SR06 SR11)
- L4.H `contracts/observability/` — `inventory.yaml` registry + admission lib (SR12 I19)
- L4.I `contracts/capacity/` — `budgets.yaml` + admission lib (SR08 I17)
- L4.J `contracts/supply_chain/` — SBOM + dep-pinning lib (SR10 I18)
- L4.K `contracts/turn/` + `contracts/errors/` — turn state + canonical errors (SR11)
- L4.L `contracts/ws/` — WS ticket handshake skeleton (L6 details, S12)
- L4.M `contracts/service_acl/` — `matrix.yaml` + SVID lib (S11 I11)
- L4.N `contracts/dependencies/` — `matrix.yaml` of P0/P1/P2 deps (SR06)
- L4.O `contracts/chaos/` — `experiments.yaml` + chaos-engine client lib (SR07)
- L4.P `contracts/alerts/` — `rules.yaml` registry (SR09)
- L4.Q `contracts/pii/` — `scrubber.go` + `tables_classification.yaml` (S08)

**OUT (handled in other layers / deferred):**
- `contracts/events/` ship in L2.F (event schema registry)
- `contracts/migrations/` ship in L1.C (provisioner) + L2.A-B (per-reality migrations)
- LLM provider routing inside `contracts/prompt/` — L6
- Full intent classifier / world oracle / injection defense logic — out of foundation (per scope decision)

---

## §2. Sub-components

### L4.A — `crates/dp-kernel/` core crate (Rust)

**Owning chunks:** 00_overview §4 (events), §5 (projections), §6 (snapshots), SR06 (resilience), R02 (projection rebuild — load_aggregate)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.A.1 | `crates/dp-kernel/Cargo.toml` | Manifest | Rust 2021 edition; deps: tokio, serde, sqlx, tracing |
| L4.A.2 | `crates/dp-kernel/src/lib.rs` | Code | Crate entry; re-exports all traits + types |
| L4.A.3 | `crates/dp-kernel/src/event.rs` | Trait | `Event` trait — `event_type()`, `aggregate_id()`, `payload()`, `metadata()` |
| L4.A.4 | `crates/dp-kernel/src/aggregate.rs` | Trait | `Aggregate` trait — `aggregate_type()`, `id()`, `version()`, `apply(event)` |
| L4.A.5 | `crates/dp-kernel/src/projection.rs` | Trait | (L3.B.1) `Projection` trait |
| L4.A.6 | `crates/dp-kernel/src/snapshot.rs` | Trait | (L3.C.1) `Snapshot` trait + `load_aggregate()` algorithm |
| L4.A.7 | `crates/dp-kernel/src/event_store.rs` | Trait | `EventStore` trait — `append`, `read`, `snapshot_write`, `snapshot_read` |
| L4.A.8 | `crates/dp-kernel/src/event_store_pg.rs` | Impl | Postgres impl of EventStore (uses sqlx) |
| L4.A.9 | `crates/dp-kernel/src/outbox.rs` | Code | (L2.C.2) `outbox::write` helper |
| L4.A.10 | `crates/dp-kernel/src/upcaster.rs` | Trait | (L2.H.1) Upcaster trait |
| L4.A.11 | `crates/dp-kernel/src/event_validator.rs` | Code | (L2.I.1) Schema validation on write |
| L4.A.12 | `crates/dp-kernel/src/snapshot_runtime.rs` | Code | (L3.C.1) Load-aggregate algorithm |
| L4.A.13 | `crates/dp-kernel/src/error.rs` | Types | Canonical errors: `ErrConcurrencyConflict`, `ErrUnknownEventSchema`, `ErrSchemaViolation`, `ErrAggregateNotFound`, `ErrSnapshotMissing` |
| L4.A.14 | `crates/dp-kernel/src/metadata.rs` | Types | Event metadata struct (actor, causation_id, correlation_id, source, occurred_at, instance_clock_tick) |
| L4.A.15 | `crates/dp-kernel/tests/integration_event_store.rs` | Test | EventStore implementations pass shared test suite |
| L4.A.16 | `crates/dp-kernel/benches/append_throughput.rs` | Bench | Criterion benchmark: append rate ≥ 10K events/sec single thread |

**Acceptance criteria:**
- `cargo doc --no-deps` clean (no warnings)
- All traits have default impls where reasonable
- EventStore Postgres impl passes shared test suite
- Append throughput ≥ 10K events/sec single thread (benched)

**Open question:**
- Q-L4A-1: `EventStore` trait — is `sqlx::PgPool` exposed, or wrapped behind a custom connection type? Suggested: wrapped (allows future swap to other backends + cleaner test mocking).

---

### L4.B — `crates/dp-kernel-macros/` proc-macros

**Owning chunks:** R03 §12C (schema-as-code), 00_overview §4 (aggregates)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.B.1 | `crates/dp-kernel-macros/Cargo.toml` | Manifest | `proc-macro = true`; deps: syn, quote, proc-macro2 |
| L4.B.2 | `crates/dp-kernel-macros/src/lib.rs` | Code | Crate entry; `proc_macro_derive(Aggregate)` + `proc_macro_derive(Projection)` |
| L4.B.3 | `crates/dp-kernel-macros/src/aggregate.rs` | Code | `#[derive(Aggregate)]` impl — generates `Aggregate` trait impl with apply() dispatch + version tracking |
| L4.B.4 | `crates/dp-kernel-macros/src/projection.rs` | Code | `#[derive(Projection)]` impl — generates projection apply dispatch |
| L4.B.5 | `crates/dp-kernel-macros/src/event_annotations.rs` | Code | `@event`/`@version`/`@upcast` annotation parsing (shared with L2.G eventgen) |
| L4.B.6 | `crates/dp-kernel-macros/tests/derive_aggregate_test.rs` | Test | Macro produces correct trait impl; compiles + functions |
| L4.B.7 | `crates/dp-kernel-macros/tests/derive_projection_test.rs` | Test | Same for projection |
| L4.B.8 | `docs/dp-kernel/macros.md` | Doc | Macro usage guide (what struct shape produces what) |

**Acceptance criteria:**
- `#[derive(Aggregate)]` on a struct with `#[event_handler]` methods produces valid Aggregate impl
- Compile-time error messages helpful (use `Span`-tracked diagnostics)
- Macro stable across rustc 1.75+ (foundation target)

**Open question:**
- Q-L4B-1: Macro attribute syntax — `#[event_handler(npc.said)]` vs `#[handles_event = "npc.said"]`? Suggested: `#[handles_event("npc.said")]` (rustc-idiomatic, supports multiple).

---

### L4.C — `contracts/meta/` Rust client port

**Owning chunks:** L1.B (already enumerated for Go); this section = Rust port

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.C.1 | `crates/contracts-meta/Cargo.toml` | Manifest | Rust crate |
| L4.C.2 | `crates/contracts-meta/src/lib.rs` | Code | Re-export all client APIs |
| L4.C.3 | `crates/contracts-meta/src/meta_write.rs` | Code | Rust port of `MetaWrite()` |
| L4.C.4 | `crates/contracts-meta/src/state_transition.rs` | Code | Rust port of `AttemptStateTransition()` |
| L4.C.5 | `crates/contracts-meta/src/cache.rs` | Code | Same Redis cache patterns as Go (L1.B.2) — shared key naming |
| L4.C.6 | `crates/contracts-meta/src/fallback.rs` | Code | Same degraded-mode logic + buffer (L1.B.3) |
| L4.C.7 | `crates/contracts-meta/tests/parity_test.rs` | Test | Round-trip: Go writes via MetaWrite → Rust reads + interprets correctly |

**Acceptance criteria:**
- Rust ↔ Go cross-language parity tests pass
- Same `transitions.yaml` consumed by both languages
- Cache keys + invalidation events shared

---

### L4.D — `contracts/prompt/` SDK skeleton

**Owning chunks:** S09 §12Y (full spec — but logic out-of-foundation), I2 + I10 invariants

**Artifacts (SKELETON only — LLM logic in L6 / out of foundation):**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.D.1 | `contracts/prompt/v1.yaml` | OpenAPI | API surface — AssemblePrompt + ResolveContext signatures (Go + Rust + Python) |
| L4.D.2 | `contracts/prompt/intent.rs` + `intent.go` + `intent.py` | Code | 7-intent enum (S09 §12Y.2): session_turn, npc_reply, canon_check, canon_extraction, admin_triggered, world_seed, summary |
| L4.D.3 | `contracts/prompt/section.rs` (8-section structure) | Code | 8-section template enum: SYSTEM, WORLD_CANON, SESSION_STATE, ACTOR_CONTEXT, MEMORY, HISTORY, INSTRUCTION, INPUT |
| L4.D.4 | `contracts/prompt/bundle.rs` | Types | `PromptBundle` return type (rendered_prompt, provider_config, audit_ref_id) |
| L4.D.5 | `contracts/prompt/context.rs` | Types | `PromptContext` input type (reality_id, session_id, intent, …) |
| L4.D.6 | `contracts/prompt/templates/` empty dir | Convention | Placeholder for L6 templates per intent |
| L4.D.7 | `contracts/prompt/audit_writer.rs` | Code | Writes `prompt_audit` (meta) row on every Assemble call (no body) |
| L4.D.8 | `crates/contracts-prompt/tests/skeleton_test.rs` | Test | Skeleton compiles, signatures stable, audit writer works against mock |

**Acceptance criteria:**
- Skeleton compiles in all 3 languages
- API surface stable (signature freeze) — L6 adds bodies without changing signatures
- `prompt_audit` row written for every skeleton invocation

**Open question:**
- Q-L4D-1: ProviderPayload type — opaque `serde_json::Value` or strongly typed enum per provider? Suggested: opaque V1 (cross-provider diversity); typed enum V2+.

---

### L4.E — `contracts/entity_status/` (`GetEntityStatus`)

**Owning chunks:** S10 §12Z (GoneState enum, resolution order, cache)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.E.1 | `crates/contracts-entity-status/` | Crate | Rust port |
| L4.E.2 | `contracts/entity_status/v1.yaml` | OpenAPI | API surface (Go + Rust + Python) |
| L4.E.3 | `contracts/entity_status/gone_state.go` (+ Rust + Python) | Code | `GoneState` enum (active|severed|archived|dropped|user_erased) |
| L4.E.4 | `contracts/entity_status/resolver.go` (+ Rust) | Code | Resolution order: `pii_kek → reality_registry → reality_ancestry → projections` (S10) |
| L4.E.5 | `contracts/entity_status/cache.go` (+ Rust) | Code | 60s Redis cache; invalidated via MetaWrite events |
| L4.E.6 | `contracts/entity_status/precedence.go` (+ Rust) | Code | Compound state precedence: dropped > user_erased > severed > archived > active |
| L4.E.7 | `tests/integration/entity_status_test.rs` | Test | All 5 states resolve correctly + cache invalidation + precedence |

**Acceptance criteria:**
- Resolves entity status across all 5 sources correctly
- Cache hit < 5ms; miss < 50ms
- Cache invalidation propagates < 2s after MetaWrite event

---

### L4.F — `contracts/resilience/` (SR06 I16)

**Owning chunks:** SR06 §12AI.3-.5, .10

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.F.1 | `contracts/resilience/v1.yaml` | API | WithTimeout, Breaker, Retry, Bulkhead signatures |
| L4.F.2 | `contracts/resilience/timeout.go` (+ Rust) | Code | `WithTimeout(ctx, dep, fn)` |
| L4.F.3 | `contracts/resilience/breaker.go` (+ Rust) | Code | 3-state circuit breaker (closed/half_open/open) |
| L4.F.4 | `contracts/resilience/retry.go` (+ Rust) | Code | Exponential backoff + 25% jitter, respects `Retry-After` |
| L4.F.5 | `contracts/resilience/bulkhead.go` (+ Rust) | Code | Resource isolation per (service, dep), fast-fail `ErrBulkheadFull` |
| L4.F.6 | `contracts/resilience/dependency_events.go` | Code | Emits `dependency_events` (meta) audit rows on breaker transitions, retry exhaustion, bulkhead rejection |
| L4.F.7 | `tests/integration/resilience_test.rs` | Test | Each primitive tested independently + composed |
| L4.F.8 | `tests/integration/breaker_chaos_test.rs` | Test | Inject failures; breaker transitions correctly; audit rows written |

**Acceptance criteria:**
- All 4 primitives composable
- Breaker state transitions auditable via `dependency_events`
- Bulkhead enforces concurrency cap
- CI lint `timeout-discipline-lint.sh` (L1.K.9) catches missing `WithTimeout`

---

### L4.G — `contracts/lifecycle/` (SR06 SR11)

**Owning chunks:** SR06 §12AI.6, .11; SR11 (PresenceState)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.G.1 | `contracts/lifecycle/v1.yaml` | API | Drain + ServiceMode |
| L4.G.2 | `contracts/lifecycle/drain.go` (+ Rust) | Code | `Drain(ctx, timeout, hooks)` per SR6-D10 |
| L4.G.3 | `contracts/lifecycle/service_mode.go` (+ Rust) | Code | (L1.J.2) ServiceMode enum |
| L4.G.4 | `contracts/lifecycle/mode_propagation.go` (+ Rust) | Code | (L1.J.3) Redis control channel `lw:dependency:control` |
| L4.G.5 | `contracts/lifecycle/presence.go` (+ Rust) | Code | PresenceState enum (6 variants per SR11) |
| L4.G.6 | `tests/integration/drain_test.rs` | Test | SIGTERM triggers Drain; hooks execute in order; bounded by timeout |

**Acceptance criteria:**
- Drain hook execution order: StopAccepting → WaitInFlight → FlushOutbox → CloseBreakers → CloseResources
- Default timeouts: 30s (stateless 10s, long-runners 120s)
- Mode propagation reaches all services < 5s

---

### L4.H — `contracts/observability/` (SR12 I19)

**Owning chunks:** SR12 §12AO (inventory + admission control)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.H.1 | `contracts/observability/inventory.yaml` | Registry | Master `lw_*` metric + audit table registry |
| L4.H.2 | `contracts/observability/v1.yaml` | API | Admission API: `EmitMetric(name, labels, value)` |
| L4.H.3 | `contracts/observability/admission.go` (+ Rust + Python) | Code | Rejects unauthorized labels at emission |
| L4.H.4 | `contracts/observability/inventory_loader.go` | Code | Loads inventory.yaml + builds in-memory admission lookup |
| L4.H.5 | `scripts/observability-inventory-lint.sh` | CI lint | (L1.K.6) Detects `lw_*` emit without inventory entry |
| L4.H.6 | `contracts/observability/budget_breach_writer.go` | Code | Writes `observability_budget_breaches` (meta) row on rejection (V1 warn-and-drop, V1+30d hard-reject) |
| L4.H.7 | `tests/integration/admission_control_test.rs` | Test | Unregistered metric: V1 warns + drops; V1+30d rejects |

**Acceptance criteria:**
- All foundation `lw_*` metrics declared in inventory
- Admission control rejects unregistered (V1+30d) / warns (V1)
- CI lint blocks PR with unregistered metric

---

### L4.I — `contracts/capacity/` (SR08 I17)

**Owning chunks:** SR08 §12AK (capacity budget + lints)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.I.1 | `contracts/capacity/budgets.yaml` | Registry | Per-service capacity budget (class + 5 dimensions × V1/V2/V3 tiers) |
| L4.I.2 | `scripts/capacity-budget-lint.sh` | CI lint | (L1.K.7) Block missing service |
| L4.I.3 | `contracts/capacity/admission.go` | Code | Runtime check on deploy |
| L4.I.4 | `services/admin-cli/commands/capacity_override.go` | Code | (L1.L.3) Already enumerated; refer here |

**Acceptance criteria:**
- All 20+ services declared in budgets.yaml
- CI lint blocks new service without entry
- Override audited via S5 Tier 2

---

### L4.J — `contracts/supply_chain/` (SR10 I18)

**Owning chunks:** SR10 §12AM (dep pinning + SBOM)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.J.1 | `scripts/dep-pinning-lint.sh` | CI lint | (L1.K.8) Block unhashed deps |
| L4.J.2 | `scripts/dockerfile-digest-lint.sh` | CI lint | Block `FROM image:tag` without digest |
| L4.J.3 | `infra/sbom/generate.sh` | Script | SBOM generation (CycloneDX format) per build |
| L4.J.4 | `contracts/supply_chain/sbom_emit.go` | Code | Emits `supply_chain_events` (meta) row per build |
| L4.J.5 | `contracts/supply_chain/dependabot.yaml` | Config | Renovate/Dependabot automated PR config |

**Acceptance criteria:**
- All Dockerfiles use digest
- All language lockfiles use hashes (go.sum, package-lock.json integrity, uv.lock --require-hashes)
- SBOM generated per build, persisted to MinIO

---

### L4.K — `contracts/turn/` + `contracts/errors/` (SR11)

**Owning chunks:** SR11 §12AN (turn UX reliability)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.K.1 | `contracts/turn/v1.yaml` | API | Turn submission contract |
| L4.K.2 | `contracts/turn/turn_state.go` (+ Rust + Python) | Code | TurnState enum 8 variants per SR11 vocabulary addition |
| L4.K.3 | `contracts/turn/turn_outcome_writer.go` | Code | Writes `turn_outcomes` (meta) row |
| L4.K.4 | `contracts/errors/canonical.go` (+ Rust + Python) | Code | Canonical error types (per SR11 errors module) |
| L4.K.5 | `tests/integration/turn_state_machine_test.rs` | Test | All 8 transitions valid; invalid rejected |

**Acceptance criteria:**
- TurnState enum aligned across 3 languages
- `turn_outcomes` writes from all 3 language services

---

### L4.L — `contracts/ws/` SKELETON

**Owning chunks:** S12 §12AB (full spec — but logic in L6 / api-gateway-bff)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.L.1 | `contracts/ws/v1.yaml` | API | WS ticket + message envelope (per S12 §12AB.2) |
| L4.L.2 | `contracts/ws/ticket.go` (+ Rust) | Code | Ticket structure (60s TTL, allowed_realities, allowed_scopes, origin_hash, fingerprint_hash) |
| L4.L.3 | `contracts/ws/envelope.go` (+ Rust + TS) | Code | WS message envelope (control vs data, severity codes 1000, 4001..4010) |
| L4.L.4 | `contracts/ws/session_store.go` | Code | WSSession server-side state — 15-min TTL, refresh via ws.refresh |

**Note:** Full WS server implementation in L6 (api-gateway-bff + roleplay-service WS lib). L4 ships only the contract types.

**Acceptance criteria:**
- Envelope + ticket types compile across 3 languages
- TS types match Go types byte-equal on serialization

---

### L4.M — `contracts/service_acl/` (S11 I11)

**Owning chunks:** S11 §12AA (SVID, ACL matrix)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.M.1 | `contracts/service_acl/matrix.yaml` | Registry | Every `(caller → callee + rpc)` pair authorized |
| L4.M.2 | `contracts/service_acl/v1.yaml` | API | SVID issuance + verification API |
| L4.M.3 | `contracts/service_acl/svid_client.go` (+ Rust) | Code | SVID issuance client (SPIFFE-style) |
| L4.M.4 | `contracts/service_acl/svid_verifier.go` (+ Rust) | Code | Inbound RPC verifier (entry middleware) |
| L4.M.5 | `contracts/service_acl/audit_emitter.go` | Code | Writes `service_to_service_audit` (meta) row per RPC (FULL audit per Q-L1A-3 LOCKED) |
| L4.M.6 | `contracts/service_acl/principal_mode.go` | Code | `requires_user|system_only|either` enum |
| L4.M.7 | `scripts/service-acl-matrix-lint.sh` | CI lint | (L1.K.13) Block new RPC without matrix entry |
| L4.M.8 | `tests/integration/svid_test.rs` | Test | SVID issuance + verification; expired SVID rejected; out-of-matrix RPC rejected |

**Acceptance criteria:**
- All RPCs declared in matrix
- Full audit row per RPC (no sampling per Q-L1A-3 LOCKED)
- CI lint blocks new RPC

---

### L4.N — `contracts/dependencies/` (SR06)

**Owning chunks:** SR06 §12AI matrix of P0/P1/P2 deps

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.N.1 | `contracts/dependencies/matrix.yaml` | Registry | All P0/P1/P2 deps (Postgres meta, Postgres per-reality, Redis cache, Redis Streams, MinIO, LLM providers, Patroni etcd, …) with timeout defaults |
| L4.N.2 | `scripts/dependency-registry-lint.sh` | CI lint | Block new HTTP client / DB driver / Redis client outside matrix |
| L4.N.3 | `contracts/dependencies/client_factory.go` (+ Rust) | Code | Returns properly-wrapped client (timeout + breaker + retry + bulkhead per dep) |

**Acceptance criteria:**
- All deps declared with timeout defaults
- Client factory produces wrapped clients
- Lint blocks raw client outside factory

---

### L4.O — `contracts/chaos/` (SR07)

**Owning chunks:** SR07 §12AJ

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.O.1 | `contracts/chaos/experiments.yaml` | Registry | Chaos drill experiment definitions |
| L4.O.2 | `services/chaos-engine/` Go service | Code | Executes drills per schedule |
| L4.O.3 | `contracts/chaos/event_emitter.go` | Code | Writes `chaos_drills` (meta) audit rows |
| L4.O.4 | `contracts/chaos/v1.yaml` | API | Drill request/response surface |

**Acceptance criteria:**
- Drill execution audited
- Drills can target individual services or shards
- IF-39g activated per SR07 §12AJ

---

### L4.P — `contracts/alerts/` (SR09)

**Owning chunks:** SR09 §12AL

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.P.1 | `contracts/alerts/rules.yaml` | Registry | All alert rules with severity_map + escalation per SR2 routing table |
| L4.P.2 | `contracts/alerts/silence_writer.go` | Code | Writes `alert_silences` (meta) row + propagates to alert engine |
| L4.P.3 | `contracts/alerts/outcome_recorder.go` | Code | Writes `alert_outcomes` (meta) row on ack/resolution |
| L4.P.4 | `infra/alertmanager/config.yaml` | Config | Routing per SR2 alert routing table |

**Acceptance criteria:**
- All foundation alerts in rules.yaml
- 4-severity × 4-action-class taxonomy enforced per SR09 §12AL

---

### L4.Q — `contracts/pii/` (S08)

**Owning chunks:** S08 §12X (PII registry, classification, scrubber)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L4.Q.1 | `contracts/pii/scrubber.go` (+ Rust + Python) | Code | Free-text PII scrubber lib (S08 §12X.5; used by L1.B.15 audit writer) |
| L4.Q.2 | `contracts/pii/tables_classification.yaml` | Registry | Per-table PII classification + retention class + erasure method + legal basis (S08 §12X.3) |
| L4.Q.3 | `scripts/pii-classify-lint.sh` | CI lint | (L1.K.2) Block migration without classification tags |
| L4.Q.4 | `contracts/pii/kek_manager.go` | Code | KEK lifecycle (rotate, destroy) — wraps KMS |
| L4.Q.5 | `contracts/pii/erasure.go` | Code | `admin/user-erasure` execution logic (S08 §12X.6) |
| L4.Q.6 | `tests/integration/pii_scrubber_test.rs` | Test | All 7 regex patterns (email, phone, ipv4, ipv6, cc, ssn, api_key_like) detected |
| L4.Q.7 | `tests/integration/kek_rotation_test.go` | Test | KEK rotation preserves blob readability |
| L4.Q.8 | `tests/integration/user_erasure_test.go` | Test | Full 10-step erasure runbook executes correctly |

**Acceptance criteria:**
- Scrubber detects all 7 patterns
- KEK rotation succeeds without data loss
- Erasure runbook completes within 1h immediate effect; 30d full cert

---

## §3. L4 cross-component dependency graph

```
L4.A (dp-kernel) ──┬─→ L4.B (macros) — macro generates kernel-trait impls
                   ├─→ L4.C (Rust meta client)
                   ├─→ L4.D (prompt Rust skeleton)
                   └─→ L4.E (entity_status Rust)

L4.F (resilience) ←─ ALL contracts/* (every contract uses resilience primitives)
L4.G (lifecycle) ←─ ALL services (every service has Drain + ServiceMode)
L4.H (observability) ←─ ALL services (every service emits inventoried metrics)
L4.I (capacity) ←─ ALL services (every service in budgets)
L4.J (supply_chain) ←─ build pipeline
L4.K (turn + errors) ←─ roleplay-service
L4.L (ws skeleton) ←─ api-gateway-bff + roleplay-service (L6)
L4.M (service_acl) ←─ ALL inter-service RPC
L4.N (dependencies) ←─ ALL outbound clients
L4.O (chaos) ←─ chaos-engine (L4.O.2)
L4.P (alerts) ←─ alertmanager + SRE
L4.Q (pii) ←─ L4.M (audit emitter scrubs reasons) + L1.B audit_writer

Approximate ordering: L4.A + L4.B (kernel + macros) → L4.F + L4.G + L4.J (resilience + lifecycle + supply chain — foundational cross-cuts) → L4.H + L4.I (observability + capacity admission) → L4.C + L4.D + L4.E + L4.K + L4.L + L4.M + L4.N + L4.O + L4.P + L4.Q (contract packages — independently buildable)
```

---

## §4. Cycle decomposition hint for L4

| Cycle | Scope | Why grouped |
|---|---|---|
| L4-cycle-1 | L4.A (dp-kernel core) + L4.B (macros) | Keystone. Everything depends on this. Cannot ship anything else without it. |
| L4-cycle-2 | L4.F (resilience) + L4.G (lifecycle) + L4.N (dependencies matrix) | Cross-cutting primitives; every service uses these. |
| L4-cycle-3 | L4.H (observability admission) + L4.I (capacity admission) + L4.J (supply chain) | Admission control trio; need to be in place before service deployments enforce them. |
| L4-cycle-4 | L4.C (meta Rust port) + L4.E (entity_status) + L4.K (turn + errors) | Rust client ports + SR11 vocabulary; depend on kernel + meta library exists. |
| L4-cycle-5 | L4.D (prompt skeleton) + L4.L (ws skeleton) | Skeleton-only; full logic in L6. Sign contracts now. |
| L4-cycle-6 | L4.M (service_acl) + L4.O (chaos) + L4.P (alerts) + L4.Q (pii) | Cross-cutting governance contracts; share audit + lint infrastructure. |

**Total L4 estimate: ~6 RAID XL cycles.**

---

## §5. Open questions surfaced during L4 enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L4A-1 | EventStore trait — sqlx::PgPool exposed or wrapped? | Wrapped | Suggested |
| Q-L4B-1 | Macro attribute syntax | `#[handles_event("npc.said")]` | Suggested |
| Q-L4D-1 | ProviderPayload type — opaque or typed? | Opaque V1; typed V2+ | Suggested |
| Q-L4-1 | Rust client ports for Go contracts — how many languages? | 3 (Go + Rust + Python) for runtime types; TS only for events + WS envelope | Suggested |
| Q-L4-2 | Single workspace `Cargo.toml` or split workspaces per service? | Single root workspace (matches current `Cargo.toml`); per-service members | Confirmed by repo state |
| Q-L4-3 | Polyglot type generation — codegen tool unified or per-contract? | Unified `contractgen` tool similar to `eventgen` (extends scope of L2.G) | Suggested |
| Q-L4-4 | `contracts/chaos/` deployment — chaos-engine V1 or V1+30d? | V1+30d (SR07 §12AJ implementation phase) | Confirmed by SR07 |
| Q-L4-5 | Many contracts have `v1.yaml` OpenAPI specs — are these served by api-gateway-bff or internal documentation only? | Internal documentation V1; api-gateway-bff serves user-facing APIs only | Suggested |

---

## §6. Status

```
[x] L4 — 17 sub-components enumerated at B-level (A-Q)
[x] L4 — cross-component deps mapped
[x] L4 — 8 open questions surfaced
[x] L4 — cycle decomposition hint (~6 cycles)
[ ] L4 — open questions resolved (batch at end of all layers)
[ ] Continue to L5 (Inbound canon ingestion)
```
