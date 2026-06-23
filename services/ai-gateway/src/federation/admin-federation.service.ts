import { Injectable, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { AppConfig, ProviderConfig, loadConfig } from '../config/config.js';
import { Catalog, computeCatalog, ProviderResult } from './catalog.js';
import { Envelope } from './federation.service.js';

const EMPTY: Catalog = {
  toolList: [],
  toolToProvider: new Map(),
  version: '',
  partial: false,
  // H10 per-provider availability — populated by computeCatalog on a successful
  // list; empty here (no providers listed yet / EMPTY fallback).
  providers: [],
};

/**
 * AdminFederationService — the SEPARATE admin-only federation (INV-T6, spec §4c/§6.2).
 *
 * It is a distinct instance from {@link FederationService} that federates ONLY the
 * `/mcp/admin` upstreams (glossary + knowledge) and keeps its OWN catalog. The two
 * catalogs are NEVER blended — admin tool names cannot appear in the user/book `/mcp`
 * catalog, because this service's tool list lives in a different object the `/mcp`
 * proxy server never reads. Each upstream's C-GW prefix keeps the namespaces disjoint
 * (`glossary_*` vs `kg_*`).
 *
 * Auth model (differs from the user path on purpose):
 *  • `tools/list` and `tools/call` BOTH require the caller's RS256 `X-Admin-Token`,
 *    forwarded to each upstream so its transport middleware can verify `admin:write`
 *    BEFORE listing — a non-admin caller cannot even enumerate the admin tools.
 *  • `X-Internal-Token` is still sent for service trust (SO-1).
 *  • The admin token is a bearer credential and is NEVER logged (§6.7, §11 #7).
 *  • Per-call fresh MCP client (INV-7 — no connection reuse / no admin-token caching).
 */
@Injectable()
export class AdminFederationService implements OnModuleInit, OnModuleDestroy {
  private readonly log = new Logger(AdminFederationService.name);
  private readonly cfg: AppConfig = loadConfig();
  private readonly providers: ProviderConfig[] = this.cfg.adminProviders;
  private state: Catalog = EMPTY;

  // The admin catalog is intentionally NOT refreshed on a background timer: unlike
  // the user catalog it cannot be listed without an admin token, so there is no
  // ambient token the gateway could use to poll it. Each admin `tools/list` lists
  // live from the upstreams with the caller's own token (see catalogFor).
  async onModuleInit(): Promise<void> {
    // no-op: admin catalog is fetched per-request with the caller's token.
  }
  onModuleDestroy(): void {
    // no-op.
  }

  /**
   * List the merged admin catalog using the caller's admin token. Unlike the user
   * path (which can list with only the service token), the admin upstreams are gated
   * at the transport — so a list REQUIRES the admin token. Each upstream is dialed
   * with the caller's token; its C-GW prefix keeps namespaces disjoint.
   *
   * Failure policy (INV-T6 + robustness): if EVERY upstream errors — the invalid /
   * absent-token case, where all return 401 — we throw so the controller relays the
   * 401 and NOTHING is enumerated. If only SOME error (one admin upstream down while
   * the token is still valid for the others), we degrade to a PARTIAL catalog rather
   * than blanking the whole admin surface. No token ⇒ throw before dialing anything.
   */
  async catalogFor(env: Envelope): Promise<Catalog> {
    if (!env.adminToken) {
      // Defense in depth: never dial an admin upstream without a token to present.
      throw new Error('admin token required');
    }
    const results: ProviderResult[] = [];
    const errors: unknown[] = [];
    for (const provider of this.providers) {
      try {
        results.push({ provider, tools: await this.listAdminTools(provider, env) });
      } catch (e) {
        errors.push(e);
        results.push({ provider, error: e });
      }
    }
    // All upstreams failed → surface it loudly (the invalid-token case → all 401),
    // so the controller passes through a 401 and nothing is enumerated (INV-T6).
    if (this.providers.length > 0 && errors.length === this.providers.length) {
      throw errors[0];
    }
    this.state = computeCatalog(results);
    return this.state;
  }

  providerFor(tool: string, catalog: Catalog): ProviderConfig | undefined {
    return catalog.toolToProvider.get(tool);
  }

  private adminHeaders(env: Envelope): Record<string, string> {
    // X-Internal-Token for service trust (SO-1) + X-Admin-Token for admin authority
    // (INV-T2). The admin token is NEVER logged anywhere in this class.
    const headers: Record<string, string> = {
      'X-Internal-Token': this.cfg.internalToken,
      'X-Admin-Token': env.adminToken as string,
    };
    if (env.userId) headers['X-User-Id'] = env.userId;
    if (env.sessionId) headers['X-Session-Id'] = env.sessionId;
    if (env.traceId) headers['X-Trace-Id'] = env.traceId;
    if (env.projectId) headers['X-Project-Id'] = env.projectId;
    return headers;
  }

  private async listAdminTools(provider: ProviderConfig, env: Envelope): Promise<any[]> {
    const client = new Client({ name: 'ai-gateway-admin-federation', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(provider.mcpUrl), {
      requestInit: { headers: this.adminHeaders(env) },
    });
    try {
      await client.connect(transport);
      const res: any = await client.listTools();
      return res?.tools ?? [];
    } finally {
      await client.close().catch(() => undefined);
    }
  }

  /**
   * Execute an admin tool against the upstream that owns it. The caller resolves the
   * owning provider from the per-call catalog (`providerFor`) and passes it in, so
   * routing is race-free (never reads mutable shared state). Fresh per-call client
   * carrying the admin token (INV-7).
   */
  async executeTool(
    provider: ProviderConfig,
    tool: string,
    args: Record<string, unknown>,
    env: Envelope,
    meta?: unknown,
  ): Promise<unknown> {
    if (!env.adminToken) {
      throw new Error('admin token required');
    }
    const client = new Client({ name: 'ai-gateway-admin', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(provider.mcpUrl), {
      requestInit: { headers: this.adminHeaders(env) },
    });
    try {
      await client.connect(transport);
      const params: { name: string; arguments: Record<string, unknown>; _meta?: Record<string, unknown> } = {
        name: tool,
        arguments: args,
      };
      if (meta && typeof meta === 'object') params._meta = meta as Record<string, unknown>;
      return await client.callTool(params);
    } finally {
      await client.close().catch(() => undefined);
    }
  }
}
