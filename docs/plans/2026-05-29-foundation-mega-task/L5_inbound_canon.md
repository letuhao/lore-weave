# L5 — Inbound Canon Ingestion

> **Parent:** [_index.md](_index.md)
> **Depth target:** B (artifact-level)
> **Status:** DRAFT — first-pass enumeration

---

## §1. Scope of L5

Pipelines that ingest **book canon** (L1 axiomatic + L2 seeded) from the LoreWeave novel platform (`book-service`, `glossary-service`, `knowledge-service`) into per-reality state, and route canon updates across realities.

**Critical context from Q-L1A-2 LOCKED 2026-05-29:**
- `canon_entries`, `canonization_audit`, `book_authorship`, `canon_change_log` live in **glossary-service's `glossary` DB**, NOT meta.
- L5 push = event-driven via glossary-service outbox → meta-worker.
- L5 pull = RPC to glossary-service (with per-reality cache).
- Service map line 71 amendment required (foundation deliverable).

**3 mặt của inbound canon (per top-of-CLARIFY confirmation):**

```
┌──────────────────────────────────────────────────────────────┐
│ Glossary DB (canon_entries, canonization_audit,              │
│  book_authorship, canon_change_log)                          │
│   ↑                                                          │
│   │ author canonization via MetaWrite() in glossary DB       │
│   │                                                          │
│  ┌──────────────────────────────────┐                        │
│  │  glossary-service emits via      │                        │
│  │  ITS OWN outbox (R06 pattern)    │                        │
│  └──────────────────────────────────┘                        │
│              │ canon.change.* events                         │
│              ▼                                               │
│   Publisher (L2.D) → Redis Streams                           │
│              │ xreality.book.canon.updated                   │
│              ▼                                               │
│   meta-worker (L2.L) consumes                                │
│      ▼                                                       │
│   ┌──────────────────┐  ┌──────────────────┐                 │
│   │ PUSH:            │  │ SEED:            │                 │
│   │ writes to        │  │ world-service    │                 │
│   │ per-reality      │  │ on reality       │                 │
│   │ canon projection │  │ creation reads   │                 │
│   │                  │  │ canon via RPC    │                 │
│   └────────┬─────────┘  │ + writes initial │                 │
│            │            │ canon projection │                 │
│            │            └──────────────────┘                 │
│            ▼                                                 │
│   Per-reality DB canon_projection table                      │
│                                                              │
│   ┌──────────────────────────────────┐                       │
│   │ PULL: roleplay-service           │                       │
│   │ AssemblePrompt() [WORLD_CANON]   │                       │
│   │ reads per-reality canon          │                       │
│   │ projection (cached fast read)    │                       │
│   │ + RPC to glossary-service on     │                       │
│   │ cache miss for full body         │                       │
│   └──────────────────────────────────┘                       │
└──────────────────────────────────────────────────────────────┘
```

**IN scope:**
- L5.A glossary-service outbox emission (CHANGE to existing service — coordinated, not full impl)
- L5.B meta-worker canon-update consumer
- L5.C meta-worker user-erased consumer
- L5.D Per-reality `canon_projection` table
- L5.E Per-reality canon cache (hot read for `[WORLD_CANON]`)
- L5.F RPC contract glossary-service ↔ roleplay-service / world-service
- L5.G world-service reality-seed flow
- L5.H Force-propagate compensating event mechanism (M4-D3)
- L5.I L1 axiomatic conflict detection (M4-D4)
- L5.J Glossary entity change timeline contract

**OUT (deferred / out of foundation):**
- DF3 Canonization workbench UI (out of scope — feature)
- DF14 Vanish Reality Mystery System
- Author preview modal UI (M4-D1)
- L1 axiomatic full conflict-resolution UX
- E3 IP ownership legal review

---

## §2. Sub-components

### L5.A — Glossary-service outbox emission (CHANGE to existing service)

**Owning chunks:** R05 §12E.3 (xreality topics), R06 §12F (outbox pattern), M4 §9.8.5 (xreality.book.canon.updated)

**Note:** glossary-service is an EXISTING LoreWeave novel-platform service. Foundation does not own its full implementation, but must **coordinate** the outbox-emission change with the novel-platform team. This sub-component is a **contract** that glossary-service must implement before L5 push works.

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.A.1 | `contracts/events/canon.go` (+ Rust + TS) | Schema | Authoritative `canon.change.*` event types (promoted, updated, decanonized, l1_axiom_change) |
| L5.A.2 | `contracts/events/xreality_canon.go` (+ Rust + TS) | Schema | `xreality.book.canon.updated` envelope (per M4-D5 payload: book_id, attribute_path, old_value, new_value, canon_layer, propagation_mode) |
| L5.A.3 | `docs/governance/glossary-service-outbox-contract.md` | Doc | Contract document for novel-platform team: glossary-service MUST emit these events via outbox |
| L5.A.4 | `services/glossary-service/migrations/0099_outbox_table.sql` (sister to existing) | SQL | Add outbox table (same pattern as L2.C.1 events_outbox) — CHANGE TO EXISTING SERVICE |
| L5.A.5 | `tests/contract/canon_event_contract_test.go` | Test | Schema test: glossary-service emits valid event matching contract |

**Acceptance criteria:**
- Schema in place (foundation owns)
- Contract document signed-off by novel-platform team
- Contract test fails if glossary-service emits schema-violating events

**Open question:**
- Q-L5A-1: glossary-service migration to outbox pattern — V1 of foundation or separate sub-program? Suggested: **separate sub-program** before L5 push activates; foundation owns contract + test fixture.

---

### L5.B — meta-worker canon-update consumer

**Owning chunks:** R05 §12E.3 (meta-worker consumer protocol), M4 §9.8.5 (consumption + reality.last_canon_sync_at update)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.B.1 | `services/meta-worker/internal/canon_consumer/` Go | Code | Consumes `xreality.book.canon.updated` Redis Stream |
| L5.B.2 | `services/meta-worker/internal/canon_router/` Go | Code | Routes event to ALL realities subscribed to `book_id` |
| L5.B.3 | `services/meta-worker/internal/canon_writer/` Go | Code | For each affected reality: writes to per-reality `canon_projection` table (L5.D) via per-reality DB connection |
| L5.B.4 | `services/meta-worker/internal/reality_subscription/` Go | Code | Looks up `WHERE book_id = ? AND status IN ('active', 'frozen')` in reality_registry to find subscribers |
| L5.B.5 | `tests/integration/canon_propagation_test.go` | Test | Emit canon.change → verify all subscribed realities get update within 2s P99 |
| L5.B.6 | `runbooks/meta-worker/canon_lag.md` | Doc | SRE runbook |
| L5.B.7 | `contracts/observability/inventory.yaml` entries | Registry | `lw_canon_propagation_lag_seconds{book_id, propagation_mode}` |

**Acceptance criteria:**
- Propagation lag < 2s P99 for read_through mode
- Force-propagate mode triggers compensating event flow (see L5.H)
- meta-worker is sole writer to per-reality canon_projection (I7 enforced)
- At-least-once delivery; dedupe via correlation_id (per R05 §12E.3)

---

### L5.C — meta-worker user-erased consumer

**Owning chunks:** R05 §12E.3 (xreality.user.deleted), S08 §12X.6 (erasure runbook step 5)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.C.1 | `services/meta-worker/internal/user_erased_consumer/` Go | Code | Consumes `xreality.user.deleted` |
| L5.C.2 | `services/meta-worker/internal/pc_tombstone_writer/` Go | Code | For each reality where user has PC: writes tombstone (display name → `[erased]`, preserve structural ID) |
| L5.C.3 | `tests/integration/user_erasure_propagation_test.go` | Test | Emit user.deleted; verify all PCs in N realities tombstoned within 1h (S08 SLA) |
| L5.C.4 | `runbooks/erasure/propagation_failure.md` | Doc | SRE runbook |

**Acceptance criteria:**
- Tombstoning completes within 1h of erasure event
- Structural PC ID preserved (canon integrity per S08 §12X.6)
- Audit row in `admin_action_audit` linking erasure → tombstone events

---

### L5.D — Per-reality `canon_projection` table

**Owning chunks:** S09 §12Y.4 Layer 3 (`[WORLD_CANON]` section format), M4 §9.8.2 (cascade read-through), 03 multiverse §3 (cascade rule)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.D.1 | `contracts/migrations/per_reality/0009_canon_projection.sql` | SQL | Schema: `canon_entry_id UUID PK`, `book_id UUID`, `attribute_path TEXT`, `value JSONB`, `canon_layer TEXT` (`L1_axiom|L2_seeded`), `lock_level TEXT`, `source_event_id UUID NULL`, `cascaded_from_reality_id UUID NULL` (cascade read-through tracking), `last_synced_at TIMESTAMPTZ`, `overridden_by_l3_event_id UUID NULL` |
| L5.D.2 | `contracts/migrations/per_reality/0010_canon_projection_indexes.sql` | SQL | Indexes: `(book_id, canon_layer)`, partial `(attribute_path) WHERE overridden_by_l3_event_id IS NULL`, `(last_synced_at)` |
| L5.D.3 | `crates/projections/canon/` Rust | Code | (L3.B extension) Projection module — applies canon events to canon_projection |
| L5.D.4 | `tests/integration/canon_projection_test.rs` | Test | Apply L2 canon entry → projection has correct row; apply L3 override → `overridden_by_l3_event_id` populated; cascade read-through populates from ancestor reality (per multiverse §3) |

**Acceptance criteria:**
- Canon projection populated correctly via meta-worker writes
- Cascade rule respected (L3 override wins per multiverse §3)
- `last_synced_at` updated on every write

---

### L5.E — Per-reality canon cache (hot read)

**Owning chunks:** S09 §12Y.4 (`[WORLD_CANON]` section), perf optimization for prompt assembly hot path

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.E.1 | `contracts/prompt/canon_cache.rs` (+ Go) | Code | In-process LRU cache of `(book_id, attribute_path) → canon_value` |
| L5.E.2 | `contracts/prompt/canon_cache.go` | Code | Go-side same patterns |
| L5.E.3 | `contracts/prompt/canon_reader.rs` (+ Go) | Code | `read_canon(reality_id, attribute_path)` — checks cache → per-reality projection (L5.D) → RPC to glossary-service for full body if needed |
| L5.E.4 | `tests/integration/canon_cache_test.rs` | Test | Hit rate ≥ 90% in steady-state prompt assembly load |
| L5.E.5 | `contracts/observability/inventory.yaml` entries | Registry | `lw_canon_cache_hit_rate{reality_id}` |

**Acceptance criteria:**
- Cache hit < 1ms; miss to projection < 10ms; miss to RPC < 50ms P99
- Cache invalidation on `last_synced_at` change (event-driven)
- Hit rate ≥ 90% under typical prompt assembly load

---

### L5.F — RPC contract glossary-service ↔ roleplay-service / world-service

**Owning chunks:** S11 §12AA (ACL matrix), S09 §12Y (prompt assembly canon read), 04 (reality seeding)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.F.1 | `contracts/api/glossary-service/canon_read.yaml` | OpenAPI | RPC `GET /canon/{book_id}/entries?since=last_synced_at` |
| L5.F.2 | `contracts/api/glossary-service/seed_export.yaml` | OpenAPI | RPC `GET /canon/{book_id}/seed_export` — bulk export for reality seeding (L5.G) |
| L5.F.3 | `contracts/service_acl/matrix.yaml` entries | ACL | Add: `roleplay-service → glossary-service GetCanonEntries` (`requires_user`), `world-service → glossary-service ExportCanonForSeed` (`system_only`) |
| L5.F.4 | `clients/rust/glossary_client.rs` | Code | Generated Rust client (per L4.G `contractgen`) |
| L5.F.5 | `tests/integration/canon_rpc_test.rs` | Test | RPC calls respect ACL; rejected without SVID; full audit in `service_to_service_audit` |

**Acceptance criteria:**
- ACL enforced (SVID required)
- RPC respects `since=last_synced_at` for incremental sync
- Audit row per call (full audit per Q-L1A-3)

---

### L5.G — world-service reality-seed flow

**Owning chunks:** 00_overview §7.3 (instance lifecycle CREATE), R04 §12D.1 step 5 (background seeding), R09 §12R.2 (reality bootstrap), M-REV-5 (translated content for non-source locale)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.G.1 | `services/world-service/internal/reality_seeder/` Rust | Code | Background worker invoked after `status=seeding` |
| L5.G.2 | `services/world-service/internal/reality_seeder/book_reader.rs` | Code | RPC client to `book-service` — reads regions (initial geography) |
| L5.G.3 | `services/world-service/internal/reality_seeder/canon_reader.rs` | Code | RPC client to `glossary-service` — calls L5.F.2 `ExportCanonForSeed` |
| L5.G.4 | `services/world-service/internal/reality_seeder/knowledge_reader.rs` | Code | RPC client to `knowledge-service` — reads NPC proxies |
| L5.G.5 | `services/world-service/internal/reality_seeder/translation_orchestrator.rs` | Code | If `reality.locale != book.source_locale`: triggers translation-service (M-REV-5) |
| L5.G.6 | `services/world-service/internal/reality_seeder/checkpointer.rs` | Code | Checkpoint every 100 regions; resumable on failure |
| L5.G.7 | `services/world-service/internal/reality_seeder/lifecycle_transitioner.rs` | Code | On success: `AttemptStateTransition(reality_id, 'seeding' → 'active')` |
| L5.G.8 | `contracts/service_acl/matrix.yaml` entries | ACL | world-service → book-service, world-service → glossary-service (already L5.F.3), world-service → knowledge-service, world-service → translation-service |
| L5.G.9 | `tests/integration/reality_seed_test.rs` | Test | Provision reality → seeder runs → all initial state populated → status transitions to active |
| L5.G.10 | `runbooks/reality_seed/stuck_seeding.md` | Doc | SRE runbook for seeder failure (R04 §12D.1 + R09 §12R.2 says "admin intervention if stuck") |

**Acceptance criteria:**
- Seeding completes for typical book within 5min P99
- Resumable: kill seeder mid-flight, restart, completes without duplication
- Lifecycle transition to `active` correct
- All canon entries from book present in per-reality canon_projection after seed

---

### L5.H — Force-propagate compensating event mechanism (M4-D3)

**Owning chunks:** M4 §9.8.3 (force-propagate gates + per-reality consent)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.H.1 | `services/meta-worker/internal/force_propagate/` Go | Code | Orchestrates per-reality consent request + compensating L3 event writes |
| L5.H.2 | `services/meta-worker/internal/force_propagate/consent_collector.rs` Rust (?) | Code | Sends consent request to reality owners; waits for ack/veto |
| L5.H.3 | `services/world-service/internal/compensating_event_writer/` Rust | Code | Writes compensating L3 event in target reality |
| L5.H.4 | `contracts/events/admin_canon_override.go` | Schema | New event type per R13-L2 `admin_override` pattern |
| L5.H.5 | `tests/integration/force_propagate_test.go` | Test | Author force-propagates canon edit; 5 realities ack, 1 vetoes; verify 5 get compensating event, 1 skipped |
| L5.H.6 | `runbooks/canon/force_propagate.md` | Doc | SRE runbook |

**Acceptance criteria:**
- 3-gate flow enforced (opt-in + owner consent + R13 audit)
- Veto correctly skips per-reality propagation
- Compensating event correctly emitted in audit-distinguishable form

**Open question:**
- Q-L5H-1: Consent timeout — author waits how long for reality-owner ack? Suggested: 24h; on no-response, default to consent (per "ownerless / abandoned realities" residual in M4 §9.8.7). Need governance lock.

---

### L5.I — L1 axiomatic conflict detection (M4-D4)

**Owning chunks:** M4 §9.8.4 (L1 conflict warning), §9.7.4 (L2 → L1 promotion harder gate)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.I.1 | `services/meta-worker/internal/l1_conflict_detector/` Go | Code | On L1 canon update event: scans per-reality projections for L3 events conflicting |
| L5.I.2 | `services/meta-worker/internal/l1_conflict_reporter/` Go | Code | Returns conflict list to authoring UI (cross-service callback or polling) |
| L5.I.3 | `crates/contracts-prompt/canon_guardrail.rs` | Code | Runtime canon-guardrail flags/rejects conflicting future L3 writes (M4 §9.8.4) |
| L5.I.4 | `tests/integration/l1_conflict_test.go` | Test | Inject L3 events conflicting with proposed L1; detector reports all conflicts |
| L5.I.5 | `runbooks/canon/l1_conflict_resolution.md` | Doc | SRE runbook (manual review for forced-through L1 updates) |

**Acceptance criteria:**
- Detector finds all conflicting L3 events
- Canon-guardrail rejects future L3 writes that contradict L1
- Existing conflicting L3 stays historical but canonically void per M4 §9.8.4

---

### L5.J — Glossary entity change timeline contract

**Owning chunks:** M4 §9.8.6 (author-facing history)

**Artifacts:**

| ID | Artifact | Type | Notes |
|---|---|---|---|
| L5.J.1 | `contracts/events/canon_change_history.go` | Schema | Per-attribute change history event |
| L5.J.2 | `services/meta-worker/internal/canon_history_writer/` Go | Code | Aggregates `canon.change.*` events into queryable history per attribute |
| L5.J.3 | `contracts/api/glossary-service/canon_history.yaml` | OpenAPI | RPC for author-UI to query history |

**Note:** Author-UI implementation is out of foundation. Foundation owns the contract.

**Acceptance criteria:**
- History query returns all changes per `(book_id, attribute_path)` with propagation status
- Per-reality drill-down available

---

## §3. L5 cross-component dependency graph

```
L5.A (glossary outbox) ←─ glossary-service team (coordination required, NOT foundation impl)
L5.A ─→ Publisher (L2.D) — drains glossary outbox

Publisher (L2.D) ─→ Redis Streams xreality.book.canon.updated
                                     │
                                     ▼
L5.B (meta-worker consumer) ─→ L5.D (per-reality canon_projection)
L5.C (user-erased consumer) ─→ per-reality pc_projection tombstones

L5.D ─→ L5.E (cache reads it)
L5.E ─→ L4.D contracts/prompt/ [WORLD_CANON] section (hot path)

L5.F (RPC contract) ←─ glossary-service + world-service + roleplay-service
L5.F ─→ L4.M contracts/service_acl/ (ACL matrix entries)

L5.G (reality seeder) ←─ L5.F (RPC clients) + L1.C (provisioner — invoked on status=seeding)
L5.G ─→ L5.D (writes initial canon projection)

L5.H (force-propagate) ←─ L5.B + R13-L2 admin override pattern
L5.I (L1 conflict) ←─ L5.B + per-reality projections (L3.A)
L5.J (history) ←─ L5.B + L5.A events

Approximate ordering: L5.A (contract) → L5.D (per-reality schema) → L5.B + L5.C (meta-worker consumers) → L5.E + L5.F (cache + RPC) → L5.G (seeder) → L5.H + L5.I + L5.J (advanced flows)
```

---

## §4. Acceptance criteria for whole L5 (RAID verify gate)

- Glossary-service contract test green
- Canon propagation lag < 2s P99 (read_through mode)
- User-erased propagation < 1h
- Reality seeding completes < 5min for typical book
- Force-propagate 3-gate flow enforced
- L1 conflict detector finds 100% of conflicts (no false negatives in test fixture)
- Cache hit rate ≥ 90% in prompt assembly load

---

## §5. Open questions surfaced during L5 enumeration

| # | Question | Suggested resolution | Status |
|---|---|---|---|
| Q-L5A-1 | glossary-service outbox migration — V1 of foundation or separate sub-program? | Separate sub-program; foundation owns contract + tests | Suggested |
| Q-L5H-1 | Force-propagate consent timeout | 24h; default-to-consent on no-response | Suggested — needs governance lock |
| Q-L5-1 | Canon cache invalidation strategy — event-driven vs TTL? | Event-driven (per `last_synced_at` change); TTL 60s as fallback | Suggested |
| Q-L5-2 | translation-service for reality seeding (M-REV-5) — V1 or V2+? | V1 if reality.locale != book.source_locale (per M-REV-5) | Confirmed by M-REV-5 |
| Q-L5-3 | `canon_projection` schema — single table or per-canon-layer (L1, L2)? | Single table with `canon_layer` column | Suggested |
| Q-L5-4 | RPC vs gRPC vs HTTP/JSON for glossary-service RPC? | HTTP/JSON V1 (consistent with existing LoreWeave novel platform); gRPC V2+ if perf demands | Suggested |
| Q-L5-5 | L1 axiomatic — runtime canon-guardrail rejects future L3 conflicts. How? | Roleplay-service prompt-assembly stage checks proposed event against `canon_guardrail.rs` (L5.I.3) before write | Suggested |

---

## §6. Cycle decomposition hint for L5

| Cycle | Scope | Why grouped |
|---|---|---|
| L5-cycle-1 | L5.A (contracts) + L5.D (per-reality canon_projection table) | Schema + contract foundation; depends on per-reality DB exists from L1+L2 |
| L5-cycle-2 | L5.B + L5.C (meta-worker consumers) | Both consumers in meta-worker; share infrastructure |
| L5-cycle-3 | L5.E + L5.F (cache + RPC) | Read-path infrastructure for `[WORLD_CANON]` |
| L5-cycle-4 | L5.G (reality seeder) | Substantial new world-service component; depends on RPC + canon projection exist |
| L5-cycle-5 | L5.H + L5.I + L5.J (force-propagate + conflict detection + history) | Advanced flows; lower priority |

**Total L5 estimate: ~5 RAID XL cycles.**

---

## §7. Status

```
[x] L5 — 10 sub-components enumerated at B-level (A-J)
[x] L5 — cross-component deps mapped
[x] L5 — 7 open questions surfaced (6 suggested, 1 confirmed)
[x] L5 — cycle decomposition hint (~5 cycles)
[ ] L5 — open questions resolved (batch at end of all layers)
[ ] Continue to L6 (WS + Obs/Cap + LLM safety pre-spec)
```
