# CFT — Crafting System V2 Reservation

> **Status:** RESERVED 2026-04-26 — V2 deferred. No design here. Captures namespace reservation + V1 hooks + V2 scope sketch.
>
> **DO NOT design crafting in this file.** When V2 begins, create `CFT_001_recipe_foundation.md` per pattern of foundation tier features.

---

## §1 — What crafting system is

**Recipe-driven transformation**: actor consumes input materials + invokes skill + uses tool + waits time → produces output material/item. Multi-step production chains (ore → ingot → tool → weapon) emerge from chained recipes.

V2 scope (high-level): Recipe aggregate + ingredient/output declarations + skill/tool prerequisites + crafting station integration + quality variation per skill + production chain composability.

---

## §2 — Why V2 deferred (not V1)

- **Depends on Item-unique kind** — quality variation requires per-instance ItemInstanceId tracking; RES_001 Item kind is V1+30d reserved (RES-D1)
- **Depends on DF7 PC Stats** — skill checks require numeric stats system; DF7 is V1-blocking deferred
- **Depends on full crafting station model** — workshop integration extends RES_001 cell-as-producer pattern
- **V1 has no V1 producer** — without crafting feature, RES_001 Material kind has no consumer V1 (just trade good); ship as-is V1
- **Reference-games survey** — P11 production chains is dominant in Anno/Banished/Vic3 (V2 Economy module territory)

---

## §3 — Existing V1 hooks already reserved

| Hook | Owner | Reserved as |
|---|---|---|
| `Recipe(RecipeId)` ResourceKind variant | RES_001 §3.1 | V2 reserved enum variant — recipes-as-knowledge transferable resource |
| `RES-D11 Recipe aggregate` | RES_001 §15.2 V2 Economy module | "Production chains (Recipe aggregate + crafting feature; multi-step input → output chains)" |
| `Material(MaterialKindId)` ResourceKind | RES_001 §3.1 | V1 active — V1 trade only; V2 becomes crafting input |
| `PL_005 Use kind` | PL_005 §9.1 | extends to "use crafting tool with material inputs" V2 |

---

## §4 — V2 scope sketch (no design — bullets only)

When V2 design begins:

- **Recipe aggregate** (T2/Reality scope; per-(reality, recipe_id) row OR canonical RealityManifest decl)
- **Ingredient declarations** — `Vec<ResourceCost>` (kinds + amounts; references RES_001 ResourceKind)
- **Output declarations** — `Vec<ProductionOutput>` (with quality variance based on skill V2)
- **Tool requirements** — references EF_001 EntityRef::Item; tool consumed/non-consumed per recipe
- **Skill requirements** — references DF7 PC Stats (e.g., `smithing >= 10`)
- **Crafting station** — references PF_001 PlaceType (smithy, kitchen, alchemy lab); recipe restricted to compatible station
- **Time cost** — fiction-time consumed during craft (page-turn pattern)
- **Quality variation** — per-skill output tier (rough → fine → masterwork; DF reference)
- **Recipe discovery** — author-canonical V2; LLM-discovered V2+; quest-rewarded V2+
- **Production chain composability** — output of recipe A is input of recipe B (Anno pattern)
- **NPC crafters** — NPCs with Occupation craft via own recipes (V2 NPC-job system RES-D15)

---

## §5 — Cross-folder relationships when V2 designs

| Touched folder | Concern |
|---|---|
| `00_resource/` (RES_001) | Material/Item kinds as input/output; ResourceBalance accounting |
| `00_entity/` (EF_001) | Tool entities; Item-unique tracking V1+30d |
| `00_place/` (PF_001) | Crafting station = cell with PlaceType (smithy / kitchen / alchemy lab) |
| `04_play_loop/` (PL_005) | Use kind extends with crafting sub-intent |
| `06_pc_systems/` (PCS_001 + DF7) | Per-PC skill checks; recipe knowledge per PC |
| `05_npc_systems/` (NPC_001) | NPC crafters with own recipe knowledge V2+ |
| `02_world_authoring/` (WA_003 Forge) | Author UI for declaring recipes + ingredients + outputs |
| `13_quests/` | Crafting quests (gather X, craft Y) — V2 Quest + V2 Crafting interplay |

---

## §6 — Reference games for V2 design

- **Mount & Blade Bannerlord** — smithing (skill-driven; quality tiers; player-crafted unique items)
- **Dwarf Fortress** — full material × quality × craftsmanship (most detailed)
- **RimWorld** — quality tiers + skill-driven; integrated with stockpile system
- **Anno 1800** — production chains (3-5 step chains; building per recipe; storage between steps)
- **Banished** — simpler chains (food → preserved food; iron ore → iron → tools)
- **Frostpunk** — crisis-driven crafting (limited materials force prioritization)
- **Stardew Valley** — workbench-tier progression (basic → advanced recipes unlock)
- **Wuxia/xianxia tone** — alchemy / 丹药 / 法宝 forging; spirit-stones as ingredient (V2+ Mana/Qi resource)

---

## §7 — Boundary lines (when V2 designs)

CFT will OWN:
- `Recipe` aggregate + `RecipeDecl` shape
- `Ingredient` + `Output` declarations
- `Skill requirement` references (DF7 stats)
- `Crafting station` association (PF_001 PlaceType)
- Quality variation algorithm (per-skill output tier)
- `crafting.*` RejectReason namespace
- Recipe discovery rules

CFT will NOT own (these stay where they are):
- Material kinds (RES_001 — author-declared in RealityManifest)
- Item-unique tracking (RES_001 V1+30d Item kind)
- PC skill values (DF7 PC Stats)
- Workshop building entities (PF_001 cell + PlaceType)
- Tool entities (EF_001 + RES_001 Item kind)

---

## §8 — Promotion checklist (when V2 design begins)

1. Read RES_001 §15.2 V2 Economy module (RES-D11 Recipe aggregate hook)
2. Read DF7 PC Stats (when designed; skill check pattern)
3. Read PCS_001 (per-PC skill state)
4. Survey reference games §6 (Anno production chains + DF material specificity primary)
5. Claim `_boundaries/_LOCK.md`
6. Create `catalog/cat_14_CFT_crafting.md`
7. Update `_boundaries/01_feature_ownership_matrix.md` Stable-ID prefix ownership row to add `CFT-*`
8. Update `_boundaries/02_extension_contracts.md` §1.4 add `crafting.*` rule_id namespace
9. Promote → CFT_001 DRAFT (~700-900 lines; matches RES_001 / NPC_001 precedent)
10. Coordinate with RES_001 closure pass to formalize Recipe(RecipeId) variant active
11. Release lock + commit `[boundaries-lock-claim+release]`

---

## §9 — DO NOT design here

- ❌ NO Rust struct definitions for Recipe aggregate
- ❌ NO ingredient/output schemas
- ❌ NO skill check formulas (DF7 owns)
- ❌ NO RejectReason rule_ids
- ❌ NO acceptance criteria

This is a RESERVATION + SCOPE SKETCH. V2 design lives in `CFT_001_recipe_foundation.md` when V2 begins.
