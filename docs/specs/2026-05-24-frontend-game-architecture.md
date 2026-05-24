# Spec — frontend-game architecture (LoreWeave MMORPG client)

> **Status:** DESIGN 2026-05-24 + /review-impl hardening 2026-05-24. XL
> design task; spans 6 future BUILD sessions (A→F per §16). Branch
> `mmo-rpg/zone-map-amaw`.
> **Workflow:** v2.2 default (human-in-loop). PO requested /review-impl
> deeper adversarial review BEFORE spec commit — 9 MED + 5 LOW + 1
> COSMETIC findings; all 15 applied to this revision.
> **CLARIFY answers (PO, 2026-05-24, multi-round):** 11 load-bearing
> decisions consolidated in §1.
> **Sources:** research batch saved in this session (Phaser official template,
> Colyseus, Gabriel Gambetta prediction/reconciliation, Phaser 4 release notes).

---

## 1. Decision summary

Eleven load-bearing choices locked through PO Q&A this session:

| # | Decision | Choice |
|--:|---|---|
| 1 | Frontend topology | **Option A** — separate `frontend-game/` alongside existing `frontend/`, same monorepo, separate Vite project, separate Dockerfile, separate compose service |
| 2 | Game engine | **Phaser 4** (GA 2026-04-10, MIT license) — TilemapGPULayer + SpriteGPULayer are perfect for our iso tilemap render |
| 3 | UI integration | **Hybrid: React UI overlay + Phaser canvas** (DOM-sibling, NOT Phaser DOMElement). Apply to HUD, sidebar, inventory, modal. DOMElement reserved for world-anchored UI (nameplates) only |
| 4 | State management | **Zustand** for high-freq game state (synced from server, not owned) + **TanStack Query** for server state + **React Context** for stable session + **EventBus** for discrete events |
| 5 | Workspace mode | **pnpm workspace scoped to game subtree** (revised 2026-05-24 per PO pushback) — `pnpm-workspace.yaml` at repo root lists **only** `frontend-game/` + `packages/*`. `frontend/` is **NOT** in the workspace — keeps its existing npm tooling + lockfile + Dockerfile untouched. Zero risk to the live novel-workflow site. Rationale: Session A spec originally pulled `frontend/` in for shared `packages/i18n`, but inheriting cluster langs can be done via a one-time copy of language JSONs rather than a live extraction (see §12 revision). Workspace stays narrow until a real need to share runtime code appears. |
| 6 | Game model | **Turn-based combat + idle-MMO events** (NOT action MMORPG). Implication: NO client prediction / reconciliation / interpolation / input-buffer needed. Lower-frequency event model |
| 7 | Game server (V1+) | **Colyseus** locked (Node.js + TypeScript) despite being overkill for turn-based; convenience of built-in matchmaking + reconnection + room arch + Phaser SDK > minimalism |
| 8 | Target device | **Desktop + mobile landscape from V0** (MED-4 from /review-impl: 128×64 HD tiles + 375px portrait = ~3×6 visible tiles, practically unplayable). Mobile **landscape-lock** for V0; portrait deferred V2+ with separate 64×32 asset set. Touch controls + virtual gamepad scaffolded from day 1 |
| 9 | V0 placeholder assets | **Kenney.nl CC0 isometric pack** (10-20 sprites, MIT/CC0 license safe) |
| 10 | Tile dimensions | **Iso 2:1 dimetric, 128×64 px HD.** Continent 256² grid = camera + viewport scrolling required |
| 11 | Internationalization | **Inherit cluster langs (vi, en, ja, ko, zh, ...)** by one-time copy of `frontend/src/i18n/` language JSONs into `packages/i18n/` (NOT live extraction — decision #5 keeps `frontend/` out of the workspace). `packages/i18n` is standalone; if novel-workflow translation keys diverge from game keys, that's fine — they evolve independently. Phaser text uses React DOM overlay (NOT Phaser BitmapText — multi-language Unicode unfriendly) |

---

## 2. Stack + licenses (audit)

| Dep | Version | License | Use |
|---|---|---|---|
| `phaser` | `^4.0` | MIT | Canvas/WebGL game engine |
| `react`, `react-dom` | `^18.3` | MIT | UI overlay (matches existing `frontend/`) |
| `react-router-dom` | `^6` | MIT | Client-side routing (login → world-select → play) |
| `zustand` | `^5` | MIT | Reactive game state store |
| `@tanstack/react-query` | `^5` | MIT | HTTP server-state cache, retry, dedup |
| `colyseus.js` | `^0.16` | MIT | Game server SDK (V1+; not in V0 deps yet) |
| `tailwindcss` | `^3` | MIT | Styling (matches existing `frontend/`) |
| `shadcn` components | — | MIT (vendored copies) | Button/Dialog/Tooltip baseline |
| `typescript` | `^5` | Apache-2.0 | Type-safety |
| `vite` | `^5` | MIT | Dev + bundler |
| `vitest` | `^1` | MIT | Tests |
| `@testing-library/react` | `^14` | MIT | Component tests |

**No proprietary, no GPL, no SSPL.** Suitable for any commercial deployment.

---

## 3. Directory structure (full)

```
<repo-root>/
├── pnpm-workspace.yaml             (NEW: lists frontend-game, packages/* — NOT frontend)
├── package.json                    (NEW: minimal — pnpm workspace root, scoped to game subtree)
├── frontend/                       (EXISTING — fully untouched; keeps npm + own package-lock.json + own Dockerfile)
├── frontend-game/                  (NEW — this spec scaffolds it)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.cjs
│   ├── Dockerfile
│   ├── index.html                  <div id="root"> + <div id="game-container">
│   ├── public/assets/
│   │   ├── tiles/                  iso tile sprites (Kenney CC0)
│   │   ├── sprites/                characters, NPCs, props
│   │   ├── audio/                  SFX, BGM (deferred)
│   │   └── ui/                     icons for HUD/inventory
│   ├── src/
│   │   ├── main.tsx                React entry
│   │   ├── App.tsx                 React Router shell
│   │   ├── routes/                 ← URL → React view
│   │   │   ├── login.tsx
│   │   │   ├── world-select.tsx
│   │   │   └── play.tsx            (PhaserGame + HUD overlay)
│   │   ├── components/             ← React UI
│   │   │   ├── PhaserGame.tsx      Bridge (forwardRef + EventBus, ~50 LOC)
│   │   │   ├── hud/                HpBar, ManaBar, MiniMap, ActionBar
│   │   │   ├── sidebar/            Inventory, Chat, Party, Quest
│   │   │   ├── modal/              Settings, DialogChoice, Confirm
│   │   │   ├── mobile/             VirtualGamepad, MobileMenu, Drawer
│   │   │   └── shared/             Button, Tooltip, Icon (vendored shadcn)
│   │   ├── game/                   ← Phaser canvas code
│   │   │   ├── main.ts             Phaser Game config + scene list
│   │   │   ├── EventBus.ts         Single `new Events.EventEmitter()` (3 lines)
│   │   │   ├── config/             Constants (TILE_W=128, TILE_H=64, CAMERA_LERP, …)
│   │   │   ├── scenes/             ← Scene state machine
│   │   │   │   ├── BootScene.ts        config scale, minimal load
│   │   │   │   ├── PreloaderScene.ts   load all assets + progress bar
│   │   │   │   ├── MainMenuScene.ts
│   │   │   │   ├── WorldScene.ts       gameplay: render tilemap + control
│   │   │   │   └── HudScene.ts         optional Phaser-side HUD overlay
│   │   │   ├── entities/           ← Prefabs extending Phaser GameObjects
│   │   │   │   ├── Player.ts           extends Phaser.Physics.Arcade.Sprite
│   │   │   │   ├── Npc.ts
│   │   │   │   ├── ItemPickup.ts
│   │   │   │   └── IsoTile.ts
│   │   │   ├── systems/            ← Cross-cutting per-frame logic
│   │   │   │   ├── input-system.ts     keyboard + touch + virtual gamepad
│   │   │   │   ├── movement-system.ts  tile-by-tile movement
│   │   │   │   ├── camera-system.ts    follow target + lerp + viewport
│   │   │   │   └── iso-projection.ts   world↔screen coord math
│   │   │   ├── state-machine/      ← Reusable per-entity FSM
│   │   │   │   └── StateMachine.ts
│   │   │   └── data/               ← Static game data (later: fetched)
│   │   │       └── items.ts            placeholder item defs
│   │   ├── net/                    ← Networking layer (V0 = stubs)
│   │   │   ├── ws-client.ts            Colyseus SDK wrapper (V1+)
│   │   │   ├── http-action.ts          POST actions to game-server (V1+)
│   │   │   ├── protocol.ts             typed message unions
│   │   │   └── reconnect.ts            queue + retry while offline
│   │   ├── store/                  ← React-side state
│   │   │   ├── game-store.ts           Zustand: hp/mp/inventory (synced)
│   │   │   ├── ui-store.ts             Zustand: modal open, sidebar collapsed
│   │   │   ├── net-store.ts            connection state, latency, peers
│   │   │   └── session-context.tsx     React Context: user (stable)
│   │   ├── api/                    ← HTTP clients (TanStack Query)
│   │   │   ├── tilemap-client.ts       POST /v1/tilemaps/render
│   │   │   ├── auth-client.ts          (re-exports packages/auth-client)
│   │   │   └── query-keys.ts           central key factory
│   │   ├── lib/                    ← Pure utilities
│   │   │   ├── iso-math.ts             world↔screen coord conversion
│   │   │   └── seeded-rng.ts           mirror Rust if needed
│   │   ├── styles/
│   │   │   ├── globals.css
│   │   │   ├── overlay.css             z-index + pointer-events orchestration
│   │   │   └── responsive.css          breakpoints, mobile drawer
│   │   └── types/                  ← TS types shared React+Phaser
│   │       ├── tilemap.ts              mirror Rust TilemapView
│   │       └── domain.ts
│   └── tests/
│       ├── components/             Vitest + Testing Library
│       └── game/                   Phaser scene logic (where possible)
├── packages/                       (NEW)
│   ├── auth-client/                shared auth API + types (used by both frontends)
│   ├── api-types/                  TS mirrors of Rust/Go service contracts
│   ├── design-tokens/              Tailwind config + CSS vars + Phaser color palette
│   ├── i18n/                       one-time copy of frontend/src/i18n/ language JSONs (cluster langs); evolves independently going forward
│   └── shared-ui/                  (FUTURE — extract when ≥3 components duplicate AND frontend/ is also migrated into workspace)
└── services/                       (existing)
```

---

## 4. Communication architecture

### 4.1 React ↔ Phaser bridge (3 patterns)

```
┌─────────────────────────────┐
│  React components           │
│  (HUD, inventory, modal)    │
└────┬────────────────┬───────┘
     │                │
     │  EventBus      │  forwardRef
     │  (events)      │  (direct call)
     │                │
     ▼                ▼
┌─────────────────────────────┐
│  PhaserGame.tsx bridge      │
│  - forwardRef → { game, scene }
│  - listens 'current-scene-ready'
└─────────────────────────────┘
          │ EventBus
          ▼
┌─────────────────────────────┐
│  Phaser scenes              │
│  - EventBus.emit/on         │
│  - scene.events (intra-scene)
└─────────────────────────────┘
          │ Zustand.setState
          ▼
┌─────────────────────────────┐
│  Zustand stores             │
│  - game-store, ui-store     │
│  - React useStore() re-renders
└─────────────────────────────┘
```

**Direction matrix:**

| From → To | Mechanism | Use case |
|---|---|---|
| React → Phaser | `EventBus.emit('pause-game')` | Fire-and-forget commands |
| React → Phaser | `phaserRef.current.scene.method(arg)` | Synchronous call w/ return value |
| Phaser → React | `EventBus.emit('player-damaged', { hp })` | Discrete events |
| Phaser → React | `useGameStore.getState().setHp(50)` | High-freq state needing UI re-render |
| Phaser ↔ Phaser | `scene.events.emit/on` | Intra-scene/system communication |

### 4.2 Client ↔ Server protocol layering

| Layer | Protocol | When | What |
|---|---|---|---|
| HTTP | REST/JSON via `fetch` + TanStack Query | V0 + always | Login, char select, tilemap fetch, marketplace browse, turn-based combat actions |
| WebSocket | Colyseus client SDK | V1+ | Chat, presence, world events, push state updates |
| SSE | EventSource | V2+ option | Long-running activity completion (gather 5min → done event) |

**Auth handshake (V1+):**
- HTTP: cookie-based session (matches existing `auth-service`)
- WebSocket: cookie on same parent domain (loreweave.local + game.loreweave.local) OR signed token in connect payload
- Server validates → joins room → state sync begins

### 4.3 Game model implication — no client prediction needed

PO clarified game is turn-based + idle-MMO event-driven (not action MMORPG):

| Action MMORPG (NOT us) | Turn-based + idle (LoreWeave) |
|---|---|
| 60Hz tick + snapshot stream | Event-driven push, 0.1-2Hz |
| Client prediction mandatory | Not needed — turn-based natural pause |
| Server reconciliation w/ replay | Not needed — no snapshot stream |
| Position interpolation | Not needed — tile-by-tile discrete movement |
| Input sequence/buffer | Not needed — no rollback |

Result: `net/` layer is **dramatically simpler** than action MMORPG net code.
~5 files vs 15+ for a fighting/FPS engine.

---

## 5. State management hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│ Server state (TanStack Query)                                   │
│ - Tilemap (cached, deterministic)                                │
│ - Character profile (fetched on login)                           │
│ - Marketplace listings                                            │
└─────────────────────┬───────────────────────────────────────────┘
                      │ pushed via WS / pulled via HTTP
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ High-freq game state (Zustand)                                  │
│ - game-store: hp, mp, inventory, target  (SYNCED from server)   │
│ - ui-store:   modal open, sidebar collapsed (client-owned)      │
│ - net-store:  connection, latency, peers                         │
└─────────────────────┬───────────────────────────────────────────┘
                      │ Phaser scenes read via getState()
                      │ React components read via useStore()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ Discrete events (EventBus)                                       │
│ - 'player-damaged', 'item-picked', 'level-up'                    │
│ - Listeners on both sides; no re-render coupling                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Stable session (React Context)                                   │
│ - user, accessToken, locale                                       │
│ - Rarely changes; safe for Context (no high-freq re-render)     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Phaser-only state (scene fields)                                 │
│ - sprite x/y, animation frame, particle positions                │
│ - Updated 60fps in scene.update(); NEVER pushed to Zustand       │
└─────────────────────────────────────────────────────────────────┘
```

**Hard rule (CLAUDE.md "split by update frequency"):** state that React UI
must visually reflect → Zustand; state only used inside the render loop →
scene fields. **Don't duplicate.**

### 5.1 Scenarios not covered by the 5 tiers above (MED-5 from /review-impl)

| Scenario | Where it lives | Mechanism |
|---|---|---|
| **Optimistic UI + rollback** (drink potion → HP rises → server rejects) | Zustand store with `pending_actions` slice | Apply optimistic update immediately + push action to `pending_actions` queue. On server confirm: clear queue entry. On server reject: rollback (re-apply server snapshot or inverse op) + show toast |
| **Multi-step interaction state** (trade window, multi-tab form) | React component local state (`useState`) | Transient + scoped; lifts to Zustand only if abandoning the flow needs to remember progress |
| **Persistent UI prefs** (sidebar collapsed, audio volume) | Zustand + `persist` middleware → `localStorage` | `import { persist } from 'zustand/middleware'`; namespace key `loreweave-game-ui-prefs-v1` (version in key) |
| **Network error state** (WS dropped, request failed) | `net-store` with `connection: 'connected' / 'reconnecting' / 'offline'` + `last_error` | React reads to show "reconnecting..." banner; net layer dispatches transitions |
| **Bootstrap loading sequence** | TanStack Query suspense + EventBus progress events | Order: cookie validate → user fetch → character select → tilemap fetch → asset preload → Phaser scene start. Each step emits progress; React displays loading screen until done |

---

## 6. Scene state machine

```
┌──────┐    ┌────────────┐    ┌─────────────┐    ┌───────────┐
│ Boot │──▶ │ Preloader  │──▶ │ MainMenu    │──▶ │ World     │
└──────┘    └────────────┘    └─────────────┘    └─────┬─────┘
                                                       │
                                                       ▼
                                            ┌──────────────────┐
                                            │ Combat (overlay) │
                                            └──────────────────┘
```

| Scene | Lifecycle | Responsibilities |
|---|---|---|
| **Boot** | One-time, < 100ms | Configure scale manager, set up minimal config, load splash image |
| **Preloader** | One-time | Load all assets with progress bar (emit progress via EventBus → React-side splash UI) |
| **MainMenu** | Idle until user selects | Optional — V0 may skip; V1 menu UI mostly React |
| **World** | Long-running gameplay | Render tilemap (TilemapGPULayer), render entities (SpriteGPULayer), drive input/movement/camera systems |
| **Combat** | Overlay scene (runs on top of World, World paused) | Turn-based combat UI; React HUD shows action choices |

Phaser supports scene overlay via `scene.run('Combat')` — `World` remains
loaded but paused while `Combat` runs.

---

## 7. Layout + responsive design

### 7.1 Desktop (≥ 1024px wide)

```
┌──────────────────────────────────────────────────────────────┐
│ HUD top — HP, MP, buffs, level, currency       z=10 absolute │
├──────────────────────────────────────┬───────────────────────┤
│                                      │ Sidebar               │
│                                      │ - Inventory           │
│   <canvas>                           │ - Chat                │
│   Phaser game world                  │ - Party               │
│   (camera follow, iso tilemap)       │ - Quest               │
│   z=1                                │   (tabbed; ~320px)    │
│                                      │   z=10                │
├──────────────────────────────────────┴───────────────────────┤
│ Action bar — skills / items / menu                  z=10     │
└──────────────────────────────────────────────────────────────┘
   Modal layer (Settings, DialogChoice)                z=100
```

### 7.2 Mobile landscape (640-1023px wide)

```
┌──────────────────────────────────────────────────────────────┐
│ Compact HUD: HP/MP horizontal bar only            z=10       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   <canvas> (full width)                                      │
│                                                              │
│   Virtual gamepad: bottom-left  z=15  (touch)                │
│                                                              │
│   Action buttons: bottom-right  z=15  (touch)                │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Sidebar = drawer (slides in from right when tapped)    z=20  │
└──────────────────────────────────────────────────────────────┘
```

### 7.3 Mobile portrait — **DEFERRED V2+** (MED-4 from /review-impl)

Portrait layout at 375×667 with 128×64 HD tiles yields ~3×6 visible
tiles = unplayable. V0 forces **landscape-lock** on mobile via:

```html
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<link rel="manifest" href="/manifest.webmanifest">
<!-- manifest.webmanifest: "orientation": "landscape" -->
```

```typescript
// On mount in App.tsx
if (window.screen.orientation?.lock) {
  await window.screen.orientation.lock('landscape').catch(() => {
    // Locking fails outside PWA / fullscreen; show rotate prompt instead
  });
}
```

A `<RotatePrompt>` React component shows "Please rotate to landscape"
overlay when `window.matchMedia('(orientation: portrait)').matches` AND
viewport < 1024px. Player can dismiss but UI is degraded.

**V2+ portrait support** will require:
- Separate `assets/tiles-mobile/` 64×32 sprite set (re-export from Kenney source)
- Conditional asset preload based on `window.matchMedia('(max-width: 640px)')`
- Re-layout HUD per §7.3 original sketch (compact 3-row top + drawer sidebar)
- Touch target audit (44×44 minimum per Apple HIG, 48×48 Material)

### 7.4 CSS pointer-events orchestration

```css
#game-container {
  position: absolute; inset: 0; z-index: 1;
}

.react-hud-root {
  position: absolute; inset: 0; z-index: 10;
  pointer-events: none;  /* clicks pass to canvas by default */
}
.react-hud-root .interactive {
  pointer-events: auto;  /* HUD panels opt-in */
}

.virtual-gamepad {
  position: absolute; z-index: 15;
  pointer-events: auto;  /* touch always consumed by gamepad */
}

.modal-backdrop {
  position: fixed; inset: 0; z-index: 100;
  pointer-events: auto;  /* modals BLOCK canvas */
}
```

### 7.5 Phaser scale mode

```typescript
scale: {
  mode: Phaser.Scale.FIT,           // preserve aspect ratio (iso math sensitive)
  autoCenter: Phaser.Scale.CENTER_BOTH,
  width: 1280, height: 720,          // logical resolution (16:9 base)
}
```

`FIT` + `CENTER_BOTH` letterbox the canvas in its container. React HUD
wraps canvas in flexbox — when canvas letterboxes (e.g. portrait mobile),
React fills the surrounding space without distorting iso math.

---

## 8. Network architecture (phased)

```
V0:  Client ──HTTP──▶ tilemap-service (render endpoint)
                      auth-service     (login cookie)

V1:  Client ──HTTP──▶ ↑ (above)
       │
       └──WebSocket──▶ game-server (Colyseus)
                        - chat room
                        - presence room
                        - world events broadcast

V2:  Client ──HTTP──▶ ↑ (above)
       │
       ├──WebSocket──▶ game-server (Colyseus)
       │                + combat room (turn-based)
       │                + inventory state sync
       │
       └──SSE──────▶ activity-service (long-running task completion)

V3:  + marketplace, guild, matchmaking, persistent world events
```

**Auth handshake (V1+) — single-domain + path-routing (MED-8 from /review-impl):**

Rejected: cross-domain subdomain pattern (`app.loreweave.local` ↔
`game.loreweave.local`). Reasons: Safari ITP blocks cross-subdomain
cookies, `SameSite=None; Secure` requires HTTPS even in dev (mkcert
hassle), WebSocket cross-origin CORS preflight complexity, `/etc/hosts`
per-dev-machine maintenance.

Chosen: **single domain + path-based routing** via api-gateway-bff:

```
https://loreweave.com/app/*      → reverse proxy → frontend  (port 5173)
https://loreweave.com/game/*     → reverse proxy → frontend-game (port 5174)
https://loreweave.com/v1/*       → reverse proxy → backend services
wss://loreweave.com/ws/*         → reverse proxy → game-server (Colyseus)

Local dev: http://localhost:3001/{app,game,v1,ws}  via gateway dev mode
```

Auth flow:
1. User opens `/app` or `/game` → not logged in → redirect to `/app/login`
2. POST `/v1/auth/login` → `auth-service` sets `Session` cookie (`Path=/`,
   `SameSite=Lax`, `HttpOnly`, `Secure` in prod) — applies to ALL paths under
   `loreweave.com` automatically; **no cross-domain issues**
3. Subsequent request to `/game` includes cookie → game site renders
4. WebSocket upgrade `wss://loreweave.com/ws/world` includes cookie via
   `credentials: include` — gateway proxies upgrade to game-server which
   validates cookie via `/internal/validate`

**api-gateway-bff is the load-bearing piece** — it owns the routing
table and must be configured to proxy 4 path-prefixes correctly. WebSocket
upgrade specifically requires HTTP/1.1 `Upgrade: websocket` header
forwarding (not all reverse proxies do this by default; nginx + axum +
node http-proxy all support it with config).

**Local dev complication**: existing `frontend/` runs `npm run dev` (its
own toolchain — NOT pnpm) on `localhost:5173`. `frontend-game` will run
`pnpm --filter frontend-game dev` on `:5174`. api-gateway-bff dev mode
at `:3001` proxies both. Devs use `http://localhost:3001` as the single
entry point. The two frontends use different package managers; that's
intentional per §1 decision #5.

---

## 9. Design patterns (baked in from day 1)

1. **Scene state machine** — `scenes/` Boot → Preloader → MainMenu → World; clear lifecycle per scene
2. **Composition over inheritance** — entities extend Phaser GameObjects + mixin behaviors (Movable, Damageable); avoid deep class hierarchies
3. **Per-entity FSM** — `state-machine/StateMachine.ts`; Player.state = Idle / Walking / Casting / Stunned; transitions explicit
4. **Event-driven (Observer)** — EventBus + scene.events; combat-system emit `'damage-dealt'` → quest-system listens; loose coupling
5. **Object pooling** — projectiles, particles, damage numbers via `Phaser.GameObjects.Group`; no per-frame allocation
6. **Data-driven design** — `data/items.ts` defines stats; code renders generically; later fetched from backend
7. **Service locator (light)** — module singletons: `AudioService.play(id)`, `SaveService.checkpoint()`
8. **Separation of layers** — React = view + form UI; Phaser = canvas + game loop; no state duplication

### 9.1 Patterns omitted in first draft, added per /review-impl (MED-6)

9. **CQRS** (Command vs Query separation) — player actions = Commands (need idempotency keys, retry safety, audit). Data fetches = Queries (cacheable, repeatable, safe to dedupe). `net/protocol.ts` types these as distinct unions:
   ```typescript
   type Command = MoveCommand | AttackCommand | UseItemCommand; // each has client_seq + idempotency_key
   type Query   = GetInventory  | GetMarket      | GetCharacter;  // cacheable; TanStack Query handles
   ```
   Server treats Commands as transactional (validate → apply → broadcast → ack). Retry-safe: same idempotency_key → same outcome.

10. **Offline-first / network resilience** — turn-based + idle MMO actively benefits from offline play. Behavior when WebSocket disconnects:
    - Browsing UI (inventory, chat history, character sheet) — read from local Zustand cache, show "Offline" banner
    - Outgoing Commands — queue in `net-store.outbox`, retry on reconnect (idempotency_key prevents dupe)
    - Incoming events while offline — replayed by server on reconnect (server keeps last-N events per session)
    - Bounded queue: drop commands older than 60s with "action expired" toast

11. **React error boundary** — placed at each route + around `<PhaserGame>`:
    ```tsx
    <ErrorBoundary fallback={<RoutFallback/>}>
      <Routes>
        <Route path="/play" element={
          <ErrorBoundary fallback={<GameFallback/>}>
            <PhaserGame/>
          </ErrorBoundary>
        }/>
      </Routes>
    </ErrorBoundary>
    ```
    Inner boundary catches Phaser-adjacent React errors without nuking the whole site. Outer catches route-level. Phaser scene throws are NOT caught by React boundaries — must be wrapped in `try/catch` inside scene `update()` per Phaser team guidance.

12. **Cache invalidation policy (TanStack Query)** — explicit per-query:
    | Query | staleTime | gcTime | Invalidate on |
    |---|---|---|---|
    | tilemap (deterministic) | `Infinity` | `Infinity` | never |
    | character profile | `5 * 60_000` | `15 * 60_000` | combat end, level-up event |
    | inventory | `30_000` | `5 * 60_000` | item-pickup, trade, craft events |
    | marketplace | `10_000` | `2 * 60_000` | manual refresh |
    Invalidations triggered by EventBus listeners: `EventBus.on('combat-ended', () => queryClient.invalidateQueries({ queryKey: ['character'] }))`.

13. **Bootstrap sequence** — explicit order, owned by `App.tsx`:
    ```
    1. Cookie validate (HEAD /v1/auth/check)
       └─ Fail → /login
    2. User profile fetch (GET /v1/users/me)
       └─ Fail → /login
    3. Character select / create (GET /v1/characters/mine)
       └─ No character → /character-create
    4. Channel select (GET /v1/channels/mine)
       └─ No channel → /world-select
    5. Tilemap fetch (POST /v1/tilemaps/render)
    6. Asset preload (Phaser PreloaderScene)
    7. Phaser scene start (WorldScene)
    ```
    Each step emits EventBus progress events; React shows splash screen with progress until step 7.

---

## 10. Anti-patterns to avoid

1. ❌ **God scene** — one scene containing all logic. Split per concern (menu, world, combat)
2. ❌ **Deep entity class hierarchies** — `Character extends Entity extends GameObject`. Compose instead
3. ❌ **State duplication** between Zustand and scene fields. Rule: UI-visible → Zustand; render-loop only → scene
4. ❌ **`useEffect` running game logic** — 60fps loop in `useEffect` is a nightmare. Game logic in `scene.update()`
5. ❌ **Phaser DOMElement for HUD** — pointer-events hard to control, can't nest deep, perf worse than DOM sibling
6. ❌ **Hardcoded item/skill/enemy data** in code. Use data files (TS const V0, JSON-fetched later)
7. ❌ **Trusting client for combat/inventory state in V1+. Server is truth; client is hint.** V0 is single-player local — client-authoritative is FINE for V0; V1+ shared persistent world MUST be server-authoritative
8. ❌ **Phaser BitmapText for translatable strings** — Unicode + glyph baking nightmare. Use React DOM overlay for any text players read
9. ❌ **Implicit bootstrap order** (MED-6) — every call site re-derives the load sequence. Centralize in `App.tsx` per §9.1 #13
10. ❌ **No error boundary** (MED-6) — a single React render throw kills the canvas + UI. Place boundaries per §9.1 #11
11. ❌ **Per-frame React `setState` for canvas-tracked DOM** (LOW-10) — use `ref.current.style.transform` direct mutation; never `setState` in animation frame callback

---

## 11. Visual style + tile dimensions

- **Style:** iso 2:1 dimetric (matches tilemap-service render contract)
- **Tile size:** 128 × 64 px HD (PO choice — bigger sprites, easier to see characters)
- **V0 demo tier:** `ChannelTier::Town` 64×64 grid (LOW-14 from /review-impl) — lighter rendering, faster perceived load; Continent 256² reserved for V2+ performance validation
- **Tier dimensions** (match tilemap-service `GridSize` constants):
  - Continent: 256² = 65 536 tiles (`MAX_GRID_TILES` cap in tilemap-service)
  - Country: 192² = 36 864 tiles
  - District: 128² = 16 384 tiles
  - Town: 64² = 4 096 tiles (V0 default)
- **Viewport math** (with 128×64 HD tile at logical 1280×720 resolution):
  - Desktop 1920×1080 → ~15 × 17 tiles visible → camera scroll to navigate
  - Desktop 1280×720 → ~10 × 11 tiles visible
  - Mobile landscape 1280×720 → same as 1280 desktop
  - Mobile portrait — **landscape-locked** for V0 (see §7.3); V2+ adds 64×32 mobile asset set
- **Camera:** follow player with lerp; viewport scrolls smoothly

**Render path:** Phaser 4 `TilemapGPULayer` — single draw call regardless
of tile count; cost is per pixel on screen. Perfect for our 256² grid.

### 11.1 Phaser 4 production-readiness validation (MED-1 from /review-impl)

Phaser 4.0.0 GA was 2026-04-10 — 6 weeks before this spec. `TilemapGPULayer`
+ `SpriteGPULayer` are NEW APIs. Historical pattern: major engine releases
have 3-6 months of edge-case bug discovery.

**Validation gate at Session C** (scaffold) — MUST PASS before Session D.

> **GATE EXECUTED 2026-05-24 (Session C Phase 1) — PASS with 3 findings:**
>
> 1. **Phaser 4 + WebGL context** — ✓ Phaser 4.1.0 boots; WebGLRenderer
>    active. Original gate wording "WebGL 2.0 context" was incorrect:
>    Phaser 4 by design requests a WebGL 1.0 context (`canvas.getContext('webgl')`
>    at `phaser.esm.js:186435`) and polyfills WebGL 2 features via
>    extensions (ANGLE_instanced_arrays, OES_vertex_array_object,
>    OES_standard_derivatives — see `phaser.esm.js:186622-186644`).
>    Correct check: WebGLRenderer is active AND required extensions
>    are obtained. To force a true WebGL2 context, pre-create one and
>    pass via `game.config.context` — NOT needed for V0.
>
> 2. **TilemapGPULayer** — ✗ **N/A by design.** Phaser docs explicitly
>    state TilemapGPULayer is **orthographic-only** (`CHANGELOG-v4.0.0.md:549`:
>    "Orthographic tilemaps only — not suitable for isometric or hexagonal
>    maps"). Our game uses iso 2:1 dimetric per §1 #10, so TilemapGPULayer
>    can NEVER apply to our V0+ tilemap rendering. **Use standard
>    TilemapLayer for iso** — verified working in Session C Phase 1
>    (64×64 stub tilemap renders at 60 FPS). The earlier spec assumption
>    that TilemapGPULayer would optimize our tilemap was wrong; the
>    optimization is unavailable. Acceptable: standard TilemapLayer
>    handles 64² Town and 256² Continent (with culling) fine.
>
> 3. **SpriteGPULayer** — ✓ but requires `globalThis.Phaser = Phaser`
>    shim. Phaser 4.1.0's ESM bundle has internal code that references
>    the bare global `Phaser` identifier (e.g. `new Phaser.Structs.Map()`
>    at `phaser.esm.js:88604` inside SpriteGPULayer constructor; also
>    lines 33884/34948/34969 in render code). Without the shim, calling
>    `this.add.spriteGPULayer(...)` throws `"Phaser is not defined"`.
>    Workaround applied in `frontend-game/src/game/main.ts`:
>    `(globalThis as any).Phaser = Phaser;` before any scene boots.
>    Track upstream — remove shim once Phaser releases an ESM-clean
>    patch (likely 4.x.y).
>
> 4. **HMR** — deferred to user manual smoke (edit ValidationScene.ts,
>    confirm no canvas freeze). Acceptable per AC-FG-14: controlled
>    full-reload OK; silent freeze not.
>
> 5. **RexUI / DragonBones / Spine / Phaser Editor** — deferred / N/A
>    for V0 per spec §1 #3 (React handles all UI; no skeletal animation
>    until V2+).
>
> **Outcome:** Phaser 4.1.0 ACCEPTED for V0+. No Phaser 3 LTS fallback
> needed. Re-validate when Phaser ships 4.2+ in case the ESM shim can
> be removed.

Original gate criteria (kept for historical reference; replaced by
findings above):

1. ~~Boot Phaser 4 + render an empty scene → confirm WebGL context creates~~ → **Revised:** WebGLRenderer + WebGL2-equiv extensions present (Phaser 4 design intent — WebGL1 context with polyfills, NOT a true WebGL2 context)
2. ~~Render a `TilemapGPULayer` with a 64×64 stub tilemap (Town tier) → confirm no rendering bug~~ → **REMOVED:** TilemapGPULayer is orthographic-only; N/A for our iso pick. Use standard TilemapLayer; verified at 60 FPS.
3. Render a `SpriteGPULayer` with 100 sprites moving → confirm no jank — ✓ (with ESM shim)
4. HMR pass: edit a scene file, confirm hot-reload doesn't crash canvas (or document the known limitation)
5. RexUI plugin compatibility check (if we plan to use it) — at time of writing some 3rd-party plugins still v3-only

**If any gate fails:** declare Phaser 4 not ready, fall back to Phaser 3
LTS (Phaser team committed v3 LTS through 2027). Migration cost: low —
API differences for our scope (basic tilemap + sprites + scenes) are
minimal per migration guide.

**Audit list of plugins to verify at Session C:**
- RexUI (if needed for native UI components inside Phaser, e.g. text input) — N/A V0 per §1 #3
- DragonBones / Spine (only if we adopt skeletal animation, V2+)
- Phaser Editor v5 (PO mentioned in earlier research; "full Phaser 4
  support" but verify on actual project) — deferred

### 11.2 FX / post-processing strategy (COSMETIC-15 from /review-impl)

Phaser 4 unifies FX + masks into a Filter system. To avoid ad-hoc filter
spam later, predefine the FX vocabulary per use case:

| Filter | Use case | Phase |
|---|---|---|
| `Bloom` | Spell glow on cast / level-up effect | V1 |
| `Glow` | Highlight selected target / interactable object | V1 |
| `Blur` | Background dim when modal opens (canvas only) | V0 |
| `Shadow` | Drop shadow under sprites for depth perception | V0 |
| `ColorMatrix` | Biome ambience tint (cold blue tundra, warm sand desert) | V1 |
| `Wipe` | Scene transitions (World → Combat) | V1 |
| `Pixelate` | "Stunned" status visual feedback | V2 |

**Stacking budget**: max 2 active filters per game object simultaneously
(Phaser 4 supports unlimited but perf cost compounds). Filters on a Camera
apply to entire scene — used sparingly (biome tint OK; bloom-everywhere
NOT OK).

**FX = data-driven**: define a `FX_REGISTRY` keyed by named effects
(`'spell.cast.fire'`, `'status.stunned'`) → filter config. Code emits
`FX.play('spell.cast.fire', target)`. New effects = data entry, no code
change. Aligns with §9 pattern #6 (data-driven design).

---

## 12. i18n strategy

- **Seed source:** `frontend/src/i18n/` (existing — cluster langs: vi, en, ja, ko, zh, …) — one-time copy of language JSON files into `packages/i18n/` during Session B
- **Ownership going forward:** `packages/i18n/` is the SSOT for `frontend-game/` only; `frontend/` continues to own its own translations independently (revised per §1 decision #5 — workspace does NOT include `frontend/`)
- **Phaser text:** **DOM overlay only** — never Phaser BitmapText (multi-language Unicode requires per-glyph bake which is impractical for CJK)
- **Implementation:** any text players read (HUD labels, dialog, item names, NPC speech bubble) is rendered as React DOM over Phaser. NPC speech bubble = absolutely-positioned React component tracking the NPC's screen position via **direct `ref.current.style.transform = 'translate(x, y)'` mutation** in a per-frame callback registered with `Phaser.Scene.events.on('preupdate', ...)` (LOW-10 from /review-impl). **Do NOT use React `setState` for per-frame position updates** — 60fps `setState` × N visible bubbles causes reconciler thrash. CSS `will-change: transform` hints the compositor. The component renders ONCE (when bubble shows); only the `transform` mutates each frame.
- **What CAN stay in Phaser:** untranslated numeric/symbolic content — damage numbers, coordinates debug overlays, particle text effects (use Phaser Text with system font + emoji)

---

## 13. Asset pipeline

### V0 — Kenney.nl placeholder

| Source | Pack | Files |
|---|---|---|
| kenney.nl | Isometric Buildings | 10-20 tile sprites |
| kenney.nl | Isometric Characters | 5-10 character sprites |
| kenney.nl | Isometric Objects | 10-20 prop sprites |

**License audit per pack** (MED-9 from /review-impl): Kenney publishes
under multiple licenses across packs:

| License | Treatment |
|---|---|
| **CC0 1.0** (most common) | No attribution required; copy freely. Default expectation |
| **CC-BY** (rare; some donation packs) | Attribution required: "Kenney (kenney.nl) — CC-BY"; add to in-game credits scene + `frontend-game/LICENSES.md` |

**Required steps before adopting a pack:**

1. Open the pack's `License.txt` (always shipped with the download)
2. Confirm it says `CC0 1.0 Universal` OR `Creative Commons CC0`
3. If CC-BY: add the credit string to `frontend-game/LICENSES.md` AND
   render a "Credits" link in the main menu UI
4. Record license in `public/assets/PACKAGES.md` (per-pack provenance log)

### Asset folder convention

```
public/assets/
├── tiles/<biome>/<terrain>.png      e.g. tiles/grass/plain_01.png
├── sprites/<category>/<name>.png    e.g. sprites/character/wizard_01.png
├── atlases/<pack>.json + .png       texture atlases for perf
├── audio/<category>/<name>.ogg      SFX + BGM (V1+)
└── ui/<component>/<state>.png       icons, buttons (use shadcn where possible)
```

### Loading

- `PreloaderScene` loads atlases + sprites with progress bar
- Progress emitted via `EventBus.emit('preload-progress', pct)` → React splash UI
- After 100%, `EventBus.emit('preload-done')` → transition to `MainMenu` or `World`

---

## 14. Mobile + responsive

### Touch input

- `VirtualGamepad` React component (touch-only, hidden on desktop via CSS `@media`)
- Emits canonical input events on `EventBus`: `'input:move'`, `'input:action'`
- `input-system.ts` in Phaser scene listens — same listener handles keyboard input on desktop and gamepad input on mobile

### Responsive breakpoints (Tailwind defaults)

| Breakpoint | Range | Layout |
|---|---|---|
| `sm` | < 640px | Mobile portrait — drawer sidebar, virtual gamepad, compact HUD |
| `md` | 640–1023px | Mobile landscape — overlay sidebar, virtual gamepad, compact HUD |
| `lg` | 1024–1279px | Tablet/small desktop — fixed sidebar, keyboard primary |
| `xl` | ≥ 1280px | Desktop — full HUD + sidebar + action bar |

### Performance budget — per phase (MED-3 from /review-impl)

Original "2 MB asset bundle" was unrealistic. Re-budgeted per phase:

| Target | V0 | V1 | V2 | V3 |
|---|---|---|---|---|
| Initial JS+CSS bundle (gzip) | < 500 KB | < 700 KB | < 900 KB | < 1.2 MB |
| Initial asset bundle (bundled with app) | < 1 MB | < 1 MB | < 1 MB | < 1 MB |
| Lazy-loaded assets (per scene) | < 2 MB | < 5 MB | < 10 MB | CDN-served |
| Total assets over CDN | N/A | < 50 MB | < 200 MB | < 1 GB |
| First playable frame (after JS bundle download) | < 3 s on 4G mobile | < 4 s | < 5 s | < 5 s |
| Render frame budget | 16 ms (60fps) desktop, 33 ms (30fps) mobile | same | same | same |
| Memory | < 200 MB on mid-range mobile | < 300 MB | < 500 MB | < 800 MB |

**Why the original budget was wrong:** 128×64 PNG with iso transparency
~6-15 KB/tile. One character with 8 directions × 4 frames = 32 frames ≈
640 KB. V0 placeholder (1 character + 20 tiles + 20 props + UI) = ~1.2 MB
— already 60% of the original 2 MB cap before any real content.

**Asset compression strategy:**

- Default format: **WebP** (lossy, ~50% smaller than PNG; Phaser 4 supports
  via native browser texture loader)
- Fallback: PNG for browsers without WebP (Safari < 14, IE — both out
  of our support matrix per §18, so WebP-only is fine)
- Sprite atlases via `texturepacker` or Phaser CLI — pack many sprites
  into single PNG/WebP + JSON descriptor; reduces HTTP request count
- Audio: **Opus** in OGG container (~40% smaller than MP3); browsers
  support natively except old Safari (acceptable trade)

**CDN strategy (promoted from V2 to V1 prerequisite):**

V0 ships all assets bundled with the app via Vite's static asset
handling. V1+ adds:
- CloudFront / Cloudflare R2 / MinIO public bucket as asset origin
- Cache headers: `immutable` + content-hash filename (already standard via Vite)
- Asset URLs constructed via `import.meta.env.VITE_ASSET_CDN_URL`
- Fallback to same-origin (`/assets/...`) when CDN var unset (local dev)

---

## 15. Phased delivery

| Phase | Network | Features visible | Sessions |
|---|---|---|---|
| **V0** | HTTP only | Single-player explore: login → world select → fetch tilemap → walk around → camera follow → 1 React HUD panel mock | A-F (6 sessions per §16) |
| **V1** | + WebSocket (Colyseus) | See other online players in same channel; chat; presence; no combat | **15-25 sessions** (LOW-12 from /review-impl — revised from optimistic 5-10. V1 includes Colyseus server scaffolding + character-service backend Go service + WebSocket integration + presence + chat + reconnect + cross-service tests + /review-impl rounds) |
| **V2** | + Auth state sync | Turn-based combat (server-authoritative); HP/MP persisted; loot drops; inventory backed by backend | 20-30 sessions |
| **V3** | + SSE + matchmaking | Idle activities (gather, craft 5min); marketplace; guild; dynamic world events | Long-tail |

---

## 16. Session plan (A → F for V0)

| Session | Scope | Size | Output |
|---|---|---|---|
| **A** (this session) | This spec doc | M | `docs/specs/2026-05-24-frontend-game-architecture.md` |
| **B** | pnpm workspace setup (game subtree only) + `packages/{auth-client, api-types, design-tokens, i18n}` skeletons; **`frontend/` not touched** (revised 2026-05-24 per PO) | M | Session B-AC (revised): (1) `pnpm-workspace.yaml` at repo root lists ONLY `frontend-game`, `packages/*` — explicitly NOT `frontend`; (2) root `package.json` is pnpm workspace root, scoped to game subtree; (3) `packages/{auth-client,api-types,design-tokens,i18n}/package.json` + minimal `src/index.ts` skeletons present, each with `"private": true`, MIT, version `0.0.0`; (4) `packages/i18n/` contains a one-time copy of `frontend/src/i18n/` language JSONs (snapshot via git, NOT a live symlink); (5) `pnpm install` from repo root resolves without errors (a no-op until `frontend-game/` exists in Session C; the skeleton packages have no runtime deps yet); (6) `frontend/` is bit-for-bit unchanged — `git diff frontend/` is empty; existing `npm` workflow + `docker compose up frontend` still works |
| **C** | Scaffold `frontend-game/` full structure (folders, configs, Phaser+React bridge, scene state machine, EventBus, stores, net/ stubs, tests setup) | L | Scaffold compiles + 1 sanity test |
| **D** | V0 demo: Phaser hello-world (1 iso tile from Kenney CC0) + React HUD mock + fetch `tilemap-service` `/livez` via TanStack Query | M | Visible browser demo |
| **E** | WebSocket echo demo: minimal Rust/Node echo service + `frontend-game/net/` WS client demo (verify auth handshake + reconnect) | M | WS path validated end-to-end |
| **F** | Dockerfile + docker-compose entry for `frontend-game` (profile `[game, full]`); smoke `docker compose up` | M | Containerized + running on `localhost:5174` |

V0 done after F → unblocks V1 (Colyseus integration, real-time presence).

---

## 17. Backend services growth (forward-looking)

| Service | When needed | Lang | Status |
|---|---|---|---|
| `tilemap-service` | V0 | Rust | ✅ done |
| `auth-service` | V0 | Go | ✅ done |
| **`game-server`** | V1 | Node + Colyseus | ❌ — design when V1 opens |
| **`character-service`** | V1 | Go | ❌ |
| **`inventory-service`** | V2 | Go | ❌ |
| **`activity-service`** | V3 | TBD | ❌ |
| `chat-service` (exists for novel-workflow) | V1 | Python | ✅ — expand for game chat |

### 17.1 Colyseus migration trigger conditions (MED-2 from /review-impl)

PO accepted Colyseus despite overkill for turn-based + idle MMO. Re-evaluate
if any of these fire:

| Trigger | Action |
|---|---|
| **>100 active rooms** (persistent worlds, not match-based) per node | Re-evaluate Colyseus room arch vs custom session model |
| **State diff payload > 5 KB/s per client** | Colyseus binary delta sync is wasteful; consider raw WS + manual diff |
| **Need for Rust-only operations** (e.g. sharing types with `tilemap-service` workspace) | Migrate to Rust + axum-tungstenite |
| **Matchmaking unused after 3 months** | Trim Colyseus features, consider lighter framework |
| **Colyseus dep abandoned / security CVE unpatched** | Hard migration trigger |

**Migration cost estimate (Colyseus → Rust + axum-tungstenite):**
- Client SDK rewrite (serialization layer): ~1 week
- Server room → session model rewrite: ~2 weeks
- Schema → message-type rewrite: ~1 week
- Testing + integration: ~2 weeks
- **Total: ~6 weeks of focused dev** if triggered after V2

Mitigation: keep `net/` module abstract enough that Colyseus details don't
leak into game code. Specifically, `net/protocol.ts` defines typed message
shapes; `net/ws-client.ts` is the only file importing `colyseus.js`.
Migrating means rewriting `ws-client.ts` + protocol serialization, not
the entire net/ tree.

---

## 18. Acceptance criteria (for the V0 milestone after Sessions A-F)

| ID | Criterion |
|---|---|
| AC-FG-1 | `pnpm install` from repo root resolves `frontend-game/` + `packages/*` workspaces (revised — `frontend/` is NOT in the workspace per §1 decision #5) |
| AC-FG-2 | Existing `frontend/` continues to serve at `:5173` via its own `npm run dev` — bit-for-bit unchanged from before Session B (revised) |
| AC-FG-3 | `pnpm --filter frontend-game dev` serves new game site at `:5174` |
| AC-FG-4 | `frontend-game` opens with login page → world-select → play route navigation works |
| AC-FG-5 | `/play` renders Phaser canvas with 1 iso tile (Kenney CC0 placeholder) visible |
| AC-FG-6 | React HUD overlay shows mock HP/MP bars over the canvas |
| AC-FG-7 | EventBus bidirectional verified: React button click triggers Phaser scene method; Phaser emits `current-scene-ready` → React displays scene name |
| AC-FG-8 | TanStack Query fetches `tilemap-service/livez` and displays "tilemap-service: ok" |
| AC-FG-9 | WebSocket echo end-to-end: type → send → echo response → display |
| AC-FG-10 | Mobile responsive: shrink browser to 375px wide, layout adapts (drawer sidebar, virtual gamepad visible) |
| AC-FG-11 | `docker compose --profile game up frontend-game` builds + serves on `localhost:5174` |
| AC-FG-12 | All existing tests stay green; new tests cover bridge + EventBus + 1 store + 1 component |
| AC-FG-13 | **CORS** (LOW-11): fetch from `localhost:5174` → `localhost:8220/livez` succeeds in browser without CORS error; tilemap-service config adds `Access-Control-Allow-Origin: http://localhost:5174` for dev |
| AC-FG-14 | **HMR with Phaser** (LOW-11): edit a React HUD component → Vite HMR updates without canvas freeze. Edit a Phaser scene file → controlled full-reload triggered (NOT silent canvas freeze); `vite.config.ts` has `import.meta.hot.invalidate` rule for `src/game/scenes/**` |
| AC-FG-15 | **Build size** (LOW-11): `pnpm --filter frontend-game build` produces gzipped JS+CSS ≤ 700 KB (V0 budget per §14) |
| AC-FG-16 | **Browser compat** (LOW-11): smoke `play` route in Chrome (latest), Firefox (latest), Safari (≥14) — Phaser 4 WebGL2 detection works; no console errors |

---

## 19. Compliance check (vs CLAUDE.md)

| Rule | This spec |
|---|---|
| Contract-first | ✅ TanStack Query consumes `tilemap-service` per existing OpenAPI shape |
| Gateway invariant | ✅ All external HTTP routes via `api-gateway-bff` (when wired V1+); V0 direct hit on `tilemap-service` `localhost:8220` for dev |
| Provider gateway invariant | ✅ N/A — no LLM calls from `frontend-game` |
| Language rule | ✅ TypeScript matches gateway/BFF convention; Phaser is JS-family |
| No hardcoded secrets | ✅ All env via `import.meta.env.*` in Vite; runtime config injected at Docker build |
| No hardcoded model names | ✅ N/A |
| Each service owns its Postgres DB | ✅ N/A — frontend-game stateless client |
| Frontend MVC rules | ✅ Separation: routes (controllers) → context/store (services) → components (views); explicit |
| Multi-device support | ✅ Desktop + mobile equal per PO; auth cookie shared cross-device |
| No localStorage for user data | ✅ Server-state via TanStack Query; localStorage only for per-device UI prefs (sidebar collapsed, audio volume) |
| Hosting model — cloud | ✅ Stateless static SPA; deploys to CDN or `nginx` container |

---

## 20. Open questions deliberately deferred (V1+ concerns)

| # | Topic | Defer to |
|--:|---|---|
| 1 | Exact Colyseus room schema (player state shape) | V1 game-server design session |
| 2 | Combat data model (turn order, hit/miss math) | V2 combat design |
| 3 | Inventory grid vs list vs weight-based | V2 inventory design |
| 4 | Audio engine choice (Phaser built-in vs Howler) | V1 — first audio scope |
| 5 | Asset CDN vs bundled (V0 = bundled) | V2 — when asset count > 100 |
| 6 | PWA (offline asset cache, install) | V3 |
| 7 | Native mobile wrapper (Capacitor) | V4+ |
| 8 | Browser support matrix (just Chrome? Safari?) | V1 — first user testing |
| 9 | Analytics / telemetry | V2 |
| 10 | Accessibility audit (WCAG) | V2 |

---

## 21. PO sign-off checklist

- [ ] Eleven decisions in §1 reflect PO intent accurately
- [ ] Stack + licenses (§2) acceptable (Phaser 4 MIT, Colyseus MIT, Kenney CC0)
- [ ] Directory structure (§3) matches mental model — adjust before scaffold
- [ ] Hybrid React+Phaser communication (§4) is the right shape
- [ ] State management hierarchy (§5) matches CLAUDE.md "split by update frequency" rule
- [ ] Scene state machine (§6) — V0 strict (no Combat scene scaffolded)
- [ ] Mobile responsive layouts (§7) cover the cases PO cares about
- [ ] Network phasing (§8) — defer Colyseus until V1 is OK
- [ ] 8 design patterns (§9) + 8 anti-patterns (§10) — agree these are the right ones
- [ ] Iso 2:1 dimetric 128×64 (§11) confirmed
- [ ] i18n via React DOM overlay (NOT Phaser BitmapText) is acceptable (§12)
- [ ] Kenney.nl CC0 asset placeholder for V0 (§13)
- [ ] Performance budget targets (§14) realistic
- [ ] Phased delivery V0-V3 (§15) makes sense
- [ ] Session plan A-F (§16) — sized correctly
- [ ] Backend services growth (§17) acknowledged
- [ ] V0 acceptance criteria (§18) testable
- [ ] Deferred items (§20) — none of them are actually blocking V0
