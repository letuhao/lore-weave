import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  GetPromptRequestSchema,
  ListPromptsRequestSchema,
  ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { FederationService } from '../federation/federation.service.js';
import {
  handleCallTool,
  handleGetPrompt,
  handleListPrompts,
  handleListResources,
  handleListResourceTemplates,
  handleListTools,
  handleReadResource,
} from './handlers.js';

/**
 * A fresh low-level MCP proxy Server (stateless — one per HTTP request). It
 * advertises the federated catalog and forwards each CallTool to the owning
 * provider with the per-call envelope read from `extra.requestInfo.headers`.
 * Wave C5: resources (list/templates/read) and prompts (list/get) are
 * federated the same way, so the capabilities block advertises all three.
 */
export function buildProxyServer(federation: FederationService): Server {
  const server = new Server(
    { name: 'ai-gateway', version: '0.1.0' },
    { capabilities: { tools: {}, resources: {}, prompts: {} } },
  );

  type ExtraHeaders = Record<string, string | string[] | undefined> | undefined;
  const headersOf = (extra: { requestInfo?: { headers?: unknown } }): ExtraHeaders =>
    extra.requestInfo?.headers as ExtraHeaders;

  server.setRequestHandler(ListToolsRequestSchema, async () => handleListTools(federation));

  server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
    const headers = headersOf(extra);
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

  // ── Wave C5 — resources + prompts, federated exactly like tools ──────
  server.setRequestHandler(ListResourcesRequestSchema, async () =>
    handleListResources(federation),
  );
  server.setRequestHandler(ListResourceTemplatesRequestSchema, async () =>
    handleListResourceTemplates(federation),
  );
  server.setRequestHandler(ReadResourceRequestSchema, async (request, extra) =>
    handleReadResource(federation, request.params.uri, headersOf(extra), extra.signal),
  );
  server.setRequestHandler(ListPromptsRequestSchema, async () => handleListPrompts(federation));
  server.setRequestHandler(GetPromptRequestSchema, async (request, extra) =>
    handleGetPrompt(
      federation,
      request.params.name,
      (request.params.arguments ?? {}) as Record<string, unknown>,
      headersOf(extra),
      extra.signal,
    ),
  );

  return server;
}
