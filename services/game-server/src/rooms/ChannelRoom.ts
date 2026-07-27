import { Room, type Client } from 'colyseus';
import Redis from 'ioredis';

import {
  emptyView,
  foldEvent,
  projectTurnOutcome,
  type ChannelView,
  type CommittedEvent,
  type TurnOutcome,
} from '../wire/turnOutcome.js';
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
  /** The DP-A16 channel (= sim-core island) this room is a lens on. */
  channelId: string;
  redisUrl: string;
  /** RLS-A13 content address of the resolved ruleset (W0). */
  rulesetDigest?: string;
  /** Start cursor: '$' = only new, '0' = replay everything retained. */
  from?: string;
  pollBlockMs?: number;
}

/**
 * The proposal bus the commit-service spine consumes for a channel. The room
 * WRITES here (a proposal is a request, never a write — AGT-A6/CWC-A1) and
 * never reads it back; outcomes return only via the committed-event stream.
 */
export function proposalStreamFor(realityId: string, channelId: string): string {
  return `reality:${realityId}:cell:${channelId}:proposals`;
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
  view?: ChannelView,
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
      if (view) foldEvent(view, ev);
      const outcome = projectTurnOutcome(ev);
      if (outcome) sink(outcome, id);
    }
  }
  return last;
}

/**
 * Build the W1 first frame by REPLAYING the channel from the given cursor
 * (D2 — the room is a projection, so its state comes from the log, not from a
 * second read API that could disagree with it). Returns the folded view and
 * the cursor reached, which IS the client's DP-Ch18 `from_token`.
 */
export async function replayView(
  redis: Redis,
  stream: string,
  from = '0',
): Promise<ChannelView> {
  const view = emptyView();
  let cursor = from;
  for (;;) {
    const next = await consumeOnce(redis, stream, cursor, () => {}, 0, view);
    if (next === cursor) break;
    cursor = next;
  }
  return view;
}

export class ChannelRoom extends Room {
  private redis?: Redis;
  private cursor = '$';
  private running = false;
  private opts!: ChannelRoomOptions;
  private view: ChannelView = emptyView();
  /** sessionId → the entity this connection may act as (D3). */
  private actorOf = new Map<string, string>();

  async onCreate(options: ChannelRoomOptions): Promise<void> {
    this.opts = options;
    this.redis = new Redis(options.redisUrl);
    const stream = streamFor(options.realityId);

    // W1 source: replay the channel to "now", then tail from there. The
    // replay cursor is the join-time `from_token` (GDA-D7: reconnect is W0 +
    // catch-up, and a fresh join is just a catch-up from 0).
    this.view = await replayView(this.redis, stream, options.from ?? '0');
    this.cursor = this.view.last_event_id === '0' ? '0' : '$';
    this.running = true;
    void this.pump(stream, options.pollBlockMs ?? 2000);

    // Inbound (D3/D5). The client sends an ACTION; it never sends an actor.
    this.onMessage('turn.submit', (client, message) => {
      void this.submit(client, message as { client_request_id?: string; action?: unknown });
    });
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
          this.view,
        );
      } catch (err) {
        if (!this.running) return;
        log.warn('channel-room: stream read failed, retrying', { err: String(err) });
        await new Promise((r) => setTimeout(r, 500));
      }
    }
  }

  /**
   * D3 — the confused-deputy guard. The room stamps `actor` from the
   * AUTHENTICATED session; a client that could name its own actor could act as
   * another player. This is the one authority-adjacent thing the room does,
   * and it is an identity binding, not an authorization: admission still
   * validates everything (CWC-A1).
   */
  private async submit(
    client: Client,
    msg: { client_request_id?: string; action?: unknown },
  ): Promise<void> {
    const actor = this.actorOf.get(client.sessionId);
    if (!actor) {
      client.send('turn.error', { code: 'no_actor_bound', message: 'session has no actor' });
      return;
    }
    if (!msg?.client_request_id || !msg.action) {
      // Refused at the edge, with a reason — never silently dropped.
      client.send('turn.error', {
        code: 'malformed_submit',
        message: 'client_request_id and action are required',
      });
      return;
    }
    // EVT-T1 Submitted (15 §7b.2: the player is NOT an EVT-A7 trusted
    // producer — commit-service validates on their behalf). The EVT-L3 triple
    // is (producer_service, client_request_id, target_channel): the id is
    // CLIENT-minted, so a retry over a flaky link is idempotent by
    // construction rather than by luck.
    const proposal = {
      producer_service: 'game-server',
      proposal_id: msg.client_request_id,
      target_channel: Number(this.opts.channelId),
      event_category: 'T1',
      actor: Number(actor),
      candidates: this.candidates(actor),
      decision: msg.action,
    };
    try {
      await this.redis!.xadd(
        proposalStreamFor(this.opts.realityId, this.opts.channelId),
        '*',
        'proposal',
        JSON.stringify(proposal),
      );
      client.send('turn.accepted', { client_request_id: msg.client_request_id });
    } catch (err) {
      // The bus is down: tell the client so it can retry with the SAME id.
      client.send('turn.error', { code: 'bus_unavailable', message: String(err) });
    }
  }

  /**
   * THR-A4 — the engine offers the targets; the client picks from them and can
   * name nobody else. Derived from the replayed view, so it reflects committed
   * truth rather than anything a client asserted.
   */
  private candidates(self: string): [number, string][] {
    return Object.entries(this.view.actors)
      .filter(([id, a]) => id !== self && !a.down && !a.fled)
      .map(([id]) => [Number(id), `hostile-${id}`] as [number, string]);
  }

  onJoin(client: Client, options?: { actorEntityId?: string }): void {
    // PoC identity binding. Production takes this from the redeemed WS ticket
    // (the EchoRoom path), never from join options — the TODO is the auth
    // source, NOT the guard: the guard (stamp server-side, ignore any actor a
    // client puts in a message) is already in place above.
    const actor = options?.actorEntityId ?? '1';
    this.actorOf.set(client.sessionId, actor);

    // W0 — bind ack (doc 20 §2). from_tokens is the DP-Ch18 per-channel map.
    client.send('w0.bind', {
      session_id: client.sessionId,
      reality_id: this.opts.realityId,
      channel_id: this.opts.channelId,
      ruleset_digest: this.opts.rulesetDigest ?? '0'.repeat(64),
      from_tokens: { [this.opts.channelId]: this.view.last_event_id },
      client_protocol: 1,
    });
    // W1 — first frame, folded from the replayed log (D2).
    client.send('w1.frame', {
      self: { entity_id: actor, ...this.view.actors[actor] },
      turn_number: this.view.turn_number,
      roster: Object.entries(this.view.actors).map(([id, a]) => ({
        entity_id: id,
        display_name: `entity-${id}`,
        disposition: id === actor ? 'friendly' : 'hostile',
        condition: a.down ? 'down' : a.hp !== undefined && a.hp <= 10 ? 'critical' : 'healthy',
      })),
    });
  }

  onLeave(client: Client): void {
    this.actorOf.delete(client.sessionId);
  }

  async onDispose(): Promise<void> {
    this.running = false;
    await this.redis?.quit();
  }
}
