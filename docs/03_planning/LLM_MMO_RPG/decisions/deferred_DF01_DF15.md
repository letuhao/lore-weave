<!-- CHUNK-META
source: OPEN_DECISIONS.ARCHIVED.md
chunk: deferred_DF01_DF15.md
byte_range: 169510-175067
sha256: d9def81f05f2c689e7a6d7f3c61955bba8280f560b878a617dae09cbe6a62eca
generated_by: scripts/chunk_doc.py
-->

## Deferred big features (DF1–DF15, DF12 withdrawn)

Features identified during design discussions that are not yet designed but are **known to be needed**. Each requires its own design doc when touched. Listed here so they don't get lost.

| ID | Feature | Surfaced in | Covers decisions |
|---|---|---|---|
| **DF1** | Daily Life / "Sinh hoạt" — offline PC/NPC behavior, daily routines, NPC-conversion mechanics, reclaim UX | [04_PC §4](04_PLAYER_CHARACTER_DESIGN.md) | PC-B2, PC-B3, partial C-PC2, links to [01 B3](01_OPEN_PROBLEMS.md#b3-world-simulation-tick--open) |
| **DF2** | Monetization / PC slot purchase | [04_PC §5.1](04_PLAYER_CHARACTER_DESIGN.md) | PC-C1 extension |
| **DF3** | Canonization / Author Review Flow — L3→L2 promotion, diff UI, IP attribution | [03 §3, 04 §7](04_PLAYER_CHARACTER_DESIGN.md) | MV2 details, PC-E1, PC-E2, links to [01 E3](01_OPEN_PROBLEMS.md#e3-ip-ownership--open) and [§M3](01_OPEN_PROBLEMS.md#m-multiverse-model-specific-risks) |
| **DF4** | World Rule feature — per-reality rule engine (death, paradox tolerance, PvP, canon strictness) | [04 §7](04_PLAYER_CHARACTER_DESIGN.md) | PC-B1 details, PC-D2 consent, PC-E3, A-PC3 runtime enforcement |
| **DF5** | Session / Group Chat feature — multi-character scene, turn arbitration, PvP, message routing | [04 §6](04_PLAYER_CHARACTER_DESIGN.md) | PC-D1, PC-D2, PC-D3; sibling to [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md) |
| **DF6** | World Travel — cross-reality PC travel, state transfer policy, entity identity | [OPEN_DECISIONS §MV5 primitives](OPEN_DECISIONS.md) | MV5, partial A-PC3 |
| **DF7** | PC Stats & Capabilities (small) | [04 §5.3](04_PLAYER_CHARACTER_DESIGN.md) | PC-C3 concrete schema |
| **DF8** | NPC persona generation from PC history | [04 §4, §5.2](04_PLAYER_CHARACTER_DESIGN.md) | PC-B3 NPC-conversion, PC-C2 persona semantics; may merge into DF1 |
| **DF9** | Event + Projection + Publisher + NPC Memory Ops — admin UX for: rebuild dashboard, manual triggers, drift reports, schema migration planner, rolling orchestrator, publisher health per shard/partition, dead-letter queue review (replay/skip/manual-publish), partition assignment editor, NPC memory size dashboard, manual compaction trigger, archive/restore controls, memory content inspector | [02 §12B.7, §12F.12, §12H.14](02_STORAGE_ARCHITECTURE.md) | Admin UX over §12B (rebuild/integrity) + §12F (publisher reliability) + §12H (NPC memory ops) mechanisms; algorithms locked in those sections |
| **DF10** | Event Schema Tooling — registry viewer, upcaster test harness, codegen CLI (`eventgen`), deprecation dashboard, cross-service schema sync verifier, docs auto-generation | [02 §12C.11](02_STORAGE_ARCHITECTURE.md) | Dev UX + CI integration around R3 mechanisms; mechanisms locked in §12C |
| **DF11** | Database Fleet + Reality Lifecycle + Migration Management — shard health dashboard, per-reality DB inspector, migration status board, backup verification dashboard, orphan resolution workflow, capacity planner, shard rebalance planner, **closure queue + state timeline + verification viewer + double-approval workflow + emergency cancel controls**, **migration queue + per-migration timeline + abort controls + post-migration verification dashboard + subtree split planner** | [02 §12D.11, §12I.14, §12N.11](02_STORAGE_ARCHITECTURE.md) | Ops UI wrapping R4 + R9 + C2 mechanisms; platform-wide fleet + per-reality lifecycle + migration (distinct from DF9 per-reality correctness) |
| ~~DF12~~ | ~~Cross-Reality Analytics & Search~~ | — | **WITHDRAWN** (see R5-DF12 in decisions log); no justifying product feature. Slot left as tombstone for audit trail. |
| **DF13** | Cross-Session Event Handler — event handler health dashboard, cursor lag per reality, session event queue inspector, scope distribution analytics, manual propagation trigger, queue replay | [02 §12G.13](02_STORAGE_ARCHITECTURE.md) | Admin + dev UX for §12G mechanisms; different from DF9 (publisher) — DF9 broadcasts to clients, DF13 routes between sessions |
| **DF14** | Vanish Reality Mystery System — pre-severance breadcrumb generation (ruins, prophecies, lore fragments, mysterious artifacts) seeded in descendants before ancestor closes; players discover + reconstruct lost past as in-game lore. Gameplay layer on top of §12M severance substrate. Short track, detailed design later. | [02 §12M.11](02_STORAGE_ARCHITECTURE.md) · [03 §9.9.6](03_MULTIVERSE_MODEL.md) | Surfaced 2026-04-24 in SA+DE review during C1 orphan worlds discussion. §12M severance ships independently; DF14 builds on it post-V1. |
| **DF15** | External Integration Authentication — MCP server auth, external webhooks (e.g., payment providers, SSO IdPs), third-party developer API keys, partner integrations. Distinct from S11 internal service auth (which is SPIFFE-based). Requires its own model: API-key lifecycle, OAuth flows, webhook signature verification, rate-limit-per-partner, revocation. | [02 §12AA.12 residuals](02_STORAGE_ARCHITECTURE.md) | Surfaced 2026-04-24 in S11 Security review. S11 scope is internal service-to-service only; external integrations need separate design due to different trust model (partner keys vs workload attestation). Not V1-blocking; scope when external integrations are required beyond core LLM providers. |

These features are NOT gates for current design docs (02, 03, 04). They are gated by their own future design. Each should get its own numbered doc when work begins.

---

