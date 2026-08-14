import { Room, ServerError, type AuthContext, type Client } from 'colyseus';

import {
  authCloseCode,
  authenticateTicket,
  ticketRedeemerFromEnv,
  wsTrustedProxy,
} from '../ws/auth.js';
import Redis from 'ioredis';

import {
  emptyView,
  foldEvent,
  projectTurnOutcome,
  type ChannelView,
  type CommittedEvent,
  type TurnOutcome,
} from '../wire/turnOutcome.js';
import { MessageRateLimiter, rateLimitsFromEnv } from '../ws/rate-limit.js';
import { GlobalRateLimiter, globalRateLimitFromEnv } from '../ws/global-rate-limit.js';
import { PRODUCER_NAME, producerKeyFromEnv, signProposal } from '../ws/producer-sign.js';
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

/**
 * Room configuration. **Sourced from the SERVER's environment, never from the
 * joining client** — `redisUrl` in particular is infrastructure: a
 * client-supplied value would point the room at an attacker's broker (an SSRF
 * / data-exfiltration hole dressed up as a join option). The only thing a
 * client contributes is its identity claim, and even that is a claim the room
 * re-derives (see `onJoin`).
 */
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
  /**
   * sessionId → authenticated user, for the CNC-Q1 user-keyed global cap —
   * and, since `SEALED-SUBJECT`, for the `user_ref_id` the proposal carries.
   */
  private userOf = new Map<string, string>();

  /**
   * IAS-D5 — per-connection submit rate limit, layer 1 of the doc-22 defence
   * stack. Until this existed, `ChannelRoom` had none at all: the limiter was
   * wired only into `EchoRoom`, the V0 demo, so the room that actually
   * carries the game was the unprotected one.
   *
   * IAS-A6 — this sits ABOVE the durable boundary and that placement is the
   * whole point. CS-A4 makes admission rejections durable events, so a
   * refusal that reached admission would still cost a commit; at CEI-2's
   * ~170 commits/sec, 100 refused requests would burn ~0.57 s of the
   * channel's entire budget. Being refused loudly enough would BE the attack.
   * A transport refusal therefore closes the socket and emits nothing: no
   * event, no bus write, no proposal. It is not a verdict about an intent —
   * it is a decision not to hear one.
   */
  private submitLimiters = new Map<string, MessageRateLimiter>();
  private rateConfig = rateLimitsFromEnv();

  /**
   * CNC-Q1 — the CROSS-REPLICA cap, keyed by user. The limiter above is
   * per-connection and per-process; on a fleet of N replicas a client that
   * opens a connection to each would otherwise get N× the budget (audit
   * CNC-F7). Keyed by the authenticated user, so opening more connections
   * buys nothing.
   *
   * Null when no Redis is configured: a single-node dev run keeps the
   * per-replica cap and nothing else, which is what it had before.
   */
  private globalLimiter: GlobalRateLimiter | null = null;

  /** PID-A2 — this service's producer key; `undefined` means unsigned. */
  private producerKey = producerKeyFromEnv();

  async onCreate(joinOptions: Partial<ChannelRoomOptions> = {}): Promise<void> {
    // Config from ENV; anything a client passed is ignored except in dev,
    // where an explicit override is convenient and harmless because the dev
    // broker is local. Production has no client-controlled path here.
    const fromEnv: ChannelRoomOptions = {
      realityId: process.env.LW_CHANNEL_REALITY_ID ?? '',
      channelId: process.env.LW_CHANNEL_ID ?? '1',
      redisUrl: process.env.LW_CHANNEL_REDIS_URL ?? 'redis://127.0.0.1:6399/0',
      rulesetDigest: process.env.LW_CHANNEL_RULESET_DIGEST,
    };
    // Even in dev, a client may never supply INFRASTRUCTURE (`redisUrl`) —
    // that would be an SSRF/exfiltration hole with a debug flag in front of
    // it. The override covers only the two identifiers that are safe to vary
    // per room.
    const devOverride = process.env.LW_CHANNEL_ALLOW_CLIENT_CONFIG === '1';
    this.opts = devOverride
      ? {
          ...fromEnv,
          realityId: joinOptions.realityId ?? fromEnv.realityId,
          channelId: joinOptions.channelId ?? fromEnv.channelId,
        }
      : fromEnv;
    if (!this.opts.realityId) {
      throw new Error('ChannelRoom: LW_CHANNEL_REALITY_ID is required (server config)');
    }
    const options = this.opts;
    this.redis = new Redis(options.redisUrl);
    // Reuses the room's Redis connection: the bucket is a couple of hash
    // fields per user, not a second infrastructure dependency.
    this.globalLimiter = new GlobalRateLimiter(this.redis, globalRateLimitFromEnv());
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
    // IAS-D5/A6 — layer 1, and it runs FIRST: before the actor lookup, before
    // any validation, and above all before anything that could reach the bus.
    // Over the cap the socket is closed (4006) and NOTHING is emitted — no
    // event, no proposal. See the `submitLimiters` note for why a durable
    // refusal here would be the attack rather than the defence.
    // Cross-replica cap first (CNC-Q1) — it is the one an attacker with N
    // connections cannot dodge. Degrades to `allowed` if Redis is down, in
    // which case the per-connection limiter below is still enforcing.
    const userId = this.userOf.get(client.sessionId);
    if (this.globalLimiter && userId) {
      const decision = await this.globalLimiter.take(userId, Date.now());
      if (!decision.allowed) {
        log.warn('channel-room: global rate limit exceeded, closing', { userId });
        client.leave(4006);
        return;
      }
    }

    const limiter = this.submitLimiters.get(client.sessionId);
    if (limiter && !limiter.allow(Date.now())) {
      log.warn('channel-room: submit rate limit exceeded, closing', {
        sessionId: client.sessionId,
      });
      client.leave(4006);
      return;
    }

    const actor = this.actorOf.get(client.sessionId);
    if (!userId) {
      // Unreachable if `onAuth` ran — asserted rather than assumed, because a
      // proposal with no submitter is refused at the far side's schema stage
      // and would arrive there as an opaque malformed body.
      client.send('turn.error', { code: 'no_user_bound', message: 'session has no user' });
      return;
    }
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
    // PID-D5 — `event_category` is NOT sent. It used to ride here and select
    // the validator subset on the far side, which let any producer elect its
    // own trust tier. commit-service now derives the tier from whichever
    // producer key verifies the signature below; `producer_service` survives
    // only as a lookup hint that the MAC has to prove.
    const proposal = {
      producer_service: PRODUCER_NAME,
      proposal_id: msg.client_request_id,
      target_channel: Number(this.opts.channelId),
      // SEALED-SUBJECT — the USER, never the actor.
      //
      // This sent `actor: Number(actor)` and commit-service believed it. The
      // room stamped it from the authenticated session, so the CLIENT could
      // not choose — but the field still existed on the wire, and a field on
      // the wire is a field some other producer can set. The subject is now
      // resolved from `actor_control_binding` on the authoritative side, and
      // the way to make it unassertable is for it to be ABSENT rather than
      // trusted: `admission::Proposal` has no `actor` to deserialise into.
      //
      // `candidates` still needs the local actor, and that is fine — it is an
      // OFFER the far side re-validates against island state (THR-A4), not a
      // claim about who is acting.
      user_ref_id: userId,
      candidates: this.candidates(actor),
      decision: msg.action,
    };
    try {
      // PID-D2 — sign the EXACT bytes that go on the stream and send the
      // signature beside them. Re-stringifying `proposal` for the XADD would
      // risk producing different bytes from the ones that were signed.
      const { raw, sig } = signProposal(proposal, this.producerKey);
      const fields: string[] = ['proposal', raw];
      if (sig) fields.push('producer_sig', sig);
      await this.redis!.xadd(
        proposalStreamFor(this.opts.realityId, this.opts.channelId),
        '*',
        ...fields,
      );
      client.send('turn.accepted', { client_request_id: msg.client_request_id });
    } catch (err) {
      // The bus is down: tell the client so it can retry with the SAME id.
      client.send('turn.error', { code: 'bus_unavailable', message: String(err) });
    }
  }

  /**
   * Map an authenticated user to the entity they control on this channel, or
   * `undefined` when this user drives nobody here.
   *
   * **`undefined` IS THE FIX.** This returned `LW_CHANNEL_DEFAULT_ACTOR ?? '1'`
   * for any authenticated user absent from the map, so every unmapped user was
   * legitimately bound to the SAME subject — two humans acting as one actor,
   * with the server itself stamping the claim. A red-team pass called it the
   * load-bearing hole and downgraded the confused-deputy guard because of it:
   * `CMD-12`'s keyed-MAC over a subject is a lock on the wrong door while the
   * caller can already BE that subject. It is a tenancy defect by CLAUDE.md's
   * own checklist before it is an offer problem.
   *
   * Two lines above, `onJoin` refuses a missing `userId` with the comment *"loud
   * rather than defaulting to entity 1"* — and then called a function that
   * defaulted to entity 1. The principle was already written down; only this
   * function disagreed with it.
   *
   * The refusal it now reaches is not new either: `handleSubmit` has always had
   * `no_actor_bound`, which the default made unreachable. Refusing at SUBMIT and
   * not at join is deliberate — the user is authenticated and entitled to the
   * channel, they simply drive nobody in it, so they may watch and may not act.
   * Closing the socket would need a close code that does not exist in the
   * four-language `§12AB.9` set, to say something this transport can already say.
   *
   * The durable source is `actor_control_binding` (migration 034 — which human
   * drives which actor, in which reality). game-server has no Postgres client
   * and must not grow one (I3: TypeScript is gateway/realtime), so reaching it
   * needs a control-plane lookup that does not exist yet — tracked as
   * `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`. The env map stays as the dev-time
   * binding and is NOT the bug: it is explicit and per-user, and it never lets
   * the CLIENT choose. Env form: `user:entity,user:entity`.
   */
  private actorForUser(userId: string): string | undefined {
    const raw = process.env.LW_CHANNEL_ACTOR_MAP ?? '';
    for (const pair of raw.split(',')) {
      const [u, e] = pair.split(':').map((x) => x.trim());
      if (u && e && u === userId) return e;
    }
    return undefined;
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

  /**
   * PRR-20 edge auth, same path as EchoRoom: redeem the gateway-issued WS
   * ticket (one-shot, origin- + fingerprint-bound) and take the userId from
   * IT. Without a ticket store configured, the dev static-token fallback
   * applies — and ONLY when `LW_WS_DEV_ALLOW_STATIC=1`, so a production
   * deployment that forgets to configure Redis fails closed instead of
   * accepting anyone.
   */
  async onAuth(_client: Client, options: { jwt?: string }, context: AuthContext) {
    try {
      const redeemer = ticketRedeemerFromEnv();
      if (redeemer) {
        const authed = await authenticateTicket(
          redeemer,
          Object.fromEntries(context.headers),
          context.ip,
          Date.now(),
          { trustedProxy: wsTrustedProxy() },
        );
        return { userId: authed.userId };
      }
      if (process.env.LW_WS_DEV_ALLOW_STATIC !== '1') {
        throw new ServerError(4001, 'no ticket store configured (fail closed)');
      }
      const expected = process.env.LOREWEAVE_INTERNAL_TOKEN ?? 'dev_token';
      if (!options?.jwt || options.jwt !== expected) {
        throw new ServerError(4001, 'invalid token');
      }
      return { userId: `dev:${String(options.jwt).slice(0, 4)}` };
    } catch (err) {
      const code = err instanceof ServerError ? (err.code as number) : authCloseCode(err);
      throw err instanceof ServerError ? err : new ServerError(code, (err as Error).message);
    }
  }

  onJoin(client: Client): void {
    // D3 — identity comes from the AUTHENTICATED session, never from join
    // options. Taking `actorEntityId` off the wire (as this did while it was
    // a PoC) lets any client claim any actor and act as another player; the
    // fact that the room re-stamps it on submit is not enough, because what
    // it stamps would BE the attacker's claim.
    const userId = (client.auth as { userId?: string } | undefined)?.userId;
    if (!userId) {
      // Unreachable if onAuth ran; loud rather than defaulting to entity 1.
      client.leave(4001);
      return;
    }
    const actor = this.actorForUser(userId);
    // Only bind when there IS a binding. An unmapped user gets no entry, which
    // is what makes `handleSubmit`'s `no_actor_bound` reachable — see
    // `actorForUser`. Storing a default here was the confused-deputy hole.
    if (actor !== undefined) {
      this.actorOf.set(client.sessionId, actor);
    }
    this.userOf.set(client.sessionId, userId);
    // IAS-D5 — one limiter per connection, created here so a reconnect gets a
    // fresh window rather than inheriting a stranger's.
    this.submitLimiters.set(
      client.sessionId,
      new MessageRateLimiter(this.rateConfig.messagesPerWindow, this.rateConfig.windowMs),
    );

    // W0 — bind ack (doc 20 §2). from_tokens is the DP-Ch18 per-channel map.
    client.send('w0.bind', {
      session_id: client.sessionId,
      reality_id: this.opts.realityId,
      channel_id: this.opts.channelId,
      // zero-digest-gate: ok — D-WIRE-DIGEST-ZERO, tracked, blocked on F2.
      //
      // This is the SAME bug F1 removed from the Rust side, still standing here:
      // a 64-zero fallback, and `common.schema.json` says the client caches BY
      // digest — so every reality would share one cache key. It is LATENT, not
      // live: nothing in `frontend/src` reads `ruleset_digest` yet.
      //
      // It is not fixable here. The real digest is `Ruleset::digest()` inside
      // commit-service; `LW_CHANNEL_RULESET_DIGEST` is an env var carrying a
      // PER-REALITY value, which is itself the wrong shape (a per-reality fact
      // is not deploy-time config). Wiring it through the bind path is a
      // cross-service seam that lands with F2's loader.
      ruleset_digest: this.opts.rulesetDigest ?? '0'.repeat(64),
      from_tokens: { [this.opts.channelId]: this.view.last_event_id },
      client_protocol: 1,
    });
    // W1 — first frame, folded from the replayed log (D2).
    //
    // `self` is null when this user drives nobody here (see `actorForUser`).
    // Null and not a default entity: the frame is what the client renders as
    // "you", and inventing one is the same confused-deputy claim one layer up
    // from the submit path — it would show a stranger's actor as the reader's.
    client.send('w1.frame', {
      self: actor === undefined ? null : { entity_id: actor, ...this.view.actors[actor] },
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
    // Both maps are keyed by sessionId; leaving one behind leaks per
    // connection for the lifetime of the room.
    this.submitLimiters.delete(client.sessionId);
    this.userOf.delete(client.sessionId);
  }

  async onDispose(): Promise<void> {
    this.running = false;
    await this.redis?.quit();
  }
}
