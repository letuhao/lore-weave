<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R08_npc_memory_split.md
byte_range: 103908-116616
sha256: 988f285e95ad81a6684568e8d2aa5adf3a7ffaa4dab82b1c02421b5765d21519
generated_by: scripts/chunk_doc.py
-->

## 12H. NPC Memory Aggregate Split (R8 mitigation, A1 foundation)

NPC state grows linearly with interaction count. A popular NPC (tavern keeper) after 1 year with 10K PCs would have ~75MB state per snapshot in a naive design. Resolution: split NPC into core aggregate + per-pair memory aggregates. This is also the storage foundation for A1 (NPC memory at scale) — A1's semantic layer builds on this infrastructure.

### 12H.1 Core insight — linear growth must be broken

Naive NPC aggregate embedding per-PC memory:
- Elena after 1 year × 10K interacted PCs = 10K × 7.5KB = **~75MB per snapshot**
- 3 retained snapshots: **~225MB just for Elena**
- Loading NPC for turn = read 75MB + deserialize. Unworkable.

Split NPC into two aggregate types, both event-sourced:

| Aggregate type | Scope | Snapshot size |
|---|---|---|
| `npc` | Core state per NPC | ~10-20KB (stable) |
| `npc_pc_memory` | One per (npc_id, pc_id) pair | ~2-10KB per pair (bounded) |

Total per NPC at 10K interacted PCs after cold decay (L4): ~6MB steady, loaded lazily (L5) as ~2-10KB per active pair.

### 12H.2 Layer 1 — Aggregate split (core mechanism)

> **⚠ SUPERSEDED PORTIONS (2026-04-24 per §12S.2):** the `npc_pc_memory` per-pair aggregate below is **replaced** by session-scoped `npc_session_memory` + derived `npc_pc_relationship`. Core `npc` aggregate unchanged. See [§12S.2 S2](#12s-security-review--s1s2s3-resolutions-2026-04-24) for current design.

**`npc` aggregate** — core state only (UNCHANGED):
```
Aggregate ID: npc_id (UUID)
State snapshot: {
  glossary_entity_id,
  current_region_id,
  current_session_id,         // R7-L6: NPC in ≤1 session at a time
  mood,
  core_beliefs: {...},        // L1 canon reference
  flexible_state: {...}       // L3 reality-local drift
}
Size: ~10-20KB, stable regardless of player count
```

**~~`npc_pc_memory` aggregate~~** — SUPERSEDED by §12S.2.3 `npc_session_memory` aggregate.

Old per-pair memory model (for audit trail only, not current design):
```
~~Aggregate ID: uuidv5('npc_pc_memory', concat(npc_id, pc_id))~~
~~State: summary + facts + embedding_ref per pair~~
```

**Current design (§12S.2.3):**
- `npc_session_memory` aggregate: one per `(npc_id, session_id)` pair — knowledge scoped to session participation
- `npc_pc_relationship_projection`: derived stance (trust/familiarity) per `(npc_id, other_entity_id)` — small, doesn't leak knowledge
- Session-scoped model makes cross-PC leak structurally impossible

Aggregate types enum:
```
'pc' | 'npc' | 'npc_session_memory' | 'region' | 'world'
(note: 'npc_pc_memory' type name reserved but not used in current design)
```

**Event emission pattern (UPDATED per §12S.2)** — when Elena talks in session S to Alice (both in session S):
```sql
BEGIN;

-- Event on Elena (npc aggregate)
INSERT INTO events (reality_id, aggregate_type, aggregate_id, aggregate_version,
                    event_type, payload, session_id, visibility, ...)
VALUES ($reality, 'npc', $elena_id, $elena_v+1,
        'npc.said', {...}, $session_id, 'public_in_session', ...);

-- Event on Elena's session memory (npc_session_memory aggregate)
INSERT INTO events (...)
VALUES ($reality, 'npc_session_memory', $elena_session_agg_id, $sess_v+1,
        'npc_session_memory.interaction_logged', {...}, $session_id, 'public_in_session', ...);

-- Projection updates (including npc_pc_relationship_projection derivation at session-end)
-- + outbox
COMMIT;
```

Both version-bumped atomically, independent snapshot cadence.

### 12H.3 Layer 2 — Bounded memory per pair

Hard caps prevent unbounded pair growth:

```
npc_memory.max_facts_per_pc = 100            # LRU eviction over this
npc_memory.summary_rewrite_every_events = 50  # LLM compaction trigger
npc_memory.summary_max_length_chars = 2000
```

**Fact structure:**
```json
{
  "fact_id": "uuid",
  "content": "Alice defended Elena's son",
  "source_event_id": 12345,
  "importance_score": 0.8,
  "created_at": "...",
  "last_accessed_at": "..."
}
```

**LRU eviction:** when pair hits 100 facts, evict `ORDER BY last_accessed_at ASC` until ≤100.

**Summary rewrite flow:**
```
Trigger: pair receives 50 interaction events since last summary rewrite

  1. Load pair state: summary + recent facts + recent interactions
  2. LLM prompt: "Update this NPC's understanding of this PC..."
  3. Emit event: npc_pc_memory.summary_rewritten { new_summary, obsolete_facts_pruned }
  4. Prune facts that are now subsumed by summary (importance < threshold)
  5. Next 50 events → next rewrite
```

This keeps summary fresh + facts bounded.

### 12H.4 Layer 3 — Snapshot size enforcement + auto-compaction

Hard thresholds:
```
npc_memory.snapshot_size_warn_mb = 1
npc_memory.snapshot_size_critical_mb = 5
```

**On snapshot creation:** measure serialized JSONB size.
- **> warn:** log + metric + review flag
- **> critical:** trigger emergency compaction immediately (aggressive summary rewrite, drop oldest facts)

Prevents any single aggregate from becoming a hot spot.

### 12H.5 Layer 4 — Cold memory decay

Pairs with no recent interaction get progressively pruned:

| Time since last interaction | Action |
|---|---|
| 0–30 days | Full retention (summary + facts + embedding) |
| 30–90 days | Keep summary + embedding; drop facts array |
| 90–365 days | Keep summary only (short); drop embedding |
| 365+ days | Archive entire pair aggregate to MinIO; restore on PC return |

**Archive/restore:**
- Archive: dump aggregate events + snapshots to MinIO (reuses R1-L4 pipeline, per-aggregate granularity)
- Restore: on first new interaction, pull events from MinIO, rebuild projection
- Latency: 1-2 seconds for restore (acceptable for rare long-absence returns)

**Config:**
```
npc_memory.cold_decay_fact_drop_days = 30
npc_memory.cold_decay_embedding_drop_days = 90
npc_memory.archive_days = 365
```

### 12H.6 Layer 5 — Lazy loading (session-scoped)

Turn processor loads minimal state per turn:

```go
func processNPCTurn(sessionID, npcID UUID, currentSpeakerPCID UUID) {
    // Load NPC core — always needed
    npcCore := loadAggregate("npc", npcID)

    // Load memory ONLY for the PC currently speaking + others in session
    sessionPCs := getSessionPCs(sessionID)  // typically 1-10 PCs
    memories := make(map[UUID]NPCPCMemory)
    for _, pcID := range sessionPCs {
        pairID := npcPCMemoryID(npcID, pcID)
        memories[pcID] = loadAggregate("npc_pc_memory", pairID)
    }

    // Do NOT load memories of PCs not in this session
    // R7-L6 constraint: NPC in 1 session at a time → only session's PCs matter

    response := llm(npcCore, memories, sessionContext, currentSpeakerPCID)
    ...
}
```

With R7-L6 (NPC in one session at a time) + session cap (typically 5-10 PCs): max load per turn = 1 npc + ≤10 npc_pc_memory aggregates. **Bounded regardless of NPC's total interaction history.**

### 12H.7 Layer 6 — Embedding storage separation (pgvector)

Embeddings (~6KB each) are the biggest component of memory state. Keep them **outside aggregate snapshots** in a dedicated projection table:

```sql
CREATE TABLE npc_pc_memory_embedding (
  npc_id        UUID NOT NULL,
  pc_id         UUID NOT NULL,
  embedding     vector(1536),           -- pgvector
  content_hash  TEXT NOT NULL,          -- hash of what was embedded (for change detection)
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (npc_id, pc_id)
);
CREATE INDEX npc_pc_memory_embedding_hnsw
  ON npc_pc_memory_embedding USING hnsw (embedding vector_cosine_ops);
```

Aggregate events include `embedding_content_hash` and `embedding_update_token` references, not the vector itself. Actual vector in this projection table.

**Win:** snapshot size ~2KB per pair (vs ~15KB with embedded vector). 7× reduction on hot path.

**Trade:** extra lookup per turn for embedding. Fast (indexed, hot cache). Acceptable cost.

**Rebuild:** projection lost → re-run embedding generation from latest memory content (event-sourced: `npc_pc_memory.summary_rewritten` events trigger embedding refresh).

### 12H.8 Layer 7 — Observability

```
lw_npc_aggregate_count_per_reality                    gauge
lw_npc_pc_memory_aggregate_count_per_reality          gauge
lw_npc_pc_memory_snapshot_size_bytes                  histogram
lw_npc_pc_memory_fact_count                           histogram
lw_npc_pc_memory_seconds_since_interaction            histogram
lw_npc_pc_memory_archive_count_per_reality            counter
lw_npc_pc_memory_restore_count_per_reality            counter
lw_npc_memory_compaction_triggered_count              counter
```

**Alerts:**
- Snapshot size >1MB warn → review triggers
- Snapshot size >5MB critical → auto-compact fires
- High archive rate → possibly too aggressive
- High restore rate → many returning players after long absence

### 12H.9 Connection to A1 (NPC memory at scale)

[01_OPEN_PROBLEMS A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--open) was critical-path `OPEN`. With R8 resolution (this section), A1 moves to `PARTIAL`:

**What R8 provides (infrastructure):**
- Bounded state per (NPC, PC) pair
- Lazy loading (only session's PCs)
- Cold decay + archive for inactive pairs
- Separate embedding storage (pgvector)
- Size enforcement + auto-compaction

**What A1 still needs (semantic layer):**
- Retrieval quality: which facts to surface during prompt assembly?
- Summary quality: LLM prompt for compaction
- Fact extraction: what from an interaction becomes a "fact"?
- Evaluation: measurable success on real book data

R8 is the plumbing; A1 is the art. A1 design is deferred pending real data from V1 prototype.

### 12H.10 Capacity model

**Per NPC at maturity** (10K PCs interacted, with L4 decay applied):
- Active pairs (<30 days): ~100 × 2KB snapshot × 3 retained = 600KB
- Warming pairs (30-90d): ~500 × 1KB × 3 = 1.5MB
- Summary-only pairs (90-365d): ~2000 × 0.5KB × 3 = 3MB
- Archived pairs (>365d): 0 in Postgres (in MinIO)

**Total per hot NPC: ~5MB** (vs ~75MB naive). 15× reduction.

**Platform at V3** (1000 realities × 50 NPCs × ~20 active pairs avg):
- npc_pc_memory aggregate count: ~1M
- Avg snapshot size: ~2KB
- Platform storage: ~6GB npc_pc_memory across all realities
- Eminently manageable

### 12H.11 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 aggregate split | More aggregate rows (1 NPC → 1 npc + N npc_pc_memory); simpler loading |
| L2 bounded facts | Long-term detail loss (accepted; summary retains high-level memory) |
| L3 size enforcement | Auto-compaction may be aggressive; tunable |
| L4 cold decay | Returning player sees "less precise" memory after long absence; trade for storage |
| L5 lazy loading | Requires session scope discipline (already locked in R7-L6) |
| L6 embedding separation | Extra read per turn; major win on snapshot size |
| L7 observability | Metric cardinality per-pair (capped by reality) |

Main win: **linear scaling broken** — per-NPC cost bounded, grows with session participation not total history.

### 12H.12 Config keys (R8)

```
npc_memory.max_facts_per_pc = 100
npc_memory.summary_rewrite_every_events = 50
npc_memory.summary_max_length_chars = 2000
npc_memory.snapshot_size_warn_mb = 1
npc_memory.snapshot_size_critical_mb = 5
npc_memory.cold_decay_fact_drop_days = 30
npc_memory.cold_decay_embedding_drop_days = 90
npc_memory.archive_days = 365
```

### 12H.13 Implementation ordering

- **V1 launch**: L1 (aggregate split — foundational, must start correctly), L2 (bounded memory caps), L5 (lazy loading — already aligned with R7-L6), L6 (embedding separation), L7 (metrics)
- **V1 + 60 days**: L3 (size enforcement active when real data emerges), L4 (cold decay schedule)
- **V2**: Tune thresholds based on observed patterns
- **V3+**: Archive/restore flow matures for long-tail returning players

### 12H.14 Tooling surface (folded into DF9)

Admin + dev tooling for NPC memory:
- Memory size dashboard (top-N aggregates by size, trends)
- Manual compaction trigger (for specific pair)
- Archive/restore controls (per pair, bulk by NPC or by age)
- Memory content inspector (facts, summary, embedding heatmap)
- Decay schedule overview
- Compaction event log

**Folded into DF9** (Event + Projection + Publisher Ops). DF9 scope grows to **"Event + Projection + Publisher + NPC Memory Ops"** — all per-reality data-correctness ops in one admin surface. Avoids DF proliferation.

