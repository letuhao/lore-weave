# frontend-game

LoreWeave MMORPG client. Hybrid **React UI overlay** + **Phaser 4 canvas**.

Per spec [`docs/specs/2026-05-24-frontend-game-architecture.md`](../docs/specs/2026-05-24-frontend-game-architecture.md).

## Status

**V0 milestone COMPLETE.** All 16 AC-FG-* from spec §18 verified end-to-end.

## Run

### Full V0 demo (one command)

From repo root:

```bash
docker compose --profile full up
# Open http://localhost:5174/play
```

Boots all 3 services:
- `frontend-game` (nginx :5174) — this app
- `tilemap-service` (Rust :8220) — procedural tilemaps (V0 only smokes `/livez`)
- `game-server` (Node + Colyseus :2567) — WebSocket multiplayer (V0 only EchoRoom)

### Dev (hot-reload)

```bash
# Terminal 1 — start backends
docker compose --profile full up tilemap-service game-server

# Terminal 2 — start Vite dev server
pnpm install
pnpm --filter frontend-game dev
# → http://localhost:5174
```

### Tests

```bash
# Unit tests (Vitest)
pnpm --filter frontend-game test           # 3 tests (iso-math round-trip)

# Cross-browser e2e smoke (Playwright)
pnpm --filter frontend-game e2e:install    # one-time: install browser binaries
pnpm --filter frontend-game e2e            # chromium only (fast)
pnpm --filter frontend-game e2e:all-browsers  # chromium + firefox + webkit
```

### Build

```bash
pnpm --filter frontend-game build          # → frontend-game/dist/
# Bundle: ~484 KB gzipped (under V0 budget 700 KB per AC-FG-15)
```

## Architecture (V0)

```
src/
├── main.tsx                 React entry + QueryClientProvider + Router + SessionProvider
├── App.tsx                  Router shell (login → world-select → play)
├── config/services.ts       Centralized service URLs (V1 env-var injection lands here)
├── routes/                  3 pages — login, world-select, play
├── components/
│   ├── PhaserGame.tsx       React ↔ Phaser bridge
│   ├── hud/                 HpBar, ManaBar (Zustand-driven)
│   ├── sidebar/             Sidebar placeholder
│   ├── modal/               Modal scaffolding
│   ├── mobile/              RotatePrompt (landscape-lock), VirtualGamepad
│   ├── shared/              Button (shadcn-style)
│   └── echo/EchoPanel.tsx   Session E WS demo UI
├── game/                    Phaser-side code
│   ├── main.ts              Game factory + globalThis.Phaser shim (see Quirks below)
│   ├── EventBus.ts          Typed scene ↔ React event bus
│   ├── config/constants.ts  TILE_W=128, TILE_H=64, DEFAULT_ZONE_*
│   ├── scenes/              Boot → Preloader → MainMenu → World → Hud
│   ├── entities/            Player (real walkTo with boundary check), Npc/IsoTile stubs
│   ├── systems/             input-system, movement-system, camera-system, iso-projection
│   ├── state-machine/       Generic FSM
│   └── data/items.ts        Static placeholders (V1: server-fetched)
├── net/                     ws-client (colyseus.js), protocol typed unions, http-action stub, reconnect queue
├── store/                   Zustand × 3 (game/ui/net) + SessionProvider
├── api/                     tilemap-client (useTilemapHealth), auth-client re-export, query-keys factory
├── lib/                     iso-math (real), seeded-rng (Mulberry32)
├── styles/                  globals + overlay + responsive CSS
└── types/                   tilemap + domain TS shapes
```

## V0 capabilities

- **Iso tilemap rendering** — 8×8 Kenney CC0 grass cubes via `lib/iso-math.ts` (128×64 dimetric)
- **Click-to-walk Player** — canvas pointer → `screenToTile` → EventBus → `Player.walkTo` tween (with bounds check)
- **HUD overlay** — HP/MP bars driven by Zustand `game-store`
- **TanStack Query** — polls `tilemap-service/livez` every 10s
- **WebSocket echo** — Colyseus client connects to `game-server/EchoRoom`, sends/receives messages, handles disconnect + reconnect
- **Responsive** — landscape-lock on mobile (RotatePrompt overlay <700px portrait), VirtualGamepad
- **Routing** — React Router v6 (`/login`, `/world-select`, `/play`)

## Phaser 4 quirks (saved to project memory)

`src/game/main.ts` includes a `globalThis.Phaser = Phaser` shim required because Phaser 4.1.0's webpack-bundled ESM still references the bare global `Phaser` identifier internally (`new Phaser.Structs.Map()` etc.). Remove this shim when Phaser ships an ESM-clean patch.

`TilemapGPULayer` is **orthographic-only** per Phaser docs — we use iso 2:1 dimetric, so standard `Tilemap.createLayer` is the path. The spec originally planned to use GPU layer for optimization; corrected during Session C Phase 1.

WebGL: Phaser 4 deliberately requests a **WebGL 1.0 context with extensions** (ANGLE_instanced_arrays, OES_vertex_array_object, OES_standard_derivatives) and polyfills WebGL 2 features on top. `gl.getParameter(gl.VERSION)` reports "WebGL 1.0" even in real Chrome/Edge — by design, not a fallback.

## Environment variables (build-time, Vite VITE_*)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_TILEMAP_SERVICE_URL` | `http://localhost:8220` | Used by `useTilemapHealth` + future render endpoints |
| `VITE_GAME_SERVER_URL` | `ws://localhost:2567` | colyseus.js Client URL |
| `VITE_INTERNAL_TOKEN` | `dev_internal_token` | V0 dev auth token (sent to EchoRoom.onAuth). **V1 replace with auth-service JWT** — this bundles into client JS visible in DevTools. |

## V1+ scope (NOT in this repo yet)

Per spec §17:
- Real game rooms (ZoneRoom, CombatRoom, ChatRoom) replacing EchoRoom
- `character-service` (Go) backend
- JWT auth handshake against `auth-service` (replaces dev token)
- `tilemap-service` POST `/v1/tilemaps/render` integration (currently only `/livez` smoked)
- Colyseus Schema for player state sync
- Combat data model, inventory, audio, i18n actually wired, PWA, CDN deploy

## Workspace deps

This package consumes 4 `@loreweave/*` workspace packages from `packages/`:
- `@loreweave/auth-client` — re-exported via `src/api/auth-client.ts`
- `@loreweave/api-types` — TS mirrors of Rust/Go service contracts
- `@loreweave/design-tokens` — shared Tailwind preset + color palette
- `@loreweave/i18n` — translations (4 locales seeded from `frontend/`)

The novel-workflow `frontend/` is **outside** the pnpm workspace and stays independent on npm (per PO scope decision Session B).
