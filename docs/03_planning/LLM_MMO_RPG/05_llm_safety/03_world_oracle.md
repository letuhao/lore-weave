<!-- CHUNK-META
source: 05_LLM_SAFETY_LAYER.ARCHIVED.md
chunk: 03_world_oracle.md
byte_range: 5216-7864
sha256: 70be4a8597a680f4625831f4edb5bf42675575dda23c2d77deb8d05d8fea9975
generated_by: scripts/chunk_doc.py
-->

## 4. World Oracle (A3)

### 4.1 API (A3-D1)

```python
oracle.query(
    reality_id: UUID,
    pc_id: UUID,
    key: OracleKey,
    context_cutoff: int | None = None,
) -> OracleResult

# OracleResult:
#   answer: str | dict              # deterministic answer
#   confidence: float               # 1.0 if pre-computed, < 1.0 if partial match
#   source_events: list[event_id]   # traceable provenance
#   cache_age_seconds: int
```

Same `(reality_id, pc_id, key, context_cutoff)` → same answer, always. Deterministic by construction.

### 4.2 Pre-computed fact categories (A3-D2)

The Oracle pre-computes answers for these key categories at reality creation + invalidates on L3 events touching the key:

| Category | Key example | Source |
|---|---|---|
| `entity_location` | `("Alice", "current_location")` | `entity_location` projection |
| `entity_relation` | `("Alice", "enemy_of", "Bob")` | `entity_relation` projection |
| `L1_axiom` | `("magic", "exists")` | Book L1 canon (never drifts) |
| `book_content` | `("chapter", 3, "summary")` | Book SSOT (immutable per reality unless canonized) |
| `world_state_kv` | `("kingdom_castle", "guards")` | `world_kv_projection` |

Cache invalidation:
- L3 event emitted in reality R touches key K → invalidate `cache[R, *, K, *]`
- Next query recomputes from projections
- For hot keys, pre-warm on invalidation

### 4.3 Fact-question routing (A3-D3)

```
Fact question intent from classifier
        │
        ▼
  Oracle key extraction (NER + fact-pattern match)
        │
        ├─ Match → oracle.query() → fixed answer
        │         │
        │         ▼
        │   LLM prompt: "Elena knows {answer}. Wrap in her voice."
        │
        └─ Miss  → audit-log `oracle.classifier_miss` + fall back to LLM with canon retrieval
                   │
                   ▼
            Canon-drift detector (G3) monitors for answer divergence across sessions
```

Miss rate feeds V1 tuning of classifier + Oracle key coverage.

### 4.4 Timeline-cutoff + per-PC visibility (A3-D4)

`context_cutoff` is the event_id the PC has witnessed up to. Oracle filters facts by this cutoff:

- Spoilers prevented: PC asks "Will Alice betray the guild?" — Oracle sees no event past PC's cutoff → returns "unknown" (or a vague canon hint from L2)
- Cross-PC leaks prevented: Facts established in another PC's private memory are not in the Oracle's retrieval scope for this PC

**This is structural, not prompt-level.** Even a perfect jailbreak cannot extract what the Oracle didn't return.

---

