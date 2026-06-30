import { HttpException, Logger } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

/**
 * Thin downstream HTTP client for the owning services. The KAL is the ONLY sanctioned
 * caller of glossary/knowledge `/internal/*` knowledge routes (INV-KAL); everything else
 * goes through the KAL's typed contract. Uses Node's global fetch (Node 18+).
 *
 * Auth: presents X-Internal-Token (+ X-User-Id when a caller identity is forwarded). The
 * token is held in config and never surfaced to KAL callers.
 */
const log = new Logger('kal-downstream');

export interface DownstreamCtx {
  /** the authenticated caller's user id, forwarded as X-User-Id for tenancy. */
  userId?: string;
}

async function call(base: string, path: string, init: RequestInit, ctx: DownstreamCtx): Promise<unknown> {
  const cfg = loadConfig();
  const headers: Record<string, string> = {
    'X-Internal-Token': cfg.internalToken,
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  if (ctx.userId) headers['X-User-Id'] = ctx.userId;
  const url = `${base}${path}`;
  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (e) {
    log.error(`downstream ${url} unreachable: ${(e as Error).message}`);
    throw new HttpException('knowledge backend unreachable', 502);
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new HttpException(`downstream ${res.status}: ${body.slice(0, 200)}`, res.status === 404 ? 404 : 502);
  }
  return res.status === 204 ? null : res.json();
}

export const glossary = {
  get: (path: string, ctx: DownstreamCtx) => call(loadConfig().glossaryUrl, path, { method: 'GET' }, ctx),
  post: (path: string, body: unknown, ctx: DownstreamCtx) =>
    call(loadConfig().glossaryUrl, path, { method: 'POST', body: JSON.stringify(body) }, ctx),
};

export const knowledge = {
  get: (path: string, ctx: DownstreamCtx) => call(loadConfig().knowledgeUrl, path, { method: 'GET' }, ctx),
  post: (path: string, body: unknown, ctx: DownstreamCtx) =>
    call(loadConfig().knowledgeUrl, path, { method: 'POST', body: JSON.stringify(body) }, ctx),
};

/** Extract the caller identity from the standard internal headers. */
export function ctxFromHeaders(headers: Record<string, string | undefined>): DownstreamCtx {
  return { userId: headers['x-user-id'] };
}
