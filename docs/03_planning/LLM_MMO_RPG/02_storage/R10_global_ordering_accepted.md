<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R10_global_ordering_accepted.md
byte_range: 130041-131372
sha256: f1ea3298c69aaa72ae2067c332e698d2bf08e2ca06cb0a2cdb6be23f3c9699d4
generated_by: scripts/chunk_doc.py
-->

## 12J. Global Event Ordering — Accepted Trade-off (R10)

Per-reality `event_id` is monotonic per-DB only; no global sequence across realities.

### 12J.1 Why this is accepted (not mitigated)

With R5 cross-instance live query REJECTED and analytics deferred indefinitely, **no product feature requires global event ordering**:

| Use case | Needs global order? |
|---|---|
| Realtime UX per session | No — intra-reality ordering sufficient |
| Canon propagation | No — causal ordering via `xreality.*` events |
| Replay one reality | No — reality-local order suffices |
| Admin "all events by user X" | Timestamp merge acceptable (rare) |
| Analytics aggregates | ETL merges by `created_at` — ordering fuzz OK |
| Legal discovery | Timestamp merge OK — not ordered-join |

Cost of mitigation (centralized sequencer, Lamport clocks, vector clocks) is high; product benefit is zero.

### 12J.2 Discipline required — timestamp hygiene

Must-haves (already required by other resolutions):
- All events have `created_at TIMESTAMPTZ NOT NULL` from Postgres server clock
- Postgres servers run NTP-synced (standard ops practice)
- Timestamps accurate to ~100ms across shards
- Sufficient for analytics-grade ordering when needed

No new code. No config keys. No tooling. Consciously accepted.

