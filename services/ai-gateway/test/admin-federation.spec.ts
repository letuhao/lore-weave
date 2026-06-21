import { Logger } from '@nestjs/common';
import { AdminFederationService } from '../src/federation/admin-federation.service.js';
import { FederationService } from '../src/federation/federation.service.js';
import { AdminMcpController } from '../src/mcp/admin-mcp.controller.js';
import {
  extractAdminEnvelope,
  handleAdminCallTool,
  handleAdminListTools,
} from '../src/mcp/admin-handlers.js';
import { loadConfig, resetConfigForTest } from '../src/config/config.js';
import { computeCatalog } from '../src/federation/catalog.js';

const ADMIN_TOKEN = 'rs256.admin.SECRET-DO-NOT-LOG';

function mockReqRes(headers: Record<string, string | undefined>) {
  const req: any = {
    header: (k: string) => headers[k.toLowerCase()],
    on: () => undefined,
    body: {},
  };
  const res: any = {
    statusCode: 200,
    body: undefined as unknown,
    headersSent: false,
    status(c: number) {
      this.statusCode = c;
      return this;
    },
    json(b: unknown) {
      this.body = b;
      this.headersSent = true;
      return this;
    },
    on: () => undefined,
  };
  return { req, res };
}

beforeAll(() => {
  process.env.INTERNAL_SERVICE_TOKEN = 'tok';
  resetConfigForTest();
});

// ─────────────────────────────────────────────────────────────────────────────
// (a) Catalog isolation — admin tools never blend into the user/book /mcp catalog
// ─────────────────────────────────────────────────────────────────────────────
describe('catalog isolation (INV-T6)', () => {
  it('the admin upstream is NOT a member of the user-facing providers list', () => {
    const cfg = loadConfig();
    const providerUrls = cfg.providers.map((p) => p.mcpUrl);
    const providerNames = cfg.providers.map((p) => p.name);
    // The admin upstream lives in its own config field, never in `providers`,
    // so the user `/mcp` federation (which iterates `providers`) can never list it.
    expect(providerNames).not.toContain('glossary-admin');
    expect(providerUrls).not.toContain(cfg.adminProvider.mcpUrl);
    expect(cfg.adminProvider.mcpUrl).toMatch(/\/mcp\/admin$/);
  });

  it('the user catalog (computeCatalog over providers) contains no admin tool names', () => {
    // Simulate the user federation: only the `providers` upstreams contribute.
    const cfg = loadConfig();
    const userCatalog = computeCatalog(
      cfg.providers.map((p) => ({
        provider: p,
        tools: [{ name: `${p.name}_search`, inputSchema: { type: 'object' } }],
      })),
    );
    const names = userCatalog.toolList.map((t) => t.name);
    expect(names.some((n) => n.startsWith('glossary_admin_'))).toBe(false);
  });

  it('admin and user federation keep distinct catalog sources', async () => {
    // Admin catalog is produced by AdminFederationService against the admin upstream;
    // user catalog is produced by FederationService against `providers`. They are
    // never the same object and the admin one is only reachable WITH a token.
    const admin = new AdminFederationService();
    const listAdmin = jest
      .spyOn(admin as any, 'listAdminTools')
      .mockResolvedValue([{ name: 'glossary_admin_standards_read', inputSchema: {} }]);

    const adminCatalog = await admin.catalogFor({ adminToken: ADMIN_TOKEN });
    expect(adminCatalog.toolList.map((t) => t.name)).toEqual([
      'glossary_admin_standards_read',
    ]);
    // One list call per admin upstream (glossary-admin + knowledge-admin). The spy
    // returns the same glossary tool for both; knowledge-admin's `kg_` prefix drops
    // it, so the merged catalog still has just the glossary admin tool.
    expect(listAdmin).toHaveBeenCalledTimes((admin as any).providers.length);

    // The user FederationService has its own EMPTY/independent catalog state and
    // does not expose any glossary_admin_* tool through its `catalog()` accessor.
    const fed = new FederationService();
    expect((fed.catalog() as any[]).some((t) => String(t.name).startsWith('glossary_admin_'))).toBe(
      false,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (b) No admin token → cannot list/call /mcp/admin (401 passthrough, no enumeration)
// ─────────────────────────────────────────────────────────────────────────────
describe('no admin token → no admin surface (INV-T6 barrier 1)', () => {
  it('controller 401s when the internal token is missing/wrong (before admin check)', async () => {
    const admin = {} as AdminFederationService;
    const { req, res } = mockReqRes({ 'x-internal-token': 'wrong', 'x-admin-token': ADMIN_TOKEN });
    await new AdminMcpController(admin).handle(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.body.error.message).toContain('internal token');
  });

  it('controller 401s when no admin token is present — no enumeration', async () => {
    const admin = {
      catalogFor: jest.fn(),
      executeTool: jest.fn(),
    } as unknown as AdminFederationService;
    const { req, res } = mockReqRes({ 'x-internal-token': 'tok' /* no x-admin-token */ });
    await new AdminMcpController(admin).handle(req, res);
    expect(res.statusCode).toBe(401);
    expect(res.body.error.message).toContain('admin token required');
    // Proven non-enumeration: the federation was never dialed.
    expect((admin as any).catalogFor).not.toHaveBeenCalled();
    expect((admin as any).executeTool).not.toHaveBeenCalled();
  });

  it('AdminFederationService.catalogFor throws without a token (never dials upstream)', async () => {
    const admin = new AdminFederationService();
    const list = jest.spyOn(admin as any, 'listAdminTools');
    await expect(admin.catalogFor({})).rejects.toThrow('admin token required');
    expect(list).not.toHaveBeenCalled();
  });

  it('AdminFederationService.executeTool throws without a token', async () => {
    const admin = new AdminFederationService();
    const prov = { name: 'glossary-admin', mcpUrl: 'http://g/mcp/admin' };
    await expect(admin.executeTool(prov, 'glossary_admin_standards_read', {}, {})).rejects.toThrow(
      'admin token required',
    );
  });

  it('handleAdminListTools propagates an upstream 401 (no partial-catalog fallback)', async () => {
    // An invalid admin token surfaces as a thrown error from the upstream list, so
    // nothing is enumerated rather than degrading to a partial (leaky) catalog.
    const admin = {
      catalogFor: jest.fn().mockRejectedValue(new Error('HTTP 401 Unauthorized')),
    } as unknown as AdminFederationService;
    await expect(
      handleAdminListTools(admin, { 'x-admin-token': 'invalid' }),
    ).rejects.toThrow('401');
  });

  it('handleAdminCallTool rejects a tool not present in the live admin catalog', async () => {
    const admin = {
      catalogFor: jest
        .fn()
        .mockResolvedValue(computeCatalog([])), // empty admin catalog
      providerFor: (name: string, cat: any) => cat.toolToProvider.get(name),
      executeTool: jest.fn(),
    } as unknown as AdminFederationService;
    const res = await handleAdminCallTool(admin, 'glossary_search', {}, {
      'x-admin-token': ADMIN_TOKEN,
    });
    expect(res.isError).toBe(true);
    expect(res.content[0].text).toContain('unknown admin tool');
    expect((admin as any).executeTool).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (b2) KM5-M4b — multiple admin upstreams (glossary + knowledge), disjoint namespaces
// ─────────────────────────────────────────────────────────────────────────────
describe('multi-provider admin federation (KM5-M4b)', () => {
  const tool = (name: string) => ({ name, inputSchema: { type: 'object' } });

  it('config registers glossary-admin AND knowledge-admin (kg_), neither in user providers', () => {
    const cfg = loadConfig();
    const byName = Object.fromEntries(cfg.adminProviders.map((p) => [p.name, p]));
    expect(Object.keys(byName).sort()).toEqual(['glossary-admin', 'knowledge-admin']);
    expect(byName['knowledge-admin'].mcpUrl).toMatch(/\/mcp\/admin$/);
    expect(byName['knowledge-admin'].prefix).toBe('kg_');
    // both admin upstreams are policed → namespace-disjoint shared catalog (LOW-2)
    expect(byName['glossary-admin'].prefix).toBe('glossary_');
    // INV-T6: admin upstreams are never user-facing providers.
    const userNames = cfg.providers.map((p) => p.name);
    expect(userNames).not.toContain('knowledge-admin');
    expect(userNames).not.toContain('glossary-admin');
    // back-compat alias still points at the first (glossary) admin upstream
    expect(cfg.adminProvider.name).toBe('glossary-admin');
  });

  it('merged admin catalog keeps BOTH glossary_admin_* and kg_admin_*; drops cross-namespace', () => {
    const cat = computeCatalog([
      { provider: { name: 'glossary-admin', mcpUrl: 'http://g/mcp/admin' }, tools: [tool('glossary_admin_genre_create')] },
      {
        provider: { name: 'knowledge-admin', mcpUrl: 'http://k/mcp/admin', prefix: 'kg_' },
        tools: [tool('kg_admin_propose_template'), tool('glossary_admin_smuggled')],
      },
    ], jest.fn());
    const names = cat.toolList.map((t) => t.name);
    expect(names).toContain('glossary_admin_genre_create');
    expect(names).toContain('kg_admin_propose_template');
    // a non-kg_ tool from the knowledge-admin upstream is dropped (namespace gate)
    expect(names).not.toContain('glossary_admin_smuggled');
  });

  it('routes each admin tool to its OWNING upstream (providerFor mapping) — the M4b core', () => {
    const glossaryAdmin = { name: 'glossary-admin', mcpUrl: 'http://g/mcp/admin', prefix: 'glossary_' };
    const knowledgeAdmin = { name: 'knowledge-admin', mcpUrl: 'http://k/mcp/admin', prefix: 'kg_' };
    const cat = computeCatalog([
      { provider: glossaryAdmin, tools: [tool('glossary_admin_propose_create')] },
      { provider: knowledgeAdmin, tools: [tool('kg_admin_propose_template')] },
    ], jest.fn());
    const admin = new AdminFederationService();
    // a glossary admin tool resolves to the glossary upstream URL; a kg_ one to knowledge.
    expect(admin.providerFor('glossary_admin_propose_create', cat)?.mcpUrl).toBe('http://g/mcp/admin');
    expect(admin.providerFor('kg_admin_propose_template', cat)?.mcpUrl).toBe('http://k/mcp/admin');
    expect(admin.providerFor('nonexistent_tool', cat)).toBeUndefined();
  });

  it('catalogFor degrades to PARTIAL when one upstream is down but the token is valid', async () => {
    const admin = new AdminFederationService();
    jest.spyOn(admin as any, 'listAdminTools').mockImplementation(async (p: any) => {
      if (p.name === 'glossary-admin') return [tool('glossary_admin_genre_create')];
      throw new Error('HTTP 503 knowledge-admin down');
    });
    const cat = await admin.catalogFor({ adminToken: ADMIN_TOKEN });
    expect(cat.toolList.map((t) => t.name)).toEqual(['glossary_admin_genre_create']);
    expect(cat.partial).toBe(true);
  });

  it('catalogFor THROWS when EVERY upstream errors (invalid token → all 401 → no enumeration)', async () => {
    const admin = new AdminFederationService();
    jest.spyOn(admin as any, 'listAdminTools').mockRejectedValue(new Error('HTTP 401 Unauthorized'));
    await expect(admin.catalogFor({ adminToken: 'invalid' })).rejects.toThrow('401');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// (c) X-Admin-Token is redacted — never appears in any log
// ─────────────────────────────────────────────────────────────────────────────
describe('X-Admin-Token is never logged (§6.7, §11 #7)', () => {
  it('extractAdminEnvelope reads the token but it is carried only in the envelope', () => {
    const env = extractAdminEnvelope({ 'x-admin-token': ADMIN_TOKEN, 'x-user-id': 'u1' });
    expect(env.adminToken).toBe(ADMIN_TOKEN);
    expect(env.userId).toBe('u1');
  });

  it('adminHeaders sets X-Admin-Token + X-Internal-Token for the upstream call', () => {
    const admin = new AdminFederationService();
    const headers = (admin as any).adminHeaders({
      adminToken: ADMIN_TOKEN,
      userId: 'u1',
      traceId: 't1',
    });
    expect(headers['X-Admin-Token']).toBe(ADMIN_TOKEN);
    expect(headers['X-Internal-Token']).toBe('tok');
    expect(headers['X-User-Id']).toBe('u1');
    expect(headers['X-Trace-Id']).toBe('t1');
  });

  it('a failing admin tool call logs the failure WITHOUT the admin token', async () => {
    const logged: string[] = [];
    const warnSpy = jest
      .spyOn(Logger.prototype, 'warn')
      .mockImplementation((msg: any) => {
        logged.push(String(msg));
        return undefined as any;
      });
    try {
      const admin = {
        catalogFor: jest
          .fn()
          .mockResolvedValue(
            computeCatalog([
              {
                provider: { name: 'glossary-admin', mcpUrl: 'http://g/mcp/admin' },
                tools: [{ name: 'glossary_admin_standards_read', inputSchema: {} }],
              },
            ]),
          ),
        providerFor: (name: string, cat: any) => cat.toolToProvider.get(name),
        executeTool: jest.fn().mockRejectedValue(new Error('upstream boom')),
      } as unknown as AdminFederationService;

      const res = await handleAdminCallTool(
        admin,
        'glossary_admin_standards_read',
        {},
        { 'x-admin-token': ADMIN_TOKEN },
      );
      expect(res.isError).toBe(true);
      // The failure was logged...
      expect(logged.some((l) => l.includes('glossary_admin_standards_read'))).toBe(true);
      // ...but the secret admin token NEVER appears in any log line.
      expect(logged.some((l) => l.includes(ADMIN_TOKEN))).toBe(false);
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('the controller error path logs a generic message without the admin token', async () => {
    const logged: string[] = [];
    const warnSpy = jest
      .spyOn(Logger.prototype, 'warn')
      .mockImplementation((msg: any) => {
        logged.push(String(msg));
        return undefined as any;
      });
    // Force the proxy build to throw so we hit the controller's catch branch
    // synchronously (no real transport / socket needed — avoids SDK stderr noise).
    const factory = require('../src/mcp/admin-proxy-server.factory.js');
    const buildSpy = jest
      .spyOn(factory, 'buildAdminProxyServer')
      .mockImplementation(() => {
        throw new Error('boom-no-token-here');
      });
    try {
      const admin = {} as AdminFederationService;
      const { req, res } = mockReqRes({
        'x-internal-token': 'tok',
        'x-admin-token': ADMIN_TOKEN,
      });
      await new AdminMcpController(admin).handle(req, res);
      // The catch branch ran (generic message logged) and the token is absent.
      expect(logged.some((l) => l.includes('admin MCP request handling failed'))).toBe(true);
      expect(logged.some((l) => l.includes(ADMIN_TOKEN))).toBe(false);
      expect(res.statusCode).toBe(500);
    } finally {
      buildSpy.mockRestore();
      warnSpy.mockRestore();
    }
  });
});
