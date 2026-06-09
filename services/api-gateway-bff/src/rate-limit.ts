import type { Request, Response, NextFunction } from 'express';

type Entry = { count: number; windowStart: number };

const buckets = new Map<string, Entry>();

function clientIp(req: Request): string {
  if (process.env.TRUST_PROXY === 'true') {
    const xff = req.headers['x-forwarded-for'];
    if (typeof xff === 'string' && xff.length > 0) {
      return xff.split(',')[0].trim();
    }
  }
  return req.socket.remoteAddress ?? 'unknown';
}

export function createRateLimitMiddleware(opts: {
  windowMs: number;
  max: number;
  keyPrefix: string;
  pathPrefix: string;
}): (req: Request, res: Response, next: NextFunction) => void {
  const { windowMs, max, keyPrefix, pathPrefix } = opts;
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.path.startsWith(pathPrefix)) {
      return next();
    }
    const key = `${keyPrefix}:${clientIp(req)}`;
    const now = Date.now();
    let entry = buckets.get(key);
    if (!entry || now - entry.windowStart >= windowMs) {
      entry = { count: 1, windowStart: now };
      buckets.set(key, entry);
      return next();
    }
    if (entry.count >= max) {
      res.setHeader('Retry-After', String(Math.ceil(windowMs / 1000)));
      res.status(429).json({
        code: 'BFF_RATE_LIMITED',
        message: 'Too many requests',
      });
      return;
    }
    entry.count++;
    return next();
  };
}

export function resolveBffRateLimit(): { windowMs: number; max: number } {
  const windowSec = parseInt(process.env.BFF_RATE_LIMIT_WINDOW_SECONDS || '60', 10);
  const max = parseInt(process.env.BFF_RATE_LIMIT_MAX_REQUESTS || '120', 10);
  return {
    windowMs: (Number.isFinite(windowSec) && windowSec > 0 ? windowSec : 60) * 1000,
    max: Number.isFinite(max) && max > 0 ? max : 120,
  };
}
