// FE→MCP-tool bridge client (D-W10-ARC-CONFORMANCE-DEEP-FE). Invokes a SINGLE
// whitelisted federated MCP tool through the BFF — the FE's path to a Tier-W
// *propose* (mint a cost-gated confirm token) or a job poll WITHOUT a chat agent in
// the loop. The BFF validates the JWT (→ X-User-Id, server-derived, SEC-1), enforces
// the FE-tool allowlist, and forwards to ai-gateway's /internal/tools/execute.
// See services/api-gateway-bff/src/tools/tools.controller.ts.
import { apiJson } from './api';

/**
 * Call a federated MCP tool by name. `args` is the tool's argument object (the same
 * shape the chat agent would pass). Returns the tool's unwrapped JSON result. Throws
 * (via apiJson) on a 4xx/5xx — a 403 means the tool isn't on the FE allowlist, a 400
 * carries the tool's own refusal reason (e.g. an EDIT-grant denial).
 */
export async function mcpExecute<T = unknown>(
  tool: string,
  args: Record<string, unknown>,
  token: string,
): Promise<T> {
  const { result } = await apiJson<{ result: T }>('/v1/ai/tools/execute', {
    method: 'POST',
    body: JSON.stringify({ tool, args }),
    token,
  });
  return result;
}
