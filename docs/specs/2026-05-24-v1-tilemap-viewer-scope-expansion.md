# V1 tilemap viewer — scope expansion

> **Branch:** `mmo-rpg/zone-map-amaw`
> **Builds on:** [`2026-05-24-v1-tilemap-viewer-rescope.md`](./2026-05-24-v1-tilemap-viewer-rescope.md)
> **Status:** ACCEPTED 2026-05-24 (PO direct, after catching the scope gap)
> **Size:** L–XL (≥ 12 files, 6+ logic blocks, side effects: spec re-open)

## 0. Why this addendum exists

The prior rescope (commit `34fa39bf`) shipped foundation tile rendering
and was declared "V1 done" — incorrectly. The `TilemapView` response
contains 5 visualisable layers; the viewer rendered only 1. PO caught
this with: "v1 làm gì đã xong? có mỗi foundation, chúng ta build
tilemap rồi đâu?".

Root cause analysis preserved in
[`feedback-viewer-scope-enumerate-all-backend-fields`](file:///C:/Users/NeneScarlet/.claude/projects/d--Works-source-lore-weave-zone-map-design/memory/feedback_viewer_scope_enumerate_all_backend_fields.md):
when scoping a viewer/debugger for an existing backend, the AC list
MUST enumerate every backend field. Spec data-shape documentation
is not the same as render scope. The prior spec §4 listed all 5
fields but §2 Definition of Done + §8 ACs covered only `terrain_layer`.

This addendum expands V1 to render every field the backend returns.

## 1. Backend output — full enumeration

`POST /internal/v1/tilemaps/render` returns `TilemapView` with these
visualisable fields (mirror of
`services/tilemap-service/src/types/tilemap.rs`):

| Field | What it is | Sample @ seed=1 town 64² |
|---|---|---|
| `terrain_layer: u8[width*height]` | Flat per-tile TerrainKind index (1–10) | 4 096 tiles |
| `zones: ZoneRuntime[]` | Per-zone metadata (id, role, center, terrain, `assigned_tiles` bitmap) | 5 zones |
| `road_segments: RoadSegment[]` | MST edge polylines (each is `waypoints: TileCoord[]`) | 4 segments / 108 waypoints |
| `river_segments: RiverSegment[]` | Polylines (`tiles: TileCoord[]`) + `crossings: { at, kind: bridge \| ford }[]` | 4 segments / 164 tiles / 93 crossings |
| `object_placements: TilemapObjectPlacement[]` | Placed objects (`kind`, `anchor`, `biome_object_type?`, `value?`) | 88 placements (all `obstacle.mountain` at this seed) |
| `child_cell_anchors: Record<string, TileCoord>` | Cross-aggregate anchors for drill-down (V2+) | empty |
| `generation_source: { kind: 'engine_generated' \| 'llm_augmented' }` | Provenance | engine_generated |
| `regional_narration: string?` | V2 LLM narration cache | None V1 |
| `prompt_template_version: u32` | V2 L4 cache invalidator | 0 |

V1 viewer renders the **first 5 fields**; the latter 3 are V2 hooks
that don't visualise (display as a side-panel metadata block).

### Tiered sprite size system (approved 2026-05-24 PO)

Minimum sprite display = **128 × 128** (no smaller). Character /
landmark sprites scale up per RPG genre convention (Tale of Immortal
style: substantial prop presence on a top-down map). DPI math:
5 cm physical at 96 DPI desktop ≈ 189 px; at 144 DPI HiDPI ≈ 284 px —
Player + landmark sprites sit in this range.

**TILE_PX stays at 64**; sprites larger than a tile span multiple
tiles visually (HoMM3 convention — town is 4-6 tiles wide etc.).

| Tier | Display | Tiles wide | Source res | Kind / subtype | Default HoMM3 source candidate |
|---|---|---|---|---|---|
| **Player** | 192×192 | 3 | 384×384 | Main character avatar | (programmatic warrior silhouette V1; per-book gen V2) |
| **Tier-XL** | 384×384 | 6 | 768×768 | Town / major landmark | `castle_quarter_wide`, `hamlet_timber_row`, `cottage_cluster`, `hero_monument_statue_tall` |
| **Tier-L** | 256×256 | 4 | 512×512 | Mine / shrine / portal / tower | `mine_gold_entrance`, `mine_ore_entrance`, `mine_gem_cavern_mouth`, `shrine_magic_arcane`, `portal_gate_stone`, `wizard_tower_ruin`, `monument_obelisk` |
| **Tier-M** | 192×192 | 3 | 384×384 | Mountain / large obstacle | `rock_pillar_obstacle`, `siege_tower_fragment_tall`, `palisade_fence_segment` |
| **Tier-S** | 160×160 | 2.5 | 320×320 | Tree / bush / treasure | trees (135 biome variants), bushes, `treasure_pile_prop` |
| **Tier-XS** | 128×128 | 2 | 256×256 | Misc small / decoration / mushroom | `boundary_stones_ring`, `lantern_post_double`, `haystack_pitchfork_prop`, mushrooms |
| **Tier-Marker** | 128×128 | 2 | 128×128 (programmatic) | Abstract markers — MonsterLair, Ferry, Animal (V2), Other, Crater, Lake | programmatic (no HoMM3 asset) |

### Per-(kind, subtype) sprite mapping — V1 default

| `TilemapObjectKind` | `biome_object_type` | Tier | Source strategy |
|---|---|---|---|
| `town` | — | XL | HoMM3 `castle_quarter_wide` (default) |
| `landmark` | — | XL / L | HoMM3 `hero_monument_statue_tall` (XL) or `monument_obelisk` (L) |
| `mine` | — | L | HoMM3 `mine_gold_entrance` (V2 may vary by treasure value) |
| `monolith` | — | L | HoMM3 `portal_gate_stone` |
| `treasure` | — | S | HoMM3 `treasure_pile_prop` |
| `obstacle` | `mountain` | M | HoMM3 `rock_pillar_obstacle` |
| `obstacle` | `tree` | S | HoMM3 tree (V1 default: `grassland_temperate/silver_birch`; biome-aware = V2 work) |
| `obstacle` | `plant` | S | HoMM3 bush (V1 default `grassland_temperate`) |
| `obstacle` | `structure` | M | HoMM3 `siege_tower_fragment_tall` |
| `obstacle` | `rock` | XS | HoMM3 `rock_pillar_obstacle` (smaller-scale instance) |
| `obstacle` | `lake` | M | programmatic blue ellipse |
| `obstacle` | `crater` | S | programmatic dark ring |
| `obstacle` | `animal` | Marker | programmatic red silhouette (V2 reserve) |
| `obstacle` | `other` | Marker | programmatic magenta question-mark |
| `monster_lair` | — | Marker | programmatic skull icon |
| `ferry` | — | Marker | programmatic boat icon |
| `decoration` | — | XS | HoMM3 `boundary_stones_ring` / `lantern_post_double` |

**~16 HoMM3 placeholders (Flux1-dev, non-commercial via DEFERRED #037)
+ ~5–6 programmatic Tier-Marker icons (ship-anywhere license).**

### Rendering rules

- **Anchor:** `setOrigin(0.5, 1.0)` — sprite foot at tile center, top
  grows upward. Multi-tile sprites overlap neighbouring tiles
  visually but are *placed* at single `anchor` coord.
- **Depth sort:** by `anchor.y` (lower-y = behind, higher-y = front)
  so props don't z-fight when clustered. Player keeps `depth=1000`
  above everything.
- **License:** HoMM3 sources are Flux1-dev (non-commercial); same
  DEFERRED #037 caveat as foundation pre-pivot. Programmatic markers
  are first-party, no restrictions.

### Bundle weight estimate

| Tier | Count | Per-PNG | Subtotal |
|---|---|---|---|
| Tier-XL | 4 | ~350 KB | 1.4 MB |
| Tier-L | 4 | ~150 KB | 600 KB |
| Tier-M | 3 | ~80 KB | 240 KB |
| Tier-S | 4 | ~60 KB | 240 KB |
| Tier-XS | 2 | ~40 KB | 80 KB |
| Tier-Marker | 5–6 | ~15 KB | ~90 KB |
| Player sprite | 1 | ~80 KB | 80 KB |

**Total ≈ 2.7 MB asset bundle.** Out-of-band from JS gzip budget
(700 KB) — `dist/assets/*.js` stays well under.

### Implementation strategy

- Step A in §7 (was `gen-prop-icons.py 32×32`) renamed to
  `gen-prop-bundle.py`:
  - Downsample 16 HoMM3 PNGs from `G:/local-image-generator-service/
    outputs/homm3-bundle/pass-full-001/` to per-tier source res, save
    into `frontend-game/public/assets/sprites/<tier>/<kind>.png`
  - Draw 5–6 programmatic markers via PIL at 128×128 each into
    `frontend-game/public/assets/sprites/marker/<name>.png`
  - Draw 1 programmatic player at 384×384 into
    `frontend-game/public/assets/sprites/player.png`
  - Same first-party generator pattern as
    `gen-foundation-tiles.py`

## 2. V1 layers — what to render

| # | Layer | Render approach |
|---|---|---|
| L0 | Foundation (`terrain_layer`) | ✅ shipped 34fa39bf — algorithm-generated tile per TerrainKind |
| L1 | Roads (`road_segments[].waypoints`) | Line strip in earth-brown, width ~6 px, drawn between waypoint centres. One per segment. |
| L2 | Rivers (`river_segments[].tiles`) | Line strip in deep-blue, width ~8 px (wider than roads). Drawn along tile centres in order. |
| L3 | River crossings | At each `crossing.at` tile, draw a small sprite: `kind=bridge` → golden plank icon; `kind=ford` → lighter blue stepping-stones icon. |
| L4 | Object placements | At each `placement.anchor` tile, draw the kind/subtype icon centered on the tile. |
| L5 | Zone boundaries (debug overlay, default OFF) | For each zone, derive outline from `assigned_tiles` bitmap → draw 1 px outline in zone-role-colored tint (capital=gold, hub=indigo, wilderness=green, sea=blue, forbidden=red, etc.). |
| L6 | Zone center markers (debug overlay, default OFF) | At each `zone.center_position`, draw a small × marker labelled with `zone.zone_id`. |
| L7 | Player sprite | ✅ shipped — yellow circle at hub center spawn. |

## 3. Viewer UX features

### 3.1 Layer toggle panel
Top-right of `/play` route — checkboxes for L0, L1, L2, L3, L4, L5, L6.
Default state: L0–L4 + L7 ON; L5, L6 OFF (debug-only).

### 3.2 Tile inspector
On pointerdown over a tile (consumed BEFORE Player.walkTo), show a
side panel with:
- Tile coord `(x, y)`
- TerrainKind tag from `terrain_layer[y*W + x]`
- Owning zone id + role (lookup via `zones[].assigned_tiles`)
- Any object placement at this anchor (kind, biome_object_type, value)
- Road segment passing through? River segment? Crossing?

Right-click or Esc closes the inspector. Click-to-walk still works
when inspector is closed.

### 3.3 Existing controls (kept)
Seed input · tier dropdown · width / height · "Render zone" button —
already shipped 34fa39bf, retained as-is.

### 3.4 Metadata side panel (compact, bottom-left or collapsed)
Display non-visual `TilemapView` metadata:
- `template_id`, `seed`, `tier`, `grid_size`
- `generation_source.kind` + (V2) model + attempts
- `prompt_template_version`
- Per-zone summary table (zone_id, role, center, terrain)

## 4. Out of scope (V2 / future)

| Item | Where |
|---|---|
| Hand-painted prop overlay sprites (replacing programmatic icons) | DEFERRED #037 — V2 asset pipeline (prop/overlay layer) |
| Click drill-down on Town → CSC_001 16×16 interior | V2+ — depends on `mmo-rpg/csc-interior` (future) |
| LLM-narration display per zone | V2+ — depends on `mmo-rpg/llm-narration` (future) |
| Multi-template browser (other than `minimal.json`) | V1.x add-on, low priority |
| Continent (256²) render perf optimisations | V1.x perf pass (DEFERRED #016/#018/#020 already cleared) |
| Camera drag-to-pan (currently arrow keys + wheel zoom only) | Small follow-up, see §9 |

## 5. Code changes

### 5.1 New files

| File | Purpose |
|---|---|
| `frontend-game/scripts/gen-prop-icons.py` | Generates 17 programmatic icon PNGs (8 kinds + 9 obstacle subtypes; 32×32 each, total ~50 KB). PIL drawing primitives, no AI. |
| `frontend-game/public/assets/icons/objects/*.png` | The 17 generated icons. |
| `frontend-game/public/assets/icons/crossings/{bridge,ford}.png` | Crossing markers (small 24×24 each). |
| `frontend-game/src/game/render/road-overlay.ts` | Layer renderer: draws polylines for `road_segments`. |
| `frontend-game/src/game/render/river-overlay.ts` | Layer renderer: draws river polylines + crossings. |
| `frontend-game/src/game/render/object-overlay.ts` | Layer renderer: places sprite per `object_placements[]` entry. |
| `frontend-game/src/game/render/zone-overlay.ts` | Layer renderer: zone boundaries + center markers (toggleable). |
| `frontend-game/src/components/viewer/LayerToggles.tsx` | Checkbox panel for L0–L6. |
| `frontend-game/src/components/viewer/TileInspector.tsx` | Side panel showing clicked-tile metadata. |
| `frontend-game/src/components/viewer/MetadataPanel.tsx` | Bottom-left metadata block (template_id, seed, etc.). |
| `frontend-game/src/store/viewer-store.ts` | Zustand store for layer-visibility + inspector state. |

### 5.2 Modified files

| File | Change |
|---|---|
| `frontend-game/src/game/scenes/WorldScene.ts` | Call each layer renderer in turn (L0 → L4); subscribe to viewer-store for toggles. Tile inspector hook intercepts pointerdown. |
| `frontend-game/src/game/scenes/PreloaderScene.ts` | Load 17 icon PNGs + 2 crossing PNGs as additional textures. |
| `frontend-game/src/routes/play.tsx` | Mount `LayerToggles`, `TileInspector`, `MetadataPanel` overlays. |
| `frontend-game/src/types/tilemap.ts` | Expand `ZoneRuntime` (already there), add `TilemapObjectKind` + `BiomeObjectType` enums + tag functions. |

### 5.3 No backend changes

`/internal/v1/tilemaps/render` already returns everything we need.
Zero changes to `services/tilemap-service`.

## 6. Acceptance criteria (V1 done, complete enumeration)

Each backend field gets its own AC. Each viewer UX feature gets its own.

### 6.1 Render coverage ACs

| AC | Statement |
|---|---|
| AC-V1-X1 | L0 foundation tiles render — already shipped 34fa39bf (carried forward) |
| AC-V1-X2 | L1 — every `road_segments[i].waypoints` polyline is drawn as a connected line strip on the canvas |
| AC-V1-X3 | L2 — every `river_segments[i].tiles` polyline is drawn as a connected line strip, visibly distinct from roads (blue vs brown, wider) |
| AC-V1-X4 | L3 — at each `river_segments[i].crossings[j].at` tile, a bridge OR ford marker is drawn matching `crossings[j].kind` |
| AC-V1-X5 | L4 — at each `object_placements[i].anchor` tile, an icon is drawn corresponding to `placements[i].kind` (and `biome_object_type` for obstacles) |
| AC-V1-X6 | L5 — zone-boundaries overlay can be toggled on; when on, each `zones[i].assigned_tiles` boundary is outlined |
| AC-V1-X7 | L6 — zone-center overlay can be toggled on; when on, each `zones[i].center_position` shows a marker + zone id |

### 6.2 UX feature ACs

| AC | Statement |
|---|---|
| AC-V1-X8 | LayerToggles panel — 7 checkboxes (L0–L6) wired to viewer-store; toggling re-renders without re-fetching backend |
| AC-V1-X9 | TileInspector — clicking a tile shows (x,y) + terrain tag + zone (id, role) + objects at that anchor + road/river hits |
| AC-V1-X10 | MetadataPanel — shows `template_id`, `seed`, `tier`, `grid_size`, `generation_source.kind`, and per-zone summary table |

### 6.3 Carried-forward ACs (already passed 34fa39bf)

AC-V1-1 (POST + bearer) · AC-V1-2 (typed parse) · AC-V1-5 (different seed → different map) · AC-V1-6 (click-to-walk respects bounds) · AC-V1-7 (iso deleted) · AC-V1-8 (build ≤ 700 KB gzip) · AC-V1-9 (tests pass) — all retained.

### 6.4 Test coverage (additive)

- `road-overlay.test.ts` — given a RoadSegment with 5 waypoints, asserts 4 line segments drawn at expected (sx, sy) pairs
- `river-overlay.test.ts` — same for RiverSegment + assert crossing markers placed at correct tiles
- `object-overlay.test.ts` — assert icon-key picked correctly per kind/biome_object_type permutation (9 obstacle subtypes + 8 other kinds = 17 cases)
- `tile-inspector.test.ts` — given a clicked (x,y), assert correct metadata extracted from a TilemapView fixture

Target: +12 unit tests, total 29.

## 7. Implementation order (concrete sub-tasks)

1. **Icons + assets** (Step A — ~30 min)
   - Write `gen-prop-icons.py`: 8 kind icons + 9 obstacle subtype icons + 2 crossing markers, 32×32 PNG each
   - Run → 17 icon PNGs + 2 crossings into `frontend-game/public/assets/icons/`

2. **Types** (Step B — ~15 min)
   - Add `TilemapObjectKind` + `BiomeObjectType` enums + tag functions to `src/types/tilemap.ts`

3. **Viewer store** (Step C — ~15 min)
   - `src/store/viewer-store.ts` — `{ visibleLayers, selectedTile, inspectorOpen, setLayer, selectTile }`

4. **Road overlay** (Step D — ~30 min)
   - Layer renderer reading `tilemap.road_segments` → `scene.add.graphics()` line strip
   - Wire into WorldScene render order (after L0 foundation)
   - Unit test

5. **River overlay + crossings** (Step E — ~45 min)
   - Layer renderer for `river_segments[].tiles` (polyline)
   - + sprite placement for `crossings[]` per kind
   - Wire into WorldScene
   - Unit test

6. **Object overlay** (Step F — ~60 min)
   - Map `(kind, biome_object_type)` → icon texture key
   - Place sprite at each `anchor` tile (centered, depth above L1/L2/L3)
   - Wire into WorldScene
   - Unit test (17-case mapping)

7. **Zone boundary + center overlays** (Step G — ~45 min)
   - Boundary: iterate `assigned_tiles` bitmap, find boundary tiles (8-neighbour check), draw 1-px lines
   - Center: marker + label
   - Toggle wired to viewer-store; default OFF
   - Unit test

8. **Layer toggles UI** (Step H — ~30 min)
   - `LayerToggles.tsx` — 7 checkboxes, Zustand-bound

9. **Tile inspector UI** (Step I — ~45 min)
   - `TileInspector.tsx` side panel
   - InputSystem extended: distinguish inspector click vs walk click (modifier key or panel state)
   - Unit test

10. **Metadata panel** (Step J — ~20 min)
    - `MetadataPanel.tsx` collapsed by default

11. **Verify + tile screenshots** (Step K — ~30 min)
    - Browser smoke: render at seed=1, seed=42; layer toggles work; inspector opens
    - Screenshots: full-render (L0–L4) + with zone boundaries (L5)

12. **Test pass + commit** (Step L — ~15 min)
    - 29 tests passing, typecheck clean, build clean
    - Commit on top of `34fa39bf` on same branch

Total estimate: **~6 hours** of focused work. Could split into 2
sessions (steps A–F = render layers, ~3h; G–L = UX features + verify, ~3h).

## 8. Out-of-scope notes carried as DEFERRED

- **#039 (NEW)** — `gen-prop-icons.py` produces simple icon-style
  programmatic sprites; V2 asset pipeline replaces with hand-painted
  prop sprites at full resolution (DEFERRED #037 already covers
  prop/overlay rework). #039 records the specific "icons are
  symbolic placeholders, not artistic" gap.
- Camera drag-to-pan — see §4
- Click drill-down on Town/Landmark → CSC_001 interior — V2 (own
  branch when CSC_001 is built)

## 9. PO sign-off

PO direct decision 2026-05-24 after catching the prior scope gap.
Lesson saved cross-session
([`feedback-viewer-scope-enumerate-all-backend-fields`](../../C:/Users/NeneScarlet/.claude/projects/d--Works-source-lore-weave-zone-map-design/memory/feedback_viewer_scope_enumerate_all_backend_fields.md)).
