# V1 rescope — tilemap viewer / debug tool (Tale of Immortal camera pivot)

> **Branch:** `mmo-rpg/zone-map-amaw`
> **Supersedes:** parts of [`2026-05-24-frontend-game-architecture.md`](2026-05-24-frontend-game-architecture.md) — specifically §1 #7, §1 #10, §11 visual style, and §15–§17 (V1 scope + session ordering)
> **Status:** ACCEPTED 2026-05-24 (PO direct decision; no /review-impl round — short focused scope)
> **Size:** L (8 files, 4 logic blocks, 2 side effects)

## 1. Why this rescope exists

After V0 milestone close-out, PO surfaced two corrections:

1. **Asset-gen reality** — current image-gen models (Flux1-dev/SDXL +
   LoRAs) reliably produce front-view portraits + background
   paintings + top-down tile concepts but **FAIL** at iso 8-direction
   character spritesheets, seamless tileable iso terrain, and
   real-time combat animation frames. LoreWeave is a **multi-book
   platform** — each ingested novel becomes its own playable world
   with its own asset pack — so asset cost amortises across many
   books. Camera/visual paradigm must suit cheap per-book gen, not
   single-game polish. Iso 2:1 dimetric does not.

2. **Branch scope creep** — `mmo-rpg/zone-map-amaw` literal scope is
   **zone map**. The prior `2026-05-24-frontend-game-architecture.md`
   §17 V1 listed character-service (Go), JWT auth handshake,
   ZoneRoom presence sync, ChatRoom, CombatRoom — those are MMO
   infrastructure for the broader product vision and belong on
   separate branches (`mmo-rpg/character-service`,
   `mmo-rpg/multiplayer-rooms`, `mmo-rpg/combat`, etc.) when their
   time comes. Pulling them into V1 of this branch is scope drift.

## 2. New scope cap for V1 of this branch

V1 of `mmo-rpg/zone-map-amaw` ships **one thing**: a **tilemap
viewer / debug-tool component** that renders one real zone from
`tilemap-service`'s `POST /internal/v1/tilemaps/render` output.

### V1 Definition of Done

> Open browser at `/play` → frontend-game posts a baked-in minimal
> `TilemapTemplate` + seed + grid_size to tilemap-service's render
> endpoint → receives a real `TilemapView` → Phaser scene renders
> the procedural `terrain_layer` with placeholder textures (one per
> `TerrainKind` variant: grass, forest, mountain, water, sand,
> snow, swamp, road, rough, subterranean) → user can visually
> confirm the tilemap looks plausible across at least 3 distinct
> terrain regions.

If quality is OK during in-session smoke test → done → PR to `main`.

### Out of scope (explicit — these belong on different branches)

| Item | Where it goes |
|---|---|
| character-service (Go) | `mmo-rpg/character-service` branch (future) |
| JWT auth handshake (replacing dev token) | `mmo-rpg/auth-integration` branch (future) |
| ZoneRoom presence sync | `mmo-rpg/multiplayer-rooms` branch (future) |
| ChatRoom (global/party/zone) | `mmo-rpg/multiplayer-rooms` branch (future) |
| CombatRoom + paper-doll combat | `mmo-rpg/combat` branch (future) |
| Encounter scene UI / portrait flow | `mmo-rpg/encounter-scenes` branch (future) |
| LLM-driven scene narration | `mmo-rpg/llm-narration` branch (future) |
| Real character creation + persistence | depends on `mmo-rpg/character-service` |
| Asset pipeline rework (license-clean, per-book gen) | V2 design pass — see DEFERRED #037 |

### V0 features that stay AS-IS (not primary V1 deliverables)

- HUD HpBar / ManaBar — already shipped, leave on screen as debug
  readout of placeholder state
- EchoPanel WS echo — already shipped, leave wired to game-server
  EchoRoom; not expanded
- Click-to-walk Player on top-down grid — replaces V0 iso click;
  same semantics, simpler math
- TanStack Query `/livez` indicator — already shipped, stays

## 3. Visual paradigm — Tale of Immortal-style hybrid

| Layer | Camera | Why |
|---|---|---|
| **World/zone map** (this branch) | **Top-down 2D** (identity transform) | What `tilemap-service` outputs natively — its `terrain_layer` is a 2D flat array, no projection needed. Matches multi-book asset constraint (Flux can produce top-down tile concepts). |
| Encounter scene (future branch) | Front-view portrait + hand-painted background | Tale of Immortal pattern. Flux excels at portraits + paintings. |
| Combat (future branch) | Paper-doll side-view, no real-time animation | Sand of Salzaar / xianxia pattern; turn-based; cheap per-book to gen. |

This branch only ships the top-down zone map layer.

### Replaces in prior spec

- §1 #7 "iso 128×64 HD" → **top-down tile, default 64×64 px,
  configurable via `TILE_PX` constant**
- §1 #10 "iso 2:1 dimetric" → **top-down orthogonal grid (identity
  projection)**
- §11 visual style — references to iso math, depth sorting, ¾ view
  art — replaced with top-down references
- §3 directory — `iso-math.ts` / `iso-projection.ts` get renamed
  `world-math.ts` (identity transform) — old names removed

## 4. Wire shape (already exists — verified 2026-05-24)

Frontend posts to backend's existing endpoint:

```
POST http://localhost:8220/internal/v1/tilemaps/render
Authorization: Bearer ${VITE_LOREWEAVE_INTERNAL_TOKEN}
Content-Type: application/json

{
  "template": <TilemapTemplate JSON — 5 zones, see fixtures>,
  "channel_id": "ch_v1_viewer",
  "tier": "town",                    // or country/district/continent
  "grid_size": { "width": 64, "height": 64 },
  "seed": 1
}
```

Response is `TilemapView` JSON:
- `terrain_layer: number[]` — flat array `y*width + x`, value 1-10
  per `TerrainKind` enum
- `zones: ZoneRuntime[]` — zone metadata (id, role, center, terrain)
- `road_segments: RoadSegment[]` — polylines
- `river_segments: RiverSegment[]` — polylines
- `object_placements: TilemapObjectPlacement[]` — placed objects

### TerrainKind enum (10 variants, u8 index)

| u8 | tag | placeholder asset (HoMM3 bundle) |
|---|---|---|
| 1 | grass | `homm3/terrain/grassland_temperate/primary_surface_blend` |
| 2 | forest | `homm3/terrain/grassland_temperate/dense_scrub_brush_patch` |
| 3 | mountain | `homm3/terrain/volcanic_ash/elevation_cliff_rim_chunk` |
| 4 | water | `homm3/terrain/ocean_abyssal/primary_surface_blend` |
| 5 | sand | `homm3/terrain/desert_dry/primary_surface_blend` |
| 6 | snow | `homm3/terrain/snow_frost/primary_surface_blend` |
| 7 | swamp | `homm3/terrain/swamp_dark/primary_surface_blend` |
| 8 | road | `homm3/terrain/grassland_temperate/road_wagon_ruts` |
| 9 | rough | `homm3/terrain/drake_badlands/primary_surface_blend` |
| 10 | subterranean | `homm3/terrain/abyss_chaos_rift/primary_surface_blend` |

The 1024×1024 source PNGs get downsampled to `TILE_PX` (64×64
default) at load time. **Non-tileable / non-seamless is OK for V1
debug tool** — the goal is "see procedural map render"; texture
seams are visible but acceptable for a viewer. License-clean
seamless gen is V2 (see DEFERRED #037).

## 5. Code changes (BUILD)

### 5.1 New files

| File | Purpose |
|---|---|
| `frontend-game/src/lib/world-math.ts` | Identity transform (worldX → screenX = x × TILE_PX). Replaces `iso-math.ts`. |
| `frontend-game/public/templates/minimal.json` | Baked-in `TilemapTemplate` fixture mirroring `services/tilemap-service/tests/http_integration.rs::minimal_template()` — 5 zones × 100 tiles, town tier, grid 64×64. |
| `frontend-game/public/assets/tiles/homm3-placeholder/*.png` | 10 downsampled tiles from HoMM3 bundle (per §4 table) — pre-baked at 64×64 each. Total ~50 KB. |

### 5.2 Modified files

| File | Change |
|---|---|
| `frontend-game/src/api/tilemap-client.ts` | + `useZoneTilemap()` hook posting to `/internal/v1/tilemaps/render` with template fixture + grid + seed; cached by `[seed, grid_size]` query key |
| `frontend-game/src/config/services.ts` | + `SERVICES.tilemapInternalToken` from `VITE_LOREWEAVE_INTERNAL_TOKEN` (V0 default `dev_internal_token`) |
| `frontend-game/src/game/scenes/PreloaderScene.ts` | Load 10 HoMM3 placeholder tiles + map TerrainKind u8 → texture key |
| `frontend-game/src/game/scenes/WorldScene.ts` | Replace 8×8 stub render: subscribe to `useZoneTilemap` data via EventBus / React-Phaser bridge; render top-down `terrain_layer` (each `(x,y)` → tile texture by `terrain_layer[y*W+x]`); respect `grid_size` from server |
| `frontend-game/src/game/systems/input-system.ts` | Replace iso `screenToTile` with identity transform (`Math.floor(pointerX / TILE_PX)`) |
| `frontend-game/src/game/systems/iso-projection.ts` | DELETE (replaced by `world-math.ts`) |
| `frontend-game/src/game/entities/Player.ts` | Top-down boundary check uses grid dims from server snapshot (not local constants); same `walkTo` tween |
| `frontend-game/src/game/config/constants.ts` | `TILE_PX = 64` (was `TILE_WIDTH=128 TILE_HEIGHT=64`); remove iso constants |
| `frontend-game/src/lib/iso-math.ts` | DELETE (replaced by `world-math.ts`) |
| `frontend-game/tests/lib/iso-math.test.ts` | DELETE → `tests/lib/world-math.test.ts` covers identity round-trip |
| `frontend-game/src/routes/play.tsx` | Add "Render zone" controls (seed input + tier dropdown + grid_size input + render button) bound to `useZoneTilemap` |

### 5.3 No backend changes

Tilemap-service `/internal/v1/tilemaps/render` already exists +
production-tested. Adding only `LOREWEAVE_CORS_ORIGINS` already
covers frontend-game origin (from V0 Session D). Nothing to change
in tilemap-service for this rescope.

## 6. Test plan (in-session VERIFY)

1. `pnpm --filter frontend-game typecheck` — clean
2. `pnpm --filter frontend-game test` — at least world-math identity
   round-trip passes (replaces 3 iso-math tests)
3. `pnpm --filter frontend-game build` — under 700 KB gzip budget
4. `docker compose --profile tilemap up tilemap-service` — health 200
5. `pnpm --filter frontend-game dev` (or compose with `frontend-game`
   profile) — navigate to `/play`
6. Click "Render zone" with default seed=1 → expect:
   - Network panel shows POST `/internal/v1/tilemaps/render` → 200
   - Canvas renders 64×64 tilegrid with visible distinct terrain
     regions (≥3 different `TerrainKind` variants visible)
   - Player sprite at top-left of grid; click-to-walk works on the
     real grid (boundary respects 64×64)
   - Console: 0 errors
7. Screenshot saved for SESSION_HANDOFF evidence

**If quality OK:** session marks task complete → PR to `main`.
**If not OK:** debug → another iteration; still in same session.

## 7. Risks + mitigations

| Risk | Mitigation |
|---|---|
| HoMM3 1024×1024 tiles look bad at 64×64 downsample | Acceptable for V1 debug tool. V2 asset rework (DEFERRED #037) replaces. |
| 64×64 grid × 10 textures × 1024² source = browser memory? | Pre-baked at 64×64 PNGs in `public/`; ~50 KB total — negligible |
| Internal-token bearer in client JS = security leak | Already DEFERRED #033 (V0 close-out). V1 viewer is dev/debug only; production deploy of viewer would need api-gateway-bff proxy. |
| `TilemapTemplate` JSON shape changes between versions | Bake template fixture in `public/templates/`; pinned to current schema. Re-bake if schema migrates. |
| EchoPanel + WS echo still on screen confuses "tilemap viewer" framing | Hide EchoPanel behind a `?debug=echo` query param to declutter (small frontend change). Optional — discuss if time permits. |

## 8. Acceptance criteria (V1 done)

| AC | Pass |
|---|---|
| AC-V1-1 — `useZoneTilemap` posts to render endpoint with bearer auth | |
| AC-V1-2 — Render endpoint 200 response parsed into `TilemapView` typed value | |
| AC-V1-3 — Phaser scene renders 64×64 tilegrid from `terrain_layer` | |
| AC-V1-4 — At least 3 distinct `TerrainKind` variants visible in 1 render | |
| AC-V1-5 — Re-render with different seed produces visually different map | |
| AC-V1-6 — Click-to-walk respects server-provided grid_size boundary | |
| AC-V1-7 — `iso-math.ts` / `iso-projection.ts` deleted; `world-math.ts` covers tile math | |
| AC-V1-8 — Build still ≤ 700 KB gzip | |
| AC-V1-9 — All existing tests (V0 23 unit + 15 e2e) still pass after pivot | |
| AC-V1-10 — Branch `mmo-rpg/zone-map-amaw` mergeable to `main` | |

## 9. DEFERRED follow-ups

- **#037** — V2 asset pipeline rework (license-clean per-book gen);
  target: V2 launch prep
- **#038** — HoMM3-bundle placeholder license documentation (Flux1-dev
  non-commercial; record in `frontend-game/public/assets/tiles/LICENSES.md`)

## 10. PO sign-off

PO direct decision 2026-05-24. No /review-impl this rescope — scope
narrowed enough that adversarial review on the rescope itself is
not load-bearing. /review-impl available if VERIFY surfaces concerns.
