import { KalReadController } from '../src/kal/kal-read.controller.js';
import { resetConfigForTest } from '../src/config/config.js';

/**
 * state@as_of forwarding (plan T6). The KAL maps the read to glossary's
 * /internal/books/{id}/state, threads `as_of`, pins X-User-Id from the guard-validated
 * kalUserId (anti-spoof), and shapes the response.
 *
 * The load-bearing case is the LAST one: a missing `as_of` must NOT be quietly repaired
 * here. The gateway carries no domain logic (decision B2), so the rule lives once, in the
 * service that owns it, and the gateway's job is to let its 400 through.
 */
describe('KalReadController.state', () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'svc-token';
    process.env.GLOSSARY_SERVICE_URL = 'http://glossary-service:8088';
    process.env.JWT_SECRET = 'test_secret_at_least_32_chars_long_xx';
    process.env.BOOK_SERVICE_URL = 'http://book-service:8082';
    resetConfigForTest();
    fetchMock = jest.fn();
    (globalThis as { fetch: unknown }).fetch = fetchMock;
  });

  function ok(body: unknown) {
    return { ok: true, status: 200, text: async () => JSON.stringify(body) } as unknown as Response;
  }

  const sampleBody = {
    book_id: 'b1',
    as_of_ordinal: 30,
    entities: [
      { entity_id: 'e1', facts: [{ attr: 'rank', value: 'inner disciple', fact_kind: 'attribute', valid_from_ordinal: 25 }] },
    ],
  };

  it('forwards as_of to glossary and returns the state, pinning the guard identity', async () => {
    fetchMock.mockResolvedValue(ok(sampleBody));
    const ctrl = new KalReadController();
    const req = { headers: { 'x-user-id': 'spoofed' }, kalUserId: 'real-user' };
    const out = (await ctrl.state('b1', '30', req as never)) as Record<string, unknown>;

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/internal/books/b1/state');
    expect(url).toContain('as_of=30');
    expect((init.headers as Record<string, string>)['X-User-Id']).toBe('real-user'); // NOT 'spoofed'
    expect((init.headers as Record<string, string>)['X-Internal-Token']).toBe('svc-token');

    expect(out.as_of_ordinal).toBe(30);
    expect(out.entities).toEqual(sampleBody.entities);
    // Every temporal read advertises what each substrate can honor (§12.5.1 / A5). Without
    // it a consumer cannot tell "no facts at this position" from "this source ignored as_of".
    expect(out.temporal_capability).toMatchObject({ glossary: 'ordinal_valid_time' });
  });

  it('does not pass a downstream non-array through as the entity list', async () => {
    // The keyed-by-id shape is the one that matters: a nullish-coalescing guard (`?? []`)
    // accepts it silently, and the consumer then iterates an object and finds nothing while
    // the contract promised an array. Only an isArray check refuses it.
    fetchMock.mockResolvedValue(
      ok({ book_id: 'b1', as_of_ordinal: 7, entities: { e1: { facts: [] } } }),
    );
    const ctrl = new KalReadController();
    const out = (await ctrl.state('b1', '7', { headers: {}, kalUserId: 'u' } as never)) as Record<string, unknown>;
    expect(Array.isArray(out.entities)).toBe(true);
    expect(out.entities).toEqual([]);
  });

  it('propagates the service 400 for a missing as_of instead of defaulting it', async () => {
    // The gateway must not invent a position. Glossary refuses; the KAL forwards the refusal.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => '{"code":"GLOSS_BAD_REQUEST","message":"as_of query param required"}',
    } as unknown as Response);
    const ctrl = new KalReadController();

    await expect(ctrl.state('b1', undefined, { headers: {}, kalUserId: 'u' } as never)).rejects.toMatchObject({
      status: 400,
    });
    // And it really did reach the service — a gateway that short-circuited with its own 400
    // would pass the assertion above while owning a second copy of the rule.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain('/internal/books/b1/state');
    expect(url).not.toContain('as_of=');
  });
});
