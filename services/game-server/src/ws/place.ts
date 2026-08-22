/**
 * `A4` — WHERE the driven actor is, for the frame the browser renders.
 *
 * The twin of `subject.ts`, and deliberately so: that file answers *"who does
 * this user drive"*, this one answers *"where is that actor"*, and the room asks
 * both at bind. Same shape, same failure discipline, same reason for each — a
 * second pattern here would be a second set of edge cases to get wrong.
 *
 * # It is ADVISORY, and that is the whole difference
 *
 * A failed subject lookup means the room cannot know who is acting, so it binds
 * nobody. A failed PLACE lookup means the room cannot say where they are — which
 * is a poorer frame, not a wrong one. So every failure here degrades to
 * `undefined` and the frame ships without a location, rather than refusing the
 * join.
 *
 * **That asymmetry is the thing to keep.** Making this fail closed would let a
 * space-view outage take down joins that never needed it.
 */

/** What world-service answers. Three distinct facts, mirroring `Whereabouts`. */
export type Whereabouts =
  | { kind: 'unbound' }
  | {
      kind: 'in_cell';
      entity_id: number;
      node: number;
      /** The node's `MapKind`. Named `node_kind` so it cannot collide with the
       *  `kind` discriminant -- a duplicate JSON key silently wins. */
      node_kind?: string;
      level_name: string;
      place_name: string | null;
    }
  | { kind: 'not_in_a_cell'; location_kind: string };

/** What the room puts on the frame. Flattened, because the browser renders a
 *  line of text and has no use for the discriminant. */
export interface FramePlace {
  node: number;
  /** The reality's own word for the level (`DP-A13`). */
  level_name: string;
  /** Present only when the node is a `Domain` carrying a `place`. */
  place_name?: string;
}

export interface PlaceResolver {
  resolve(realityId: string, entityId: number): Promise<FramePlace | undefined>;
}

/** The real resolver. Node's global `fetch` — no new dependency. */
export class HttpPlaceResolver implements PlaceResolver {
  constructor(
    private readonly baseUrl: string,
    private readonly internalToken: string,
    private readonly timeoutMs = 3000,
  ) {}

  async resolve(realityId: string, entityId: number): Promise<FramePlace | undefined> {
    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}/internal/v1/space/where-is`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'X-Internal-Token': this.internalToken,
        },
        body: JSON.stringify({ reality_id: realityId, entity_id: entityId }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch {
      // Advisory: an unreachable world-service costs a location, not a join.
      return undefined;
    }
    if (!res.ok) return undefined;

    let body: { whereabouts?: Whereabouts };
    try {
      body = (await res.json()) as { whereabouts?: Whereabouts };
    } catch {
      return undefined;
    }
    const w = body.whereabouts;
    if (!w || w.kind !== 'in_cell') {
      // `unbound` and `not_in_a_cell` are REAL ANSWERS, not failures -- and both
      // mean the same thing to a frame that can only render a cell. They are
      // kept distinct on the wire because they are distinct facts; they collapse
      // HERE, at the one boundary where the difference genuinely does not
      // matter, and this comment is why that is not the bug `Whereabouts`
      // exists to prevent.
      return undefined;
    }
    return {
      node: w.node,
      level_name: w.level_name,
      ...(w.place_name ? { place_name: w.place_name } : {}),
    };
  }
}

/**
 * Build one from the environment, or `undefined`.
 *
 * Reads the SAME two variables `subjectResolverFromEnv` does, because they name
 * the same service. A third variable for one more endpoint on one more path of
 * the same host is a configuration surface nobody would keep in step.
 */
export function placeResolverFromEnv(): PlaceResolver | undefined {
  const base = (process.env.LW_WORLD_SERVICE_URL ?? '').trim().replace(/\/+$/, '');
  const token = (process.env.LOREWEAVE_INTERNAL_TOKEN ?? '').trim();
  if (!base || !token) return undefined;
  const timeout = Number(process.env.LW_PLACE_TIMEOUT_MS ?? '3000');
  return new HttpPlaceResolver(
    base,
    token,
    Number.isFinite(timeout) && timeout > 0 ? timeout : 3000,
  );
}
