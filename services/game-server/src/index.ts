import { createServer } from 'http';
import express from 'express';
import cors from 'cors';
import { Server } from 'colyseus';
import { WebSocketTransport } from '@colyseus/ws-transport';
import { EchoRoom } from './rooms/EchoRoom.js';
import { assertWsAuthConfig } from './ws/auth.js';

// Entry: Express HTTP (for matchmake + health) + Colyseus WS attached.
//
// V0 ships only EchoRoom for Session E WS path validation. V1+ registers
// real zone/combat/chat rooms per spec §17.

const PORT = Number(process.env.PORT ?? 2567);
const CORS_ORIGINS = (process.env.LOREWEAVE_CORS_ORIGINS ?? 'http://localhost:5174')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const app = express();

// CORS for matchmake HTTP endpoint (Colyseus client hits POST /matchmake/<room>
// before opening the WS — that HTTP request needs CORS allow-origin).
app.use(cors({ origin: CORS_ORIGINS }));
app.use(express.json());

// Liveness probe — non-Colyseus, always returns 200 if the process is up.
app.get('/livez', (_req, res) => {
  res.json({ status: 'ok', endpoint: 'livez', service: 'game-server' });
});

const httpServer = createServer(app);

const gameServer = new Server({
  transport: new WebSocketTransport({ server: httpServer }),
});

gameServer.define('echo', EchoRoom);

// Fail-closed (077 review HIGH-2): refuse to start a PUBLIC listener that would
// fall back to static dev_token auth in production (no shared Redis ticket store).
assertWsAuthConfig();

gameServer.listen(PORT).then(() => {
  // eslint-disable-next-line no-console
  console.log(`[game-server] listening on :${PORT}`);
  // eslint-disable-next-line no-console
  console.log(`[game-server] CORS allowed origins: ${CORS_ORIGINS.join(', ')}`);
});

// Graceful shutdown so docker stop doesn't leave hanging sockets.
const shutdown = (signal: string): void => {
  // eslint-disable-next-line no-console
  console.log(`[game-server] received ${signal}, shutting down...`);
  gameServer.gracefullyShutdown().then(() => {
    process.exit(0);
  });
};
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
