# 05_npc_systems — Index

> **Category:** NPC — NPC Systems
> **Catalog reference:** [`catalog/cat_05_NPC_systems.md`](../../catalog/cat_05_NPC_systems.md) (owns `NPC-*` stable-ID namespace)
> **Purpose:** NPC design — persona templates, schedules, memory, dialogue, reactions, LLM persona generation. Feeds into DF1 (daily life) + DF8 (persona from PC history).

**Active:** none (folder closure pass 2026-04-26 — both features at CANDIDATE-LOCK)

**Folder closure status:** **CLOSED for V1 design 2026-04-26.** Both NPC features (Cast + Chorus) at CANDIDATE-LOCK with §14 acceptance criteria. Option C event-model terminology applied 2026-04-25 (EVT-T2 NPCTurn `_withdrawn`; NPCTurn now lives as sub-type of EVT-T1 Submitted per EVT-A11 sub-type ownership discipline). LOCK pending integration tests. No further design work in NPC folder until V2+ extensions or new sibling NPC catalog items open new design threads.

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| NPC_001 | **Cast** (CST) | NPC foundation: ActorId variant model + R8-aggregate import + persona assembly + owner-node binding + cross-node handoff (resolves PL_001 §3.6 defer) + opinion stub realization (resolves NPC_002 §3 stub) + EVT-T1 Submitted/NPCTurn producer JWT shape (post Option C reframe). §14 acceptance criteria added 2026-04-26 (10 scenarios AC-CST-1..10). | **CANDIDATE-LOCK** 2026-04-26 | [`NPC_001_cast.md`](NPC_001_cast.md) | 46f60d7 → closure pending |
| NPC_002 | **Chorus** (CHO) | Multi-NPC turn ordering. Batched orchestrator + 4-tier priority + V1 cap=3, cascade=1, sequential LLM calls. Resolves MV12-D8 (no new sub-shapes; metadata-rich Speak/Action). Catalog NPC-7. §14 acceptance criteria added 2026-04-26 (10 scenarios AC-CHO-1..10; SPIKE_01 turn 5 reproducibility verified). | **CANDIDATE-LOCK** 2026-04-26 | [`NPC_002_chorus.md`](NPC_002_chorus.md) | d11dea0 → closure pending |

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
