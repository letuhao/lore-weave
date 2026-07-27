// Channel client — joins the game-server `channel` room and drives the
// channel store from the doc-20 wire messages.
//
// ⚠ `frontend-game` (MMORPG client, :5176). NOT `frontend/` (:5174).
//
// Kept separate from `ws-client.ts` on purpose: that one is the V0 echo/
// abstract-protocol path; this one speaks the game-wire contract. Both import
// `@colyseus/sdk` — the 0.17 package (the pre-0.17 name `colyseus.js` cannot
// talk to a 0.17 server: @colyseus/schema went 3→4).

import { Client, Room } from '@colyseus/sdk';

import {
  CHANNEL_MESSAGES,
  newClientRequestId,
  type TurnOutcome,
  type TurnSubmit,
  type W0Bind,
  type W1Frame,
} from './channel-protocol';
import { useChannelStore } from '@/store/channel-store';

export interface ChannelClient {
  join(url: string, opts: { jwt: string; actorEntityId?: string }): Promise<void>;
  /** Submit an action. Returns the client_request_id used — a RETRY must pass
   *  it back in `retryOf` rather than minting a new one, or the server's
   *  EVT-L3 dedup cannot recognise it as the same intent. */
  submit(action: TurnSubmit['action'], retryOf?: string): string;
  leave(): Promise<void>;
  isJoined(): boolean;
}

export function createChannelClient(): ChannelClient {
  let client: Client | null = null;
  let room: Room | null = null;

  const wire = (r: Room): void => {
    const store = useChannelStore.getState();

    r.onMessage(CHANNEL_MESSAGES.w0, (m: W0Bind) => store.applyW0(m));
    r.onMessage(CHANNEL_MESSAGES.w1, (m: W1Frame) => store.applyW1(m));
    r.onMessage(CHANNEL_MESSAGES.outcome, (m: TurnOutcome) => store.applyOutcome(m));

    // `turn.accepted` means the proposal reached the BUS — not that it was
    // applied. The in-flight marker therefore stays set until an OUTCOME
    // arrives; treating "accepted" as "done" is how a UI reports success for
    // an action the validator later rejected.
    r.onMessage(CHANNEL_MESSAGES.accepted, () => {});

    // An edge-level refusal (malformed / no actor bound / bus down). The
    // action never reached admission, so it has no outcome coming — clear the
    // marker here or the UI waits forever.
    r.onMessage(CHANNEL_MESSAGES.error, (m: { code: string; message: string }) => {
      useChannelStore.setState((s) => ({
        pending: null,
        log: [`[${m.code}] ${m.message}`, ...s.log].slice(0, 200),
      }));
    });
  };

  return {
    async join(url, opts) {
      client = new Client(url);
      room = await client.joinOrCreate('channel', {
        jwt: opts.jwt,
        actorEntityId: opts.actorEntityId,
      });
      wire(room);
    },

    submit(action, retryOf) {
      if (!room) throw new Error('channel-client: not joined');
      const id = retryOf ?? newClientRequestId();
      useChannelStore.getState().markSubmitted(id);
      const msg: TurnSubmit = { client_request_id: id, action };
      room.send(CHANNEL_MESSAGES.submit, msg);
      return id;
    },

    async leave() {
      await room?.leave();
      room = null;
      client = null;
      useChannelStore.getState().reset();
    },

    isJoined: () => room !== null,
  };
}
