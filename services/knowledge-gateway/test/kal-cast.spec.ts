import { KalReadController } from '../src/kal/kal-read.controller.js';
import { resetConfigForTest } from '../src/config/config.js';

/**
 * `cast` — the KAL's DETAIL read (plan T38 B1/B2).
 *
 * `roster` is projection-restricted to id+name+kind, and T38's census found that **0 of 10**
 * pinned consumers could migrate onto it: four went straight to glossary's `entities/by-ids`
 * for the detail, two need `aliases`, one needs `kind` + `short_description`. `cast` is the
 * missing rung — `roster`'s page shape with the projection those consumers actually read.
 *
 * The load-bearing case is the LAST one. `truncated` is returned explicitly instead of being
 * inferred from a short page, because a caller that stops at `items.length < limit` is
 * guessing — and the guess is wrong exactly when the upstream capped it. That silent
 * truncation once cut a deep book's cast at ~100 while reporting a complete-looking count.
 */
describe('KalReadController.cast', () => {
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

  const upstream = {
    items: [
      {
        entity_id: 'e1',
        cached_name: 'Kai',
        // The LIST endpoint's REAL key. The first cut of this mock said
        // `cached_aliases` (the by-ids shape) and passed against a controller that
        // read the same wrong key — a mock and an implementation agreeing about a
        // field neither had checked.
        aliases: ['Kai', 'the heir'],
        short_description: 'the betrayed heir',
        kind_code: 'character',
      },
    ],
    next_cursor: null,
  };

  it('carries the fields roster strips — that is the whole reason it exists', async () => {
    fetchMock.mockResolvedValue(ok(upstream));
    const ctrl = new KalReadController();
    const req = { headers: {}, kalUserId: 'real-user' };

    const out = (await ctrl.cast('b1', undefined, undefined, req as never)) as {
      items: Array<Record<string, unknown>>;
    };

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain('/internal/books/b1/entities');
    expect(out.items[0]).toEqual({
      entity_id: 'e1',
      name: 'Kai',
      cached_name: 'Kai',
      kind: 'character',
      aliases: ['Kai', 'the heir'],
      short_description: 'the betrayed heir',
    });
  });

  it('defaults the projection safely when the upstream omits a field', async () => {
    // A missing alias array must become [], never undefined: a consumer iterating it would
    // throw on a book whose entities have no recorded surface forms.
    fetchMock.mockResolvedValue(ok({ items: [{ entity_id: 'e2', name: 'Mira' }], next_cursor: null }));
    const ctrl = new KalReadController();

    const out = (await ctrl.cast('b1', undefined, undefined, { headers: {}, kalUserId: 'u' } as never)) as {
      items: Array<Record<string, unknown>>;
    };

    expect(out.items[0]).toEqual({
      entity_id: 'e2',
      name: 'Mira',
      cached_name: 'Mira',
      kind: null,
      aliases: [],
      short_description: null,
    });
  });

  it('forwards the keyset cursor and limit rather than re-deciding them', async () => {
    fetchMock.mockResolvedValue(ok({ items: [], next_cursor: 'c2' }));
    const ctrl = new KalReadController();

    await ctrl.cast('b1', 'c1', '25', { headers: {}, kalUserId: 'u' } as never);

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain('cursor=c1');
    expect(url).toContain('limit=25');
  });

  it('reports truncation EXPLICITLY, so no caller has to infer it from a short page', async () => {
    fetchMock.mockResolvedValue(ok({ items: [{ entity_id: 'e1', name: 'Kai' }], next_cursor: 'c2' }));
    const ctrl = new KalReadController();

    const out = (await ctrl.cast('b1', undefined, '1', { headers: {}, kalUserId: 'u' } as never)) as {
      truncated: boolean;
      next_cursor: string | null;
    };

    expect(out.next_cursor).toBe('c2');
    expect(out.truncated).toBe(true);
  });

  it('is not truncated when the upstream drained to the end', async () => {
    // The counterweight: without it, `truncated: true` hard-coded would pass the test above
    // and every consumer would drain forever.
    fetchMock.mockResolvedValue(ok(upstream));
    const ctrl = new KalReadController();

    const out = (await ctrl.cast('b1', undefined, undefined, { headers: {}, kalUserId: 'u' } as never)) as {
      truncated: boolean;
    };

    expect(out.truncated).toBe(false);
  });

  // ── cast/by-ids (T38 B5) ──────────────────────────────────────────────────

  it('by-ids returns the SAME projection as cast, so one concept has one shape', async () => {
    fetchMock.mockResolvedValue(ok({ items: [{
      entity_id: 'e1', cached_name: 'Kai', kind_code: 'character',
      cached_aliases: ['the heir'], short_description: 'the betrayed heir',
    }] }));
    const ctrl = new KalReadController();

    const out = (await ctrl.castByIds('b1', { entity_ids: ['e1'] }, { headers: {}, kalUserId: 'u' } as never)) as {
      items: Array<Record<string, unknown>>;
    };

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/internal/books/b1/entities/by-ids');
    expect(JSON.parse(String(init.body))).toEqual({ entity_ids: ['e1'] });
    expect(out.items[0]).toEqual({
      entity_id: 'e1',
      name: 'Kai',
      cached_name: 'Kai',
      kind: 'character',
      aliases: ['the heir'],
      short_description: 'the betrayed heir',
    });
  });

  it('an EMPTY id list is a no-op, never "the whole book"', async () => {
    // The inversion this guards against turns a no-op pin into a full-cast read on every
    // empty call — expensive, and invisible because the answer looks richer, not wrong.
    const ctrl = new KalReadController();

    const out = (await ctrl.castByIds('b1', { entity_ids: [] }, { headers: {}, kalUserId: 'u' } as never)) as {
      items: unknown[];
    };

    expect(out.items).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards include_attributes and carries the values back', async () => {
    fetchMock.mockResolvedValue(ok({ items: [{
      entity_id: 'e1', cached_name: 'Kai', kind_code: 'character',
      attributes: [{ code: 'rank', value: 'inner disciple' }],
    }] }));
    const ctrl = new KalReadController();

    const out = (await ctrl.castByIds('b1', { entity_ids: ['e1'], include_attributes: true },
      { headers: {}, kalUserId: 'u' } as never)) as { items: Array<Record<string, unknown>> };

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ entity_ids: ['e1'], include_attributes: true });
    expect(out.items[0].attributes).toEqual([{ code: 'rank', value: 'inner disciple' }]);
  });

  it('omits attributes entirely when they were not asked for', async () => {
    // The counterweight: always returning `attributes: []` would let a caller that FORGOT the
    // flag read "this entity has no attributes" instead of "I did not ask".
    fetchMock.mockResolvedValue(ok({ items: [{ entity_id: 'e1', cached_name: 'Kai',
      attributes: [{ code: 'rank', value: 'inner disciple' }] }] }));
    const ctrl = new KalReadController();

    const out = (await ctrl.castByIds('b1', { entity_ids: ['e1'] },
      { headers: {}, kalUserId: 'u' } as never)) as { items: Array<Record<string, unknown>> };

    expect('attributes' in out.items[0]).toBe(false);
  });
});
