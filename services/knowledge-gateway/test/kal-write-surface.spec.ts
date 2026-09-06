import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { HttpException } from '@nestjs/common';
import { resetConfigForTest } from '../src/config/config.js';
import { KalWriteController } from '../src/kal/kal-write.controller.js';

/**
 * T48f — the eight destructive routes, tested for BEHAVIOUR rather than for being guarded.
 *
 * T48e closed the skip census on this service and found the other way a suite goes dark: 20 of
 * 31 routes were named by no test, eight of them the entity lifecycle (merge / split / purge /
 * fold / restore / reassign-kind / episodes / resolve-entity). It bought them a guard and said
 * plainly that it had not bought their behaviour. This is that.
 *
 * Only `fetch` is mocked, deliberately. The two properties under test do not live in the
 * controller — the faithful-status mapping and the identity-omission guard are both in
 * `downstream.ts`, and mocking `glossary.post` would test the seam by replacing it. What runs
 * here is the real chain: handler -> glossary.post -> call() -> fetch.
 */

const SRC = join(__dirname, '..', 'src', 'kal', 'kal-write.controller.ts');
const BOOK = 'b-1';
const ENT = 'e-1';

/** Every @Post handler, with the downstream path it must reach. Hand-written ON PURPOSE — the
 *  point of the contract is that each route DECLARES where it forwards — and made complete by
 *  the ratchet below, which derives the handler list from the source. */
const ROUTES: Array<[string, string, (c: KalWriteController, h: Record<string, string>) => unknown]> = [
  ['ingestEpisode',  `/internal/books/${BOOK}/facts/episode`,        (c, h) => c.ingestEpisode(BOOK, {}, h)],
  ['resolveEntity',  `/internal/books/${BOOK}/facts/resolve-entity`, (c, h) => c.resolveEntity(BOOK, {}, h)],
  ['appendFact',     `/internal/books/${BOOK}/facts/append`,         (c, h) => c.appendFact(BOOK, {}, h)],
  ['closeFact',      `/internal/books/${BOOK}/facts/close`,          (c, h) => c.closeFact(BOOK, {}, h)],
  ['retract',        `/internal/books/${BOOK}/facts/retract`,        (c, h) => c.retract(BOOK, {}, h)],
  ['merge',          `/internal/books/${BOOK}/facts/merge`,          (c, h) => c.merge(BOOK, {}, h)],
  ['split',          `/internal/books/${BOOK}/facts/split`,          (c, h) => c.split(BOOK, {}, h)],
  ['fold',           `/internal/books/${BOOK}/entities/${ENT}/fold`, (c, h) => c.fold(BOOK, ENT, {}, h)],
  ['deleteEntity',   `/internal/books/${BOOK}/entities/${ENT}/delete`,        (c, h) => c.deleteEntity(BOOK, ENT, h)],
  ['restoreEntity',  `/internal/books/${BOOK}/entities/${ENT}/restore`,       (c, h) => c.restoreEntity(BOOK, ENT, h)],
  ['purgeEntity',    `/internal/books/${BOOK}/entities/${ENT}/purge`,         (c, h) => c.purgeEntity(BOOK, ENT, h)],
  ['reassignKind',   `/internal/books/${BOOK}/entities/${ENT}/reassign-kind`, (c, h) => c.reassignKind(BOOK, ENT, {}, h)],
  ['setStatus',      `/internal/books/${BOOK}/entities/status`,      (c, h) => c.setStatus(BOOK, {}, h)],
];

function respond(status: number, body = '{}') {
  return jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    text: async () => body,
    json: async () => JSON.parse(body),
  });
}

function headersOf(fetchMock: jest.Mock): Record<string, string> {
  return (fetchMock.mock.calls[0][1] as { headers: Record<string, string> }).headers;
}

describe('KAL write surface (T48f)', () => {
  const controller = new KalWriteController();
  const orig = process.env.INTERNAL_SERVICE_TOKEN;

  beforeEach(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    resetConfigForTest();
  });
  afterEach(() => {
    if (orig === undefined) delete process.env.INTERNAL_SERVICE_TOKEN;
    else process.env.INTERNAL_SERVICE_TOKEN = orig;
    resetConfigForTest();
    jest.restoreAllMocks();
  });

  it('exercises EVERY @Post handler — a new route is untested until it is on the table', () => {
    /* The ratchet, and the reason the table above is allowed to be hand-written. A route added
       tomorrow is invisible to a list it is not on; this derives the handler names from the
       source so the omission fails here instead of shipping green. It is also the control arm:
       every other assertion in this file is satisfied by an EMPTY table. */
    const src = readFileSync(SRC, 'utf8');
    const declared = [...src.matchAll(/@Post\([^)]*\)\s*\n\s*(?:async\s+)?(\w+)\s*\(/g)].map((m) => m[1]);
    expect(declared.length).toBeGreaterThanOrEqual(13);
    expect(new Set(ROUTES.map((r) => r[0]))).toEqual(new Set(declared));
  });

  describe.each(ROUTES)('%s', (_name, path, invoke) => {
    it(`forwards to ${path} and carries the caller identity`, async () => {
      const f = respond(200);
      global.fetch = f as unknown as typeof fetch;
      await invoke(controller, { 'x-user-id': 'u-7' });
      expect(f.mock.calls[0][0]).toBe(`http://glossary-service:8088${path}`);
      expect(headersOf(f)['X-User-Id']).toBe('u-7');
      expect(headersOf(f)['X-Internal-Token']).toBe('tok');
    });

    it('OMITS X-User-Id when there is no caller identity (a pipeline sweep is not a user)', async () => {
      /* The controller's own comment: "forwards X-User-Id when a caller identity exists and
         omits it otherwise ... Nothing here synthesises an identity to fill the gap." That is
         what lets glossary attribute a pipeline sweep to `pipeline` rather than to some user.
         `downstream.ts:29` guards with `if (ctx.userId)`; written as a plain assignment the
         header goes out as the STRING "undefined" and every one of these destructive commands
         — purge included — is recorded against a user who did not issue it. */
      const f = respond(200);
      global.fetch = f as unknown as typeof fetch;
      await invoke(controller, {});
      expect(Object.keys(headersOf(f))).not.toContain('X-User-Id');
    });

    it('surfaces a downstream 4xx faithfully rather than as a silent success', async () => {
      const f = respond(409, 'conflict: entity already merged');
      global.fetch = f as unknown as typeof fetch;
      await expect(invoke(controller, { 'x-user-id': 'u-7' })).rejects.toThrow(HttpException);
      await expect(invoke(controller, { 'x-user-id': 'u-7' })).rejects.toMatchObject({ status: 409 });
    });

    it('maps a downstream 5xx to 502 — the caller is not told the backend is fine', async () => {
      const f = respond(503, 'upstream down');
      global.fetch = f as unknown as typeof fetch;
      await expect(invoke(controller, { 'x-user-id': 'u-7' })).rejects.toMatchObject({ status: 502 });
    });
  });

  it('an empty x-user-id is treated as NO identity, not as a user named ""', async () => {
    /* The boundary the truthy guard buys, pinned once rather than per-route: a caller that
       forwards the header with nothing in it must not be attributed either. */
    const f = respond(200);
    global.fetch = f as unknown as typeof fetch;
    await controller.purgeEntity(BOOK, ENT, { 'x-user-id': '' });
    expect(Object.keys(headersOf(f))).not.toContain('X-User-Id');
  });
});
