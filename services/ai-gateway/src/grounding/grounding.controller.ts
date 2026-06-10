import { Controller, Post, Req, Res } from '@nestjs/common';
import type { Request, Response } from 'express';
import { loadConfig } from '../config/config.js';

/**
 * P6 grounding port — the gateway's grounding face. Chat posts here to build the
 * per-turn memory/glossary context; the gateway forwards to knowledge-service.
 * This makes ai-gateway the single AI integration layer (tools + grounding).
 *
 * It is a PURE pass-through: no LLM inference, no token metering (SO-6 — grounding
 * is retrieval). On a knowledge outage it returns 502 so the consumer treats it
 * as a gateway-grounding failure and falls back to calling knowledge directly
 * (H2 — a gateway outage degrades context, never breaks the turn).
 */
// Backstop timeout for the gateway→knowledge grounding call (the consumer's own
// timeout is tighter and is the real latency control; this only prevents leaks).
const GROUNDING_UPSTREAM_TIMEOUT_MS = 10_000;

@Controller('internal/context')
export class GroundingController {
  private readonly cfg = loadConfig();

  @Post('build')
  async build(@Req() req: Request, @Res() res: Response): Promise<void> {
    // SO-1: the same service-auth gate as /mcp.
    const token = req.header('x-internal-token');
    if (!this.cfg.internalToken || token !== this.cfg.internalToken) {
      res.status(401).json({ error: 'invalid internal token' });
      return;
    }

    const target = `${this.cfg.groundingUrl}/internal/context/build`;
    const headers: Record<string, string> = {
      'content-type': 'application/json',
      // The gateway presents ITS OWN internal token to knowledge (SO-1).
      'x-internal-token': this.cfg.internalToken,
    };
    // Forward identity + trace so knowledge stitches logs to the originating turn.
    const userId = req.header('x-user-id');
    if (userId) headers['x-user-id'] = userId;
    const traceId = req.header('x-trace-id');
    if (traceId) headers['x-trace-id'] = traceId;

    let upstream: globalThis.Response;
    try {
      upstream = await fetch(target, {
        method: 'POST',
        headers,
        body: JSON.stringify(req.body ?? {}),
        // Backstop so a hung knowledge doesn't leak a pending request — the
        // consumer's own (tighter) grounding timeout is the real latency control.
        signal: AbortSignal.timeout(GROUNDING_UPSTREAM_TIMEOUT_MS),
      });
    } catch {
      // Knowledge unreachable → 502; the consumer falls back to knowledge-direct.
      res.status(502).json({ error: 'grounding upstream unavailable' });
      return;
    }

    // Pass the upstream status + body straight through (a 404 project-not-found,
    // a 501 Mode-3, a 200 context — all relayed verbatim; the consumer decides).
    const body = await upstream.text();
    res.status(upstream.status);
    const ct = upstream.headers.get('content-type');
    if (ct) res.setHeader('content-type', ct);
    res.send(body);
  }
}
