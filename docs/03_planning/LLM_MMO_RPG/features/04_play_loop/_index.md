# 04_play_loop — Index

> **Category:** PL — Play Loop (core runtime)
> **Catalog reference:** [`catalog/cat_04_PL_play_loop.md`](../../catalog/cat_04_PL_play_loop.md) (owns `PL-*` stable-ID namespace)
> **Purpose:** The moment-to-moment core gameplay — turn submission, response, session-tick, time-advancement, scene transitions. High-touch with hot-path SDK (being designed by another agent).

**Active:** PL_001 — **Continuum** (DRAFT 2026-04-25 — first concrete implementation-ready feature design after DP Phase 4 LOCK)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| PL_001 | **Continuum** (CON) | Contract layer §1-§10: aggregates + tier table + DP primitives + capabilities + subscribe + patterns + failure UX + cross-service handoff. Boundary-review tightened 2026-04-25 (TurnEvent envelope rule + thin RejectReason + actor-removal hook). | CANDIDATE-LOCK 2026-04-25 (boundary-tightened) | [`PL_001_continuum.md`](PL_001_continuum.md) | b4ea611 → 1364487 → a4f2d26 → tightening pending |
| PL_001b | Continuum lifecycle (CON-L) | Lifecycle layer §11-§20: 5 sequences (normal/sleep/travel/reconnect/rejection) + bootstrap + 16 acceptance criteria. §18 deferrals updated 2026-04-25 with G1/G3/G4/G5 + B2/B3 boundary-review items. | CANDIDATE-LOCK 2026-04-25 (boundary-tightened) | [`PL_001b_continuum_lifecycle.md`](PL_001b_continuum_lifecycle.md) | a4f2d26 → tightening pending |
| PL_002 | **Grammar** (GR) | Command grammar (5 V1 commands: /verbatim /prose /sleep /travel /help) + intent classifier dispatch + tool-call allowlist + per-rule_id Vietnamese reject copy. Resolves MV12-D9. Option C event-model terminology applied (§2.5 by event-model agent). §13 acceptance criteria added 2026-04-25 (10 scenarios). | **CANDIDATE-LOCK** 2026-04-25 | [`PL_002_command_grammar.md`](PL_002_command_grammar.md) | f89aa48 → closure pending |
| ~~PL_003~~ → **NPC_002** | (relocated) | Multi-NPC turn ordering — was originally drafted here as PL_003 Chorus, then relocated to `05_npc_systems/` because catalog NPC-7 ("Multi-NPC conversation turn arbitration") is the correct domain. See [`../05_npc_systems/NPC_002_chorus.md`](../05_npc_systems/NPC_002_chorus.md). | RELOCATED 2026-04-25 | (moved) | d11dea0 (original) → relocate pending |

---

## Kernel touchpoints (shared across PL features)

- `02_storage/SR11_turn_ux_reliability.md` §12AN — TurnState 8-state machine + `turn_outcomes` audit
- `02_storage/S09_prompt_assembly.md` — AssemblePrompt() for every turn; intent classification at turn-input
- `02_storage/R07_concurrency_cross_session.md` — session-as-concurrency-boundary; one command processor per session
- `03_multiverse/` (MV12) — fiction-time model; every turn has fiction_duration; page-turn time advancement
- `05_llm_safety/` — A3 World Oracle for determinism · A5 intent classifier · A6 injection defense
- **Hot-path SDK** (being designed externally) — PL features MUST go through SDK, no direct kernel calls

---

## Naming convention

`PL_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".

---

## Coordination note

~~Play-loop features have highest coupling with hot-path SDK. When SDK design is still in flux...~~ **2026-04-25 update:** the hot-path SDK design landed as the LOCKED DP contract in [`../../06_data_plane/`](../../06_data_plane/) (Phase 1-4 complete: DP-A1..A19 + DP-T0..T3 + DP-R1..R8 + DP-K1..K12 + DP-Ch1..Ch53). PL features now reference DP primitives by name and use [`22_feature_design_quickstart.md`](../../06_data_plane/22_feature_design_quickstart.md) as the authoring template. PL_001 is the first feature to do this and serves as the example for subsequent PL_NNN docs.
