// Typed message protocol for WebSocket comms with the game-server
// (V1+). Per spec §17 + §17.1: Colyseus is the V1 transport but the
// protocol layer stays abstract so we can swap to Rust+axum-tungstenite
// later. ws-client.ts is the only file that imports colyseus.js.

export type ClientToServer =
  | { kind: 'auth-handshake'; jwt: string }
  | { kind: 'enter-zone'; zoneId: string }
  | { kind: 'player-action'; action: 'move' | 'attack' | 'use-item'; targetX?: number; targetY?: number };

export type ServerToClient =
  | { kind: 'session-established'; characterId: string }
  | { kind: 'zone-snapshot'; zoneId: string; players: unknown[] }
  | { kind: 'action-result'; ok: boolean; reason?: string }
  | { kind: 'world-event'; eventId: string; payload: unknown };
