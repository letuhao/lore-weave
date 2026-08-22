import { hasBookAccess, hasProjectAccess } from '../src/auth/grants.js';
import { resetConfigForTest } from '../src/config/config.js';

/**
 * T55/g — `hasProjectAccess`, and the shared `/access` reader both grant checks now run
 * through (spec §8.7).
 *
 * `grants.ts` had NO test file before this one. That is worth saying plainly rather than
 * quietly fixing: it is the KAL's entire user-mode authorisation, its every failure mode is
 * "fail closed", and a fail-closed bug is invisible in production until someone is wrongly
 * let IN — the direction that does not generate a support ticket.
 *
 * The cases below are the ones the extraction could have broken: a non-200, a transport
 * throw, a `none` level, an inactive lifecycle, and the cache. The last is the sharpest —
 * **positives are cached and negatives are not**, so a freshly-granted user is not locked out
 * for the TTL, and the key is NAMESPACED so a project id equal to a book id cannot answer for
 * the other.
 */

const REAL_FETCH = globalThis.fetch;

function stubFetch(impl: (url: string) => { ok: boolean; json?: () => Promise<unknown> } | Error) {
  const calls: string[] = [];
  globalThis.fetch = (async (url: string) => {
    calls.push(String(url));
    const out = impl(String(url));
    if (out instanceof Error) throw out;
    return { ok: out.ok, json: out.json ?? (async () => ({})) } as Response;
  }) as typeof fetch;
  return calls;
}

function grants(level: string, lifecycle = 'active') {
  return { ok: true, json: async () => ({ grant_level: level, lifecycle_state: lifecycle }) };
}

describe('grants — the shared /access reader', () => {
  beforeEach(() => {
    process.env.KAL_JWT_SECRET = 'test_secret_at_least_32_chars_long_xx';
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    process.env.BOOK_SERVICE_URL = 'http://book:8080';
    process.env.KNOWLEDGE_SERVICE_URL = 'http://knowledge:8092';
    resetConfigForTest();
  });
  afterEach(() => {
    globalThis.fetch = REAL_FETCH;
  });

  it('asks the OWNING service, on the project path', async () => {
    const calls = stubFetch(() => grants('owner'));
    await expect(hasProjectAccess('p1', 'u1')).resolves.toBe(true);
    expect(calls[0]).toBe('http://knowledge:8092/internal/projects/p1/access?user_id=u1');
  });

  it('asks BOOK-service for a book, not knowledge-service', async () => {
    const calls = stubFetch(() => grants('view'));
    await expect(hasBookAccess('b1', 'u1')).resolves.toBe(true);
    expect(calls[0]).toBe('http://book:8080/internal/books/b1/access?user_id=u1');
  });

  it.each([['none'], ['']])('treats %p as NO access', async (level) => {
    stubFetch(() => grants(level));
    await expect(hasProjectAccess(`p-${level}`, 'u1')).resolves.toBe(false);
  });

  it('treats a non-active lifecycle as no access, and an EMPTY one as fine', async () => {
    stubFetch(() => grants('edit', 'archived'));
    await expect(hasProjectAccess('p-arch', 'u1')).resolves.toBe(false);
    stubFetch(() => grants('edit', ''));
    await expect(hasProjectAccess('p-empty', 'u1')).resolves.toBe(true);
  });

  it('fails CLOSED on a non-200 and on a transport throw', async () => {
    stubFetch(() => ({ ok: false }));
    await expect(hasProjectAccess('p-500', 'u1')).resolves.toBe(false);
    stubFetch(() => new Error('ECONNREFUSED'));
    await expect(hasProjectAccess('p-down', 'u1')).resolves.toBe(false);
  });

  it('fails CLOSED on a body that is not the contract', async () => {
    stubFetch(() => ({ ok: true, json: async () => { throw new Error('not json'); } }));
    await expect(hasProjectAccess('p-junk', 'u1')).resolves.toBe(false);
  });

  it('caches a POSITIVE but never a negative', async () => {
    let calls = stubFetch(() => grants('owner'));
    await hasProjectAccess('p-cache', 'u1');
    await hasProjectAccess('p-cache', 'u1');
    expect(calls.length).toBe(1); // second answered from cache

    // A negative must NOT stick, or a user granted access seconds ago stays locked out.
    calls = stubFetch(() => grants('none'));
    await hasProjectAccess('p-neg', 'u1');
    await hasProjectAccess('p-neg', 'u1');
    expect(calls.length).toBe(2);
  });

  it('NAMESPACES the cache so a project id cannot answer for a book id', async () => {
    // The id is deliberately identical. Before namespacing, the book lookup would have been
    // served from the project's positive entry and never reached book-service at all.
    stubFetch(() => grants('owner'));
    await expect(hasProjectAccess('same-id', 'u9')).resolves.toBe(true);
    const calls = stubFetch(() => grants('none'));
    await expect(hasBookAccess('same-id', 'u9')).resolves.toBe(false);
    expect(calls).toEqual(['http://book:8080/internal/books/same-id/access?user_id=u9']);
  });
});
