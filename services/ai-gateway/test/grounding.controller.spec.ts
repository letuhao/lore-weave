import { GroundingController } from '../src/grounding/grounding.controller.js';
import { resetConfigForTest } from '../src/config/config.js';

// P6 grounding proxy — SO-1 gate + pass-through forwarding + 502-on-outage (so
// the consumer falls back to knowledge-direct, H2).

function mockReqRes(opts: { token?: string; userId?: string; traceId?: string; body?: unknown }) {
  const headers: Record<string, string | undefined> = {
    'x-internal-token': opts.token,
    'x-user-id': opts.userId,
    'x-trace-id': opts.traceId,
  };
  const req: any = {
    header: (k: string) => headers[k.toLowerCase()],
    body: opts.body ?? {},
  };
  const res: any = {
    statusCode: 200,
    body: undefined as unknown,
    headers: {} as Record<string, string>,
    status(c: number) { this.statusCode = c; return this; },
    json(b: unknown) { this.body = b; return this; },
    send(b: unknown) { this.body = b; return this; },
    setHeader(k: string, v: string) { this.headers[k] = v; },
  };
  return { req, res };
}

describe('GroundingController (P6 grounding proxy)', () => {
  beforeAll(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'tok';
    process.env.KNOWLEDGE_SERVICE_URL = 'http://knowledge:8092';
    resetConfigForTest();
  });
  afterEach(() => {
    (global as any).fetch = undefined;
  });

  it('rejects a missing internal token with 401 (before any forward)', async () => {
    const fetchMock = jest.fn();
    (global as any).fetch = fetchMock;
    const { req, res } = mockReqRes({ token: undefined, body: {} });
    await new GroundingController().build(req, res);
    expect(res.statusCode).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards to knowledge with the gateway token + identity, relaying status + body', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      status: 200,
      text: async () => JSON.stringify({ mode: 'static', context: 'ctx' }),
      headers: { get: (k: string) => (k === 'content-type' ? 'application/json' : null) },
    });
    (global as any).fetch = fetchMock;
    const { req, res } = mockReqRes({ token: 'tok', userId: 'u1', traceId: 't1', body: { user_id: 'u1' } });
    await new GroundingController().build(req, res);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://knowledge:8092/internal/context/build');
    expect(init.headers['x-internal-token']).toBe('tok'); // gateway presents its own
    expect(init.headers['x-user-id']).toBe('u1');
    expect(init.headers['x-trace-id']).toBe('t1');
    expect(JSON.parse(init.body)).toEqual({ user_id: 'u1' });
    expect(res.statusCode).toBe(200);
    expect(res.body).toBe(JSON.stringify({ mode: 'static', context: 'ctx' }));
  });

  it('relays a stable knowledge 404 verbatim (consumer degrades, no fallback)', async () => {
    (global as any).fetch = jest.fn().mockResolvedValue({
      status: 404,
      text: async () => '{"error":"project not found"}',
      headers: { get: () => 'application/json' },
    });
    const { req, res } = mockReqRes({ token: 'tok', body: {} });
    await new GroundingController().build(req, res);
    expect(res.statusCode).toBe(404);
  });

  it('returns 502 when knowledge is unreachable (consumer falls back to direct)', async () => {
    (global as any).fetch = jest.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const { req, res } = mockReqRes({ token: 'tok', body: {} });
    await new GroundingController().build(req, res);
    expect(res.statusCode).toBe(502);
  });
});
