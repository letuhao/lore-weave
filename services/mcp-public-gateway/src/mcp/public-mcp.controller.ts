import { All, Controller, Logger, Req, Res } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { Request, Response } from 'express';
import { loadConfig } from '../config/config.js';
import { KeyResolver } from '../auth/key-resolver.js';
import { filterListResponseText, gateRequestBody, isListRequest } from '../scope/scope-filter.js';

/**
 * The PUBLIC MCP edge. An external agent connects here (via api-gateway-bff `/mcp`)
 * with its OWN credential in the Authorization header. The edge:
 *   1. rejects a credential supplied in the query string (H-R — would land in logs)
 *   2. authenticates the credential → a LoreWeave user (PUB-1: identity derived here,
 *      never trusted from the agent)
 *   3. STRIPS the entire inbound `x-*` namespace and mints a FRESH envelope
 *      (PUB-9 — an agent that sends X-Admin-Token / X-Internal-Token / X-User-Id
 *      must have it discarded, never forwarded)
 *   4. relays to `${aiGatewayUrl}/mcp` ONLY — there is NO route to `/mcp/admin`,
 *      and the edge holds no admin token (PUB-9 / H-A)
 *
 * MCP semantics are preserved end-to-end: the relay is transport-transparent, so
 * the external client effectively speaks to ai-gateway's spec-compliant MCP server
 * through it (H-M). ai-gateway runs stateless JSON-RPC, so a request/response relay
 * is faithful for v1.
 *
 * P0 scope: envelope hop + strip + admin isolation, read tools only. Scope filter
 * (P2), rate-limit + spend gate (P3), and write-approval (P4) layer on top.
 */
@Controller('mcp')
export class PublicMcpController {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(PublicMcpController.name);
  private readonly resolver = new KeyResolver();

  @All()
  async handle(@Req() req: Request, @Res() res: Response): Promise<void> {
    // H-R: a key in the query string would be logged by every proxy/CDN. Refuse it.
    if (typeof req.query?.key === 'string' || typeof req.query?.token === 'string') {
      return this.deny(res, -32001, 'credential must be sent in the Authorization header, not the URL');
    }

    const bearer = parseBearer(req.header('authorization'));
    const resolved = await this.resolver.resolve(bearer);
    if (!resolved) {
      // Uniform 401 — no oracle about which check failed (flag off / bad key / no store).
      return this.deny(res, -32001, 'unauthorized');
    }

    if (!this.cfg.internalToken) {
      this.log.error('FATAL: INTERNAL_SERVICE_TOKEN missing — cannot mint envelope');
      return this.deny(res, -32603, 'gateway misconfigured', 500);
    }

    // PUB-9: build the outbound header set FROM SCRATCH. We copy NOTHING from the
    // inbound x-* namespace (in particular X-Admin-Token / X-Internal-Token /
    // X-User-Id can never be smuggled through). Only transport-relevant non-x-*
    // headers (Accept, Content-Type, MCP-Protocol-Version) are carried.
    const traceId = randomUUID(); // mint our own; never trust an inbound x-trace-id
    const outboundHeaders: Record<string, string> = {
      'x-internal-token': this.cfg.internalToken,
      'x-user-id': resolved.userId,
      'x-mcp-key-id': resolved.keyId,
      'x-trace-id': traceId,
      accept: req.header('accept') ?? 'application/json, text/event-stream',
      'content-type': req.header('content-type') ?? 'application/json',
    };
    const mcpVersion = req.header('mcp-protocol-version');
    if (mcpVersion) outboundHeaders['mcp-protocol-version'] = mcpVersion;

    // PUB-3 / H-E: scope gate the REQUEST. A `tools/call` to a tool outside the key's
    // tier∩domain scope (or an unknown tool) is denied HERE, before the relay —
    // default-deny / fail-closed. A `*` (dev) key bypasses inside the helper.
    const hasBody = req.method !== 'GET' && req.method !== 'HEAD' && req.body !== undefined;
    if (hasBody) {
      const denial = gateRequestBody(req.body, resolved.scopes);
      if (denial !== null) {
        res.status(200).json(denial); // JSON-RPC errors travel as a 200 envelope
        return;
      }
    }

    // Relay to the USER surface only — never `/mcp/admin` (PUB-9 / H-A).
    const target = `${this.cfg.aiGatewayUrl}/mcp`;
    try {
      const upstream = await fetch(target, {
        method: req.method,
        headers: outboundHeaders,
        body: hasBody ? JSON.stringify(req.body) : undefined,
      });
      let text = await upstream.text();
      // PUB-3 / H-F: filter the `tools/list` RESPONSE so the agent only ever sees the
      // tools its key may call. Only rewrite a successful list; errors pass through.
      const ok = upstream.status >= 200 && upstream.status < 300;
      const rewroteList = ok && hasBody && isListRequest(req.body);
      if (rewroteList) {
        text = filterListResponseText(text, resolved.scopes, this.log);
      }
      res.status(upstream.status);
      // We emit JSON when we rewrote the list; otherwise echo the upstream type.
      const ct = rewroteList ? 'application/json' : upstream.headers.get('content-type');
      if (ct) res.setHeader('content-type', ct);
      res.send(text);
    } catch (e) {
      this.log.warn(`relay to ai-gateway failed: ${e}`);
      return this.deny(res, -32603, 'upstream gateway unavailable', 502);
    }
  }

  private deny(res: Response, code: number, message: string, status = 401): void {
    res.status(status).json({ jsonrpc: '2.0', error: { code, message }, id: null });
  }
}

/** Extract the bearer token from an `Authorization: Bearer <token>` header. */
export function parseBearer(header: string | undefined): string | undefined {
  if (!header) return undefined;
  const m = /^Bearer\s+(.+)$/i.exec(header.trim());
  return m ? m[1].trim() : undefined;
}
