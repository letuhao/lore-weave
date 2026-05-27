# Engine→L3→L4 Bootstrap Rewire — Spec

> **Track:** `LLM_MMO_RPG` tilemap-service · **Branch:** `mmo-rpg/zone-map-amaw`
> **Workflow:** default v2.2 human-in-loop · **Size:** M (1 file + tests)
> **Source:** `services/tilemap-service/src/harness/bootstrap.rs`

---

## §1 Context

`bootstrap_small_reality` (the `tilemap-service bootstrap` CLI demo) places a
small reality via the engine, then drives the L3 zone-classifier + L4 narration
retry loops. Today it classifies a **hardcoded fixture object set**
(`bootstrap_placeholders()` — 6 invented `L3Placeholder`s) — the bootstrap's own
module docs flag this: *"The objects are fixture, not engine-placed."*

Phase E completed the modificator pipeline: `place_tilemap` now emits a real
`object_placements` Vec (treasures, guards, monoliths, obstacles, ferries). This
task **rewires the bootstrap to feed engine-placed objects into L3** — the
genuine engine→L3→L4 flow.

## §2 Scope

### In scope
- Replace `bootstrap_placeholders()` with a function that derives
  `Vec<L3Placeholder>` from `tilemap.object_placements`.
- Map every `TilemapObjectKind` → an L3 `kind` label + a `suggested_canon_kind`
  closed set (PO decision: **all kinds, including `Obstacle`**, are classified).
- Resolve each object's `zone_id` from the zone owning its `anchor`.
- Synthesize `obj_id`s (`^obj_[0-9]+$`).
- Enrich `bootstrap_template` so the engine reliably produces a varied object
  set (treasure + guards + obstacles + a monolith) — otherwise the demo
  classifies a thin set.
- Remove the dead fixture object set from `bootstrap.rs`.

### PO decision (CLARIFY 2026-05-18)
- **PO-1** — the bootstrap classifies **every placed object kind, including
  `Obstacle`** (biome fill). The bootstrap runs on a small 48×48 reality, so the
  obstacle count is demo-sized, not continent-scale.

### Out of scope
- L3 payload scaling / sampling caps for continent-scale maps (a real concern at
  256² — deferred; the bootstrap is a small-reality demo).
- The HTTP service surface, Postgres, production object-classification API.
- Changes to the L3/L4 retry loops, prompt, or tool schema.

## §3 Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | `bootstrap_small_reality` builds its `L3Placeholder`s from `tilemap.object_placements`; the hardcoded `bootstrap_placeholders()` is gone. |
| AC-2 | Every `TilemapObjectKind` variant maps to a non-empty `kind` label and a non-empty `suggested_canon_kind` list (index 0 = engine default), `Obstacle` included. |
| AC-3 | Each placeholder's `zone_id` is the id of the zone whose `assigned_tiles` contains the object's `anchor`. |
| AC-4 | `obj_id`s are `obj_{i}` over `object_placements` order — unique and matching the tool schema's `^obj_[0-9]+$`. |
| AC-5 | `bootstrap_template` deterministically yields a varied object set — ≥1 `Treasure`, ≥1 `MonsterLair`, ≥1 `Obstacle` — so the L3 demo is non-trivial. |
| AC-6 | The L4 input join (`objects_by_zone`) still resolves engine-derived placeholders to placed zones. |
| AC-7 | Determinism — a fixed seed yields the same placeholder set (obj_id, kind, zone, suggestions). |
| AC-8 | An `Obstacle` placeholder's `suggested_canon_kind` is keyed by its `biome_object_type` — every `BiomeObjectType` (and the untagged `None`) maps to a non-empty list, and distinct biome types get distinct lists (post-review finding #1). |

## §5 Module design

All changes are in `harness/bootstrap.rs`.

### §5.1 `kind_label` (D2)

`fn kind_label(TilemapObjectKind) -> &'static str` — the PascalCase variant name
(`Treasure`, `MonsterLair`, `Town`, `Mine`, `Landmark`, `Monolith`,
`Decoration`, `Obstacle`, `Ferry`). A `match` over all 9 variants (no wildcard —
a future variant forces a compile error here).

### §5.2 `suggested_canon_kind` (D3)

`fn suggested_canon_kind(TilemapObjectKind) -> &'static [&'static str]` — a
static closed set per kind, **index 0 = the engine default** (TMP_008b §6
canonical-default fallback). Wuxia-flavoured to match the bootstrap reality:

| Kind | Suggestions (index 0 = default) |
|---|---|
| `Treasure` | BanditCache, AbandonedCellar, OldShrine |
| `MonsterLair` | BanditCamp, WolfDen, ElvenWatcher |
| `Monolith` | AncientWaygate, JadePortalStone, SpiritGate |
| `Obstacle` | RockOutcrop, TangledThicket, FallenTimber |
| `Ferry` | RiverFerry, RopeBridgeCrossing, FerrymanDock |
| `Landmark` | AncientTree, RuinedWell, RobberShrine |
| `Town` | MarketTown, WalledCity, TradingPost |
| `Mine` | IronMine, JadeQuarry, SaltMine |
| `Decoration` | WildFlowers, MossyStones, Brambles |

For `Obstacle`, the suggestion list is keyed by `biome_object_type` instead
(`obstacle_suggestions`, §5.3a) — a mountain, lake, and tree get distinct
canonical kinds rather than one generic list, so an L3 classification (and the
§6 default) is semantically honest. The `Obstacle` arm of `suggested_canon_kind`
remains as the `biome_object_type: None` fallback.

### §5.3a `obstacle_suggestions` (post-review finding #1)

`fn obstacle_suggestions(Option<BiomeObjectType>) -> &'static [&'static str]` —
a static closed set per `BiomeObjectType` (all 9 variants — Mountain, Tree,
Lake, Crater, Rock, Plant, Structure, Animal, Other), index 0 = engine default.
`None` (an untagged obstacle — engine obstacles are always tagged, so this is
defensive) falls back to `suggested_canon_kind(Obstacle)`. `engine_placeholders`
dispatches: `Obstacle` ⇒ `obstacle_suggestions(p.biome_object_type)`, every
other kind ⇒ `suggested_canon_kind(p.kind)`.

### §5.3 `engine_placeholders` (D1·D3·D4)

Replaces `bootstrap_placeholders()`:

```
fn engine_placeholders(tilemap: &TilemapView) -> Vec<L3Placeholder>
```

For each `(i, placement)` in `tilemap.object_placements.iter().enumerate()`:
- `obj_id = format!("obj_{}", i + 1)` — 1-based, matches the existing
  `obj_1…` convention + the tool schema's `^obj_[0-9]+$` (D1).
- `kind = kind_label(placement.kind)`.
- `zone_id` = the zone whose `assigned_tiles` contains `placement.anchor`
  (`tilemap.zones.iter().find(...)`). An anchor in no zone (impossible — zones
  partition the grid) ⇒ the object is **skipped** (defensive, no panic) (D4).
- `suggested_canon_kind = suggested_canon_kind(placement.kind)`.

Determinism: `object_placements` order is fixed (deterministic engine), so the
placeholder set — obj_id, kind, zone, suggestions — is reproducible (AC-7).

### §5.4 `bootstrap_template` enrichment (D5)

The current 3-zone template carries no `treasure_tiers`, so the engine places
only obstacles + connection guards. Enrich it so a varied object set appears:

- Give both `Wilderness` zones a `treasure_tiers` entry with `min ≥ 2000` ⇒
  `TreasurePlacer` emits `Treasure` piles **and** their `MonsterLair` guards
  (the Phase-C precedent).
- Add a 4th zone — a `Forbidden` zone reached from `jianghu_capital` by a
  `Portal` connection ⇒ `ConnectionsPlacer` places a `Monolith` pair.
- `Obstacle`s appear automatically (ObstaclePlacer's §2.3 Mountain rule).

Result: the demo classifies `Treasure` + `MonsterLair` + `Obstacle` +
`Monolith` — exercising the multi-kind mapping (AC-5). `Ferry` needs specific
non-bordering-Sea geometry and is not forced; the mapping still handles it if
one ever appears.

### §5.5 L4 join (AC-6)

The existing `objects_by_zone` join keys `L3Classification.obj_id` →
`L3Placeholder.zone_id` via the `obj_zone` map built from the placeholder list.
Because `engine_placeholders` populates `zone_id` honestly, the join is
unchanged — it already reads `placeholders`, now engine-derived.

### §5.6 Test plan

- `engine_placeholders` over a hand-built `TilemapView`: obj_ids unique +
  `^obj_[0-9]+$`; each `zone_id` is the anchor's owning zone; every kind maps to
  a non-empty suggestion list.
- `kind_label` / `suggested_canon_kind` total over all 9 variants (a `match`
  with no wildcard already guarantees this at compile time; the test asserts
  non-empty suggestions).
- `bootstrap_template` + `place_tilemap` ⇒ `object_placements` carries ≥1
  `Treasure`, ≥1 `MonsterLair`, ≥1 `Obstacle` (AC-5).
- Determinism: `engine_placeholders` on a fixed-seed `place_tilemap` twice ⇒
  equal placeholder sets (AC-7). *(REVIEW-DESIGN R1: `L3Placeholder` derives
  only `Debug, Clone` — no `PartialEq`. To keep the rewire a single-file change
  the test compares **projected tuples** `(obj_id, kind, zone_id,
  suggested_canon_kind)` rather than the struct directly.)*

