# game-server

LoreWeave MMORPG game server. Node + TypeScript + Colyseus.

**Status:** V0 — single EchoRoom for Session E WS path validation.

**Future (V1+):**
- Real zone rooms (one room per active town/continent zone)
- Turn-based combat room (matches spec §1 #6)
- Chat room (global + party + zone-local)
- Schema state sync for player positions / vitals

## Run locally

```bash
cd services/game-server
npm install
npm run build
PORT=2567 LOREWEAVE_INTERNAL_TOKEN=dev_token npm start
```

Or via docker compose (from repo root):

```bash
docker compose --profile game up -d game-server
```

Then connect from the browser:

```js
import { Client } from 'colyseus.js';
const client = new Client('ws://localhost:2567');
const room = await client.joinOrCreate('echo', { jwt: 'dev_token' });
room.send('echo', { text: 'hello' });
room.onMessage('echo', (msg) => console.log(msg));
```

## Why Colyseus from V0

Per spec §1 #7 + §17: Colyseus is the locked V1 transport. PO chose to
bring it forward to V0 (this session) so the WebSocket wire protocol
matches prod from day 1. Migrating to raw WS later (per §17.1 trigger
conditions) would require rewriting both client and server transport
layers; using Colyseus now means only `net/ws-client.ts` would need
rewriting if we ever migrate off.

## Auth model (V0)

`EchoRoom.onAuth` accepts any non-empty `options.jwt` (dev token).
Real JWT verification against auth-service is V1+ scope. Session F
wires the dev token via `LOREWEAVE_INTERNAL_TOKEN` env into the
EchoRoom's onAuth check.

## Reconnect model (V0)

Colyseus rooms support `client.consumeSeatReservation(reconnectToken)`
to resume a session after temporary disconnect. EchoPanel UI in
frontend-game/ stores the token in localStorage and offers a Reconnect
button when the connection drops.
