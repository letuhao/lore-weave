import { Logger } from '@nestjs/common';
import type { Envelope, FederationService } from '../federation/federation.service.js';

const log = new Logger('McpProxy');

type Headers = Record<string, string | string[] | undefined> | undefined;

export function headerValue(headers: Headers, key: string): string | undefined {
  if (!headers) return undefined;
  const v = headers[key.toLowerCase()];
  return Array.isArray(v) ? v[0] : v;
}

/** Per-call identity, lifted off the request headers (SEC-1: never from the LLM). */
export function extractEnvelope(headers: Headers): Envelope {
  return {
    userId: headerValue(headers, 'x-user-id'),
    sessionId: headerValue(headers, 'x-session-id'),
    traceId: headerValue(headers, 'x-trace-id'),
  };
}

export function handleListTools(federation: FederationService): { tools: any[] } {
  return { tools: federation.catalog() as any[] };
}

/**
 * Route a CallTool to the owning provider with the per-call envelope. A provider
 * failure becomes an MCP tool error (`isError`), NOT a transport 5xx — so the
 * consumer's tool-loop reports "tool failed" to the LLM and carries on (the
 * house degradation contract).
 */
export async function handleCallTool(
  federation: FederationService,
  name: string,
  args: Record<string, unknown>,
  headers: Headers,
  meta?: unknown,
): Promise<any> {
  const env = extractEnvelope(headers);
  // A CallTool with no caller identity is almost always a bug. Per-tool identity
  // enforcement stays on the PROVIDER (SEC-2 — and some tools, e.g.
  // glossary_list_system_standards, are legitimately global), so the gateway forwards
  // regardless but logs the anomaly for observability rather than failing blind.
  if (!env.userId) {
    log.warn(`tool '${name}' called with no X-User-Id envelope`);
  }
  try {
    // Forward the MCP `_meta` channel downstream (the proven TS→Go alternate to
    // headers, §20) so a provider that reads req.Params.Meta still receives it.
    return await federation.executeTool(name, args, env, meta);
  } catch (e) {
    log.warn(`tool '${name}' execution failed: ${e}`);
    return {
      isError: true,
      content: [{ type: 'text', text: `tool '${name}' failed: ${String(e)}` }],
    };
  }
}
