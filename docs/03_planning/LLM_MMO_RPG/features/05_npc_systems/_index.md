# 05_npc_systems — Index

> **Category:** NPC — NPC Systems
> **Catalog reference:** [`catalog/cat_05_NPC_systems.md`](../../catalog/cat_05_NPC_systems.md) (owns `NPC-*` stable-ID namespace)
> **Purpose:** NPC design — persona templates, schedules, memory, dialogue, reactions, LLM persona generation. Feeds into DF1 (daily life) + DF8 (persona from PC history).

**Active:** NPC_003 — **NPC Desires** (DRAFT 2026-04-26 — Path A sandbox-mitigation V1; LIGHT extension to NPC_001 npc aggregate)

**Folder closure status:** Re-opened 2026-04-26 for NPC_003 desires LIGHT (sandbox concern Path A from `13_quests/00_V2_RESERVATION.md` §5). Both NPC_001 (Cast) + NPC_002 (Chorus) remain at CANDIDATE-LOCK; NPC_003 ADDS to folder without modifying existing locks (additive I14 evolution — npc.desires field on NPC_001-owned aggregate). Option C event-model terminology applied 2026-04-25 (EVT-T2 NPCTurn `_withdrawn`; NPCTurn now lives as sub-type of EVT-T1 Submitted per EVT-A11 sub-type ownership discipline).

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| NPC_001 | **Cast** (CST) | NPC foundation: ActorId variant model + R8-aggregate import + persona assembly + owner-node binding + cross-node handoff (resolves PL_001 §3.6 defer) + opinion stub realization (resolves NPC_002 §3 stub) + EVT-T1 Submitted/NPCTurn producer JWT shape (post Option C reframe). §14 acceptance criteria added 2026-04-26 (10 scenarios AC-CST-1..10). | **CANDIDATE-LOCK** 2026-04-26 | [`NPC_001_cast.md`](NPC_001_cast.md) | 46f60d7 → closure pending |
| NPC_002 | **Chorus** (CHO) | Multi-NPC turn ordering. Batched orchestrator + 4-tier priority + V1 cap=3, cascade=1, sequential LLM calls. Resolves MV12-D8 (no new sub-shapes; metadata-rich Speak/Action). Catalog NPC-7. §14 acceptance criteria added 2026-04-26 (10 scenarios AC-CHO-1..10; SPIKE_01 turn 5 reproducibility verified). | **CANDIDATE-LOCK** 2026-04-26 | [`NPC_002_chorus.md`](NPC_002_chorus.md) | d11dea0 → closure pending |
| NPC_003 | **Desires** (DSR) | LIGHT author-declared NPC goal scaffolding. Path A from `13_quests/00_V2_RESERVATION.md` §5 — solves sandbox concern WITHOUT full quest system. Adds `desires: Vec<NpcDesireDecl>` field on NPC_001 npc aggregate (additive per I14). Each desire = `{ desire_id, kind: I18nBundle, intensity: u8, satisfied: bool, references: Vec<EntityRef> }`. RealityManifest declares per-NPC initial desires + `desires_prompt_top_n` (default 3). LLM AssemblePrompt persona context renders top-N intensity-sorted desires per active locale (i18n per RES_001 §2). Author toggles `satisfied` via WA_003 Forge `ToggleNpcDesire` AdminAction (no automatic detection V1). NO state machine, NO objective tracking, NO rewards — pure LLM-context scaffolding. ~5 desires/NPC cap V1. 5 V1-testable acceptance scenarios AC-DSR-1..5 + 8 deferrals (DSR-D1..D8) + 3 open questions (DSR-Q1..Q3). | **DRAFT 2026-04-26** | [`NPC_003_desires.md`](NPC_003_desires.md) | (this commit) |

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
