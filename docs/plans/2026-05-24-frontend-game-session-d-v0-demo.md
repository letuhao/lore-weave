# Plan — Session D: V0 demo (Kenney CC0 + Player walk + tilemap-service /livez smoke)

> **Spec:** `docs/specs/2026-05-24-frontend-game-architecture.md` (§16 Session D, §13 asset pipeline, §1 #6 turn-based game model)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Size:** L (8 files: LICENSES, PACKAGES, loader rewrite, Player impl, input system, smoke notes; reclassified L by gate)
> **Predecessor:** Session C Phase 2 (commit 747acb06) — scaffold compiles, 3/3 tests pass, /play route renders 32×32 stub iso tilemap

## Goal

Visible browser demo proving:
1. Real Kenney CC0 PNG iso tiles load via `this.load.image` → `WorldScene` renders them at correct 128×64 dimensions
2. Click on a tile → Player sprite walks to that tile (tween over screenToTile target)
3. `useTilemapHealth()` shows `tilemap-service: ok` when the docker container is running

## Asset choice (per PO research this session)

**Pack:** Kenney **Isometric Tiles Landscape**
- URL: https://kenney.nl/assets/isometric-tiles-landscape
- Direct ZIP: https://kenney.nl/media/pages/assets/isometric-tiles-landscape/37eb18a8d1-1677695072/kenney_isometric-landscape.zip
- License: **CC0** (public domain — perfect, no attribution required but we credit anyway)
- Tile dimensions: **128×128** sprite (PNG canvas); iso diamond inside is 128 wide × 64 tall — **exact match for spec §1 #10 (128×64 iso 2:1 dimetric)**
- Contents: nature/landscape tiles (grass, water, dirt, stones)

**Why this pack over others:**
- 128×64 visible diamond matches our spec dimensions exactly (no scaling needed)
- Nature/landscape suits MMORPG world (grass + water primary)
- CC0 = simplest license footprint (no attribution requirement, though we credit)
- Larger Kenney "Isometric Miniature" series is 3D-render style; landscape pack is flat 2D iso which renders predictably on WebGL

## User action required (BUILD blocker — wait for PO drop)

1. Download `kenney_isometric-landscape.zip` from the direct URL above
2. Unzip into `frontend-game/public/assets/tiles/kenney-isometric-landscape/`
3. Resulting structure should look like:
   ```
   frontend-game/public/assets/tiles/kenney-isometric-landscape/
   ├── License.txt           (CC0 declaration from Kenney)
   ├── PNG/
   │   ├── landscapeTiles_001.png
   │   ├── landscapeTiles_002.png
   │   └── ... (~80-130 PNG files)
   └── Preview.png           (optional)
   ```
4. Tell me the filename of a grass tile (e.g., `landscapeTiles_067.png`) so I wire the loader to the right file
5. Confirm "downloaded" so I proceed to wire the loader

## Files to create (this session)

| # | File | Purpose |
|---|---|---|
| 1 | `frontend-game/public/assets/tiles/LICENSES.md` | Per-pack license audit per spec §13 + LOW-9; lists Kenney pack + future packs |
| 2 | `frontend-game/public/assets/PACKAGES.md` | Per-pack manifest (filename → use case mapping) so we know which tile is grass vs water |
| 3 | `frontend-game/src/game/scenes/PreloaderScene.ts` (REWRITE) | Drop stub graphics; `this.load.image('grass', '/assets/tiles/...')` + progress bar |
| 4 | `frontend-game/src/game/scenes/WorldScene.ts` (REWRITE) | Use real `'grass'` texture instead of `'stub-iso-tile'`; add Player + click handler |
| 5 | `frontend-game/src/game/entities/Player.ts` (REWRITE) | Real sprite + walk-to-target tween + queue |
| 6 | `frontend-game/src/game/systems/input-system.ts` (REWRITE) | Real Phaser pointer listener → screenToTile → emit `move-to` event |
| 7 | `docs/plans/2026-05-24-frontend-game-session-d-v0-demo.md` (this file) | Plan doc (L gate requirement) |
| 8 | `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` (UPDATE) | New CURRENT STATE entry |

Plus deletion:
- `frontend-game/public/assets/tiles/.gitkeep` (removed once real Kenney files land)

## Player movement design (per spec §1 #6 turn-based + idle MMO)

NOT action-MMO movement (no client prediction, no input buffer, no interpolation).

Pattern:
1. User clicks canvas pixel `(px, py)`
2. `input-system.ts`: convert to world tile via `screenToTile`, emit `EventBus.emit('player-action', { kind: 'move', target: { x, y } })`
3. `WorldScene` listens for `'player-action'`, calls `player.walkTo(target)`
4. `Player.walkTo(target)`: enqueue target; if no current walk, start a Phaser tween from current screen pos to `worldToScreen(target)` over ~250 ms; on complete, dequeue next or idle

Concession to spec turn-based:
- No collision detection in V0 (Session E+ adds server-validated movement)
- No animation frames (sprite just translates; Session D adds animation later)
- Single Player at fixed start tile (multiplayer is V1)

## tilemap-service /livez verification

1. `docker compose --profile tilemap up -d tilemap-service` from repo root
2. Wait for healthcheck (start_period 10s per Session A4 wire-up)
3. `curl http://localhost:8220/livez` → expect `{"status":"ok","endpoint":"livez","service":"tilemap-service"}`
4. Open `/play` route in browser → `useTilemapHealth()` polls every 10s → React HUD overlay shows `tilemap-service: ok`
5. Stop container after smoke (`docker compose --profile tilemap down`)

## Verification

1. `pnpm --filter frontend-game typecheck` clean
2. `pnpm --filter frontend-game test` 3/3 ✓ (existing iso-math tests still pass)
3. `pnpm --filter frontend-game build` clean, bundle ≤ 700 KB gzipped
4. `pnpm --filter frontend-game dev` boots on :5174
5. Playwright smoke `/play`:
   - Real Kenney grass tiles visible (not stub indigo diamond)
   - Player sprite at center
   - Click on a tile → Player walks there (tween animation)
   - `tilemap-service: ok` shown in HUD (with tilemap docker running)
6. Visual screenshot of working demo

## Risk register

| Risk | Mitigation |
|---|---|
| Kenney filenames don't match my guess | Wait for PO to drop pack + tell me filename |
| Kenney tiles are 128×128 PNG canvas but iso diamond inside has transparent corners — origin/anchor matters | Use `setOrigin(0.5, 0.5)` (center) and offset in worldToScreen accordingly |
| Player sprite not in pack | Use a placeholder colored circle for V0 Player (Kenney has separate character packs we can add later) |
| tilemap-service healthcheck fails in docker | Check `services/tilemap-service/Dockerfile` is current; rebuild if needed |
| Click event swallowed by React HUD overlay | Ensure `pointer-events:none` on overlay containers + `pointer-events:auto` only on actual interactive HUD elements (already set in PhaserGame.tsx) |
