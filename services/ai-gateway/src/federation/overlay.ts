import { Logger } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import type { Envelope } from './federation.service.js';
import { buildEnvelopeHeaders } from './federation.service.js';
import { CircuitBreaker, makeEgressFetch, chooseOutboundHeaders } from './egress.js';

// REG-P3-04 — response-size cap for a user server's outbound call (1 MiB).
const EGRESS_MAX_BYTES = 1 << 20;

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
  serverId: string;
  egressAllowlist: string[];
  /** true for an internal loreweave server (dev/system) — skip the SSRF internal-block. */
  allowInternal: boolean;
  authKind: string; // none | bearer | oauth2
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
  is_external?: boolean;
  auth_kind?: string;
  egress_allowlist?: string[];
}

const OVERLAY_NAME_RE = /^[ub]_[0-9a-f]{8}_/;
const EMPTY = { tools: [] as any[], route: new Map<string, RouteEntry>() };

export class PerUserOverlay {
  private readonly log = new Logger('Overlay');
  private readonly cache = new Map<string, OverlayEntry>();
  private readonly ttl: number;
  // /review-impl FIX-A: bound every upstream call so a HUNG agent-registry or a
  // hung user MCP server can never stall the hot path (fail-open only catches
  // errors, not hangs). Resolver probe is tight; per-server list/dispatch a bit
  // looser (a legit tool call may be slow) but still bounded.
  private readonly fetchTimeoutMs = 2_000;
  private readonly callTimeoutMs = 15_000;
  // REG-P3-04 — per-server circuit breaker: 5 consecutive failures → open 30s. A
  // flapping user server then fails fast (tool error) instead of stalling every turn.
  private readonly breaker = new CircuitBreaker(5, 30_000);

  constructor(private readonly cfg: OverlayConfig) {
    this.ttl = cfg.ttlMs ?? 30_000;
  }

  /** A timeout signal, combined with an optional external abort (turn-stop). */
  private deadline(ms: number, external?: AbortSignal): AbortSignal {
    const t = AbortSignal.timeout(ms);
    return external ? AbortSignal.any([external, t]) : t;
  }

  /** A tool name is overlay-owned iff it carries a u_/b_ prefix (never a System tool). */
  isOverlayName(name: string): boolean {
    return this.cfg.enabled && OVERLAY_NAME_RE.test(name);
  }

  private key(env: Envelope): string {
    return `${env.userId ?? ''}|${env.projectId ?? ''}`;
  }

  /**
   * Build the outbound headers for a federated server. CRITICAL tenancy/security
   * boundary: the internal envelope (X-Internal-Token/X-User-Id) is trusted platform
   * identity and MUST go ONLY to internal loreweave servers — NEVER to a third-party
   * external server (that would leak our internal service token). An external server
   * gets ONLY its own registered credential (bearer/oauth access token from the vault),
   * fetched fresh per call so a refreshed token is picked up immediately.
   */
  private async outboundHeaders(serverId: string, isExternal: boolean, authKind: string, env: Envelope): Promise<Record<string, string>> {
    const credential = isExternal && (authKind === 'bearer' || authKind === 'oauth2') ? await this.fetchCredential(serverId, env) : null;
    return chooseOutboundHeaders(isExternal, authKind, buildEnvelopeHeaders(this.cfg.internalToken, env), credential);
  }

  /** Fetch an external server's decrypted credential from agent-registry (internal-token). */
  private async fetchCredential(serverId: string, env: Envelope): Promise<string | null> {
    const url = new URL(`${this.cfg.agentRegistryInternalUrl}/internal/mcp-servers/${serverId}/credentials`);
    url.searchParams.set('user_id', env.userId!);
    if (env.projectId) url.searchParams.set('book_id', env.projectId);
    try {
      const res = await fetch(url, {
        headers: { 'X-Internal-Token': this.cfg.internalToken },
        signal: AbortSignal.timeout(this.fetchTimeoutMs),
      });
      if (!res.ok) return null;
      const body = (await res.json()) as { secret?: string };
      return body.secret ?? null;
    } catch (e) {
      this.log.warn(`credential fetch failed for ${serverId}: ${e}`);
      return null;
    }
  }

  /** Resolve the overlay for a turn's envelope (cached). Fail-open → EMPTY/stale. */
  async resolve(env: Envelope): Promise<{ tools: any[]; route: Map<string, RouteEntry> }> {
    if (!this.cfg.enabled || !env.userId) return EMPTY;
    const key = this.key(env);
    const now = Date.now();
    const cached = this.cache.get(key);

    // /review-impl FIX-B: TTL hit → serve from cache WITHOUT any upstream call.
    // This keeps the hot path (every tools/list) off agent-registry; enable/disable
    // staleness is bounded by the TTL (Q-CACHE: 30s). Fetching on every turn defeated
    // the cache's load-reduction purpose and added an unbounded dependency.
    if (cached && cached.exp > now) {
      return { tools: cached.tools, route: cached.route };
    }

    // Cache miss/expired → refresh from agent-registry (timeout-bounded, fail-open).
    let servers: EffectiveServer[];
    let version: number;
    try {
      const resolved = await this.fetchEffective(env);
      servers = resolved.servers;
      version = resolved.version;
    } catch (e) {
      // Fail-open: serve the last-known catalog (even if stale) rather than drop the
      // user's tools mid-session; a fresh user with no cache gets the System catalog.
      this.log.warn(`overlay resolve failed (fail-open): ${e}`);
      return cached ? { tools: cached.tools, route: cached.route } : EMPTY;
    }

    // Zero registrations → the static fast path (empty overlay, cached for the TTL).
    if (servers.length === 0) {
      this.cache.set(key, { version, tools: [], route: new Map(), exp: now + this.ttl });
      return EMPTY;
    }
    // Version unchanged → skip the (expensive) per-server re-federation, extend the TTL.
    if (cached && cached.version === version) {
      cached.exp = now + this.ttl;
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
        route.set(prefixed, {
          endpointUrl: s.endpoint_url,
          originalName: t.name,
          serverId: s.mcp_server_id,
          egressAllowlist: Array.isArray(s.egress_allowlist) ? s.egress_allowlist : [],
          allowInternal: !s.is_external, // internal loreweave servers skip the SSRF block
          authKind: s.auth_kind ?? 'none',
        });
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
    // REG-P3-04: breaker — a server that has failed repeatedly fails fast (surfaced as
    // a tool error) rather than stalling the turn while it flaps.
    if (!this.breaker.canRequest(entry.serverId)) {
      throw new Error(`overlay server temporarily unavailable (circuit open after repeated failures)`);
    }
    const headers = await this.outboundHeaders(entry.serverId, !entry.allowInternal, entry.authKind, env);
    const deadline = this.deadline(this.callTimeoutMs, signal);
    const egressFetch = makeEgressFetch({
      allowlist: entry.egressAllowlist,
      allowInternal: entry.allowInternal,
      maxBytes: EGRESS_MAX_BYTES,
    });
    const client = new Client({ name: 'ai-gateway-overlay', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(entry.endpointUrl), {
      requestInit: { headers, signal: deadline },
      fetch: egressFetch as any,
    });
    try {
      await client.connect(transport);
      const res = await client.callTool({ name: entry.originalName, arguments: args }, undefined, { signal: deadline });
      this.breaker.onSuccess(entry.serverId);
      return res;
    } catch (e) {
      this.breaker.onFailure(entry.serverId);
      throw e;
    } finally {
      await client.close().catch(() => undefined);
    }
  }

  private async fetchEffective(env: Envelope): Promise<{ servers: EffectiveServer[]; version: number }> {
    const url = new URL(`${this.cfg.agentRegistryInternalUrl}/internal/effective-mcp-servers`);
    url.searchParams.set('user_id', env.userId!);
    if (env.projectId) url.searchParams.set('book_id', env.projectId);
    const res = await fetch(url, {
      headers: { 'X-Internal-Token': this.cfg.internalToken },
      signal: AbortSignal.timeout(this.fetchTimeoutMs),
    });
    if (!res.ok) throw new Error(`effective-mcp-servers ${res.status}`);
    const body = (await res.json()) as { servers?: EffectiveServer[]; catalog_version?: number };
    return { servers: Array.isArray(body.servers) ? body.servers : [], version: body.catalog_version ?? 0 };
  }

  private async listServerTools(s: EffectiveServer, env: Envelope): Promise<any[]> {
    const headers = await this.outboundHeaders(s.mcp_server_id, !!s.is_external, s.auth_kind ?? 'none', env);
    // Federation-time egress is guarded too: listing a user server's tools re-applies
    // the SSRF + allowlist policy so a rebind can't reach the internal network here either.
    const egressFetch = makeEgressFetch({
      allowlist: Array.isArray(s.egress_allowlist) ? s.egress_allowlist : [],
      allowInternal: !s.is_external,
      maxBytes: EGRESS_MAX_BYTES,
    });
    const client = new Client({ name: 'ai-gateway-overlay', version: '0.1.0' });
    const transport = new StreamableHTTPClientTransport(new URL(s.endpoint_url), {
      requestInit: { headers, signal: AbortSignal.timeout(this.callTimeoutMs) },
      fetch: egressFetch as any,
    });
    try {
      await client.connect(transport);
      const res: any = await client.listTools();
      return res?.tools ?? [];
    } finally {
      await client.close().catch(() => undefined);
    }
  }
}
