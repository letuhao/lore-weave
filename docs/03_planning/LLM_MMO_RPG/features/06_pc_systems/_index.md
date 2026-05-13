# 06_pc_systems — Index

> **Category:** PCS — PC Systems
> **Catalog reference:** [`catalog/cat_06_PCS_pc_systems.md`](../../catalog/cat_06_PCS_pc_systems.md) (owns `PCS-*` stable-ID namespace)
> **Purpose:** PC-specific substrate post-ACT_001 unification — `pc_user_binding` (user_id + current_session + body_memory xuyên không) + `pc_mortality_state` (handoff from WA_006) + (V1+ pc_stats_v1_stub TBD) + `PcXuyenKhongCompleted` event integrating TDIL_001 clock-split. Builds on ACT_001 stable base for IDENTITY (actor_core absorbs persona + canonical_traits + flexible_state) + bilateral opinion (actor_actor_opinion) + session memory (actor_session_memory).

**Active:** PCS_001 — **PC Substrate** (CANDIDATE-LOCK 2026-04-27 — 4-commit cycle complete: Phase 0 3c76f33 + Q-LOCKED 1/4 5c34b93 + DRAFT 2/4 67b53cd + Phase 3 3/4 7e3218e + closure 4/4 this commit)

**Folder closure status:** **COMPLETE 2026-04-27** — PCS_001 at CANDIDATE-LOCK. Folder ready. Resolves WA_006 §6 closure pass pc_mortality_state aggregate handoff. Future V1+ priorities: PO_001 Player Onboarding (consumes PCS_001 primitives Forge:RegisterPc + Forge:BindPcUser per PCS-D1) + AI-controls-PC-offline activation (cross-ref ACT-D1) + PCS-D2 Respawn flow + V1+ A6 canon-drift detector body_memory integration (PCS-D7).

**Origin signal:**
- Brief commissioned 2026-04-25 (`00_AGENT_BRIEF.md`) for parallel agent design
- Multiple Tier 5 feature designs since (IDF + FF + FAC + REP + PROG + RES + ACT + AIT + TDIL) absorbed parts of brief
- Main session 2026-04-27 picks up PCS_001 directly post-ACT_001 cycle (Q2 LOCKED sequencing — ACT_001 first, PCS_001 on stable base)
- Brief §S2 (PC persona) + §S6 (PC-NPC relationship read) ABSORBED by ACT_001
- Brief §S5 (pc_stats_v1_stub) PROBABLY SUPERSEDED by PROG_001 (Q-decision pending)
- Brief §S3 (xuyên không body-memory) + §S8 (xuyên không body-substitution) STILL CORE PCS_001 territory
- TDIL_001 clock-split (soul_clock + body_clock) integrates with §S3 + §S8

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|
| (commission) | **00_AGENT_BRIEF.md** — PCS_001 PC substrate design commission | LOCKED brief 2026-04-25 (HISTORICAL; superseded by main session ACT_001-aware design 2026-04-27) | [`00_AGENT_BRIEF.md`](00_AGENT_BRIEF.md) | seeding pending |
| (concept) | **00_CONCEPT_NOTES.md** — PCS_001 brainstorm + Q1-Q10 + ACT_001/TDIL_001 reconciliation | CONCEPT 2026-04-27 — captures user framing + post-ACT_001 reconciliation (8 brief sections audited; 2 absorbed by ACT_001, 1 superseded by PROG_001, 5 still PCS_001 V1 scope) + Q1-Q10 critical scope questions | [`00_CONCEPT_NOTES.md`](00_CONCEPT_NOTES.md) | (this commit) |
| (research) | **01_REFERENCE_GAMES_SURVEY.md** — PC substrate + xuyên không reference games | DRAFT 2026-04-27 — Wuxia transmigration novels (primary; xuyên không canon basis) + Persona series multi-persona + Mass Effect Shepard customization + D&D party multi-PC + WoW respawn pattern + Permadeath genre + CRPG character creation | [`01_REFERENCE_GAMES_SURVEY.md`](01_REFERENCE_GAMES_SURVEY.md) | (this commit) |
| PCS_001 | **PC Substrate** (PCS) | Per-PC user binding + xuyên không body-memory (SoulLayer + BodyLayer + LeakagePolicy 4-variant) + pc_mortality_state 4-state (handoff from WA_006 §6 closure RESOLVED) + PcTransmigrationCompleted EVT-T1 (renamed from PcXuyenKhongCompleted per user direction; TDIL_001 §10 clock-split contract integration). **2 V1 aggregates** (pc_user_binding + pc_mortality_state per Q4 LOCKED — pc_stats_v1_stub deferred V1+ PCS-D4 since PROG_001 + RES_001 + PL_006 cover stats). Synthetic actors forbidden V1 (PCS-A7). Cross-reality strict V1 (PCS-A8 V2+ Heresy). Multi-PC cap=1 V1 (PCS-A9; V1+ relax via RealityManifest.max_pc_count Optional PCS-D3). Q1-Q10 LOCKED via 6-batch deep-dive (1 REFINEMENT Q5 + 1 RENAME). 1 EVT-T4 (PcRegistered) + 5 EVT-T8 Forge sub-shapes + 3 V1 EVT-T3 mortality delta_kinds + 3 V1+ reserved + 1 EVT-T1 PcTransmigrationCompleted (schema V1; emission V1+ deferred PCS-D-N). 7 V1 reject rules + 3 V1+ reservations (`pc.*` namespace). 2 RealityManifest CanonicalActorDecl additive fields (body_memory_init + user_id_init; REQUIRED V1 for kind=Pc). 10 V1 AC + 4 V1+ deferred. 10 deferrals (PCS-D1..PCS-D10). Resolves PCS_001 brief §S1 + §S3 + §S4 + §S7 + §S8. ABSORBED by ACT_001: §S2 + §S6. SUPERSEDED by PROG_001 + RES_001 + PL_006: §S5. RESOLVES WA_006 §6 closure pass pc_mortality_state handoff. | **CANDIDATE-LOCK** 2026-04-27 (4-commit cycle complete) | [`PCS_001_pc_substrate.md`](PCS_001_pc_substrate.md) | 3c76f33 → 5c34b93 → 67b53cd → 7e3218e → (this commit 4/4) |

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
