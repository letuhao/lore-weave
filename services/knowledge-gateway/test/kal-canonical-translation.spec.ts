import { KalReadController } from '../src/kal/kal-read.controller.js';
import { resetConfigForTest } from '../src/config/config.js';

/**
 * get_canonical_translation forwarding: the KAL maps the read to glossary's
 * /internal/.../canonical-translation, threads `lang`+`as_of`, pins X-User-Id from the
 * guard-validated kalUserId (anti-spoof), and returns the downstream body verbatim.
 */
describe('KalReadController.getCanonicalTranslation', () => {
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

  it('forwards lang + as_of and pins X-User-Id from kalUserId, returning the body', async () => {
    fetchMock.mockResolvedValue(
      ok({ entity_id: 'e1', language_code: 'en', content: 'orig', translated: false, status: 'translating' }),
    );
    const ctrl = new KalReadController();
    const req = { headers: { 'x-user-id': 'spoofed' }, kalUserId: 'real-user' };
    const out = await ctrl.getCanonicalTranslation('b1', 'e1', 'en', '300', req as never);

    expect(out).toMatchObject({ status: 'translating', language_code: 'en', translated: false });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/internal/books/b1/entities/e1/canonical-translation');
    expect(url).toContain('lang=en');
    expect(url).toContain('as_of=300');
    expect((init.headers as Record<string, string>)['X-User-Id']).toBe('real-user'); // NOT 'spoofed'
    expect((init.headers as Record<string, string>)['X-Internal-Token']).toBe('svc-token');
  });

  it('omits as_of when not provided', async () => {
    fetchMock.mockResolvedValue(ok({ entity_id: 'e1', language_code: 'vi', content: '', translated: false, status: 'unbuildable' }));
    const ctrl = new KalReadController();
    const out = await ctrl.getCanonicalTranslation('b1', 'e1', 'vi', undefined, { headers: {}, kalUserId: 'u' } as never);
    expect(out).toMatchObject({ status: 'unbuildable' });
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain('lang=vi');
    expect(url).not.toContain('as_of=');
  });
});
