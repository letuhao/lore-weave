import { Controller, Logger, Post, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { FederationService } from '../federation/federation.service.js';
import { extractEnvelope } from '../mcp/handlers.js';
import { loadConfig } from '../config/config.js';

/**
 * FE→MCP-tool bridge (server side). Invokes a SINGLE federated tool over plain
 * HTTP instead of opening an MCP session — the ergonomic path the api-gateway-bff
 * uses to let the FE drive a Tier-W *propose* (mint a confirm token) or poll a job
 * WITHOUT a chat agent in the loop.
 *
 * SO-1 gated (internal-token), exactly like `/mcp` and `/internal/context`: the
 * SAME trust level — an internal-token holder can already invoke any federated tool
 * via `/mcp`; this is just dict-in / dict-out. The per-call identity (`X-User-Id`)
 * is lifted off the headers (SEC-1 — never from a body field a client controls);
 * the BFF sets it from the validated JWT. The FE-facing tool ALLOWLIST lives in the
 * BFF (closest to the FE surface), not here — this endpoint is a generic internal
 * primitive.
 */
@Controller('internal/tools')
export class ToolsController {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(ToolsController.name);

  constructor(private readonly federation: FederationService) {}

  @Post('execute')
  async execute(@Req() req: Request, @Res() res: Response): Promise<void> {
    // SO-1: the same service-auth gate as /mcp.
    const token = req.header('x-internal-token');
    if (!this.cfg.internalToken || token !== this.cfg.internalToken) {
      res.status(401).json({ error: 'invalid internal token' });
      return;
    }

    const body = (req.body ?? {}) as { tool?: unknown; args?: unknown; meta?: unknown };
    const tool = typeof body.tool === 'string' ? body.tool : '';
    if (!tool) {
      res.status(400).json({ error: 'missing tool' });
      return;
    }
    const args = (body.args && typeof body.args === 'object' ? body.args : {}) as Record<
      string,
      unknown
    >;

    // Unknown tool → 404 (a clean status the FE can branch on, distinct from a
    // provider failure). federation.executeTool would also throw, but a 404 reads
    // truthfully as "no such tool" rather than "tool execution failed".
    if (!this.federation.providerFor(tool)) {
      res.status(404).json({ error: `unknown tool '${tool}'` });
      return;
    }

    const env = extractEnvelope(req.headers as Record<string, string | string[] | undefined>);
    let result: unknown;
    try {
      result = await this.federation.executeTool(tool, args, env, body.meta);
    } catch (e) {
      // Detail stays server-side — String(e) can carry the internal provider URL.
      this.log.warn(`tool '${tool}' execute failed: ${e}`);
      res.status(502).json({ error: 'tool execution failed' });
      return;
    }

    const r = result as {
      isError?: boolean;
      structuredContent?: unknown;
      content?: Array<{ type?: string; text?: string }>;
    };
    const textOf = (): string | undefined => r.content?.find((c) => c?.type === 'text')?.text;

    if (r.isError) {
      // The call reached the tool and it refused (gate denial, bad args, billing) —
      // surface the text so the FE can render it; 400 (a client-correctable error).
      res.status(400).json({ error: textOf() ?? 'tool error' });
      return;
    }

    // FastMCP returns a dict tool result as BOTH `structuredContent` AND a JSON text
    // block. Prefer the structured form; fall back to parsing the text block; last
    // resort, hand back the raw result.
    if (r.structuredContent !== undefined) {
      res.status(200).json({ result: r.structuredContent });
      return;
    }
    const text = textOf();
    if (text !== undefined) {
      try {
        res.status(200).json({ result: JSON.parse(text) });
      } catch {
        res.status(200).json({ result: text });
      }
      return;
    }
    res.status(200).json({ result: r });
  }
}
