import { Client, Room, type ServerError } from 'colyseus.js';
import type { ClientToServer, ServerToClient } from './protocol';

// Real Colyseus client implementation. Per spec §17.1, this is the
// ONLY file in the codebase that imports colyseus.js — keeping the
// abstraction narrow so a future migration to Rust + axum-tungstenite
// (per §17.1 trigger conditions) only rewrites this file + the
// protocol serialization, not the entire net/ tree.
//
// Auth: passes options.jwt to Colyseus, which calls EchoRoom.onAuth
// server-side. Reject → client receives a ServerError (kind: 'error'
// in our ServerToClient union).
//
// Reconnect: Colyseus rooms expose `room.reconnectionToken`. Stored in
// localStorage so a page reload or temporary disconnect can resume the
// session via `client.reconnect(token)` within the seatReservationTime
// window (30s, set in EchoRoom.onCreate).

const RECONNECT_TOKEN_KEY = 'lw_reconnect_token';

export interface WsClient {
  connect(url: string, jwt: string): Promise<void>;
  send(msg: ClientToServer): void;
  on(handler: (msg: ServerToClient) => void): () => void;
  reconnect(): Promise<void>;
  disconnect(): void;
  isConnected(): boolean;
}

export function createWsClient(): WsClient {
  let client: Client | null = null;
  let room: Room | null = null;
  const handlers = new Set<(msg: ServerToClient) => void>();

  const dispatch = (msg: ServerToClient): void => {
    for (const h of handlers) {
      try {
        h(msg);
      } catch (err) {
        console.error('[ws-client] handler threw', err);
      }
    }
  };

  const wireRoom = (r: Room): void => {
    room = r;
    if (r.reconnectionToken) {
      localStorage.setItem(RECONNECT_TOKEN_KEY, r.reconnectionToken);
    }
    r.onMessage('*', (type, payload) => {
      dispatch({
        kind: 'world-event',
        eventId: String(type),
        payload: payload as unknown,
      });
    });
    r.onLeave((code) => {
      dispatch({
        kind: 'action-result',
        ok: false,
        reason: `room left (code ${code})`,
      });
      room = null;
    });
    r.onError((code, message) => {
      dispatch({
        kind: 'action-result',
        ok: false,
        reason: `room error ${code}: ${message ?? 'unknown'}`,
      });
    });
  };

  return {
    async connect(url, jwt) {
      client = new Client(url);
      try {
        const r = await client.joinOrCreate('echo', { jwt });
        wireRoom(r);
        dispatch({ kind: 'session-established', characterId: r.sessionId });
      } catch (err) {
        const e = err as ServerError;
        dispatch({
          kind: 'action-result',
          ok: false,
          reason: `connect failed: ${e?.message ?? String(err)}`,
        });
        throw err;
      }
    },

    send(msg) {
      if (!room) {
        throw new Error('ws-client: not connected');
      }
      // Colyseus signature: room.send(type, message). We use msg.kind
      // as the type so the server's onMessage handler keys match.
      room.send(msg.kind, msg);
    },

    on(handler) {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    },

    async reconnect() {
      const token = localStorage.getItem(RECONNECT_TOKEN_KEY);
      if (!token) {
        throw new Error('ws-client: no reconnect token stored');
      }
      if (!client) {
        throw new Error('ws-client: never connected — call connect first');
      }
      try {
        const r = await client.reconnect(token);
        wireRoom(r);
        dispatch({ kind: 'session-established', characterId: r.sessionId });
      } catch (err) {
        // Reconnect token expired or invalid — clear it so a fresh
        // connect happens next time.
        localStorage.removeItem(RECONNECT_TOKEN_KEY);
        throw err;
      }
    },

    disconnect() {
      room?.leave(true);
      room = null;
      localStorage.removeItem(RECONNECT_TOKEN_KEY);
    },

    isConnected() {
      return room !== null;
    },
  };
}
