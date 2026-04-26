# 13_quests — Index

> **Category:** QST — Quests / Goals / Objectives (V2 deferred — pre-staged 2026-04-26 to reserve namespace + capture V1 hooks)
> **Catalog reference:** `catalog/cat_13_QST_quests.md` (NOT YET CREATED — defer to V2 actual design start)
> **Purpose:** Player-facing goals + objectives + rewards + persistence. Gives RPG direction beyond freeplay sandbox.

**Active:** none — folder is V2 reservation placeholder.

**Status:** **V2 RESERVED 2026-04-26.** No design files. No catalog file. No boundary registration. See [`00_V2_RESERVATION.md`](00_V2_RESERVATION.md) for V2 scope sketch + V1 sandbox alternatives.

---

## Why this folder exists pre-design

User confirmed 2026-04-26 that quest system is V2 deferred (full design too large for V1), BUT requested pre-staging the folder NOW to:
- Reserve `QST-*` namespace before collision risk
- Anchor 07_event_model existing hooks (`Scheduled:QuestTrigger` + `QuestOutcome` already reserved per Option C taxonomy)
- Capture V1 sandbox-mitigation alternatives (NPC desires LIGHT path) so V1 has direction without full quest system
- Track V2 scope sketch for when V2 design begins

Pattern matches PCS_001 brief discipline: "we know we need this; pre-stage it minimally; design when ready."

---

## Feature list (V2 deferred)

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (reservation) | **00_V2_RESERVATION.md** — V2 placeholder | RESERVED 2026-04-26 | [`00_V2_RESERVATION.md`](00_V2_RESERVATION.md) | (this commit) |
| QST_001 | (V2 — not designed) | Quest Foundation: Quest aggregate + objective state machine + rewards + branching + persistence | NOT YET DRAFTED — V2 deferred | (TBD V2) | n/a |

---

## Naming convention

`QST_<NNN>_<short_name>.md`. Sequence per-category. Reserve QST_001 for foundation; QST_002+ for extensions (radiant quests / multi-PC quests / quest chains).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature". When V2 design begins:
1. Create `catalog/cat_13_QST_quests.md`
2. Update `_boundaries/01_feature_ownership_matrix.md` Stable-ID prefix ownership row to add `QST-*`
3. Promote V2_RESERVATION → QST_001 DRAFT via `[boundaries-lock-claim+release]` commit

---

## Coordination note

Quest system touches MANY existing folders (NPC givers / PL_005 triggers / RES_001 rewards / NAR canonization V3 / SOC group quests V2+). When V2 design starts, expect cross-folder coordination — likely parallel agent commission (similar to PCS_001 brief pattern).
