<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R11_pgvector_footprint.md
byte_range: 131372-134184
sha256: 446ac10cc6049c0c1834d0958574ec8150662f7715520f8f993651acb95c6ea9
generated_by: scripts/chunk_doc.py
-->

## 12K. pgvector Footprint Management (R11 mitigation)

pgvector per-reality (locked S2) produces many small vector indexes. Quantify at V3 scale; design for monitoring not mitigation.

### 12K.1 Capacity quantified

Per active reality (after R8-L6 embedding-in-separate-table):
- ~20 active NPCs × ~20 active pairs = 400 vectors/reality
- Vector size: 1536 float32 × 4 = 6KB raw
- Total raw: 2.4MB per reality
- HNSW index overhead ~30%: ~3MB
- **Per-reality total: ~6MB (data + index)**

V3 platform (1000 active on 4 servers @ 250 each):
- Per Postgres server: 250 × 6MB = **1.5GB pgvector in RAM**
- Large server (256GB RAM): 1.5GB = **<1% utilization**
- Concern: low

Frozen realities (10K): ~3MB each (after R8-L4 embedding drop for >90d), but cold — not loaded in buffer pool unless queried. No steady RAM cost.

**Conclusion:** pgvector footprint is a monitoring problem, not a design problem.

### 12K.2 Layer 1 — Embedding in separate table (done, R8-L6)

Already locked. Embeddings not in aggregate snapshots → query-time loading only.

### 12K.3 Layer 2 — HNSW index tuning

```sql
CREATE INDEX npc_pc_memory_embedding_hnsw
  ON npc_pc_memory_embedding USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

Parameters:
- `m = 16`: connections per layer, balanced recall vs memory
- `ef_construction = 64`: fast build, acceptable quality
- Query-time `ef_search` tunable per query (default 40)

For 400-vector indexes these defaults are overkill-safe.

### 12K.4 Layer 3 — Cold reality eviction (automatic)

Postgres handles this naturally. Frozen realities not queried → buffer pool doesn't keep pages hot. Cold-start penalty on first query ~50ms, acceptable.

No manual eviction code needed.

### 12K.5 Layer 4 — Memory monitoring

```
lw_pgvector_index_memory_bytes{shard_host, reality_id}   gauge
lw_pgvector_index_build_duration_seconds                  histogram
lw_pgvector_query_duration_seconds{reality_id}            histogram
lw_pgvector_recall_at_k                                   gauge (sampling-based)
```

**Alerts:**
- Per-shard pgvector memory > 10% of RAM → investigate
- Query p99 > 50ms → check index health
- Recall drift → reindex candidate

### 12K.6 Escape hatch — external vector store

Documented for future escalation if pgvector insufficient:
- Qdrant / Weaviate / Pinecone as out-of-band store
- Per-reality namespace
- Sync via event-handler consumer for `npc_pc_memory.summary_rewritten`

**Not V1.** Inline note documenting the path; promoted to ADR only if activated.

### 12K.7 Config keys (R11)

```
pgvector.hnsw.m = 16
pgvector.hnsw.ef_construction = 64
pgvector.hnsw.ef_search = 40
pgvector.memory_alert_pct_of_ram = 10
```

