import { Logger } from '@nestjs/common';
import type { Envelope } from '../federation/federation.service.js';
import type { AdminFederationService } from '../federation/admin-federation.service.js';
import { headerValue } from './handlers.js';
import {
  GLOSSARY_CONFIRM_ACTION_TOOL, handleGlossaryConfirmAction,
} from './confirm-tools.js';

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
    projectId: headerValue(headers, 'x-project-id'),
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
  // V7 (2026-09-03) — the admin surface's ONLY System-write confirm vehicle, served here as a
  // consumer-local DIRECTIVE tool. It used to be appended by chat-service from its own local def
  // (stream_service.py:10745, :13946), which was the last production use of frontend_tools.py.
  //
  // ONLY this one, deliberately: `confirm_action` and `glossary_propose_entity_edit` are not part
  // of any admin flow, and widening a System-tier surface past what it needs is the opposite of
  // least-privilege. `/mcp/admin` is a SEPARATE federation from `/mcp`, so nothing arrives here
  // by default.
  return { tools: [...(catalog.toolList as any[]), GLOSSARY_CONFIRM_ACTION_TOOL] };
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
  // Consumer-local, dispatched HERE — it has no admin upstream, so the provider lookup below
  // would (correctly) refuse it as an unknown admin tool. Handled before that check for the same
  // reason the main surface handles its consumer-local tools before routing.
  if (name === GLOSSARY_CONFIRM_ACTION_TOOL.name) {
    return handleGlossaryConfirmAction(args);
  }
  try {
    // Re-list with the caller's token so dispatch authority is re-proven and the
    // tool name is confirmed to be an admin tool (no cross-surface smuggling). The
    // resolved provider (which upstream owns the tool) is passed to executeTool so
    // routing is race-free across multiple admin upstreams (glossary + knowledge).
    const catalog = await admin.catalogFor(env);
    const provider = admin.providerFor(name, catalog);
    if (!provider) {
      return {
        isError: true,
        content: [{ type: 'text', text: `unknown admin tool '${name}'` }],
      };
    }
    return await admin.executeTool(provider, name, args, env, meta);
  } catch (e) {
    log.warn(`admin tool '${name}' execution failed: ${e}`);
    return {
      isError: true,
      content: [{ type: 'text', text: `admin tool '${name}' failed: ${String(e)}` }],
    };
  }
}
