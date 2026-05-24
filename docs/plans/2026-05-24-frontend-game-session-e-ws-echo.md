# Plan — Session E: WebSocket echo demo (full Colyseus stack)

> **Spec:** `docs/specs/2026-05-24-frontend-game-architecture.md` (§16 Session E, §17 game-server scheduled V1 — brought forward to V0 per PO this session, §1 #7 Colyseus locked)
> **Branch:** `mmo-rpg/zone-map-amaw`
> **Size:** XL (~14 files including new Node service)
> **Predecessor:** Session D (commit fbfb93cf) — V0 demo end-to-end working with tilemap-service

## Goal

Validate the full WebSocket path that V1 will rely on:
- Real Colyseus server (Node + TypeScript + @colyseus/core 0.16)
- Real colyseus.js client connecting from browser
- Auth handshake via Colyseus `onAuth` hook (dev token for V0)
- Reconnect via Colyseus built-in `reconnectionToken` + `Client.consumeSeatReservation`

PO chose full Colyseus stack from V0 (vs raw WS) so the V0 demo matches
production wire protocol — when V1 game logic (rooms, state sync, chat)
starts, the transport is already proven.

## Stack decision rationale

| Option | Pick? | Why |
|---|---|---|
| Full Colyseus (Node server + colyseus.js client) | **✓ PO pick** | Matches spec §1 #7 + §17 V1 plan. Prod wire protocol from day 1. Built-in auth handshake + reconnect. |
| Raw WS (Rust server + browser WebSocket client) | ✗ | Smaller V0, but two transport rewrites required by V1 (server-side: Rust → Node + Colyseus, client-side: raw WS → colyseus.js). |
| External wss://echo.websocket.org | ✗ | No auth handshake — fails spec §16 Session E AC |

## File inventory (~14 files)

### New service: `services/game-server/` (Node + TypeScript)

| # | File | Purpose |
|---|---|---|
| 1 | `services/game-server/package.json` | Node 20+, TypeScript, colyseus 0.16 |
| 2 | `services/game-server/tsconfig.json` | Strict, ESM output |
| 3 | `services/game-server/Dockerfile` | Multi-stage Node 20 alpine, prod-only deps |
| 4 | `services/game-server/.dockerignore` | Exclude node_modules + dist |
| 5 | `services/game-server/src/index.ts` | Express + listen helper + register EchoRoom |
| 6 | `services/game-server/src/rooms/EchoRoom.ts` | onAuth (dev token check) + onMessage('echo') (echo back) |
| 7 | `services/game-server/README.md` | Run instructions + future Colyseus room growth |

### Modified compose

| 8 | `infra/docker-compose.yml` | + game-server entry, port 2567 (standard Colyseus), profile [game, full], LOREWEAVE_INTERNAL_TOKEN env |

### Frontend WS client + UI

| 9 | `frontend-game/package.json` | + colyseus.js@^0.16 |
| 10 | `frontend-game/src/net/ws-client.ts` | REWRITE: real Colyseus.Client wrapped in WsClient interface |
| 11 | `frontend-game/src/components/echo/EchoPanel.tsx` | NEW: text input + send button + scrollable response list, connect/disconnect/reconnect status |
| 12 | `frontend-game/src/routes/play.tsx` | + `<EchoPanel />` overlay |

### Docs

| 13 | `docs/plans/2026-05-24-frontend-game-session-e-ws-echo.md` | This file |
| 14 | `docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md` | Update |

## Server design

### EchoRoom

```typescript
class EchoRoom extends Room {
  // V0 auth: any non-empty jwt accepted. Session F+ wires real verify.
  onAuth(_client, options) {
    if (!options?.jwt) throw new ServerError(401, 'missing jwt');
    return { userId: options.userId ?? 'guest' };
  }

  onCreate() {
    this.onMessage('echo', (client, message) => {
      client.send('echo', {
        original: message,
        receivedAt: Date.now(),
        echoedBy: 'EchoRoom',
      });
    });
  }
}
```

### Server config

- Port: 2567 (Colyseus default — exposed as host port 2567)
- Transport: built-in WebSocketTransport (Colyseus 0.16+ ships it as the default)
- Monitor: skip (V0+1)

## Client design

### WsClient impl (replaces stub)

```typescript
import { Client, Room } from 'colyseus.js';

export function createWsClient(): WsClient {
  let room: Room | null = null;
  let handlers = new Set<(msg: ServerToClient) => void>();

  return {
    connect: async (url, jwt) => {
      const client = new Client(url);
      room = await client.joinOrCreate('echo', { jwt });
      room.onMessage('*', (type, payload) => {
        for (const h of handlers) {
          h({ kind: 'world-event', eventId: type as string, payload });
        }
      });
      // Persist reconnect token for /reconnect path
      localStorage.setItem('lw_reconnect_token', room.reconnectionToken);
    },
    send: (msg) => {
      if (!room) throw new Error('not connected');
      room.send(msg.kind, msg);
    },
    on: (handler) => {
      handlers.add(handler);
      return () => handlers.delete(handler);
    },
    disconnect: () => {
      room?.leave();
      room = null;
    },
  };
}
```

### EchoPanel UI

Bottom-right of /play overlay:
- Connection status indicator (dot color: gray=disconnected, yellow=connecting, green=connected, red=error)
- Text input + Send button
- Scrolling response list (last 10 messages)
- "Reconnect" button when disconnected

## Auth handshake verification

1. Client `Client(url)` + `joinOrCreate('echo', { jwt: 'dev_token' })`
2. Server `onAuth(client, { jwt: 'dev_token' })` returns user object
3. If jwt missing → server throws `ServerError(401)` → client receives error
4. **Smoke**: connect with empty jwt → expect error event

## Reconnect verification

1. Client connects, receives reconnectionToken
2. Stop game-server container
3. Client emits `disconnect` event
4. Restart game-server container
5. Client uses stored token via `client.reconnect(token)` → resumes session
6. **Smoke**: kill container mid-session → verify client reconnects without losing state

## Verification (Phase 6 evidence)

1. `pnpm --filter frontend-game typecheck` clean
2. `pnpm --filter frontend-game test` 3/3 ✓
3. `pnpm --filter frontend-game build` clean, bundle ≤ 700 KB gzipped (+ ~50 KB for colyseus.js dep)
4. `cd services/game-server && npm run build` clean
5. `docker compose --profile game up -d game-server` → starts, healthchecks pass
6. `docker compose --profile game logs game-server` → "listening on 2567"
7. Playwright `/play` smoke:
   - EchoPanel shows "connected" after navigate
   - Type "hello" → send → response appears: `{"original":{"kind":"echo","text":"hello"},...}`
   - `docker compose stop game-server` → EchoPanel shows "disconnected"
   - `docker compose start game-server` → EchoPanel shows "reconnected" within 5s

## Risk register

| Risk | Mitigation |
|---|---|
| colyseus 0.16 API differs from older docs | Read installed package's TypeScript types via node_modules/.pnpm/colyseus@0.16/... |
| ws-transport not auto-loaded in 0.16 | Explicitly `import { WebSocketTransport } from '@colyseus/ws-transport'` if needed |
| Bundle size blow-up from colyseus.js (~50 KB gzip) | Acceptable: under V0 budget 700 KB gzip total |
| StrictMode double-connect leaks rooms | useEffect cleanup must `room.leave()` |
| CORS: WS connections don't preflight, but Colyseus matchmaking HTTP endpoint does | Need to add CORS to Colyseus Express app — `server.express.use(cors())` |
| Docker healthcheck for WS service | Colyseus exposes HTTP `/matchmake` endpoint; healthcheck wget that |
| localStorage reconnect token across page reloads vs new tab confuses Colyseus | OK for V0 single-tab; warn in EchoPanel if reconnect fails |
