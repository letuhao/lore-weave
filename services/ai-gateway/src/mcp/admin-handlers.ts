import { Logger } from '@nestjs/common';
import type { Envelope } from '../federation/federation.service.js';
import type { AdminFederationService } from '../federation/admin-federation.service.js';
import { headerValue } from './handlers.js';

const log = new Logger('McpAdminProxy');

type Headers = Record<string, string | string[] | undefined> | undefined;

/**
 * Per-call admin envelope, lifted off the request headers (SEC-1: never from the
 * LLM). Adds `adminToken` (X-Admin-Token) on top of the user envelope. NOTE: the
 * admin token is a bearer credential — it lives only in the returned envelope and
 * is NEVER logged (spec §6.7, §11 #7).
 */
export function extractAdminEnvelope(headers: Headers): Envelope {
  return {
    userId: headerValue(headers, 'x-user-id'),
    sessionId: headerValue(headers, 'x-session-id'),
    traceId: headerValue(headers, 'x-trace-id'),
    adminToken: headerValue(headers, 'x-admin-token'),
  };
}

/**
 * List the admin catalog for this caller. Requires the admin token (the upstream
 * transport gate verifies it before listing). On any failure — including a 401
 * from an absent/invalid admin token — we throw so the controller surfaces it and
 * NOTHING is enumerated (INV-T6). We log only the failure shape, never the token.
 */
export async function handleAdminListTools(
  admin: AdminFederationService,
  headers: Headers,
): Promise<{ tools: any[] }> {
  const env = extractAdminEnvelope(headers);
  const catalog = await admin.catalogFor(env);
  return { tools: catalog.toolList as any[] };
}

/**
 * Route an admin CallTool to the glossary admin upstream with the admin envelope.
 * The tool must be present in the caller's live admin catalog (validated here) so
 * a caller cannot smuggle a non-admin tool name through the admin surface. A
 * provider failure becomes an MCP tool error (isError), not a transport 5xx.
 */
export async function handleAdminCallTool(
  admin: AdminFederationService,
  name: string,
  args: Record<string, unknown>,
  headers: Headers,
  meta?: unknown,
): Promise<any> {
  const env = extractAdminEnvelope(headers);
  try {
    // Re-list with the caller's token so dispatch authority is re-proven and the
    // tool name is confirmed to be an admin tool (no cross-surface smuggling).
    const catalog = await admin.catalogFor(env);
    if (!admin.providerFor(name, catalog)) {
      return {
        isError: true,
        content: [{ type: 'text', text: `unknown admin tool '${name}'` }],
      };
    }
    return await admin.executeTool(name, args, env, meta);
  } catch (e) {
    log.warn(`admin tool '${name}' execution failed: ${e}`);
    return {
      isError: true,
      content: [{ type: 'text', text: `admin tool '${name}' failed: ${String(e)}` }],
    };
  }
}
