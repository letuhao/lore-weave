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
      request.params._meta,
      // D-PLANNER-INFLIGHT-ABORT (#19): the SDK aborts `extra.signal` when this
      // request's transport closes (the controller closes it on the client's
      // `res 'close'`). Thread it to the downstream tool call so a chat-turn
      // stop cancels an in-flight heavy tool (e.g. the ~39s glossary_plan) all
      // the way to the provider — the rest of the chain already honours ctx.
      extra.signal,
    );
  });

  return server;
}
