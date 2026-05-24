// WebSocket client stub. Session E wires Colyseus SDK and verifies
// auth handshake + reconnect end-to-end. Per spec §17.1 mitigation,
// this is the ONLY file that should import colyseus.js — keeping the
// surface narrow so a future migration to Rust+axum-tungstenite only
// rewrites this file + protocol serialization.

import type { ClientToServer, ServerToClient } from './protocol';

export interface WsClient {
  connect(url: string, jwt: string): Promise<void>;
  send(msg: ClientToServer): void;
  on(handler: (msg: ServerToClient) => void): () => void;
  disconnect(): void;
}

export function createWsClient(): WsClient {
  // TODO Session E: import { Client } from 'colyseus.js'; const client = new Client(url)
  return {
    connect: async () => {
      throw new Error('ws-client not yet implemented — Session E');
    },
    send: () => {
      throw new Error('ws-client not yet implemented — Session E');
    },
    on: () => () => undefined,
    disconnect: () => undefined,
  };
}
