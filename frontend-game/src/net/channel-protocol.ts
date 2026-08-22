// The CHANNEL protocol — the doc-20 client wire contract as the browser sees
// it (`contracts/game-wire/`). This is the THIRD side of that contract:
//
//   commit-service::wire  (Rust, producer)
//     ↕  contracts/game-wire/*.schema.json   ← the only thing joining them
//   game-server/src/wire  (TS, room projection)
//     ↕
//   frontend-game/src/net (TS, browser)      ← here
//
// Each side asserts against the SCHEMA, never against another side. Two ends
// that agree with each other but not the contract is exactly the drift that
// passes every unit test and dies live.
//
// ⚠ This file is for `frontend-game` (the MMORPG client, :5176). The other
// SPA — `frontend/` (:5174) — is the novel-workflow app and has nothing to do
// with this protocol.
//
// Superseding note: `protocol.ts` holds the V0 placeholder shapes
// (`enter-zone` / `player-action` / `zone-snapshot`) invented before the wire
// contract existed. They are NOT the contract and are being replaced by these
// as each surface migrates.

/** CWC-A2 — a 64-bit server id, ALWAYS a decimal string on the wire. */
export type U64 = string;

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

/**
 * `turn.outcome` — projected from a committed event. THREE distinct kinds the
 * UI must not collapse (CWC-A6):
 *   • `resolved`  — it happened; the turn was consumed.
 *   • `discarded` — a valid intent the world moved out from under; NO turn
 *                   consumed; re-read the frame and try again.
 *   • `rejected`  — the validator said no; NO turn consumed; retry is free.
 * Showing "not allowed" for a `discarded` would be a lie to the player, and
 * burning a turn slot on either non-resolution contradicts EVT-V4.
 */
export interface TurnOutcome {
  channel_event_id: U64;
  kind: OutcomeKind;
  turn_number: U64;
  detail: ResolvedDetail | DiscardDetail | RejectDetail;
}

/** `w0.bind` — the bind ack (doc 20 §2). */
export interface W0Bind {
  session_id: string;
  reality_id: string;
  channel_id: U64;
  ruleset_digest: string;
  /** DP-Ch18 per-channel resume cursors: channel_id → last event seen. */
  from_tokens: Record<string, U64>;
  client_protocol: number;
}

export interface RosterEntry {
  entity_id: U64;
  display_name: string;
  disposition: 'friendly' | 'neutral' | 'hostile';
  /** REC-79 — condition travels BESIDE identity, never inside the id token. */
  condition: 'healthy' | 'wounded' | 'critical' | 'down';
}

/** `w1.frame` — the first frame (doc 20 §3). */
/**
 * `A4` — WHERE the driven actor is.
 *
 * OPTIONAL, and its absence is a real answer rather than a gap: an actor that
 * has never been sited is nowhere, and until a reality has a world that is every
 * actor. The room also omits it when the lookup fails, because a location is
 * ADVISORY — a space-view outage must cost a line of text, never a join.
 *
 * `place_name` is present only when the node is a `Domain` carrying a `place`;
 * `PF_001` makes that 1:1 and no other kind has one.
 */
export interface FramePlace {
  node: U64;
  /** The reality's own word for the level (`DP-A13`). */
  level_name: string;
  place_name?: string;
}

export interface W1Frame {
  self: { entity_id: U64; hp?: number; down?: boolean; fled?: boolean };
  turn_number: U64;
  roster: RosterEntry[];
  place?: FramePlace;
}

/**
 * `turn.submit` — what the player sends. Note what is ABSENT: there is no
 * actor field. The room stamps identity from the authenticated session; a
 * client that could name its own actor could act as another player.
 */
export interface TurnSubmit {
  /** Client-minted. A retry MUST reuse it — that is what makes a flaky link
   *  safe (EVT-L3 idempotency triple, middle member). */
  client_request_id: string;
  /** The `contracts/agent` Decision envelope — the same object an NPC's
   *  LlmDriver emits (AGT-A3: four drivers, one wire shape). */
  action: { vocabulary: string; tool: string; params: Record<string, unknown> };
}

export type ChannelServerMessage =
  | { kind: 'w0.bind'; data: W0Bind }
  | { kind: 'w1.frame'; data: W1Frame }
  | { kind: 'turn.outcome'; data: TurnOutcome }
  | { kind: 'turn.accepted'; data: { client_request_id: string } }
  | { kind: 'turn.error'; data: { code: string; message: string } };

/** The wire message names, kept in one place so a listener cannot be
 *  registered for a name the server never sends. */
export const CHANNEL_MESSAGES = {
  w0: 'w0.bind',
  w1: 'w1.frame',
  outcome: 'turn.outcome',
  accepted: 'turn.accepted',
  error: 'turn.error',
  submit: 'turn.submit',
} as const;

/** Mint a `client_request_id`. Separate function because the SAME id must be
 *  reused on retry — minting inside a retry loop is the bug this prevents. */
export function newClientRequestId(): string {
  return crypto.randomUUID();
}

/**
 * Did this outcome consume the player's turn? Only `resolved` does (EVT-V4).
 * The UI asks this rather than testing `kind === 'resolved'` inline, so the
 * rule lives in one place instead of being re-derived at every call site.
 */
export function consumedTurn(o: TurnOutcome): boolean {
  return o.kind === 'resolved';
}

/** Human-facing line for an outcome, for a log/toast surface. */
export function outcomeLines(o: TurnOutcome): string[] {
  switch (o.kind) {
    case 'resolved':
      return (o.detail as ResolvedDetail).events;
    case 'discarded':
      return [(o.detail as DiscardDetail).user_message];
    case 'rejected':
      return [(o.detail as RejectDetail).user_message];
  }
}
