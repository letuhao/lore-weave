// Reconnect queue: holds messages while WS is disconnected, replays
// on reconnect. Session E wires real impl with exponential backoff
// and at-most-once semantics for idempotent actions.

import type { ClientToServer } from './protocol';

export class ReconnectQueue {
  private buffer: ClientToServer[] = [];

  enqueue(msg: ClientToServer): void {
    this.buffer.push(msg);
  }

  drain(): ClientToServer[] {
    const out = this.buffer;
    this.buffer = [];
    return out;
  }

  get size(): number {
    return this.buffer.length;
  }
}
