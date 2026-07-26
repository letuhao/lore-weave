import { All, Controller, Logger, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { AdminFederationService } from '../federation/admin-federation.service.js';
import { buildAdminProxyServer } from './admin-proxy-server.factory.js';
import { loadConfig } from '../config/config.js';
import { constantTimeEquals } from '../util/auth.js';

/**
 * The gateway's admin MCP face (`/mcp/admin`) — a SEPARATE downstream surface from
 * `/mcp` (INV-T6, spec §4c/§6.2). The CMS admin surface connects here; book/reader
 * chats connect to `/mcp` and never hold an admin token, so they can neither see
 * nor reach admin tools.
 *
 * Two transport gates before any MCP processing:
 *  1. SO-1 — the internal service token (same as `/mcp`).
 *  2. Presence of an `X-Admin-Token` — the gateway only dials glossary `/mcp/admin`
 *     when it has an admin token to present (INV-T6 barrier 1). The AUTHORITATIVE
 *     RS256 `admin:write` verification happens at glossary's transport (INV-T2);
 *     the gateway forwards the token and relays glossary's 401 on an invalid one
 *     (so a non-admin cannot enumerate admin tools). The gateway never derives
 *     admin authority from `X-User-Id`.
 *
 * Stateless: a fresh admin proxy Server + transport per request. The admin token
 * is NEVER logged (spec §6.7).
 */
@Controller('mcp/admin')
export class AdminMcpController {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(AdminMcpController.name);

  constructor(private readonly admin: AdminFederationService) {}

  @All()
  async handle(@Req() req: Request, @Res() res: Response): Promise<void> {
    // SO-1: service-auth gate on EVERY /mcp/admin request.
    const token = req.header('x-internal-token');
    if (!this.cfg.internalToken || !constantTimeEquals(token ?? '', this.cfg.internalToken)) {
      res.status(401).json({
        jsonrpc: '2.0',
        error: { code: -32001, message: 'invalid internal token' },
        id: null,
      });
      return;
    }

    // INV-T6 barrier 1: without an admin token to present, the gateway does not
    // open the admin surface at all — so a non-admin caller cannot list or call
    // admin tools (no enumeration). 401 passthrough, no admin-tool leak.
    const adminToken = req.header('x-admin-token');
    if (!adminToken) {
      res.status(401).json({
        jsonrpc: '2.0',
        error: { code: -32001, message: 'admin token required' },
        id: null,
      });
      return;
    }

    try {
      const server = buildAdminProxyServer(this.admin);
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined, // stateless
        enableJsonResponse: true,
      });
      res.on('close', () => {
        Promise.resolve(transport.close()).catch(() => undefined);
        Promise.resolve(server.close()).catch(() => undefined);
      });
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (e) {
      // Never include the token in the error log.
      this.log.warn(`admin MCP request handling failed: ${e}`);
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: '2.0',
          error: { code: -32603, message: 'internal gateway error' },
          id: null,
        });
      }
    }
  }
}
