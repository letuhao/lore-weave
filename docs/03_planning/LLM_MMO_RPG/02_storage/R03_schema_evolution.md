<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R03_schema_evolution.md
byte_range: 51819-61548
sha256: 2a89cc1fb66e7c2e4686202b516b48c2b4310d78b85b4719618cbc3a32cd27eb
generated_by: scripts/chunk_doc.py
-->

## 12C. Event Schema Evolution (R3 mitigation)

Unlike R1 (volume) and R2 (rebuild), R3 is a **discipline problem**, not a one-shot fix. Without tooling, schema evolution cost compounds; with tooling, it stays linear. The strategy below locks discipline + tooling together.

### 12C.1 Layer 1 — Additive-first discipline

Default stance: **do not modify existing event types**. Prefer, in order:

1. Add a new **optional** field (MINOR bump, backward compatible, trivial upcaster)
2. Introduce a **new event type** for semantically different behavior (see L5)

Only when neither works is the existing event_version bumped with a non-trivial upcaster.

**Rule:** when naming trade-offs vs schema stability come up, choose stability.

### 12C.2 Layer 2 — Schema-as-code + registry

Every event type and version is a typed struct in code. Upcasters are code. A registry generator extracts metadata into a lookup table.

**Example (Go):**

```go
// events/pc.go

// @event pc.said
// @version 1
type PCSaid_V1 struct {
    Content string `json:"content"`
}

// @event pc.said
// @version 2
// @description Added optional speech_act classification
type PCSaid_V2 struct {
    Content   string `json:"content"`
    SpeechAct string `json:"speech_act,omitempty"`
}

// @upcast pc.said 1 -> 2
func UpcastPCSaid_1_to_2(raw json.RawMessage) (PCSaid_V2, error) {
    var v1 PCSaid_V1
    if err := json.Unmarshal(raw, &v1); err != nil {
        return PCSaid_V2{}, err
    }
    return PCSaid_V2{Content: v1.Content}, nil
}

type PCSaid = PCSaid_V2  // CURRENT alias
```

**Registry generator** (CI tool, language-agnostic):
- Parses annotations across all files
- Generates `events/registry.go` with dispatch table `(event_type, event_version) → struct + upcaster chain`
- Generates TypeScript + Python bindings from same annotations (see L7 polyglot strategy below)
- CI fails if: upcaster missing between versions, schema change without version bump, undocumented event_type

**Decision — single source of truth:**
- **Go structs are authoritative** (event producer services are mostly Go: world-service, auth-service, book-service)
- Codegen tool produces TypeScript types (for frontend + api-gateway-bff) and Python types (for roleplay-service, knowledge-service, chat-service)
- One repo location for event schemas: `contracts/events/` at monorepo root
- Changes require PR review across affected services

**Storage for registry:**
- Git-versioned files + codegen output (no separate registry microservice)
- Registry is read-at-startup by services, cached in memory
- Registry changes require service restart (not dynamic reload in V1)

### 12C.3 Layer 3 — Upcaster chain on read

Already framed in §10. Refined:

```
Read path:
  1. SELECT raw events from DB
  2. For each: look up (event_type, event_version) in registry
  3. If event_version < latest_version:
     apply upcaster chain v_n → v_n+1 → ... → latest
  4. Return upcast events to projection fold
```

Chain is automated — registry builds it from individual `@upcast` annotations. Developer never manually composes `v1 → v4` — they just write `v1 → v2`, `v2 → v3`, `v3 → v4` and registry stitches them.

Events stored on disk are **never modified**. Immutability preserved.

### 12C.4 Layer 4 — Schema validation on write

Every event append goes through schema validation:

```go
func AppendEvent(ctx context.Context, evt Event) error {
    schema := registry.Get(evt.EventType, evt.EventVersion)
    if schema == nil {
        return ErrUnknownEventSchema
    }
    if err := schema.Validate(evt.Payload); err != nil {
        return fmt.Errorf("schema violation for %s v%d: %w",
            evt.EventType, evt.EventVersion, err)
    }
    return appendToEventsTable(ctx, evt)
}
```

Config:
```
storage.events.schema_validation.enabled = true   # strict in ALL environments
```

Prevents malformed events from entering the log — bugs fail at write time, not at projection-rebuild time two weeks later.

### 12C.5 Layer 5 — Breaking change = new event type

When a true semantic change is needed (existing event's meaning changes), **do not bump event_version**. Instead:

1. Mark old event type `deprecated: true` in registry — emits warning on write
2. **Register upcaster `deprecated_type → new_type`** (amendment per H4 review 2026-04-24) — events of the deprecated type are translated to new type on read
3. Stop writing old events from new code
4. Introduce new event type (e.g., `pc.moved_v2` → though prefer semantically named `pc.teleported`)
5. Projection consumes both old and new types for a transition period; upcaster handles old events transparently
6. After **90 days** (configurable) + confirmed no old events in hot storage: old handler can be dropped; upcaster chain handles any archive restores
7. R3-L6 archive-upgrade (when activated V2+) can bake upcaster into archived events for simpler restore

**Cooldown config:**
```
storage.events.deprecated_type_cooldown_days = 90
storage.events.deprecated_type_requires_upcaster = true   # H4 amendment — mandatory
```

**Rationale:** better to have `pc.said_v2` as a new type than an upcaster that reinterprets `pc.said v3` as "same thing but different meaning." Explicit > implicit.

**H4 amendment rationale:** without upcaster-to-new-type, old events in hot storage would fail projection rebuild after handler drop. Upcaster requirement guarantees hot-storage events are always consumable by current projection logic.

### 12C.6 Layer 6 — Archive upgrade (deferred V2)

When events are archived to MinIO cold storage (R1-L4), an ideal approach is to **upcast to latest version** before writing cold. This keeps the upcaster chain bounded going forward.

**V1 decision: NOT implemented.** Archive writes events in their original version. Upcaster chain handles them at restore time.

**V2 plan:** introduce archive upgrade job:
```
Monthly archive:
  for each event in partition being detached:
    upcast(event, to: latest_version_at_archive_time)
  write to Parquet with schema=latest
  checksum + upload to MinIO
  delete from Postgres
```

Benefits at scale: shorter upcaster chains, simpler restore. Risk: if upcaster has a bug, cold archive permanently corrupted — mitigated by V1-time test harness being mature before V2 activation.

### 12C.7 Polyglot type generation

LoreWeave services span Go, Python, and TypeScript. Event schemas must stay in sync across all three.

**Strategy:**
- Go is source of truth (annotated structs in `contracts/events/`)
- Codegen tool (`eventgen`) produces:
  - `contracts/events/generated/ts/` — TypeScript interfaces for frontend + api-gateway-bff
  - `contracts/events/generated/python/` — Pydantic models for Python services
- Codegen runs in CI; generated files committed so consumers don't need Go toolchain
- Services import generated types; never hand-write event types

**CI gates:**
- Go struct changes without regenerated TS/Python → CI fail
- Generated files modified directly without source change → CI fail
- New event type without `@description` annotation → CI fail

### 12C.8 Expected maintenance cost

With tooling + discipline:

| Change kind | Dev effort | Risk |
|---|---|---|
| Add new event type | 1–2 hours | Low |
| Add optional field (MINOR) | 30 min | Low |
| Rename field / semantic change | 2–4 hours | Medium |
| Breaking change (new event_type via L5) | 4–8 hours | Medium |
| Remove deprecated event type after cooldown | 1 hour | Low |

Projected cost at mature scale (40 event types × 2 versions avg after 3 years):
- 80 version/type changes × 1–2 hours = **80–160 dev-hours over 3 years** ≈ 3–5 dev-hours/month
- Linear scaling, not compounding

### 12C.9 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 additive discipline | Occasional suboptimal field naming (accepted for stability) |
| L2 schema-as-code + codegen | ~2 weeks upfront tooling; ongoing CI maintenance |
| L3 upcaster chain on read | +0.5–1 ms read latency per event per version gap |
| L4 schema validation on write | +0.5 ms write latency per event |
| L5 new event_type for breaking change | Event type proliferation; projection logic forks |
| L6 archive upgrade (V2+) | Archive job complexity; correctness-critical |
| Polyglot codegen | Every event change touches 3 languages (auto-generated but still PR diff) |

Main cost is L2 upfront tooling. Without it, R3 compounds; with it, R3 stays linear. Worth the investment.

### 12C.10 Implementation ordering

- **V1 launch**: L1 (discipline), L2 (schema-as-code + codegen), L3 (upcaster chain), L4 (validation on write). Mandatory — can't start event sourcing without these.
- **V1 + ongoing**: L5 (new event_type for breaking changes) as policy
- **V2**: L6 archive upgrade when cold archive volume justifies
- **V1+30d → V3**: DF10 (see 12C.11) matures

### 12C.11 Tooling surface (deferred to DF10)

The mechanisms above require tooling. Admin + dev tooling around schema evolution is substantial:

- Schema registry viewer (browse all event types, versions, upcasters)
- Upcaster test harness (load sample events, validate chains)
- Codegen CLI (`eventgen generate` / `eventgen validate`)
- Deprecation dashboard (which types are deprecated, what hot-storage counts remain)
- Cross-service schema sync verifier
- Documentation auto-generation from annotations

Deferred to **DF10 — Event Schema Tooling**. Mechanisms (L1–L5) locked here in §12C; dev UX + CI integration is DF10's scope.

