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
  /** abort signal derived from the inbound request — a client disconnect cancels the
   *  downstream call instead of orphaning it (no zombie KG/retrieve calls). */
  signal?: AbortSignal;
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
    res = await fetch(url, { ...init, headers, signal: ctx.signal });
  } catch (e) {
    // A client-disconnect abort is not a backend failure — surface 499 (client closed).
    if ((e as Error)?.name === 'AbortError') {
      throw new HttpException('client disconnected', 499);
    }
    log.error(`downstream ${url} unreachable: ${(e as Error).message}`);
    throw new HttpException('knowledge backend unreachable', 502);
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    // A 404 from a route that DOES NOT EXIST is not a 404 about the caller's resource, and
    // forwarding it as one is a lie the caller cannot see through (T55b). Measured on the live
    // stack: two of the KAL's fourteen routes federate to downstream paths nobody built, and
    // both answered with their framework's default page — indistinguishable, at the KAL's edge,
    // from "your book has no such entity".
    if (res.status === 404 && isUnroutedDownstream(body)) {
      log.error(`downstream ${url} has NO SUCH ROUTE — the KAL federates to a path that does not exist`);
      throw new HttpException(
        `this KAL route federates to ${path}, which the downstream service does not implement`,
        501,
      );
    }
    // Forward a downstream 4xx faithfully (bad request / unauthorized / not-found /
    // conflict are the caller's to see), map 5xx → 502 (the backend is broken, not the call).
    const status = res.status >= 400 && res.status < 500 ? res.status : 502;
    throw new HttpException(`downstream ${res.status}: ${body.slice(0, 200)}`, status);
  }
  if (res.status === 204) return null;
  // Guard the success-body parse: a 2xx with an empty or non-JSON body must NOT escape as an
  // unhandled 500 that masks the real downstream status. Read text once, parse defensively.
  const raw = await res.text();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    log.warn(`downstream ${url} returned 2xx with non-JSON body (${raw.length}b)`);
    return null;
  }
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

/**
 * Build a downstream ctx from the inbound request: the caller identity AND an abort signal
 * tied to the client connection. By the time a Nest handler runs the request body is already
 * parsed, so a later `close` on the request means the CLIENT disconnected — abort the
 * downstream fetch so a slow KG/retrieve call doesn't run on as a zombie. Best-effort: any
 * wiring failure degrades to "no signal" (the prior behavior), never throws.
 */
export function ctxFromReq(req: {
  headers?: Record<string, string | undefined>;
  kalUserId?: string;
  on?: (ev: string, cb: () => void) => void;
}): DownstreamCtx {
  // In user mode KalAuthGuard pins req.kalUserId from the validated JWT — prefer it over the
  // x-user-id header so a FE client cannot spoof the tenancy identity. In service mode kalUserId
  // is unset and the forwarded x-user-id header (set by a trusted caller) is used.
  const ctx: DownstreamCtx = { userId: req?.kalUserId ?? req?.headers?.['x-user-id'] };
  try {
    if (typeof req?.on === 'function') {
      const ac = new AbortController();
      req.on('close', () => ac.abort());
      ctx.signal = ac.signal;
    }
  } catch {
    /* best-effort — no signal */
  }
  return ctx;
}

/**
 * Did this 404 come from a router that has no such path, rather than from a handler saying the
 * resource is absent?
 *
 * The needles are each framework's DEFAULT 404 page, which a handler never produces:
 *
 *     Go (chi/mux)   `404 page not found`
 *     FastAPI        `{"detail":"Not Found"}` — Starlette's unmatched-path body
 *     Nest           `Cannot GET /…` — RAW, and also wrapped in Nest's JSON envelope:
 *                    `{"message":"Cannot GET /…","error":"Not Found","statusCode":404}`
 *
 * A handler that means "absent" says so in the service's own vocabulary — glossary answers
 * `{"code":"GLOSS_NOT_FOUND","message":"entity not found in this book"}`, and that MUST keep
 * forwarding as a 404. The distinction is the whole point: one is about the caller's resource,
 * the other is about the KAL's own wiring.
 */
export function isUnroutedDownstream(body: string): boolean {
  const b = body.trim();
  return (
    b === '404 page not found' ||
    b.startsWith('404 page not found') ||
    /^\{"detail":\s*"Not Found"\}$/.test(b) ||
    /^Cannot (GET|POST|PUT|PATCH|DELETE) /.test(b) ||
    // T48av — Nest's ENVELOPE, measured live on the iso gateway 2026-08-30:
    //   {"message":"Cannot GET /no-such-route","error":"Not Found","statusCode":404}
    // The raw needle above requires the body to START with `Cannot`, so this form did not
    // match and a KAL route federating to an unbuilt Nest path would have forwarded a 404 —
    // the exact lie T55b fixed, surviving for one of the three frameworks the list names.
    // Latent rather than live: the KAL federates to FastAPI and Go services today.
    //
    // Still precise: a handler that means "absent" answers in its own vocabulary
    // (`GLOSS_NOT_FOUND`), never with `"message":"Cannot <VERB> /"`.
    /"message"\s*:\s*"Cannot (GET|POST|PUT|PATCH|DELETE) \//.test(b)
  );
}
