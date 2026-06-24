/**
 * L6.A.3 — Per-connection inbound message router (RAID cycle 28).
 *
 * Pure logic — accepts the envelope JSON the gateway already parsed, then
 * dispatches by `type` to one of:
 *
 *   1. CONTROL  — ws.ping → reply ws.pong; ws.refresh → renew session
 *   2. DATA     — chat.*, session.*, presence.* → downstream (roleplay-service)
 *
 * Per S12 §12AB.4 the control fast-path skips per-message authz; data
 * messages go through L6.C re-auth (cycle 29, not us). Foundation here
 * ships the dispatch table + the contract that ALL data messages are
 * tagged for downstream authz.
 *
 * Per Q-L6-3: foundation owns server + envelope types only — the
 * downstream service contracts (chat-service, roleplay-service) own
 * their per-Type payloads.
 */

import type { Direction, Kind, WsMetrics } from './metrics';

/** Wire-compatible with `contracts/ws/envelope.go::Envelope`. */
export interface Envelope {
  readonly v: number;
  readonly kind: Kind;
  readonly type: string;
  readonly dir: Direction;
  readonly seq?: number;
  readonly nonce?: string;
  readonly payload?: unknown;
}

export const ENVELOPE_VERSION = 1;

export type RouteOutcome =
  | { tag: 'control_ack'; reply: Envelope }
  | { tag: 'data_forward'; payload: unknown; type: string; envelope: Envelope }
  | { tag: 'refresh_requested' }
  | { tag: 'rejected'; reason: RejectReason };

export type RejectReason =
  | 'schema_invalid'
  | 'version_mismatch'
  | 'unknown_type'
  | 'direction_invalid';

export class RouterError extends Error {
  constructor(public readonly reason: RejectReason, message: string) {
    super(message);
    this.name = 'RouterError';
  }
}

/**
 * Envelope shape check — mirrors `contracts/ws/envelope.go::Validate`.
 */
export function validateEnvelope(env: unknown): Envelope {
  if (!env || typeof env !== 'object') {
    throw new RouterError('schema_invalid', 'envelope not an object');
  }
  const e = env as Partial<Envelope>;
  if (e.v !== ENVELOPE_VERSION) {
    throw new RouterError('version_mismatch', `envelope v=${e.v} != ${ENVELOPE_VERSION}`);
  }
  if (e.kind !== 'control' && e.kind !== 'data') {
    throw new RouterError('schema_invalid', `bad kind ${e.kind}`);
  }
  if (e.dir !== 'c2s' && e.dir !== 's2c') {
    throw new RouterError('direction_invalid', `bad direction ${e.dir}`);
  }
  if (!e.type || typeof e.type !== 'string') {
    throw new RouterError('schema_invalid', 'type empty');
  }
  if (e.kind === 'data' && (!e.nonce || typeof e.nonce !== 'string')) {
    throw new RouterError('schema_invalid', 'data envelope requires nonce');
  }
  return e as Envelope;
}

/**
 * Reserved CONTROL message types served entirely in-gateway. Anything
 * not in this set + kind=control is rejected (defense against future-proofing
 * confusion where a client invents a control type the server doesn't know).
 */
const CONTROL_TYPES = new Set(['ws.ping', 'ws.refresh', 'ws.close'] as const);

export interface RouterDeps {
  /** Called when client requests session.refresh — server hands back a hint frame; full refresh handshake is HTTP. */
  onRefreshRequested?: () => void;
}

/**
 * The router is stateless per call — the WS server passes an envelope
 * and we return what to do. State (seq counters, nonces) lives on the
 * WSSession that the caller owns.
 *
 * Direction validation: c2s envelopes are the only thing this router
 * accepts. The server side never asks the router to validate an outbound
 * frame (those bypass the router entirely).
 */
export function routeInbound(env: unknown, metrics: WsMetrics, deps: RouterDeps = {}): RouteOutcome {
  let parsed: Envelope;
  try {
    parsed = validateEnvelope(env);
  } catch (err) {
    metrics.onMessage('c2s', 'data');
    if (err instanceof RouterError) return { tag: 'rejected', reason: err.reason };
    return { tag: 'rejected', reason: 'schema_invalid' };
  }
  if (parsed.dir !== 'c2s') {
    return { tag: 'rejected', reason: 'direction_invalid' };
  }

  metrics.onMessage('c2s', parsed.kind);

  if (parsed.kind === 'control') {
    if (!CONTROL_TYPES.has(parsed.type as never)) {
      return { tag: 'rejected', reason: 'unknown_type' };
    }
    switch (parsed.type) {
      case 'ws.ping':
        return {
          tag: 'control_ack',
          reply: {
            v: ENVELOPE_VERSION,
            kind: 'control',
            type: 'ws.pong',
            dir: 's2c',
          },
        };
      case 'ws.refresh':
        deps.onRefreshRequested?.();
        return { tag: 'refresh_requested' };
      case 'ws.close':
        // The actual socket-close is done by the gateway after this
        // router-call returns; we just acknowledge intent.
        return {
          tag: 'control_ack',
          reply: {
            v: ENVELOPE_VERSION,
            kind: 'control',
            type: 'ws.close',
            dir: 's2c',
          },
        };
    }
  }

  // Data — caller forwards downstream after running L6.C authz (cycle 29).
  // The envelope is returned alongside the payload so the caller can pluck
  // session_id / reality_id / privacy_level out of the wire payload metadata
  // to feed `PerMessageAuthz.evaluateInbound`.
  return { tag: 'data_forward', payload: parsed.payload, type: parsed.type, envelope: parsed };
}
