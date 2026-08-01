// Channel store — the browser's projection of one DP-A16 channel.
//
// CWC-A1/A7: the server is the source of truth and this store holds ONLY the
// session projection (memory, rebuilt on every connect). It never invents
// state and never advances the turn itself — `turn_number` is copied from the
// commit, because a client that increments its own counter drifts the moment a
// rejection lands (EVT-V4: a rejection consumes no turn).
//
// ⚠ `frontend-game` (MMORPG client). Not `frontend/` (the novel app).

import { create } from 'zustand';

import {
  consumedTurn,
  outcomeLines,
  type RosterEntry,
  type TurnOutcome,
  type U64,
  type W0Bind,
  type W1Frame,
} from '@/net/channel-protocol';

export interface ChannelState {
  bound: W0Bind | null;
  selfEntityId: U64 | null;
  turnNumber: U64;
  roster: RosterEntry[];
  /** Newest-first outcome log for the UI. Bounded — a long session must not
   *  grow this without limit. */
  log: string[];
  /** In-flight submission (client_request_id) — the UI disables acting while
   *  set, and a retry reuses this id rather than minting a new one. */
  pending: string | null;
  /** Did the LAST outcome consume the player's turn? Lets the UI distinguish
   *  "your move happened" from "it failed, try again" without re-deriving the
   *  EVT-V4 rule at each call site. */
  lastConsumedTurn: boolean | null;

  applyW0: (b: W0Bind) => void;
  applyW1: (f: W1Frame) => void;
  applyOutcome: (o: TurnOutcome) => void;
  markSubmitted: (clientRequestId: string) => void;
  reset: () => void;
}

const LOG_CAP = 200;

export const useChannelStore = create<ChannelState>((set) => ({
  bound: null,
  selfEntityId: null,
  turnNumber: '0',
  roster: [],
  log: [],
  pending: null,
  lastConsumedTurn: null,

  applyW0: (b) => set({ bound: b }),

  applyW1: (f) =>
    set({
      selfEntityId: f.self.entity_id,
      turnNumber: f.turn_number,
      roster: f.roster,
    }),

  applyOutcome: (o) =>
    set((s) => ({
      // Copied from the commit, never incremented locally.
      turnNumber: o.turn_number,
      log: [...outcomeLines(o), ...s.log].slice(0, LOG_CAP),
      // Clear the in-flight marker on ANY outcome — including the two
      // non-resolutions. A UI that only cleared on `resolved` would wedge
      // itself permanently the first time a rejection came back.
      pending: null,
      // A consumed turn is the only case where the player's slot is gone;
      // exposed so the UI can distinguish "your move failed, try again" from
      // "your move happened".
      lastConsumedTurn: consumedTurn(o),
    })),

  markSubmitted: (clientRequestId) => set({ pending: clientRequestId }),

  reset: () =>
    set({
      bound: null,
      selfEntityId: null,
      turnNumber: '0',
      roster: [],
      log: [],
      pending: null,
      lastConsumedTurn: null,
    }),
}));
