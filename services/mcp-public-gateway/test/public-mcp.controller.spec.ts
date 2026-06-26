import type { Request, Response } from 'express';
import { PublicMcpController, parseBearer } from '../src/mcp/public-mcp.controller.js';
import { constantTimeEquals } from '../src/auth/key-resolver.js';
import { resetConfigForTest } from '../src/config/config.js';

const INTERNAL = 'internal-secret-xyz';
const TEST_KEY = 'lw_pk_testkey_abc123';
const TEST_USER = '019d5e3c-7cc5-7e6a-8b27-1344e148bf7c';

function setEnv(overrides: Record<string, string | undefined> = {}): void {
  process.env.INTERNAL_SERVICE_TOKEN = INTERNAL;
  process.env.AI_GATEWAY_URL = 'http://ai-gateway:8210';
  process.env.PUBLIC_MCP_ENABLED = 'true';
  process.env.MCP_PUBLIC_TEST_KEY = TEST_KEY;
  process.env.MCP_PUBLIC_TEST_USER_ID = TEST_USER;
  for (const [k, v] of Object.entries(overrides)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
  resetConfigForTest();
}

interface MockRes {
  res: Response;
  statusCode: number;
  jsonBody: unknown;
  sentBody: unknown;
  headers: Record<string, string>;
}

function mockRes(): MockRes {
  const state: MockRes = { res: {} as Response, statusCode: 0, jsonBody: undefined, sentBody: undefined, headers: {} };
  state.res = {
    status(code: number) {
      state.statusCode = code;
      return this;
    },
    json(body: unknown) {
      state.jsonBody = body;
      return this;
    },
    send(body: unknown) {
      state.sentBody = body;
      return this;
    },
    setHeader(name: string, value: string) {
      state.headers[name.toLowerCase()] = value;
      return this;
    },
  } as unknown as Response;
  return state;
}

function mockReq(opts: {
  method?: string;
  headers?: Record<string, string>;
  query?: Record<string, string>;
  body?: unknown;
}): Request {
  const headers = Object.fromEntries(Object.entries(opts.headers ?? {}).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    method: opts.method ?? 'POST',
    query: opts.query ?? {},
    body: opts.body,
    header(name: string) {
      return headers[name.toLowerCase()];
    },
  } as unknown as Request;
}

describe('PublicMcpController', () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      status: 200,
      text: async () => '{"jsonrpc":"2.0","result":{"tools":[]},"id":1}',
      headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
    });
    (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;
  });

  afterEach(() => resetConfigForTest());

  it('denies all traffic when the feature flag is off (Q-GATE)', async () => {
    setEnv({ PUBLIC_MCP_ENABLED: 'false' });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: `Bearer ${TEST_KEY}` } }),
      r.res,
    );
    expect(r.statusCode).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('denies a missing or invalid bearer', async () => {
    setEnv();
    const r1 = mockRes();
    await new PublicMcpController().handle(mockReq({}), r1.res);
    expect(r1.statusCode).toBe(401);

    const r2 = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: 'Bearer wrong-key' } }),
      r2.res,
    );
    expect(r2.statusCode).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('refuses a credential in the query string (H-R)', async () => {
    setEnv();
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ query: { key: TEST_KEY }, headers: { authorization: `Bearer ${TEST_KEY}` } }),
      r.res,
    );
    expect(r.statusCode).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('relays a valid call and mints a fresh envelope (PUB-1)', async () => {
    setEnv();
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: `Bearer ${TEST_KEY}` },
        body: { jsonrpc: '2.0', method: 'tools/list', id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://ai-gateway:8210/mcp'); // never /mcp/admin
    expect(init.headers['x-internal-token']).toBe(INTERNAL);
    expect(init.headers['x-user-id']).toBe(TEST_USER);
    expect(init.headers['x-mcp-key-id']).toBe('p0-test-key');
    expect(init.headers['x-trace-id']).toMatch(/[0-9a-f-]{36}/);
  });

  it('STRIPS inbound x-* and never forwards smuggled identity/admin headers (PUB-9 / H-A)', async () => {
    setEnv();
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: {
          authorization: `Bearer ${TEST_KEY}`,
          'x-admin-token': 'EVIL-ADMIN',
          'x-internal-token': 'EVIL-INTERNAL',
          'x-user-id': 'victim-user-id',
          'x-project-id': 'victim-project',
          'x-trace-id': 'attacker-trace',
        },
        body: { jsonrpc: '2.0', method: 'tools/list', id: 1 },
      }),
      r.res,
    );
    const [url, init] = fetchMock.mock.calls[0];
    // Admin token is never forwarded; edge has no /mcp/admin route.
    expect(init.headers['x-admin-token']).toBeUndefined();
    expect(url).not.toContain('/mcp/admin');
    // The agent's smuggled identity/internal/trace are overwritten by edge-minted values.
    expect(init.headers['x-internal-token']).toBe(INTERNAL);
    expect(init.headers['x-user-id']).toBe(TEST_USER); // NOT 'victim-user-id'
    expect(init.headers['x-user-id']).not.toBe('victim-user-id');
    expect(init.headers['x-trace-id']).not.toBe('attacker-trace');
    // No inbound x-project-id leaks through (P0 relays no project scope).
    expect(init.headers['x-project-id']).toBeUndefined();
  });

  it('returns 502 when the upstream gateway is unreachable', async () => {
    setEnv();
    fetchMock.mockRejectedValueOnce(new Error('ECONNREFUSED'));
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: `Bearer ${TEST_KEY}` }, body: { jsonrpc: '2.0', id: 1 } }),
      r.res,
    );
    expect(r.statusCode).toBe(502);
  });
});

describe('helpers', () => {
  it('parseBearer extracts the token', () => {
    expect(parseBearer('Bearer abc')).toBe('abc');
    expect(parseBearer('bearer  xyz ')).toBe('xyz');
    expect(parseBearer('Basic abc')).toBeUndefined();
    expect(parseBearer(undefined)).toBeUndefined();
  });

  it('constantTimeEquals compares correctly', () => {
    expect(constantTimeEquals('abc', 'abc')).toBe(true);
    expect(constantTimeEquals('abc', 'abd')).toBe(false);
    expect(constantTimeEquals('abc', 'abcd')).toBe(false);
    expect(constantTimeEquals('', '')).toBe(true);
  });
});
