// Client-wire projection, CONSUMER half — committed event → `TurnOutcome`
// (`contracts/game-wire/turn.schema.json`, doc 20 §6).
//
// This is the second side of the game-wire contract. The producer half lives
// in `services/commit-service/src/wire.rs`; the two are joined only by the
// schema file, which is exactly the drift surface the Frontend-Tool Contract
// standard exists for ("BE schema ↔ FE resolver joined only by the wire — a
// drift passes unit tests yet kills the live loop"). Both sides therefore
// assert against the schema, not against each other.
//
// Two doc-20 rules are structural here:
//   • CWC-A2 — every 64-bit id is a `string` in these types. Not `number`:
//     `channel_event_id` and `turn_number` are BIGINT server-side and JS
//     silently corrupts them past 2^53. Typing them as strings makes the
//     corruption unrepresentable rather than merely discouraged.
//   • CWC-A6 — `resolved` / `discarded` / `rejected` are three DIFFERENT
//     things and the UI must not collapse them. Only `resolved` consumed a
//     turn; the other two leave `turn_number` untouched (EVT-V4).

export type OutcomeKind = 'resolved' | 'discarded' | 'rejected';

/** The 5-variant sim-core closed set (REC-63 as amended by REC-78). */
export type DiscardReason =
  | 'duplicate'
  | 'precondition_failed'
  | 'superseded'
  | 'expired'
  | 'quarantined';

export interface ResolvedDetail {
  events: string[];
}
export interface DiscardDetail {
  reason: DiscardReason;
  user_message: string;
}
export interface RejectDetail {
  stage: string;
  user_message: string;
}

export interface TurnOutcome {
  /** CWC-A2: decimal string, never a number. */
  channel_event_id: string;
  kind: OutcomeKind;
  /** CWC-A2 + DP-A17: decimal string; advances on `resolved` only. */
  turn_number: string;
  detail: ResolvedDetail | DiscardDetail | RejectDetail;
}

/**
 * A committed event as it arrives off the proposal/event bus — the shape
 * `commit-service` writes through `dp-kernel::ChannelWriter` and the platform
 * publisher fans out. Numeric fields arrive as strings or numbers depending on
 * the JSON encoder upstream, so the projection normalizes rather than trusting.
 */
export interface CommittedEvent {
  event_type: string;
  channel_event_id: string | number;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

/**
 * Normalize a wire integer to its decimal-string form WITHOUT going through
 * `number` (CWC-A2). A JSON encoder that already emitted a string is trusted
 * as-is; a `number` is accepted only when it is a safe integer, because a
 * larger one has ALREADY lost precision by the time it reaches us — silently
 * passing it on would launder the corruption downstream.
 */
export function toU64String(v: string | number | undefined, field: string): string {
  if (typeof v === 'string') {
    if (!/^(0|[1-9][0-9]{0,19})$/.test(v)) {
      throw new Error(`${field}: not a u64 decimal string: ${JSON.stringify(v)}`);
    }
    return v;
  }
  if (typeof v === 'number') {
    if (!Number.isSafeInteger(v)) {
      throw new Error(
        `${field}: arrived as a JS number beyond 2^53 (${v}) — precision was ` +
          `already lost upstream; the producer must emit a string (CWC-A2)`,
      );
    }
    return String(v);
  }
  throw new Error(`${field}: missing`);
}

/**
 * Project one committed event into the client DTO. Returns `null` for events
 * that are not turn outcomes (the stream carries every committed event; a
 * room projects the subset its clients render).
 */
export function projectTurnOutcome(ev: CommittedEvent): TurnOutcome | null {
  const meta = ev.metadata ?? {};
  const payload = ev.payload ?? {};
  const channel_event_id = toU64String(
    ev.channel_event_id as string | number,
    'channel_event_id',
  );
  // turn_number is authoritative from the COMMIT — never recomputed here. A
  // consumer that increments its own counter would drift the moment a
  // rejection lands (EVT-V4: rejections do not advance the turn).
  const turn_number = toU64String(meta.turn_number as string | number, 'turn_number');

  switch (ev.event_type) {
    case 'turn.resolved':
      return {
        channel_event_id,
        kind: 'resolved',
        turn_number,
        // D1 — structured domain facts, rendered to lines here (rendering is
        // the CLIENT's job; the wire carries facts, not prose).
        detail: { events: (asDomainEvents(payload.events)).map(renderEvent) },
      };
    case 'turn.discarded':
      return {
        channel_event_id,
        kind: 'discarded',
        turn_number,
        detail: {
          reason: (payload.discard_reason as DiscardReason) ?? 'precondition_failed',
          user_message: (payload.user_message as string) ?? 'The world moved on.',
        },
      };
    case 'proposal.rejected':
      return {
        channel_event_id,
        kind: 'rejected',
        turn_number,
        detail: {
          stage: (payload.rejected_at_stage as string) ?? 'unknown',
          user_message: (payload.reason as string) ?? 'That action was not allowed.',
        },
      };
    default:
      return null;
  }
}


// ── D1/D2: structured domain facts ──────────────────────────────────────────

/** A committed combat fact. Mirrors `commit-service::domain::CombatEvent`; the
 *  two are joined only by this shape, so the closed `type` set is asserted in
 *  the tests rather than trusted. */
export type DomainEvent =
  | { type: 'struck'; attacker: string; target: string; damage: number; hp_left: number }
  | { type: 'missed'; attacker: string; target: string }
  | { type: 'defended'; actor: string }
  | { type: 'moved'; actor: string; stance: string }
  | { type: 'fled'; actor: string }
  | { type: 'downed'; target: string };

export function asDomainEvents(raw: unknown): DomainEvent[] {
  return Array.isArray(raw) ? (raw as DomainEvent[]) : [];
}

/** Render one fact as a line. Deliberately trivial and client-side: the SERVER
 *  ships facts, the client decides words (and, later, locale — CWC-D7). */
export function renderEvent(e: DomainEvent): string {
  switch (e.type) {
    case 'struck':
      return `${e.attacker} strikes ${e.target} for ${e.damage} (${e.hp_left} left)`;
    case 'missed':
      return `${e.attacker} finds no target`;
    case 'defended':
      return `${e.actor} braces`;
    case 'moved':
      return `${e.actor} repositions (${e.stance})`;
    case 'fled':
      return `${e.actor} flees`;
    case 'downed':
      return `${e.target} goes down`;
  }
}

/** The replayed view of a channel (D2): W1 is a FOLD of the committed stream,
 *  not a second read API that could disagree with the log. */
export interface ChannelView {
  actors: Record<string, { hp?: number; down: boolean; fled: boolean; stance?: string }>;
  turn_number: string;
  last_event_id: string;
}

export function emptyView(): ChannelView {
  return { actors: {}, turn_number: '0', last_event_id: '0' };
}

function actor(v: ChannelView, id: string) {
  return (v.actors[id] ??= { down: false, fled: false });
}

/** Fold one committed event into the view. Pure + idempotent per event id, so
 *  a replay from `0` and a live tail produce the same state (GDA-A7). */
export function foldEvent(view: ChannelView, ev: CommittedEvent): ChannelView {
  const outcome = projectTurnOutcome(ev);
  if (outcome) view.turn_number = outcome.turn_number;
  if (ev.channel_event_id !== undefined) {
    view.last_event_id = toU64String(ev.channel_event_id, 'channel_event_id');
  }
  for (const e of asDomainEvents(ev.payload?.events)) {
    switch (e.type) {
      case 'struck':
        actor(view, e.target).hp = e.hp_left;
        break;
      case 'downed':
        actor(view, e.target).down = true;
        break;
      case 'fled':
        actor(view, e.actor).fled = true;
        break;
      case 'moved':
        actor(view, e.actor).stance = e.stance;
        break;
      default:
        break;
    }
  }
  return view;
}
