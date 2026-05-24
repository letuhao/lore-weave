# Plan — Session C Phase 2: full frontend-game scaffold per spec §3

> **Spec:** `docs/specs/2026-05-24-frontend-game-architecture.md` (§3 directory structure, §16 Session C)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Size:** XL (~45 files; skeleton-heavy)
> **Predecessor:** Session C Phase 1 (commit 0845e723) — Phaser 4.1.0 validation gate ✓ 3/3 in real browsers

## Goal

Lay down full directory structure per spec §3 so Sessions D/E/F have concrete places to put HUD code, scene logic, WS client, and Docker entry. Most files are skeleton stubs with comment blocks pointing to their future session. A few utilities (iso-math, seeded-rng) get real implementations since they're pure math.

Replace `ValidationScene` (Phase 1) with proper `Boot → Preloader → MainMenu → World → Hud` scene chain. World scene renders 1 iso tile via `lib/iso-math.ts` so visual smoke confirms the scaffold actually works.

## Deps to add

- `react-router-dom@^6` — routes (login → world-select → play)
- `zustand@^5` — high-freq game state (per spec §1 #4)
- `@tanstack/react-query@^5` — server-state cache (per spec §1 #4)
- `vitest@^1`, `@testing-library/react@^16`, `jsdom` — test setup (devDeps)

NOT added (deferred):
- `colyseus.js` — V1+ per spec §15
- `i18next` — Session D when HUD ships actual strings

## File inventory (~45 files)

### Routes (3)
- `src/routes/login.tsx` — placeholder form
- `src/routes/world-select.tsx` — placeholder list
- `src/routes/play.tsx` — `<PhaserGame>` + HUD overlay slot

### Components (5 categories — ~10 files)
- `src/components/PhaserGame.tsx` — KEEP from Phase 1, adapt onStatus → onSceneReady event
- `src/components/hud/HpBar.tsx`, `hud/ManaBar.tsx`, `hud/index.ts`
- `src/components/sidebar/Sidebar.tsx`
- `src/components/modal/Modal.tsx`
- `src/components/mobile/VirtualGamepad.tsx`, `mobile/RotatePrompt.tsx` (per spec §7.3 landscape-lock)
- `src/components/shared/Button.tsx`

### Game (~15 files)
- `src/game/main.ts` — KEEP, add scene list (Boot→Preloader→MainMenu→World→Hud), keep `globalThis.Phaser` shim
- `src/game/EventBus.ts` — KEEP, expand event types
- `src/game/config/constants.ts` — TILE_W=128, TILE_H=64, etc.
- `src/game/scenes/BootScene.ts` — scale config + minimal load
- `src/game/scenes/PreloaderScene.ts` — placeholder progress bar
- `src/game/scenes/MainMenuScene.ts` — placeholder
- `src/game/scenes/WorldScene.ts` — minimal iso tile render (replaces ValidationScene)
- `src/game/scenes/HudScene.ts` — optional Phaser-side HUD (placeholder)
- `src/game/entities/Player.ts`, `entities/Npc.ts`, `entities/ItemPickup.ts`, `entities/IsoTile.ts`
- `src/game/systems/input-system.ts`, `systems/movement-system.ts`, `systems/camera-system.ts`, `systems/iso-projection.ts`
- `src/game/state-machine/StateMachine.ts` — generic FSM (small real implementation)
- `src/game/data/items.ts` — placeholder item defs

### Net (4 stubs)
- `src/net/ws-client.ts`, `net/http-action.ts`, `net/protocol.ts`, `net/reconnect.ts`

### Store (4)
- `src/store/game-store.ts` — Zustand game state stub
- `src/store/ui-store.ts` — Zustand UI state stub
- `src/store/net-store.ts` — Zustand network state stub
- `src/store/session-context.tsx` — React Context for session

### API (3)
- `src/api/tilemap-client.ts` — TanStack Query hook stub for `/tilemaps/render`
- `src/api/auth-client.ts` — re-exports `@loreweave/auth-client`
- `src/api/query-keys.ts` — central key factory

### Lib (2 — real implementations)
- `src/lib/iso-math.ts` — world↔screen iso coord conversion
- `src/lib/seeded-rng.ts` — deterministic PRNG (mirror Rust)

### Styles (3)
- `src/styles/globals.css`, `styles/overlay.css`, `styles/responsive.css`
- Move existing `src/index.css` content into globals.css

### Types (2)
- `src/types/tilemap.ts` — placeholder, will mirror Rust contract in Session D
- `src/types/domain.ts` — Player, Npc, Item, etc. domain types

### App + entry (2)
- `src/App.tsx` — rewrite from validation harness → Router shell (Login/WorldSelect/Play routes)
- `src/main.tsx` — KEEP, add TanStack QueryClientProvider + RouterProvider

### Public/assets dirs (4 placeholders)
- `public/assets/tiles/.gitkeep`
- `public/assets/sprites/.gitkeep`
- `public/assets/audio/.gitkeep`
- `public/assets/ui/.gitkeep`

### Tests setup (2)
- `vitest.config.ts`
- `tests/lib/iso-math.test.ts` — 1 sanity test verifying iso math round-trip

### REMOVE
- `src/game/scenes/ValidationScene.ts` — its purpose was Phase 1 gate; Boot→World now serves the same visual-smoke role

## Verification

1. `pnpm install` from repo root → resolves new deps cleanly
2. `pnpm --filter frontend-game typecheck` → clean
3. `pnpm --filter frontend-game build` → clean, bundle ≤ 700KB gzipped (V0 budget)
4. `pnpm --filter frontend-game test` → 1 sanity test passes (iso-math round-trip)
5. `pnpm --filter frontend-game dev` → boot on :5174, no console errors, /play route renders 1 iso tile
6. Router smoke: `/login` → `/world-select` → `/play` navigation works
7. Visual smoke (handed to user): `/play` shows Phaser canvas + 1 iso tile

## Risk register

| Risk | Mitigation |
|---|---|
| react-router-dom v6 has different API from v5 | Use BrowserRouter + Routes pattern (v6 canonical) |
| Zustand store boilerplate too heavy for stub | Use minimal `create((set) => ({ ... }))` shells |
| TanStack QueryClient required even for stub | Wrap in `main.tsx`; queries are stubs returning empty |
| Visual smoke breaks because PhaserGame depends on validation gate flow | Strip PhaserGame down to "mount canvas + emit ready event"; no validation status props |
| Bundle size blow-up from adding 3 large deps | react-router-dom ~25KB, zustand ~3KB, react-query ~50KB gzipped — should keep under 700KB total |
| TS strict + noUncheckedIndexedAccess clashes with stub code | Use explicit undefined-handling or `// @ts-expect-error TODO Session D` comments where futile |

## Sequence

1. Add deps via `pnpm add -F frontend-game ...`
2. Write `lib/iso-math.ts` + `lib/seeded-rng.ts` (real, will be used by World scene)
3. Write `game/config/constants.ts` (TILE_W/H + other shared constants)
4. Write new scene files: Boot, Preloader, MainMenu, World, Hud (delete ValidationScene)
5. Update `game/main.ts` to register new scene chain
6. Write entities/systems/state-machine/data stubs
7. Write net/store/api stubs
8. Write components/{hud,sidebar,modal,mobile,shared} stubs
9. Write routes + new App.tsx + new main.tsx (Router + QueryProvider)
10. Write styles (move index.css → globals.css)
11. Write types stubs
12. Write vitest config + 1 iso-math test
13. Build + typecheck + test + dev server smoke
14. Self-review: scaffold compiles, /play visually renders, 1 test passes
