<!-- CHUNK-META
source: OPEN_DECISIONS.ARCHIVED.md
chunk: pending_questions.md
byte_range: 1211-4152
sha256: ad31551010228504c97fdb0f5a9a8cb9082a68bb57e22913b84ad20d7bbe34c4
generated_by: scripts/chunk_doc.py
-->

## Questions without defaults (need explicit user input)

These are items where I did not propose a default because either (a) the question is genuinely ambiguous and needs product intent, or (b) the answer has dependencies on decisions above.

### Q-RISK — Risk discussion items
User indicated they have ideas for risks R1–R13 in [02_STORAGE_ARCHITECTURE.md §13](02_STORAGE_ARCHITECTURE.md) and M1–M7 in [01_OPEN_PROBLEMS.md §M](01_OPEN_PROBLEMS.md). These were parked for separate discussion.

| # | Risk | Source | Note |
|---|---|---|---|
| R1 | Event volume explosion | 02 §13 | User flagged this as largest risk; multiverse model is the proposed mitigation, awaiting user feedback |
| R2 | Projection rebuild time at scale | 02 §13 | |
| R3 | Event schema evolution pain | 02 §13 | |
| R4 | DB-per-instance operational cost | 02 §13 | |
| R5 | Cross-instance queries | 02 §13 | |
| R6 | Outbox publisher failure | 02 §13 | |
| R7 | Multi-aggregate transaction deadlocks | 02 §13 | |
| R8 | Snapshot size drift | 02 §13 | |
| R9 | Instance close = destructive | 02 §13 | |
| R10 | No built-in global ordering across instances | 02 §13 | |
| R11 | pgvector per-instance footprint | 02 §13 | Depends on S2 |
| R12 | Redis stream ephemerality | 02 §13 | Depends on S3 |
| R13 | Admin tooling complexity | 02 §13 | |
| ~~M1~~ | ~~Reality discovery problem~~ | 01 §M | **LOCKED 2026-04-23** — M1-D1..D7 below; [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery) |
| ~~M3~~ | ~~Canonization contamination~~ | 01 §M | **LOCKED 2026-04-23** — M3-D1..D8 below; [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution). DF3 implementation + E3 legal still independent. |
| ~~M4~~ | ~~Inconsistent L1/L2 updates across reality lifetimes~~ | 01 §M | **LOCKED 2026-04-23** — M4-D1..D6 below; [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution). Reuses R5-L2 xreality infrastructure. |
| ~~M7~~ | ~~Concept complexity for users~~ | 01 §M | **LOCKED 2026-04-23** — M7-D1..D5 below; [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution) |

### Q-A1 — NPC memory at scale
Critical-path `OPEN` problem. Multiverse bounds the scope (per-reality) but storage strategy still unsolved. Needs:
- Concrete memory schema decision (structured facts vs summary vs hybrid)
- Retrieval strategy (keyword vs semantic vs hybrid)
- Rewrite/compaction cadence
- Research review (MemGPT, Generative Agents, mem0, Zep)

### Q-A4 — Retrieval quality evaluation
Cannot be answered in design; needs measured evaluation on real LoreWeave books. Blocks implementation commitment.

### Q-D1 — LLM cost measurement
Requires V1 prototype to measure actual cost/user-hour. Blocks business-model commitment.

### Q-E3 — IP ownership legal review
Requires external legal input. Not something a design doc can resolve.

---

