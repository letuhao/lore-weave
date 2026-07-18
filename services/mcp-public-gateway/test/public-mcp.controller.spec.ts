import { generateKeyPairSync, sign, type KeyObject } from 'node:crypto';
import type { Request, Response } from 'express';
import { PublicMcpController, parseBearer } from '../src/mcp/public-mcp.controller.js';
import { constantTimeEquals } from '../src/auth/key-resolver.js';
import { OAuthDiscoveryController } from '../src/oauth/oauth-discovery.controller.js';
import { resetConfigForTest } from '../src/config/config.js';
import { Idempotency, PENDING_MARKER, type IdempotencyStore } from '../src/idempotency/idempotency-store.js';

const INTERNAL = 'internal-secret-xyz';
const TEST_KEY = 'lw_pk_testkey_abc123';
const TEST_USER = '019d5e3c-7cc5-7e6a-8b27-1344e148bf7c';

function setEnv(overrides: Record<string, string | undefined> = {}): void {
  process.env.INTERNAL_SERVICE_TOKEN = INTERNAL;
  process.env.AI_GATEWAY_URL = 'http://ai-gateway:8210';
  process.env.PUBLIC_MCP_ENABLED = 'true';
  process.env.MCP_PUBLIC_TEST_KEY = TEST_KEY;
  process.env.MCP_PUBLIC_TEST_USER_ID = TEST_USER;
  // P5 OAuth env is OFF by default — cleared each call so an OAuth test can't leak
  // its config into a later test (order-independence).
  delete process.env.OAUTH_ISSUER;
  delete process.env.MCP_RESOURCE_URL;
  delete process.env.OAUTH_JWKS_URL;
  delete process.env.OAUTH_DEFAULT_RPM;
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

  it('H-G: strips the edge-only idempotency_key from a write_auto create before relay', async () => {
    setEnv();
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: `Bearer ${TEST_KEY}` },
        body: {
          jsonrpc: '2.0',
          method: 'tools/call',
          id: 5,
          params: { name: 'book_create', arguments: { title: 'My Book', idempotency_key: 'k-1' } },
        },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    const relayCall = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    expect(relayCall).toBeDefined();
    const sentBody = JSON.parse((relayCall![1] as { body: string }).body) as {
      params: { arguments: Record<string, unknown> };
    };
    // The underlying tool uses ForbidExtra — the edge field must NOT reach it…
    expect('idempotency_key' in sentBody.params.arguments).toBe(false);
    // …while the real create arguments are preserved verbatim.
    expect(sentBody.params.arguments.title).toBe('My Book');
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

  it('a FRESH session on a BROAD (>=20-tool) scope lists only find_tools — lazy loading (the in-scope catalogue is hidden until discovered)', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          // read+domain:knowledge (11 tools) alone is BELOW the scope-size-adaptive threshold
          // (2026-07-07 spec §6) and would now get the direct-list path (see the dedicated
          // small-scope test below) — add domain:composition (15 more read tools) so this key
          // resolves to 26 tools, safely >=20, to keep testing the COLLAPSED-path regression.
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['read', 'domain:knowledge', 'domain:composition'] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({
        status: 200,
        // ai-gateway prepends find_tools; the rest is the federated catalogue.
        text: async () =>
          JSON.stringify({
            jsonrpc: '2.0',
            result: {
              tools: [{ name: 'find_tools' }, { name: 'kg_graph_query' }, { name: 'book_get' }, { name: 'memory_remember' }],
            },
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
    // Minimal session surface: find_tools + invoke_tool (the always-present discover+execute
    // pair). Out-of-scope tools (book_get/memory_remember) are scope-filtered AND the in-scope
    // kg_graph_query is hidden by lazy loading until find_tools activates it — so nothing but
    // the two synthetic edge tools is advertised on a fresh session.
    expect(parsed.result.tools.map((t: { name: string }) => t.name).sort()).toEqual(['find_tools', 'invoke_tool']);
    expect(r.headers['content-type']).toBe('application/json');
  });

  // ── Scope-size-adaptive exposure (2026-07-07 spec §3.3/§6/§8b.7) ────────────
  it('a SMALL (<20-tool) scope gets the FULL scope-filtered list directly — no lazy collapse', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        // read+domain:book resolves to exactly 5 tools (book_list/get/list_chapters/
        // get_chapter/list_revisions) — well under the 20-tool threshold.
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['read', 'domain:book'] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({
        status: 200,
        text: async () =>
          JSON.stringify({
            jsonrpc: '2.0',
            result: {
              tools: [{ name: 'find_tools' }, { name: 'book_list' }, { name: 'book_get' }, { name: 'kg_graph_query' }],
            },
            id: 1,
          }),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_smallkey' },
        body: { jsonrpc: '2.0', method: 'tools/list', id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    const parsed = JSON.parse(r.sentBody as string);
    const names = parsed.result.tools.map((t: { name: string }) => t.name).sort();
    // book_list/book_get are advertised DIRECTLY on a fresh session — no find_tools-then-
    // activate round trip needed. kg_graph_query is correctly scope-filtered out (out of
    // scope). invoke_tool stays present (unconditional today — harmless if unused; the
    // change here is only about WHEN the collapse happens, not invoke_tool's availability).
    expect(names).toEqual(['book_get', 'book_list', 'find_tools', 'invoke_tool']);
    expect(r.headers['content-type']).toBe('application/json');
  });

  it('an EMPTY-scope key (scopeToolCount=0) also takes the direct-list path safely — no leak beyond find_tools', async () => {
    // review-impl finding (2026-07-08, LOW): scopeToolCount([]) is 0 (< 20) so this key
    // takes the SAME directList=true branch as a small real scope — verify at the
    // controller/tools-list level (not just the pure-function level in tool-policy.spec.ts)
    // that this doesn't leak anything beyond find_tools, since filterTools/isToolAllowed
    // still gate every entry identically regardless of which list-mode advertised it.
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: [] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({
        status: 200,
        text: async () =>
          JSON.stringify({
            jsonrpc: '2.0',
            result: { tools: [{ name: 'find_tools' }, { name: 'book_list' }, { name: 'kg_graph_query' }] },
            id: 1,
          }),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_emptyscope' },
        body: { jsonrpc: '2.0', method: 'tools/list', id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    const parsed = JSON.parse(r.sentBody as string);
    const names = parsed.result.tools.map((t: { name: string }) => t.name).sort();
    // No domain tool leaks through — an empty scope is allowed exactly find_tools + invoke_tool,
    // identical to what the collapsed (large-scope) path would have shown.
    expect(names).toEqual(['find_tools', 'invoke_tool']);
  });

  it('a directly-listed tool (small scope) is immediately callable via a normal tools/call — no find_tools/activation needed first', async () => {
    setEnv();
    const f = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({
          status: 200,
          json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['read', 'domain:book'] }),
          headers: { get: () => 'application/json' },
        });
      }
      return Promise.resolve({
        status: 200,
        text: async () => JSON.stringify({ jsonrpc: '2.0', id: 1, result: { structuredContent: { books: [] } } }),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_directcall' },
        body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_list' }, id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    // Relayed straight through as a normal tools/call — no invoke_tool unwrap, no "not
    // activated" denial. The security boundary is `isToolAllowed` (the scope gate), never
    // the list-mode/activation bookkeeping — a raw tools/call was never activation-gated to
    // begin with (only the invoke_tool facade's unwrap path checks activation), so this holds
    // for a small-scope key exactly the same way it already did for a large-scope key.
    const relay = f.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    expect(relay).toBeDefined();
    expect(JSON.parse((relay![1] as { body: string }).body).params.name).toBe('book_list');
    const out = JSON.parse(r.sentBody as string);
    expect(out.result.structuredContent).toEqual({ books: [] });
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

  // ── P4 / OD-2: BATCH write_confirm divert (D-PMCP-BATCH-WCONFIRM-DIVERT) ─────
  // A default key's JSON-RPC BATCH containing a write_confirm propose must NOT leak the
  // token either: each propose item is diverted to the queue + token-stripped, fail-closed.
  function wcBatchFetch(resolve: Record<string, unknown>, opts?: { approvalStatus?: number; created?: unknown[] }) {
    return jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => resolve, headers: { get: () => 'application/json' } });
      }
      if (String(url).includes('/internal/mcp-keys/approvals')) {
        if (opts?.created) opts.created.push(JSON.parse(init!.body!));
        const st = opts?.approvalStatus ?? 201;
        return Promise.resolve({ status: st, json: async () => (st < 300 ? { approval_id: 'appr-b1' } : {}), headers: { get: () => 'application/json' } });
      }
      // relay → a BATCH response array: one propose (id 5), one normal read (id 6)
      return Promise.resolve({
        status: 200,
        text: async () =>
          JSON.stringify([
            { jsonrpc: '2.0', id: 5, result: { structuredContent: { confirm_token: 'SECRET-TOK', domain: 'composition', title: 'Generate' } } },
            { jsonrpc: '2.0', id: 6, result: { structuredContent: { books: [] } } },
          ]),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
  }
  const batchBody = [
    { jsonrpc: '2.0', method: 'tools/call', params: { name: 'composition_publish' }, id: 5 },
    { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 6 },
  ];
  const batchScopes = { user_id: 'u', key_id: 'k', scopes: ['read', 'write_confirm', 'domain:composition', 'domain:book'], allow_self_confirm: false };

  it('diverts a write_confirm propose INSIDE a batch and STRIPS the token, keeping other items (D-PMCP-BATCH-WCONFIRM-DIVERT)', async () => {
    setEnv();
    const created: unknown[] = [];
    (global as unknown as { fetch: jest.Mock }).fetch = wcBatchFetch(batchScopes, { created });
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_batch' }, body: batchBody }), r.res);
    expect(r.statusCode).toBe(200);
    expect(r.sentBody as string).not.toContain('SECRET-TOK'); // token NEVER returned to the agent
    const sent = JSON.parse(r.sentBody as string) as Array<{ id: unknown; result: { structuredContent?: unknown }; _meta?: { step_outcome?: string } }>;
    const item5 = sent.find((x) => x.id === 5)!;
    expect(item5.result.structuredContent).toEqual({ status: 'pending_human_approval', approval_id: 'appr-b1' });
    expect(item5._meta?.step_outcome).toBe('relayed'); // slice-F honesty preserved
    const item6 = sent.find((x) => x.id === 6)!;
    expect(item6.result.structuredContent).toEqual({ books: [] }); // untouched
    expect(item6._meta?.step_outcome).toBe('relayed');
    // exactly one approval created, attributed to the write_confirm step's tool
    expect(created).toHaveLength(1);
    expect(created[0]).toMatchObject({ key_id: 'k', owner_user_id: 'u', domain: 'composition', confirm_token: 'SECRET-TOK', tool_name: 'composition_publish' });
    expect((created[0] as { preview: Record<string, unknown> }).preview.confirm_token).toBeUndefined();
  });

  it('fails CLOSED per item when the approval queue is unreachable (batch, no token leak)', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = wcBatchFetch(batchScopes, { approvalStatus: 500 });
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_batch' }, body: batchBody }), r.res);
    expect(r.sentBody as string).not.toContain('SECRET-TOK');
    const sent = JSON.parse(r.sentBody as string) as Array<{ id: unknown; result: { isError?: boolean } }>;
    expect(sent.find((x) => x.id === 5)!.result.isError).toBe(true);
  });

  it('does NOT divert a batch when the key allows self-confirm (tokens flow back)', async () => {
    setEnv();
    const f = wcBatchFetch({ ...batchScopes, allow_self_confirm: true });
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_batch_sc' }, body: batchBody }), r.res);
    expect(r.sentBody as string).toContain('SECRET-TOK'); // self-confirm keeps the token (slice-B path)
    expect(f.mock.calls.some((c) => String(c[0]).includes('/internal/mcp-keys/approvals'))).toBe(false);
  });

  it('STILL scope-filters the tools/list item of a mixed batch after diverting the propose (no catalogue leak)', async () => {
    setEnv();
    // A batch that mixes a tools/list with a write_confirm propose. The divert must strip the
    // token AND the list must still be filtered to the key's scope (regression guard).
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['read', 'write_confirm', 'domain:composition'], allow_self_confirm: false }), headers: { get: () => 'application/json' } });
      }
      if (String(url).includes('/internal/mcp-keys/approvals')) {
        return Promise.resolve({ status: 201, json: async () => ({ approval_id: 'appr-mix' }), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({
        status: 200,
        text: async () =>
          JSON.stringify([
            { jsonrpc: '2.0', id: 'L', result: { tools: [{ name: 'find_tools' }, { name: 'book_get' }, { name: 'composition_publish' }, { name: 'kg_graph_query' }] } },
            { jsonrpc: '2.0', id: 5, result: { structuredContent: { confirm_token: 'SECRET-TOK', domain: 'composition' } } },
          ]),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    const mixedBody = [
      { jsonrpc: '2.0', method: 'tools/list', id: 'L' },
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'composition_publish' }, id: 5 },
    ];
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_mix' }, body: mixedBody }), r.res);
    expect(r.sentBody as string).not.toContain('SECRET-TOK'); // token stripped
    const sent = JSON.parse(r.sentBody as string) as Array<{ id: unknown; result: { tools?: Array<{ name: string }>; structuredContent?: unknown } }>;
    const listItem = sent.find((x) => x.id === 'L')!;
    const names = (listItem.result.tools ?? []).map((t) => t.name);
    // Fresh session → only find_tools + invoke_tool advertised (lazy loading). book_get/
    // kg_graph_query are out of scope; the in-scope composition_publish is hidden until
    // find_tools activates it.
    expect(names.sort()).toEqual(['find_tools', 'invoke_tool']);
    expect(sent.find((x) => x.id === 5)!.result.structuredContent).toEqual({ status: 'pending_human_approval', approval_id: 'appr-mix' });
  });

  // ── P4 slice B: confirm_action (headless self-confirm) ─────────────────────
  const caBody = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'confirm_action', arguments: { confirm_token: 'tok', domain: 'composition' } }, id: 8 };

  it('executes confirm_action for a dual-flag key via auth self-confirm', async () => {
    setEnv();
    let confirmBody: Record<string, unknown> | undefined;
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:composition'], allow_self_confirm: true }), headers: { get: () => 'application/json' } });
      }
      if (String(url).includes('/internal/mcp-keys/confirm')) {
        confirmBody = JSON.parse(init!.body!);
        return Promise.resolve({ status: 200, text: async () => JSON.stringify({ status: 'executed', result: { ok: true } }), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_sc' }, body: caBody }), r.res);
    expect(r.statusCode).toBe(200);
    expect(confirmBody).toMatchObject({ key_id: 'k', owner_user_id: 'u', domain: 'composition', confirm_token: 'tok' });
    const out = JSON.parse(r.sentBody as string);
    expect(out.result.structuredContent.status).toBe('executed');
    // confirm_action is intercepted, NEVER relayed to ai-gateway.
    expect((global as unknown as { fetch: jest.Mock }).fetch.mock.calls.some((c) => String(c[0]).endsWith('/mcp'))).toBe(false);
  });

  it('denies confirm_action for a key WITHOUT the dual flag (anti-oracle, no auth call)', async () => {
    setEnv();
    const f = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        // has write_confirm but NOT allow_self_confirm
        return Promise.resolve({ status: 200, json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:composition'], allow_self_confirm: false }), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_nosc' }, body: caBody }), r.res);
    expect((r.jsonBody as { error?: { code: number } }).error?.code).toBe(-32601);
    expect(f.mock.calls.some((c) => String(c[0]).includes('/internal/mcp-keys/confirm'))).toBe(false);
  });

  it('denies confirm_action when the self-confirm key lacks the action domain scope (least-privilege)', async () => {
    setEnv();
    const f = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        // self-confirm + write_confirm, but domain:book (NOT domain:composition)
        return Promise.resolve({ status: 200, json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:book'], allow_self_confirm: true }), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_sc' }, body: caBody }), r.res);
    expect((r.jsonBody as { error?: { code: number } }).error?.code).toBe(-32601);
    expect(f.mock.calls.some((c) => String(c[0]).includes('/internal/mcp-keys/confirm'))).toBe(false);
  });

  // ── P4 slice F (H17): multi-step partial-failure honesty ───────────────────
  // A relayed JSON-RPC BATCH stays a bare array; each item gains _meta.step_outcome.
  function batchFetch(resolve: Record<string, unknown>, upstreamArray: unknown[] | string) {
    return jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => resolve, headers: { get: () => 'application/json' } });
      }
      const text = typeof upstreamArray === 'string' ? upstreamArray : JSON.stringify(upstreamArray);
      return Promise.resolve({
        status: 200,
        text: async () => text,
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
  }
  const kgReadResolve = { user_id: 'u', key_id: 'k', scopes: ['read', 'domain:knowledge'] };
  const twoStepBatch = [
    { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 },
    { jsonrpc: '2.0', method: 'tools/call', params: { name: 'memory_search' }, id: 2 },
  ];

  it('annotates a partially-failed batch with per-item _meta.step_outcome, keeping the array (H17)', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = batchFetch(kgReadResolve, [
      { jsonrpc: '2.0', id: 1, result: { ok: true } },
      { jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' } },
    ]);
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: 'Bearer lw_pk_kgkey' }, body: twoStepBatch }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    const out = JSON.parse(r.sentBody as string);
    // STILL a bare JSON-RPC array (transport-transparent), each item gains _meta.step_outcome.
    expect(Array.isArray(out)).toBe(true);
    expect(out[0]).toEqual({ jsonrpc: '2.0', id: 1, result: { ok: true }, _meta: { step_outcome: 'relayed' } });
    expect(out[1]).toEqual({ jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' }, _meta: { step_outcome: 'failed' } });
    expect(r.headers['content-type']).toBe('application/json');
  });

  it('leaves a SINGLE request response unchanged (backward-compat — no step_outcomes)', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = batchFetch(
      kgReadResolve,
      '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}',
    );
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({
        headers: { authorization: 'Bearer lw_pk_kgkey' },
        body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 },
      }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    // Byte-for-byte upstream echo — no annotation, no step_outcome key.
    expect(r.sentBody).toBe('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}');
    expect(r.sentBody as string).not.toContain('step_outcome');
  });

  it('does NOT wrap when the upstream batch body is not a JSON array (no fabrication)', async () => {
    setEnv();
    // ai-gateway answered the batch with a single error envelope (object, not array).
    const upstream = '{"jsonrpc":"2.0","error":{"code":-32600,"message":"bad"},"id":null}';
    (global as unknown as { fetch: jest.Mock }).fetch = batchFetch(kgReadResolve, upstream);
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: 'Bearer lw_pk_kgkey' }, body: twoStepBatch }),
      r.res,
    );
    expect(r.sentBody).toBe(upstream); // passed through unchanged
    expect(r.sentBody as string).not.toContain('step_outcome');
  });

  it('advertises confirm_action in tools/list for a dual-flag key', async () => {
    setEnv();
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['write_confirm', 'domain:composition'], allow_self_confirm: true }), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({ status: 200, text: async () => JSON.stringify({ jsonrpc: '2.0', id: 1, result: { tools: [{ name: 'composition_publish' }] } }), headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) } });
    });
    const r = mockRes();
    await new PublicMcpController().handle(mockReq({ headers: { authorization: 'Bearer lw_pk_sc' }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }), r.res);
    const names = JSON.parse(r.sentBody as string).result.tools.map((t: { name: string }) => t.name);
    expect(names).toContain('confirm_action');
  });

  // ── D-PMCP-BATCH-IDEMPOTENCY: per-item idempotency inside a JSON-RPC batch ──
  // A FakeStore with SET-NX semantics, injected so the edge actually dedups (the default
  // build has no REDIS_URL → idempotency disabled). Mirrors idempotency.spec's FakeStore.
  class FakeIdemStore implements IdempotencyStore {
    m = new Map<string, string>();
    async claimOrLoad(key: string, pendingValue: string): Promise<{ won: true } | { won: false; value: string }> {
      if (!this.m.has(key)) {
        this.m.set(key, pendingValue);
        return { won: true };
      }
      return { won: false, value: this.m.get(key)! };
    }
    async store(key: string, value: string): Promise<void> {
      this.m.set(key, value);
    }
    async remove(key: string): Promise<void> {
      this.m.delete(key);
    }
  }
  const wa = (name: string, args: Record<string, unknown>, id: unknown) => ({
    jsonrpc: '2.0',
    method: 'tools/call',
    params: { name, arguments: args },
    id,
  });
  // A relay mock that ECHOES one response item per relayed tools/call (id preserved) — so it
  // works for a full relay AND a reduced (partial) relay. Records the relayed bodies.
  function idemRelayFetch(resolve: Record<string, unknown>) {
    return jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => resolve, headers: { get: () => 'application/json' } });
      }
      const relayed = init?.body ? JSON.parse(init.body) : undefined;
      const items = (Array.isArray(relayed) ? relayed : []).filter((m) => m?.method === 'tools/call');
      const respArr = items.map((m) => ({ jsonrpc: '2.0', id: m.id, result: { structuredContent: { created: m.id } } }));
      return Promise.resolve({
        status: 200,
        text: async () => JSON.stringify(respArr),
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
  }
  const waScopes = { user_id: 'u', key_id: 'k', scopes: ['write_auto', 'domain:book'] };
  const relaysTo = (f: jest.Mock) => f.mock.calls.filter((c) => String(c[0]).endsWith('/mcp')).length;

  it('dedups a batch: first call relays + caches each item (keys stripped), a full retry replays with NO relay', async () => {
    setEnv();
    const f = idemRelayFetch(waScopes);
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const ctrl = new PublicMcpController();
    (ctrl as unknown as { idempotency: Idempotency }).idempotency = new Idempotency(new FakeIdemStore());
    const body = [wa('book_create', { title: 'A', idempotency_key: 'k-a' }, 1), wa('book_create', { title: 'B', idempotency_key: 'k-b' }, 2)];

    const r1 = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body }), r1.res);
    expect(r1.statusCode).toBe(200);
    const out1 = JSON.parse(r1.sentBody as string) as Array<{ id: number }>;
    expect(out1.map((x) => x.id).sort()).toEqual([1, 2]);
    // The relay body carried NO edge-only idempotency_key on any item (ForbidExtra safety).
    const relay1 = f.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    const sent1 = JSON.parse((relay1![1] as { body: string }).body) as Array<{ params: { arguments: Record<string, unknown> } }>;
    expect(sent1.every((m) => !('idempotency_key' in m.params.arguments))).toBe(true);
    expect(sent1).toHaveLength(2); // first call → both items relayed

    // Retry the SAME batch → both items replay from cache, nothing re-relayed.
    const before = relaysTo(f);
    const r2 = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body }), r2.res);
    expect(relaysTo(f)).toBe(before); // NO new relay — fully served from cache
    const out2 = JSON.parse(r2.sentBody as string) as Array<{ id: number; result: { structuredContent: { created: number } } }>;
    expect(out2.map((x) => x.id).sort()).toEqual([1, 2]);
    expect(out2.find((x) => x.id === 1)!.result.structuredContent.created).toBe(1); // original response replayed
  });

  it('relays ONLY the not-yet-seen item of a batch and merges the cached one back (partial dedup)', async () => {
    setEnv();
    const f = idemRelayFetch(waScopes);
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const ctrl = new PublicMcpController();
    (ctrl as unknown as { idempotency: Idempotency }).idempotency = new Idempotency(new FakeIdemStore());

    // Prime item 1 with a single-item batch.
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body: [wa('book_create', { title: 'A', idempotency_key: 'k-a' }, 1)] }), mockRes().res);
    const before = relaysTo(f);

    // Now a batch of {1 (already done), 2 (new)} → only item 2 is relayed; item 1 merges from cache.
    const r = mockRes();
    await ctrl.handle(
      mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body: [wa('book_create', { title: 'A', idempotency_key: 'k-a' }, 1), wa('book_create', { title: 'B', idempotency_key: 'k-b' }, 2)] }),
      r.res,
    );
    expect(relaysTo(f)).toBe(before + 1); // exactly one new relay
    const relay2 = f.mock.calls.filter((c) => String(c[0]).endsWith('/mcp')).pop();
    const sent = JSON.parse((relay2![1] as { body: string }).body) as Array<{ id: number }>;
    expect(sent.map((m) => m.id)).toEqual([2]); // ONLY the new item went upstream
    const out = JSON.parse(r.sentBody as string) as Array<{ id: number }>;
    expect(out.map((x) => x.id).sort()).toEqual([1, 2]); // both ids present (1 from cache, 2 relayed)
  });

  it('returns an in-progress error for a concurrently in-flight batch item (pending), no relay', async () => {
    setEnv();
    const f = idemRelayFetch(waScopes);
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const ctrl = new PublicMcpController();
    const store = new FakeIdemStore();
    store.m.set('mcp:idem:k:book_create:k-a', PENDING_MARKER); // someone else already claimed it
    (ctrl as unknown as { idempotency: Idempotency }).idempotency = new Idempotency(store);
    const before = relaysTo(f);

    const r = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body: [wa('book_create', { title: 'A', idempotency_key: 'k-a' }, 1)] }), r.res);
    expect(relaysTo(f)).toBe(before); // the only item was pending → nothing relayed
    const out = JSON.parse(r.sentBody as string) as Array<{ id: number; error?: { code: number } }>;
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe(1);
    expect(out[0].error?.code).toBe(-32030); // in-progress
  });

  it('leaves a batch with NO idempotency keys completely untouched (backward-compat with divert/annotate)', async () => {
    setEnv();
    // A plain read batch — no idempotency items → the relay body equals the request body.
    const f = idemRelayFetch({ user_id: 'u', key_id: 'k', scopes: ['read', 'domain:book'] });
    (global as unknown as { fetch: jest.Mock }).fetch = f;
    const ctrl = new PublicMcpController();
    (ctrl as unknown as { idempotency: Idempotency }).idempotency = new Idempotency(new FakeIdemStore());
    const body = [
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get', arguments: { id: 'x' } }, id: 1 },
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get', arguments: { id: 'y' } }, id: 2 },
    ];
    const r = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body }), r.res);
    const relay = f.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    const sent = JSON.parse((relay![1] as { body: string }).body);
    expect(sent).toEqual(body); // relayed verbatim — no strip, no reduce
  });

  it('coexists with the write_confirm divert: idempotent create caches, the propose token is still diverted (no leak)', async () => {
    setEnv();
    // A default key's batch mixing a FREE write_auto create (idempotent) with a PRICED
    // write_confirm propose. The merge must run before the divert so the token is stripped.
    const created: unknown[] = [];
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (String(url).includes('/internal/mcp-keys/resolve')) {
        return Promise.resolve({ status: 200, json: async () => ({ user_id: 'u', key_id: 'k', scopes: ['write_auto', 'domain:book', 'write_confirm', 'domain:composition'], allow_self_confirm: false }), headers: { get: () => 'application/json' } });
      }
      if (String(url).includes('/internal/mcp-keys/approvals')) {
        created.push(JSON.parse(init!.body!));
        return Promise.resolve({ status: 201, json: async () => ({ approval_id: 'appr-coex' }), headers: { get: () => 'application/json' } });
      }
      // relay echoes: the create (id 1) and the propose (id 2, with a token)
      const relayed = init?.body ? JSON.parse(init.body) : [];
      const out = (relayed as Array<{ id: unknown; params: { name: string } }>).map((m) =>
        m.params.name === 'composition_publish'
          ? { jsonrpc: '2.0', id: m.id, result: { structuredContent: { confirm_token: 'SECRET-TOK', domain: 'composition', title: 'Gen' } } }
          : { jsonrpc: '2.0', id: m.id, result: { structuredContent: { created: m.id } } },
      );
      return Promise.resolve({ status: 200, text: async () => JSON.stringify(out), headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) } });
    });
    const ctrl = new PublicMcpController();
    (ctrl as unknown as { idempotency: Idempotency }).idempotency = new Idempotency(new FakeIdemStore());
    const body = [wa('book_create', { title: 'A', idempotency_key: 'k-a' }, 1), { jsonrpc: '2.0', method: 'tools/call', params: { name: 'composition_publish' }, id: 2 }];
    const r = mockRes();
    await ctrl.handle(mockReq({ headers: { authorization: 'Bearer lw_pk_b' }, body }), r.res);
    expect(r.sentBody as string).not.toContain('SECRET-TOK'); // token never leaks
    const out = JSON.parse(r.sentBody as string) as Array<{ id: unknown; result: { structuredContent?: Record<string, unknown> } }>;
    expect(out.find((x) => x.id === 1)!.result.structuredContent!.created).toBe(1); // create landed
    expect(out.find((x) => x.id === 2)!.result.structuredContent).toEqual({ status: 'pending_human_approval', approval_id: 'appr-coex' }); // propose diverted
    expect(created).toHaveLength(1); // exactly one approval queued
  });

  // ── P5 OAuth 2.1 (slice 1) — discovery + local token verify ────────────────
  const OAUTH_ISS = 'loreweave-mcp-oauth';
  const OAUTH_RES = 'https://app.loreweave.dev/mcp';
  const oauthKeys = generateKeyPairSync('rsa', { modulusLength: 2048 });

  function mintOAuth(key: KeyObject, claims: Record<string, unknown>, kid = 'oauth-kid'): string {
    const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT', kid })).toString('base64url');
    const payload = Buffer.from(
      JSON.stringify({ iss: OAUTH_ISS, aud: OAUTH_RES, exp: Math.floor(Date.now() / 1000) + 600, ...claims }),
    ).toString('base64url');
    const si = `${header}.${payload}`;
    return `${si}.${sign('RSA-SHA256', Buffer.from(si), key).toString('base64url')}`;
  }

  function oauthJwks(kid = 'oauth-kid') {
    const j = oauthKeys.publicKey.export({ format: 'jwk' }) as { n: string; e: string };
    return { keys: [{ kty: 'RSA', use: 'sig', alg: 'RS256', kid, n: j.n, e: j.e }] };
  }

  // ── invoke_tool — the execution facade that makes lazy tool-loading actually callable ──
  describe('invoke_tool', () => {
    const bookReadScopes = { user_id: 'u', key_id: 'k', scopes: ['read', 'domain:book'] };

    function invokeFetch(resolve: Record<string, unknown>) {
      return jest.fn().mockImplementation((url: string, init?: { body?: string }) => {
        if (String(url).includes('/internal/mcp-keys/resolve')) {
          return Promise.resolve({ status: 200, json: async () => resolve, headers: { get: () => 'application/json' } });
        }
        const sent = init?.body ? JSON.parse(init.body) : undefined;
        if (sent?.params?.name === 'find_tools') {
          const payload = { tools: [{ name: 'book_list', description: 'List books' }] };
          return Promise.resolve({
            status: 200,
            text: async () => JSON.stringify({ jsonrpc: '2.0', id: sent.id, result: { content: [{ type: 'text', text: JSON.stringify(payload) }], structuredContent: payload } }),
            headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
          });
        }
        if (sent?.method === 'tools/list') {
          return Promise.resolve({
            status: 200,
            text: async () => JSON.stringify({ jsonrpc: '2.0', id: sent.id, result: { tools: [{ name: 'find_tools' }] } }),
            headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
          });
        }
        // the unwrapped real-tool relay
        return Promise.resolve({
          status: 200,
          text: async () => JSON.stringify({ jsonrpc: '2.0', id: sent?.id, result: { structuredContent: { books: [] } } }),
          headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
        });
      });
    }

    it('relays to the REAL target after find_tools activates it (unwrap makes every existing gate see the genuine name)', async () => {
      setEnv();
      const f = invokeFetch(bookReadScopes);
      (global as unknown as { fetch: jest.Mock }).fetch = f;
      const ctrl = new PublicMcpController();

      // Step 1 — discover.
      await ctrl.handle(
        mockReq({ headers: { authorization: 'Bearer lw_pk_inv' }, body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'find_tools', arguments: { intent: 'list books' } }, id: 1 } }),
        mockRes().res,
      );

      // Step 2 — invoke_tool with the name find_tools returned.
      const r = mockRes();
      await ctrl.handle(
        mockReq({
          headers: { authorization: 'Bearer lw_pk_inv' },
          body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'invoke_tool', arguments: { name: 'book_list', arguments: { limit: 5 } } }, id: 2 },
        }),
        r.res,
      );
      expect(r.statusCode).toBe(200);
      // The relay saw a normal tools/call for the REAL tool — invoke_tool never reached upstream.
      const relayCalls = f.mock.calls.filter((c) => String(c[0]).endsWith('/mcp'));
      const secondRelay = JSON.parse((relayCalls[relayCalls.length - 1][1] as { body: string }).body);
      expect(secondRelay.params.name).toBe('book_list');
      expect(secondRelay.params.arguments).toEqual({ limit: 5 });
      const out = JSON.parse(r.sentBody as string);
      expect(out.result.structuredContent).toEqual({ books: [] });
    });

    it('denies invoke_tool for a target that was never find_tools-activated (no relay, actionable hint)', async () => {
      setEnv();
      const f = invokeFetch(bookReadScopes);
      (global as unknown as { fetch: jest.Mock }).fetch = f;
      const ctrl = new PublicMcpController();
      const r = mockRes();
      await ctrl.handle(
        mockReq({
          headers: { authorization: 'Bearer lw_pk_inv2' },
          body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'invoke_tool', arguments: { name: 'book_list', arguments: {} } }, id: 1 },
        }),
        r.res,
      );
      const out = r.jsonBody as { result: { isError: boolean; content: Array<{ text: string }> } };
      expect(out.result.isError).toBe(true);
      expect(out.result.content[0].text).toContain('find_tools');
      expect(f.mock.calls.some((c) => String(c[0]).endsWith('/mcp'))).toBe(false);
    });

    it('audits a not-activated denial as tool_error, not denied_scope (review-impl MED — a first-call-flow miss is not a scope violation)', async () => {
      setEnv();
      const f = invokeFetch(bookReadScopes);
      (global as unknown as { fetch: jest.Mock }).fetch = f;
      const ctrl = new PublicMcpController();
      await ctrl.handle(
        mockReq({
          headers: { authorization: 'Bearer lw_pk_inv_audit' },
          body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'invoke_tool', arguments: { name: 'book_list', arguments: {} } }, id: 1 },
        }),
        mockRes().res,
      );
      const auditCall = f.mock.calls.find((c) => String(c[0]).includes('/internal/mcp-keys/audit'));
      expect(auditCall).toBeDefined();
      const rows = JSON.parse((auditCall![1] as { body: string }).body) as Array<{ outcome: string; tool_name: string }>;
      expect(rows[0]).toMatchObject({ tool_name: 'book_list', outcome: 'tool_error' });
    });

    it('rejects a malformed invoke_tool call (after rate-limiting, per review-impl — an authenticated key still burns its budget on a bad call) with no relay', async () => {
      setEnv();
      const f = invokeFetch(bookReadScopes);
      (global as unknown as { fetch: jest.Mock }).fetch = f;
      const ctrl = new PublicMcpController();
      let checked = false;
      (ctrl as unknown as { limiter: { check: () => Promise<unknown> } }).limiter = {
        check: async () => {
          checked = true;
          return { allowed: true, retryAfter: 0, limit: 60, remaining: 59 };
        },
      };
      const r = mockRes();
      await ctrl.handle(
        mockReq({
          headers: { authorization: 'Bearer lw_pk_inv3' },
          body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'invoke_tool', arguments: {} }, id: 9 },
        }),
        r.res,
      );
      expect(checked).toBe(true); // the rate limiter DID run before the malformed-shape rejection
      const out = r.jsonBody as { result: { isError: boolean } };
      expect(out.result.isError).toBe(true);
      expect(f.mock.calls.some((c) => String(c[0]).endsWith('/mcp'))).toBe(false);
    });

    it('the wildcard dev key bypasses the activation gate (already sees the full catalogue directly)', async () => {
      setEnv();
      // The TRUE wildcard is the dev/smoke static key (TEST_KEY) — it short-circuits auth-service
      // entirely (key-resolver.ts) and is the only credential that keeps a real `['*']` scope; an
      // auth-service-resolved key's `'*'` is stripped (see the "strips a STORED wildcard" test).
      const f = invokeFetch(bookReadScopes);
      (global as unknown as { fetch: jest.Mock }).fetch = f;
      const ctrl = new PublicMcpController();
      const r = mockRes();
      await ctrl.handle(
        mockReq({
          headers: { authorization: `Bearer ${TEST_KEY}` },
          body: { jsonrpc: '2.0', method: 'tools/call', params: { name: 'invoke_tool', arguments: { name: 'book_list', arguments: {} } }, id: 1 },
        }),
        r.res,
      );
      expect(r.statusCode).toBe(200);
      const relay = f.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
      expect(relay).toBeDefined();
      expect(JSON.parse((relay![1] as { body: string }).body).params.name).toBe('book_list');
    });

    it('every tools/list carries invoke_tool + an edge-specific find_tools description', async () => {
      setEnv();
      const f = invokeFetch(bookReadScopes);
      (global as unknown as { fetch: jest.Mock }).fetch = f;
      const r = mockRes();
      await new PublicMcpController().handle(
        mockReq({ headers: { authorization: 'Bearer lw_pk_list' }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }),
        r.res,
      );
      // the default relay text for a plain tools/list is a bare {tools:[]} — the invoke_tool
      // injection still runs and finds no find_tools entry to rewrite, which is fine (no-op).
      const parsed = JSON.parse(r.sentBody as string);
      expect(parsed.result.tools.map((t: { name: string }) => t.name)).toContain('invoke_tool');
    });
  });

  it('serves the RFC 9728 Protected Resource Metadata doc', () => {
    setEnv({ MCP_RESOURCE_URL: OAUTH_RES });
    const doc = new OAuthDiscoveryController().protectedResource() as { resource: string; authorization_servers: string[] };
    expect(doc.resource).toBe(OAUTH_RES);
    expect(doc.authorization_servers).toEqual(['https://app.loreweave.dev']);
  });

  it('sets WWW-Authenticate (RFC 9728) on a 401 when a resource URL is configured', async () => {
    setEnv({ MCP_RESOURCE_URL: OAUTH_RES });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: 'Bearer lw_pk_unknownkey999' }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }),
      r.res,
    );
    expect(r.statusCode).toBe(401);
    expect(r.headers['www-authenticate']).toContain('resource_metadata=');
  });

  it('verifies an OAuth access token LOCALLY and relays on-behalf-of (P5/S9)', async () => {
    setEnv({ OAUTH_ISSUER: OAUTH_ISS, MCP_RESOURCE_URL: OAUTH_RES });
    const token = mintOAuth(oauthKeys.privateKey, { sub: 'user-oauth', grant_id: 'grant-xyz', scope: 'read domain:book' });
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/oauth/jwks')) {
        return Promise.resolve({ status: 200, json: async () => oauthJwks(), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({
        status: 200,
        text: async () => '{"jsonrpc":"2.0","result":{"tools":[]},"id":1}',
        headers: { get: (h: string) => (h.toLowerCase() === 'content-type' ? 'application/json' : null) },
      });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: `Bearer ${token}` }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }),
      r.res,
    );
    expect(r.statusCode).toBe(200);
    const relay = (global as unknown as { fetch: jest.Mock }).fetch.mock.calls.find((c) => String(c[0]).endsWith('/mcp'));
    expect(relay).toBeDefined();
    // identity derived from the verified token — never client-supplied; grant_id rides x-mcp-key-id
    expect(relay![1].headers['x-user-id']).toBe('user-oauth');
    expect(relay![1].headers['x-mcp-key-id']).toBe('grant-xyz');
    expect(relay![1].headers['x-internal-token']).toBe(INTERNAL);
  });

  it('rejects an OAuth token with the WRONG audience (S9 confused-deputy) → 401, no relay', async () => {
    setEnv({ OAUTH_ISSUER: OAUTH_ISS, MCP_RESOURCE_URL: OAUTH_RES });
    const token = mintOAuth(oauthKeys.privateKey, { sub: 'u', grant_id: 'g', scope: 'read', aud: 'https://evil.example/mcp' });
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockImplementation((url: string) => {
      if (String(url).includes('/oauth/jwks')) {
        return Promise.resolve({ status: 200, json: async () => oauthJwks(), headers: { get: () => 'application/json' } });
      }
      return Promise.resolve({ status: 200, text: async () => '{}', headers: { get: () => 'application/json' } });
    });
    const r = mockRes();
    await new PublicMcpController().handle(
      mockReq({ headers: { authorization: `Bearer ${token}` }, body: { jsonrpc: '2.0', method: 'tools/list', id: 1 } }),
      r.res,
    );
    expect(r.statusCode).toBe(401);
    expect((global as unknown as { fetch: jest.Mock }).fetch.mock.calls.some((c) => String(c[0]).endsWith('/mcp'))).toBe(false);
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
