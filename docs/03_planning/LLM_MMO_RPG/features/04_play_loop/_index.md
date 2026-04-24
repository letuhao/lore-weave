# 04_play_loop — Index

> **Category:** PL — Play Loop (core runtime)
> **Catalog reference:** [`catalog/cat_04_PL_play_loop.md`](../../catalog/cat_04_PL_play_loop.md) (owns `PL-*` stable-ID namespace)
> **Purpose:** The moment-to-moment core gameplay — turn submission, response, session-tick, time-advancement, scene transitions. High-touch with hot-path SDK (being designed by another agent).

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `PL_001_<name>.md`.)

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

Play-loop features have highest coupling with hot-path SDK. When SDK design is still in flux, features in this category should describe **what they need from the SDK** (capabilities + data shapes) rather than specific function calls. Adapt to actual SDK API when it's published.
