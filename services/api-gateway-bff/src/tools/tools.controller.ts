// FE→MCP-tool bridge (D-W10-ARC-CONFORMANCE-DEEP-FE). Lets the FE drive a Tier-W
// *propose* (mint a cost-gated confirm token) or poll a motif job by invoking a
// single federated MCP tool WITHOUT a chat agent in the loop — the deep
// arc-conformance model-picker needs this, and it is reusable for every FE Tier-W op.
//
// Trust model:
//   - The FE presents its normal user JWT (Bearer). We validate it here and derive
//     X-User-Id from `sub` (SEC-1 — identity is NEVER taken from a client body field).
//   - Only an ALLOWLIST of safe propose/poll tools is reachable; destructive/confirm/
//     admin tools are NOT (confirm stays a separate signed-token write on the domain).
//   - We forward to ai-gateway's SO-1-gated /internal/tools/execute with the shared
//     INTERNAL_SERVICE_TOKEN — the same internal trust an MCP client already holds.

import { Body, Controller, Headers, HttpException, Logger, Post } from '@nestjs/common';
import * as jwt from 'jsonwebtoken';

/**
 * Tools the FE may invoke through the bridge. Propose tools MINT a confirm token
 * (the spend is gated by the subsequent human confirm); the poll tool is a pure
 * read. NOTHING here writes or deletes — `composition_*` confirm/bind/unbind and any
 * `*_admin_*` tool are deliberately excluded.
 */
export const FE_BRIDGE_TOOL_ALLOWLIST: ReadonlySet<string> = new Set([
  'composition_conformance_run', // PROPOSE — deep arc-conformance job (the feature)
  'composition_motif_mine', // PROPOSE — mine motifs from a book/corpus
  'composition_motif_adopt', // PROPOSE — clone a motif into the user/book library
  'composition_arc_import_analyze', // PROPOSE — deconstruct a reference into an arc
  'composition_get_mine_job', // POLL — read a motif/conformance job to terminal
]);

interface ExecuteBody {
  tool?: string;
  args?: Record<string, unknown>;
  meta?: unknown;
}

@Controller('v1/ai/tools')
export class ToolsController {
  private readonly logger = new Logger(ToolsController.name);

  @Post('execute')
  async execute(
    @Body() body: ExecuteBody,
    @Headers('authorization') authorization?: string,
  ): Promise<{ result: unknown }> {
    // 1. Authenticate the FE (Bearer JWT) → userId. Identity is server-derived.
    const token = (authorization ?? '').replace(/^Bearer\s+/i, '').trim();
    if (!token) {
      throw new HttpException('missing bearer token', 401);
    }
    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      this.logger.error('tool-execute rejected: JWT_SECRET not configured');
      throw new HttpException('server_error', 500);
    }
    let userId: string;
    try {
      const decoded = jwt.verify(token, jwtSecret) as { sub: string };
      userId = decoded.sub;
    } catch {
      throw new HttpException('invalid_token', 401);
    }

    // 2. Allowlist — the FE may reach only safe propose/poll tools.
    const tool = typeof body?.tool === 'string' ? body.tool : '';
    if (!tool) {
      throw new HttpException('missing tool', 400);
    }
    if (!FE_BRIDGE_TOOL_ALLOWLIST.has(tool)) {
      // Uniform 403 — do not reveal whether the tool exists (anti-enumeration).
      this.logger.warn(`tool-execute denied: '${tool}' not in FE allowlist (user ${userId})`);
      throw new HttpException('tool not permitted', 403);
    }

    const args = body?.args && typeof body.args === 'object' ? body.args : {};

    // 3. Forward to ai-gateway (SO-1). Identity + project scope ride the headers.
    const gatewayUrl = process.env.AI_GATEWAY_URL;
    const internalToken = process.env.INTERNAL_SERVICE_TOKEN;
    if (!gatewayUrl || !internalToken) {
      this.logger.error('tool-execute rejected: AI_GATEWAY_URL / INTERNAL_SERVICE_TOKEN not configured');
      throw new HttpException('server_error', 500);
    }
    const headers: Record<string, string> = {
      'content-type': 'application/json',
      'x-internal-token': internalToken,
      'x-user-id': userId,
    };
    // Project scope (X-Project-Id) lets project-scoped tools resolve "the current
    // project" downstream. Taken from args.project_id — non-identity, safe to relay.
    const projectId = typeof args.project_id === 'string' ? args.project_id : undefined;
    if (projectId) headers['x-project-id'] = projectId;

    let upstream: globalThis.Response;
    try {
      upstream = await fetch(`${gatewayUrl.replace(/\/$/, '')}/internal/tools/execute`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ tool, args, ...(body?.meta ? { meta: body.meta } : {}) }),
        signal: AbortSignal.timeout(TOOL_EXECUTE_TIMEOUT_MS),
      });
    } catch {
      throw new HttpException('ai_gateway_unavailable', 502);
    }

    const text = await upstream.text();
    let parsed: { result?: unknown; error?: string } = {};
    try {
      parsed = text ? JSON.parse(text) : {};
    } catch {
      parsed = {};
    }
    if (!upstream.ok) {
      // Relay the gateway's status + error message (a tool gate denial is a 400 with
      // a human-readable reason; 404 unknown tool; 502 transport). Default to the raw
      // status so the FE can branch.
      throw new HttpException(parsed.error ?? 'tool execution failed', upstream.status);
    }
    return { result: parsed.result };
  }
}

// A propose (LLM plan/estimate) can take a while on a slow local model; the deep
// arc-conformance propose only mints a token (fast), but keep a generous backstop.
const TOOL_EXECUTE_TIMEOUT_MS = 120_000;
