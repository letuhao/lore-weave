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
    // URL-aware mock: the auth-service resolve endpoint vs the ai-gateway relay.
    fetchMock = jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (typeof url === 'string' && url.includes('/internal/mcp-keys/resolve')) {
        // Mimic auth-service: 200 only for the one known real key, else 401.
        const key = init?.body ? (JSON.parse(init.body) as { key?: string }).key : undefined;
        if (key === 'lw_pk_realkeyfromstore123') {
          return Promise.resolve({
            status: 200,
            json: async () => ({ user_id: 'real-user-from-auth', key_id: 'key-123', scopes: ['read'], allow_self_confirm: false, rate_limit_rpm: 60 }),
            headers: { get: () => 'application/json' },
          });
        }
        return Promise.resolve({ status: 401, json: async () => ({}), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({
        status: 200,
        text: async () => '{"jsonrpc":"2.0","result":{"tools":[]},"id":1}',
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
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

  it('denies a missing bearer without any upstream call', async () => {
    setEnv();
    const r1 = mockRes();
    await new PublicMcpController().handle(mockReq({}), r1.res);
    expect(r1.statusCode).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled(); // no bearer → rejected before any fetch
  });

  it('denies an invalid key that auth-service rejects (no relay)', async () => {
    setEnv();
    const r2 = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: 'Bearer lw_pk_unknownkey999' } }),
      r2.res,
    );
    expect(r2.statusCode).toBe(401);
    // The auth resolve was attempted, but nothing was relayed to ai-gateway.
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('/mcp'))).toBe(false);
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
    expect(init.headers['x-mcp-key-id']).toBe('dev-test-key');
    expect(init.headers['x-trace-id']).toMatch(/[0-9a-f-]{36}/);
    // Edge mints a session (knowledge requires X-Session-Id) = the key id, stable
    // per credential. Never absent, never client-supplied.
    expect(init.headers['x-session-id']).toBe('dev-test-key');
  });

  it('resolves a REAL key via auth-service and relays with the resolved identity (P1)', async () => {
    setEnv();
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_realkeyfromstore123' }, // NOT the dev test key
        body: { jsonrpc: '2.0', method: 'tools/list', id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    // Two fetches: one to auth resolve, one relayed to ai-gateway.
    const authCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('/internal/mcp-keys/resolve'));
    const relayCall = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    expect(authCall).toBeDefined();
    expect(relayCall).toBeDefined();
    // The relay carries the identity auth-service resolved — not anything client-supplied.
    expect(relayCall![1].headers['x-user-id']).toBe('real-user-from-auth');
    expect(relayCall![1].headers['x-internal-token']).toBe(INTERNAL);
    // A key with NO cap → the cap header is absent (owner guardrail only, H-K).
    expect('x-mcp-spend-cap-usd' in relayCall![1].headers).toBe(false);
  });

  it('forwards X-Mcp-Spend-Cap-Usd to the relay when the resolved key carries a cap (H-K)', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u1', key_id: 'capped-key', scopes: ['read'], spend_cap_usd: 7.5, rate_limit_rpm: 60 }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({
        status: 200,
        text: async () => '{"jsonrpc":"2.0","result":{"tools":[]},"id":1}',
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: 'Bearer lw_pk_cappedkey' }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }),
      r.res,
    );
    const relayCall = (global as unknown as { fetch: jest.Mock }).fetch.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    expect(relayCall).toBeDefined();
    expect(relayCall![1].headers['x-mcp-spend-cap-usd']).toBe('7.5');
  });

  it('does NOT cache a transient auth failure (HIGH — a blip must not deny a valid key)', async () => {
    setEnv();
    // First resolve → 500 (transient); second → 200. With correct behavior the
    // 500 is NOT cached, so the second call re-hits auth and succeeds.
    let calls = 0;
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        calls++;
        if (calls === 1) return Promise.resolve({ status: 500, json: async () => ({}), headers: { get: () => null } });
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: [] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    const ctrl = new PublicMcpController();
    const r1 = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_flaky' }, body: {} }), r1.res);
    expect(r1.statusCode).toBe(401); // transient failure denied (not authenticated)
    const r2 = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_flaky' }, body: {} }), r2.res);
    expect(r2.statusCode).toBe(200); // recovered — the 500 was NOT cached
  });

  it('DOES cache a positive resolve (second call serves from cache, one auth hit)', async () => {
    setEnv();
    const ctrl = new PublicMcpController();
    const key = { headers: { authorization: 'Bearer lw_pk_realkeyfromstore123' }, body: {} };
    await ctrl.handle(mockReq(key), mockRes().res);
    await ctrl.handle(mockReq(key), mockRes().res);
    const authCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/internal/mcp-keys/resolve'));
    expect(authCalls.length).toBe(1); // second resolve came from cache
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
          'x-session-id': 'attacker-session',
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
    // The smuggled session is discarded and replaced by the edge-minted key id.
    expect(init.headers['x-session-id']).toBe('dev-test-key');
    expect(init.headers['x-session-id']).not.toBe('attacker-session');
  });

  it('denies an out-of-scope tools/call at the edge without relaying (PUB-3 / H-E)', async () => {
    setEnv();
    // A real key scoped to knowledge-read only.
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['read', 'domain:knowledge'] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_kgkey' },
        body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 9 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200); // JSON-RPC error rides a 200 envelope
    expect((r.jsonBody as { error?: { code: number } }).error?.code).toBe(-32601);
    // Critically: nothing was relayed to ai-gateway.
    const relay = (global as unknown as { fetch: jest.Mock }).fetch.mock.calls.find((c: unknown[]) =>
      String(c[0]).endsWith('/mcp'),
    );
    expect(relay).toBeUndefined();
  });

  it('filters the tools/list response down to the key scope (PUB-3 / H-F)', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['read', 'domain:knowledge'] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({
        status: 200,
        text: async () =>
          JSON.stringify({
            jsonrpc: '2.0',
            result: { tools: [{ name: 'kg_graph_query' }, { name: 'book_get' }, { name: 'memory_remember' }] },
            id: 1,
          }),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_kgkey' },
        body: { jsonrpc: '2.0', method: 'tools/list', id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    const parsed = JSON.parse(r.sentBody as string);
    expect(parsed.result.tools.map((t: { name: string }) => t.name)).toEqual(['kg_graph_query']);
    expect(r.headers['content-type']).toBe('application/json');
  });

  it('strips a STORED `*` wildcard from an auth-resolved key (no scope bypass)', async () => {
    setEnv();
    // A user crafted a key with scopes ["*"] directly via the API. The edge must
    // NOT honor it as the full-bypass token (that is the dev static key's privilege
    // only) — after stripping, the key has no scopes → fails closed on a tool call.
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['*'] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_wildcardkey' },
        body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 3 },
      }),
      r.res,
    );
    // Denied at the edge (stripped `*` → no scope → fail-closed), nothing relayed.
    expect((r.jsonBody as { error?: { code: number } }).error?.code).toBe(-32601);
    const relay = (global as unknown as { fetch: jest.Mock }).fetch.mock.calls.find((c: unknown[]) =>
      String(c[0]).endsWith('/mcp'),
    );
    expect(relay).toBeUndefined();
  });

  it('returns 429 with Retry-After when the per-key rate limit is exceeded (PUB-8)', async () => {
    setEnv();
    const ctrl = new PublicMcpController();
    // Inject a limiter that always blocks (test seam — production builds from REDIS_URL).
    (ctrl as unknown as { limiter: { check: () => Promise<unknown> } }).limiter = {
      check: async () => ({ allowed: false, retryAfter: 42, limit: 60, remaining: 0 }),
    };
    const r = mockRes();
    await ctrl.handle(
      mockReq({ headers: { authorization: `Bearer ${TEST_KEY}` }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }),
      r.res,
    );
    expect(r.statusCode).toBe(429);
    expect(r.headers['retry-after']).toBe('42');
    expect((r.jsonBody as { error?: { code: number } }).error?.code).toBe(-32029);
    // Nothing relayed to ai-gateway once rate-limited.
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith('/mcp'))).toBe(false);
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

  // ── P4 / OD-2: human-approval divert ──────────────────────────────────────
  // A default key (allow_self_confirm=false) calling a write_confirm propose has its
  // token diverted to the owner's queue; the agent gets only {pending_human_approval}.
  function wcFetch(resolve: Record<string, unknown>, opts?: { approvalStatus?: number; created?: unknown[] }) {
    return jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => resolve, headers: { get: () => 'application/json' } });
      }
      if (String(url).includes('/internal/mcp-keys/approvals')) {
        if (opts?.created) opts.created.push(JSON.parse(init!.body!));
        const st = opts?.approvalStatus ?? 201;
        return Promise.resolve({ status: st, json: async () => (st < 300 ? { approval_id: 'appr-77' } : {}), headers: { get: () => 'application/json' } });
      }
      // relay → a propose result carrying a confirm_token
      return Promise.resolve({
        status: 200,
        text: async () => JSON.stringify({ jsonrpc: '2.0', id: 5, result: { structuredContent: { confirm_token: 'SECRET-TOK', domain: 'composition', title: 'Generate' } } }),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
  }
  const wcBody = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'composition_publish' }, id: 5 };

  it('diverts a default key Tier-W propose to the approval queue and STRIPS the token (P4/OD-2)', async () => {
    setEnv();
    const created: unknown[] = [];
    (global as unknown as { fetch: jest.Mock }).fetch = wcFetch(
      { user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:composition'], allow_self_confirm: false },
      { created },
    );
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_wckey' }, body: wcBody }), r.res);
    expect(r.statusCode).toBe(200);
    const sent = JSON.parse(r.sentBody as string);
    expect(sent.result.structuredContent).toEqual({ status: 'pending_human_approval', approval_id: 'appr-77' });
    expect(r.sentBody as string).not.toContain('SECRET-TOK'); // token NEVER returned to the agent
    expect(created[0]).toMatchObject({ key_id: 'k', owner_user_id: 'u', domain: 'composition', confirm_token: 'SECRET-TOK', tool_name: 'composition_publish' });
    expect((created[0] as { preview: Record<string, unknown> }).preview.confirm_token).toBeUndefined();
  });

  it('fails CLOSED (no token leak) when the approval queue is unreachable', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = wcFetch(
      { user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:composition'], allow_self_confirm: false },
      { approvalStatus: 500 },
    );
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_wckey' }, body: wcBody }), r.res);
    expect(r.sentBody as string).not.toContain('SECRET-TOK');
    expect(JSON.parse(r.sentBody as string).result.isError).toBe(true);
  });

  it('does NOT divert when the key allows self-confirm (token flows back for slice-B confirm_action)', async () => {
    setEnv();
    const f = wcFetch({ user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:composition'], allow_self_confirm: true });
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_sc' }, body: wcBody }), r.res);
    expect(r.sentBody as string).toContain('SECRET-TOK'); // self-confirm keeps the token
    expect(f.mock.calls.some((c) => String(c[0]).includes('/internal/mcp-keys/approvals'))).toBe(false);
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
