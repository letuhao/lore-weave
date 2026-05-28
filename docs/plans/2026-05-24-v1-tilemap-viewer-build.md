# V1 tilemap viewer — BUILD plan

> Spec: [`docs/specs/2026-05-24-v1-tilemap-viewer-rescope.md`](../specs/2026-05-24-v1-tilemap-viewer-rescope.md)
> Size: L · Session: continuous (DESIGN → BUILD → TEST → PR in one)

## Execution order

### Step A — DEFERRED entries + memory hygiene
1. Add `#037` + `#038` rows to `docs/deferred/DEFERRED.md` (next ID slot = 037 per header comment)
2. Index updated next-id to 039

### Step B — placeholder asset bake
1. Copy 10 picked HoMM3 tiles per spec §4 table to
   `frontend-game/public/assets/tiles/homm3-placeholder/<terrain-tag>.png`
   - At 1024×1024 source resolution (browser downsample during Phaser load is fine
     for a debug viewer; pre-downsample optimisation = V2)
2. Write `frontend-game/public/assets/tiles/homm3-placeholder/LICENSES.md` noting:
   - Source: Flux1-dev + dark_fantasy_digital_v11 LoRA, generated 2026-04-30
   - License: **NON-COMMERCIAL ONLY** (Flux1-dev license restriction)
   - Status: V1 placeholder; V2 will re-gen with Flux schnell (Apache 2.0) or SDXL — see DEFERRED #037
3. Write `frontend-game/public/templates/minimal.json` — mirror of
   `services/tilemap-service/tests/http_integration.rs::minimal_template()`

### Step C — frontend math + config

1. NEW `frontend-game/src/lib/world-math.ts` — identity transform:
   - `tileToScreen(x, y, TILE_PX) → (x*TILE_PX, y*TILE_PX)`
   - `screenToTile(px, py, TILE_PX) → (floor(px/TILE_PX), floor(py/TILE_PX))`
   - Identity round-trip
2. DELETE `frontend-game/src/lib/iso-math.ts`
3. DELETE `frontend-game/src/game/systems/iso-projection.ts`
4. UPDATE `frontend-game/src/game/config/constants.ts` —
   `TILE_PX = 64`; remove `TILE_WIDTH` / `TILE_HEIGHT`

### Step D — API client + service config

1. UPDATE `frontend-game/src/config/services.ts` —
   add `SERVICES.tilemapInternalToken` reading
   `VITE_LOREWEAVE_INTERNAL_TOKEN` (V0 default `dev_internal_token`,
   matching V0 SERVICES.devToken pattern)
2. UPDATE `frontend-game/src/api/tilemap-client.ts` —
   add `useZoneTilemap({ seed, gridWidth, gridHeight, tier })`:
   - useQuery with key `['tilemap', seed, gridWidth, gridHeight, tier]`
   - fetches `/templates/minimal.json` first (cached after first call)
   - POSTs to `${SERVICES.tilemap}/internal/v1/tilemaps/render` with
     `Authorization: Bearer ${SERVICES.tilemapInternalToken}`,
     `Content-Type: application/json`
   - returns typed `TilemapView`
3. UPDATE `frontend-game/src/types/tilemap.ts` —
   add `TerrainKind` enum (1-10 matching backend), `TileCoord`,
   `ZoneRuntime`, `TilemapView` TS shapes (copy from
   `services/tilemap-service/src/types/tilemap.rs` Serialize defs)

### Step E — Phaser scene rewrite

1. UPDATE `frontend-game/src/game/scenes/PreloaderScene.ts`:
   - Load 10 HoMM3 placeholder tiles by texture key
     (`terrain-grass`, `terrain-forest`, ..., `terrain-subterranean`)
   - Display loading bar (already done)
2. UPDATE `frontend-game/src/game/scenes/WorldScene.ts`:
   - Accept `tilemap: TilemapView` via `scene.data.set('tilemap', view)`
     before scene.start (or via EventBus emit from React side)
   - In `create()`: iterate `view.terrain_layer`,
     for each `(x, y)` compute `kind = terrain_layer[y * width + x]`
     and `this.add.image(x * TILE_PX, y * TILE_PX, terrainKeyForKind(kind))
       .setDisplaySize(TILE_PX, TILE_PX).setOrigin(0, 0)`
   - Camera bounds = `(0, 0, width * TILE_PX, height * TILE_PX)`
   - Player spawn at zone with `zone_role === Hub` center, fallback (0,0)
3. UPDATE `frontend-game/src/game/systems/input-system.ts`:
   - `screenToTile` uses `world-math` identity transform
4. UPDATE `frontend-game/src/game/entities/Player.ts`:
   - Constructor takes `(scene, x, y, gridWidth, gridHeight)`
   - `isInBounds` uses passed grid dims (not constants)
   - `walkTo` tween moves to `tileToScreen` target

### Step F — Route wiring

1. UPDATE `frontend-game/src/routes/play.tsx`:
   - `useZoneTilemap({ seed: 1, gridWidth: 64, gridHeight: 64, tier: 'town' })`
   - When `data` ready, mount `<PhaserGame tilemap={data} />`
   - Add minimal controls panel (3 inputs + 1 button): seed integer,
     tier select (town/district/country/continent), re-render button
     calls `refetch()` with new seed
2. UPDATE `frontend-game/src/components/PhaserGame.tsx`:
   - Accept optional `tilemap` prop
   - When tilemap changes, restart `WorldScene` with the new data

### Step G — Test update

1. DELETE `frontend-game/tests/lib/iso-math.test.ts`
2. NEW `frontend-game/tests/lib/world-math.test.ts` — identity round-trip
3. UPDATE `frontend-game/tests/game/Player.test.ts` — pass grid dims to ctor
4. UPDATE `frontend-game/tests/setup.ts` — Phaser mock should still work
5. Run `pnpm --filter frontend-game test` — expect all green

### Step H — Compose env update

1. UPDATE `infra/docker-compose.yml` frontend-game env:
   - `VITE_LOREWEAVE_INTERNAL_TOKEN=dev_internal_token` (matches tilemap-service)
2. tilemap-service `LOREWEAVE_CORS_ORIGINS` already set to `http://localhost:5174`

## VERIFY (Step I)

Per spec §6. Capture screenshot for SESSION_HANDOFF evidence.

## Definition of done (this BUILD)

- All 10 AC from spec §8 satisfied
- 0 typecheck / lint errors
- All tests pass (delta: +1 test file world-math, -1 iso-math)
- Bundle ≤ 700 KB gzip
- Screenshot of real tilemap render saved
- 1 commit; PR opened to `main`
