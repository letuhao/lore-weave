/**
 * L6.A.4 — Outbound fanout from Redis Streams to subscribed WS connections.
 *
 * Foundation-grade SKELETON (cycle 28). Wired full in cycle-29+ when L6.D
 * (forced disconnect via Redis control channel) lands its Redis stream
 * consumer pattern; we share the same XREAD wire plumbing.
 *
 * Per Q-L6-3: foundation owns server only — this code lives in the gateway,
 * consumes `reality:<id>:events`, fans matching frames to subscribed WS
 * sockets. Down-stream service writes events via `services/meta-worker/`
 * (existing) — that wire contract is already locked.
 *
 * Contract:
 *   - Subscribe(connectionId, topics[]) → register interest
 *   - Unsubscribe(connectionId) → on socket close
 *   - The XREAD loop dispatches each frame to all subscribers of its topic
 *   - Per-message authz (S2/S3) is the OUTBOUND check (cycle 29 L6.C)
 */

import type { WebSocket } from 'ws';
import type { WsMetrics } from './metrics';

export interface FanoutDeps {
  readonly metrics: WsMetrics;
}

interface FanoutEntry {
  readonly connectionId: string;
  readonly socket: WebSocket;
  readonly topics: Set<string>;
}

/**
 * In-process fanout registry. The XREAD reader (separate goroutine —
 * here, a Node async iterator) calls `dispatch(topic, frame)` which
 * walks the registry and sends to each matching socket.
 */
export class OutboundFanout {
  private readonly entries = new Map<string, FanoutEntry>();

  constructor(private readonly deps: FanoutDeps) {}

  subscribe(connectionId: string, socket: WebSocket, topics: readonly string[]): void {
    if (topics.length === 0) return;
    const existing = this.entries.get(connectionId);
    if (existing) {
      for (const t of topics) existing.topics.add(t);
      return;
    }
    this.entries.set(connectionId, {
      connectionId,
      socket,
      topics: new Set(topics),
    });
  }

  unsubscribe(connectionId: string): void {
    this.entries.delete(connectionId);
  }

  /**
   * Dispatch a frame to every subscribed WS connection. The frame string
   * is assumed to be a serialized Envelope (the caller — XREAD loop —
   * already wrapped the raw event in the wire envelope). Caller passes
   * the topic the frame was published on; we match against subscriptions.
   *
   * Per-message authz is NOT done here — the writer that produced the
   * event MUST have already filtered the recipient list. This is the
   * cycle-29 wire-up; foundation here just routes by topic.
   */
  dispatch(topic: string, frame: string): number {
    let sent = 0;
    for (const e of this.entries.values()) {
      if (!e.topics.has(topic)) continue;
      if (e.socket.readyState !== e.socket.OPEN) continue;
      e.socket.send(frame);
      this.deps.metrics.onMessage('s2c', 'data');
      sent += 1;
    }
    return sent;
  }

  /** Test inspection. */
  size(): number {
    return this.entries.size;
  }
}
