import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { FederationService } from '../federation/federation.service.js';
import { handleCallTool, handleListTools } from './handlers.js';

/**
 * A fresh low-level MCP proxy Server (stateless — one per HTTP request). It
 * advertises the federated catalog and forwards each CallTool to the owning
 * provider with the per-call envelope read from `extra.requestInfo.headers`.
 */
export function buildProxyServer(federation: FederationService): Server {
  const server = new Server(
    { name: 'ai-gateway', version: '0.1.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => handleListTools(federation));

  server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
    const headers = extra.requestInfo?.headers as
      | Record<string, string | string[] | undefined>
      | undefined;
    return handleCallTool(
      federation,
      request.params.name,
      (request.params.arguments ?? {}) as Record<string, unknown>,
      headers,
    );
  });

  return server;
}
