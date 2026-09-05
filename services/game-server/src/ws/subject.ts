// `E3` — which actor does this user drive? Asked, not assumed.
//
// # What this replaces
//
// `ChannelRoom.actorForUser` read `LW_CHANNEL_ACTOR_MAP`, a `user:entity` env
// map. It was never the confused-deputy bug its predecessor was — it is
// explicit, per-user, and never lets the CLIENT choose — but it meant a human
// could drive an actor only if an operator edited an environment variable and
// restarted the process. The durable answer has lived in
// `actor_control_binding` since migration `034`, and this is the first thing
// that reads it.
//
// # Why HTTP and not a database client
//
// `I3`: TypeScript is gateway/realtime. game-server ships no Postgres client
// and must not grow one — measured, zero `pg`/`postgres`/`knex` in its
// manifest, and that is correct rather than an omission. So the read is
// world-service's `POST /internal/v1/actor-control/subject`, declared in
// `contracts/service_acl/matrix.yaml` as `world-service-rpcs.ResolveActorSubject`
// with `allowed_callers: [game-server]`.
//
// The PO also refused the cheaper shape: "the client asserts an actor and the
// server verifies it". That is the class `P3` killed — a subject on the wire is
// a subject that can be forged, and verification is a lock on the wrong door.
//
// # Four answers, because collapsing them is the recurring bug
//
// "You drive nobody", "this world is closed" and "we could not ask" are three
// different facts, and only the first is a normal state. Rendering an outage as
// `self: null` would silently demote every player to a spectator with nothing
// logged — the same mistake `classify_bind_failure` exists to prevent one tier
// down, where a missing migration reached an operator as "REFUSED — reload and
// decide".

import { log } from '../log.js';

/** What the control plane says about a user's subject in one reality. */
export type SubjectLookup =
  /** A live binding. `entityId` is what the island acts on. */
  | { kind: 'driving'; entityId: string; actorId: string }
  /** No live binding — a spectator, or the instant after a revoke. NORMAL. */
  | { kind: 'nobody' }
  /**
   * The reality does not accept commands: frozen, archived, provisioning, or
   * not registered at all. A statement about the WORLD — `4004` in the
   * `§12AB.9` close-code set is named for exactly this.
   */
  | { kind: 'realityClosed'; detail: string }
  /**
   * We could not ask. OURS. There is no truthful close code for it in the
   * enumerated set, and the contract refuses any code outside that set, so the
   * caller's fail-closed move is to refuse the JOIN rather than invent one.
   */
  | { kind: 'unavailable'; detail: string };

/** Anything that can answer the question. An interface so a test need not
 *  stand up an HTTP server to prove the room's branching. */
export interface SubjectResolver {
  resolve(realityId: string, userRefId: string): Promise<SubjectLookup>;
}

/**
 * Is this string the `user_ref_id` the meta table is keyed by?
 *
 * The ticket path yields `ticket.userRefId`, which is that id. The DEV static
 * fallback yields `dev:abcd`, which is not — and calling world-service with it
 * would be a 422 on every join. Checked here so the refusal names the real
 * reason instead of arriving as a validation error from another service.
 */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUserRefId(s: string): boolean {
  return UUID_RE.test(s);
}

/** The real resolver. Node's global `fetch` — no new dependency. */
export class HttpSubjectResolver implements SubjectResolver {
  constructor(
    private readonly baseUrl: string,
    private readonly internalToken: string,
    private readonly timeoutMs = 3000,
  ) {}

  async resolve(realityId: string, userRefId: string): Promise<SubjectLookup> {
    // A malformed id never leaves the process. It is not a lookup failure and
    // must not read as one: nothing is wrong with world-service.
    if (!isUserRefId(userRefId)) {
      return {
        kind: 'unavailable',
        detail: `authenticated principal is not a user_ref_id (got ${userRefId.length} chars)`,
      };
    }

    // A wedged control plane must not wedge every join. AbortSignal.timeout
    // rather than a hand-rolled race: it cancels the socket too.
    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}/internal/v1/actor-control/subject`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'X-Internal-Token': this.internalToken,
        },
        body: JSON.stringify({ reality_id: realityId, user_ref_id: userRefId }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      return { kind: 'unavailable', detail: `world-service unreachable: ${String(err)}` };
    }

    if (res.status === 400) {
      // The three cases world-service reserves a 400 for are all statements
      // about the world: unregistered, closed, or a binding whose actor the
      // registry lost. A player cannot act in any of them.
      const detail = await res.text().catch(() => '');
      return { kind: 'realityClosed', detail: detail.slice(0, 500) };
    }
    if (res.status !== 200) {
      // 401 belongs here and not in `realityClosed`: a rejected internal token
      // is OUR misconfiguration, and calling it "the world is closed" would
      // send an operator to look at the reality instead of at the deployment.
      return { kind: 'unavailable', detail: `world-service returned ${res.status}` };
    }

    let body: unknown;
    try {
      body = await res.json();
    } catch (err) {
      return { kind: 'unavailable', detail: `unparseable response: ${String(err)}` };
    }

    const self = (body as { self?: unknown } | null)?.self;
    if (self === null || self === undefined) {
      // `self: null` is the documented spectator answer. `undefined` reaches
      // here only if the key went missing — which would mean the wire contract
      // drifted, and treating that as "spectator" is the silent-no-op failure
      // the Rust side has a serde test against. Both are refusals to act, so
      // both are safe; the log is what tells them apart.
      if (self === undefined) {
        log.warn('subject response carried no `self` key — wire contract drift?', {
          reality_id: realityId,
        });
      }
      return { kind: 'nobody' };
    }

    const { actor_id: actorId, entity_id: entityId } = self as {
      actor_id?: unknown;
      entity_id?: unknown;
    };
    if (typeof entityId !== 'number' || !Number.isInteger(entityId) || entityId < 0) {
      return {
        kind: 'unavailable',
        detail: `self.entity_id is not an island id: ${JSON.stringify(entityId)}`,
      };
    }
    return { kind: 'driving', entityId: String(entityId), actorId: String(actorId ?? '') };
  }
}

/**
 * Build the resolver from the environment, or `undefined` when it is not
 * configured.
 *
 * `undefined` is NOT "fall back to the env map". The caller decides what to do
 * with it, and the rule it applies is the one `onAuth` already applies six
 * lines away for the ticket store: without configuration you fail closed unless
 * `LW_WS_DEV_ALLOW_STATIC=1` says a developer meant it. A production deployment
 * that forgets this variable must not quietly serve subjects from an env map.
 */
export function subjectResolverFromEnv(): SubjectResolver | undefined {
  const base = (process.env.LW_WORLD_SERVICE_URL ?? '').trim().replace(/\/+$/, '');
  const token = (process.env.LOREWEAVE_INTERNAL_TOKEN ?? '').trim();
  if (!base || !token) return undefined;
  const timeout = Number(process.env.LW_SUBJECT_TIMEOUT_MS ?? '3000');
  return new HttpSubjectResolver(
    base,
    token,
    Number.isFinite(timeout) && timeout > 0 ? timeout : 3000,
  );
}
