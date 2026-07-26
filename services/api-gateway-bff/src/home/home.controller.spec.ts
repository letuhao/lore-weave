import * as jwt from 'jsonwebtoken';
import { HttpException } from '@nestjs/common';

import { HomeController } from './home.controller';

const TEST_SECRET = 'home-controller-test-secret-32chars!!';

function bearer(sub: string): string {
  return `Bearer ${jwt.sign({ sub }, TEST_SECRET, { expiresIn: '1h' })}`;
}
function resp(status: number, bodyObj: unknown) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(bodyObj) };
}
// Route the mocked fetch by URL so the fan-out order doesn't matter.
function routeFetch(map: Record<string, () => Promise<any> | any>) {
  return jest.fn((url: string, _init?: any) => {
    for (const key of Object.keys(map)) {
      if (url.includes(key)) return Promise.resolve(map[key]());
    }
    return Promise.resolve(resp(404, {}));
  });
}
async function expectStatus(p: Promise<unknown>, status: number): Promise<void> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(HttpException);
    expect((e as HttpException).getStatus()).toBe(status);
    return;
  }
  throw new Error(`expected an HttpException with status ${status}`);
}

describe('HomeController (M2 — home degrade + activity feed)', () => {
  let controller: HomeController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.NOTIFICATION_SERVICE_URL = 'http://notif:8300';
    process.env.BOOK_SERVICE_URL = 'http://book:8205';
    process.env.JOBS_SERVICE_URL = 'http://jobs:8400';
    controller = new HomeController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.NOTIFICATION_SERVICE_URL;
    delete process.env.BOOK_SERVICE_URL;
    delete process.env.JOBS_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  it('401 without a bearer — no fan-out', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.home(undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('composes all tiles OK, deriving owner from the JWT (forwards the Bearer)', async () => {
    const f = routeFetch({
      'unread-count': () => resp(200, { count: 3 }),
      '/v1/books': () => resp(200, { items: [{ id: 'b1', title: 'Novel', updated_at: 't' }] }),
      '/v1/jobs': () => resp(200, { items: [{ id: 'j1', kind: 'translation', status: 'completed' }] }),
    });
    (global as any).fetch = f;

    const out = await controller.home(bearer('user-1'));
    expect(out.tiles.activity.status).toBe('ok');
    expect(out.tiles.activity.data).toEqual({ unread: 3 });
    expect(out.tiles.books.status).toBe('ok');
    expect(out.tiles.books.data).toEqual([{ id: 'b1', title: 'Novel', updated_at: 't' }]);
    expect(out.tiles.jobs.status).toBe('ok');
    expect(typeof out.generated_at).toBe('string');
    // every downstream call carried the caller's Bearer (owner-scoped server-side).
    for (const call of f.mock.calls) {
      expect((call[1] as any).headers.authorization).toBe(bearer('user-1'));
    }
  });

  it('a DOWN optional source degrades ONLY its tile — the page still renders (never blank)', async () => {
    const f = routeFetch({
      'unread-count': () => resp(200, { count: 0 }),
      '/v1/books': () => resp(500, {}), // books down
      '/v1/jobs': () => resp(200, { items: [] }),
    });
    (global as any).fetch = f;

    const out = await controller.home(bearer('user-2'));
    expect(out.tiles.books.status).toBe('degraded'); // its tile only
    expect(out.tiles.activity.status).toBe('empty'); // ok + unread 0 → empty
    expect(out.tiles.jobs.status).toBe('empty'); // ok + [] → empty
    // the page is a real object, not a 500.
    expect(out.tiles).toBeDefined();
  });

  it('a DOWN critical source (activity) still returns a non-blank page (degraded tile)', async () => {
    const f = routeFetch({
      'unread-count': () => resp(503, {}),
      '/v1/books': () => resp(200, { items: [{ id: 'b1', title: 'X' }] }),
      '/v1/jobs': () => resp(200, { items: [] }),
    });
    (global as any).fetch = f;
    const out = await controller.home(bearer('user-3'));
    expect(out.tiles.activity.status).toBe('degraded');
    expect(out.tiles.books.status).toBe('ok'); // other tiles still resolve
  });

  it('serves a STALE cached snapshot when a critical source later goes down', async () => {
    // 1st call healthy → cached.
    (global as any).fetch = routeFetch({
      'unread-count': () => resp(200, { count: 5 }),
      '/v1/books': () => resp(200, { items: [] }),
      '/v1/jobs': () => resp(200, { items: [] }),
    });
    const first = await controller.home(bearer('user-4'));
    expect(first.tiles.activity.data).toEqual({ unread: 5 });

    // 2nd call: activity down → should serve the stale snapshot (unread 5), marked stale.
    (global as any).fetch = routeFetch({
      'unread-count': () => resp(503, {}),
      '/v1/books': () => resp(200, { items: [] }),
      '/v1/jobs': () => resp(200, { items: [] }),
    });
    const second = await controller.home(bearer('user-4'));
    expect(second.stale).toBe(true);
    expect(second.tiles.activity.data).toEqual({ unread: 5 });
  });

  it('activity feed: forwards keyset cursor and shapes {items,next_cursor,unread_count}', async () => {
    const f = routeFetch({
      '/v1/notifications/unread-count': () => resp(200, { count: 2 }),
      '/v1/notifications?': () =>
        resp(200, { items: [{ id: 'n1' }], next_cursor: { before: '2026-07-14T10:00:00Z', before_id: 'abc' } }),
    });
    (global as any).fetch = f;

    const page1 = await controller.activity(undefined, '20', bearer('user-5'));
    expect(page1.items).toHaveLength(1);
    expect(page1.unread_count).toBe(2);
    expect(typeof page1.next_cursor).toBe('string'); // opaque encoded cursor

    // Round-trip the cursor: decoding it must reproduce the before/before_id on the downstream call.
    await controller.activity(page1.next_cursor!, '20', bearer('user-5'));
    const secondListCall = f.mock.calls
      .filter((c: any[]) => String(c[0]).includes('/v1/notifications?'))
      .pop();
    expect(secondListCall).toBeDefined();
    expect(String(secondListCall![0])).toContain('before=');
    expect(String(secondListCall![0])).toContain('before_id=abc');
  });

  it('activity feed: clamps limit to 50 and defaults on garbage', async () => {
    const f = routeFetch({
      '/v1/notifications/unread-count': () => resp(200, { count: 0 }),
      '/v1/notifications?': () => resp(200, { items: [], next_cursor: null }),
    });
    (global as any).fetch = f;
    await controller.activity(undefined, '9999', bearer('user-6'));
    const call = f.mock.calls.find((c: any[]) => String(c[0]).includes('/v1/notifications?'));
    expect(call).toBeDefined();
    expect(String(call![0])).toContain('limit=50');
  });

  it('mark-all-read proxies read-all', async () => {
    const f = routeFetch({ 'read-all': () => resp(200, { marked: 7 }) });
    (global as any).fetch = f;
    const out = await controller.markAllRead(bearer('user-7'));
    expect(out.marked).toBe(7);
  });
});
