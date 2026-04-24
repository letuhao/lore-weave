<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: HMP_followups.md
byte_range: 189001-203334
sha256: 514fdb6cee3fba33696062cc1dafbb0190d4e4eb72242649c3992b1906d647b7
generated_by: scripts/chunk_doc.py
-->

## 12R. Adversarial Review Follow-ups (H/M/P tier, 2026-04-24)

**Origin:** SA+DE adversarial review raised 16 additional concerns beyond the 5 Critical (C1-C5). Consolidated here for scannability. Most are observability/doc-level; two substantive: H3 (session caps + queue UX, reversing doppelganger proposal) and H5 (bootstrap worker + seeding state).

### 12R.1 Session Size Caps + Queue UX (H3 revised)

**Framing:** Popular NPC ("tavern keeper Elena") bottleneck under R7-L6 single-session constraint.

**Design stance** (user directive 2026-04-24): realistic world semantics preferred over MMO cloning. NPC single-session is **permanent**, not V2+ stopgap. Doppelganger pattern rejected. Multi-presence (R7-L6 alternative) rejected permanently, removed from V3+ roadmap.

Popular NPC queue becomes **first-class UX feature**, not emergency backstop. Scarcity = gameplay.

#### 12R.1.1 Session size caps

Realistic table sizes, configurable per-reality via DF4:

| Session type | Max PCs | Max NPCs | Max total |
|---|---|---|---|
| **Default** (tavern, small gathering) | 6 | 4 | 10 |
| **Intimate** (private conversation, duel) | 2 | 2 | 4 |
| **Large gathering** (council, ritual, rare) | 10 | 6 | 16 |

V1 default: 6/4/10. DF4 allows per-reality override.

```sql
ALTER TABLE reality_registry
  ADD COLUMN session_max_pcs INT NOT NULL DEFAULT 6,
  ADD COLUMN session_max_npcs INT NOT NULL DEFAULT 4,
  ADD COLUMN session_max_total INT NOT NULL DEFAULT 10;
```

**When cap reached** (new PC requests to join full session):
- System rejects with explicit reason + surfaced alternatives
- User sees: queue-wait / new-session-different-NPCs / travel / reschedule options

#### 12R.1.2 Queue UX — first-class feature

```sql
CREATE TABLE npc_session_queue (
  queue_id              BIGSERIAL PRIMARY KEY,
  npc_id                UUID NOT NULL,
  pc_id                 UUID NOT NULL,
  reality_id            UUID NOT NULL,
  joined_queue_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  estimated_wait_seconds INT,
  position_hint         INT,
  notified_at           TIMESTAMPTZ,
  expired_at            TIMESTAMPTZ
);
CREATE INDEX ON npc_session_queue (npc_id, joined_queue_at);
CREATE INDEX ON npc_session_queue (pc_id);
```

Queue UI surfaces:
- Position in queue + estimated wait time
- Notification when slot opens
- Alternative NPCs in same region
- Scheduled availability hints (if NPC has office hours, §12R.1.3)

#### 12R.1.3 NPC availability schedule (V2+ hook)

Popular NPCs can have explicit "office hours" — creates real-world-like rhythm:

```sql
CREATE TABLE npc_availability_schedule (
  npc_id        UUID NOT NULL,
  reality_id    UUID NOT NULL,
  day_of_week   INT,                -- 0-6, NULL = every day
  start_time    TIME,
  end_time      TIME,
  reason        TEXT,                -- e.g. "quest briefing hours"
  PRIMARY KEY (npc_id, reality_id, day_of_week, start_time)
);
```

V1 schema reserved, feature disabled. V2+ enables. Advance booking + reservation mechanics belong to DF5 when it lands.

#### 12R.1.4 Config

```
session.max_pcs_default = 6
session.max_npcs_default = 4
session.max_total_default = 10
session.queue.max_depth_default = 20             # queue cap per NPC
session.queue.wait_estimate_algo = "sliding_window_p50"
session.queue.notify_when_slot_opens = true
session.queue.expire_entry_after_hours = 24
npc.availability_schedule.enabled = false        # V2+
```

#### 12R.1.5 R7-L6 upgrade — permanent, not deferred

[§12G.7](#12g7-npc-in-multiple-sessions-simultaneously) previously framed NPC single-session as "V1 constraint, multi-presence deferred V2+." **Upgraded to PERMANENT design.**

R7-L6 stance change:
- ~~"V2+ alternative: multi-presence"~~ — REMOVED from roadmap
- NPC single-session is intentional realism, not scaling workaround
- Popular-NPC bottleneck solved by session caps + queue UX, not by cloning

#### 12R.1.6 Implementation ordering

- **V1 launch**: session cap fields on reality_registry + enforcement on session join + queue table + basic queue UI
- **V1 + 30 days**: queue notifications + alternative-NPC suggestions
- **V2**: availability schedule + reservation mechanics (part of DF5)
- **V3+**: DF4 per-reality rule overrides surfaced to author

### 12R.2 Reality Bootstrap Process — `seeding` state + worker (H5 + M-REV-5)

**Framing:** For a book with 50K glossary entities and 1000 regions, synchronous bootstrap during reality creation would block user for minutes. Plus: locale translation needed when reality locale ≠ book source locale.

#### 12R.2.1 New `seeding` lifecycle state

Inserted between `provisioning` (DB creation) and `active` (ready for play):

```
admin/user requests reality
  ↓
provisioning  — CREATE DATABASE + extensions + schema migrations (<30s)
  ↓
seeding       — background worker seeds NPC proxies, regions, translates content
  ↓ (resumable, idempotent, progress-reportable)
active        — ready for play
```

CAS-protected per §12Q. Mutual exclusion with all other lifecycle states.

#### 12R.2.2 Bootstrap worker

**Service:** folded into existing `migration-orchestrator` (same pattern — long-running stateful job with checkpoint state in meta registry). Avoids service proliferation.

**Workflow:**
```
bootstrap_reality(reality_id):
  FOR each book region → create region aggregate in reality DB (checkpoint every 100)
  FOR each glossary entity marked player-relevant → create npc_proxy with core_beliefs
  IF reality.locale != book.source_locale:
    invoke translation-service for NPC greetings + region descriptions + item names
    cache localized content in reality DB
  Snapshot initial state
  AttemptStateTransition(reality_id, 'seeding', 'active')
```

Progress reported to UI via `reality_bootstrap_progress` metric per checkpoint.

#### 12R.2.3 Locale translation integration (M-REV-5)

If `reality.locale ≠ book.source_locale`:
- Translation-service invoked during seeding
- Translated content cached in reality-local tables (becomes part of L3 state once reality starts play)
- Translation latency factored into bootstrap budget

Config:
```
reality.bootstrap.translate_on_mismatch = true
reality.bootstrap.translation_service_url = "http://translation-service:8080"
reality.bootstrap.translation_timeout_seconds = 60   # per entity
reality.bootstrap.target_max_minutes = 30
reality.bootstrap.progress_update_interval_seconds = 5
reality.bootstrap.checkpoint_every_entities = 100
reality.bootstrap.max_retries = 5
```

Bootstrap time budget:
- No translation: 1-5 min typical, <15 min for large books
- With translation: +50-100% depending on book size

#### 12R.2.4 Failure + retry

Worker checkpoints every 100 entities. On failure:
- Retry from last checkpoint (up to 5 retries, exponential backoff)
- After max retries: reality stuck in `seeding` status with error record
- Admin intervention: `admin-cli reality-bootstrap-resume --reality=X` OR `--abort --cleanup`

### 12R.3 Deprecated Event Type Upcaster Requirement (H4)

**Framing:** R3-L5 breaking-change path (§12C.5) was "deprecate old type, drop handler after 90d." But old events in hot storage would fail projection rebuild after handler drop.

**Amendment:** breaking change requires **upcaster from deprecated_type → new_type**.

**Updated §12C.5 contract:**
1. Introduce new event type
2. Mark old type `deprecated: true` + register upcaster `deprecated_type → new_type`
3. During 90-day cooldown: both types coexist; projection handler consumes both; upcaster translates deprecated → new on read
4. After cooldown, before dropping old handler:
   - Option A (preferred): R3-L6 archive-upgrade path runs upcaster on all events of deprecated type
   - Option B (fallback): keep upcaster + handler in "legacy replay" mode indefinitely for archived events

Hot storage never has events the projection can't handle. Archive restores walk upcaster chain.

```sql
-- Schema addition to event registry (R3-L2 codegen output)
event_schema_registry row includes:
  is_deprecated BOOLEAN
  deprecated_since TIMESTAMPTZ
  superseded_by_event_type TEXT
  upcaster_function_ref TEXT
```

### 12R.4 Cross-Cutting Observability (H1, H2, H6, M-REV-6)

Metrics added to cover concerns that need visibility but no mechanism change:

```
-- H1 Region aggregate contention
lw_region_aggregate_retry_rate{region_id, reality_id}    gauge
  alert: > 5% retry rate

-- H2 BIGSERIAL contention
lw_event_sequence_wait_ms                                 histogram
  alert: p99 > 10ms (threshold warning)

-- H6 Cascade depth
lw_cascade_depth_histogram{reality_id}                    histogram
lw_cascade_read_latency_ms{depth}                          histogram
  alert: p99 depth > 4 (approaching MV9 limit → auto-rebase recommended)

-- M-REV-6 Consumer cursor skew
lw_consumer_cursor_skew_seconds{consumer_a, consumer_b, reality_id}  gauge
  alert: > 5s skew between any pair of consumers
```

DF11 admin dashboard surfaces these. No mechanism changes; discipline via observability.

### 12R.5 HNSW Pre-warm on Reality Thaw (M-REV-3)

**Framing:** pgvector HNSW index cold after reality `frozen → active` transition. First queries slow.

**Fix:** pre-warm step added to thaw flow:
```sql
-- Triggered by AttemptStateTransition(..., from='frozen', to='active')
SELECT embedding FROM npc_pc_memory_embedding
  WHERE reality_id = $1
  LIMIT 100;
-- Forces buffer pool to load + HNSW navigable graph
```

~1-2 seconds overhead on thaw. Acceptable for rare event.

Added to §12K as §12K.8 Pre-warm on Thaw.

### 12R.6 L1 Critical Sync-Check Cross-Reference (M-REV-4)

**Framing:** Async G3 linter catches L1 violations post-response. User already saw bad output before detection.

**Scope:** This is **05_LLM_SAFETY_LAYER** territory, not storage/multiverse. Cross-reference only.

Rule sketch (to be implemented in 05 work):
- L1 attributes tagged `l1_severity = 'critical'` (species_exists, magic_fundamental, physics_laws)
- Critical-L1 sync pre-response check (~50-100ms) on LLM output before streaming to user
- Non-critical L1 + L2 drift → async G3 linter (existing)

Cross-ref added to [03 §3 four-layer canon](03_MULTIVERSE_MODEL.md) noting L1_severity tag reserved.

### 12R.7 Projection Rebuild Determinism (P4)

**Rule (added to §5):** projections use `event.created_at` for temporal fields, not `now()`.

Exception only: true "last rebuilt at" meta fields explicitly labeled as non-deterministic. These MUST be separate from any field that gets folded from events.

Projection rebuild produces bitwise-identical result to original (excluding explicitly-marked exceptions). Enables integrity verification via diff.

### 12R.8 Validation Mechanism Clarification (P3)

**Clarification (added to §12C.4):** schema validation on write uses **typed-struct at compile time** (from R3-L2 codegen output), NOT runtime JSON Schema reflection.

Cost budget:
- Typed struct: ~0.1ms per validation
- Runtime JSON Schema (rejected): ~0.5ms per validation
- At 100K events/sec: 10s CPU vs 50s CPU per wall second
- Single core ~10% utilization at peak. Acceptable.

Already implicit; doc clarification prevents future implementer from adding runtime validation.

### 12R.9 Command Library Discoverability (P2)

**Amendment (added to §12L.1 R13-L1):** admin-cli commands carry searchable metadata:

```go
// Command registration
RegisterCommand(Command{
    Name: "admin/reset-npc-mood",
    Description: "...",
    Keywords: []string{"reset", "npc", "mood", "stuck", "behavior"},
    Category: "npc_state_ops",
    Destructive: false,
    Reversible: true,
})
```

UX:
- `admin-cli help` — categorized command index
- `admin-cli help --search "reset stuck npc"` — keyword search + category match
- `admin-cli help admin/reset-npc-mood` — command detail
- Auto-generated command reference in DF9 UI (searchable)

### 12R.10 Polish Notes

**P1 — NPC memory capacity estimate updated.** §12K.1 numbers revised:
- Conservative: 20 NPCs × 20 pairs = 400 vectors/reality = 2.4MB
- Realistic (popular): 50 NPCs × 50 pairs = 2500 vectors/reality = 15MB
- At V3 (1000 realities): 15GB total vector data + index
- Still <2% RAM at V3 scale. No change to decision.

### 12R.11 Doc Cross-References

**M-REV-1 — Freeze atomicity** (§12I): already covered by §12Q CAS pattern (C5). Cross-ref note added to §12I.1 explicitly calling out that state transition CAS + mutual exclusion obviates explicit fence.

**M-REV-2 — Session event queue retention**: config split (§12G.11):
```
session.event_queue_retention_days.applied = 7      # was 30
session.event_queue_retention_days.failed = 30       # kept for debug
```

### 12R.12 What this resolves

All 16 H/M/P concerns addressed:

| # | Concern | Mechanism |
|---|---|---|
| H1 | Region contention | ✅ Observability (§12R.4) |
| H2 | BIGSERIAL contention | ✅ Observability + documented threshold |
| H3 | Popular NPC bottleneck | ✅ Session caps + queue UX (§12R.1). R7-L6 permanent. |
| H4 | Schema drops | ✅ Upcaster for deprecated types (§12R.3) |
| H5 | Bootstrap time | ✅ `seeding` state + worker (§12R.2) |
| H6 | Cascade depth | ✅ Observability + auto-rebase recommendation |
| M-REV-1 | Freeze atomicity | ✅ Doc cross-ref (already covered by C5) |
| M-REV-2 | Queue retention | ✅ Config split (applied 7d / failed 30d) |
| M-REV-3 | HNSW cold-start | ✅ Pre-warm on thaw (§12R.5) |
| M-REV-4 | L1 enforcement | ✅ Cross-ref to 05 LLM safety |
| M-REV-5 | Locale mismatch | ✅ Translation in bootstrap (§12R.2.3) |
| M-REV-6 | Cursor skew | ✅ Observability (§12R.4) |
| P1 | Vector count estimate | ✅ Updated numbers (§12R.10) |
| P2 | Command discoverability | ✅ Keywords + search (§12R.9) |
| P3 | Validation cost | ✅ Clarified typed-struct mechanism (§12R.8) |
| P4 | Rebuild determinism | ✅ Rule added to §5 (§12R.7) |

**Storage + multiverse design passes full SA+DE adversarial review (21 concerns → all resolved or cross-referenced to deferred work).**

