import { Injectable, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { AppConfig, ProviderConfig, loadConfig } from '../config/config.js';
import { Catalog, computeCatalog, ProviderResult } from './catalog.js';

/** Per-call identity forwarded to a provider (SO-1 / INV-7). Never sourced from the LLM. */
export interface Envelope {
  userId?: string;
  sessionId?: string;
  traceId?: string;
}

const EMPTY: Catalog = {
  toolList: [],
  toolToProvider: new Map(),
  version: '',
  partial: false,
};

/**
 * FederationService — the heart of the gateway.
 *
 *  • Periodically lists tools from every provider's MCP and rebuilds the
 *    `tool name -> provider` registry + catalog version (H10). Degrades to a
 *    PARTIAL catalog when a provider is unreachable — never throws.
 *  • Executes a tool via a **fresh, per-call** downstream MCP client carrying
 *    that call's envelope headers (INV-7 — no cross-user connection reuse).
 *    Each provider is an independent MCP session (H14).
 */
@Injectable()
export class FederationService implements OnModuleInit, OnModuleDestroy {
  private readonly log = new Logger(FederationService.name);
  private readonly cfg: AppConfig = loadConfig();
  private state: Catalog = EMPTY;
  private timer?: NodeJS.Timeout;

  async onModuleInit(): Promise<void> {
    await this.refresh();
    this.timer = setInterval(() => {
      this.refresh().catch((e) => this.log.warn(`catalog refresh failed: ${e}`));
    }, this.cfg.catalogRefreshMs);
    this.timer.unref?.();
  }

  onModuleDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  catalog(): any[] {
    return this.state.toolList;
  }
  catalogVersion(): string {
    return this.state.version;
  }
  isPartial(): boolean {
    return this.state.partial;
  }
  providerCount(): number {
    return this.cfg.providers.length;
  }
  providerFor(tool: string): ProviderConfig | undefined {
    return this.state.toolToProvider.get(tool);
  }

  /** Re-list every provider and rebuild the catalog. Never throws (best-effort). */
  async refresh(): Promise<void> {
    const results: ProviderResult[] = [];
    for (const provider of this.cfg.providers) {
      try {
        results.push({ provider, tools: await this.listProviderTools(provider) });
      } catch (error) {
        results.push({ provider, error });
        this.log.warn(`provider '${provider.name}' list-tools failed → PARTIAL: ${error}`);
      }
    }
    this.state = computeCatalog(results);
    this.log.log(
      `catalog: ${this.state.toolList.length} tools / ${this.cfg.providers.length} providers ` +
        `(version ${this.state.version || '∅'}${this.state.partial ? ' PARTIAL' : ''})`,
    );
  }

  private async listProviderTools(p: ProviderConfig): Promise<any[]> {
    // Listing needs only the service token — user scope is required on tool
    // DISPATCH (provider side), not on tools/list.
    const client = new Client({ name: 'ai-gateway-federation', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(p.mcpUrl), {
      requestInit: { headers: { 'X-Internal-Token': this.cfg.internalToken } },
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
   * Execute a federated tool. Opens a fresh per-call client carrying the
   * envelope so identity varies per call and is never pinned to a connection
   * shared across users (INV-7). Returns the provider's CallToolResult verbatim.
   */
  async executeTool(
    tool: string,
    args: Record<string, unknown>,
    env: Envelope,
  ): Promise<unknown> {
    const p = this.providerFor(tool);
    if (!p) {
      throw new Error(`unknown tool '${tool}'`);
    }
    const headers: Record<string, string> = { 'X-Internal-Token': this.cfg.internalToken };
    if (env.userId) headers['X-User-Id'] = env.userId;
    if (env.sessionId) headers['X-Session-Id'] = env.sessionId;
    if (env.traceId) headers['X-Trace-Id'] = env.traceId;

    const client = new Client({ name: 'ai-gateway', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(p.mcpUrl), {
      requestInit: { headers },
    });
    try {
      await client.connect(transport);
      return await client.callTool({ name: tool, arguments: args });
    } finally {
      await client.close().catch(() => undefined);
    }
  }
}
