# 05_npc_systems — Index

> **Category:** NPC — NPC Systems
> **Catalog reference:** [`catalog/cat_05_NPC_systems.md`](../../catalog/cat_05_NPC_systems.md) (owns `NPC-*` stable-ID namespace)
> **Purpose:** NPC design — persona templates, schedules, memory, dialogue, reactions, LLM persona generation. Feeds into DF1 (daily life) + DF8 (persona from PC history).

**Active:** NPC_001 Cast (DRAFT 2026-04-25)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| NPC_001 | **Cast** (CST) | NPC foundation: ActorId variant model + R8-aggregate import + persona assembly + owner-node binding + cross-node handoff (resolves PL_001 §3.6 defer) + opinion stub realization (resolves NPC_002 §3 stub) + EVT-T2 NPCTurn producer JWT shape | DRAFT 2026-04-25 | [`NPC_001_cast.md`](NPC_001_cast.md) | 46f60d7 |
| NPC_002 | **Chorus** (CHO) | Multi-NPC turn ordering. Batched orchestrator + 4-tier priority + V1 cap=3, cascade=1, sequential LLM calls. Resolves MV12-D8 (no new sub-shapes; metadata-rich Speak/Action). Catalog NPC-7. | DRAFT 2026-04-25 (relocated from 04_play_loop/) | [`NPC_002_chorus.md`](NPC_002_chorus.md) | d11dea0 (original drafted as PL_003) → relocate pending |

---

## Kernel touchpoints (shared across NPC features)

- `02_storage/R08_npc_memory_split.md` §12H — NPC aggregate split (`npc` core + `npc_session_memory` + `npc_pc_relationship`)
- `02_storage/S01_03_session_scoped_memory.md` §12S — session-scoped capability-based memory; cross-PC leak structurally impossible
- `02_storage/S09_prompt_assembly.md` §12Y — AssemblePrompt() `[ACTOR_CONTEXT]` section for NPCs
- `decisions/deferred_DF01_DF15.md` — DF1 (daily life / routines) + DF8 (persona from PC history) forward links

---

## Naming convention

`NPC_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
