import { Logger } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import type { Envelope } from './federation.service.js';
import { buildEnvelopeHeaders } from './federation.service.js';

/**
 * REG-P2-03 — the per-user federation overlay. When enabled, a turn's tools/list
 * is the static System catalog PLUS the caller's registered MCP servers (resolved
 * from agent-registry /internal/effective-mcp-servers), each server's tools RENAMED
 * under its mandatory `u_/b_<hash>_` prefix so a user tool can never shadow a System
 * tool. Per-(user, book) cache keyed on agent-registry's catalog_version + a short
 * TTL (Q-CACHE). Fail-open: any resolve error yields an empty overlay so the turn
 * proceeds on the System catalog alone (never breaks a turn).
 */

export interface OverlayConfig {
  enabled: boolean;
  agentRegistryInternalUrl: string;
  internalToken: string;
  /** cache TTL ms (default 30s). */
  ttlMs?: number;
}

interface RouteEntry {
  endpointUrl: string;
  originalName: string;
}

interface OverlayEntry {
  version: number;
  tools: any[];
  route: Map<string, RouteEntry>;
  exp: number;
}

interface EffectiveServer {
  mcp_server_id: string;
  endpoint_url: string;
  transport: string;
  tool_name_prefix: string;
  tier: string;
}

const OVERLAY_NAME_RE = /^[ub]_[0-9a-f]{8}_/;
const EMPTY = { tools: [] as any[], route: new Map<string, RouteEntry>() };

export class PerUserOverlay {
  private readonly log = new Logger('Overlay');
  private readonly cache = new Map<string, OverlayEntry>();
  private readonly ttl: number;

  constructor(private readonly cfg: OverlayConfig) {
    this.ttl = cfg.ttlMs ?? 30_000;
  }

  /** A tool name is overlay-owned iff it carries a u_/b_ prefix (never a System tool). */
  isOverlayName(name: string): boolean {
    return this.cfg.enabled && OVERLAY_NAME_RE.test(name);
  }

  private key(env: Envelope): string {
    return `${env.userId ?? ''}|${env.projectId ?? ''}`;
  }

  /** Resolve the overlay for a turn's envelope (cached). Fail-open → EMPTY. */
  async resolve(env: Envelope): Promise<{ tools: any[]; route: Map<string, RouteEntry> }> {
    if (!this.cfg.enabled || !env.userId) return EMPTY;
    const key = this.key(env);
    const now = Date.now();
    const cached = this.cache.get(key);

    // Cheap freshness probe: fetch the effective server list (carries catalog_version).
    let servers: EffectiveServer[];
    let version: number;
    try {
      const resolved = await this.fetchEffective(env);
      servers = resolved.servers;
      version = resolved.version;
    } catch (e) {
      this.log.warn(`overlay resolve failed (fail-open, System catalog only): ${e}`);
      return cached && cached.exp > now ? cached : EMPTY;
    }

    // Zero registrations → the static fast path (empty overlay, cached briefly).
    if (servers.length === 0) {
      this.cache.set(key, { version, tools: [], route: new Map(), exp: now + this.ttl });
      return EMPTY;
    }
    // Version + TTL hit → reuse (no re-federation of the user servers).
    if (cached && cached.version === version && cached.exp > now) {
      return { tools: cached.tools, route: cached.route };
    }

    // Re-federate each user server: list its tools, rename under its prefix.
    const tools: any[] = [];
    const route = new Map<string, RouteEntry>();
    for (const s of servers) {
      let serverTools: any[];
      try {
        serverTools = await this.listServerTools(s, env);
      } catch (e) {
        this.log.warn(`overlay server '${s.mcp_server_id}' list failed (skipped): ${e}`);
        continue;
      }
      for (const t of serverTools) {
        const prefixed = `${s.tool_name_prefix}${t.name}`;
        if (route.has(prefixed)) continue; // first-wins on a same-user collision
        route.set(prefixed, { endpointUrl: s.endpoint_url, originalName: t.name });
        tools.push({ ...t, name: prefixed });
      }
    }
    this.cache.set(key, { version, tools, route, exp: now + this.ttl });
    return { tools, route };
  }

  /** Tools to merge into tools/list for this envelope. */
  async tools(env: Envelope): Promise<any[]> {
    return (await this.resolve(env)).tools;
  }

  /** Dispatch an overlay tool: strip the prefix, call the owning user server with
   * the per-call envelope. Throws like federation.executeTool so the caller's
   * handleCallTool classifier wraps it as an MCP tool error. */
  async dispatch(name: string, args: Record<string, unknown>, env: Envelope, signal?: AbortSignal): Promise<unknown> {
    const { route } = await this.resolve(env);
    const entry = route.get(name);
    if (!entry) throw new Error(`unknown tool '${name}'`);
    const headers = buildEnvelopeHeaders(this.cfg.internalToken, env);
    const client = new Client({ name: 'ai-gateway-overlay', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(entry.endpointUrl), { requestInit: { headers } });
    try {
      await client.connect(transport);
      return await client.callTool({ name: entry.originalName, arguments: args }, undefined, signal ? { signal } : undefined);
    } finally {
      await client.close().catch(() => undefined);
    }
  }

  private async fetchEffective(env: Envelope): Promise<{ servers: EffectiveServer[]; version: number }> {
    const url = new URL(`${this.cfg.agentRegistryInternalUrl}/internal/effective-mcp-servers`);
    url.searchParams.set('user_id', env.userId!);
    if (env.projectId) url.searchParams.set('book_id', env.projectId);
    const res = await fetch(url, { headers: { 'X-Internal-Token': this.cfg.internalToken } });
    if (!res.ok) throw new Error(`effective-mcp-servers ${res.status}`);
    const body = (await res.json()) as { servers?: EffectiveServer[]; catalog_version?: number };
    return { servers: Array.isArray(body.servers) ? body.servers : [], version: body.catalog_version ?? 0 };
  }

  private async listServerTools(s: EffectiveServer, env: Envelope): Promise<any[]> {
    const headers = buildEnvelopeHeaders(this.cfg.internalToken, env);
    const client = new Client({ name: 'ai-gateway-overlay', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(s.endpoint_url), { requestInit: { headers } });
    try {
      await client.connect(transport);
      const res: any = await client.listTools();
      return res?.tools ?? [];
    } finally {
      await client.close().catch(() => undefined);
    }
  }
}
