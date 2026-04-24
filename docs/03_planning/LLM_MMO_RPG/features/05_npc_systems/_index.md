# 05_npc_systems — Index

> **Category:** NPC — NPC Systems
> **Catalog reference:** [`catalog/cat_05_NPC_systems.md`](../../catalog/cat_05_NPC_systems.md) (owns `NPC-*` stable-ID namespace)
> **Purpose:** NPC design — persona templates, schedules, memory, dialogue, reactions, LLM persona generation. Feeds into DF1 (daily life) + DF8 (persona from PC history).

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `NPC_001_<name>.md`.)

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
