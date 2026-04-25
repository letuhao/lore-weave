# 06_pc_systems — Index

> **Category:** PCS — PC Systems
> **Catalog reference:** [`catalog/cat_06_PCS_pc_systems.md`](../../catalog/cat_06_PCS_pc_systems.md) (owns `PCS-*` stable-ID namespace)
> **Purpose:** PC sheet design — identity layers, inventory, relationships, simple state fields (no RPG mechanics per F4 ACCEPTED). Feeds into DF7 PC Stats & Capabilities.

**Active:** **awaiting parallel agent** (PCS_001 design commissioned via [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) — folder seeded 2026-04-25, brief LOCKED, design pass not yet started)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|
| (commission) | **00_AGENT_BRIEF.md** — PCS_001 PC substrate design commission | LOCKED brief 2026-04-25 (ready for parallel agent) | [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) | seeding pending |
| PCS_001 | (awaiting parallel agent) — PC substrate (PcId + persona + xuyên không body-memory + pc_mortality_state handoff from WA_006 + V1 stats stub + PC-NPC relationship read-side) | NOT YET STARTED | (to be created by agent) | n/a |

---

## Why this folder is empty + brief-driven

PCS_001 PC substrate is critical V1 work but introduces a NEW DOMAIN (xuyên không soul/body model — no precedent in existing features). The user explicitly identified that designing PCS_001 inline in the same session as world-layer work would risk:

1. **Session-scope boundary** — too many features in one session degrades quality
2. **Domain freshness** — xuyên không model deserves dedicated thinking, not "while we're at it" treatment
3. **Boundary discipline** — having PCS designed by a fresh agent with the boundary folder + extension contracts already in place reduces over-extension risk

So: PCS_001 follows the **parallel agent pattern** established by 07_event_model. The brief at [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) is the entry point. A future session or parallel agent picks it up, reads the brief + required reading list (§4), executes Phase 0 first-session deliverable (§10) for user approval, then drafts PCS_001 across 1-2 passes.

**WHAT'S NOT in PCS folder (boundary clarity):**

- ❌ PC creation flow → `03_player_onboarding/PO_001` (separate folder)
- ❌ Combat / DF7 stats system → V2+ feature
- ❌ A6 canon-drift detection algorithm → `05_llm_safety/`
- ❌ Hot-path turn-submission check → `04_play_loop/PL_001/PL_002`
- ❌ Author-side per-PC overrides UI → `02_world_authoring/WA_003 Forge` (already designed)
- ❌ NpcId / NpcOpinion projection → `05_npc_systems/NPC_001 Cast` (already designed; PCS consumes read-side)

---

## Kernel touchpoints (shared across PCS features)

- `04_player_character/` (entire subfolder) — PC-A1..E3 decisions already locked
- `decisions/locked_decisions.md` — PC-A1..E3 + PC-C3 "simple state-based" + F4 "minimal RPG mechanics"
- `02_storage/R08_npc_memory_split.md` — `npc_pc_relationship` edge carries PC-side state too
- `02_storage/SR11_turn_ux_reliability.md` — TurnState + PresenceState apply per-PC
- `03_multiverse/` MV12 — fiction_ts snapshots of PC sheet at time-points (PC state changes over fiction-time)

---

## Naming convention

`PCS_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
