import { Room, type Client } from 'colyseus';
import Redis from 'ioredis';

import { projectTurnOutcome, type CommittedEvent, type TurnOutcome } from '../wire/turnOutcome.js';
import { log } from '../log.js';

// ChannelRoom — the GDA-A7 projection: one Colyseus room per DP-A16 channel
// (= one sim-core island). It consumes the per-reality committed-event stream
// and fans `TurnOutcome` frames to the clients bound to that channel.
//
// CWC-A1 — the room holds NO authority. Nothing a client sends mutates state
// here; every state-bearing frame is derived from an event commit-service
// already made durable under its epoch-fenced writer. The room is a lens.
//
// Scope (PoC, 2026-07-27): the turn lane only. W0/W1 framing, movement (Class
// A / RTM lane) and turn submission back onto the bus ride the next slices;
// this proves the committed-event → client-DTO path end to end.

export interface ChannelRoomOptions {
  /** The reality whose committed-event stream this room projects. */
  realityId: string;
  redisUrl: string;
  /** Start cursor: '$' = only new, '0' = replay everything retained. */
  from?: string;
  pollBlockMs?: number;
}

/**
 * The per-reality stream the platform publisher XADDs to
 * (`services/publisher/pkg/redisemit`: `lw.events.<reality_id>`). Kept as a
 * function, not a caller-supplied string, so a consumer cannot quietly point
 * at a stream nobody writes — that exact drift is how a room would sit silent
 * forever with no error to show for it.
 */
export function streamFor(realityId: string): string {
  return `lw.events.${realityId}`;
}

/**
 * Parse the publisher's envelope: FLAT Redis stream fields, with `payload` and
 * `metadata` carried as JSON strings and the channel-ordering ids as decimal
 * strings (CWC-A2). This mirrors `redisemit.envelopeFields` — the two are
 * joined only by the wire, so the shape lives in one named function rather
 * than inline, and its test feeds it a byte-for-byte real entry.
 */
export function parseEnvelope(fields: string[]): CommittedEvent {
  const bag: Record<string, string> = {};
  for (let i = 0; i + 1 < fields.length; i += 2) bag[fields[i]] = fields[i + 1];
  if (!bag.event_type) throw new Error('envelope has no event_type');
  const json = (raw: string | undefined): Record<string, unknown> | undefined =>
    raw ? (JSON.parse(raw) as Record<string, unknown>) : undefined;
  return {
    event_type: bag.event_type,
    channel_event_id: bag.channel_event_id,
    payload: json(bag.payload),
    metadata: json(bag.metadata),
  };
}

/**
 * Pure consumer loop, extracted from the Room so it can be tested without a
 * Colyseus server: reads the stream forward and hands each projected outcome
 * to `sink`. Returns the cursor it reached (the DP-Ch18 `from_token` for this
 * channel — the same value W0 hands a reconnecting client).
 */
export async function consumeOnce(
  redis: Redis,
  stream: string,
  cursor: string,
  sink: (o: TurnOutcome, id: string) => void,
  blockMs = 0,
): Promise<string> {
  // ioredis's typed overloads don't cover the BLOCK+COUNT combination, so the
  // variadic call goes through `xread` positionally (the wire command is the
  // same either way).
  const xread = redis.xread.bind(redis) as (...args: unknown[]) => Promise<unknown>;
  const res = (await (blockMs
    ? xread('BLOCK', blockMs, 'COUNT', 64, 'STREAMS', stream, cursor)
    : xread('COUNT', 64, 'STREAMS', stream, cursor))) as
    | [string, [string, string[]][]][]
    | null;
  if (!res) return cursor;
  let last = cursor;
  for (const [, entries] of res) {
    for (const [id, fields] of entries) {
      last = id;
      let ev: CommittedEvent;
      try {
        ev = parseEnvelope(fields);
      } catch (err) {
        // A malformed entry is recorded and SKIPPED, never fatal: one bad
        // entry must not stall a channel's whole projection (EVT-L5 forbids
        // silent drop, so it is logged, not swallowed).
        log.warn('channel-room: unparseable stream entry', { id, err: String(err) });
        continue;
      }
      const outcome = projectTurnOutcome(ev);
      if (outcome) sink(outcome, id);
    }
  }
  return last;
}

export class ChannelRoom extends Room {
  private redis?: Redis;
  private cursor = '$';
  private running = false;

  async onCreate(options: ChannelRoomOptions): Promise<void> {
    this.cursor = options.from ?? '$';
    this.redis = new Redis(options.redisUrl);
    this.running = true;
    const stream = streamFor(options.realityId);
    void this.pump(stream, options.pollBlockMs ?? 2000);
    log.info('channel-room: consuming', { stream, from: this.cursor });
  }

  private async pump(stream: string, blockMs: number): Promise<void> {
    while (this.running && this.redis) {
      try {
        this.cursor = await consumeOnce(
          this.redis,
          stream,
          this.cursor,
          (outcome) => this.broadcast('turn.outcome', outcome),
          blockMs,
        );
      } catch (err) {
        if (!this.running) return;
        log.warn('channel-room: stream read failed, retrying', { err: String(err) });
        await new Promise((r) => setTimeout(r, 500));
      }
    }
  }

  onJoin(client: Client): void {
    // The client's per-channel resume cursor (DP-Ch18 / CWC W0 `from_tokens`).
    client.send('channel.bound', { from_token: this.cursor });
  }

  async onDispose(): Promise<void> {
    this.running = false;
    await this.redis?.quit();
  }
}
