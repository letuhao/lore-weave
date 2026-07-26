import { createHmac } from 'node:crypto';
import { ForbiddenException, UnauthorizedException } from '@nestjs/common';
import { verifyHs256 } from '../src/auth/jwt.js';
import { KalAuthGuard } from '../src/auth/kal-auth.guard.js';
import { resetConfigForTest } from '../src/config/config.js';

const SECRET = 'test_secret_at_least_32_chars_long_xx';

function b64url(buf: Buffer | string): string {
  return Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Mint an HS256 JWT for tests (no external lib — mirror the verifier). */
function mintJwt(payload: Record<string, unknown>, secret = SECRET, alg = 'HS256'): string {
  const header = b64url(JSON.stringify({ alg, typ: 'JWT' }));
  const body = b64url(JSON.stringify(payload));
  const sig =
    alg === 'none'
      ? ''
      : b64url(createHmac('sha256', secret).update(`${header}.${body}`).digest());
  return `${header}.${body}.${sig}`;
}

function ctx(req: unknown) {
  return { switchToHttp: () => ({ getRequest: () => req }) } as never;
}

describe('verifyHs256', () => {
  const future = Math.floor(Date.now() / 1000) + 3600;

  it('accepts a valid token and returns sub', () => {
    expect(verifyHs256(mintJwt({ sub: 'user-1', exp: future }), SECRET)).toBe('user-1');
  });
  it('rejects a wrong-secret signature', () => {
    expect(verifyHs256(mintJwt({ sub: 'user-1', exp: future }, 'other_secret'), SECRET)).toBeNull();
  });
  it('rejects alg=none (alg confusion)', () => {
    expect(verifyHs256(mintJwt({ sub: 'user-1', exp: future }, SECRET, 'none'), SECRET)).toBeNull();
  });
  it('rejects an expired token', () => {
    const past = Math.floor(Date.now() / 1000) - 10;
    expect(verifyHs256(mintJwt({ sub: 'user-1', exp: past }), SECRET)).toBeNull();
  });
  it('rejects a malformed token / empty / no-sub', () => {
    expect(verifyHs256('not.a.jwt.x', SECRET)).toBeNull();
    expect(verifyHs256(undefined, SECRET)).toBeNull();
    expect(verifyHs256(mintJwt({ exp: future }), SECRET)).toBeNull();
  });
  it('rejects when secret is empty (user mode disabled)', () => {
    expect(verifyHs256(mintJwt({ sub: 'u', exp: future }), '')).toBeNull();
  });
});

describe('KalAuthGuard dual-auth', () => {
  const guard = new KalAuthGuard();
  const future = Math.floor(Date.now() / 1000) + 3600;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'svc-token';
    process.env.JWT_SECRET = SECRET;
    process.env.BOOK_SERVICE_URL = 'http://book-service:8082';
    resetConfigForTest();
    fetchMock = jest.fn();
    (globalThis as { fetch: unknown }).fetch = fetchMock;
  });

  it('SERVICE mode: a valid internal token is allowed without a grant check', async () => {
    const req = { headers: { 'x-internal-token': 'svc-token' }, params: { bookId: 'b1' } };
    await expect(guard.canActivate(ctx(req))).resolves.toBe(true);
    expect(fetchMock).not.toHaveBeenCalled(); // service caller is trusted
  });

  it('USER mode: valid JWT + a grant pins kalUserId from the token (anti-spoof)', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ grant_level: 'view', lifecycle_state: 'active' }),
    });
    const req: Record<string, unknown> = {
      headers: { authorization: `Bearer ${mintJwt({ sub: 'real-user', exp: future })}`, 'x-user-id': 'spoofed' },
      params: { bookId: 'b1' },
    };
    await expect(guard.canActivate(ctx(req))).resolves.toBe(true);
    expect(req.kalUserId).toBe('real-user'); // from JWT, NOT the spoofed header
  });

  it('USER mode: valid JWT but NO grant → 403', async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) }); // 404 no grant
    const req = {
      headers: { authorization: `Bearer ${mintJwt({ sub: 'u', exp: future })}` },
      params: { bookId: 'b1' },
    };
    await expect(guard.canActivate(ctx(req))).rejects.toBeInstanceOf(ForbiddenException);
  });

  it('USER mode: grant_level none → 403', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ grant_level: 'none' }) });
    const req = {
      headers: { authorization: `Bearer ${mintJwt({ sub: 'u', exp: future })}` },
      params: { bookId: 'b1' },
    };
    await expect(guard.canActivate(ctx(req))).rejects.toBeInstanceOf(ForbiddenException);
  });

  it('neither a valid token nor a valid JWT → 401', async () => {
    const req = { headers: { authorization: 'Bearer garbage' }, params: { bookId: 'b1' } };
    await expect(guard.canActivate(ctx(req))).rejects.toBeInstanceOf(UnauthorizedException);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('book-service unreachable during grant check → fail closed (403)', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED'));
    const req = {
      headers: { authorization: `Bearer ${mintJwt({ sub: 'u', exp: future })}` },
      params: { bookId: 'b1' },
    };
    await expect(guard.canActivate(ctx(req))).rejects.toBeInstanceOf(ForbiddenException);
  });
});
