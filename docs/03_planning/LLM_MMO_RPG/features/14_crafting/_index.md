# 14_crafting — Index

> **Category:** CFT — Crafting / Recipes / Production Chains (V2 deferred — pre-staged 2026-04-26 to reserve namespace + capture V1 hooks)
> **Catalog reference:** `catalog/cat_14_CFT_crafting.md` (NOT YET CREATED — defer to V2 actual design start)
> **Purpose:** Recipe-driven transformation of materials → items/products via skill + tool + time. Foundation for V2 Economy module production chains.

**Active:** none — folder is V2 reservation placeholder.

**Status:** **V2 RESERVED 2026-04-26.** No design files. No catalog file. No boundary registration. See [`00_V2_RESERVATION.md`](00_V2_RESERVATION.md) for V2 scope sketch.

---

## Why this folder exists pre-design

User confirmed 2026-04-26 that crafting is V2 deferred (depends on RES_001 Item kind V1+30d + skill checks DF7), BUT requested pre-staging the folder NOW to:
- Reserve `CFT-*` namespace
- Anchor RES_001 RES-D11 Recipe aggregate hook (already declared in V1 Economy module reservation)
- Track production-chain pattern (Anno 1800 reference) for V2 Economy module
- Establish boundary line between RES_001 (resources/inventory/trade) and CFT (transformation rules)

Pattern matches `13_quests/` discipline: minimal V2 reservation, not full design.

---

## Feature list (V2 deferred)

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (reservation) | **00_V2_RESERVATION.md** — V2 placeholder | RESERVED 2026-04-26 | [`00_V2_RESERVATION.md`](00_V2_RESERVATION.md) | (this commit) |
| CFT_001 | (V2 — not designed) | Recipe Foundation: Recipe aggregate + ingredient/output decl + skill/tool prereqs + crafting station + quality variation | NOT YET DRAFTED — V2 deferred | (TBD V2) | n/a |

---

## Naming convention

`CFT_<NNN>_<short_name>.md`. Sequence per-category. Reserve CFT_001 for foundation; CFT_002+ for extensions (multi-step chains / smelting / cooking / alchemy).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature". When V2 design begins:
1. Create `catalog/cat_14_CFT_crafting.md`
2. Update `_boundaries/01_feature_ownership_matrix.md` Stable-ID prefix ownership row to add `CFT-*`
3. Coordinate with RES_001 §15.2 RES-D11 Recipe aggregate (will likely consume CFT recipe declarations)
4. Promote V2_RESERVATION → CFT_001 DRAFT via `[boundaries-lock-claim+release]` commit

---

## Coordination note

Crafting is the **#1 expected V2 Economy module feature** per RES_001 §15.2 + REFERENCE_GAMES_SURVEY P11 (production chains in Anno/Banished/Frostpunk/Vic3). Heavy coupling with RES_001 (input/output ResourceBalance), DF7 (skill checks), PCS_001 (per-PC skill/recipes), NPC_001 (NPC crafters).
