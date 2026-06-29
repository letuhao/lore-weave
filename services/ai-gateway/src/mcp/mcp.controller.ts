import { All, Controller, Logger, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { FederationService } from '../federation/federation.service.js';
import { buildProxyServer } from './proxy-server.factory.js';
import { loadConfig } from '../config/config.js';
import { constantTimeEquals } from '../util/auth.js';

/**
 * The single upstream MCP face. Consumers (chat, composition) connect here as
 * MCP clients. Stateless: a fresh proxy Server + transport per HTTP request
 * (one request == one call), so concurrent consumers never share state and the
 * per-call envelope maps cleanly (the proven H3 pattern, server side).
 */
@Controller('mcp')
export class McpController {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(McpController.name);

  constructor(private readonly federation: FederationService) {}

  @All()
  async handle(@Req() req: Request, @Res() res: Response): Promise<void> {
    // SO-1: service-auth gate on EVERY /mcp request (initialize / list / call).
    const token = req.header('x-internal-token');
    if (!this.cfg.internalToken || !constantTimeEquals(token ?? '', this.cfg.internalToken)) {
      res.status(401).json({
        jsonrpc: '2.0',
        error: { code: -32001, message: 'invalid internal token' },
        id: null,
      });
      return;
    }

    const server = buildProxyServer(this.federation);
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined, // stateless
      enableJsonResponse: true,
    });
    res.on('close', () => {
      Promise.resolve(transport.close()).catch(() => undefined);
      Promise.resolve(server.close()).catch(() => undefined);
    });
    // AIGW-LOW1: a throw out of the transport must not become an unhandled
    // rejection / hung socket — return a clean JSON-RPC error if nothing was sent.
    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (e) {
      this.log.warn(`MCP request handling failed: ${e}`);
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
