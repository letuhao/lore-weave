import { createRateLimitMiddleware } from '../src/rate-limit';
import type { Request, Response, NextFunction } from 'express';

function mockReq(path: string, ip = '1.2.3.4'): Request {
  return {
    path,
    headers: {},
    socket: { remoteAddress: ip },
  } as Request;
}

function mockRes(): Response & { statusCode: number; body?: unknown } {
  const res = {
    statusCode: 200,
    body: undefined as unknown,
    setHeader: jest.fn(),
    status(code: number) {
      this.statusCode = code;
      return this;
    },
    json(payload: unknown) {
      this.body = payload;
      return this;
    },
  };
  return res as unknown as Response & { statusCode: number; body?: unknown };
}

describe('BFF rate limit', () => {
  it('allows requests under the limit', () => {
    const mw = createRateLimitMiddleware({
      windowMs: 60_000,
      max: 5,
      keyPrefix: 'test',
      pathPrefix: '/v1/auth',
    });
    const next = jest.fn();
    for (let i = 0; i < 5; i++) {
      mw(mockReq('/v1/auth/login'), mockRes(), next as NextFunction);
    }
    expect(next).toHaveBeenCalledTimes(5);
  });

  it('returns 429 when over the limit', () => {
    const mw = createRateLimitMiddleware({
      windowMs: 60_000,
      max: 2,
      keyPrefix: 'test2',
      pathPrefix: '/v1/auth',
    });
    const next = jest.fn();
    mw(mockReq('/v1/auth/login', '9.9.9.9'), mockRes(), next as NextFunction);
    mw(mockReq('/v1/auth/login', '9.9.9.9'), mockRes(), next as NextFunction);
    const res = mockRes();
    mw(mockReq('/v1/auth/login', '9.9.9.9'), res, next as NextFunction);
    expect(res.statusCode).toBe(429);
  });

  it('skips paths outside prefix', () => {
    const mw = createRateLimitMiddleware({
      windowMs: 60_000,
      max: 1,
      keyPrefix: 'test3',
      pathPrefix: '/v1/auth',
    });
    const next = jest.fn();
    mw(mockReq('/health'), mockRes(), next as NextFunction);
    expect(next).toHaveBeenCalledTimes(1);
  });
});
