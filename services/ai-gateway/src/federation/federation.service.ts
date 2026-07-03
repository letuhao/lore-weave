import { Injectable, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { AppConfig, ProviderConfig, loadConfig } from '../config/config.js';
import {
  AuxCatalog,
  Catalog,
  computeAuxCatalog,
  computeCatalog,
  EMPTY_AUX,
  ProviderAuxResult,
  ProviderAvailability,
  ProviderResult,
  uriScheme,
} from './catalog.js';
import { PerUserOverlay } from './overlay.js';

/** Per-call identity forwarded to a provider (SO-1 / INV-7). Never sourced from the LLM. */
export interface Envelope {
  userId?: string;
  sessionId?: string;
  traceId?: string;
  /**
   * Active project scope (X-Project-Id) — forwarded so project-scoped provider
   * tools (kg_build_graph, kg_build_wiki, any `ctx.project_id`-resolving tool)
   * can resolve "the current project" downstream. Lifted off the request headers
   * only (SEC-1 — never from the LLM); forwarded only when present.
   */
  projectId?: string;
  /**
   * Public MCP API key id (X-Mcp-Key-Id) — set ONLY for traffic that entered via
   * the public edge (mcp-public-gateway). Lifted off the request headers (SEC-1)
   * and forwarded downstream so providers can attribute per-key spend (H-C) and
   * apply the owned-resources-only default (OD-8). Absent on first-party calls.
   */
  mcpKeyId?: string;
  /**
   * Public key per-key USD spend sub-cap (X-Mcp-Spend-Cap-Usd) — set only for
   * public-edge traffic whose key carries a cap. Forwarded downstream (SEC-1)
   * so a priced tool's provider job carries it into job_meta → the
   * provider-registry per-key reserve (H-K). Absent on first-party calls and on
   * keys with no cap.
   */
  spendCapUsd?: string;
  /**
   * Admin authority (INV-T2) — the RS256 `admin:write` token, forwarded ONLY on
   * the admin federation path as `X-Admin-Token`. It is a bearer credential and
   * MUST NEVER be logged or serialized (spec §6.7, §11 #7). The normal `/mcp`
   * federation never sets this; `extractEnvelope` (handlers.ts) never reads it
   * for the user/book surface.
   */
  adminToken?: string;
}

/**
 * Build the downstream header set for a federated `/mcp` tool call: the synthesized
 * X-Internal-Token (SO-1) plus each envelope identity field, forwarded ONLY when
 * present (so an absent field is never sent as an empty string). Identity is always
 * from the envelope, never the LLM (SEC-1). `X-Mcp-Key-Id` rides only this
 * public-reachable surface — the admin path (adminHeaders) never carries it, since
 * the public edge has no route to /mcp/admin (H-A). Extracted as a pure function so
 * the forwarding contract is unit-testable without a live transport.
 */
export function buildEnvelopeHeaders(internalToken: string, env: Envelope): Record<string, string> {
  const headers: Record<string, string> = { 'X-Internal-Token': internalToken };
  if (env.userId) headers['X-User-Id'] = env.userId;
  if (env.sessionId) headers['X-Session-Id'] = env.sessionId;
  if (env.traceId) headers['X-Trace-Id'] = env.traceId;
  if (env.projectId) headers['X-Project-Id'] = env.projectId;
  if (env.mcpKeyId) headers['X-Mcp-Key-Id'] = env.mcpKeyId;
  if (env.spendCapUsd) headers['X-Mcp-Spend-Cap-Usd'] = env.spendCapUsd;
  return headers;
}

const EMPTY: Catalog = {
  toolList: [],
  toolToProvider: new Map(),
  version: '',
  partial: false,
  providers: [],
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
  // Wave C5 — the federated resources + prompts registry, refreshed on the
  // same cadence as the tool catalog.
  private auxState: AuxCatalog = EMPTY_AUX;
  private timer?: NodeJS.Timeout;
  // REG-P2-03 — per-user federation overlay (flag-gated; default off).
  private readonly overlay = new PerUserOverlay({
    enabled: this.cfg.overlayEnabled,
    agentRegistryInternalUrl: this.cfg.agentRegistryInternalUrl,
    internalToken: this.cfg.internalToken,
  });

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

  // ── REG-P2-03 — per-user overlay (flag-gated; default off = no-op) ────────

  /** The caller's registered MCP-server tools to merge into tools/list, under
   * their u_/b_ prefix. Empty when the flag is off, no envelope, or zero regs. */
  async overlayTools(env: Envelope): Promise<any[]> {
    return this.overlay.tools(env);
  }
  /** True iff `name` is an overlay-owned tool (u_/b_ prefix) AND the flag is on. */
  isOverlayTool(name: string): boolean {
    return this.overlay.isOverlayName(name);
  }
  /** Dispatch an overlay tool to the caller's own registered server. */
  async executeOverlay(name: string, args: Record<string, unknown>, env: Envelope, signal?: AbortSignal): Promise<unknown> {
    return this.overlay.dispatch(name, args, env, signal);
  }
  isPartial(): boolean {
    return this.state.partial;
  }
  providerCount(): number {
    return this.cfg.providers.length;
  }
  /** H10 — per-provider availability (`{name, available}`); a down provider
   * reads `available:false` so a consumer's find_tools can say "try again",
   * not "no such tool". Mirrors the configured provider set even before the
   * first refresh (all unavailable until federation runs). */
  providerAvailability(): ProviderAvailability[] {
    if (this.state.providers.length > 0) return this.state.providers;
    return this.cfg.providers.map((p) => ({ name: p.name, available: false }));
  }
  providerFor(tool: string): ProviderConfig | undefined {
    return this.state.toolToProvider.get(tool);
  }

  // ── Wave C5 — resources + prompts (federated like tools) ─────────────

  resourceCatalog(): any[] {
    return this.auxState.resourceList;
  }
  resourceTemplateCatalog(): any[] {
    return this.auxState.resourceTemplateList;
  }
  promptCatalog(): any[] {
    return this.auxState.promptList;
  }
  /** Owning provider for a resources/read URI. A concrete catalog hit wins;
   * otherwise route by URI SCHEME (the C5 namespace rule: scheme == provider
   * name), which is how a TEMPLATE-instantiated URI — never present in the
   * concrete list — finds its provider. The final name-match fallback covers
   * a scheme whose provider listed nothing cacheable yet. */
  providerForResource(uri: string): ProviderConfig | undefined {
    const direct = this.auxState.resourceToProvider.get(uri);
    if (direct) return direct;
    const scheme = uriScheme(uri);
    if (!scheme) return undefined;
    return (
      this.auxState.schemeToProvider.get(scheme) ??
      this.cfg.providers.find((p) => p.name === scheme)
    );
  }
  providerForPrompt(name: string): ProviderConfig | undefined {
    return this.auxState.promptToProvider.get(name);
  }

  /** Re-list every provider and rebuild the catalog. Never throws (best-effort). */
  async refresh(): Promise<void> {
    const results: ProviderResult[] = [];
    const auxResults: ProviderAuxResult[] = [];
    for (const provider of this.cfg.providers) {
      try {
        results.push({ provider, tools: await this.listProviderTools(provider) });
      } catch (error) {
        results.push({ provider, error });
        this.log.warn(`provider '${provider.name}' list-tools failed → PARTIAL: ${error}`);
      }
      // Wave C5 — resources + prompts ride the same refresh cadence. A
      // provider that errors (or lacks the capability — handled inside
      // listProviderAux) contributes empty lists, never breaks the aggregate.
      try {
        auxResults.push({ provider, ...(await this.listProviderAux(provider)) });
      } catch (error) {
        auxResults.push({ provider, error });
        this.log.warn(`provider '${provider.name}' list-resources/prompts failed → empty: ${error}`);
      }
    }
    this.state = computeCatalog(results);
    this.auxState = computeAuxCatalog(auxResults, (m) => this.log.warn(m));
    this.log.log(
      `catalog: ${this.state.toolList.length} tools / ${this.cfg.providers.length} providers ` +
        `(version ${this.state.version || '∅'}${this.state.partial ? ' PARTIAL' : ''}) · ` +
        `${this.auxState.resourceList.length}+${this.auxState.resourceTemplateList.length} ` +
        `resources(+templates) / ${this.auxState.promptList.length} prompts`,
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

  /** Wave C5 — list one provider's resources, resource templates, and prompts.
   * Like tools/list, only the service token rides (identity is enforced on
   * READ dispatch, provider side). Each capability is probed independently:
   * a downstream that doesn't support it (the SDK's client-side capability
   * assertion, or a -32601 method-not-found) contributes `[]` for that list —
   * the aggregate never breaks. A connect failure throws to the caller. */
  private async listProviderAux(
    p: ProviderConfig,
  ): Promise<{ resources: any[]; resourceTemplates: any[]; prompts: any[] }> {
    const client = new Client({ name: 'ai-gateway-federation', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(p.mcpUrl), {
      requestInit: { headers: { 'X-Internal-Token': this.cfg.internalToken } },
    });
    const tryList = async (fn: () => Promise<any[]>): Promise<any[]> => {
      try {
        return await fn();
      } catch {
        return []; // capability missing / method unsupported → empty, not fatal
      }
    };
    try {
      await client.connect(transport);
      const resources = await tryList(async () => ((await client.listResources()) as any)?.resources ?? []);
      const resourceTemplates = await tryList(
        async () => ((await client.listResourceTemplates()) as any)?.resourceTemplates ?? [],
      );
      const prompts = await tryList(async () => ((await client.listPrompts()) as any)?.prompts ?? []);
      return { resources, resourceTemplates, prompts };
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
    meta?: unknown,
    // D-PLANNER-INFLIGHT-ABORT (#19): when set and aborted (inbound chat request
    // closed), the downstream provider callTool is cancelled — its fetch aborts,
    // dropping the provider's HTTP connection so the provider's own r.Context()
    // cancels and a heavy in-flight call (the ~39s glossary_plan) stops instead
    // of running to completion after the user already stopped the turn.
    signal?: AbortSignal,
  ): Promise<unknown> {
    const p = this.providerFor(tool);
    if (!p) {
      throw new Error(`unknown tool '${tool}'`);
    }
    const headers = buildEnvelopeHeaders(this.cfg.internalToken, env);

    const client = new Client({ name: 'ai-gateway', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(p.mcpUrl), {
      requestInit: { headers },
    });
    try {
      await client.connect(transport);
      // Pass the `_meta` channel through when the caller supplied it (AIGW-LOW2).
      const params: { name: string; arguments: Record<string, unknown>; _meta?: Record<string, unknown> } = {
        name: tool,
        arguments: args,
      };
      if (meta && typeof meta === 'object') params._meta = meta as Record<string, unknown>;
      // `signal` propagates an inbound chat-turn stop down to the provider call.
      // Omit `resultSchema` (pass-through) but supply it explicitly since the
      // signal rides the 3rd `options` arg.
      return await client.callTool(params, undefined, signal ? { signal } : undefined);
    } finally {
      await client.close().catch(() => undefined);
    }
  }

  /**
   * Wave C5 — read a federated resource. Fresh per-call client carrying the
   * envelope headers, exactly like {@link executeTool} (INV-7 — identity is
   * never pinned to a shared connection; the provider enforces tenancy on the
   * read). Returns the provider's ReadResourceResult verbatim.
   */
  async readResource(uri: string, env: Envelope, signal?: AbortSignal): Promise<unknown> {
    const p = this.providerForResource(uri);
    if (!p) {
      throw new Error(`unknown resource '${uri}'`);
    }
    const headers = buildEnvelopeHeaders(this.cfg.internalToken, env);
    const client = new Client({ name: 'ai-gateway', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(p.mcpUrl), {
      requestInit: { headers },
    });
    try {
      await client.connect(transport);
      return await client.readResource({ uri }, signal ? { signal } : undefined);
    } finally {
      await client.close().catch(() => undefined);
    }
  }

  /**
   * Wave C5 — get (render) a federated prompt. Same per-call envelope client
   * as {@link readResource}. Returns the provider's GetPromptResult verbatim.
   */
  async getPrompt(
    name: string,
    args: Record<string, unknown>,
    env: Envelope,
    signal?: AbortSignal,
  ): Promise<unknown> {
    const p = this.providerForPrompt(name);
    if (!p) {
      throw new Error(`unknown prompt '${name}'`);
    }
    const headers = buildEnvelopeHeaders(this.cfg.internalToken, env);
    const client = new Client({ name: 'ai-gateway', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(p.mcpUrl), {
      requestInit: { headers },
    });
    try {
      await client.connect(transport);
      return await client.getPrompt(
        // MCP prompt arguments are string-valued on the wire.
        { name, arguments: args as Record<string, string> },
        signal ? { signal } : undefined,
      );
    } finally {
      await client.close().catch(() => undefined);
    }
  }
}
