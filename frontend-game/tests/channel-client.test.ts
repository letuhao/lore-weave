// Channel-client wiring tests — a fake Room stands in for Colyseus so the
// message→store path is provable without a server.
//
// ⚠ frontend-game (MMORPG client). Not frontend/.

import { describe, expect, it, beforeEach, vi } from 'vitest';

import { CHANNEL_MESSAGES } from '@/net/channel-protocol';
import { useChannelStore } from '@/store/channel-store';

// Minimal Room stand-in: records handlers + sends, and lets a test push a
// server message in.
class FakeRoom {
  handlers = new Map<string, (m: unknown) => void>();
  sent: { type: string; msg: unknown }[] = [];
  onMessage(type: string, cb: (m: unknown) => void) {
    this.handlers.set(type, cb);
  }
  send(type: string, msg: unknown) {
    this.sent.push({ type, msg });
  }
  async leave() {}
  emit(type: string, msg: unknown) {
    const h = this.handlers.get(type);
    if (!h) throw new Error(`no handler registered for ${type}`);
    h(msg);
  }
}

const fake = new FakeRoom();
vi.mock('@colyseus/sdk', () => ({
  Client: class {
    async joinOrCreate() {
      return fake;
    }
  },
  Room: class {},
}));

const { createChannelClient } = await import('@/net/channel-client');

describe('channel client', () => {
  beforeEach(() => {
    useChannelStore.getState().reset();
    fake.handlers.clear();
    fake.sent = [];
  });

  it('registers a handler for every server message it expects', async () => {
    const c = createChannelClient();
    await c.join('ws://x', { jwt: 'dev_token' });
    for (const name of [
      CHANNEL_MESSAGES.w0,
      CHANNEL_MESSAGES.w1,
      CHANNEL_MESSAGES.outcome,
      CHANNEL_MESSAGES.accepted,
      CHANNEL_MESSAGES.error,
    ]) {
      expect(fake.handlers.has(name), `no handler for ${name}`).toBe(true);
    }
  });

  it('drives the store from W0/W1/outcome', async () => {
    const c = createChannelClient();
    await c.join('ws://x', { jwt: 'dev_token' });

    fake.emit(CHANNEL_MESSAGES.w0, {
      session_id: 's1',
      reality_id: 'r1',
      channel_id: '1',
      ruleset_digest: '0'.repeat(64),
      from_tokens: { '1': '9' },
      client_protocol: 1,
    });
    expect(useChannelStore.getState().bound?.from_tokens['1']).toBe('9');

    fake.emit(CHANNEL_MESSAGES.w1, {
      self: { entity_id: '1' },
      turn_number: '3',
      roster: [
        { entity_id: '2', display_name: 'e2', disposition: 'hostile', condition: 'healthy' },
      ],
    });
    expect(useChannelStore.getState().turnNumber).toBe('3');
    expect(useChannelStore.getState().roster).toHaveLength(1);

    fake.emit(CHANNEL_MESSAGES.outcome, {
      channel_event_id: '10',
      kind: 'resolved',
      turn_number: '4',
      detail: { events: ['1 strikes 2'] },
    });
    expect(useChannelStore.getState().turnNumber).toBe('4');
    expect(useChannelStore.getState().log[0]).toBe('1 strikes 2');
  });

  it('a RETRY reuses the client_request_id — that is what makes it idempotent', async () => {
    const c = createChannelClient();
    await c.join('ws://x', { jwt: 'dev_token' });
    const action = { vocabulary: 'combat_v1', tool: 'defend', params: {} };

    const first = c.submit(action);
    const retry = c.submit(action, first);
    expect(retry).toBe(first);
    // Kill-mutation: mint a new id on retry → the server sees a SECOND
    // distinct intent and executes twice.
    expect(fake.sent).toHaveLength(2);
    const ids = fake.sent.map((s) => (s.msg as { client_request_id: string }).client_request_id);
    expect(ids[0]).toBe(ids[1]);
  });

  it('`turn.accepted` does NOT clear the in-flight marker — only an outcome does', async () => {
    const c = createChannelClient();
    await c.join('ws://x', { jwt: 'dev_token' });
    const id = c.submit({ vocabulary: 'combat_v1', tool: 'defend', params: {} });
    expect(useChannelStore.getState().pending).toBe(id);

    // Accepted = it reached the BUS, not that it was applied. Reporting
    // success here would claim an action the validator may still reject.
    fake.emit(CHANNEL_MESSAGES.accepted, { client_request_id: id });
    expect(useChannelStore.getState().pending).toBe(id);

    fake.emit(CHANNEL_MESSAGES.outcome, {
      channel_event_id: '11',
      kind: 'rejected',
      turn_number: '4',
      detail: { stage: 'decision-vocabulary', user_message: 'nope' },
    });
    expect(useChannelStore.getState().pending).toBeNull();
  });

  it('an edge error clears the marker — it has no outcome coming', async () => {
    const c = createChannelClient();
    await c.join('ws://x', { jwt: 'dev_token' });
    c.submit({ vocabulary: 'combat_v1', tool: 'defend', params: {} });
    // Kill-mutation: ignore turn.error → the UI waits forever for an outcome
    // that will never arrive, because the action never reached admission.
    fake.emit(CHANNEL_MESSAGES.error, { code: 'bus_unavailable', message: 'down' });
    expect(useChannelStore.getState().pending).toBeNull();
    expect(useChannelStore.getState().log[0]).toContain('bus_unavailable');
  });

  it('submitting before join is a loud error, not a silent no-op', () => {
    const c = createChannelClient();
    expect(() => c.submit({ vocabulary: 'combat_v1', tool: 'defend', params: {} })).toThrow(
      /not joined/,
    );
  });
});
