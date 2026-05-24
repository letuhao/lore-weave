# Plan — Session C: frontend-game minimal scaffold + Phaser 4 validation gate

> **Spec:** `docs/specs/2026-05-24-frontend-game-architecture.md` (§11.1 — Phaser 4 production-readiness validation, MED-1 from prior /review-impl)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Size:** XL (validation gate ~14 files; full scaffold conditional ~+15 files in Phase 2)
> **PO decisions (this session):** (1) validation-gate-first approach — minimal scaffold for gate verification, full scaffold conditional on gate pass. (2) TypeScript `strict: true` + `noUncheckedIndexedAccess: true`. (3) After initial gate FAIL, research correct Phaser 4 GPU APIs instead of falling back to Phaser 3 LTS.
>
> **GATE OUTCOME 2026-05-24:** ✓ PASS (3/3) after 3 research-driven fixes — see Spec §11.1 inline notes. Phaser 4.1.0 accepted; no Phaser 3 fallback.

## Goal

**Phase 1 (this commit):** validate Phaser 4 + TilemapGPULayer + SpriteGPULayer + HMR work end-to-end in our Vite + React + TS strict stack. If gate fails, fall back to Phaser 3 LTS per spec §11.1.

**Phase 2 (next commit if gate passes):** expand to full frontend-game/ directory structure per spec §3.

## Why gate first

Spec §11.1: "Phaser 4.0.0 GA was 2026-04-10 — 6 weeks before this spec. `TilemapGPULayer` + `SpriteGPULayer` are NEW APIs. Historical pattern: major engine releases have 3-6 months of edge-case bug discovery." If we build the full scaffold first and later discover TilemapGPULayer is broken, we redo many files. Minimal gate-only setup keeps redo cost small.

## Validation gate criteria (spec §11.1, four items)

| # | Criterion | Pass evidence |
|---|---|---|
| 1 | WebGL2 context creates | Canvas element present; `canvas.getContext('webgl2')` returns truthy; Phaser scene `create()` fires |
| 2 | TilemapGPULayer renders 64×64 stub | Visible tilemap on screen; no `Cannot read property of undefined` in console |
| 3 | SpriteGPULayer renders 100 moving sprites | 100 sprites visible, animating; FPS counter ≥ 30 |
| 4 | HMR doesn't crash canvas on scene edit | Edit ValidationScene.ts → Vite HMR triggers → canvas either gracefully reloads (preferred) OR controlled full-page-reload (acceptable per spec §1 #3 AC-FG-14) |

**Plugin checks deferred:** RexUI / DragonBones / Spine — N/A for V0 per spec §1 #3 (React handles all UI; no skeletal animation V0).

**Pass = all 4 ✓. Fail = any ✗ → Phaser 3 LTS fallback (spec §11.1).**

## Files — Phase 1 (validation gate, ~11 files)

| # | File | Purpose |
|---|---|---|
| 1 | `frontend-game/package.json` | Workspace package; deps: `phaser@^4`, `react@^18`, `react-dom@^18`, `vite@^5`, `@vitejs/plugin-react`, `typescript@^5`, `tailwindcss@^3`, `autoprefixer`, `postcss` |
| 2 | `frontend-game/vite.config.ts` | Vite config: React plugin, port 5174 (spec AC-FG-3), HMR override for `src/game/**` |
| 3 | `frontend-game/tsconfig.json` | TS strict + noUncheckedIndexedAccess + path aliases (`@/*`, `@game/*`) |
| 4 | `frontend-game/tsconfig.node.json` | Separate tsconfig for vite.config.ts (Node context) |
| 5 | `frontend-game/index.html` | `<div id="root">` + `<div id="game-container">` |
| 6 | `frontend-game/src/main.tsx` | React entry; ReactDOM.createRoot |
| 7 | `frontend-game/src/App.tsx` | Single-page shell with `<PhaserGame>` + a status panel |
| 8 | `frontend-game/src/components/PhaserGame.tsx` | React-Phaser bridge (forwardRef + useLayoutEffect + StrictMode guard) |
| 9 | `frontend-game/src/game/main.ts` | Phaser.Game factory + config |
| 10 | `frontend-game/src/game/scenes/ValidationScene.ts` | All 4 gate checks in one scene; emits results to console + window.__validation |
| 11 | `frontend-game/tailwind.config.cjs` + `postcss.config.js` | Minimal Tailwind setup (matches frontend/) |

Plus skeletons-as-comments:
- `frontend-game/src/game/EventBus.ts` (1-line file: `export const EventBus = new Phaser.Events.EventEmitter();`)

## Files — Phase 2 (full scaffold, conditional on gate ✓)

Per spec §3 directory structure. NOT in this commit unless gate passes and we choose to bundle. Likely separate commit.

| Bucket | Files |
|---|---|
| `routes/` | login.tsx, world-select.tsx, play.tsx |
| `components/` | hud/, sidebar/, modal/, mobile/, shared/ skeletons |
| `game/scenes/` | Boot.ts, Preloader.ts, MainMenu.ts, World.ts (instead of just ValidationScene) |
| `game/entities/` | Player.ts stub |
| `game/systems/` | stubs |
| `game/state-machine/` | StateMachine.ts |
| `net/` | ws-client.ts stub, http-action.ts stub, protocol.ts stub |
| `store/` | game-store.ts (Zustand), ui-store.ts, net-store.ts, session-context.tsx |
| `api/` | tilemap-client.ts (TanStack Query) |
| `lib/` | iso-math.ts |
| `types/` | tilemap.ts, domain.ts |

## Verification (Phase 6 evidence)

For Phase 1:
1. `pnpm install` from repo root → adds frontend-game/ to lockfile, fetches Phaser 4 + React 18 + Vite 5
2. `pnpm --filter frontend-game build` → tsc clean + Vite bundles without errors
3. `pnpm --filter frontend-game dev` → Vite serves on `localhost:5174`
4. Open `http://localhost:5174` in browser → canvas visible + 4 gate criteria reported in console
5. Edit `src/game/scenes/ValidationScene.ts` (change a color) → HMR triggers, canvas updates or reloads cleanly

For browser smoke I'll provide concrete steps for the user to execute; I cannot visually inspect the canvas from CLI alone.

## Risk register

| Risk | Mitigation |
|---|---|
| Phaser 4 + Vite ESM interop bug | Spec §11.1 fallback Phaser 3 LTS — small redo cost in minimal scaffold |
| TilemapGPULayer API surface unstable | Use the most basic constructor signature; if it breaks, document + fall back |
| HMR crashes canvas | Per spec AC-FG-14, controlled full-reload is acceptable; document if encountered |
| `noUncheckedIndexedAccess` clashes with Phaser type defs | Phaser 4 types should be modern; if not, scope-disable in `tsconfig` for `src/game/**` (escape hatch) |
| pnpm peer-dep warnings | `.npmrc` has `auto-install-peers=true` default; should be quiet |

## Sequence

1. `pnpm add -F frontend-game ...` for all deps (single command)
2. Write config files (Vite, TS, Tailwind, postcss, index.html)
3. Write React entry (main.tsx, App.tsx, PhaserGame bridge)
4. Write Phaser entry (game/main.ts, scenes/ValidationScene.ts, EventBus.ts)
5. `pnpm --filter frontend-game build` — confirm TS strict + Vite produces no errors
6. `pnpm --filter frontend-game dev` — confirm dev server boots on :5174
7. Browser smoke: open `localhost:5174`, verify 4 gate criteria (user-driven step)
8. Self-review: walk file list, check TS strict compliance, confirm no console errors at boot
