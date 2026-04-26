<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_05_NPC_systems.md
byte_range: 50053-53160
sha256: 2877eb9298c3835fef1462fdee2ff6c56592900b1d4159da7731aa9438fca6b2
generated_by: scripts/chunk_doc.py
-->

## NPC — NPC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| NPC-1 | NPC proxy derivation from glossary entity (per reality) | 🟡 | V1 | IF-3, WA-1 | [02 §5.2](02_STORAGE_ARCHITECTURE.md), [03 §2](03_MULTIVERSE_MODEL.md) |
| NPC-2 | NPC persona assembly (core_beliefs + flexible_state + per-PC memory) | 🟡 | V1 | NPC-1 | [02 §5.2](02_STORAGE_ARCHITECTURE.md); full prompt design in PL-4 |
| NPC-3 | Per-PC memory storage + retrieval | 🟡 | V1 | NPC-1, IF-12 | [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial) — infrastructure resolved by R8 ([02 §12H](02_STORAGE_ARCHITECTURE.md)); semantic layer partial |
| NPC-3a | NPC aggregate split (core + per-pair memory aggregates) | ✅ | V1 | IF-1 | [02 §12H.2](02_STORAGE_ARCHITECTURE.md) (R8-L1 locked) |
| NPC-3b | Bounded memory per pair (LRU facts + rolling summary) | ✅ | V1 | NPC-3a | [02 §12H.3](02_STORAGE_ARCHITECTURE.md) (R8-L2 locked) |
| NPC-3c | Snapshot size enforcement + auto-compaction | ✅ | V1 | NPC-3a | [02 §12H.4](02_STORAGE_ARCHITECTURE.md) (R8-L3 locked) |
| NPC-3d | Cold memory decay (30d/90d/365d) + archive/restore | ✅ | V2 | NPC-3a, IF-10 | [02 §12H.5](02_STORAGE_ARCHITECTURE.md) (R8-L4 locked) |
| NPC-3e | Lazy memory loading (session-scoped) | ✅ | V1 | NPC-3a, IF-5a | [02 §12H.6](02_STORAGE_ARCHITECTURE.md) (R8-L5 locked) |
| NPC-3f | Embedding storage separation (pgvector dedicated table) | ✅ | V1 | IF-12 | [02 §12H.7](02_STORAGE_ARCHITECTURE.md) (R8-L6 locked) |
| NPC-3g | Semantic retrieval quality (which facts to surface) | 🟡 | V1 | NPC-3a, NPC-4 | Needs V1 prototype measurement ([01 A1 semantic layer](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial)) |
| NPC-3h | LLM summary rewrite prompt quality | 🟡 | V1 | NPC-3b | Needs V1 prototype measurement |
| NPC-4 | Retrieval from knowledge-service (timeline-scoped, canon-faithful) | ❓ | V1 | — | [01 A4](01_OPEN_PROBLEMS.md#a4-retrieval-quality-from-knowledge-service--partial) — needs measurement |
| NPC-5 | NPC mood / flexible_state drift (LLM output updates per-reality) | 🟡 | V1 | NPC-2 | [02 §5.2](02_STORAGE_ARCHITECTURE.md) |
| NPC-6 | Canon-drift linter — async post-response check against knowledge-service oracle, logs to `canon_drift_log` | ✅ | V1 | NPC-4, WA-3, IF-1 | [05_qa §4.1](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#41-layer-1--async-post-response-lint-g3-d1), G3-D1 |
| NPC-7 | Multi-NPC conversation turn arbitration | 🟡 | V2 | PL-1 | [01 B4](01_OPEN_PROBLEMS.md#b4-multi-user-turn-arbitration--partial), DF5 |
| NPC-8 | NPC daily routines when no player around | 📦 | V3 | NPC-1 | **DF1 — Daily Life** |
| NPC-9 | NPC memory decay / summarization (prevent unbounded growth) | 🟡 | V1 | NPC-3 | Part of A1 solution |
| NPC-10 | NPC tool calling (trigger world-state change via LLM) | 🟡 | V1 | PL-6 | [01 A5](01_OPEN_PROBLEMS.md#a5-tool-use-reliability-for-world-actions--partial) |
| NPC-11 | Classification (SillyTavern pattern — mood from last message) | 📦 | V3 | — | Feature comparison doc |
| NPC-12 | NPC Desires LIGHT — author-declared narrative goal scaffolding (sandbox-mitigation Path A; NO state machine, NO tracking, NO rewards; LLM AssemblePrompt context integration only; Forge `ToggleNpcDesire` AdminAction for satisfied flag) | ✅ | V1 | NPC-1, NPC-2, RES-23 (i18n) | [`features/05_npc_systems/NPC_003_desires.md`](../features/05_npc_systems/NPC_003_desires.md) — DRAFT 2026-04-26; resolves [`13_quests/00_V2_RESERVATION.md`](../features/13_quests/00_V2_RESERVATION.md) §5 Path A |

