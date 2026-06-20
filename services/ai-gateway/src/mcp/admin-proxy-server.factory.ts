import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { AdminFederationService } from '../federation/admin-federation.service.js';
import { handleAdminCallTool, handleAdminListTools } from './admin-handlers.js';

/**
 * A fresh low-level MCP proxy Server for the gateway's `/mcp/admin` surface
 * (stateless — one per HTTP request). It advertises ONLY the admin catalog
 * (federated from glossary `/mcp/admin`) and forwards each CallTool with the
 * per-call admin envelope read from `extra.requestInfo.headers`. Entirely
 * separate from the user/book proxy (INV-T6).
 */
export function buildAdminProxyServer(admin: AdminFederationService): Server {
  const server = new Server(
    { name: 'ai-gateway-admin', version: '0.1.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async (_req, extra) => {
    const headers = extra.requestInfo?.headers as
      | Record<string, string | string[] | undefined>
      | undefined;
    return handleAdminListTools(admin, headers);
  });

  server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
    const headers = extra.requestInfo?.headers as
      | Record<string, string | string[] | undefined>
      | undefined;
    return handleAdminCallTool(
      admin,
      request.params.name,
      (request.params.arguments ?? {}) as Record<string, unknown>,
      headers,
      request.params._meta,
    );
  });

  return server;
}
